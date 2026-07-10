#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Doushesh Raw Data Scraper
=========================
Writes each car to:
  • rawdata_doushesh.jsonl  (local backup)
  • Google Sheet (set SHEET_ID below)

Strategy
--------
• requests + BeautifulSoup (site is server-rendered Livewire/Alpine.js)
• Initial page: GET https://doushesh.com/cars
• Pagination:   GET https://doushesh.com/livewire/load-more-ads?offset=N&url=https://doushesh.com/cars
• Detail page:  GET https://doushesh.com/listing/{slug}

Filters
-------
• Only cars with year >= 2015
• Only listings with تاريخ الإعلان in Jun-Jul 2026 (configurable)
• Cover image (from listing card) → dewatermark.ai → Google Drive

USAGE
-----
  python rawdata_doushesh.py
  python rawdata_doushesh.py --start-date 2026-06-01 --end-date 2026-07-31
  python rawdata_doushesh.py --dewatermark-key YOUR_KEY
"""

import argparse
import base64
import io
import json
import logging
import os
import re
import signal
import sys
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

import requests as req_lib
from bs4 import BeautifulSoup, NavigableString, Tag

import gspread
from google.auth.transport.requests import Request
from google.oauth2 import credentials as google_creds_module
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build as google_build
from googleapiclient.http import MediaIoBaseUpload

# ── Logging ───────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)-8s %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('rawdata_doushesh.log', encoding='utf-8'),
    ],
)
logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────────────

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

OAUTH_CLIENT_FILE = os.path.join(
    SCRIPT_DIR,
    'client_secret_798447276011-9bfpmjkfo8et8c2r4omri13kbh7h5202.apps.googleusercontent.com.json',
)
OAUTH_TOKEN_FILE = os.path.join(SCRIPT_DIR, 'oauth_token.json')

OUTPUT_FILE = os.path.join(SCRIPT_DIR, 'rawdata_doushesh.jsonl')

# ── Set your target Google Sheet ID here ──────────────────────────────────────
SHEET_ID = '1dlQIEsN87GXio0mh7nawVZyoM0v8cMLpDH5zMn7RfUw'

SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive',
]

SITE_URL       = 'https://doushesh.com'
LIST_URL       = 'https://doushesh.com/cars'
LOAD_MORE_URL  = 'https://doushesh.com/livewire/load-more-ads'
SOURCE         = 'doushesh'
BATCH_SIZE     = 10       # cards per load-more request
REQUEST_DELAY  = 1.5      # seconds between requests
STOP_OLD_PAGES = 3        # stop after N consecutive pages of all-old cars

DEWATERMARK_URL  = 'https://platform.dewatermark.ai/api/object_removal/v2/erase_watermark'
DRIVE_FOLDER_ID  = '1JrEXZVNlfL54Z22lRWtEDHkT4mnVNCIf'
MIN_YEAR         = 2015

# ── Sheet columns ─────────────────────────────────────────────────────────────

COLUMNS: List[str] = [
    'id', 'source', 'car_url', 'listing_id',
    'ad_title', 'listing_type',
    'make', 'model', 'year', 'condition',
    'exterior_color',
    'fuel_type', 'engine_size', 'engine_power', 'transmission',
    'body_type', 'drive_system',
    'warranty', 'seller_type',
    'city', 'mileage', 'price',
    'date_added', 'scraped_at',
    'phone', 'seller_name',
    'description',
    'interior_features', 'exterior_features', 'entertainment_features',
    'cover_image_url', 'image_clean_link',
]

# ── Arabic label → column name ────────────────────────────────────────────────

LABEL_MAP: Dict[str, str] = {
    'السعر':                'price',
    'الماركة':              'make',
    'الموديل':              'model',
    'المسافة المقطوعة':     'mileage',
    'الهيكل':               'body_type',
    'سنة التصنيع':          'year',
    'المحروقات':            'fuel_type',
    'ناقل السرعة':          'transmission',
    'الحالة':               'condition',
    'قوة المحرك':           'engine_power',
    'حجم المحرك':           'engine_size',
    'الدفع':                'drive_system',
    'اللون':                'exterior_color',
    'الكفالة':              'warranty',
    'المعلن':               'seller_type',
    'رقم الإعلان':          'listing_id',
    'تاريخ الإعلان':        'date_added',
}

FEATURE_SECTIONS = {
    'الميزات الداخلية':    'interior_features',
    'الميزات الخارجية':    'exterior_features',
    'الترفيه والشاشة':     'entertainment_features',
}

# Same "أخرى" variants used to replace with "غير ذلك" in non-make fields
_AKHRY = {'أخرى', 'أخري', 'اخرى', 'اخري'}

# ── Helpers ───────────────────────────────────────────────────────────────────


def _clean(v: Any) -> str:
    if v is None:
        return ''
    t = ' '.join(str(v).split())
    return '' if t in ('-', '—', '–', '', 'null', 'None') else t


def _clean_year(text: str) -> str:
    m = re.search(r'\b(19\d{2}|20\d{2})\b', str(text))
    return m.group(1) if m else ''


def _strip_km(text: str) -> str:
    return re.sub(r'\s*كم\s*$', '', str(text).strip()).strip()


def _strip_cc(text: str) -> str:
    return re.sub(r'\s*(?:CC|cc|سي\s+سي)\s*$', '', str(text).strip()).strip()


def _strip_hp(text: str) -> str:
    return re.sub(r'\s*حصان\s*$', '', str(text).strip()).strip()


def _parse_price(raw: str) -> str:
    if not raw:
        return ''
    digits = re.sub(r'[^\d.]', '', raw.replace(',', ''))
    try:
        n = float(digits)
        return str(int(n)) if n == int(n) else str(n)
    except (ValueError, TypeError):
        return digits


def _strip_bidi(text: str) -> str:
    """Strip Unicode bidirectional control characters (LRM, RLM, embeddings)."""
    return re.sub(r'[‎‏‪-‮⁦-⁩]', '', text).strip()


def _to_cell(v) -> str:
    if v is None:
        return ''
    if isinstance(v, list):
        return ', '.join(str(x) for x in v)
    return str(v)


def _has_class(tag: Tag, cls: str) -> bool:
    """Return True if `cls` is among the tag's CSS classes."""
    return cls in (tag.get('class') or [])


def _text(tag: Optional[Tag]) -> str:
    if tag is None:
        return ''
    return _clean(tag.get_text(separator=' ', strip=True))


# ── Google OAuth ──────────────────────────────────────────────────────────────


def _get_oauth_credentials():
    creds = None
    if os.path.exists(OAUTH_TOKEN_FILE):
        try:
            with open(OAUTH_TOKEN_FILE, encoding='utf-8') as fh:
                creds = google_creds_module.Credentials.from_authorized_user_info(
                    json.load(fh), SCOPES
                )
        except Exception as exc:
            logger.warning(f'Could not load token: {exc}')

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            logger.info('Refreshing OAuth2 token …')
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(OAUTH_CLIENT_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(OAUTH_TOKEN_FILE, 'w', encoding='utf-8') as fh:
            fh.write(creds.to_json())

    return creds


# ── JSONL backup ──────────────────────────────────────────────────────────────


def _append_jsonl(record: Dict):
    with open(OUTPUT_FILE, 'a', encoding='utf-8') as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + '\n')


# ── HTML parsing: listing cards ───────────────────────────────────────────────


def _parse_card(a: Tag) -> Optional[Dict]:
    """
    Parse a single car card <a data-ad-id="..."> from the listing page.
    Returns a partial dict (missing detail-page fields).
    """
    ad_id = (a.get('data-ad-id') or '').strip()
    href  = (a.get('href') or '').strip()
    if not ad_id or not href:
        return None

    # Slug = last path segment (or the whole path after /listing/)
    slug = href.rstrip('/').split('/listing/')[-1] if '/listing/' in href else ad_id

    # Cover image — inside .basis-[28%] div
    img_div = a.find('div', class_=lambda c: c and 'basis-[28%]' in (c if isinstance(c, str) else ' '.join(c)))
    cover_url = ''
    if img_div:
        img_tag = img_div.find('img')
        if img_tag:
            cover_url = (img_tag.get('src') or '').strip()
            if cover_url.startswith('%'):
                cover_url = ''  # URL-encoded local path from saved HTML — skip

    # Detail spans (background colour classes carry semantic meaning)
    spans = a.find_all('span', class_=lambda c: c and isinstance(c, list) and any(
        x in c for x in ('bg-custom_light_gray', 'bg-very_light_blue',
                          'bg-very_light_yellow', 'bg-very_light_green')
    ))

    make_model_raw = ''
    mileage_raw    = ''
    year_raw       = ''
    transmission   = ''

    for sp in spans:
        cls = sp.get('class') or []
        txt = _clean(sp.get_text(separator=' ', strip=True))
        if 'bg-custom_light_gray' in cls:
            make_model_raw = txt
        elif 'bg-very_light_blue' in cls:
            mileage_raw = txt
        elif 'bg-very_light_yellow' in cls:
            year_raw = txt
        elif 'bg-very_light_green' in cls:
            transmission = txt

    # make ‏> model — separator is ">" possibly preceded by a bidi control char
    make, model = '', ''
    if make_model_raw:
        sep_match = re.split(r'[^\S\r\n]*>[\s\xa0]*', make_model_raw, maxsplit=1)
        if len(sep_match) >= 2:
            make  = _strip_bidi(sep_match[0].strip())
            model = _strip_bidi(sep_match[1].strip())
        else:
            make = _strip_bidi(make_model_raw.strip())

    # Year: strip "موديل " prefix
    year = _clean_year(re.sub(r'^موديل\s*', '', year_raw))

    # Mileage: strip "كم" suffix
    mileage = _strip_km(mileage_raw)

    # Title from <h2>
    h2 = a.find('h2')
    ad_title = _text(h2)

    # City — small text span near location SVG (font-medium text-xs inside flex items-center)
    city = ''
    loc_span = a.find('span', class_=lambda c: c and isinstance(c, list)
                       and 'font-medium' in c and 'text-xs' in c)
    if loc_span:
        city = _clean(loc_span.get_text(strip=True))

    # Price — span.text-doush_blue
    price_span = a.find('span', class_=lambda c: c and isinstance(c, list)
                          and 'text-doush_blue' in c)
    price = _parse_price(_text(price_span)) if price_span else ''

    # Description snippet from the absolutely-positioned <p> inside the card
    desc_p = a.find('p', class_=lambda c: c and isinstance(c, list) and 'absolute' in c)
    description = _clean(desc_p.get_text(separator=' ', strip=True)) if desc_p else ''

    listing_type = 'للبيع'
    if ad_title and any(k in ad_title for k in ('إيجار', 'ايجار', 'للإيجار')):
        listing_type = 'للإيجار'

    return {
        'id':           f'doushesh_{ad_id}',
        'source':       SOURCE,
        'car_url':      href,
        'listing_id':   ad_id,
        'slug':         slug,
        'ad_title':     ad_title,
        'listing_type': listing_type,
        'make':         make,
        'model':        model,
        'year':         year,
        'mileage':      mileage,
        'transmission': transmission,
        'city':         city,
        'price':        price,
        'description':  description,
        'cover_image_url': cover_url,
    }


def _parse_cards_from_html(html: str) -> List[Dict]:
    """Parse all car cards from a page/fragment HTML string."""
    soup = BeautifulSoup(html, 'html.parser')
    cards = []
    for a in soup.find_all('a', attrs={'data-ad-id': True}):
        card = _parse_card(a)
        if card:
            cards.append(card)
    return cards


# ── HTML parsing: detail page ─────────────────────────────────────────────────


def _parse_detail(html: str) -> Dict:
    """
    Parse the detail page at https://doushesh.com/listing/{slug}.
    Returns a dict of additional fields that complement the listing card data.
    """
    soup = BeautifulSoup(html, 'html.parser')
    detail: Dict = {}

    # ── Spec table ────────────────────────────────────────────────────────────
    table = soup.find('table', class_=lambda c: c and 'w-full' in (c if isinstance(c, str) else ' '.join(c)))
    if table:
        for tr in table.find_all('tr'):
            tds = tr.find_all('td')
            if not tds:
                continue

            # Feature section row: colspan=2
            if tds[0].get('colspan') == '2':
                section_div = tds[0].find('div', class_=lambda c: c and 'py-1' in (c if isinstance(c, str) else ' '.join(c)))
                if not section_div:
                    continue
                section_name = _clean(section_div.get_text(strip=True)).rstrip(':').strip()
                col = FEATURE_SECTIONS.get(section_name)
                if not col:
                    continue
                checked = []
                grid = section_div.find_next_sibling('div')
                if not grid:
                    continue
                for feat_span in grid.find_all('span', class_=lambda c: c and isinstance(c, list)
                                               and 'flex' in c and 'items-center' in c):
                    # Checked if the inner circle span has bg-emerald-100
                    circle = feat_span.find('span', class_=lambda c: c and isinstance(c, list)
                                            and 'rounded-full' in c)
                    if circle and 'bg-emerald-100' in (circle.get('class') or []):
                        # Feature name = direct NavigableString children of feat_span
                        name_parts = [
                            str(c).strip()
                            for c in feat_span.children
                            if isinstance(c, NavigableString) and str(c).strip()
                        ]
                        name = ' '.join(name_parts).strip()
                        if name:
                            checked.append(name)
                detail[col] = ', '.join(checked)
                continue

            # Regular label/value row (2 cells)
            if len(tds) < 2:
                continue
            label = _clean(tds[0].get_text(strip=True))
            col   = LABEL_MAP.get(label)
            if not col:
                continue

            # Extract value — some cells have complex structure
            if label == 'الماركة':
                # <div class="table-brand"><img><div><div>ARABIC</div><div>ENGLISH</div></div></div>
                brand_div = tds[1].find('div', class_=lambda c: c and 'table-brand' in (c if isinstance(c, str) else ' '.join(c)))
                if brand_div:
                    divs = brand_div.find_all('div', recursive=False)
                    if divs:
                        inner = divs[-1].find('div')
                        value = _clean(inner.get_text(strip=True)) if inner else _text(divs[-1])
                    else:
                        value = _text(brand_div)
                else:
                    value = _clean(tds[1].get_text(strip=True))
            elif label == 'الموديل':
                # <div>Arabic model</div><div>English model</div>
                first_div = tds[1].find('div')
                value = _clean(first_div.get_text(strip=True)) if first_div else _clean(tds[1].get_text(strip=True))
            elif label == 'السعر':
                value = _parse_price(_clean(tds[1].get_text(strip=True)))
            elif label == 'رقم الإعلان':
                # The copy() attr holds the value: @click="copy('VALUE', ...)"
                click_span = tds[1].find(attrs={'@click': True})
                if click_span:
                    m = re.search(r"copy\('([^']+)'", click_span.get('@click', ''))
                    value = m.group(1) if m else re.sub(r'\D', '', _clean(tds[1].get_text(strip=True)))
                else:
                    value = re.search(r'\d{5,}', tds[1].get_text()).group(0) if re.search(r'\d{5,}', tds[1].get_text()) else ''
            else:
                value = _clean(tds[1].get_text(strip=True))

            if value:
                detail[col] = value

    # ── Seller name ───────────────────────────────────────────────────────────
    name_span = soup.find('span', class_=lambda c: c and isinstance(c, list)
                           and 'text-primary' in c and 'font-semibold' in c)
    if name_span:
        detail['seller_name'] = _clean(name_span.get_text(strip=True))

    # ── Phone from seller profile URL ─────────────────────────────────────────
    # The profile link is https://doushesh.com/users/PHONE_NUMBER
    for a in soup.find_all('a', href=lambda h: h and '/users/' in (h or '')):
        href = a.get('href', '')
        m = re.search(r'/users/(\d{9,})', href)
        if m:
            detail['phone'] = m.group(1)
            break

    # ── Description (loaded async, fallback: h2 title area) ──────────────────
    # Description is loaded via XHR at /listing/{id}/description — not in SSR HTML
    # We capture a snippet from the listing card's <p> tag as fallback

    # ── City: breadcrumb / SeeMore section ───────────────────────────────────
    # The detail page has location in a div with location name; complement card city
    if not detail.get('city'):
        loc_text_divs = soup.find_all('div', class_=lambda c: c and isinstance(c, list)
                                      and 'text-xs' in c and 'font-semibold' in c
                                      and 'text-gray-500' in c)
        for div in loc_text_divs:
            txt = _clean(div.get_text(strip=True))
            # Location breadcrumbs contain ‏> as separator, e.g. "ريف دمشق ‏> قدسيا"
            if '>' in txt or '‏>' in txt:
                # Keep the finest-grained part (last segment)
                parts = re.split(r'\s*[‏>＞›»]\s*', txt)
                detail['city_detail'] = parts[-1].strip() if parts else txt
                break

    return detail


# ── Scraper class ─────────────────────────────────────────────────────────────


class DousheshRawScraper:

    def __init__(
        self,
        start_date: Optional[str] = None,
        end_date:   Optional[str] = None,
        dewatermark_key: Optional[str] = None,
    ):
        self.start_date      = start_date
        self.end_date        = end_date
        self.dewatermark_key = dewatermark_key
        self._stop           = False

        if not SHEET_ID:
            logger.warning('SHEET_ID is empty — will write only to JSONL file!')

        logger.info('Authenticating with Google APIs …')
        creds = _get_oauth_credentials()

        self.gc    = gspread.authorize(creds) if SHEET_ID else None
        self.sheet = self.gc.open_by_key(SHEET_ID).sheet1 if self.gc else None

        self.drive_svc = None
        try:
            self.drive_svc = google_build('drive', 'v3', credentials=creds)
            logger.info('Google Drive service initialized.')
        except Exception as exc:
            logger.warning(f'Could not initialize Drive service: {exc}')

        if self.sheet:
            self._ensure_headers()

        self.existing_ids: Set[str] = self._load_existing_ids()

        self.http = req_lib.Session()
        self.http.headers.update({
            'User-Agent': (
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                'AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/120.0.0.0 Safari/537.36'
            ),
            'Accept':          'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'ar,en;q=0.5',
            'Referer':         LIST_URL,
        })

        logger.info(f'Existing IDs: {len(self.existing_ids)}')

    def _ensure_headers(self):
        first = self.sheet.row_values(1)
        if first == COLUMNS:
            return
        logger.info('Writing sheet headers …')
        self.sheet.clear()
        self.sheet.insert_row(COLUMNS, 1)

    def _load_existing_ids(self) -> Set[str]:
        if not self.sheet:
            return set()
        col_idx = COLUMNS.index('id') + 1
        vals = self.sheet.col_values(col_idx)
        return set(vals[1:])

    def _sheet_append(self, data: Dict):
        if not self.sheet:
            return
        row = [_to_cell(data.get(col)) for col in COLUMNS]
        self.sheet.append_row(row, value_input_option='RAW')

    # ── Drive / dewatermark ───────────────────────────────────────────────────

    def _make_public(self, file_id: str) -> None:
        try:
            self.drive_svc.permissions().create(
                fileId=file_id,
                body={'type': 'anyone', 'role': 'reader'},
            ).execute()
        except Exception as exc:
            logger.warning(f'  Drive make-public failed: {exc}')

    def _upload_bytes(self, data: bytes, mime: str, filename: str) -> str:
        if not (self.drive_svc and DRIVE_FOLDER_ID):
            return ''
        try:
            meta   = {'name': filename, 'parents': [DRIVE_FOLDER_ID]}
            media  = MediaIoBaseUpload(io.BytesIO(data), mimetype=mime, resumable=False)
            result = self.drive_svc.files().create(
                body=meta, media_body=media, fields='id'
            ).execute()
            fid = result.get('id', '')
            self._make_public(fid)
            return f'https://drive.google.com/uc?id={fid}' if fid else ''
        except Exception as exc:
            logger.warning(f'  Drive upload failed: {exc}')
            return ''

    def _remove_watermark(self, image_bytes: bytes) -> Optional[bytes]:
        try:
            resp = req_lib.post(
                DEWATERMARK_URL,
                headers={'X-API-KEY': self.dewatermark_key},
                files={'original_preview_image': ('image.jpg', image_bytes, 'image/jpeg')},
                timeout=60,
            )
            resp.raise_for_status()
            b64 = resp.json().get('edited_image', {}).get('image', '')
            if not b64:
                logger.warning('  Dewatermark: empty image in response')
                return None
            return base64.b64decode(b64)
        except Exception as exc:
            logger.warning(f'  Dewatermark API error: {exc}')
            return None

    # ── Fetch helpers ─────────────────────────────────────────────────────────

    def _fetch_html(self, url: str, params: Optional[Dict] = None,
                    accept_json: bool = False) -> Optional[str]:
        headers = {}
        if accept_json:
            headers['Accept'] = 'application/json, text/plain, */*'
            headers['X-Requested-With'] = 'XMLHttpRequest'
        try:
            resp = self.http.get(url, params=params, headers=headers, timeout=30)
            resp.raise_for_status()
            if accept_json:
                data = resp.json()
                return data.get('html') or ''
            return resp.text
        except Exception as exc:
            logger.error(f'  Fetch error {url}: {exc}')
            return None

    def _fetch_listing_page(self, offset: int) -> Optional[List[Dict]]:
        """Fetch one batch of listing cards. offset=0 → initial page HTML."""
        if offset == 0:
            html = self._fetch_html(LIST_URL)
        else:
            html = self._fetch_html(
                LOAD_MORE_URL,
                params={'offset': offset, 'url': LIST_URL},
                accept_json=True,
            )
        if html is None:
            return None
        cards = _parse_cards_from_html(html)
        logger.info(f'  offset={offset}: {len(cards)} cards found')
        return cards

    def _fetch_detail(self, car_url: str) -> Dict:
        html = self._fetch_html(car_url)
        if not html:
            return {}
        return _parse_detail(html)

    # ── Car processing ────────────────────────────────────────────────────────

    def _process_car(self, card: Dict) -> bool:
        car_id = card['id']
        if car_id in self.existing_ids:
            return False

        # Fetch detail page for full specs + date
        car_url = card['car_url']
        logger.info(f'  → {car_url}')
        time.sleep(REQUEST_DELAY)
        detail = self._fetch_detail(car_url)

        # Merge: detail overrides card for shared fields (make, model, year, etc.)
        data = {**card}
        for k, v in detail.items():
            if v and k != 'city_detail':
                data[k] = v
        # City: prefer more specific detail location if available
        if detail.get('city_detail') and not data.get('city'):
            data['city'] = detail['city_detail']

        # Date filter
        date_added = _clean(data.get('date_added', ''))
        if date_added:
            if self.start_date and date_added < self.start_date:
                logger.info(f'  Skip (date {date_added} < {self.start_date}): {car_id}')
                return False
            if self.end_date and date_added > self.end_date:
                logger.info(f'  Skip (date {date_added} > {self.end_date}): {car_id}')
                return False

        # Year filter
        year_str = _clean_year(str(data.get('year', '') or ''))
        data['year'] = year_str
        if year_str:
            try:
                if int(year_str) < MIN_YEAR:
                    logger.info(f'  Skip (year {year_str} < {MIN_YEAR}): {car_id}')
                    return False
            except ValueError:
                pass

        # Clean numeric fields
        if data.get('mileage'):
            data['mileage'] = _strip_km(data['mileage'])
        if data.get('engine_size'):
            data['engine_size'] = _strip_cc(data['engine_size'])
        if data.get('engine_power'):
            data['engine_power'] = _strip_hp(data['engine_power'])

        # Normalize "أخرى" in non-make fields
        for f in ('condition', 'exterior_color', 'fuel_type', 'engine_size',
                  'transmission', 'body_type', 'drive_system', 'city',
                  'listing_type', 'model'):
            if data.get(f) in _AKHRY:
                data[f] = 'غير ذلك'

        data['scraped_at'] = datetime.now().isoformat()

        # Full description from async endpoint /listing/{id}/description
        if not data.get('description'):
            ad_id_num = card.get('listing_id', '')
            if ad_id_num:
                desc_url = f'{SITE_URL}/listing/{ad_id_num}/description'
                try:
                    dr = self.http.get(
                        desc_url, timeout=15,
                        headers={'X-Requested-With': 'XMLHttpRequest', 'Accept': 'text/html'}
                    )
                    if dr.ok and dr.text.strip():
                        ds = BeautifulSoup(dr.text, 'html.parser')
                        data['description'] = _clean(ds.get_text(separator=' ', strip=True))
                except Exception:
                    pass

        # Cover image → dewatermark → Drive
        image_clean_link = ''
        cover_url = data.get('cover_image_url', '')
        if cover_url and self.dewatermark_key:
            try:
                r = self.http.get(cover_url, timeout=30)
                r.raise_for_status()
                logger.info('  Removing watermark …')
                clean_bytes = self._remove_watermark(r.content)
                if clean_bytes:
                    if self.drive_svc and DRIVE_FOLDER_ID:
                        cl = self._upload_bytes(
                            clean_bytes, 'image/jpeg', f'{car_id}_clean.jpg'
                        )
                        image_clean_link = cl or ''
                        logger.info('  ✓ Clean image uploaded to Drive')
            except Exception as exc:
                logger.warning(f'  Image error for {car_id}: {exc}')

        data['image_clean_link'] = image_clean_link

        try:
            self._sheet_append(data)
            _append_jsonl(data)
            self.existing_ids.add(car_id)
            logger.info(
                f'  ✓  {data.get("ad_title", car_id)!r}'
                f'  date={data.get("date_added", "-")}'
                f'  year={data.get("year", "-")}'
            )
            return True
        except Exception as exc:
            logger.error(f'  Write failed: {exc}')
            return False

    # ── Main loop ─────────────────────────────────────────────────────────────

    def run(self):
        logger.info('=' * 62)
        logger.info(f'Doushesh raw scraper  {datetime.now().isoformat()}')
        logger.info('=' * 62)

        total_new   = 0
        old_streak  = 0
        offset      = 0

        while not self._stop:
            logger.info(f'\n[offset={offset}]')
            cards = self._fetch_listing_page(offset)

            if cards is None:
                logger.error('  Fetch failed — stopping.')
                break

            if not cards:
                logger.info('  No more cards — done.')
                break

            new_cards = [c for c in cards if c['id'] not in self.existing_ids]
            logger.info(f'  {len(cards)} cards | {len(new_cards)} new')

            if not new_cards:
                old_streak += 1
                if old_streak >= STOP_OLD_PAGES:
                    logger.info('  Caught up — stopping.')
                    break
                offset += BATCH_SIZE
                time.sleep(REQUEST_DELAY)
                continue

            old_streak = 0
            all_old    = True

            for card in new_cards:
                if self._stop:
                    break
                ok = self._process_car(card)
                if ok:
                    total_new += 1
                    all_old = False
                elif card.get('date_added'):
                    # If date_added exists and is too recent, not all-old
                    if card['date_added'] >= (self.start_date or ''):
                        all_old = False

            if all_old and new_cards:
                old_streak += 1
                if old_streak >= STOP_OLD_PAGES:
                    logger.info('  All cards too old — done.')
                    break

            offset += BATCH_SIZE
            time.sleep(REQUEST_DELAY)

        logger.info('\n' + '=' * 62)
        logger.info(f'Done. {total_new} new cars → sheet + {OUTPUT_FILE}')
        logger.info('=' * 62)


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Doushesh raw data scraper')

    def _pd(s):
        if re.match(r'^\d{4}-\d{2}-\d{2}$', s):
            return s
        m = re.match(r'^(\d{2})-(\d{2})-(\d{4})$', s)
        if m:
            return f'{m.group(3)}-{m.group(2)}-{m.group(1)}'
        raise argparse.ArgumentTypeError(f'Invalid date "{s}"')

    parser.add_argument('--start-date',      type=_pd, metavar='DATE', default='2026-06-01')
    parser.add_argument('--end-date',        type=_pd, metavar='DATE', default='2026-07-31')
    parser.add_argument('--dewatermark-key', metavar='KEY',
                        help='dewatermark.ai API key for watermark removal')
    args = parser.parse_args()

    if sys.stdout.encoding != 'utf-8':
        sys.stdout.reconfigure(encoding='utf-8')

    scraper = DousheshRawScraper(
        start_date=args.start_date,
        end_date=args.end_date,
        dewatermark_key=args.dewatermark_key,
    )

    def _sig(s, f):
        scraper._stop = True

    signal.signal(signal.SIGINT,  _sig)
    signal.signal(signal.SIGTERM, _sig)

    scraper.run()
