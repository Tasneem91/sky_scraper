#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Damazzle Raw Data Scraper
=========================
Scrapes ALL listings from Damazzle, writes each car to:
  • rawdata_damazzle.jsonl  (local backup, one JSON per line)
  • Google Sheet: damazzle_raw_data

No images downloaded. No quality gate. Pure data extraction.

USAGE
-----
  python rawdata_damazzle.py                         # incremental
  python rawdata_damazzle.py --full                  # resume from last page
  python rawdata_damazzle.py --hours 4
  python rawdata_damazzle.py --start-date 2025-01-01
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
        logging.FileHandler('rawdata_damazzle.log', encoding='utf-8'),
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

OUTPUT_FILE   = os.path.join(SCRIPT_DIR, 'rawdata_damazzle.jsonl')
PROGRESS_FILE = os.path.join(SCRIPT_DIR, 'rawdata_damazzle_progress.json')

SHEET_ID = '18welFOozXYwuB-Xr5Ppwsj4EB8L19NwJ3xKu3JkbDmY'

SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive',
]

BASE_URL   = 'https://beta.damazzletech.com'
API_BASE   = f'{BASE_URL}/api/api/v1'
SOURCE     = 'damazzle'
PAGE_SIZE  = 20

REQUEST_DELAY         = 1.0
STOP_AFTER_FULL_PAGES = 3

# ── Sheet columns ─────────────────────────────────────────────────────────────

COLUMNS: List[str] = [
    'id', 'source', 'car_url', 'listing_id', 'slug',
    'ad_title', 'listing_type',
    'make', 'model', 'year', 'body_type', 'condition',
    'exterior_color', 'interior_color',
    'fuel_type', 'engine_size', 'transmission', 'drive_system',
    'cylinders', 'doors', 'chassis_number', 'chassis_condition',
    'warranty', 'horsepower', 'seats', 'steering_side', 'origin',
    'city', 'mileage', 'price',
    'date_added', 'scraped_at',
    'phone', 'seller_name', 'seller_listings',
    'description',
    'image_urls', 'image_count',
]

# ── Field maps ────────────────────────────────────────────────────────────────

SLUG_MAP: Dict[str, str] = {
    'mileage':            'mileage',
    'year':               'year',
    'exterior_color':     'exterior_color',
    'interior_color':     'interior_color',
    'fuel_type':          'fuel_type',
    'transmission':       'transmission',
    'condition':          'condition',
    'engine_size':        'engine_size',
    'body_type':          'body_type',
    'drive_system':       'drive_system',
    'doors':              'doors',
    'cylinders':          'cylinders',
    'chassis_number':     'chassis_number',
    'warranty':           'warranty',
    'chassis_condition':  'chassis_condition',
    'horsepower':         'horsepower',
    'seats':              'seats',
    'steering_side':      'steering_side',
    'origin':             'origin',
}

LABEL_MAP: Dict[str, str] = {
    'الكيلومتراج':     'mileage',
    'السنة':           'year',
    'اللون الخارجي':   'exterior_color',
    'اللون الداخلي':   'interior_color',
    'الوقود':          'fuel_type',
    'ناقل الحركة':     'transmission',
    'الغيار':          'transmission',
    'الحالة':          'condition',
    'المحرك':          'engine_size',
    'نوع الجسم':       'body_type',
    'نظام الدفع':      'drive_system',
    'الأبواب':         'doors',
    'السلندرات':       'cylinders',
    'رقم الهيكل':      'chassis_number',
    'الضمان':          'warranty',
    'حالة الهيكل':     'chassis_condition',
    'قوة الحصان':      'horsepower',
    'المقاعد':         'seats',
    'جهة القيادة':     'steering_side',
    'الوارد':          'origin',
}

COND_MAP: Dict[str, str] = {
    'used':    'مستعمل',
    'new':     'جديد',
    'damaged': 'متضرر',
}

TRANS_MAP: Dict[str, str] = {
    'automatic': 'أوتوماتيك',
    'manual':    'مانيوال',
    'cvt':       'CVT',
    'dct':       'DCT',
}

FUEL_MAP: Dict[str, str] = {
    'gasoline': 'بنزين',
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
    'fwd': 'دفع أمامي',
    'rwd': 'دفع خلفي',
    '4wd': 'دفع رباعي',
    'awd': 'دفع رباعي كامل',
    '4x4': 'دفع رباعي',
}

# ── Helpers ───────────────────────────────────────────────────────────────────


def _clean(v: Any) -> str:
    if v is None:
        return ''
    t = ' '.join(str(v).split())
    return '' if t in ('-', '—', '–', '', 'null', 'None') else t


def _arabic(eng: str, mapping: Dict[str, str]) -> str:
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


class DamazzleRawScraper:

    def __init__(
        self,
        full_mode: bool = False,
        max_hours: Optional[float] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ):
        self.full_mode  = full_mode
        self.start_date = start_date
        self.end_date   = end_date
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
            'Accept':  'application/json',
            'Referer': BASE_URL + '/',
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
        url = f'{API_BASE}/ads'
        params = {
            'page':      page,
            'pageSize':  PAGE_SIZE,
            'type':      'VEHICLE',
            'sortBy':    'createdAt',
            'sortOrder': 'DESC',
        }
        try:
            resp = self.session.get(url, params=params, timeout=30)
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            logger.error(f'  Listing API error (page {page}): {exc}')
            return None

    def _fetch_detail(self, slug: str) -> Optional[Dict]:
        url = f'{API_BASE}/ads/details-by-slug/{slug}'
        try:
            resp = self.session.get(url, timeout=30)
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            logger.error(f'  Detail API error ({slug}): {exc}')
            return None

    def _parse_car(self, c: Dict, detail: Optional[Dict] = None) -> Dict:
        data: Dict = {
            'scraped_at': datetime.now().isoformat(),
            'source':     SOURCE,
        }

        lid  = str(c.get('id', '') or c.get('_id', '') or '').strip()
        slug = str(c.get('slug', '') or '').strip()
        data['listing_id'] = lid
        data['id']         = f'damazzle_{lid}' if lid else f'damazzle_{slug}'
        data['slug']       = slug
        data['car_url']    = f'{BASE_URL}/vehicle/{slug}' if slug else ''

        title = _clean(c.get('title') or c.get('name', ''))
        data['ad_title']     = title
        data['listing_type'] = ('للإيجار'
                                if any(k in title for k in ('إيجار', 'ايجار', 'للإيجار'))
                                else 'للبيع')

        cat = c.get('category', {}) or {}
        data['make'] = _clean(
            cat.get('name_ar') or cat.get('name') or
            c.get('make') or c.get('brand') or ''
        )

        gov = c.get('governorate', {}) or {}
        data['city'] = _clean(
            gov.get('name_ar') or gov.get('name') or
            c.get('city') or ''
        )

        data['price']      = _parse_price(c.get('price'))
        data['date_added'] = _parse_date(
            c.get('createdAt') or c.get('created_at') or c.get('date_added')
        )

        # Featured attributes from listing
        for attr in (c.get('featuredAttributes', []) or []):
            key = str(attr.get('slug', '') or '').strip().lower()
            val = _clean(attr.get('value_ar') or attr.get('value') or attr.get('val', ''))
            field = SLUG_MAP.get(key)
            if field and not data.get(field):
                data[field] = val

        # Normalise
        for field, mapping in (
            ('condition',   COND_MAP),
            ('transmission', TRANS_MAP),
            ('fuel_type',   FUEL_MAP),
            ('body_type',   BODY_MAP),
            ('drive_system', DRIVE_MAP),
        ):
            if data.get(field):
                data[field] = _arabic(data[field], mapping)

        # Image URLs (collected, not downloaded)
        images: List[str] = []
        for img in (c.get('images') or c.get('photos') or []):
            src = (img.get('url') or img.get('src') or img.get('path') or ''
                   if isinstance(img, dict) else str(img)).strip()
            if src:
                if not src.startswith('http'):
                    src = BASE_URL.rstrip('/') + '/' + src.lstrip('/')
                images.append(src)

        # Enrich from detail API
        if detail:
            detail_data = (detail.get('data') or detail
                           if isinstance(detail, dict) else {})

            if not data.get('model'):
                data['model'] = _clean(
                    detail_data.get('model_ar') or detail_data.get('model') or ''
                )
            if not data.get('description'):
                data['description'] = _clean(
                    detail_data.get('description_ar') or detail_data.get('description') or ''
                )

            seller = detail_data.get('user', {}) or {}
            if not data.get('seller_name'):
                data['seller_name'] = _clean(
                    seller.get('name') or seller.get('full_name') or ''
                )
            phones = detail_data.get('phones', []) or []
            if not data.get('phone') and phones:
                p = phones[0]
                data['phone'] = _clean(p.get('number', '') if isinstance(p, dict) else str(p))
            seller_ads = seller.get('totalAds') or seller.get('ads_count')
            if seller_ads is not None:
                data['seller_listings'] = str(seller_ads)

            for attr in (detail_data.get('attributes', []) or []):
                key   = str(attr.get('slug', '') or '').strip().lower()
                label = _clean(attr.get('name_ar') or attr.get('name') or '')
                val   = _clean(attr.get('value_ar') or attr.get('value') or attr.get('val', ''))
                field = SLUG_MAP.get(key) or LABEL_MAP.get(label)
                if field and not data.get(field):
                    data[field] = val

            # Detail images (usually higher res)
            detail_imgs = detail_data.get('images') or detail_data.get('photos') or []
            if detail_imgs:
                images = []
                for img in detail_imgs:
                    src = (img.get('url') or img.get('src') or img.get('path') or ''
                           if isinstance(img, dict) else str(img)).strip()
                    if src:
                        if not src.startswith('http'):
                            src = BASE_URL.rstrip('/') + '/' + src.lstrip('/')
                        images.append(src)

        data['image_urls']  = images
        data['image_count'] = len(images)
        return data

    def _process_car(self, c: Dict) -> bool:
        slug   = str(c.get('slug', '') or '').strip()
        lid    = str(c.get('id', '') or c.get('_id', '') or '').strip()
        car_id = f'damazzle_{lid}' if lid else f'damazzle_{slug}'

        if car_id in self.existing_ids:
            return False

        logger.info(f'  → {slug}')
        detail = self._fetch_detail(slug) if slug else None
        time.sleep(0.3)

        try:
            data = self._parse_car(c, detail)
        except Exception as exc:
            logger.error(f'  Parse error: {exc}')
            return False

        try:
            self._append_row(data)
            _append_jsonl(data)
            self.existing_ids.add(car_id)
            logger.info(f'  ✓  Saved: {data.get("ad_title", slug)!r}')
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
        logger.info(f'Damazzle raw scraper  {datetime.now().isoformat()}')
        logger.info('=' * 62)

        total_new        = 0
        full_page_streak = 0
        page             = start_page

        while True:
            if self._should_stop():
                break

            logger.info(f'\n[Page {page}]')
            payload = self._fetch_page(page)

            if not payload:
                logger.info('  API error — stopping.')
                break

            items = (payload.get('data') or payload.get('results') or
                     payload.get('ads') or payload.get('items') or [])
            if not items and isinstance(payload, list):
                items = payload

            if not items:
                logger.info('  No items — stopping.')
                if self.full_mode:
                    progress['full_scrape_done'] = True
                    _save_progress(progress)
                break

            if self.start_date or self.end_date:
                def _in_range(car):
                    d = _parse_date(
                        car.get('createdAt') or car.get('created_at') or ''
                    )
                    if not d:
                        return True
                    if self.start_date and d < self.start_date:
                        return False
                    if self.end_date and d > self.end_date:
                        return False
                    return True

                if self.start_date:
                    first_dates = [
                        _parse_date(it.get('createdAt') or it.get('created_at', ''))
                        for it in items
                        if _parse_date(it.get('createdAt') or it.get('created_at', ''))
                    ]
                    if first_dates and all(d < self.start_date for d in first_dates):
                        logger.info(f'  All before {self.start_date} — done.')
                        break

                items = [it for it in items if _in_range(it)]

            new_items = [
                it for it in items
                if (f"damazzle_{it.get('id', '')}" not in self.existing_ids
                    and f"damazzle_{it.get('slug', '')}" not in self.existing_ids)
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

            total = (payload.get('total') or payload.get('count') or
                     payload.get('totalCount') or None)
            if total is not None and page * PAGE_SIZE >= int(total):
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
    parser = argparse.ArgumentParser(description='Damazzle raw data scraper')
    parser.add_argument('--full',  action='store_true')
    parser.add_argument('--hours', type=float, metavar='N')

    def _pd(s):
        if re.match(r'^\d{4}-\d{2}-\d{2}$', s):
            return s
        m = re.match(r'^(\d{2})-(\d{2})-(\d{4})$', s)
        if m:
            return f'{m.group(3)}-{m.group(2)}-{m.group(1)}'
        raise argparse.ArgumentTypeError(f'Invalid date "{s}"')

    parser.add_argument('--start-date', type=_pd, metavar='DATE')
    parser.add_argument('--end-date',   type=_pd, metavar='DATE')
    args = parser.parse_args()

    if sys.stdout.encoding != 'utf-8':
        sys.stdout.reconfigure(encoding='utf-8')

    DamazzleRawScraper(
        full_mode=args.full,
        max_hours=args.hours,
        start_date=args.start_date,
        end_date=args.end_date,
    ).run()
