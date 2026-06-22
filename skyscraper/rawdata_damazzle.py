#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Damazzle Raw Data Scraper
=========================
Scrapes ALL car listings from damazzle.com using Playwright to intercept
the real API calls the Angular SPA makes.  Writes each car to:
  • rawdata_damazzle.jsonl  (local backup, one JSON per line)
  • Google Sheet: damazzle_raw_data

No images downloaded. No quality gate. Pure data extraction.
Requires: pip install playwright && playwright install chromium

USAGE
-----
  python rawdata_damazzle.py                         # incremental
  python rawdata_damazzle.py --full                  # resume full scrape
  python rawdata_damazzle.py --hours 4
  python rawdata_damazzle.py --start-date 2025-01-01
"""

import argparse
import asyncio
import json
import logging
import os
import re
import signal
import sys
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set

import gspread
from google.auth.transport.requests import Request
from google.oauth2 import credentials as google_creds_module
from google_auth_oauthlib.flow import InstalledAppFlow
from playwright.async_api import async_playwright, Page, Response

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

SITE_URL   = 'https://damazzle.com'
SEARCH_URL = 'https://damazzle.com/motors/cars/search'
SOURCE     = 'damazzle'

# How long to wait for the page to load + API response (seconds)
PAGE_TIMEOUT    = 30_000
RESPONSE_WAIT   = 10.0
REQUEST_DELAY   = 1.5
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
    'mileage':           'mileage',
    'year':              'year',
    'exterior_color':    'exterior_color',
    'interior_color':    'interior_color',
    'fuel_type':         'fuel_type',
    'transmission':      'transmission',
    'condition':         'condition',
    'engine_size':       'engine_size',
    'body_type':         'body_type',
    'drive_system':      'drive_system',
    'doors':             'doors',
    'cylinders':         'cylinders',
    'chassis_number':    'chassis_number',
    'warranty':          'warranty',
    'chassis_condition': 'chassis_condition',
    'horsepower':        'horsepower',
    'seats':             'seats',
    'steering_side':     'steering_side',
    'origin':            'origin',
}

LABEL_MAP: Dict[str, str] = {
    'الكيلومتراج':  'mileage',
    'السنة':        'year',
    'اللون الخارجي':'exterior_color',
    'اللون الداخلي':'interior_color',
    'الوقود':       'fuel_type',
    'ناقل الحركة':  'transmission',
    'الغيار':       'transmission',
    'الحالة':       'condition',
    'المحرك':       'engine_size',
    'نوع الجسم':    'body_type',
    'نظام الدفع':   'drive_system',
    'الأبواب':      'doors',
    'السلندرات':    'cylinders',
    'رقم الهيكل':   'chassis_number',
    'الضمان':       'warranty',
    'حالة الهيكل':  'chassis_condition',
    'قوة الحصان':   'horsepower',
    'المقاعد':      'seats',
    'جهة القيادة':  'steering_side',
    'الوارد':       'origin',
}

COND_MAP  = {'used': 'مستعمل', 'new': 'جديد', 'damaged': 'متضرر'}
TRANS_MAP = {'automatic': 'أوتوماتيك', 'manual': 'مانيوال', 'cvt': 'CVT', 'dct': 'DCT'}
FUEL_MAP  = {'gasoline': 'بنزين', 'diesel': 'ديزل', 'electric': 'كهربائي',
             'hybrid': 'هايبرد', 'gas': 'غاز'}
BODY_MAP  = {'sedan': 'سيدان', 'suv': 'دفع رباعي', 'pickup': 'بيكاب',
             'hatchback': 'هاتشباك', 'coupe': 'كوبيه', 'wagon': 'ستيشن واغن',
             'van': 'فان', 'minivan': 'ميني فان', 'convertible': 'كشف',
             'truck': 'شاحنة', 'bus': 'باص'}
DRIVE_MAP = {'fwd': 'دفع أمامي', 'rwd': 'دفع خلفي', '4wd': 'دفع رباعي',
             'awd': 'دفع رباعي كامل', '4x4': 'دفع رباعي'}

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


def _looks_like_listing_array(obj: Any) -> bool:
    """Return True if obj looks like a page of car listings."""
    items = None
    if isinstance(obj, list):
        items = obj
    elif isinstance(obj, dict):
        for key in ('data', 'results', 'ads', 'items', 'records', 'listings'):
            if isinstance(obj.get(key), list):
                items = obj[key]
                break
    if not items or len(items) < 1:
        return False
    sample = items[0]
    if not isinstance(sample, dict):
        return False
    # Must have at least a few car-like keys
    car_keys = {'slug', 'title', 'price', 'id', 'make', 'brand', 'category',
                'mileage', 'year', 'condition', 'city', 'governorate'}
    return len(car_keys & set(sample.keys())) >= 2


def _extract_items(obj: Any) -> List[Dict]:
    if isinstance(obj, list):
        return obj
    if isinstance(obj, dict):
        for key in ('data', 'results', 'ads', 'items', 'records', 'listings'):
            if isinstance(obj.get(key), list):
                return obj[key]
    return []


def _extract_total(obj: Any) -> Optional[int]:
    if isinstance(obj, dict):
        for key in ('total', 'count', 'totalCount', 'total_count', 'totalItems'):
            v = obj.get(key)
            if isinstance(v, int):
                return v
    return None


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
    return {'last_page': 0, 'total_scraped': 0, 'full_scrape_done': False,
            'discovered_api': None}


def _save_progress(progress: Dict):
    tmp = PROGRESS_FILE + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as fh:
        json.dump(progress, fh, indent=2, ensure_ascii=False)
    os.replace(tmp, PROGRESS_FILE)


def _append_jsonl(record: Dict):
    with open(OUTPUT_FILE, 'a', encoding='utf-8') as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + '\n')


# ── Car parser ────────────────────────────────────────────────────────────────


def _parse_car(c: Dict, detail: Optional[Dict] = None) -> Dict:
    data: Dict = {
        'scraped_at': datetime.now().isoformat(),
        'source':     SOURCE,
    }

    lid  = str(c.get('id', '') or c.get('_id', '') or '').strip()
    slug = str(c.get('slug', '') or '').strip()
    data['listing_id'] = lid
    data['id']         = f'damazzle_{lid}' if lid else f'damazzle_{slug}'
    data['slug']       = slug

    # Build car_url from slug parts if possible
    # URL pattern: /motors/cars/{make}/{date}/{full-slug}
    if slug:
        data['car_url'] = f'{SITE_URL}/motors/cars/{slug}'
    else:
        data['car_url'] = ''

    title = _clean(c.get('title') or c.get('name', ''))
    data['ad_title']     = title
    data['listing_type'] = ('للإيجار'
                            if any(k in title for k in ('إيجار', 'ايجار', 'للإيجار'))
                            else 'للبيع')

    # Make from category or direct field
    cat = c.get('category', {}) or {}
    data['make'] = _clean(
        cat.get('name_ar') or cat.get('name') or c.get('make') or c.get('brand') or ''
    )

    # City from governorate or direct
    gov = c.get('governorate', {}) or {}
    data['city'] = _clean(
        gov.get('name_ar') or gov.get('name') or c.get('city') or ''
    )

    data['price']      = _parse_price(c.get('price'))
    data['date_added'] = _parse_date(
        c.get('createdAt') or c.get('created_at') or c.get('date_added')
    )

    # Featured attributes
    for attr in (c.get('featuredAttributes', []) or c.get('featured_attributes', []) or []):
        key   = str(attr.get('slug', '') or attr.get('key', '') or '').strip().lower()
        label = _clean(attr.get('name_ar') or attr.get('label_ar') or attr.get('name') or '')
        val   = _clean(
            attr.get('value_ar') or attr.get('value') or attr.get('val') or
            attr.get('display_value') or ''
        )
        field = SLUG_MAP.get(key) or LABEL_MAP.get(label)
        if field and not data.get(field):
            data[field] = val

    # All attributes at top level
    for attr in (c.get('attributes', []) or []):
        key   = str(attr.get('slug', '') or attr.get('key', '') or '').strip().lower()
        label = _clean(attr.get('name_ar') or attr.get('label_ar') or attr.get('name') or '')
        val   = _clean(
            attr.get('value_ar') or attr.get('value') or attr.get('val') or
            attr.get('display_value') or ''
        )
        field = SLUG_MAP.get(key) or LABEL_MAP.get(label)
        if field and not data.get(field):
            data[field] = val

    # Direct flat fields
    for src_key, field in (
        ('year', 'year'), ('model', 'model'), ('mileage', 'mileage'),
        ('color', 'exterior_color'), ('exterior_color', 'exterior_color'),
        ('interior_color', 'interior_color'), ('fuel_type', 'fuel_type'),
        ('transmission', 'transmission'), ('condition', 'condition'),
        ('engine_size', 'engine_size'), ('body_type', 'body_type'),
        ('drive_system', 'drive_system'), ('doors', 'doors'),
        ('cylinders', 'cylinders'), ('chassis_number', 'chassis_number'),
    ):
        if not data.get(field) and c.get(src_key):
            data[field] = _clean(str(c[src_key]))

    # Normalise
    for field, mapping in (
        ('condition',    COND_MAP),
        ('transmission', TRANS_MAP),
        ('fuel_type',    FUEL_MAP),
        ('body_type',    BODY_MAP),
        ('drive_system', DRIVE_MAP),
    ):
        if data.get(field):
            data[field] = _arabic(data[field], mapping)

    # Images (collected, not downloaded)
    images: List[str] = []
    for img in (c.get('images') or c.get('photos') or c.get('media') or []):
        src = (img.get('url') or img.get('src') or img.get('path') or img.get('image') or ''
               if isinstance(img, dict) else str(img)).strip()
        if src and src.startswith('http'):
            images.append(src)

    # Enrich from detail response
    if detail:
        dd = detail.get('data') or detail if isinstance(detail, dict) else {}

        if not data.get('model'):
            data['model'] = _clean(dd.get('model_ar') or dd.get('model') or '')
        if not data.get('description'):
            data['description'] = _clean(
                dd.get('description_ar') or dd.get('description') or ''
            )

        seller = dd.get('user', {}) or dd.get('seller', {}) or {}
        if not data.get('seller_name'):
            data['seller_name'] = _clean(
                seller.get('name') or seller.get('full_name') or ''
            )
        phones = dd.get('phones', []) or dd.get('contact_phones', []) or []
        if not data.get('phone') and phones:
            p = phones[0]
            data['phone'] = _clean(
                p.get('number') or p.get('phone') or ''
                if isinstance(p, dict) else str(p)
            )
        seller_ads = seller.get('totalAds') or seller.get('ads_count') or seller.get('total_ads')
        if seller_ads is not None:
            data['seller_listings'] = str(seller_ads)

        for attr in (dd.get('attributes', []) or dd.get('featuredAttributes', []) or []):
            key   = str(attr.get('slug', '') or attr.get('key', '') or '').strip().lower()
            label = _clean(attr.get('name_ar') or attr.get('label_ar') or attr.get('name') or '')
            val   = _clean(
                attr.get('value_ar') or attr.get('value') or attr.get('val') or
                attr.get('display_value') or ''
            )
            field = SLUG_MAP.get(key) or LABEL_MAP.get(label)
            if field and not data.get(field):
                data[field] = val

        # Detail images
        detail_imgs = dd.get('images') or dd.get('photos') or dd.get('media') or []
        if detail_imgs:
            images = []
            for img in detail_imgs:
                src = (img.get('url') or img.get('src') or img.get('path') or ''
                       if isinstance(img, dict) else str(img)).strip()
                if src and src.startswith('http'):
                    images.append(src)

    data['image_urls']  = images
    data['image_count'] = len(images)
    return data


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
        self._stop = False

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

    def _should_stop(self) -> bool:
        if self._stop:
            return True
        if self.deadline and datetime.now() >= self.deadline:
            logger.info('Time limit reached.')
            return True
        return False

    async def _fetch_page_via_browser(
        self, page: Page, page_num: int
    ) -> tuple[List[Dict], Optional[int], Optional[str]]:
        """
        Navigate to the search page and intercept the JSON API response.
        Returns (items, total_count, discovered_api_base).
        """
        url = f'{SEARCH_URL}?page={page_num}'
        captured: List[Dict] = []
        api_url_found: Optional[str] = None
        total_found: Optional[int] = None

        async def handle_response(response: Response):
            nonlocal api_url_found, total_found
            if response.status != 200:
                return
            ct = response.headers.get('content-type', '')
            if 'json' not in ct:
                return
            try:
                body = await response.json()
            except Exception:
                return
            if _looks_like_listing_array(body):
                items = _extract_items(body)
                if items:
                    captured.extend(items)
                    total_found = _extract_total(body) or total_found
                    api_url_found = response.url
                    logger.info(f'  Intercepted listing API: {response.url}')
                    logger.info(f'  Got {len(items)} items')

        page.on('response', handle_response)

        try:
            await page.goto(url, wait_until='networkidle', timeout=PAGE_TIMEOUT)
        except Exception:
            try:
                await page.goto(url, wait_until='domcontentloaded', timeout=PAGE_TIMEOUT)
                await asyncio.sleep(RESPONSE_WAIT)
            except Exception as exc:
                logger.error(f'  Page load failed: {exc}')

        page.remove_listener('response', handle_response)
        return captured, total_found, api_url_found

    async def _fetch_detail_via_browser(
        self, page: Page, car_url: str
    ) -> Optional[Dict]:
        """Navigate to car detail page and intercept the detail API response."""
        captured: Optional[Dict] = None

        async def handle_response(response: Response):
            nonlocal captured
            if response.status != 200:
                return
            ct = response.headers.get('content-type', '')
            if 'json' not in ct:
                return
            try:
                body = await response.json()
            except Exception:
                return
            # Detail response: a single car object (not an array)
            dd = body.get('data') if isinstance(body, dict) else None
            if not dd:
                dd = body if isinstance(body, dict) and (
                    body.get('id') or body.get('slug') or body.get('title')
                ) else None
            if dd:
                captured = body

        page.on('response', handle_response)
        try:
            await page.goto(car_url, wait_until='networkidle', timeout=PAGE_TIMEOUT)
        except Exception:
            try:
                await page.goto(car_url, wait_until='domcontentloaded', timeout=PAGE_TIMEOUT)
                await asyncio.sleep(RESPONSE_WAIT)
            except Exception as exc:
                logger.error(f'  Detail page load failed: {exc}')
        page.remove_listener('response', handle_response)
        return captured

    def _process_car(self, c: Dict, detail: Optional[Dict]) -> bool:
        lid    = str(c.get('id', '') or c.get('_id', '') or '').strip()
        slug   = str(c.get('slug', '') or '').strip()
        car_id = f'damazzle_{lid}' if lid else f'damazzle_{slug}'

        if car_id in self.existing_ids:
            return False

        try:
            data = _parse_car(c, detail)
        except Exception as exc:
            logger.error(f'  Parse error: {exc}')
            return False

        # Date filter
        if data.get('date_added'):
            if self.start_date and data['date_added'] < self.start_date:
                return False
            if self.end_date and data['date_added'] > self.end_date:
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
        asyncio.run(self._run_async())

    async def _run_async(self):
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

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            ctx     = await browser.new_context(
                user_agent=(
                    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                    'AppleWebKit/537.36 (KHTML, like Gecko) '
                    'Chrome/120.0.0.0 Safari/537.36'
                ),
                locale='ar-SY',
            )
            page = await ctx.new_page()

            total_new        = 0
            full_page_streak = 0
            pg               = start_page
            page_size        = 20
            grand_total: Optional[int] = None

            while True:
                if self._should_stop():
                    break

                logger.info(f'\n[Page {pg}]')
                items, total, _api = await self._fetch_page_via_browser(page, pg)

                if total and not grand_total:
                    grand_total = total
                    logger.info(f'  Total listings reported by API: {grand_total}')

                if not items:
                    logger.info('  No items received — stopping.')
                    if self.full_mode:
                        progress['full_scrape_done'] = True
                        _save_progress(progress)
                    break

                # Date stop check (stop when all items are before start_date)
                if self.start_date:
                    dated = [
                        _parse_date(it.get('createdAt') or it.get('created_at', ''))
                        for it in items
                        if _parse_date(it.get('createdAt') or it.get('created_at', ''))
                    ]
                    if dated and all(d < self.start_date for d in dated):
                        logger.info(f'  All before {self.start_date} — done.')
                        break

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
                        progress['last_page'] = pg
                        _save_progress(progress)
                    await asyncio.sleep(REQUEST_DELAY)
                    pg += 1
                    continue

                full_page_streak = 0

                for it in new_items:
                    if self._should_stop():
                        if self.full_mode:
                            progress['last_page'] = pg - 1
                            _save_progress(progress)
                        break

                    slug = str(it.get('slug', '') or '').strip()
                    lid  = str(it.get('id', '') or '').strip()
                    logger.info(f'  → {slug or lid}')

                    # Fetch detail page for this car
                    detail = None
                    if slug:
                        car_url = f'{SITE_URL}/motors/cars/{slug}'
                        detail  = await self._fetch_detail_via_browser(page, car_url)
                        await asyncio.sleep(REQUEST_DELAY)

                    ok = self._process_car(it, detail)
                    if ok:
                        total_new += 1
                        progress['total_scraped'] += 1

                    await asyncio.sleep(0.5)
                else:
                    if self.full_mode:
                        progress['last_page'] = pg
                        _save_progress(progress)

                if self._should_stop():
                    break

                if grand_total and pg * page_size >= grand_total:
                    logger.info('  All pages scraped.')
                    if self.full_mode:
                        progress['full_scrape_done'] = True
                        _save_progress(progress)
                    break

                await asyncio.sleep(REQUEST_DELAY)
                pg += 1

            await browser.close()

        logger.info('\n' + '=' * 62)
        logger.info(f'Done. {total_new} cars → sheet + {OUTPUT_FILE}')
        logger.info('=' * 62)


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Damazzle raw data scraper (Playwright)')
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

    scraper = DamazzleRawScraper(
        full_mode=args.full,
        max_hours=args.hours,
        start_date=args.start_date,
        end_date=args.end_date,
    )

    def _sig(s, f):
        scraper._stop = True

    signal.signal(signal.SIGINT,  _sig)
    signal.signal(signal.SIGTERM, _sig)

    scraper.run()
