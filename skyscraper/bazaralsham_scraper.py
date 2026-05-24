#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BazarAlsham (syriacar.net) Scraper
====================================
Scrapes car listings from https://syriacar.net/, uploads images to Google Drive,
and writes all data to Google Sheets.

Auth: OAuth2 user credentials — images owned by you, no quota errors.

USAGE
-----
  python bazaralsham_scraper.py --full          # scrape all pages
  python bazaralsham_scraper.py --pages 3       # scrape first 3 pages (~60 cars)
  python bazaralsham_scraper.py --repair-images # re-upload failed Drive images
"""

import argparse
import io
import json
import logging
import os
import random
import re
import sys
import time
from pathlib import Path
from typing import Optional, List
from datetime import datetime, timedelta

import gspread
import requests
from normalizer import normalize_car
from bs4 import BeautifulSoup
from google.auth.transport.requests import Request
from google.oauth2 import credentials as google_creds_module
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

sys.stdout.reconfigure(encoding='utf-8')

# ── Config ────────────────────────────────────────────────────────────────────

BASE_URL        = 'https://syriacar.net'
LOAD_MORE_URL   = f'{BASE_URL}/load-more-cars'

SHEET_ID        = '1PGgXN4EG-DLXQGwYagQt3dEAvj17NRTYQBapjfzeVuM'
DRIVE_FOLDER_ID = '1767SxfoN0gLzqhwsHgET7yAU9KUE7iTT'

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OAUTH_CLIENT_FILE = os.path.join(
    SCRIPT_DIR,
    'client_secret_798447276011-9bfpmjkfo8et8c2r4omri13kbh7h5202.apps.googleusercontent.com.json',
)
OAUTH_TOKEN_FILE = os.path.join(SCRIPT_DIR, 'oauth_token.json')

SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive',
]

DELAY_MIN = 1.5
DELAY_MAX = 3.0

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s  %(levelname)s  %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

# ── Sheet columns ─────────────────────────────────────────────────────────────

COLUMNS = [
    'id', 'source', 'car_url',
    'make', 'model', 'year', 'body_type',
    'exterior_color', 'interior_color',
    'fuel_type', 'engine_size', 'cylinders', 'horsepower',
    'transmission', 'doors', 'seats', 'steering_side',
    'origin', 'condition', 'chassis_condition', 'warranty', 'chassis_number',
    'city', 'mileage', 'price',
    'date_added', 'views',
    'phone', 'listing_id',
    'seller_name', 'seller_type', 'seller_listings',
    'description_original',
    'features', 'safety_features',
    'images_original_links', 'images_drive_links',
]

# ── OAuth2 ────────────────────────────────────────────────────────────────────

def get_oauth_credentials():
    creds = None
    if os.path.exists(OAUTH_TOKEN_FILE):
        try:
            with open(OAUTH_TOKEN_FILE) as fh:
                creds = google_creds_module.Credentials.from_authorized_user_info(
                    json.load(fh), SCOPES
                )
        except Exception as exc:
            logger.warning(f'Could not load cached token: {exc}')
            creds = None

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            logger.info('Refreshing OAuth2 token…')
            creds.refresh(Request())
        else:
            logger.info('No valid token — launching browser consent flow…')
            flow = InstalledAppFlow.from_client_secrets_file(OAUTH_CLIENT_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(OAUTH_TOKEN_FILE, 'w') as fh:
            fh.write(creds.to_json())

    return creds


# ── HTTP session ──────────────────────────────────────────────────────────────

def make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        'User-Agent': random.choice([
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/123.0.0.0',
        ]),
        'Accept-Language': 'ar,en;q=0.9',
        'Referer': BASE_URL,
    })
    return s


def get_csrf_token(session: requests.Session) -> str:
    """Fetch homepage and extract CSRF token."""
    r = session.get(BASE_URL, timeout=20)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, 'html.parser')
    meta = soup.find('meta', {'name': 'csrf-token'})
    token = meta['content'] if meta else ''
    session.headers['X-CSRF-TOKEN'] = token
    session.headers['Accept'] = 'application/json'
    logger.info(f'CSRF token: {token[:20]}…')
    return token


# ── Listing page scraping ─────────────────────────────────────────────────────

def parse_cards(html: str) -> list:
    """Parse car cards from listing HTML (either full page or load-more response)."""
    soup = BeautifulSoup(html, 'html.parser')
    cards = soup.select('div.car-card')
    results = []
    for card in cards:
        try:
            # URL
            share_btn = card.select_one('button.sharing[data-link]')
            url = share_btn['data-link'].strip() if share_btn else ''

            # Numeric ID
            bm = card.select_one('button.bookmark[data-car-id]')
            car_id = bm['data-car-id'].strip() if bm else ''

            # Make
            make_el = card.select_one('h1.car-title')
            make = make_el.get_text(strip=True) if make_el else ''

            # Model / body / year from h2
            sub_el = card.select_one('h2.car-sub-title')
            model = body_type = year = ''
            if sub_el:
                parts = [p.strip() for p in sub_el.get_text(separator='•').split('•') if p.strip()]
                if len(parts) >= 1: model     = parts[0]
                if len(parts) >= 2: body_type = parts[1]
                if len(parts) >= 3: year      = parts[2]

            # Features-a: mileage + city
            feat_a = card.select_one('div.features-a')
            mileage = city = ''
            if feat_a:
                km_el = feat_a.select_one('div.div-features-padding p')
                mileage = _strip_km(km_el.get_text(strip=True)) if km_el else ''
                city_els = feat_a.select('div > span')
                city = city_els[-1].get_text(strip=True) if city_els else ''

            # Features-b: fuel + origin
            feat_b = card.select_one('div.features-b')
            fuel = origin = ''
            if feat_b:
                spans = feat_b.select('span')
                if spans: fuel   = spans[0].get_text(strip=True)
                if len(spans) > 1: origin = spans[1].get_text(strip=True)

            # Features-c: transmission + condition
            feat_c = card.select_one('div.features-c')
            transmission = condition = ''
            if feat_c:
                spans = feat_c.select('span')
                if spans: transmission = spans[0].get_text(strip=True)
                if len(spans) > 1: condition   = spans[1].get_text(strip=True)

            # Price
            price_btn = card.select_one('button#request-price')
            price_text = price_btn.get_text(strip=True) if price_btn else ''
            price = _parse_price(price_text)

            # Card-level images
            imgs = [img['src'] for img in card.select('div.cars-images img') if img.get('src')]

            results.append({
                'id': car_id,
                'car_url': url,
                'make': make,
                'model': model,
                'body_type': body_type,
                'year': year,
                'mileage': mileage,
                'city': city,
                'fuel_type': fuel,
                'origin': origin,
                'transmission': transmission,
                'condition': condition,
                'price': price,
                '_card_images': imgs,
            })
        except Exception as exc:
            logger.warning(f'  Card parse error: {exc}')
    return results


def _parse_price(text: str) -> str:
    """Extract raw price digits from 'السعر 11,800 دولار'. Returns e.g. '11800'."""
    text = text.replace('السعر', '').strip()
    m = re.search(r'([\d,]+)', text)
    if not m:
        return ''
    return m.group(1).replace(',', '')


def _strip_km(text: str) -> str:
    """Remove Arabic 'كم' suffix and extra whitespace from mileage."""
    return re.sub(r'\s*كم\s*$', '', text.strip()).strip()


def fetch_all_listings(session: requests.Session, max_pages: Optional[int] = None) -> list:
    """Fetch all car listings using the load-more API."""
    logger.info('Fetching homepage (page 1)…')
    r = session.get(BASE_URL, timeout=20)
    r.raise_for_status()
    cars = parse_cards(r.text)
    logger.info(f'  Page 1: {len(cars)} cars')

    page = 1
    while True:
        if max_pages and page >= max_pages:
            break
        try:
            resp = session.post(
                LOAD_MORE_URL,
                data={'page': page},
                timeout=20,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            logger.warning(f'  Load-more page {page} failed: {exc}')
            break

        if not data.get('success') or not data.get('hasMore') or not data.get('html'):
            logger.info(f'  No more pages after page {page}.')
            break

        new_cars = parse_cards(data['html'])
        cars.extend(new_cars)
        page += 1
        logger.info(f'  Page {page}: +{len(new_cars)} cars  (total {len(cars)})')
        time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))

    return cars


# ── Detail page scraping ──────────────────────────────────────────────────────

def _spec_pairs(soup: BeautifulSoup, container_class: str) -> dict:
    """Extract label→value pairs from accordion spec columns."""
    container = soup.select_one(f'div.{container_class}')
    if not container:
        return {}
    uls = container.select('ul')
    if len(uls) < 2:
        return {}
    labels = [li.get_text(strip=True) for li in uls[0].select('li')]
    values = [li.get_text(strip=True) for li in uls[1].select('li.li-1-details-color')]
    return dict(zip(labels, values))


# Keywords that identify a safety-feature section (Arabic + English)
_SAFETY_KEYWORDS = ['أمان', 'سلامة', 'safety']
# Keywords that identify any generic feature/specs section
_FEATURE_KEYWORDS = ['مواصفات', 'ميزات', 'المواصفات', 'الخارجية', 'الراحة', 'التقنية']


def _extract_features(soup: BeautifulSoup) -> tuple:
    """
    Extract feature lists from bazaralsham/syriacar.net detail pages.
    Looks for accordion sections beyond the two main spec-pair columns
    (box-accordion-1-right / box-accordion-1-left).

    Returns (features_str, safety_features_str) where items are pipe-separated:
        "فتحة سقف|مقاعد جلد|نظام ملاحة"

    If the site doesn't have separate feature sections the strings are empty.
    """
    features: list = []
    safety_features: list = []

    # ── Method 1: accordion divs (box-accordion-2, box-accordion-3, …) ────────
    for section in soup.select('div[class*="box-accordion"]'):
        classes = ' '.join(section.get('class', []))
        if 'box-accordion-1' in classes:
            continue  # already handled as label:value spec pairs

        items = [li.get_text(strip=True) for li in section.select('li')
                 if li.get_text(strip=True)]
        if not items:
            continue

        # Determine category from a nearby heading
        heading_el = (
            section.select_one('h2, h3, h4, .section-header, .accordion-header')
            or section.find_previous_sibling(['h2', 'h3', 'h4'])
        )
        heading_text = heading_el.get_text(strip=True) if heading_el else ''

        if any(kw in heading_text for kw in _SAFETY_KEYWORDS):
            safety_features.extend(items)
        else:
            features.extend(items)

    # ── Method 2: headings + following UL (fallback for flat page layouts) ────
    if not features and not safety_features:
        for header in soup.find_all(['h2', 'h3', 'h4', 'p', 'span'], string=True):
            text = header.get_text(strip=True)
            if not text:
                continue
            is_safety   = any(kw in text for kw in _SAFETY_KEYWORDS)
            is_features = any(kw in text for kw in _FEATURE_KEYWORDS)
            if not (is_safety or is_features):
                continue

            # Grab the next UL (sibling or inside the next sibling)
            nxt = header.find_next_sibling('ul')
            if not nxt:
                parent_nxt = header.parent.find_next_sibling()
                if parent_nxt:
                    nxt = parent_nxt.find('ul')

            if nxt:
                items = [li.get_text(strip=True) for li in nxt.select('li')
                         if li.get_text(strip=True)]
                if is_safety:
                    safety_features.extend(items)
                elif items:
                    features.extend(items)

    # Deduplicate while preserving insertion order
    def _dedup(lst: list) -> list:
        seen: set = set()
        out: list = []
        for x in lst:
            if x not in seen:
                seen.add(x)
                out.append(x)
        return out

    return '|'.join(_dedup(features)), '|'.join(_dedup(safety_features))


def scrape_detail(session: requests.Session, url: str) -> dict:
    """Scrape full detail page for a car."""
    data = {}
    try:
        r = session.get(url, timeout=25)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, 'html.parser')

        # ── JSON-LD (fast baseline) ──────────────────────────────────────────
        ld = soup.find('script', type='application/ld+json')
        if ld:
            try:
                j = json.loads(ld.string)
                data['make']         = j.get('brand', '')
                data['model']        = j.get('model', '')
                data['year']         = j.get('vehicleModelDate', '')
                data['body_type']    = j.get('bodyType', '')
                data['exterior_color'] = j.get('color', '')
                data['transmission'] = j.get('vehicleTransmission', '')
                data['fuel_type']    = j.get('fuelType', '')
                offer = j.get('offers', {})
                raw_price = str(offer.get('price', '')).replace(',', '')
                data['price'] = raw_price
            except Exception:
                pass

        # ── Accordion spec pairs ─────────────────────────────────────────────
        right = _spec_pairs(soup, 'box-accordion-1-right')
        left  = _spec_pairs(soup, 'box-accordion-1-left')

        data['make']             = right.get('نوع المركبة',    data.get('make', ''))
        data['body_type']        = right.get('جسم المركبة',    data.get('body_type', ''))
        data['exterior_color']   = right.get('اللون الخارجي', data.get('exterior_color', ''))
        data['fuel_type']        = right.get('نوع الوقود',     data.get('fuel_type', ''))
        data['engine_size']      = right.get('سعة المحرك',    '')
        data['cylinders']        = right.get('عدد الأسطوانات','')
        data['doors']            = right.get('عدد الأبواب',   '')
        data['steering_side']    = right.get('جهة القيادة',   '')
        data['chassis_condition']= right.get('حالة الهيكل',   '')

        data['model']            = left.get('موديل المركبة',  data.get('model', ''))
        data['transmission']     = left.get('ناقل الحركة',    data.get('transmission', ''))
        data['interior_color']   = left.get('اللون الداخلي', '')
        data['horsepower']       = left.get('قوة الحصان',    '')
        data['origin']           = left.get('الوارد الإقليمي','')
        data['seats']            = left.get('عدد المقاعد',   '')
        data['condition']        = left.get('حالة المركبة',  data.get('condition', ''))
        data['warranty']         = left.get('الضمان',        '')
        data['chassis_number']   = left.get('رقم الهيكل',    '')

        # ── Date published ───────────────────────────────────────────────────
        date_box = soup.select_one('div.box-banner-car-view-date')
        if date_box:
            spans = date_box.select('span')
            for sp in spans:
                txt = sp.get_text(strip=True)
                m = re.search(r'(\d{2}-\d{2}-\d{4})', txt)
                if m:
                    parts = m.group(1).split('-')
                    data['date_added'] = f'{parts[2]}-{parts[1]}-{parts[0]}'
                    break
            for sp in spans:
                m = re.search(r'المشاهدين[:\s]*(\d+)', sp.get_text())
                if m:
                    data['views'] = m.group(1)
                    break

        # ── Description (seller notes) ───────────────────────────────────────
        desc_el = soup.select_one('div.description-car-details, div.car-description, div.notes-section')
        if desc_el:
            data['description_original'] = desc_el.get_text(separator=' ', strip=True)
        else:
            title_el = soup.select_one('h1.sub-container-title')
            data['description_original'] = title_el.get_text(strip=True) if title_el else ''

        # ── Images ───────────────────────────────────────────────────────────
        imgs = [img['src'] for img in soup.select('div.container-images-album img') if img.get('src')]
        if not imgs:
            og = soup.find('meta', property='og:image')
            if og and og.get('content'):
                imgs = [og['content']]
        data['_images'] = imgs

        # ── City / mileage from quick-bar ────────────────────────────────────
        city_el = soup.select_one('span.text-details-4')
        if city_el:
            data.setdefault('city', city_el.get_text(strip=True))
        km_el = soup.select_one('span.text-details-3')
        if km_el:
            data.setdefault('mileage', _strip_km(km_el.get_text(strip=True)))

        # ── Phone number ─────────────────────────────────────────────────────
        call_link = soup.select_one('a#direct-call[href^="tel:"]')
        if call_link:
            data['phone'] = call_link['href'].replace('tel:', '').strip()
        else:
            m = re.search(r"let phone\s*=\s*'([^']+)'", r.text)
            if m:
                data['phone'] = m.group(1)

        # ── Short listing ID ─────────────────────────────────────────────────
        id_el = soup.select_one('span.span-copy-id-code')
        if id_el:
            data['listing_id'] = id_el.get_text(strip=True).replace('ID:', '').replace('ID :', '').strip()

        # ── Seller info ──────────────────────────────────────────────────────
        seller_name_el = soup.select_one('div.div-box-border-username p')
        if seller_name_el:
            data['seller_name'] = seller_name_el.get_text(strip=True)
        sel1 = soup.select_one('span.span-seller-details-1')
        data['seller_type'] = sel1.get_text(strip=True) if sel1 else ''
        seller_listings_el = soup.select_one('span.span-seller-details-2')
        if seller_listings_el:
            m = re.search(r'(\d+)', seller_listings_el.get_text())
            data['seller_listings'] = m.group(1) if m else ''

        # ── Feature lists (ROADMAP §8) ────────────────────────────────────────
        feats, safety_feats = _extract_features(soup)
        data['features']        = feats
        data['safety_features'] = safety_feats

    except Exception as exc:
        logger.warning(f'  Detail scrape error ({url[-50:]}): {exc}')

    return data


# ── Google Drive ──────────────────────────────────────────────────────────────

def upload_image_to_drive(drive_svc, img_url: str, filename: str, folder_id: str) -> str:
    """Download image and upload to Drive. Returns webViewLink or ''."""
    try:
        r = requests.get(img_url, timeout=20, headers={
            'User-Agent': 'Mozilla/5.0',
            'Referer': BASE_URL,
        })
        r.raise_for_status()
    except Exception as exc:
        logger.warning(f'    Image download failed ({img_url[-60:]}): {exc}')
        return ''
    try:
        mime = r.headers.get('Content-Type', 'image/webp').split(';')[0]
        media = MediaIoBaseUpload(io.BytesIO(r.content), mimetype=mime)
        f = drive_svc.files().create(
            body={'name': filename, 'parents': [folder_id]},
            media_body=media,
            fields='id,webViewLink',
        ).execute()
        drive_svc.permissions().create(
            fileId=f['id'],
            body={'type': 'anyone', 'role': 'reader'},
        ).execute()
        return f.get('webViewLink', '')
    except Exception as exc:
        logger.warning(f'    Drive upload failed ({filename}): {exc}')
        return ''


# ── Google Sheets (gspread) ───────────────────────────────────────────────────

class SheetManager:
    def __init__(self, gc):
        self.ws = gc.open_by_key(SHEET_ID).sheet1
        self._existing_ids: set = set()
        self._ensure_header()
        self._load_existing_ids()

    def _ensure_header(self):
        first = self.ws.row_values(1)
        if not first:
            self.ws.insert_row(COLUMNS, 1)
            return
        if first == COLUMNS:
            return
        # Non-destructive path: existing header is a subset of COLUMNS
        # (columns were added to COLUMNS but the sheet still has the old header).
        existing = set(first)
        new_cols = [c for c in COLUMNS if c not in existing]
        if new_cols and all(c in COLUMNS for c in first):
            next_col = len(first) + 1
            for col_name in new_cols:
                self.ws.update_cell(1, next_col, col_name)
                next_col += 1
            logger.info(f'Sheet header extended — added columns: {new_cols}')
        else:
            # Major schema mismatch (e.g. fresh sheet or corrupted header) — reset
            logger.warning('Header mismatch — clearing sheet and rewriting header')
            self.ws.clear()
            self.ws.insert_row(COLUMNS, 1)

    def _load_existing_ids(self):
        vals = self.ws.col_values(1)  # column A = id
        self._existing_ids = set(vals[1:])  # skip header
        logger.info(f'Sheet has {len(self._existing_ids)} existing cars.')

    def exists(self, car_id: str) -> bool:
        return str(car_id) in self._existing_ids

    def append_row(self, car: dict):
        row = [str(car.get(col, '')) for col in COLUMNS]
        self.ws.append_row(row, value_input_option='RAW')
        self._existing_ids.add(str(car.get('id', '')))

    def sort_by_date(self):
        """Sort sheet by date_added descending (newest first), keep header."""
        logger.info('Sorting sheet by date_added (newest first)…')
        try:
            date_col = COLUMNS.index('date_added')
            self.ws.spreadsheet.batch_update({'requests': [{
                'sortRange': {
                    'range': {
                        'sheetId': self.ws.id,
                        'startRowIndex': 1,
                    },
                    'sortSpecs': [{
                        'dimensionIndex': date_col,
                        'sortOrder': 'DESCENDING',
                    }],
                }
            }]})
            logger.info('Sheet sorted.')
        except Exception as exc:
            logger.warning(f'Could not sort sheet: {exc}')

    def get_all_rows(self) -> list:
        all_values = self.ws.get_all_values()
        if not all_values:
            return []
        header = all_values[0]
        return [
            {'_row_num': i + 2, **dict(zip(header, row))}
            for i, row in enumerate(all_values[1:])
        ]

    def update_cell(self, row_num: int, col_name: str, value: str):
        col_idx = COLUMNS.index(col_name) + 1  # gspread is 1-indexed
        self.ws.update_cell(row_num, col_idx, value)


# ── Main scraper class ────────────────────────────────────────────────────────

class BazarAlshamScraper:
    def __init__(self):
        logger.info('Authenticating with Google (OAuth2)…')
        creds = get_oauth_credentials()
        self.drive  = build('drive',  'v3', credentials=creds)
        gc          = gspread.authorize(creds)
        self.sheet  = SheetManager(gc)
        self.session = make_session()
        get_csrf_token(self.session)

    def _process_card(self, card: dict, idx: int) -> bool:
        """Scrape detail, upload images, write to sheet. Returns True if written."""
        car_id  = str(card.get('id', ''))
        car_url = card.get('car_url', '')
        if not car_id or not car_url:
            return False
        if self.sheet.exists(car_id):
            logger.info(f'  [{idx}] {car_id} — already in sheet, skip')
            return False

        logger.info(f'  [{idx}] {car_id} — {car_url[-55:]}')

        detail = scrape_detail(self.session, car_url)
        car = {**card, **detail}
        car['source']  = 'bazaralsham'
        car['car_url'] = car_url

        img_urls = detail.get('_images') or card.get('_card_images', [])
        drive_links = []
        for i, img_url in enumerate(img_urls, 1):
            ext = img_url.split('.')[-1].split('?')[0] or 'webp'
            filename = f'bazaralsham_{car_id}_{i:02d}.{ext}'
            link = upload_image_to_drive(self.drive, img_url, filename, DRIVE_FOLDER_ID)
            if link:
                drive_links.append(link)
                logger.info(f'    Image {i}: uploaded ✓')
            time.sleep(0.3)

        car['images_original_links'] = ', '.join(img_urls)
        car['images_drive_links']    = ', '.join(drive_links)

        # Normalize fields to sayarti canonical values
        car = normalize_car(car)

        self.sheet.append_row(car)
        logger.info(f'    ✓ Written to sheet')
        return True

    def run(self, max_pages: Optional[int] = None, max_hours: Optional[float] = None):
        logger.info('=== BazarAlsham Scraper — FULL RUN ===')

        deadline = None
        if max_hours:
            deadline = datetime.now() + timedelta(hours=max_hours)
            logger.info(f'Time limit: {max_hours}h — will stop at {deadline.strftime("%H:%M:%S")}')

        new_count  = 0
        total_seen = 0
        stopped    = False

        # ── Page 1 (homepage, server-rendered) ────────────────────────────────
        logger.info('Fetching page 1 (homepage)…')
        r = self.session.get(BASE_URL, timeout=20)
        r.raise_for_status()
        page1_cards = parse_cards(r.text)
        logger.info(f'Page 1: {len(page1_cards)} cards — scraping now…')
        for card in page1_cards:
            if deadline and datetime.now() >= deadline:
                stopped = True; break
            total_seen += 1
            if self._process_card(card, total_seen):
                new_count += 1
                time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))

        # ── Pages 2+ (load-more API) ───────────────────────────────────────────
        page = 1
        while not stopped:
            if max_pages and page >= max_pages:
                break
            try:
                resp = self.session.post(LOAD_MORE_URL, data={'page': page}, timeout=20)
                resp.raise_for_status()
                data = resp.json()
            except Exception as exc:
                logger.warning(f'Load-more page {page} failed: {exc}')
                break

            if not data.get('success') or not data.get('html'):
                logger.info(f'No more pages after page {page}.')
                break

            cards = parse_cards(data['html'])
            page += 1
            logger.info(f'Page {page}: {len(cards)} cards — scraping now…')

            for card in cards:
                if deadline and datetime.now() >= deadline:
                    stopped = True; break
                total_seen += 1
                if self._process_card(card, total_seen):
                    new_count += 1
                    time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))

            if not data.get('hasMore'):
                logger.info('No more pages.')
                break

        if stopped:
            logger.info(f'⏰ Time limit reached after {new_count} new cars.')

        self.sheet.sort_by_date()

        logger.info('=' * 56)
        logger.info(f'Done. New cars added: {new_count}  (seen {total_seen} total)')
        logger.info('=' * 56)

    def repair_images(self):
        """Re-upload images for cars with empty images_drive_links."""
        logger.info('=== Repair Images Mode ===')
        rows = self.sheet.get_all_rows()
        repaired = 0
        for row in rows:
            if row.get('images_drive_links'):
                continue
            orig_links = row.get('images_original_links', '')
            if not orig_links:
                continue
            row_num = row['_row_num']
            car_id  = row.get('id', str(row_num))
            logger.info(f'Repairing images for car {car_id}…')
            img_urls = [u.strip() for u in orig_links.split(',') if u.strip()]
            drive_links = []
            for j, img_url in enumerate(img_urls, 1):
                ext = img_url.split('.')[-1].split('?')[0] or 'webp'
                filename = f'bazaralsham_{car_id}_{j:02d}.{ext}'
                link = upload_image_to_drive(self.drive, img_url, filename, DRIVE_FOLDER_ID)
                if link:
                    drive_links.append(link)
                time.sleep(0.3)
            if drive_links:
                self.sheet.update_cell(row_num, 'images_drive_links', ', '.join(drive_links))
                repaired += 1
                logger.info(f'  ✓ {len(drive_links)} images uploaded')
        logger.info(f'Repair complete. {repaired} cars fixed.')

    def repair_data(self):
        """Normalize all existing rows using sayarti canonical values."""
        logger.info('=== Repair Data Mode (normalize all fields) ===')
        rows = self.sheet.get_all_rows()
        fixed = 0
        NORMALIZABLE = [
            'price', 'engine_size', 'mileage', 'year', 'seats', 'horsepower',
            'cylinders', 'doors', 'fuel_type', 'transmission', 'origin',
            'body_type', 'city', 'exterior_color', 'interior_color', 'condition',
            'make', 'model',
        ]
        for row in rows:
            row_num = row['_row_num']
            car_id  = row.get('id', str(row_num))
            updates = {}
            normalized = normalize_car(row)
            for col in NORMALIZABLE:
                old = row.get(col, '')
                new = normalized.get(col, '')
                if new != old:
                    updates[col] = new
            if updates:
                # Batch all column updates for this row into one API call
                batch = []
                for col, val in updates.items():
                    col_idx = COLUMNS.index(col) + 1
                    col_letter = chr(ord('A') + col_idx - 1)
                    batch.append({
                        'range': f'{col_letter}{row_num}',
                        'values': [[val]],
                    })
                self.sheet.ws.batch_update(batch, value_input_option='RAW')
                fixed += 1
                logger.info(f'  [{car_id}] {updates}')
                time.sleep(1.2)   # stay under 60 writes/min quota
        logger.info(f'Done. {fixed} rows updated.')


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == '__main__':
    if not os.path.exists(OAUTH_CLIENT_FILE):
        print(f'ERROR: OAuth2 client secret not found:\n  {OAUTH_CLIENT_FILE}')
        sys.exit(1)

    parser = argparse.ArgumentParser(description='BazarAlsham scraper')
    parser.add_argument('--full',    action='store_true', help='Scrape all pages')
    parser.add_argument('--pages',   type=int, default=None, metavar='N',
                        help='Max number of pages to scrape (each page ≈ 20 cars)')
    parser.add_argument('--hours',   type=float, default=None, metavar='H',
                        help='Stop after this many hours (e.g. --hours 1)')
    parser.add_argument('--repair-images', action='store_true',
                        help='Re-upload failed Drive images')
    parser.add_argument('--repair-data', action='store_true',
                        help='Fix price formatting and strip كم from mileage')
    args = parser.parse_args()

    scraper = BazarAlshamScraper()

    if args.repair_images:
        scraper.repair_images()
    elif args.repair_data:
        scraper.repair_data()
    else:
        max_pages = None if (args.full or args.hours) else (args.pages or 3)
        scraper.run(max_pages=max_pages, max_hours=args.hours)
