#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SyriaCars.net Standalone Scraper  (v2)
=======================================
Scrapes https://syriacars.net/inventory/, visits every new car's detail page,
uploads images to a Google Drive folder (via OAuth2 — no storage-quota error),
and appends rows to Google Sheets.

KEY BEHAVIOURS
--------------
• Auth          : OAuth2 user credentials. First run opens a browser for consent;
                  subsequent runs reuse the saved token in oauth_token.json.
                  Images are owned by YOU → no storageQuotaExceeded errors.
• Deduplication : On startup reads the 'id' column from the sheet.
                  Any syriacars_{id} that already exists is skipped.
• Progress      : In --full mode a syriacars_progress.json file tracks the last
                  completed page so you can resume across sessions.
• Pause/Resume  : --hours N  stops gracefully after N hours and saves progress.
                  Ctrl+C also saves progress before exiting.
• N/A values    : Written to the sheet as-is ("N/A"), not converted to empty.
• Mileage       : "كم" / "km" suffixes and thousands-separators are stripped.
• Chapter specs : All h2 chapter sections (مواصفات السيارة, etc.) are parsed
                  in addition to the main spec list.

COLUMNS (in sheet order — syriacars-specific schema)
-----------------------------------------------------
id | source | car_url | make | model | year | body_type |
exterior_color | interior_color | fuel_type | engine_size | transmission |
condition | city | mileage | price | date_added | views |
phone | listing_id | seller_name | seller_type | seller_notes |
images_drive_links | drive_system | image_clean_link

SETUP
-----
pip install requests beautifulsoup4 gspread google-auth google-auth-oauthlib
pip install google-api-python-client

OAuth2 client secret:
  client_secret_798447276011-9bfpmjkfo8et8c2r4omri13kbh7h5202.apps.googleusercontent.com.json
  (must sit next to this script)

USAGE
-----
  python syriacars_standalone.py                # incremental (stops when caught up)
  python syriacars_standalone.py --hours 2      # run for 2 hours then stop
  python syriacars_standalone.py --full         # full scrape, resume from last page
  python syriacars_standalone.py --full --hours 4
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
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import requests
from bs4 import BeautifulSoup
from PIL import Image

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
        logging.FileHandler('syriacars_scraper.log', encoding='utf-8'),
    ],
)
logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────────────

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# OAuth2 client secret (created by user; must be next to this script)
OAUTH_CLIENT_FILE = os.path.join(
    SCRIPT_DIR,
    'client_secret_798447276011-9bfpmjkfo8et8c2r4omri13kbh7h5202.apps.googleusercontent.com.json',
)
# Saved token — created automatically after first consent; reused on subsequent runs
OAUTH_TOKEN_FILE = os.path.join(SCRIPT_DIR, 'oauth_token.json')

# Pause/resume progress (used in --full mode)
PROGRESS_FILE = os.path.join(SCRIPT_DIR, 'syriacars_progress.json')

# Google Sheets — target spreadsheet (SyriaCarsCleanImages)
SHEET_ID = '189XTSyzzCaltqY24N1npQ6C-JPhLVxfDBvf3BbPu_LM'

# Google Drive — root folder for car images
DRIVE_FOLDER_ID = '1m3Ne66uSpwWLFoQHnGgbxBe4DmUE4V2t'

# Site
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

# OAuth2 scopes (Sheets + Drive)
SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive',
]

# Dewatermark.ai API
DEWATERMARK_URL = 'https://platform.dewatermark.ai/api/object_removal/v2/erase_watermark'

# Dealer list scraper
DEALERS_LIST_URL    = f'{BASE_URL}/dealers-list/'
DEALERS_SHEET_ID_FILE = Path(__file__).parent / 'syriacars_dealers_sheet_id.txt'
DEALERS_COLUMNS: List[str] = [
    'dealer_name', 'username', 'profile_url', 'phone', 'city', 'car_count', 'scraped_at',
]

# Seconds between HTTP requests (polite crawling)
REQUEST_DELAY = 0.6

# Stop paginating (incremental mode) after this many consecutive all-existing pages
STOP_AFTER_FULL_PAGES = 2

# ── Arabic label → sheet column mapping ───────────────────────────────────────

SPEC_MAP: Dict[str, str] = {
    # ─ Main spec list (ul.single-listing-data) ─
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
    # ─ Extra / accordion / chapter sections ─
    'نظام الدفع':      'drive_system',
    'نوع الدفع':       'drive_system',
    'عدد الأبواب':     'doors',
    'عدد الابواب':     'doors',
    'الأبواب':         'doors',
    'السلندرات':       'cylinders',
    'عدد السلندرات':   'cylinders',
    'رقم الهيكل':      'chassis_number',
    'رقم الشاصي':      'chassis_number',
    # ─ Ignored (prefixed _) ─
    'History':         '_history',
    'الوارد':          '_origin',
    'الاستيراد':       '_origin',
    'الموديل الفرعي':  '_submodel',
}

# ── Sheet columns (order = column order in spreadsheet) ───────────────────────

COLUMNS: List[str] = [
    'id', 'source', 'car_url',
    'make', 'model', 'year', 'body_type',
    'exterior_color', 'interior_color',
    'fuel_type', 'engine_size', 'transmission',
    'condition',
    'city', 'mileage', 'price',
    'date_added', 'views',
    'phone', 'listing_id',
    'seller_name', 'seller_type',
    'seller_notes',
    'images_drive_links',
    'drive_system',
    'image_clean_link',
]

# ── OAuth2 helpers ────────────────────────────────────────────────────────────


def _get_oauth_credentials():
    """
    Load cached OAuth2 credentials from oauth_token.json, refreshing if expired.
    If no token exists (first run) launches a browser consent flow to obtain one.
    """
    creds = None

    if os.path.exists(OAUTH_TOKEN_FILE):
        try:
            with open(OAUTH_TOKEN_FILE, encoding='utf-8') as fh:
                token_data = json.load(fh)
            creds = google_creds_module.Credentials.from_authorized_user_info(
                token_data, SCOPES
            )
        except Exception as exc:
            logger.warning(f'Could not load cached token: {exc}')
            creds = None

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            logger.info('Refreshing expired OAuth2 token …')
            creds.refresh(Request())
        else:
            logger.info(
                'No valid token found — launching browser consent flow …\n'
                '  (A browser window will open.  Sign in with your Google account.)'
            )
            flow = InstalledAppFlow.from_client_secrets_file(OAUTH_CLIENT_FILE, SCOPES)
            creds = flow.run_local_server(port=0)

        # Persist token for future runs
        with open(OAUTH_TOKEN_FILE, 'w', encoding='utf-8') as fh:
            fh.write(creds.to_json())
        logger.info(f'Token saved → {OAUTH_TOKEN_FILE}')

    return creds


# ── Progress helpers ──────────────────────────────────────────────────────────


def _load_progress() -> Dict:
    """Load the progress JSON file, or return defaults."""
    if os.path.exists(PROGRESS_FILE):
        try:
            with open(PROGRESS_FILE, encoding='utf-8') as fh:
                return json.load(fh)
        except Exception as exc:
            logger.warning(f'Could not read progress file: {exc}')
    return {'last_page': 0, 'total_scraped': 0, 'full_scrape_done': False}


def _save_progress(progress: Dict):
    """Atomically write the progress dict to JSON."""
    tmp = PROGRESS_FILE + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as fh:
        json.dump(progress, fh, indent=2, ensure_ascii=False)
    os.replace(tmp, PROGRESS_FILE)
    logger.info(
        f'Progress saved → page {progress["last_page"]}, '
        f'{progress["total_scraped"]} total scraped.'
    )


# ── Pure helper functions ─────────────────────────────────────────────────────


def _clean(text: Optional[str]) -> str:
    """
    Strip and collapse whitespace.
    'N/A' is preserved as-is (written to sheet as "N/A").
    Only genuine empty/dash-only values become empty strings.
    """
    if not text:
        return ''
    t = ' '.join(text.split())
    # Collapse pure-dash placeholders to empty; keep everything else (including N/A)
    return '' if t in ('-', '—', '–', '') else t


def _clean_mileage(v: str) -> str:
    """
    Remove Arabic/Latin 'km' suffix and thousands-separators from a mileage string.
    Handles 'X ألف' (= X thousand) before clean_number strips 'ألف'.
    '150,000 كم' → '150000'
    '75٬000 km'  → '75000'
    '210 ألف كم' → '210000'
    '245 ألف'    → '245000'
    """
    v = re.sub(r'[,،٬]', '', v)
    v = re.sub(r'\s*(كم|km)\s*$', '', v, flags=re.I).strip()
    m = re.match(r'^(\d+)\s*ألف\s*$', v)
    if m:
        return str(int(m.group(1)) * 1000)
    return v


def _parse_price(text: str) -> Optional[str]:
    """Extract a USD price number: '$27,000' → '27000'."""
    if not text:
        return None
    digits = re.sub(r'[^\d.]', '', text.replace(',', ''))
    try:
        v = float(digits)
        return str(int(v)) if v == int(v) else str(v)
    except (ValueError, TypeError):
        return None


_HAS_ARABIC = re.compile(r'[؀-ۿ]')


_ALL_MODELS_SUFFIX = re.compile(r'\s*كل الفئات\s*$')
_COMPOUND_SEP      = re.compile(r'\s*[-–]\s*')


def _strip_foreign(text: str) -> str:
    """
    Syriacars stores many values as 'English - Arabic', 'Arabic - English',
    or 'Arabic-English' (no spaces around dash). Return just the Arabic portion
    when both are present; otherwise return as-is.
    Also strips 'كل الفئات' (= 'all categories') which appears when the site
    has no specific model selected.
    Examples:
        'BMW - بي ام دابليو'  →  'بي ام دابليو'
        'Rogue - روج'         →  'روج'
        'روج-Rogue'           →  'روج'
        'G class كل الفئات'   →  'G class'
        'كل الفئات'           →  '' (empty — no real value)
        'G class'             →  'G class'   (no Arabic → keep)
    """
    if not text:
        return text
    # Strip 'كل الفئات' suffix (site artifact meaning "all models")
    text = _ALL_MODELS_SUFFIX.sub('', text).strip()
    if not text:
        return ''
    # Split on ' - ' or '-' between Arabic and non-Arabic parts
    parts = [p.strip() for p in _COMPOUND_SEP.split(text) if p.strip()]
    if len(parts) < 2:
        return text
    arabic_parts = [p for p in parts if _HAS_ARABIC.search(p)]
    return arabic_parts[0] if arabic_parts else text


def _listing_type(title: str) -> str:
    """Return 'للإيجار' if rental keywords appear, otherwise 'للبيع'."""
    if any(k in title for k in ('للإيجار', 'للايجار', 'للتأجير', 'إيجار')):
        return 'للإيجار'
    return 'للبيع'


def _condition(title: str) -> str:
    """Derive condition (مستعمل/جديد) from the Arabic title."""
    if 'مستعمل' in title or 'مستعملة' in title:
        return 'مستعمل'
    if 'جديد' in title or 'جديدة' in title:
        return 'جديد'
    return ''


def _base_image_url(src: str) -> str:
    """
    Convert a resized thumbnail URL to the full-size original.
    Removes ?v=... cache-busters and -WxH resize suffixes.
    """
    src = re.sub(r'\?.*$', '', src)                       # strip query string
    src = re.sub(r'-\d+x\d+(?=\.[a-zA-Z]+$)', '', src)   # strip -768x1024
    return src


AR_MONTHS: Dict[str, int] = {
    # Arabic month names
    'يناير': 1, 'فبراير': 2, 'مارس': 3, 'أبريل': 4,
    'مايو': 5,  'يونيو': 6,  'يوليو': 7, 'أغسطس': 8,
    'سبتمبر': 9, 'أكتوبر': 10, 'نوفمبر': 11, 'ديسمبر': 12,
    # English (fallback)
    'January': 1, 'February': 2, 'March': 3,     'April': 4,
    'May': 5,     'June': 6,     'July': 7,       'August': 8,
    'September': 9, 'October': 10, 'November': 11, 'December': 12,
}


def _parse_listing_date(text: str) -> Optional[str]:
    """Parse 'مايو 15، 2026' or 'April 15, 2026' → 'YYYY-MM-DD'. Returns None if not found."""
    if not text:
        return None
    for month_name, month_num in AR_MONTHS.items():
        if month_name in text:
            m = re.search(r'(\d{1,2})[,،]?\s*(\d{4})', text)
            if m:
                day, year = int(m.group(1)), int(m.group(2))
                return f'{year}-{month_num:02d}-{day:02d}'
    return None


def _apply_spec(data: Dict, k: str, v: str) -> None:
    """
    Look up k in SPEC_MAP and store v into data if the field isn't filled yet.
    Applies mileage post-processing automatically.
    Mutates data in place; ignores unknown / ignored (_-prefixed) keys.
    """
    field = SPEC_MAP.get(k)
    if not field or field.startswith('_'):
        return
    if field in data:
        return          # first value wins
    if field == 'mileage':
        v = _clean_mileage(v)
    if v:
        data[field] = v


# ── Main scraper class ────────────────────────────────────────────────────────


class SyriaCarsScraper:
    """
    Scrapes syriacars.net inventory, uploads images to Google Drive (OAuth2),
    and writes structured rows to Google Sheets.
    """

    def __init__(self, full_mode: bool = False, max_hours: Optional[float] = None,
                 max_pages: Optional[int] = None,
                 start_date: Optional[str] = None, end_date: Optional[str] = None,
                 dewatermark_key: Optional[str] = None):
        self.full_mode       = full_mode
        self.max_pages       = max_pages        # stop after this many pages
        self.max_cars        = None             # set via run() kwarg or --max-cars
        self.start_date      = start_date       # YYYY-MM-DD — skip listings older than this
        self.end_date        = end_date         # YYYY-MM-DD — skip listings newer than this
        self.dewatermark_key = dewatermark_key  # dewatermark.ai API key
        self.deadline: Optional[datetime] = (
            datetime.now() + timedelta(hours=max_hours) if max_hours else None
        )
        self._stop_requested = False

        # Graceful Ctrl+C / SIGTERM handling
        signal.signal(signal.SIGINT,  self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)

        logger.info('Authenticating with Google APIs (OAuth2) …')
        creds = _get_oauth_credentials()

        # gspread accepts any google.auth.credentials.Credentials subclass
        self.gc    = gspread.authorize(creds)
        self.drive = build('drive', 'v3', credentials=creds)

        self.sheet = self.gc.open_by_key(SHEET_ID).sheet1
        self._ensure_headers()
        self.existing_ids: Set[str] = self._load_existing_ids()
        self.progress: Dict         = _load_progress()

        logger.info(f'Sheet has {len(self.existing_ids)} existing IDs.')
        logger.info(
            f'Progress file → last_page={self.progress["last_page"]}, '
            f'total_scraped={self.progress["total_scraped"]}, '
            f'full_scrape_done={self.progress["full_scrape_done"]}'
        )

    # ── Signal handling ───────────────────────────────────────────────────────

    def _handle_signal(self, signum, frame):
        logger.warning('\nInterrupt/termination signal received — '
                       'will finish the current car then stop …')
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
        """Ensure row 1 matches COLUMNS exactly; insert missing columns if needed."""
        first = self.sheet.row_values(1)
        if first == COLUMNS:
            return  # already correct
        if not first or first[0] != COLUMNS[0]:
            # Completely wrong / empty — clear and rewrite
            logger.info('Writing fresh header row …')
            self.sheet.clear()
            self.sheet.insert_row(COLUMNS, 1)
            return
        # Headers exist but column list changed (e.g. date_added was added).
        # Insert missing columns at their correct positions to preserve existing data.
        logger.info(f'Header mismatch — current: {first[:5]}…  expected: {COLUMNS[:5]}…')
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
                # Refresh local copy of headers after the insertion
                first = self.sheet.row_values(1)
        logger.info('Headers updated.')

    def _load_existing_ids(self) -> Set[str]:
        """Read the 'id' column (skip header) to build the dedup set."""
        col_idx = COLUMNS.index('id') + 1   # gspread is 1-based
        vals = self.sheet.col_values(col_idx)
        return set(vals[1:])

    def _append_row(self, data: Dict):
        """Serialise *data* in COLUMNS order and append it to the sheet."""
        row = []
        for col in COLUMNS:
            v = data.get(col, '')
            row.append('' if v is None else str(v))
        self.sheet.append_row(row, value_input_option='RAW')

    # ── Google Drive helpers ──────────────────────────────────────────────────

    def _make_public(self, file_id: str):
        """Grant anyone-reader permission so links work without login."""
        self.drive.permissions().create(
            fileId=file_id,
            body={'type': 'anyone', 'role': 'reader'},
        ).execute()

    def _create_subfolder(self, name: str) -> Tuple[str, str]:
        """
        Create a sub-folder inside DRIVE_FOLDER_ID.
        Returns (folder_id, webViewLink).
        """
        meta = {
            'name': name,
            'mimeType': 'application/vnd.google-apps.folder',
            'parents': [DRIVE_FOLDER_ID],
        }
        f = self.drive.files().create(body=meta, fields='id,webViewLink').execute()
        self._make_public(f['id'])
        return f['id'], f.get('webViewLink', '')

    def _upload_bytes(
        self, data: bytes, mime: str, folder_id: str, filename: str
    ) -> Optional[str]:
        """Upload raw bytes to *folder_id*. Returns webViewLink or None."""
        try:
            media = MediaIoBaseUpload(io.BytesIO(data), mimetype=mime)
            f = self.drive.files().create(
                body={'name': filename, 'parents': [folder_id]},
                media_body=media,
                fields='id,webViewLink',
            ).execute()
            self._make_public(f['id'])
            return f.get('webViewLink', '')
        except Exception as exc:
            logger.warning(f'    Drive upload failed ({filename}): {exc}')
            return None

    def _upload_image(
        self, img_url: str, folder_id: str, filename: str
    ) -> Optional[str]:
        """Download *img_url* and upload to Drive. Returns webViewLink or None."""
        try:
            r = requests.get(img_url, headers=HEADERS, timeout=30)
            r.raise_for_status()
            mime = r.headers.get('Content-Type', 'image/jpeg').split(';')[0]
            return self._upload_bytes(r.content, mime, folder_id, filename)
        except Exception as exc:
            logger.warning(f'    Image download failed ({img_url}): {exc}')
            return None

    def _remove_watermark(self, image_bytes: bytes) -> Optional[bytes]:
        """
        Send *image_bytes* to dewatermark.ai and return clean image bytes.
        Returns None on failure.
        """
        try:
            resp = requests.post(
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

    # ── HTTP fetch ────────────────────────────────────────────────────────────

    def _fetch(self, url: str) -> BeautifulSoup:
        r = requests.get(url, headers=HEADERS, timeout=30)
        r.raise_for_status()
        return BeautifulSoup(r.text, 'html.parser')

    # ── Listing page parsing ──────────────────────────────────────────────────

    def _scrape_listing_page(self, url: str) -> List[Dict]:
        """
        Fetch one inventory page and return a list of
        {'listing_id': str, 'car_url': str, 'date_added': str} dicts.
        """
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

            # ── Extract listing date ───────────────────────────────────
            date_added = ''
            time_el = div.select_one('time[datetime]')
            if time_el:
                dt_attr = time_el.get('datetime', '')
                m = re.match(r'(\d{4}-\d{2}-\d{2})', dt_attr)
                if m:
                    date_added = m.group(1)           # already ISO
                else:
                    date_added = _parse_listing_date(time_el.get_text()) or ''
            if not date_added:
                # Fallback: scan the whole card text for an Arabic month
                date_added = _parse_listing_date(div.get_text()) or ''

            items.append({'listing_id': lid, 'car_url': href, 'date_added': date_added})
        return items

    # ── Detail page parsing ───────────────────────────────────────────────────

    def _scrape_detail(self, car_url: str, listing_id: str) -> Dict:
        """
        Fetch and fully parse a car detail page.
        Returns a structured dict.  Image URLs are in '_image_urls' (private key,
        popped before writing to sheet).
        """
        soup = self._fetch(car_url)

        data: Dict = {
            'scraped_at': datetime.now().isoformat(),
            'source':     SOURCE,
            'id':         f'syriacars_{listing_id}',
            'category':   'cars',
            'ad_title':   '',
            'car_url':    car_url,
        }

        # ── Title ─────────────────────────────────────────────────────────────
        h1 = soup.select_one('h1.single-listing-title')
        title = _clean(h1.get_text()) if h1 else ''
        data['ad_title'] = title

        # ── Listing type + condition (derived from Arabic title) ───────────────
        data['listing_type'] = _listing_type(title)
        cond = _condition(title)
        if cond:
            data['condition'] = cond

        # ── Price ─────────────────────────────────────────────────────────────
        pv = soup.select_one('.single-listing-price-value')
        if pv:
            price = _parse_price(pv.get_text())
            if price:
                data['price'] = price

        # ── PASS 1 : Main spec list (ul.single-listing-data) ──────────────────
        # Selects ALL <ul class="single-listing-data"> on the page, which includes
        # every chapter section (مواصفات السيارة, مواصفات إضافية, etc.).
        for li in soup.select('ul.single-listing-data li.single-listing-data-item'):
            lbl = li.select_one('.single-listing-data-item-label')
            val = li.select_one('.single-listing-data-item-value')
            if not (lbl and val):
                continue
            k = _clean(lbl.get_text())
            v = _clean(val.get_text())
            if k and v:
                _apply_spec(data, k, v)

        # ── PASS 2 : Chapter sections (belt-and-suspenders for مواصفات السيارة)
        # Walk each h2/h3 chapter heading and parse any sibling spec lists that
        # may use slightly different class names than the main ul above.
        for chapter_h in soup.find_all(class_='single-listing-chapter-title'):
            sibling = chapter_h.find_next_sibling()
            while sibling:
                # Stop at the next chapter heading
                if (hasattr(sibling, 'get')
                        and 'single-listing-chapter-title' in sibling.get('class', [])):
                    break
                # Standard pattern inside the sibling container
                for li in sibling.select('li.single-listing-data-item'):
                    lbl = li.select_one('.single-listing-data-item-label')
                    val = li.select_one('.single-listing-data-item-value')
                    if lbl and val:
                        k = _clean(lbl.get_text())
                        v = _clean(val.get_text())
                        if k and v:
                            _apply_spec(data, k, v)
                # Also handle simple <li> pairs without the sub-classes
                plain_lis = sibling.find_all('li', recursive=False)
                if plain_lis:
                    mid = len(plain_lis) // 2
                    if mid and len(plain_lis) == mid * 2:
                        # Assume first half = labels, second half = values
                        for i in range(mid):
                            k = _clean(plain_lis[i].get_text())
                            v = _clean(plain_lis[i + mid].get_text())
                            if k and v:
                                _apply_spec(data, k, v)
                sibling = sibling.find_next_sibling()

        # ── PASS 3 : Accordion / paired-UL sections ───────────────────────────
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

        # ── Description ───────────────────────────────────────────────────────
        desc_selectors = [
            '.stm-listing-description',
            '.single-listing-description',
            '[class*="description-content"]',
            '.tab-content-item .stm-listing-description',
        ]
        for sel in desc_selectors:
            el = soup.select_one(sel)
            if el:
                desc = _clean(el.get_text(separator=' '))
                if desc:
                    data['description'] = desc
                    break

        # Fallback: paragraph following an "الوصف" chapter heading
        if not data.get('description'):
            for h2 in soup.find_all(['h2', 'h3'], class_='single-listing-chapter-title'):
                if 'الوصف' in h2.get_text() or 'Description' in h2.get_text():
                    nxt = h2.find_next_sibling()
                    if nxt:
                        desc = _clean(nxt.get_text(separator=' '))
                        if desc:
                            data['description_original'] = desc
                    break

        # ── Seller notes (ملاحظات البائع) ────────────────────────────────────
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

        # ── Seller name + type ────────────────────────────────────────────────
        # Business listings wrap the seller name in a /dealer/ profile link.
        dealer_el = soup.select_one('.single-listing-dealer-name')
        if dealer_el:
            data['seller_name'] = _clean(dealer_el.get_text())
            dealer_a = (dealer_el if dealer_el.name == 'a'
                        else dealer_el.find('a', href=re.compile(r'/dealer/')))
            data['seller_type'] = 'dealer' if dealer_a else 'private'
        else:
            data['seller_type'] = 'private'

        # ── Contact ───────────────────────────────────────────────────────────
        # The Motors theme embeds the full phone number directly in the static HTML
        # ("اظهر الرقم" is a pure CSS toggle — no AJAX needed).
        phone_span = soup.select_one('span.single-listing-phone-number')
        phone = _clean(phone_span.get_text()) if phone_span else ''

        if not phone:
            tel_a = soup.select_one('a.single-listing-phone-button[href^="tel:"]')
            if tel_a:
                phone = tel_a['href'].replace('tel:', '').strip()

        if phone:
            data['phone'] = phone

        # Append WhatsApp if it differs from the phone number
        wa_a = soup.select_one('a.single-listing-whatsapp-button[href*="wa.me"]')
        if wa_a:
            wa_m = re.search(r'wa\.me/(\+?[\d]+)', wa_a['href'])
            if wa_m:
                wa_num = wa_m.group(1)
                existing_phone = data.get('phone', '')
                if wa_num.lstrip('+') not in existing_phone.replace('+', '').replace(' ', ''):
                    data['phone'] = (existing_phone + ' / WA:' + wa_num).strip(' /')

        # ── Date added (from detail page) ─────────────────────────────────────
        # Primary: WordPress / Open Graph published-time meta tag
        meta_date = soup.find('meta', property='article:published_time')
        if meta_date:
            m_dt = re.match(r'(\d{4}-\d{2}-\d{2})', meta_date.get('content', ''))
            if m_dt:
                data['date_added'] = m_dt.group(1)
        # Fallback 1: any <time datetime="YYYY-MM-DD…"> on the page
        if not data.get('date_added'):
            for t_el in soup.find_all('time', attrs={'datetime': True}):
                m_dt = re.match(r'(\d{4}-\d{2}-\d{2})', t_el.get('datetime', ''))
                if m_dt:
                    data['date_added'] = m_dt.group(1)
                    break
        # Fallback 2: JSON-LD structured data datePublished
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

        # ── Images ────────────────────────────────────────────────────────────
        images: List[str] = []
        seen:   Set[str]  = set()

        for img in soup.select('img.single-listing-gallery-image'):
            src = img.get('data-lg-src') or img.get('src', '')
            src = _base_image_url(src)
            if src.startswith('https://syriacars.net/wp-content/uploads/') and src not in seen:
                seen.add(src)
                images.append(src)

        # Fallback: any car-upload image referenced on the page
        if not images:
            for img in soup.find_all('img'):
                src = _base_image_url(img.get('src', ''))
                if ('syriacars.net/wp-content/uploads/' in src
                        and 'car-image' in src
                        and src not in seen):
                    seen.add(src)
                    images.append(src)

        data['_image_urls'] = images   # popped before sheet write

        return data

    # ── Per-car orchestration ─────────────────────────────────────────────────

    # ── Sheet sort helper ─────────────────────────────────────────────────────

    def _sort_sheet_by_date(self):
        """Sort all data rows by date_added descending (newest first)."""
        try:
            date_col_idx = COLUMNS.index('date_added')
            self.sheet.spreadsheet.batch_update({
                'requests': [{
                    'sortRange': {
                        'range': {
                            'sheetId': self.sheet.id,
                            'startRowIndex': 1,          # skip header
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

    # ── Dealers sheet helpers ─────────────────────────────────────────────────

    def _get_or_create_dealers_sheet(self):
        """Open the dealers sheet by saved ID, or create a new spreadsheet."""
        if DEALERS_SHEET_ID_FILE.exists():
            sheet_id = DEALERS_SHEET_ID_FILE.read_text().strip()
            try:
                ws = self.gc.open_by_key(sheet_id).sheet1
                logger.info(f'Opened existing dealers sheet: {sheet_id}')
                return ws
            except Exception as exc:
                logger.warning(f'Saved dealers sheet ID not usable ({exc}), creating new …')

        sh = self.gc.create('SyriaCarsDealers')
        sh.share('', perm_type='anyone', role='reader')
        ws = sh.sheet1
        ws.update_title('Dealers')
        ws.append_row(DEALERS_COLUMNS)
        DEALERS_SHEET_ID_FILE.write_text(sh.id)
        logger.info(f'Created dealers sheet: {sh.id}  →  {sh.url}')
        return ws

    def _phones_from_cars_sheet(self) -> Dict[str, str]:
        """
        Read the cars sheet and return {seller_name_lower: phone} for every
        row where seller_type == 'dealer'. Phones collected during normal
        scraping are reused here so --scrape-dealers never needs extra HTTP calls.
        """
        phones: Dict[str, str] = {}
        try:
            all_vals = self.sheet.get_all_values()
            if len(all_vals) < 2:
                return phones
            header = all_vals[0]
            name_col  = header.index('seller_name')  if 'seller_name'  in header else -1
            phone_col = header.index('phone')         if 'phone'         in header else -1
            type_col  = header.index('seller_type')  if 'seller_type'  in header else -1
            if -1 in (name_col, phone_col, type_col):
                return phones
            for row in all_vals[1:]:
                stype = row[type_col] if type_col < len(row) else ''
                name  = row[name_col]  if name_col  < len(row) else ''
                phone = row[phone_col] if phone_col < len(row) else ''
                if stype == 'dealer' and name and phone:
                    phones[name.lower().strip()] = phone
        except Exception as exc:
            logger.warning(f'Could not read dealer phones from cars sheet: {exc}')
        return phones

    def scrape_dealers(self):
        """
        Scrape syriacars.net/dealers-list/ (all pages) to get dealer names and
        car counts. Phones come from the cars sheet (already collected during
        normal scraping — no extra HTTP requests needed). Write results to the
        SyriaCarsDealers Google Sheet (auto-created on first run).
        """
        logger.info('=== Dealer scraper ===')
        dealers: Dict[str, Dict] = {}   # username → info dict

        # ── Phase 1: paginate dealer list ────────────────────────────────────
        page = 1
        while True:
            url = (DEALERS_LIST_URL if page == 1
                   else f'{DEALERS_LIST_URL}page/{page}/')
            logger.info(f'  [page {page}] {url}')
            try:
                soup = self._fetch(url)
            except requests.HTTPError as exc:
                if exc.response.status_code == 404:
                    break
                logger.error(f'  HTTP error: {exc}')
                break
            except Exception as exc:
                logger.error(f'  Fetch error: {exc}')
                break

            # Each dealer has 3 flat <a href="/dealer/username/"> tags:
            # image link, name text link, car-count text link — no card wrapper class.
            all_dealer_links = soup.select('a[href*="/dealer/"]')
            if not all_dealer_links:
                logger.info('  No /dealer/ links found — stopping.')
                break

            page_usernames: List[str] = []
            for a_tag in all_dealer_links:
                href = a_tag.get('href', '').rstrip('/')
                if not href:
                    continue
                if href.startswith('/'):
                    href = BASE_URL + href
                username = href.split('/dealer/')[-1].rstrip('/')
                if username and username not in dealers and username not in page_usernames:
                    page_usernames.append(username)

            before = len(dealers)
            for username in page_usernames:
                name      = ''
                car_count = ''
                for a_tag in soup.select(f'a[href*="/dealer/{username}/"]'):
                    txt = _clean(a_tag.get_text())
                    if not txt:
                        continue
                    if 'سيارة' in txt:
                        m = re.search(r'\d+', txt)
                        if m:
                            car_count = m.group(0)
                    elif not name:
                        name = txt

                dealers[username] = {
                    'dealer_name': name or username,
                    'username':    username,
                    'profile_url': f'{BASE_URL}/dealer/{username}/',
                    'phone':       '',
                    'city':        '',
                    'car_count':   car_count,
                    'scraped_at':  datetime.now().date().isoformat(),
                }

            added = len(dealers) - before
            logger.info(f'  +{added} dealers  (total: {len(dealers)})')
            if added == 0:
                break
            page += 1
            time.sleep(REQUEST_DELAY)

        logger.info(f'Dealer list scraped: {len(dealers)} dealers.')
        if not dealers:
            logger.warning('No dealers found — aborting.')
            return

        # ── Phase 2: fill phones from cars sheet (zero extra HTTP requests) ──
        phones = self._phones_from_cars_sheet()
        matched = 0
        for d in dealers.values():
            phone = phones.get(d['dealer_name'].lower().strip(), '')
            if phone:
                d['phone'] = phone
                matched += 1
        logger.info(f'Phone lookup from cars sheet: {matched}/{len(dealers)} matched.')

        # ── Phase 3: write to dealers sheet ──────────────────────────────────
        dealers_ws = self._get_or_create_dealers_sheet()

        all_vals = dealers_ws.get_all_values()
        if len(all_vals) > 1:
            dealers_ws.delete_rows(2, len(all_vals))

        rows = [[d.get(col, '') for col in DEALERS_COLUMNS]
                for d in dealers.values()]
        if rows:
            dealers_ws.append_rows(rows, value_input_option='RAW')

        logger.info(f'Dealers sheet updated — {len(rows)} rows written.')

        local_json = Path(__file__).parent / 'syriacars_dealers.json'
        with open(local_json, 'w', encoding='utf-8') as f:
            json.dump(list(dealers.values()), f, ensure_ascii=False, indent=2)
        logger.info(f'Saved {local_json}')

    # ── Repair-data mode ─────────────────────────────────────────────────────

    def repair_data(self):
        """Normalize all existing sheet rows using Sayarti canonical values."""
        logger.info('=== Repair-data mode (normalize all fields) ===')
        NORMALIZABLE = [
            'price', 'engine_size', 'mileage', 'year',
            'fuel_type', 'transmission',
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
            # Snapshot originals before in-place strip so comparison uses sheet values
            originals = {col: raw.get(col, '') for col in NORMALIZABLE}
            # Apply syriacars-specific preprocessing before normalization
            for _f in ('make', 'model', 'body_type', 'fuel_type', 'transmission',
                       'condition', 'city', 'origin', 'exterior_color', 'interior_color'):
                if raw.get(_f):
                    raw[_f] = _strip_foreign(raw[_f])
            normalized = normalize_car(raw)
            updates = {}
            for col in NORMALIZABLE:
                old = originals.get(col, '')
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
        Uses the saved 'url' column when available; otherwise tries the WordPress
        ?p=<id> redirect to resolve the canonical car URL.
        """
        logger.info('=== Repair-images mode ===')

        all_values = self.sheet.get_all_values()
        if not all_values:
            logger.info('Sheet is empty — nothing to repair.')
            return
        header = all_values[0]

        try:
            id_col     = header.index('id')
            images_col = header.index('images_drive_links')
        except ValueError as exc:
            logger.error(f'Required column not found: {exc}')
            return
        url_col = header.index('car_url') if 'car_url' in header else -1

        # Collect rows that need repair
        to_repair = []
        for row_num, row in enumerate(all_values[1:], start=2):
            def _cell(idx):
                return row[idx].strip() if idx < len(row) else ''
            row_id     = _cell(id_col)
            row_images = _cell(images_col)
            if row_id and not row_images:
                to_repair.append({
                    'row_num': row_num,
                    'id':      row_id,
                    'url':     _cell(url_col) if url_col >= 0 else '',
                })

        logger.info(f'Rows needing image repair: {len(to_repair)}')
        if not to_repair:
            logger.info('Nothing to do.')
            return

        repaired = 0
        for item in to_repair:
            if self._should_stop():
                break

            row_id    = item['id']
            row_num   = item['row_num']
            car_url   = item['url']
            numeric_id = row_id.replace('syriacars_', '') if row_id.startswith('syriacars_') else row_id

            # Resolve URL via WordPress ?p= redirect if not stored
            if not car_url:
                wp_url = f'{BASE_URL}/?p={numeric_id}'
                try:
                    r = requests.get(wp_url, headers=HEADERS, timeout=15, allow_redirects=True)
                    car_url = r.url
                    logger.info(f'  [{row_num}] {row_id} → {car_url}')
                except Exception as exc:
                    logger.warning(f'  [{row_num}] Could not resolve URL for {row_id}: {exc}')
                    continue

            # Re-scrape detail page to get image URLs
            try:
                detail = self._scrape_detail(car_url, numeric_id)
            except Exception as exc:
                logger.error(f'  [{row_num}] Detail scrape failed for {row_id}: {exc}')
                time.sleep(REQUEST_DELAY)
                continue

            image_urls = detail.pop('_image_urls', [])
            if not image_urls:
                logger.info(f'  [{row_num}] {row_id} → no images on page, skipping')
                time.sleep(REQUEST_DELAY)
                continue

            # Upload images to Drive
            folder_name  = f'syriacars_{numeric_id}'
            image_links: List[str] = []
            folder_url   = ''
            try:
                folder_id, folder_url = self._create_subfolder(folder_name)
                for idx, img_url in enumerate(image_urls, 1):
                    ext   = img_url.rsplit('.', 1)[-1].lower() or 'jpg'
                    fname = f'{numeric_id}_{idx:02d}.{ext}'
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

            # Update ONLY the images_drive_links cell (leave all other data intact)
            if image_links:
                try:
                    self.sheet.update_cell(row_num, images_col + 1, ', '.join(image_links))
                    # Also save the resolved URL if the column exists and was empty
                    if url_col >= 0 and not item['url'] and car_url:
                        self.sheet.update_cell(row_num, url_col + 1, car_url)
                    repaired += 1
                    logger.info(f'  [{row_num}] ✓ {row_id} updated')
                except Exception as exc:
                    logger.error(f'  [{row_num}] Sheet update failed for {row_id}: {exc}')

            time.sleep(REQUEST_DELAY)

        logger.info(f'\nRepair complete: {repaired}/{len(to_repair)} rows updated.')

    # ── Per-car orchestration ─────────────────────────────────────────────────

    # Any field in this set containing "غير معروف" causes the listing to be skipped.
    _QUALITY_FIELDS = (
        'make', 'model', 'year', 'price', 'city',
        'body_type', 'fuel_type', 'transmission', 'condition', 'mileage',
    )

    def _passes_quality_check(self, detail: Dict) -> bool:
        """Return False if any quality field has the value غير معروف."""
        for f in self._QUALITY_FIELDS:
            if str(detail.get(f, '')).strip() == 'غير معروف':
                logger.info(f'  ✗ Quality skip — "{f}" = غير معروف')
                return False
        return True

    def _is_exterior_car_image(self, img_bytes: bytes, mime: str = 'image/jpeg') -> bool:
        """
        Return True if the image likely shows the full exterior of a car.

        Two free heuristics using Pillow:
        1. Aspect ratio — portrait images (h > w) are rarely full exterior shots.
        2. Average brightness — very dark images are typically engine bays or interiors.
        """
        try:
            img = Image.open(io.BytesIO(img_bytes)).convert('RGB')
            w, h = img.size

            # Portrait or near-square → unlikely to be a full exterior shot
            if h > w * 0.95:
                return False

            # Very dark on average → engine bay, dark interior, etc.
            small = img.resize((50, 50))
            pixels = list(small.getdata())
            avg_brightness = sum(r + g + b for r, g, b in pixels) / (len(pixels) * 3)
            if avg_brightness < 55:
                return False

            return True
        except Exception as exc:
            logger.warning(f'  Image heuristic failed: {exc} — treating as exterior')
            return True

    def _process_car(self, listing_id: str, car_url: str, date_added: str = '') -> bool:
        """
        Scrape one car detail page, upload images, write to sheet.
        Returns True on success.
        """
        logger.info(f'  → detail: {car_url}')
        try:
            detail = self._scrape_detail(car_url, listing_id)
        except Exception as exc:
            logger.error(f'  Detail scrape failed: {exc}')
            return False

        if date_added:
            detail['date_added'] = date_added   # listing-page date takes priority
        # else: _scrape_detail already set date_added from the detail page meta

        # Save image URLs before quality check (popped so they don't land in sheet)
        image_urls: List[str] = detail.pop('_image_urls', [])

        # Strip 'English - Arabic' compound values syriacars puts in make/model
        for _f in ('make', 'model', 'body_type', 'fuel_type', 'transmission',
                   'condition', 'city', 'origin', 'exterior_color', 'interior_color'):
            if detail.get(_f):
                detail[_f] = _strip_foreign(detail[_f])

        # Normalize fields to Sayarti canonical values
        detail = normalize_car(detail)

        # ── Quality gate — skip sparse listings before spending image/API credits ──
        if not self._passes_quality_check(detail):
            return False

        image_links: List[str] = []
        clean_link  = ''

        if image_urls:
            # Pick the first image that shows the full exterior of the car.
            # If vision check is enabled, try each image in order until one passes.
            selected_bytes: Optional[bytes] = None
            selected_mime  = 'image/jpeg'
            selected_ext   = 'jpg'

            for idx, img_url in enumerate(image_urls):
                try:
                    r = requests.get(img_url, headers=HEADERS, timeout=30)
                    r.raise_for_status()
                    mime_try  = r.headers.get('Content-Type', 'image/jpeg').split(';')[0]
                    bytes_try = r.content
                    ext_try   = img_url.rsplit('.', 1)[-1].lower() or 'jpg'

                    if self._is_exterior_car_image(bytes_try, mime_try):
                        selected_bytes = bytes_try
                        selected_mime  = mime_try
                        selected_ext   = ext_try
                        if idx > 0:
                            logger.info(f'  Image #{idx+1} chosen as exterior shot (first {idx} skipped)')
                        break
                    else:
                        logger.info(f'  Image #{idx+1} is not a full exterior — trying next')
                except Exception as exc:
                    logger.warning(f'  Could not fetch image #{idx+1} ({img_url}): {exc}')

            # Fall back to first image if none passed the exterior check
            if selected_bytes is None and image_urls:
                try:
                    r = requests.get(image_urls[0], headers=HEADERS, timeout=30)
                    r.raise_for_status()
                    selected_mime  = r.headers.get('Content-Type', 'image/jpeg').split(';')[0]
                    selected_bytes = r.content
                    selected_ext   = image_urls[0].rsplit('.', 1)[-1].lower() or 'jpg'
                    logger.warning('  No exterior image found — falling back to first image')
                except Exception as exc:
                    logger.error(f'  Image error for {listing_id}: {exc}')

            if selected_bytes:
                try:
                    link = self._upload_bytes(
                        selected_bytes, selected_mime, DRIVE_FOLDER_ID,
                        f'{listing_id}.{selected_ext}'
                    )
                    if link:
                        image_links.append(link)
                        logger.info('  Uploaded 1 image → Drive')

                    # ── Watermark removal ─────────────────────────────────────
                    if self.dewatermark_key:
                        logger.info('  Removing watermark…')
                        clean_bytes = self._remove_watermark(selected_bytes)
                        if clean_bytes:
                            clean_link = self._upload_bytes(
                                clean_bytes, 'image/jpeg',
                                DRIVE_FOLDER_ID, f'{listing_id}_clean.jpg',
                            ) or ''
                            logger.info('  ✓ Clean image uploaded')
                        else:
                            logger.warning('  Watermark removal returned no image — skipped')
                except Exception as exc:
                    logger.error(f'  Image error for {listing_id}: {exc}')

        detail['images_drive_links'] = ', '.join(image_links)
        detail['image_clean_link']   = clean_link

        try:
            self._append_row(detail)
            self.existing_ids.add(detail['id'])
            logger.info(f'  ✓  Sheet row written: {detail.get("ad_title", listing_id)!r}')
            return True
        except Exception as exc:
            logger.error(f'  Sheet write failed: {exc}')
            return False

    # ── Main loop ─────────────────────────────────────────────────────────────

    def run(self):
        """
        Paginate through /inventory/, scraping only new listings.

        Incremental mode (default):
          Starts at page 1. Stops when STOP_AFTER_FULL_PAGES consecutive pages
          contain nothing new — meaning we've caught up with the live feed.

        Full-scrape mode (--full):
          Resumes from progress['last_page'] + 1. Does NOT stop on caught-up
          pages — continues until 404 (end of inventory) or the --hours limit.
          Progress is saved after every page for safe pause/resume.
        """
        progress = self.progress

        if self.full_mode:
            start_page = progress['last_page'] + 1
            if progress.get('full_scrape_done'):
                logger.info('Full scrape already marked complete in progress file.')
                logger.info('Delete syriacars_progress.json to restart a full scrape.')
                return
            logger.info(f'Full scrape mode — resuming from page {start_page}')
        else:
            start_page = 1
            logger.info('Incremental mode — starting from page 1')

        logger.info('=' * 62)
        logger.info(f'SyriaCars scraper v2 started  {datetime.now().isoformat()}')
        if self.deadline:
            logger.info(f'Will stop at: {self.deadline.isoformat()}')
        logger.info(f'Existing sheet rows : {len(self.existing_ids)}')
        logger.info('=' * 62)

        total_new        = 0
        full_page_streak = 0

        page = start_page
        while True:

            # ── Check stop conditions before each new page ─────────────────
            if self._should_stop():
                break
            if self.max_pages and page > self.max_pages:
                logger.info(f'Reached --pages limit ({self.max_pages}) — stopping.')
                break

            # Sort by date descending so page 1 always has the newest listings,
            # not featured (مميز) listings pinned to the top regardless of age.
            _sort = '?orderby=date&order=DESC'
            page_url = (
                INVENTORY_URL + _sort if page == 1
                else f'{BASE_URL}/inventory/page/{page}/{_sort}'
            )
            logger.info(f'\n[Page {page}] {page_url}')

            # ── Fetch listing page ─────────────────────────────────────────
            try:
                items = self._scrape_listing_page(page_url)
            except requests.HTTPError as exc:
                if exc.response.status_code == 404:
                    logger.info('  404 — no more pages.')
                    if self.full_mode:
                        progress['full_scrape_done'] = True
                        _save_progress(progress)
                    break
                logger.error(f'  HTTP error fetching listing page: {exc}')
                break
            except Exception as exc:
                logger.error(f'  Listing page error: {exc}')
                break

            if not items:
                logger.info('  No listing items found — stopping.')
                if self.full_mode:
                    progress['full_scrape_done'] = True
                    _save_progress(progress)
                break

            # ── Date-range filter ─────────────────────────────────────────
            # Listings are date-sorted DESC, so the first all-before-start_date
            # page means every subsequent page is also too old → stop.
            _cutoff = self.start_date or '2026-01-01'
            dated = [it for it in items if it.get('date_added')]
            if dated and all(it['date_added'] < _cutoff for it in dated):
                logger.info(f'  All listings on this page are before {_cutoff} — done.')
                if self.full_mode:
                    progress['full_scrape_done'] = True
                    _save_progress(progress)
                break

            # Drop items outside [start_date, end_date]
            items = [
                it for it in items
                if (not it.get('date_added')
                    or (it['date_added'] >= _cutoff
                        and (not self.end_date or it['date_added'] <= self.end_date)))
            ]

            # ── Filter to new listings only ───────────────────────────────
            new_items = [
                it for it in items
                if f"syriacars_{it['listing_id']}" not in self.existing_ids
            ]
            logger.info(f'  {len(items)} total (2026+) | {len(new_items)} new')

            if not new_items:
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
                    # In full mode, all-existing pages still advance the counter
                    logger.info('  All existing on this page — continuing (full mode).')
                    progress['last_page'] = page
                    _save_progress(progress)
                time.sleep(REQUEST_DELAY)
                page += 1
                continue

            full_page_streak = 0

            # ── Scrape + upload each new car ──────────────────────────────
            for it in new_items:
                if self._should_stop():
                    # Save page progress BEFORE the incomplete page so next
                    # run re-tries all cars on the current page from the start.
                    if self.full_mode:
                        progress['last_page'] = page - 1
                        _save_progress(progress)
                    break
                ok = self._process_car(it['listing_id'], it['car_url'], it.get('date_added', ''))
                if ok:
                    total_new += 1
                    progress['total_scraped'] += 1
                    if self.max_cars and total_new >= self.max_cars:
                        logger.info(f'Reached --max-cars limit ({self.max_cars}) — stopping.')
                        self._stop_requested = True
                        break
                time.sleep(REQUEST_DELAY)
            else:
                # Completed all cars on this page — advance progress
                if self.full_mode:
                    progress['last_page'] = page
                    _save_progress(progress)

            if self._should_stop():
                break

            time.sleep(REQUEST_DELAY)
            page += 1

        # ── Summary ───────────────────────────────────────────────────────────
        logger.info('\n' + '=' * 62)
        logger.info(f'Done. {total_new} new listings written to Google Sheets.')
        if self.full_mode:
            logger.info(
                f'Progress: last_page={progress["last_page"]}, '
                f'total_scraped={progress["total_scraped"]}, '
                f'full_scrape_done={progress.get("full_scrape_done", False)}'
            )
        logger.info('=' * 62)

        # Sort sheet by date_added (newest first) after every run
        if total_new > 0:
            self._sort_sheet_by_date()


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='SyriaCars.net scraper v2',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
examples:
  python syriacars_standalone.py               # incremental (daily update)
  python syriacars_standalone.py --hours 2     # run for 2 hours then stop
  python syriacars_standalone.py --full        # full scrape, resume from last page
  python syriacars_standalone.py --full --hours 4
        """,
    )
    parser.add_argument(
        '--hours', type=float, metavar='N',
        help='Stop gracefully after N hours (e.g. --hours 2)',
    )
    parser.add_argument(
        '--pages', type=int, default=None, metavar='N',
        help='Stop after scraping N pages (e.g. --pages 1 for a quick test)',
    )
    parser.add_argument(
        '--max-cars', type=int, default=None, metavar='N',
        help='Stop after successfully scraping N new cars (e.g. --max-cars 100)',
    )
    parser.add_argument(
        '--full', action='store_true',
        help=(
            'Full-scrape mode: resume from the last saved page '
            'and do not stop on consecutive caught-up pages'
        ),
    )
    parser.add_argument(
        '--repair-images', action='store_true',
        help=(
            'Repair mode: re-upload Drive images for every existing sheet row '
            'whose "images" column is empty (caused by earlier Drive 403 errors). '
            'Does not scrape new listings.'
        ),
    )
    parser.add_argument(
        '--repair-data', action='store_true',
        help='Normalize all existing sheet rows to Sayarti canonical values.',
    )
    parser.add_argument(
        '--scrape-dealers', action='store_true',
        help=(
            'Scrape syriacars.net/dealers-list/, enrich each dealer with phone '
            'and city, then write results to the SyriaCarsDealers Google Sheet '
            '(created automatically on first run).'
        ),
    )

    def _parse_date(s: str) -> str:
        if re.match(r'^\d{4}-\d{2}-\d{2}$', s):
            return s
        m = re.match(r'^(\d{2})-(\d{2})-(\d{4})$', s)
        if m:
            return f'{m.group(3)}-{m.group(2)}-{m.group(1)}'
        raise argparse.ArgumentTypeError(
            f'Invalid date "{s}". Use YYYY-MM-DD or DD-MM-YYYY'
        )

    parser.add_argument(
        '--start-date', type=_parse_date, default=None, metavar='DATE',
        help='Only scrape listings from this date onward (YYYY-MM-DD or DD-MM-YYYY). '
             'Stops pagination when all items on a page are older than this date.',
    )
    parser.add_argument(
        '--end-date', type=_parse_date, default=None, metavar='DATE',
        help='Only scrape listings up to this date (YYYY-MM-DD or DD-MM-YYYY).',
    )
    parser.add_argument(
        '--dewatermark-key', default=None, metavar='KEY',
        help='dewatermark.ai API key. When provided, the best image per listing '
             'is sent for watermark removal and uploaded as {id}_clean.jpg.',
    )
    args = parser.parse_args()

    if sys.stdout.encoding != 'utf-8':
        sys.stdout.reconfigure(encoding='utf-8')

    if not os.path.exists(OAUTH_CLIENT_FILE):
        print(
            f'ERROR: OAuth2 client secret not found at:\n  {OAUTH_CLIENT_FILE}\n'
            'Download it from Google Cloud Console → APIs & Services → Credentials\n'
            'and place it next to this script.'
        )
        sys.exit(1)

    scraper = SyriaCarsScraper(
        full_mode=args.full,
        max_hours=args.hours,
        max_pages=args.pages,
        start_date=args.start_date,
        end_date=args.end_date,
        dewatermark_key=args.dewatermark_key,
    )
    scraper.max_cars = args.max_cars
    if args.scrape_dealers:
        scraper.scrape_dealers()
    elif args.repair_images:
        scraper._repair_images()
    elif args.repair_data:
        scraper.repair_data()
    else:
        scraper.run()
