#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Carsy.app Standalone Scraper
============================
Scrapes https://carsy.app/cars  (~990 listings, 50 pages × 20)
and writes structured rows to a Google Sheets tab with Drive image uploads.

HOW IT WORKS
------------
• Uses the REST JSON API at https://app.carsy.app/api — no HTML parsing.
• Step 1 : Paginate listing API  GET /api/classifieds?page=N  → car IDs
• Step 2 : For each new ID call  GET /api/classifieds/{id}    → full data
• Date   : Computed from the relative date string (created_at_en/ar)
• Images : Upgraded from /low/ to /high/ CDN path before uploading to Drive

COLUMNS match syriacars_test.py / damazzle_standalone.py exactly.

SETUP
-----
  pip install requests gspread google-auth google-auth-oauthlib
  pip install google-api-python-client

USAGE
-----
  python carsy_standalone.py                     # incremental (daily update)
  python carsy_standalone.py --hours 2           # run for 2 hours then stop
  python carsy_standalone.py --full              # full scrape, resume from last page
  python carsy_standalone.py --repair-images     # re-upload images for empty rows
"""

import argparse
import io
import json
import logging
import os
import re
import signal
import sys
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set, Tuple

import requests

import gspread
from google.auth.transport.requests import Request
from google.oauth2 import credentials as google_creds_module
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

# ── Logging ───────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)-8s %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('carsy_standalone.log', encoding='utf-8'),
    ],
)
logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────────────

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

OAUTH_CLIENT_FILE = os.path.join(
    SCRIPT_DIR,
    'client_secret_798447276011-9bfpmjkfo8et8c2r4omri13kbh7h5202.apps.googleusercontent.com.json',
)
OAUTH_TOKEN_FILE = os.path.join(SCRIPT_DIR, 'oauth_token.json')  # shared token

# ── !! Set your Sheet ID and Drive folder ID below !! ─────────────────────
SHEET_ID        = '1DfYJhshE7SYpLBRF0AE80G4jye-KuodKZ-s70-FAVzs'  # same test sheet
SHEET_TAB       = 'Carsy'                                            # tab name
DRIVE_FOLDER_ID = '10V6GubNv0uRMk9q0DMgfCQrXJfEP9Obj'              # same test folder
# ─────────────────────────────────────────────────────────────────────────────

PROGRESS_FILE = os.path.join(SCRIPT_DIR, 'carsy_progress.json')

BASE_URL          = 'https://carsy.app'
API_BASE          = 'https://app.carsy.app/api'
API_LISTING_URL   = f'{API_BASE}/classifieds'       # + ?page=N
API_DETAIL_URL    = f'{API_BASE}/classifieds'       # + /{car_id}
SOURCE            = 'carsy'

# Browser-like headers for the frontend (carsy.app)
BROWSER_HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/120.0.0.0 Safari/537.36'
    ),
    'Accept-Language': 'ar,en-US;q=0.9,en;q=0.8',
}

# API headers for the backend (app.carsy.app)
API_HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/120.0.0.0 Safari/537.36'
    ),
    'Accept': 'application/json',
    'Accept-Language': 'ar,en-US;q=0.9',
    'Referer': 'https://carsy.app/',
    'Origin': 'https://carsy.app',
}

SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive',
]

REQUEST_DELAY         = 1.0   # seconds between HTTP requests
STOP_AFTER_FULL_PAGES = 3     # incremental: stop after N pages with nothing new

# ── Value translation maps ─────────────────────────────────────────────────────

FUEL_MAP: Dict[str, str] = {
    'oil':      'بنزين',
    'diesel':   'ديزل',
    'gas':      'غاز',
    'electric': 'كهربائي',
    'hybrid':   'هجين',
}

TRANSMISSION_MAP: Dict[str, str] = {
    'automatic': 'أوتوماتيك',
    'manual':    'يدوي',
    'semi_auto': 'نصف أوتوماتيك',
}

DRIVE_MAP: Dict[str, str] = {
    'front':  'دفع أمامي',
    'rear':   'دفع خلفي',
    '4x4':    'دفع رباعي',
    'four':   'دفع رباعي',      # API uses 'four' for 4WD
    'all':    'دفع كلي',
}

SOURCE_MAP: Dict[str, str] = {
    'eroupean_american_import': 'استيراد أوروبي/أمريكي',
    'european_american_import': 'استيراد أوروبي/أمريكي',
    'local':                    'محلي',
    'gulf_import':              'استيراد خليجي',
    'khaleg_import':            'استيراد خليجي',   # alternate spelling
    'chinese_import':           'استيراد صيني',
    'korean_import':            'استيراد كوري',
    'japanese_import':          'استيراد ياباني',
}

SPECS_MAP: Dict[str, str] = {
    'first_class':  'الفئة الأولى',
    'second_class': 'الفئة الثانية',
    'third_class':  'الفئة الثالثة',
    'full_option':  'فل أوبشن',
    'half_option':  'نصف أوبشن',
}

CITY_AR: Dict[str, str] = {
    'damascus':   'دمشق',
    'aleppo':     'حلب',
    'homs':       'حمص',
    'latakia':    'اللاذقية',
    'hama':       'حماة',
    'tartus':     'طرطوس',
    'deir_ez_zor':'دير الزور',
    'idlib':      'إدلب',
    'raqqa':      'الرقة',
    'daraa':      'درعا',
    'quneitra':   'القنيطرة',
    'suwayda':    'السويداء',
    'hasaka':     'الحسكة',
    'rif_dimashq':'ريف دمشق',
}

# ── Sheet columns ─────────────────────────────────────────────────────────────

COLUMNS: List[str] = [
    'scraped_at',
    'date_added',           # approximate ISO date computed from relative date
    'source',               # 'carsy'
    'id',                   # 'carsy_{numeric_id}'
    'category',             # 'cars'
    'ad_title',
    'listing_type',         # 'للبيع'
    'condition',            # empty (not exposed by API)
    'body_type',            # empty (not exposed by API)
    'brand',                # make: brand.parent.name_ar
    'model',                # model: brand.name_ar
    'price',                # USD price string
    'location',             # city name (Arabic)
    'year',
    'drive_system',         # drive_line mapped to Arabic
    'transmission',
    'fuel_type',
    'mileage',              # kilometers (numeric)
    'engine',               # engine_capacity
    'cylinders',            # number_of_cylinders
    'color',                # external_color
    'interior_color',       # internal_color
    'doors',                # empty (not exposed)
    'vin',                  # empty
    'description',
    'seller_name',          # user.name
    'contact',              # user.phone
    'images',               # comma-separated Google Drive links
    'image_folder_url',     # Drive sub-folder link
    'images_original_links',# original CDN URLs
    'car_url',              # https://carsy.app/cars/{id}
]

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
            logger.warning(f'Could not load cached token: {exc}')
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            logger.info('Refreshing expired OAuth2 token …')
            creds.refresh(Request())
        else:
            logger.info('No valid token — launching browser consent flow …')
            flow = InstalledAppFlow.from_client_secrets_file(OAUTH_CLIENT_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(OAUTH_TOKEN_FILE, 'w', encoding='utf-8') as fh:
            fh.write(creds.to_json())
        logger.info(f'Token saved → {OAUTH_TOKEN_FILE}')
    return creds


# ── Progress ──────────────────────────────────────────────────────────────────


def _load_progress() -> Dict:
    if os.path.exists(PROGRESS_FILE):
        try:
            with open(PROGRESS_FILE, encoding='utf-8') as fh:
                return json.load(fh)
        except Exception as exc:
            logger.warning(f'Could not read progress file: {exc}')
    return {'last_page': 0, 'total_scraped': 0, 'full_scrape_done': False}


def _save_progress(progress: Dict):
    tmp = PROGRESS_FILE + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as fh:
        json.dump(progress, fh, indent=2, ensure_ascii=False)
    os.replace(tmp, PROGRESS_FILE)
    logger.info(
        f'Progress saved → page {progress["last_page"]}, '
        f'{progress["total_scraped"]} total scraped.'
    )


# ── Pure helpers ──────────────────────────────────────────────────────────────


def _clean(text) -> str:
    if not text:
        return ''
    return ' '.join(str(text).split())


def _hq_image(url: str) -> str:
    """Upgrade low-quality CDN path to high-quality."""
    return url.replace('/new/low/', '/new/high/')


def _parse_relative_date(rel_en: str, rel_ar: str = '') -> str:
    """
    Convert relative date strings like '4 days ago' / 'منذ 4 أيام'
    to an approximate YYYY-MM-DD string.
    Returns '' if unparseable.
    """
    today = datetime.now().date()
    text = (rel_en or rel_ar or '').strip().lower()

    # 'just now' / 'الآن'
    if not text or 'now' in text or 'الآن' in text or 'الان' in text:
        return today.isoformat()

    # English: "N unit(s) ago"
    m = re.search(r'(\d+)\s*(second|minute|hour|day|week|month|year)', text)
    if m:
        n, unit = int(m.group(1)), m.group(2)
        if unit in ('second', 'minute', 'hour'):
            return today.isoformat()
        if unit == 'day':
            return (today - timedelta(days=n)).isoformat()
        if unit == 'week':
            return (today - timedelta(days=n * 7)).isoformat()
        if unit == 'month':
            return (today - timedelta(days=n * 30)).isoformat()
        if unit == 'year':
            return (today - timedelta(days=n * 365)).isoformat()

    # Arabic: "منذ N وحدة"
    ar_text = rel_ar.strip()
    m = re.search(r'(\d+)\s*(ثانية|دقيقة|ساعة|يوم|أيام|أسبوع|أسابيع|شهر|أشهر|سنة|سنوات)', ar_text)
    if m:
        n, unit = int(m.group(1)), m.group(2)
        if unit in ('ثانية', 'دقيقة', 'ساعة'):
            return today.isoformat()
        if unit in ('يوم', 'أيام'):
            return (today - timedelta(days=n)).isoformat()
        if unit in ('أسبوع', 'أسابيع'):
            return (today - timedelta(days=n * 7)).isoformat()
        if unit in ('شهر', 'أشهر'):
            return (today - timedelta(days=n * 30)).isoformat()
        if unit in ('سنة', 'سنوات'):
            return (today - timedelta(days=n * 365)).isoformat()

    return ''


def _parse_classified(c: Dict) -> Dict:
    """Map a raw Carsy classified dict → sheet row dict."""
    cid     = str(c.get('id', ''))
    brand   = c.get('brand') or {}
    parent  = brand.get('parent') or {}
    user    = c.get('user') or {}

    # ── Core identification ────────────────────────────────────────────────
    data: Dict = {
        'scraped_at':   datetime.now().isoformat(),
        'source':       SOURCE,
        'id':           f'carsy_{cid}',
        'category':     'cars',
        'ad_title':     _clean(c.get('title_ar') or c.get('title_en') or ''),
        'listing_type': 'للبيع',
        'condition':    '',
        'body_type':    '',
        'car_url':      f'{BASE_URL}/cars/{cid}',
    }

    # ── Date ──────────────────────────────────────────────────────────────
    data['date_added'] = _parse_relative_date(
        c.get('created_at_en', ''),
        c.get('created_at_ar', ''),
    )

    # ── Make / Model ──────────────────────────────────────────────────────
    # In Carsy: brand.parent = make (e.g., Kia), brand = model (e.g., Sorento)
    data['brand'] = _clean(parent.get('name_ar') or parent.get('name_en') or
                           brand.get('name_ar') or brand.get('name_en') or '')
    data['model'] = _clean(brand.get('name_ar') or brand.get('name_en') or '')

    # ── Price ─────────────────────────────────────────────────────────────
    price_raw = str(c.get('price') or '')
    data['price'] = re.sub(r'[^\d.]', '', price_raw.replace(',', ''))

    # ── Location ──────────────────────────────────────────────────────────
    city_raw = _clean(str(c.get('city') or ''))
    data['location'] = CITY_AR.get(city_raw.lower(), city_raw)

    # ── Car specs ─────────────────────────────────────────────────────────
    data['year']          = _clean(str(c.get('year') or ''))
    data['engine']        = _clean(str(c.get('engine_capacity') or ''))
    data['cylinders']     = _clean(str(c.get('number_of_cylinders') or ''))
    data['color']         = _clean(str(c.get('external_color') or ''))
    data['interior_color']= _clean(str(c.get('internal_color') or ''))
    data['doors']         = ''
    data['vin']           = ''

    km = c.get('kilometers')
    data['mileage'] = str(km) if km is not None else ''

    raw_fuel = str(c.get('fuel_type') or '').strip()
    data['fuel_type'] = FUEL_MAP.get(raw_fuel, raw_fuel)

    raw_trans = str(c.get('transmission') or '').strip()
    data['transmission'] = TRANSMISSION_MAP.get(raw_trans, raw_trans)

    raw_drive = str(c.get('drive_line') or '').strip()
    data['drive_system'] = DRIVE_MAP.get(raw_drive, raw_drive)

    # ── Description (combine desc + source + specifications) ───────────────
    parts = []
    desc = _clean(c.get('description') or '')
    if desc:
        parts.append(desc)
    src = SOURCE_MAP.get(str(c.get('source') or '').strip(), '')
    if src:
        parts.append(f'المصدر: {src}')
    specs = SPECS_MAP.get(str(c.get('specifications') or '').strip(), '')
    if specs:
        parts.append(f'المواصفات: {specs}')
    data['description'] = ' | '.join(parts)

    # ── Seller ────────────────────────────────────────────────────────────
    data['seller_name'] = _clean(user.get('name') or '')
    phone = _clean(str(user.get('phone') or ''))
    data['contact'] = ('+' + phone) if phone and not phone.startswith('+') else phone

    # ── Images (internal key, popped before writing to sheet) ─────────────
    raw_imgs: List[str] = [
        img for img in (c.get('images') or [])
        if isinstance(img, str) and img.startswith('http')
    ]
    # Upgrade to high-quality
    data['_image_urls'] = [_hq_image(u) for u in raw_imgs]

    return data


# ── Main scraper class ────────────────────────────────────────────────────────


class CarsyScraper:

    def __init__(self, full_mode: bool = False, max_hours: Optional[float] = None):
        self.full_mode = full_mode
        self.deadline: Optional[datetime] = (
            datetime.now() + timedelta(hours=max_hours) if max_hours else None
        )
        self._stop_requested = False

        signal.signal(signal.SIGINT,  self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)

        logger.info('Authenticating with Google APIs (OAuth2) …')
        creds = _get_oauth_credentials()
        self.gc    = gspread.authorize(creds)
        self.drive = build('drive', 'v3', credentials=creds)

        spreadsheet = self.gc.open_by_key(SHEET_ID)
        try:
            self.sheet = spreadsheet.worksheet(SHEET_TAB)
            logger.info(f'Using existing "{SHEET_TAB}" tab.')
        except gspread.exceptions.WorksheetNotFound:
            logger.info(f'Creating "{SHEET_TAB}" tab …')
            self.sheet = spreadsheet.add_worksheet(
                title=SHEET_TAB, rows=2000, cols=len(COLUMNS)
            )

        self._ensure_headers()
        self.existing_ids: Set[str] = self._load_existing_ids()
        self.progress: Dict         = _load_progress()

        logger.info(f'Sheet has {len(self.existing_ids)} existing IDs.')
        logger.info(
            f'Progress → last_page={self.progress["last_page"]}, '
            f'total_scraped={self.progress["total_scraped"]}'
        )

    # ── Signal handling ───────────────────────────────────────────────────────

    def _handle_signal(self, signum, frame):
        logger.warning('\nInterrupt received — finishing current car then stopping …')
        self._stop_requested = True

    def _should_stop(self) -> bool:
        if self._stop_requested:
            return True
        if self.deadline and datetime.now() >= self.deadline:
            logger.info('Time limit reached.')
            return True
        return False

    # ── Google Sheets helpers ─────────────────────────────────────────────────

    def _ensure_headers(self):
        first = self.sheet.row_values(1)
        if first == COLUMNS:
            return
        if not first or first[0] != COLUMNS[0]:
            logger.info('Writing fresh header row …')
            self.sheet.clear()
            self.sheet.insert_row(COLUMNS, 1)
            return
        logger.info('Header mismatch — updating columns …')
        for col_idx, col_name in enumerate(COLUMNS):
            if col_idx >= len(first) or first[col_idx] != col_name:
                logger.info(f'  Inserting column "{col_name}" at position {col_idx + 1}')
                self.sheet.spreadsheet.batch_update({'requests': [{
                    'insertDimension': {
                        'range': {
                            'sheetId': self.sheet.id,
                            'dimension': 'COLUMNS',
                            'startIndex': col_idx,
                            'endIndex': col_idx + 1,
                        },
                        'inheritFromBefore': False,
                    }
                }]})
                self.sheet.update_cell(1, col_idx + 1, col_name)
                first = self.sheet.row_values(1)
        logger.info('Headers updated.')

    def _load_existing_ids(self) -> Set[str]:
        col_idx = COLUMNS.index('id') + 1
        vals = self.sheet.col_values(col_idx)
        return set(vals[1:])

    def _append_row(self, data: Dict):
        row = ['' if data.get(col) is None else str(data.get(col, '')) for col in COLUMNS]
        self.sheet.append_row(row, value_input_option='RAW')

    def _sort_sheet_by_date(self):
        try:
            date_col_idx = COLUMNS.index('date_added')
            self.sheet.spreadsheet.batch_update({
                'requests': [{
                    'sortRange': {
                        'range': {
                            'sheetId': self.sheet.id,
                            'startRowIndex': 1,
                            'startColumnIndex': 0,
                            'endColumnIndex': len(COLUMNS),
                        },
                        'sortSpecs': [{'dimensionIndex': date_col_idx,
                                       'sortOrder': 'DESCENDING'}],
                    }
                }]
            })
            logger.info('Sheet sorted by date_added.')
        except Exception as exc:
            logger.warning(f'Could not sort sheet: {exc}')

    # ── Google Drive helpers ──────────────────────────────────────────────────

    def _make_public(self, file_id: str):
        self.drive.permissions().create(
            fileId=file_id,
            body={'type': 'anyone', 'role': 'reader'},
        ).execute()

    def _create_subfolder(self, name: str) -> Tuple[str, str]:
        meta = {
            'name': name,
            'mimeType': 'application/vnd.google-apps.folder',
            'parents': [DRIVE_FOLDER_ID],
        }
        f = self.drive.files().create(body=meta, fields='id,webViewLink').execute()
        self._make_public(f['id'])
        return f['id'], f.get('webViewLink', '')

    def _upload_image(self, img_url: str, folder_id: str, filename: str) -> Optional[str]:
        try:
            r = requests.get(img_url, headers=BROWSER_HEADERS, timeout=30)
            r.raise_for_status()
            mime = r.headers.get('Content-Type', 'image/webp').split(';')[0]
            media = MediaIoBaseUpload(io.BytesIO(r.content), mimetype=mime)
            f = self.drive.files().create(
                body={'name': filename, 'parents': [folder_id]},
                media_body=media,
                fields='id,webViewLink',
            ).execute()
            self._make_public(f['id'])
            return f.get('webViewLink', '')
        except Exception as exc:
            logger.warning(f'    Image upload failed ({img_url}): {exc}')
            # Fallback: try low-quality URL
            if '/new/high/' in img_url:
                return self._upload_image(
                    img_url.replace('/new/high/', '/new/low/'), folder_id, filename
                )
            return None

    # ── API fetching ──────────────────────────────────────────────────────────

    def _api_get(self, url: str, params: Optional[Dict] = None) -> Dict:
        """GET the JSON API and return the parsed response dict."""
        r = requests.get(url, headers=API_HEADERS, params=params, timeout=30)
        r.raise_for_status()
        return r.json()

    def _fetch_listing_page(self, page: int) -> Tuple[List[int], int]:
        """
        Call the listing API for the given page number.
        Returns (list_of_car_ids, last_page).
        """
        data = self._api_get(API_LISTING_URL, params={'page': page})
        cars = data.get('data') or []
        pagination = data.get('pagination') or {}
        last_page = int(pagination.get('last_page', page))
        ids = [int(c['id']) for c in cars if c.get('id')]
        return ids, last_page

    def _fetch_detail(self, car_id: int) -> Optional[Dict]:
        """
        Call the detail API for a single car.
        Returns the parsed classified dict (ready for _parse_classified) or None.
        """
        try:
            data = self._api_get(f'{API_DETAIL_URL}/{car_id}')
            classified = (data.get('data') or {}).get('classified') or {}
            if not classified or not classified.get('id'):
                logger.warning(f'  Empty classified from API for {car_id}')
                return None
            return classified
        except requests.HTTPError as exc:
            if exc.response.status_code == 404:
                logger.info(f'  Car {car_id} not found (404)')
            else:
                logger.warning(f'  API error for {car_id}: {exc}')
            return None
        except Exception as exc:
            logger.warning(f'  Detail fetch failed for {car_id}: {exc}')
            return None

    # ── Per-car orchestration ─────────────────────────────────────────────────

    def _process_car(self, car_id: int) -> bool:
        car_key = f'carsy_{car_id}'
        logger.info(f'  → carsy.app/cars/{car_id}')

        classified = self._fetch_detail(car_id)
        if not classified:
            return False

        data = _parse_classified(classified)

        image_urls: List[str] = data.pop('_image_urls', [])
        data['images_original_links'] = ', '.join(image_urls)

        image_links: List[str] = []
        folder_url  = ''

        if image_urls:
            folder_name = f'carsy_{car_id}'
            try:
                folder_id, folder_url = self._create_subfolder(folder_name)
                for idx, img_url in enumerate(image_urls, 1):
                    ext   = (img_url.rsplit('.', 1)[-1].lower().split('?')[0] or 'webp')[:5]
                    fname = f'carsy_{car_id}_{idx:02d}.{ext}'
                    link  = self._upload_image(img_url, folder_id, fname)
                    if link:
                        image_links.append(link)
                logger.info(
                    f'  Uploaded {len(image_links)}/{len(image_urls)} images → {folder_url}'
                )
            except Exception as exc:
                logger.error(f'  Drive error for {car_id}: {exc}')

        data['images']           = ', '.join(image_links)
        data['image_folder_url'] = folder_url

        try:
            self._append_row(data)
            self.existing_ids.add(car_key)
            logger.info(f'  ✓  Row written: {data.get("ad_title", car_key)!r}')
            return True
        except Exception as exc:
            logger.error(f'  Sheet write failed: {exc}')
            return False

    # ── Repair-images mode ────────────────────────────────────────────────────

    def _repair_images(self):
        """
        Re-upload Drive images for every sheet row whose 'images' column is empty.
        Uses stored images_original_links first; falls back to re-calling the API.
        """
        logger.info('=== Repair-images mode ===')

        all_values = self.sheet.get_all_values()
        if not all_values:
            logger.info('Sheet is empty — nothing to repair.')
            return
        header = all_values[0]

        try:
            id_col         = header.index('id')
            images_col     = header.index('images')
            img_folder_col = header.index('image_folder_url')
            orig_col       = header.index('images_original_links')
            url_col        = header.index('car_url') if 'car_url' in header else -1
        except ValueError as exc:
            logger.error(f'Required column not found: {exc}')
            return

        to_repair = []
        for row_num, row in enumerate(all_values[1:], start=2):
            def _cell(idx, r=row):
                return r[idx].strip() if idx < len(r) else ''
            row_id = _cell(id_col)
            if row_id and not _cell(images_col):
                to_repair.append({
                    'row_num':    row_num,
                    'id':         row_id,
                    'orig_links': _cell(orig_col),
                    'car_url':    _cell(url_col) if url_col >= 0 else '',
                })

        logger.info(f'Rows needing image repair: {len(to_repair)}')
        if not to_repair:
            logger.info('Nothing to do.')
            return

        repaired = 0
        for item in to_repair:
            if self._should_stop():
                break

            row_id  = item['id']
            row_num = item['row_num']

            # Step 1: use already-stored original URLs
            image_urls = [u.strip() for u in item['orig_links'].split(',') if u.strip()]

            # Step 2: re-fetch from API using car_url
            if not image_urls and item['car_url']:
                m = re.search(r'/cars/(\d+)', item['car_url'])
                if m:
                    car_id = int(m.group(1))
                    classified = self._fetch_detail(car_id)
                    if classified:
                        raw_imgs = [
                            img for img in (classified.get('images') or [])
                            if isinstance(img, str) and img.startswith('http')
                        ]
                        image_urls = [_hq_image(u) for u in raw_imgs]

            if not image_urls:
                logger.info(f'  [{row_num}] {row_id} → no images, skipping')
                continue

            safe_id = re.sub(r'[^a-zA-Z0-9_-]', '_', row_id)
            image_links: List[str] = []
            folder_url  = ''
            try:
                folder_id, folder_url = self._create_subfolder(safe_id)
                for idx, img_url in enumerate(image_urls, 1):
                    ext   = (img_url.rsplit('.', 1)[-1].lower().split('?')[0] or 'webp')[:5]
                    fname = f'{safe_id}_{idx:02d}.{ext}'
                    link  = self._upload_image(img_url, folder_id, fname)
                    if link:
                        image_links.append(link)
                logger.info(
                    f'  [{row_num}] {row_id} → '
                    f'uploaded {len(image_links)}/{len(image_urls)} images'
                )
            except Exception as exc:
                logger.error(f'  [{row_num}] Drive error for {row_id}: {exc}')
                time.sleep(REQUEST_DELAY)
                continue

            if image_links or folder_url:
                try:
                    self.sheet.update_cell(row_num, images_col + 1,     ', '.join(image_links))
                    self.sheet.update_cell(row_num, img_folder_col + 1, folder_url)
                    repaired += 1
                    logger.info(f'  [{row_num}] ✓ {row_id} updated')
                except Exception as exc:
                    logger.error(f'  [{row_num}] Sheet update failed for {row_id}: {exc}')

            time.sleep(REQUEST_DELAY)

        logger.info(f'\nRepair complete: {repaired}/{len(to_repair)} rows updated.')

    # ── Main loop ─────────────────────────────────────────────────────────────

    def run(self):
        """
        Paginate the listing API, then fetch full details for each new car.

        Incremental mode (default):
          Starts at page 1. Stops after STOP_AFTER_FULL_PAGES consecutive pages
          with no new cars (meaning we have caught up with live listings).

        Full-scrape mode (--full):
          Resumes from progress['last_page']+1. Does not stop on caught-up pages.
          Continues until the last API page.
        """
        progress = self.progress

        if self.full_mode:
            start_page = progress['last_page'] + 1
            if progress.get('full_scrape_done'):
                logger.info(
                    'Full scrape already complete. '
                    'Delete carsy_progress.json to restart.'
                )
                return
            logger.info(f'Full scrape mode — resuming from page {start_page}')
        else:
            start_page = 1
            logger.info('Incremental mode — starting from page 1')

        logger.info('=' * 62)
        logger.info(f'Carsy scraper started  {datetime.now().isoformat()}')
        if self.deadline:
            logger.info(f'Will stop at: {self.deadline.isoformat()}')
        logger.info(f'Existing sheet rows: {len(self.existing_ids)}')
        logger.info('=' * 62)

        total_new        = 0
        full_page_streak = 0
        page             = start_page
        last_page        = 9999  # will be updated on first fetch

        while page <= last_page:
            if self._should_stop():
                break

            logger.info(f'\n[Page {page}/{last_page}]')

            # ── Fetch car IDs from listing API ────────────────────────────
            try:
                car_ids, last_page = self._fetch_listing_page(page)
            except requests.HTTPError as exc:
                logger.error(f'  Listing API error: {exc}')
                break
            except Exception as exc:
                logger.error(f'  Listing page error: {exc}')
                break

            if not car_ids:
                logger.info('  No car IDs returned — stopping.')
                if self.full_mode:
                    progress['full_scrape_done'] = True
                    _save_progress(progress)
                break

            # ── Filter to new cars only ────────────────────────────────────
            new_ids = [cid for cid in car_ids
                       if f'carsy_{cid}' not in self.existing_ids]
            logger.info(f'  {len(car_ids)} total | {len(new_ids)} new')

            if not new_ids:
                if not self.full_mode:
                    full_page_streak += 1
                    logger.info(
                        f'  All existing. Streak: {full_page_streak}'
                        f'/{STOP_AFTER_FULL_PAGES}'
                    )
                    if full_page_streak >= STOP_AFTER_FULL_PAGES:
                        logger.info('  Caught up — stopping pagination.')
                        break
                else:
                    logger.info('  All existing — continuing (full mode).')
                    progress['last_page'] = page
                    _save_progress(progress)
                time.sleep(REQUEST_DELAY)
                page += 1
                continue

            full_page_streak = 0

            # ── Scrape + upload each new car ──────────────────────────────
            for car_id in new_ids:
                if self._should_stop():
                    if self.full_mode:
                        progress['last_page'] = page - 1
                        _save_progress(progress)
                    break
                ok = self._process_car(car_id)
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

        # Mark full scrape done if we naturally reached the end
        if self.full_mode and page > last_page:
            progress['full_scrape_done'] = True
            _save_progress(progress)

        logger.info('\n' + '=' * 62)
        logger.info(f'Done. {total_new} new listings written to Google Sheets.')
        if self.full_mode:
            logger.info(
                f'Progress: last_page={progress["last_page"]}, '
                f'total_scraped={progress["total_scraped"]}, '
                f'full_scrape_done={progress.get("full_scrape_done", False)}'
            )
        logger.info('=' * 62)

        if total_new > 0:
            self._sort_sheet_by_date()


# ── Entry point ───────────────────────────────────────────────────────────────


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Carsy.app standalone scraper',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
examples:
  python carsy_standalone.py                     # incremental (daily update)
  python carsy_standalone.py --hours 2           # run for 2 hours then stop
  python carsy_standalone.py --full              # full scrape, resume from last page
  python carsy_standalone.py --full --hours 4    # full scrape, 4-hour session
  python carsy_standalone.py --repair-images     # fix rows with empty images
        """,
    )
    parser.add_argument('--hours', type=float, metavar='N',
                        help='Stop gracefully after N hours')
    parser.add_argument('--full', action='store_true',
                        help='Full-scrape mode: resume from the last saved page')
    parser.add_argument('--repair-images', action='store_true',
                        help=(
                            'Repair mode: re-upload Drive images for existing rows '
                            'whose "images" column is empty. Does not scrape new listings.'
                        ))
    args = parser.parse_args()

    if sys.stdout.encoding != 'utf-8':
        sys.stdout.reconfigure(encoding='utf-8')

    if not os.path.exists(OAUTH_CLIENT_FILE):
        print(f'ERROR: OAuth2 client secret not found:\n  {OAUTH_CLIENT_FILE}')
        sys.exit(1)

    scraper = CarsyScraper(full_mode=args.full, max_hours=args.hours)
    if args.repair_images:
        scraper._repair_images()
    else:
        scraper.run()
