#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SyriaCars.net Raw Data Scraper
==============================
Scrapes ALL listings from syriacars.net/inventory/, writes every car to:
  • rawdata_syriacars.jsonl  (local backup, one JSON per line)
  • Google Sheet: syriacars_raw_data

No images downloaded. No quality gate. Pure data extraction.

USAGE
-----
  python rawdata_syriacars.py                         # scrape from page 1
  python rawdata_syriacars.py --full                  # resume from last page
  python rawdata_syriacars.py --hours 4               # stop after 4 hours
  python rawdata_syriacars.py --start-date 2025-01-01
  python rawdata_syriacars.py --pages 5               # quick test
"""

import argparse
import json
import logging
import os
import re
import signal
import sys
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set

import requests
from bs4 import BeautifulSoup

import gspread
from google.auth.transport.requests import Request
from google.oauth2 import credentials as google_creds_module
from google_auth_oauthlib.flow import InstalledAppFlow

# ── Logging ───────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)-8s %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('rawdata_syriacars.log', encoding='utf-8'),
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

OUTPUT_FILE   = os.path.join(SCRIPT_DIR, 'rawdata_syriacars.jsonl')
PROGRESS_FILE = os.path.join(SCRIPT_DIR, 'rawdata_syriacars_progress.json')

SHEET_ID = '1uuQHoquAj5yUCaayqhqnFsQYmChNaF75MOUjv0P_0XY'

SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive',
]

BASE_URL      = 'https://syriacars.net'
INVENTORY_URL = 'https://syriacars.net/inventory/'
SOURCE        = 'syriacars'

HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/120.0.0.0 Safari/537.36'
    ),
    'Accept-Language': 'ar,en-US;q=0.9,en;q=0.8',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
}

REQUEST_DELAY         = 0.8
STOP_AFTER_FULL_PAGES = 3

# ── Sheet columns ─────────────────────────────────────────────────────────────

COLUMNS: List[str] = [
    'id', 'source', 'car_url', 'listing_id',
    'ad_title', 'listing_type',
    'make', 'model', 'year', 'body_type', 'condition',
    'exterior_color', 'interior_color',
    'fuel_type', 'engine_size', 'transmission', 'drive_system',
    'cylinders', 'doors', 'chassis_number',
    'city', 'mileage', 'price',
    'date_added', 'scraped_at', 'views',
    'phone', 'seller_name', 'seller_type', 'seller_notes',
    'description',
    'image_urls', 'image_count',
]

# ── Arabic label → field mapping ──────────────────────────────────────────────

SPEC_MAP: Dict[str, str] = {
    'السنة':           'year',
    'المدينة':         'city',
    'الماركة':         'make',
    'الموديل':         'model',
    'الحالة':          'condition',
    'الكيلومتراج':     'mileage',
    'نوع الجسم':       'body_type',
    'الوقود':          'fuel_type',
    'نوع الوقود':      'fuel_type',
    'المحرك':          'engine_size',
    'الغيار':          'transmission',
    'ناقل الحركة':     'transmission',
    'الناقل':          'transmission',
    'الانتقال':        'transmission',
    'اللون الخارجي':   'exterior_color',
    'اللون الداخلي':   'interior_color',
    'نظام الدفع':      'drive_system',
    'نوع الدفع':       'drive_system',
    'عدد الأبواب':     'doors',
    'عدد الابواب':     'doors',
    'الأبواب':         'doors',
    'السلندرات':       'cylinders',
    'عدد السلندرات':   'cylinders',
    'رقم الهيكل':      'chassis_number',
    'رقم الشاصي':      'chassis_number',
    'History':         '_history',
    'الوارد':          '_origin',
    'الاستيراد':       '_origin',
    'الموديل الفرعي':  '_submodel',
}

# ── Helpers ───────────────────────────────────────────────────────────────────

AR_MONTHS = {
    'يناير': 1, 'فبراير': 2, 'مارس': 3, 'أبريل': 4,
    'مايو': 5,  'يونيو': 6,  'يوليو': 7, 'أغسطس': 8,
    'سبتمبر': 9, 'أكتوبر': 10, 'نوفمبر': 11, 'ديسمبر': 12,
    'January': 1, 'February': 2, 'March': 3,   'April': 4,
    'May': 5,     'June': 6,     'July': 7,     'August': 8,
    'September': 9, 'October': 10, 'November': 11, 'December': 12,
}

_HAS_ARABIC        = re.compile(r'[؀-ۿ]')
_ALL_MODELS_SUFFIX = re.compile(r'\s*كل الفئات\s*$')
_COMPOUND_SEP      = re.compile(r'\s*[-–]\s*')


def _clean(text) -> str:
    if not text:
        return ''
    t = ' '.join(str(text).split())
    return '' if t in ('-', '—', '–', '') else t


def _clean_mileage(v: str) -> str:
    v = re.sub(r'[,،٬]', '', v)
    v = re.sub(r'\s*(كم|km)\s*$', '', v, flags=re.I).strip()
    m = re.match(r'^(\d+)\s*ألف\s*$', v)
    return str(int(m.group(1)) * 1000) if m else v


def _parse_price(text: str) -> str:
    if not text:
        return ''
    digits = re.sub(r'[^\d.]', '', text.replace(',', ''))
    try:
        v = float(digits)
        return str(int(v)) if v == int(v) else str(v)
    except (ValueError, TypeError):
        return ''


def _strip_foreign(text: str) -> str:
    if not text:
        return text
    text = _ALL_MODELS_SUFFIX.sub('', text).strip()
    if not text:
        return ''
    parts = [p.strip() for p in _COMPOUND_SEP.split(text) if p.strip()]
    if len(parts) < 2:
        return text
    arabic_parts = [p for p in parts if _HAS_ARABIC.search(p)]
    return arabic_parts[0] if arabic_parts else text


def _parse_listing_date(text: str) -> str:
    if not text:
        return ''
    for month_name, month_num in AR_MONTHS.items():
        if month_name in text:
            m = re.search(r'(\d{1,2})[,،]?\s*(\d{4})', text)
            if m:
                return f'{int(m.group(2))}-{month_num:02d}-{int(m.group(1)):02d}'
    return ''


def _base_image_url(src: str) -> str:
    src = re.sub(r'\?.*$', '', src)
    src = re.sub(r'-\d+x\d+(?=\.[a-zA-Z]+$)', '', src)
    return src


def _apply_spec(data: Dict, k: str, v: str) -> None:
    field = SPEC_MAP.get(k)
    if not field or field.startswith('_') or field in data:
        return
    data[field] = _clean_mileage(v) if field == 'mileage' else v


def _to_cell(v) -> str:
    if v is None:
        return ''
    if isinstance(v, list):
        return ', '.join(str(x) for x in v)
    return str(v)


# ── OAuth2 ────────────────────────────────────────────────────────────────────


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


# ── Progress helpers ──────────────────────────────────────────────────────────


def _load_progress() -> Dict:
    if os.path.exists(PROGRESS_FILE):
        try:
            with open(PROGRESS_FILE, encoding='utf-8') as fh:
                return json.load(fh)
        except Exception:
            pass
    return {'last_page': 0, 'total_scraped': 0, 'full_scrape_done': False}


def _save_progress(progress: Dict):
    tmp = PROGRESS_FILE + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as fh:
        json.dump(progress, fh, indent=2, ensure_ascii=False)
    os.replace(tmp, PROGRESS_FILE)


def _append_jsonl(record: Dict):
    out = dict(record)
    # store image_urls as list in JSONL (valid JSON)
    with open(OUTPUT_FILE, 'a', encoding='utf-8') as fh:
        fh.write(json.dumps(out, ensure_ascii=False) + '\n')


# ── Scraper ───────────────────────────────────────────────────────────────────


class SyriaCarsRawScraper:

    def __init__(
        self,
        full_mode: bool = False,
        max_hours: Optional[float] = None,
        max_pages: Optional[int] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ):
        self.full_mode  = full_mode
        self.max_pages  = max_pages
        self.start_date = start_date
        self.end_date   = end_date
        self.deadline: Optional[datetime] = (
            datetime.now() + timedelta(hours=max_hours) if max_hours else None
        )
        self._stop_requested = False

        signal.signal(signal.SIGINT,  self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)

        logger.info('Authenticating with Google APIs …')
        creds      = _get_oauth_credentials()
        self.gc    = gspread.authorize(creds)
        self.sheet = self.gc.open_by_key(SHEET_ID).sheet1

        self._ensure_headers()
        self.existing_ids: Set[str] = self._load_existing_ids()
        self.progress: Dict         = _load_progress()

        logger.info(f'Sheet IDs loaded  : {len(self.existing_ids)}')
        logger.info(
            f'Progress          : last_page={self.progress["last_page"]}, '
            f'total={self.progress["total_scraped"]}'
        )

    def _handle_signal(self, signum, frame):
        logger.warning('\nInterrupt received — finishing current car …')
        self._stop_requested = True

    def _should_stop(self) -> bool:
        if self._stop_requested:
            return True
        if self.deadline and datetime.now() >= self.deadline:
            logger.info('Time limit reached.')
            return True
        return False

    def _ensure_headers(self):
        first = self.sheet.row_values(1)
        if first == COLUMNS:
            return
        logger.info('Writing sheet headers …')
        self.sheet.clear()
        self.sheet.insert_row(COLUMNS, 1)

    def _load_existing_ids(self) -> Set[str]:
        col_idx = COLUMNS.index('id') + 1
        vals = self.sheet.col_values(col_idx)
        return set(vals[1:])

    def _append_row(self, data: Dict):
        row = [_to_cell(data.get(col)) for col in COLUMNS]
        self.sheet.append_row(row, value_input_option='RAW')

    def _fetch(self, url: str) -> BeautifulSoup:
        r = requests.get(url, headers=HEADERS, timeout=30)
        r.raise_for_status()
        return BeautifulSoup(r.text, 'html.parser')

    def _scrape_listing_page(self, url: str) -> List[Dict]:
        soup  = self._fetch(url)
        items = []
        for div in soup.select('div.stm-isotope-listing-item[data-listing-id]'):
            lid = div.get('data-listing-id', '').strip()
            if not lid:
                continue
            a = div.find('a', href=True)
            if not a:
                continue
            href = a['href']
            if not href.startswith('http'):
                href = BASE_URL.rstrip('/') + '/' + href.lstrip('/')

            # Primary: data-date="YYYYMMDDHHmm"
            date_added = ''
            raw_date = div.get('data-date', '')
            if raw_date and len(raw_date) >= 8 and raw_date[:8].isdigit():
                date_added = f'{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:8]}'

            if not date_added:
                time_el = div.select_one('time[datetime]')
                if time_el:
                    dt_attr = time_el.get('datetime', '')
                    m = re.match(r'(\d{4}-\d{2}-\d{2})', dt_attr)
                    date_added = m.group(1) if m else _parse_listing_date(time_el.get_text())

            if not date_added:
                date_added = _parse_listing_date(div.get_text())

            items.append({'listing_id': lid, 'car_url': href, 'date_added': date_added})
        return items

    def _scrape_detail(self, car_url: str, listing_id: str) -> Dict:
        soup = self._fetch(car_url)

        data: Dict = {
            'scraped_at': datetime.now().isoformat(),
            'source':     SOURCE,
            'id':         f'syriacars_{listing_id}',
            'listing_id': listing_id,
            'car_url':    car_url,
        }

        h1 = soup.select_one('h1.single-listing-title')
        title = _clean(h1.get_text()) if h1 else ''
        data['ad_title']     = title
        data['listing_type'] = ('للإيجار'
                                if any(k in title for k in ('للإيجار', 'للايجار', 'للتأجير', 'إيجار'))
                                else 'للبيع')
        if 'مستعمل' in title or 'مستعملة' in title:
            data['condition'] = 'مستعمل'
        elif 'جديد' in title or 'جديدة' in title:
            data['condition'] = 'جديد'

        pv = soup.select_one('.single-listing-price-value')
        if pv:
            data['price'] = _parse_price(pv.get_text())

        views_el = soup.select_one('.stm-listing-views-count, [class*="views"]')
        if views_el:
            m = re.search(r'\d+', views_el.get_text())
            if m:
                data['views'] = m.group(0)

        # Pass 1: main spec list
        for li in soup.select('ul.single-listing-data li.single-listing-data-item'):
            lbl = li.select_one('.single-listing-data-item-label')
            val = li.select_one('.single-listing-data-item-value')
            if lbl and val:
                k, v = _clean(lbl.get_text()), _clean(val.get_text())
                if k and v:
                    _apply_spec(data, k, v)

        # Pass 2: chapter sections
        for ch in soup.find_all(class_='single-listing-chapter-title'):
            sib = ch.find_next_sibling()
            while sib:
                if hasattr(sib, 'get') and 'single-listing-chapter-title' in sib.get('class', []):
                    break
                for li in sib.select('li.single-listing-data-item'):
                    lbl = li.select_one('.single-listing-data-item-label')
                    val = li.select_one('.single-listing-data-item-value')
                    if lbl and val:
                        k, v = _clean(lbl.get_text()), _clean(val.get_text())
                        if k and v:
                            _apply_spec(data, k, v)
                sib = sib.find_next_sibling()

        # Pass 3: accordion sections
        for outer in soup.find_all(
            'div',
            class_=re.compile(r'accordion-\d+-content-details|accordion-inner-details', re.I),
        ):
            uls = outer.find_all('ul')
            if len(uls) >= 2 and len(uls) % 2 == 0:
                for i in range(0, len(uls), 2):
                    labels = [_clean(li.get_text()) for li in uls[i].find_all('li')]
                    values = [_clean(li.get_text()) for li in uls[i + 1].find_all('li')]
                    for k, v in zip(labels, values):
                        if k and v:
                            _apply_spec(data, k, v)

        # Strip English from Arabic compound fields
        for f in ('make', 'model', 'body_type', 'fuel_type', 'transmission',
                  'condition', 'city', 'exterior_color', 'interior_color'):
            if data.get(f):
                data[f] = _strip_foreign(data[f])

        # Description
        for sel in ('.stm-listing-description', '.single-listing-description',
                    '[class*="description-content"]'):
            el = soup.select_one(sel)
            if el:
                desc = _clean(el.get_text(separator=' '))
                if desc:
                    data['description'] = desc
                    break

        # Seller notes
        for h in soup.find_all(['h2', 'h3', 'h4', 'h5'],
                               string=re.compile(r'ملاحظات|seller.?note', re.I)):
            nxt = h.find_next_sibling()
            while nxt and nxt.name in ('br', 'script', 'style'):
                nxt = nxt.find_next_sibling()
            if nxt:
                notes = _clean(nxt.get_text(separator=' '))
                if notes and notes not in ('غير معروف', 'N/A', 'n/a', '-'):
                    data['seller_notes'] = notes
            break

        # Seller name + type
        dealer_el = soup.select_one('.single-listing-dealer-name')
        if dealer_el:
            data['seller_name'] = _clean(dealer_el.get_text())
            dealer_a = (dealer_el if dealer_el.name == 'a'
                        else dealer_el.find('a', href=re.compile(r'/dealer/')))
            data['seller_type'] = 'dealer' if dealer_a else 'private'
        else:
            data['seller_type'] = 'private'

        # Phone
        phone_span = soup.select_one('span.single-listing-phone-number')
        phone = _clean(phone_span.get_text()) if phone_span else ''
        if not phone:
            tel_a = soup.select_one('a.single-listing-phone-button[href^="tel:"]')
            if tel_a:
                phone = tel_a['href'].replace('tel:', '').strip()
        if phone:
            data['phone'] = phone
        wa_a = soup.select_one('a.single-listing-whatsapp-button[href*="wa.me"]')
        if wa_a:
            wa_m = re.search(r'wa\.me/(\+?[\d]+)', wa_a['href'])
            if wa_m:
                wa_num = wa_m.group(1)
                existing = data.get('phone', '')
                if wa_num.lstrip('+') not in existing.replace('+', '').replace(' ', ''):
                    data['phone'] = (existing + ' / WA:' + wa_num).strip(' /')

        # Date from detail page meta
        meta_date = soup.find('meta', property='article:published_time')
        if meta_date:
            m_dt = re.match(r'(\d{4}-\d{2}-\d{2})', meta_date.get('content', ''))
            if m_dt:
                data['date_added'] = m_dt.group(1)
        if not data.get('date_added'):
            for t_el in soup.find_all('time', attrs={'datetime': True}):
                m_dt = re.match(r'(\d{4}-\d{2}-\d{2})', t_el.get('datetime', ''))
                if m_dt:
                    data['date_added'] = m_dt.group(1)
                    break
        if not data.get('date_added'):
            for script in soup.find_all('script', type='application/ld+json'):
                try:
                    jd = json.loads(script.string or '')
                    dp = jd.get('datePublished', '')
                    if dp:
                        m_dt = re.match(r'(\d{4}-\d{2}-\d{2})', dp)
                        if m_dt:
                            data['date_added'] = m_dt.group(1)
                            break
                except Exception:
                    pass

        # Image URLs (collected, not downloaded)
        images: List[str] = []
        seen: set = set()
        for img in soup.select('img.single-listing-gallery-image'):
            src = _base_image_url(img.get('data-lg-src') or img.get('src', ''))
            if src.startswith('https://syriacars.net/wp-content/uploads/') and src not in seen:
                seen.add(src)
                images.append(src)
        if not images:
            for img in soup.find_all('img'):
                src = _base_image_url(img.get('src', ''))
                if 'syriacars.net/wp-content/uploads/' in src and 'car-image' in src and src not in seen:
                    seen.add(src)
                    images.append(src)

        data['image_urls']  = images
        data['image_count'] = len(images)
        return data

    def _process_car(self, listing_id: str, car_url: str, date_added: str = '') -> bool:
        logger.info(f'  → {car_url}')
        try:
            data = self._scrape_detail(car_url, listing_id)
        except Exception as exc:
            logger.error(f'  Detail scrape failed: {exc}')
            return False

        if date_added and not data.get('date_added'):
            data['date_added'] = date_added

        try:
            self._append_row(data)
            _append_jsonl(data)
            self.existing_ids.add(data['id'])
            logger.info(f'  ✓  Saved: {data.get("ad_title", listing_id)!r}')
            return True
        except Exception as exc:
            logger.error(f'  Write failed: {exc}')
            return False

    def run(self):
        progress = self.progress

        if self.full_mode:
            start_page = progress['last_page'] + 1
            if progress.get('full_scrape_done'):
                logger.info('Full scrape complete. Delete rawdata_syriacars_progress.json to restart.')
                return
            logger.info(f'Full scrape mode — resuming from page {start_page}')
        else:
            start_page = 1
            logger.info('Incremental mode — starting from page 1')

        logger.info('=' * 62)
        logger.info(f'SyriaCars raw scraper  {datetime.now().isoformat()}')
        logger.info('=' * 62)

        total_new        = 0
        full_page_streak = 0
        page             = start_page

        while True:
            if self._should_stop():
                break
            if self.max_pages and page > self.max_pages:
                logger.info(f'Reached --pages limit ({self.max_pages}) — stopping.')
                break

            _sort    = '?orderby=date&order=DESC'
            page_url = (INVENTORY_URL + _sort if page == 1
                        else f'{BASE_URL}/inventory/page/{page}/{_sort}')
            logger.info(f'\n[Page {page}] {page_url}')

            try:
                items = self._scrape_listing_page(page_url)
            except requests.HTTPError as exc:
                if exc.response.status_code == 404:
                    logger.info('  404 — no more pages.')
                    if self.full_mode:
                        progress['full_scrape_done'] = True
                        _save_progress(progress)
                    break
                logger.error(f'  HTTP error: {exc}')
                break
            except Exception as exc:
                logger.error(f'  Listing page error: {exc}')
                break

            if not items:
                logger.info('  No items — stopping.')
                if self.full_mode:
                    progress['full_scrape_done'] = True
                    _save_progress(progress)
                break

            if self.start_date:
                dated = [it for it in items if it.get('date_added')]
                if dated and all(it['date_added'] < self.start_date for it in dated):
                    logger.info(f'  All before {self.start_date} — done.')
                    break
                items = [
                    it for it in items
                    if (not it.get('date_added')
                        or (it['date_added'] >= self.start_date
                            and (not self.end_date or it['date_added'] <= self.end_date)))
                ]

            new_items = [it for it in items
                         if f"syriacars_{it['listing_id']}" not in self.existing_ids]
            logger.info(f'  {len(items)} on page | {len(new_items)} new')

            if not new_items:
                if not self.full_mode:
                    full_page_streak += 1
                    if full_page_streak >= STOP_AFTER_FULL_PAGES:
                        logger.info('  Caught up — stopping.')
                        break
                else:
                    progress['last_page'] = page
                    _save_progress(progress)
                time.sleep(REQUEST_DELAY)
                page += 1
                continue

            full_page_streak = 0

            for it in new_items:
                if self._should_stop():
                    if self.full_mode:
                        progress['last_page'] = page - 1
                        _save_progress(progress)
                    break
                ok = self._process_car(it['listing_id'], it['car_url'], it.get('date_added', ''))
                if ok:
                    total_new += 1
                    progress['total_scraped'] += 1
                time.sleep(REQUEST_DELAY)
            else:
                if self.full_mode:
                    progress['last_page'] = page
                    _save_progress(progress)

            if self._should_stop():
                break

            time.sleep(REQUEST_DELAY)
            page += 1

        logger.info('\n' + '=' * 62)
        logger.info(f'Done. {total_new} cars → sheet + {OUTPUT_FILE}')
        logger.info('=' * 62)


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='SyriaCars raw data scraper')
    parser.add_argument('--full',       action='store_true')
    parser.add_argument('--hours',      type=float, metavar='N')
    parser.add_argument('--pages',      type=int,   metavar='N')

    def _parse_date(s):
        if re.match(r'^\d{4}-\d{2}-\d{2}$', s):
            return s
        m = re.match(r'^(\d{2})-(\d{2})-(\d{4})$', s)
        if m:
            return f'{m.group(3)}-{m.group(2)}-{m.group(1)}'
        raise argparse.ArgumentTypeError(f'Invalid date "{s}"')

    parser.add_argument('--start-date', type=_parse_date, metavar='DATE')
    parser.add_argument('--end-date',   type=_parse_date, metavar='DATE')
    args = parser.parse_args()

    if sys.stdout.encoding != 'utf-8':
        sys.stdout.reconfigure(encoding='utf-8')

    SyriaCarsRawScraper(
        full_mode=args.full,
        max_hours=args.hours,
        max_pages=args.pages,
        start_date=args.start_date,
        end_date=args.end_date,
    ).run()
