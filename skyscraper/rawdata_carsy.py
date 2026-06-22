#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Carsy.app Raw Data Scraper
==========================
Scrapes ALL listings from the Carsy REST API, writes each car to:
  • rawdata_carsy.jsonl  (local backup, one JSON per line)
  • Google Sheet: carzy_raw_data

No images downloaded. No quality gate. Pure data extraction.

USAGE
-----
  python rawdata_carsy.py                         # incremental
  python rawdata_carsy.py --full                  # resume full scrape
  python rawdata_carsy.py --hours 4
  python rawdata_carsy.py --pages 5               # quick test
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
from typing import Any, Dict, List, Optional, Set

import requests

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
        logging.FileHandler('rawdata_carsy.log', encoding='utf-8'),
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

OUTPUT_FILE   = os.path.join(SCRIPT_DIR, 'rawdata_carsy.jsonl')
PROGRESS_FILE = os.path.join(SCRIPT_DIR, 'rawdata_carsy_progress.json')

SHEET_ID = '1wnlLDBhXvPP0YD-aoouBJdK7dKJazNTK7BMsdP1fP7g'

SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive',
]

API_BASE        = 'https://app.carsy.app/api'
API_DETAIL_URL  = 'https://app.carsy.app/api/classifieds/{id}'
SITE_CAR_URL    = 'https://carsy.app/cars/{id}'
SOURCE          = 'carsy'
PAGE_SIZE       = 20

REQUEST_DELAY         = 0.8
STOP_AFTER_FULL_PAGES = 3

# ── Sheet columns ─────────────────────────────────────────────────────────────

COLUMNS: List[str] = [
    'id', 'source', 'car_url', 'listing_id',
    'ad_title', 'listing_type', 'condition', 'body_type', 'status',
    'make', 'model', 'year',
    'exterior_color', 'interior_color',
    'fuel_type', 'engine_size', 'cylinders', 'transmission', 'drive_system',
    'origin', 'specifications',
    'city', 'mileage', 'price',
    'date_added', 'scraped_at', 'views', 'featured',
    'phone', 'seller_name',
    'description',
    'image_urls', 'image_count',
]

# ── Value maps ────────────────────────────────────────────────────────────────

COLOR_MAP: Dict[str, str] = {
    'white':       'أبيض',
    'black':       'أسود',
    'silver':      'فضي',
    'grey':        'رمادي',
    'gray':        'رمادي',
    'red':         'أحمر',
    'blue':        'أزرق',
    'green':       'أخضر',
    'yellow':      'أصفر',
    'orange':      'برتقالي',
    'brown':       'بني',
    'beige':       'بيج',
    'gold':        'ذهبي',
    'champagne':   'شمبانيا',
    'pearl':       'لؤلؤي',
    'maroon':      'كستنائي',
    'purple':      'بنفسجي',
    'other':       'آخر',
}

TRANS_MAP: Dict[str, str] = {
    'automatic': 'أوتوماتيك',
    'manual':    'مانيوال',
    'normal':    'مانيوال',
    'cvt':       'CVT',
}

FUEL_MAP: Dict[str, str] = {
    'gasoline': 'بنزين',
    'petrol':   'بنزين',
    'oil':      'بنزين',
    'diesel':   'ديزل',
    'electric': 'كهربائي',
    'hybrid':   'هايبرد',
    'gas':      'غاز',
}

BODY_MAP: Dict[str, str] = {
    'sedan':       'سيدان',
    'suv':         'دفع رباعي',
    'pickup':      'بيكاب',
    'hatchback':   'هاتشباك',
    'coupe':       'كوبيه',
    'wagon':       'ستيشن واغن',
    'van':         'فان',
    'minivan':     'ميني فان',
    'convertible': 'كشف',
    'truck':       'شاحنة',
    'bus':         'باص',
}

DRIVE_MAP: Dict[str, str] = {
    'fwd':   'دفع أمامي',
    'rwd':   'دفع خلفي',
    '4wd':   'دفع رباعي',
    'awd':   'دفع رباعي كامل',
    '4x4':   'دفع رباعي',
    'front': 'دفع أمامي',
    'rear':  'دفع خلفي',
}

COND_MAP: Dict[str, str] = {
    'used':    'مستعمل',
    'new':     'جديد',
    'damaged': 'متضرر',
}

ORIGIN_MAP: Dict[str, str] = {
    'local':         'محلي',
    'imported':      'مستورد',
    'gcc':           'خليجي',
    'european':      'أوروبي',
    'american':      'أمريكي',
    'japanese':      'ياباني',
    'korean':        'كوري',
    'syria_agency':  'وكالة سورية',
}

SPECS_MAP: Dict[str, str] = {
    'full':        'كاملة المواصفات',
    'gcc':         'مواصفات خليجية',
    'american':    'مواصفات أمريكية',
    'european':    'مواصفات أوروبية',
    'japanese':    'مواصفات يابانية',
    'standard':    'قياسي',
    'third_class': 'الفئة الثالثة فأدنى',
}

CITY_MAP: Dict[str, str] = {
    'damascus':    'دمشق',
    'aleppo':      'حلب',
    'homs':        'حمص',
    'latakia':     'اللاذقية',
    'tartous':     'طرطوس',
    'tartus':      'طرطوس',
    'hama':        'حماة',
    'daraa':       'درعا',
    'deir_ez_zor': 'دير الزور',
    'idlib':       'إدلب',
    'raqqa':       'الرقة',
    'hasakah':     'الحسكة',
    'qamishli':    'القامشلي',
    'suwayda':     'السويداء',
    'quneitra':    'القنيطرة',
}

# ── Helpers ───────────────────────────────────────────────────────────────────


def _clean(v: Any) -> str:
    if v is None:
        return ''
    t = ' '.join(str(v).split())
    return '' if t in ('-', '—', '–', '', 'null', 'None') else t


def _ar(eng: str, mapping: Dict[str, str]) -> str:
    return mapping.get(str(eng).lower().strip(), _clean(eng))


def _parse_price(v: Any) -> str:
    if not v:
        return ''
    digits = re.sub(r'[^\d.]', '', str(v))
    try:
        n = float(digits)
        return str(int(n)) if n == int(n) else str(n)
    except (ValueError, TypeError):
        return digits


def _parse_date(v: Any) -> str:
    if not v:
        return ''
    m = re.match(r'(\d{4}-\d{2}-\d{2})', str(v))
    return m.group(1) if m else ''


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


# ── Progress ──────────────────────────────────────────────────────────────────


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
    with open(OUTPUT_FILE, 'a', encoding='utf-8') as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + '\n')


# ── Scraper ───────────────────────────────────────────────────────────────────


class CarsyRawScraper:

    def __init__(
        self,
        full_mode: bool = False,
        max_hours: Optional[float] = None,
        max_pages: Optional[int] = None,
    ):
        self.full_mode = full_mode
        self.max_pages = max_pages
        self.deadline: Optional[datetime] = (
            datetime.now() + timedelta(hours=max_hours) if max_hours else None
        )
        self._stop_requested = False

        signal.signal(signal.SIGINT,  self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)

        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': (
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                'AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/120.0.0.0 Safari/537.36'
            ),
            'Accept': 'application/json',
        })

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

    def _fetch_page(self, page: int) -> Optional[Dict]:
        url = f'{API_BASE}/classifieds'
        params = {
            'page':     page,
            'per_page': PAGE_SIZE,
            'sort':     'newest',
        }
        try:
            resp = self.session.get(url, params=params, timeout=30)
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            logger.error(f'  API error (page {page}): {exc}')
            return None

    def _fetch_detail(self, car_id: str) -> Optional[Dict]:
        url = API_DETAIL_URL.format(id=car_id)
        try:
            resp = self.session.get(url, timeout=30)
            if resp.status_code != 200:
                logger.debug(f'  Detail {car_id}: HTTP {resp.status_code}')
                return None
            body = resp.json()
            return (body.get('data') or {}).get('classified')
        except Exception as exc:
            logger.debug(f'  Detail fetch error ({car_id}): {exc}')
            return None

    def _parse_classified(self, c: Dict, listing: Optional[Dict] = None) -> Dict:
        """Parse a classified dict (from detail API) into a flat row dict.

        c       — detail API response (data.classified), the primary source
        listing — original listing item as fallback for any missing fields
        """
        data: Dict = {
            'scraped_at': datetime.now().isoformat(),
            'source':     SOURCE,
        }

        base = {**(listing or {}), **c}   # detail wins over listing

        lid = str(base.get('id', '') or '').strip()
        data['listing_id'] = lid
        data['id']         = f'carsy_{lid}'
        data['car_url']    = SITE_CAR_URL.format(id=lid) if lid else ''

        # Title (API returns title_ar)
        data['ad_title']     = _clean(base.get('title_ar') or base.get('title_en') or base.get('name') or '')
        data['listing_type'] = 'للبيع'
        data['price']        = _parse_price(base.get('price'))
        data['date_added']   = ''   # API only returns relative dates; no absolute creation date

        # Make / model from brand.parent (make) and brand (model)
        brand_obj  = base.get('brand') or {}
        if isinstance(brand_obj, dict):
            parent_obj = brand_obj.get('parent') or {}
            data['make']  = _clean(parent_obj.get('name_ar') or parent_obj.get('name') or '')
            data['model'] = _clean(brand_obj.get('name_ar') or brand_obj.get('name') or '')
        else:
            data['make'] = data['model'] = ''

        data['year'] = _clean(str(base.get('year') or ''))

        # Colors: detail API uses external_color / internal_color (English)
        raw_ext = _clean(str(base.get('external_color') or base.get('exterior_color') or base.get('color') or ''))
        data['exterior_color'] = _ar(raw_ext, COLOR_MAP) if raw_ext else ''
        raw_int = _clean(str(base.get('internal_color') or base.get('interior_color') or ''))
        data['interior_color'] = _ar(raw_int, COLOR_MAP) if raw_int else ''

        # Mileage: kilometers_parsed is human-readable ("+100,000"), kilometers is a category code
        data['mileage'] = _clean(str(base.get('kilometers_parsed') or base.get('mileage') or base.get('odometer') or ''))

        # Engine / drivetrain: detail API uses engine_capacity, number_of_cylinders, drive_line
        data['engine_size']  = _clean(str(base.get('engine_capacity') or base.get('engine_size') or base.get('engine') or ''))
        data['cylinders']    = _clean(str(base.get('number_of_cylinders') or base.get('cylinders') or ''))
        data['transmission'] = _ar(_clean(str(base.get('transmission') or '')), TRANS_MAP)
        data['fuel_type']    = _ar(_clean(str(base.get('fuel_type') or '')), FUEL_MAP)
        data['drive_system'] = _ar(_clean(str(base.get('drive_line') or base.get('drive_system') or base.get('drivetrain') or '')), DRIVE_MAP)

        # Body / condition / status
        data['body_type']  = _ar(_clean(str(base.get('body_type') or '')), BODY_MAP)
        data['condition']  = _ar(_clean(str(base.get('condition') or '')), COND_MAP)
        data['status']     = _clean(str(base.get('status') or ''))

        # Origin: detail API uses 'source' field (e.g. "syria_agency")
        raw_origin = _clean(str(base.get('source') or base.get('origin') or ''))
        data['origin'] = _ar(raw_origin, ORIGIN_MAP) if raw_origin else ''

        # Specifications
        raw_specs = _clean(str(base.get('specifications') or base.get('specs') or ''))
        data['specifications'] = _ar(raw_specs, SPECS_MAP) if raw_specs else ''

        # Location: API returns English city name (e.g. "damascus")
        raw_city = _clean(str(base.get('city') or base.get('location') or ''))
        data['city'] = _ar(raw_city, CITY_MAP) if raw_city else ''

        # Seller: detail API has user.name and user.phone
        user_obj = base.get('user') or {}
        if isinstance(user_obj, dict):
            data['seller_name'] = _clean(user_obj.get('name') or user_obj.get('full_name') or '')
            data['phone']       = _clean(str(user_obj.get('phone') or ''))
        else:
            data['seller_name'] = ''
            data['phone']       = ''

        # Description
        data['description'] = _clean(base.get('description') or base.get('notes') or '')

        # Extra fields
        data['views']    = str(base.get('views_count') or base.get('views') or '')
        data['featured'] = str(bool(base.get('is_featured') or base.get('featured')))

        # Images:
        #   listing API → space-separated string
        #   detail API  → array of strings or dicts
        images: List[str] = []
        raw_images = base.get('images') or []
        if isinstance(raw_images, str):
            images = [u.strip() for u in raw_images.split() if u.strip()]
        elif isinstance(raw_images, list):
            for img in raw_images:
                src = (img.get('url') or img.get('src') or img.get('path') or ''
                       if isinstance(img, dict) else str(img)).strip()
                if src and not src.endswith('/'):
                    images.append(src)

        data['image_urls']  = images
        data['image_count'] = len(images)
        return data

    def _process_car(self, listing: Dict) -> bool:
        lid    = str(listing.get('id', '') or '').strip()
        car_id = f'carsy_{lid}'
        if car_id in self.existing_ids:
            return False

        logger.info(f'  → {car_id}')

        # Fetch detail API for phone, specs, make/model
        classified = self._fetch_detail(lid)
        c = classified if classified else listing

        try:
            data = self._parse_classified(c, listing=listing)
        except Exception as exc:
            logger.error(f'  Parse error: {exc}')
            return False

        try:
            self._append_row(data)
            _append_jsonl(data)
            self.existing_ids.add(car_id)
            logger.info(f'  ✓  Saved: {data.get("ad_title", car_id)!r}')
            return True
        except Exception as exc:
            logger.error(f'  Write failed: {exc}')
            return False

    def run(self):
        progress = self.progress

        if self.full_mode:
            start_page = progress['last_page'] + 1
            if progress.get('full_scrape_done'):
                logger.info('Full scrape complete. Delete progress file to restart.')
                return
            logger.info(f'Full scrape mode — resuming from page {start_page}')
        else:
            start_page = 1
            logger.info('Incremental mode — starting from page 1')

        logger.info('=' * 62)
        logger.info(f'Carsy raw scraper  {datetime.now().isoformat()}')
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

            logger.info(f'\n[Page {page}]')
            payload = self._fetch_page(page)

            if not payload:
                logger.info('  API error — stopping.')
                break

            items = (payload.get('data') or payload.get('classifieds') or
                     payload.get('results') or payload.get('items') or [])
            if not items and isinstance(payload, list):
                items = payload

            if not items:
                logger.info('  No items — stopping.')
                if self.full_mode:
                    progress['full_scrape_done'] = True
                    _save_progress(progress)
                break

            new_items = [
                it for it in items
                if f"carsy_{it.get('id', '')}" not in self.existing_ids
            ]
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
                ok = self._process_car(it)
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

            pagination = payload.get('pagination') or {}
            last_page  = pagination.get('last_page')
            if last_page is not None and page >= int(last_page):
                logger.info('  All pages scraped.')
                if self.full_mode:
                    progress['full_scrape_done'] = True
                    _save_progress(progress)
                break

            time.sleep(REQUEST_DELAY)
            page += 1

        logger.info('\n' + '=' * 62)
        logger.info(f'Done. {total_new} cars → sheet + {OUTPUT_FILE}')
        logger.info('=' * 62)


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Carsy raw data scraper')
    parser.add_argument('--full',  action='store_true')
    parser.add_argument('--hours', type=float, metavar='N')
    parser.add_argument('--pages', type=int,   metavar='N')
    args = parser.parse_args()

    if sys.stdout.encoding != 'utf-8':
        sys.stdout.reconfigure(encoding='utf-8')

    CarsyRawScraper(
        full_mode=args.full,
        max_hours=args.hours,
        max_pages=args.pages,
    ).run()
