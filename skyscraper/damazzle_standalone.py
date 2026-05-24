#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Damazzle.com Standalone Scraper  (v2 — API intercept)
======================================================
Scrapes https://damazzle.com/motors/cars/search using Playwright to load
each listing page, then intercepts the Angular app's own API calls to get
full car data — including the REAL seller phone — without any detail-page
navigation.

KEY BEHAVIOURS
--------------
• Auth         : OAuth2 user credentials — images owned by you, no quota errors.
• Browser      : Playwright navigates each listing page (Angular CSR). The
                 Angular app's internal API responses are intercepted.
• API data     : Each intercepted car object contains phone, whatsapp, gallery,
                 featured_fields (mileage/year), governorate, seller info, etc.
• Contact fix  : Phone comes from car.phone in the API response — the real
                 seller phone, NOT the site footer number.
• Date filter  : published_date < 2026 → listing is skipped. All-pre-2026
                 page → scraping stops.
• Deduplication: Reads 'id' column from the sheet on startup; skips existing.
• Progress     : --full mode saves last_page to damazzle_progress.json.
• Sort         : Sheet is sorted by date_added (newest first) after each run.
• Mileage      : 'كم' / 'km' suffix and thousands-separators stripped.

COLUMNS (same as syriacars_test.py plus date_added)
----------------------------------------------------
scraped_at | date_added | source | id | category | ad_title | listing_type |
condition | body_type | brand | model | price | location | year | drive_system |
transmission | fuel_type | mileage | engine | cylinders | color |
interior_color | doors | vin | description | seller_name | contact |
images | image_folder_url | images_original_links | car_url

SETUP
-----
pip install requests gspread google-auth google-auth-oauthlib
pip install google-api-python-client playwright
playwright install chromium

USAGE
-----
  python damazzle_standalone.py --hours 1
  python damazzle_standalone.py --full --hours 4
  python damazzle_standalone.py
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
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

import gspread
from google.auth.transport.requests import Request
from google.oauth2 import credentials as google_creds_module
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from normalizer import normalize_car

# ── Logging ───────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)-8s %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('damazzle_scraper.log', encoding='utf-8'),
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
PROGRESS_FILE    = os.path.join(SCRIPT_DIR, 'damazzle_progress.json')

SHEET_ID        = '1TGaxrXEjiwihwceN2LBiS6BrR0E3rUjnaBJxI7a9mBo'
DRIVE_FOLDER_ID = '1JrEXZVNlfL54Z22lRWtEDHkT4mnVNCIf'

LISTING_URL     = 'https://damazzle.com/motors/cars/search'
API_BASE        = 'https://beta.damazzletech.com/api/api/v1/client'
API_DETAIL_BASE = 'https://beta.damazzletech.com/api/api/v1/ads/details-by-slug'
SOURCE          = 'damazzle'

UA = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
    'AppleWebKit/537.36 (KHTML, like Gecko) '
    'Chrome/120.0.0.0 Safari/537.36'
)
API_HEADERS = {
    'User-Agent': UA,
    'Accept': 'application/json',
    'Accept-Language': 'ar,en-US;q=0.9',
    'Origin': 'https://damazzle.com',
    'Referer': 'https://damazzle.com/',
}

SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive',
]

REQUEST_DELAY         = 1.5
STOP_AFTER_FULL_PAGES = 2
CUTOFF_DATE           = '2026-01-01'   # skip listings published before this

# ── featured_fields slug → sheet column ───────────────────────────────────────
# The Angular app exposes structured car specs via featured_fields.
# Each entry has template_field.slug and value.ar.

SLUG_MAP: Dict[str, str] = {
    'traveled_distance':    'mileage',
    'year_of_manufacture':  'year',
    'color':                'color',
    'Color':                'color',         # detail endpoint capitalisation
    'exterior_color':       'color',
    'interior_color':       'interior_color',
    'fuel_type':            'fuel_type',
    'Fuel_type':            'fuel_type',     # detail endpoint capitalisation
    'transmission':         'transmission',
    'Transmission':         'transmission',  # detail endpoint uses capital T
    'gearbox':              'transmission',
    'condition':            'condition',
    'Condition':            'condition',     # detail endpoint uses capital C
    'car_condition':        'condition',
    'engine_capacity':      'engine',
    'engine':               'engine',
    'body_type':            'body_type',
    'drive_system':         'drive_system',
    'drive_type':           'drive_system',
    'doors':                'doors',
    'cylinders':            'cylinders',
    'vin':                  'vin',
    'chassis':              'vin',
}

# Also map Arabic label text as fallback
LABEL_MAP: Dict[str, str] = {
    'المسافة المقطوعة':  'mileage',
    'الكيلومترات':       'mileage',
    'الكيلومتراج':       'mileage',
    'سنة الصنع':         'year',
    'السنة':             'year',
    'اللون':             'color',
    'اللون الخارجي':     'color',
    'اللون الداخلي':     'interior_color',
    'نوع الوقود':        'fuel_type',
    'الوقود':            'fuel_type',
    'ناقل الحركة':       'transmission',
    'الغيار':            'transmission',
    'الحالة':            'condition',
    'الشروط':            'condition',
    'المحرك':            'engine',
    'سعة المحرك':        'engine',
    'نوع الجسم':         'body_type',
    'نظام الدفع':        'drive_system',
    'نوع الدفع':         'drive_system',
    'عدد الأبواب':       'doors',
    'عدد الابواب':       'doors',
    'السلندرات':         'cylinders',
    'عدد السلندرات':     'cylinders',
    'رقم الهيكل':        'vin',
    'رقم الشاصي':        'vin',
}

# ── Sheet columns ─────────────────────────────────────────────────────────────

COLUMNS: List[str] = [
    'scraped_at',
    'date_added',           # listing published date (YYYY-MM-DD)
    'source',
    'id',
    'category',
    'ad_title',
    'listing_type',
    'condition',
    'body_type',
    'brand',
    'model',
    'price',
    'location',
    'year',
    'drive_system',
    'transmission',
    'fuel_type',
    'mileage',
    'engine',
    'cylinders',
    'color',
    'interior_color',
    'doors',
    'vin',
    'description',
    'seller_name',
    'contact',
    'images',                # Drive view links (comma-separated)
    'image_folder_url',      # per-car Drive sub-folder link
    'images_original_links', # original Damazzle CDN URLs
    'car_url',               # detail page link
]

# ── OAuth2 helpers ────────────────────────────────────────────────────────────


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
            creds = None

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            logger.info('Refreshing OAuth2 token …')
            creds.refresh(Request())
        else:
            logger.info('No valid token — launching browser consent flow …')
            flow = InstalledAppFlow.from_client_secrets_file(OAUTH_CLIENT_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(OAUTH_TOKEN_FILE, 'w', encoding='utf-8') as fh:
            fh.write(creds.to_json())
        logger.info(f'Token saved → {OAUTH_TOKEN_FILE}')

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
    logger.info(
        f'Progress saved → page {progress["last_page"]}, '
        f'{progress["total_scraped"]} total scraped.'
    )


# ── Pure helper functions ─────────────────────────────────────────────────────


def _clean(text) -> str:
    if not text:
        return ''
    t = ' '.join(str(text).split())
    return '' if t in ('-', '—', '–') else t


def _clean_mileage(v: str) -> str:
    v = re.sub(r'[,،٬]', '', v)
    v = re.sub(r'\s*(كم|km)\s*$', '', v, flags=re.I).strip()
    return v


def _parse_price(text) -> Optional[str]:
    """Return price as comma-formatted integer string: 10300 → '10,300'."""
    if not text:
        return None
    digits = re.sub(r'[^\d.]', '', str(text).replace(',', ''))
    try:
        v = float(digits)
        return f'{int(v):,}'    # "10,300"
    except (ValueError, TypeError):
        return None


def _clean_desc(text: str) -> str:
    """
    Clean a description that may contain HTML tags (<p>, <br>, &nbsp;, …).
    Falls back to plain-text normalisation when no HTML is detected.
    """
    if not text:
        return ''
    if '<' in text:
        soup = BeautifulSoup(text, 'html.parser')
        # Join block elements with newlines so structure is preserved
        for tag in soup.find_all(['p', 'br', 'div', 'li']):
            tag.insert_after('\n')
        text = soup.get_text(separator='')
    # Collapse multiple blank lines → single newline; strip trailing spaces
    lines = [l.rstrip() for l in text.splitlines()]
    text = '\n'.join(lines)
    text = re.sub(r'\n{3,}', '\n\n', text).strip()
    return text


def _parse_iso_date(dt_str: str) -> str:
    """'2026-05-07T08:12:39.000000Z' → '2026-05-07'"""
    if not dt_str:
        return ''
    m = re.match(r'(\d{4}-\d{2}-\d{2})', dt_str)
    return m.group(1) if m else ''


def _set_field(data: Dict, field: str, value: str) -> None:
    """Store value in data[field] if not already set (first-value-wins)."""
    if field and field not in data and value:
        if field == 'mileage':
            value = _clean_mileage(value)
        data[field] = value


def _extract_from_featured_fields(data: Dict, featured_fields: List[Dict]) -> None:
    """Parse the API's featured_fields array into structured sheet columns."""
    for ff in featured_fields:
        slug = (ff.get('template_field') or {}).get('slug', '')
        label_ar = (ff.get('template_field') or {}).get('field_name_ar', '')
        val_ar = _clean((ff.get('value') or {}).get('ar', ''))

        if not val_ar or val_ar in ('غير محدد', 'غير_محدد', '-', ''):
            continue

        # Try slug map first, then Arabic label map
        field = SLUG_MAP.get(slug) or LABEL_MAP.get(label_ar)
        if field:
            _set_field(data, field, val_ar)


def _parse_description_specs(data: Dict, description: str) -> None:
    """
    Extract structured specs from the description freetext.

    Damazzle sellers typically format descriptions with Arabic bullet-points:
      ▪نوع الـسـيـارة  :  MINI Cooper Countryman S
      ▪سـنـة الـصـنـع  :  2012
      ▪الـحـالـة الـفـنـيـة :  خالية برا جوا
      ▪ناقل الحركة  :  أوتوماتيك
      ▪نوع الوقود  :  بنزين
      ▪اللون  :  أبيض
      📌العنوان  :  دمشق / القصور
      تواجد دمشق

    Arabic tatweel (ـ) is stripped from labels before matching.
    """
    if not description:
        return

    # Strip Arabic tatweel (elongation character) from the whole text
    desc = re.sub(r'ـ', '', description)

    # ── Label → field map (tatweel-stripped Arabic labels) ──────────────────
    # "model" here means the specific car name from the free-text bullet
    DESC_MAP: Dict[str, str] = {
        'نوع السيارة':       'model',
        'الموديل':           'model',
        'نوع الوقود':        'fuel_type',
        'الوقود':            'fuel_type',
        'ناقل الحركة':       'transmission',
        'الغيار':            'transmission',
        'نوع الغيار':        'transmission',
        'اللون':             'color',
        'اللون الخارجي':     'color',
        'اللون الداخلي':     'interior_color',
        'الحالة الفنية':     'condition',
        'الحالة':            'condition',
        'الشروط':            'condition',
        'شروط':              'condition',
        'نوع الهيكل':        'body_type',
        'نوع الجسم':         'body_type',
        'سعة المحرك':        'engine',
        'المحرك':            'engine',
        'سنة الصنع':         'year',
        'السنة':             'year',
        'المسافة المقطوعة':  'mileage',
        'الكيلومتراج':       'mileage',
        'عدد الأبواب':       'doors',
        'عدد الابواب':       'doors',
        'نظام الدفع':        'drive_system',
        'نوع الدفع':         'drive_system',
        'السلندرات':         'cylinders',
        'عدد السلندرات':     'cylinders',
    }

    # ── 1. Parse ▪label : value bullet points ────────────────────────────────
    for m in re.finditer(
        r'[▪▸•]\s*(.{2,30}?)\s*[:：]\s*(.{1,120}?)(?=\n|[▪▸•]|$)',
        desc,
    ):
        label = re.sub(r'\s+', ' ', m.group(1)).strip()
        value = _clean(m.group(2))
        if not label or not value:
            continue

        field = DESC_MAP.get(label)
        if field == 'mileage':
            value = _clean_mileage(value)
        if field and value:
            _set_field(data, field, value)

    # ── 2. Location: 📌العنوان or تواجد ─────────────────────────────────────
    if 'location' not in data:
        for pattern in [
            r'(?:📌\s*)?العنوان\s*[:：]\s*([^\n/▪،,\d]{2,40})',
            r'تواجد\s+([^\n/▪،,\d]{2,30})',
        ]:
            loc_m = re.search(pattern, desc)
            if loc_m:
                loc = _clean(loc_m.group(1))
                if loc:
                    _set_field(data, 'location', loc)
                    break

    # ── 3. Mileage in free text: "ماشية 186000" / "80 الف كيلو" ────────────
    if 'mileage' not in data:
        m = re.search(
            r'(?:ماشية|عداد)[^\d]*(\d[\d,،٬.]*)\s*(?:(الف|ألف)\s*)?(?:كيلو|كم|km|K)?',
            desc, re.I,
        )
        if m:
            raw = re.sub(r'[,،٬.]', '', m.group(1))
            if m.group(2):              # "الف / ألف" → × 1000
                try:
                    raw = str(int(raw) * 1000)
                except ValueError:
                    pass
            if raw.isdigit():
                _set_field(data, 'mileage', raw)

    # ── 4. Year fallback ─────────────────────────────────────────────────────
    if 'year' not in data:
        m = re.search(r'(?:سنة|موديل)\s*(?:الصنع|الإنتاج)?\s*[:،]?\s*(20\d{2}|19\d{2})', desc)
        if m:
            _set_field(data, 'year', m.group(1))


# ── Main scraper class ────────────────────────────────────────────────────────


class DamazzleScraper:

    def __init__(self, full_mode: bool = False, max_hours: Optional[float] = None):
        self.full_mode = full_mode
        self.deadline: Optional[datetime] = (
            datetime.now() + timedelta(hours=max_hours) if max_hours else None
        )
        self._stop_requested = False

        self._pw      = None
        self._browser = None
        self._page    = None

        signal.signal(signal.SIGINT,  self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)

        logger.info('Authenticating with Google APIs (OAuth2) …')
        creds = _get_oauth_credentials()
        self.gc    = gspread.authorize(creds)
        self.drive = build('drive', 'v3', credentials=creds)

        self.sheet = self.gc.open_by_key(SHEET_ID).sheet1
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

    # ── Playwright lifecycle ──────────────────────────────────────────────────

    def _init_browser(self):
        logger.info('Launching Playwright browser (headless Chromium) …')
        self._pw      = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=True)
        self._page    = self._browser.new_page(user_agent=UA)
        self._page.set_extra_http_headers({'Accept-Language': 'ar,en-US;q=0.9,en;q=0.8'})

    def _close_browser(self):
        for obj, method in [
            (self._page,    'close'),
            (self._browser, 'close'),
            (self._pw,      'stop'),
        ]:
            try:
                if obj:
                    getattr(obj, method)()
            except Exception:
                pass
        self._page = self._browser = self._pw = None
        logger.info('Browser closed.')

    # ── Google Sheets helpers ─────────────────────────────────────────────────

    def _ensure_headers(self):
        """Ensure row 1 matches COLUMNS exactly; clear and rewrite if structure changed."""
        first = self.sheet.row_values(1)
        if first == COLUMNS:
            return  # already correct
        if not first or first[0] != COLUMNS[0]:
            logger.info('Writing fresh header row …')
            self.sheet.clear()
            self.sheet.insert_row(COLUMNS, 1)
            return
        # Column list changed — insert missing columns at the right positions.
        logger.info(f'Header mismatch — updating columns …')
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
        """Sort all data rows by date_added descending (newest first)."""
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
                        'sortSpecs': [{
                            'dimensionIndex': date_col_idx,
                            'sortOrder': 'DESCENDING',
                        }],
                    }
                }]
            })
            logger.info('Sheet sorted by date_added (newest first).')
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
            r = requests.get(img_url, timeout=30, headers={'User-Agent': UA})
            r.raise_for_status()
            mime = r.headers.get('Content-Type', 'image/jpeg').split(';')[0]
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
            return None

    # ── Detail-by-slug API: full structured fields ────────────────────────────

    def _fetch_detail_fields(self, slug: str) -> List[Dict]:
        """
        Call  GET /api/v1/ads/details-by-slug/{slug}  and return the 'fields'
        array from  data.ad.fields.

        This endpoint exposes ALL structured specs shown on the detail page
        under "معلومات اضافية" (color, fuel_type, Transmission, Condition,
        year, mileage, seats …).  The listing-page intercept only returns 2
        featured_fields; this call fills the remaining structured fields.
        """
        if not slug:
            return []
        try:
            r = requests.get(
                f'{API_DETAIL_BASE}/{slug}',
                headers=API_HEADERS,
                timeout=15,
            )
            if r.status_code != 200:
                return []
            body = r.json()
            ad = (body.get('data') or {}).get('ad') or {}
            return ad.get('fields') or []
        except Exception as exc:
            logger.warning(f'  detail-by-slug failed for {slug!r}: {exc}')
            return []

    def _fetch_detail_images(self, slug: str) -> List[str]:
        """
        Get the gallery image URLs for a car from the detail-by-slug API.
        Used by _repair_images when images_original_links was not stored.
        """
        if not slug:
            return []
        try:
            r = requests.get(f'{API_DETAIL_BASE}/{slug}', headers=API_HEADERS, timeout=15)
            if r.status_code != 200:
                return []
            body = r.json()
            ad = (body.get('data') or {}).get('ad') or {}
            gallery = ad.get('gallery') or []
            imgs = [img['src'] for img in gallery if isinstance(img, dict) and img.get('src')]
            if not imgs and ad.get('cover_image'):
                imgs = [ad['cover_image']]
            return imgs
        except Exception as exc:
            logger.warning(f'  detail images fetch failed for {slug!r}: {exc}')
            return []

    # ── Repair-data mode ─────────────────────────────────────────────────────

    def repair_data(self):
        """Normalize all existing sheet rows using Sayarti canonical values."""
        logger.info('=== Repair-data mode (normalize all fields) ===')
        NORMALIZABLE = [
            'price', 'engine_size', 'mileage', 'year', 'seats', 'horsepower',
            'cylinders', 'doors', 'fuel_type', 'transmission', 'origin',
            'body_type', 'city', 'exterior_color', 'interior_color', 'condition',
            'make', 'model',
        ]
        all_values = self.sheet.get_all_values()
        if not all_values:
            logger.info('Sheet is empty — nothing to repair.')
            return
        header = all_values[0]
        fixed = 0
        for row_num, row in enumerate(all_values[1:], start=2):
            raw = {header[i]: row[i] if i < len(row) else '' for i in range(len(header))}
            car_id = raw.get('id', str(row_num))
            normalized = normalize_car(raw)
            updates = {}
            for col in NORMALIZABLE:
                old = raw.get(col, '')
                new = normalized.get(col, '')
                if new and new != old:
                    updates[col] = new
            if updates:
                for col, new_val in updates.items():
                    try:
                        col_idx = header.index(col) + 1
                        self.sheet.update_cell(row_num, col_idx, new_val)
                    except ValueError:
                        pass
                fixed += 1
                logger.info(f'  [{car_id}] updated: {list(updates.keys())}')
        logger.info(f'Repair complete — {fixed} rows updated.')

    # ── Repair-images mode ────────────────────────────────────────────────────

    def _repair_images(self):
        """
        Re-upload Drive images for every sheet row whose 'images' column is empty.

        Strategy (fastest first):
          1. Re-use images_original_links already stored in the sheet — no HTTP.
          2. If those are missing, call the detail-by-slug API using the slug
             extracted from car_url — still no browser needed.
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

            # Step 1: use stored original URLs — no network call needed
            image_urls = [u.strip() for u in item['orig_links'].split(',') if u.strip()]

            # Step 2: fall back to detail API if original links are missing
            if not image_urls:
                slug = ''
                if item['car_url']:
                    m = re.search(r'/ads/([^/?#]+)', item['car_url'])
                    if m:
                        slug = m.group(1)
                if slug:
                    image_urls = self._fetch_detail_images(slug)
                    if image_urls:
                        logger.info(f'  [{row_num}] {row_id} → fetched {len(image_urls)} images via API')
                else:
                    logger.warning(f'  [{row_num}] {row_id} → no car_url/slug, skipping')
                    continue

            if not image_urls:
                logger.info(f'  [{row_num}] {row_id} → no images available, skipping')
                continue

            # Step 3: upload to Drive
            safe_id = re.sub(r'[^a-zA-Z0-9_-]', '_', row_id)
            image_links: List[str] = []
            folder_url  = ''
            try:
                folder_id, folder_url = self._create_subfolder(safe_id)
                for idx, img_url in enumerate(image_urls, 1):
                    ext   = (img_url.rsplit('.', 1)[-1].lower().split('?')[0] or 'jpg')[:5]
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

            # Step 4: update ONLY the images + image_folder_url cells
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

    # ── Listing page: intercept Angular's API calls ───────────────────────────

    def _scrape_listing_page(self, page_url: str) -> List[Dict]:
        """
        Navigate to one Damazzle listing page.  The Angular app fires an API
        request to /api/v1/client/ads?...  We intercept that response to get
        all car data (including phone, gallery, date) without navigating to
        individual detail pages.

        Returns a list of raw car dicts from the API (possibly empty).
        """
        captured: List[Dict] = []

        def _on_response(resp):
            url = resp.url
            # The Angular listing page calls its own API to populate the cards.
            if 'damazzletech.com' in url and '/ads' in url:
                try:
                    body = resp.body()
                    if not body or len(body) > 2_000_000:
                        return
                    d = json.loads(body)
                    if isinstance(d, dict) and isinstance(d.get('data'), list):
                        for car in d['data']:
                            if isinstance(car, dict) and car.get('id'):
                                captured.append(car)
                except Exception:
                    pass

        self._page.on('response', _on_response)

        try:
            self._page.goto(page_url, wait_until='domcontentloaded', timeout=30000)
        except Exception:
            try:
                self._page.goto(page_url, wait_until='networkidle', timeout=30000)
            except Exception as exc:
                logger.warning(f'  Listing page load failed: {exc}')
                self._page.remove_listener('response', _on_response)
                return []

        # Wait for Angular to finish loading cards
        time.sleep(5)
        try:
            self._page.wait_for_selector('.product-card, h5.product-title', timeout=15000)
        except Exception:
            pass
        time.sleep(2)

        self._page.remove_listener('response', _on_response)

        # De-duplicate by ID (Angular may fire the same request twice)
        seen: Set[int] = set()
        unique: List[Dict] = []
        for car in captured:
            cid = car.get('id')
            if cid not in seen:
                seen.add(cid)
                unique.append(car)

        logger.info(f'  Intercepted {len(unique)} car records from API.')
        return unique

    # ── Parse one intercepted car dict ────────────────────────────────────────

    def _parse_car(self, car: Dict) -> Dict:
        """
        Convert a raw Damazzle API car object into a sheet row dict.
        All data comes from the API — no HTML parsing, no detail page load.
        """
        numeric_id = car.get('id')
        slug       = car.get('slug', '')
        car_url    = car.get('ad_link') or (f'https://damazzle.com/ads/{slug}' if slug else '')
        car_id     = f'damazzle_{numeric_id}'

        data: Dict = {
            'scraped_at':   datetime.now().isoformat(),
            'source':       SOURCE,
            'id':           car_id,
            'category':     'cars',
            'car_url':      car_url,
            'listing_type': 'للبيع',
        }

        # ── Date added ────────────────────────────────────────────────────────
        data['date_added'] = _parse_iso_date(car.get('published_date', ''))

        # ── Title ─────────────────────────────────────────────────────────────
        title = _clean(car.get('title') or car.get('title_ar', ''))
        data['ad_title'] = title
        if any(k in title for k in ('للإيجار', 'للايجار', 'للتأجير', 'إيجار')):
            data['listing_type'] = 'للإيجار'

        # ── Price (comma-formatted, no currency symbol) ───────────────────────
        price = _parse_price(car.get('price') or car.get('dollar_price'))
        if price:
            data['price'] = price   # "10,300"

        # ── Governorate → location (may be refined by description later) ──────
        gov = car.get('governorate') or {}
        loc = _clean(gov.get('name_ar') or gov.get('name', ''))
        if loc:
            data['location'] = loc

        # ── Category → brand (e.g. "ميني" / "Mini") ──────────────────────────
        cat = car.get('category') or {}
        brand_from_cat = _clean(cat.get('name_ar') or cat.get('name', ''))
        if brand_from_cat and brand_from_cat not in ('سيارات', 'Cars', 'Motors', 'محركات'):
            _set_field(data, 'brand', brand_from_cat)

        # ── Structured specs from featured_fields (mileage, year) ────────────
        _extract_from_featured_fields(data, car.get('featured_fields') or [])

        # ── Description: clean HTML if present, then parse inline specs ───────
        raw_desc = car.get('description') or car.get('description_ar') or ''
        desc = _clean_desc(raw_desc)   # strips <p> tags, &nbsp;, etc.
        if desc:
            data['description'] = desc
            # Parse bullet-point specs that aren't in featured_fields:
            # condition, transmission, fuel_type, color, model, engine, …
            _parse_description_specs(data, desc)

        # ── Seller ────────────────────────────────────────────────────────────
        customer = car.get('customer') or car.get('created_by') or {}
        seller_name = _clean(customer.get('name', ''))
        if seller_name:
            data['seller_name'] = seller_name

        # ── Contact (REAL seller phone from API — not site footer) ────────────
        phone    = _clean(str(car.get('phone') or ''))
        whatsapp = _clean(str(car.get('whatsapp') or ''))
        if phone and phone not in ('None', 'null', '0', ''):
            data['contact'] = phone
            if whatsapp and whatsapp != phone:
                wa_digits = re.sub(r'\D', '', whatsapp)
                ph_digits = re.sub(r'\D', '', phone)
                if wa_digits != ph_digits:
                    data['contact'] = f'{phone} / WA:{whatsapp}'
        elif whatsapp and whatsapp not in ('None', 'null', '0', ''):
            data['contact'] = f'WA:{whatsapp}'

        # ── Images ────────────────────────────────────────────────────────────
        gallery = car.get('gallery') or []
        image_urls = [
            img['src'] for img in gallery
            if isinstance(img, dict) and img.get('src')
        ]
        # Fallback: cover image only
        if not image_urls and car.get('cover_image'):
            image_urls = [car['cover_image']]
        data['_image_urls'] = image_urls

        return data

    # ── Per-car orchestration ─────────────────────────────────────────────────

    def _process_car(self, car: Dict) -> bool:
        # Enrich with ALL structured fields from the detail-by-slug endpoint.
        # The listing intercept only gives 2 featured_fields (mileage, year).
        # The detail endpoint returns the full "معلومات اضافية" set (color,
        # fuel_type, Transmission, Condition, etc.).  We prepend them so they
        # take priority over description-parsed values (first-value-wins).
        slug = car.get('slug', '')
        if slug:
            detail_fields = self._fetch_detail_fields(slug)
            if detail_fields:
                merged_ff = detail_fields + (car.get('featured_fields') or [])
                car = {**car, 'featured_fields': merged_ff}
                logger.debug(f'  detail fields fetched: {len(detail_fields)} entries')

        data = self._parse_car(car)
        car_id = data.get('id', '')

        logger.info(f'  → {data.get("car_url", car_id)}')

        image_urls: List[str] = data.pop('_image_urls', [])
        data['images_original_links'] = ', '.join(image_urls)

        image_links: List[str] = []
        folder_url = ''

        if image_urls:
            safe_id = re.sub(r'[^a-zA-Z0-9_-]', '_', car_id)
            try:
                folder_id, folder_url = self._create_subfolder(safe_id)
                for idx, img_url in enumerate(image_urls, 1):
                    ext   = (img_url.rsplit('.', 1)[-1].lower().split('?')[0] or 'jpg')[:5]
                    fname = f'{safe_id}_{idx:02d}.{ext}'
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

        # Normalize fields to Sayarti canonical values
        data = normalize_car(data)

        try:
            self._append_row(data)
            self.existing_ids.add(car_id)
            logger.info(f'  ✓  Row written: {data.get("ad_title", car_id)!r}  '
                        f'contact={data.get("contact", "—")}')
            return True
        except Exception as exc:
            logger.error(f'  Sheet write failed: {exc}')
            return False

    # ── Main loop ─────────────────────────────────────────────────────────────

    def run(self):
        progress = self.progress

        if self.full_mode:
            start_page = progress['last_page'] + 1
            if progress.get('full_scrape_done'):
                logger.info('Full scrape already complete. '
                            'Delete damazzle_progress.json to restart.')
                return
            logger.info(f'Full scrape mode — resuming from page {start_page}')
        else:
            start_page = 1
            logger.info('Incremental mode — starting from page 1')

        logger.info('=' * 62)
        logger.info(f'Damazzle scraper v2 started  {datetime.now().isoformat()}')
        if self.deadline:
            logger.info(f'Will stop at: {self.deadline.isoformat()}')
        logger.info(f'Existing sheet rows : {len(self.existing_ids)}')
        logger.info('=' * 62)

        self._init_browser()

        total_new        = 0
        full_page_streak = 0
        page             = start_page

        try:
            while True:

                if self._should_stop():
                    break

                page_url = (
                    LISTING_URL if page == 1
                    else f'{LISTING_URL}?page={page}'
                )
                logger.info(f'\n[Page {page}] {page_url}')

                try:
                    cars = self._scrape_listing_page(page_url)
                except Exception as exc:
                    logger.error(f'  Listing page error: {exc}')
                    break

                if not cars:
                    logger.info('  No cars intercepted — end of inventory or page error.')
                    if self.full_mode:
                        progress['full_scrape_done'] = True
                        _save_progress(progress)
                    break

                # ── 2026 cutoff ───────────────────────────────────────────────
                dated = [c for c in cars if _parse_iso_date(c.get('published_date', ''))]
                if dated and all(
                    _parse_iso_date(c['published_date']) < CUTOFF_DATE for c in dated
                ):
                    logger.info(f'  All listings are pre-{CUTOFF_DATE[:4]} — done.')
                    if self.full_mode:
                        progress['full_scrape_done'] = True
                        _save_progress(progress)
                    break

                # Drop pre-cutoff items on a mixed page
                cars = [
                    c for c in cars
                    if not _parse_iso_date(c.get('published_date', ''))
                    or _parse_iso_date(c['published_date']) >= CUTOFF_DATE
                ]

                # ── Filter to new listings only ───────────────────────────────
                new_cars = [
                    c for c in cars
                    if f'damazzle_{c.get("id")}' not in self.existing_ids
                ]
                logger.info(f'  {len(cars)} total (2026+) | {len(new_cars)} new')

                if not new_cars:
                    if not self.full_mode:
                        full_page_streak += 1
                        logger.info(
                            f'  All existing. Streak: {full_page_streak}'
                            f'/{STOP_AFTER_FULL_PAGES}'
                        )
                        if full_page_streak >= STOP_AFTER_FULL_PAGES:
                            logger.info('  Caught up — stopping.')
                            break
                    else:
                        logger.info('  All existing — continuing (full mode).')
                        progress['last_page'] = page
                        _save_progress(progress)
                    time.sleep(REQUEST_DELAY)
                    page += 1
                    continue

                full_page_streak = 0

                for car in new_cars:
                    if self._should_stop():
                        if self.full_mode:
                            progress['last_page'] = page - 1
                            _save_progress(progress)
                        break
                    ok = self._process_car(car)
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

        finally:
            self._close_browser()

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
        description='Damazzle.com standalone scraper v2',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
examples:
  python damazzle_standalone.py --hours 1        # run for 1 hour (recommended first test)
  python damazzle_standalone.py --full --hours 4 # full scrape, 4-hour session
  python damazzle_standalone.py                  # incremental, no time limit
        """,
    )
    parser.add_argument('--hours', type=float, metavar='N',
                        help='Stop gracefully after N hours')
    parser.add_argument('--full', action='store_true',
                        help='Full-scrape mode: resume from the last saved page')
    parser.add_argument('--repair-images', action='store_true',
                        help=(
                            'Repair mode: re-upload Drive images for existing rows '
                            'whose "images" column is empty. Uses stored '
                            'images_original_links (no browser needed); falls back '
                            'to the detail API via car_url slug. Does not scrape new listings.'
                        ))
    parser.add_argument('--repair-data', action='store_true',
                        help='Normalize all existing sheet rows to Sayarti canonical values.')
    args = parser.parse_args()

    if sys.stdout.encoding != 'utf-8':
        sys.stdout.reconfigure(encoding='utf-8')

    if not os.path.exists(OAUTH_CLIENT_FILE):
        print(f'ERROR: OAuth2 client secret not found:\n  {OAUTH_CLIENT_FILE}')
        sys.exit(1)

    scraper = DamazzleScraper(full_mode=args.full, max_hours=args.hours)
    if args.repair_images:
        scraper._repair_images()
    elif args.repair_data:
        scraper.repair_data()
    else:
        scraper.run()
