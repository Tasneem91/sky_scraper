#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Damazzle Raw Data Scraper
=========================
Writes each car to:
  • rawdata_damazzle.jsonl  (local backup)
  • Google Sheet: damazzle_raw_data

Strategy
--------
Page 1 → Playwright browser intercepts the real listing API URL.
Pages 2+ → requests calls that URL directly (faster, per_page=20).
Detail pages → Playwright intercepts the single-car JSON response.

No images downloaded. No quality gate.
Requires: pip install playwright && playwright install chromium

USAGE
-----
  python rawdata_damazzle.py --full
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
from urllib.parse import urlencode, urlparse, parse_qs, urlunparse

import requests as req_lib

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

SITE_URL        = 'https://damazzle.com'
SEARCH_URL      = 'https://damazzle.com/motors/cars/search'
SOURCE          = 'damazzle'
PER_PAGE        = 20        # requested from API; site default is 8
PAGE_TIMEOUT    = 30_000    # ms
RESPONSE_WAIT   = 8.0       # seconds to wait after page load
REQUEST_DELAY   = 1.5       # seconds between requests
STOP_FULL_PAGES = 3         # incremental mode: stop after N all-seen pages

# Substring that identifies the listing API (not categories, not static)
LISTING_API_MARKER = 'search/ads'

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
    # Labels as they appear in the API attribute name_ar
    'الكيلومتراج':        'mileage',
    'المسافة المقطوعة':   'mileage',   # shown on page
    'السنة':              'year',
    'سنة الصنع':          'year',       # shown on page
    'اللون الخارجي':      'exterior_color',
    'اللون':              'exterior_color',  # shown on page (short form)
    'اللون الداخلي':      'interior_color',
    'الوقود':             'fuel_type',
    'نوع الوقود':         'fuel_type',   # shown on page
    'ناقل الحركة':        'transmission',
    'الغيار':             'transmission',
    'الحالة':             'condition',
    'الشروط':             'condition',   # shown on page
    'المحرك':             'engine_size',
    'نوع الجسم':          'body_type',
    'نظام الدفع':         'drive_system',
    'نوع الدفع':          'drive_system',
    'الأبواب':            'doors',
    'عدد الأبواب':        'doors',
    'السلندرات':          'cylinders',
    'عدد السلندرات':      'cylinders',
    'رقم الهيكل':         'chassis_number',
    'الضمان':             'warranty',
    'حالة الهيكل':        'chassis_condition',
    'قوة الحصان':         'horsepower',
    'المقاعد':            'seats',
    'عدد المقاعد':        'seats',      # shown on page
    'جهة القيادة':        'steering_side',
    'الوارد':             'origin',
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


def _is_listing_response(url: str, body: Any) -> bool:
    """True only if this is a car-listing API response (not categories etc.)."""
    if LISTING_API_MARKER not in url:
        return False
    items = _extract_items(body)
    if not items:
        return False
    sample = items[0]
    if not isinstance(sample, dict):
        return False
    # Must have price (categories never have price)
    return 'price' in sample or 'published_date' in sample


def _extract_items(body: Any) -> List[Dict]:
    if isinstance(body, list):
        return body
    if isinstance(body, dict):
        for key in ('data', 'results', 'ads', 'items', 'records', 'listings'):
            val = body.get(key)
            if isinstance(val, list):
                return val
    return []


def _extract_total(body: Any) -> Optional[int]:
    if isinstance(body, dict):
        for key in ('total', 'count', 'totalCount', 'total_count', 'meta'):
            v = body.get(key)
            if isinstance(v, int):
                return v
            if isinstance(v, dict):
                for k2 in ('total', 'count', 'totalItems'):
                    if isinstance(v.get(k2), int):
                        return v[k2]
    return None


def _build_page_url(base_url: str, page: int, per_page: int = PER_PAGE) -> str:
    """Replace page/per_page params in a discovered API URL."""
    parsed = urlparse(base_url)
    params = parse_qs(parsed.query, keep_blank_values=True)
    params['page']     = [str(page)]
    params['per_page'] = [str(per_page)]
    # Flatten lists for urlencode
    flat = []
    for k, vals in params.items():
        for v in vals:
            flat.append((k, v))
    new_query = urlencode(flat)
    return urlunparse(parsed._replace(query=new_query))


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
    return {
        'last_page': 0,
        'total_scraped': 0,
        'full_scrape_done': False,
        'listing_api_url': None,   # discovered on first run
    }


def _save_progress(p: Dict):
    tmp = PROGRESS_FILE + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as fh:
        json.dump(p, fh, indent=2, ensure_ascii=False)
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
    data['car_url']    = f'{SITE_URL}/motors/cars/{slug}' if slug else ''

    title = _clean(c.get('title') or c.get('name', ''))
    data['ad_title']     = title
    data['listing_type'] = ('للإيجار'
                            if any(k in title for k in ('إيجار', 'ايجار', 'للإيجار'))
                            else 'للبيع')

    cat = c.get('category', {}) or {}
    data['make'] = _clean(
        cat.get('name_ar') or cat.get('name') or c.get('make') or c.get('brand') or ''
    )
    gov = c.get('governorate', {}) or {}
    data['city'] = _clean(
        gov.get('name_ar') or gov.get('name') or c.get('city') or ''
    )
    data['price']      = _parse_price(c.get('price'))
    data['date_added'] = _parse_date(
        c.get('createdAt') or c.get('created_at') or c.get('published_date') or
        c.get('date_added')
    )

    def _apply_attrs(attrs):
        for attr in (attrs or []):
            if not isinstance(attr, dict):
                continue
            key   = str(attr.get('slug', '') or attr.get('key', '') or '').strip().lower()
            label = _clean(attr.get('name_ar') or attr.get('label_ar') or attr.get('name') or '')
            val   = _clean(
                attr.get('value_ar') or attr.get('value') or attr.get('val') or
                attr.get('display_value') or ''
            )
            field = SLUG_MAP.get(key) or LABEL_MAP.get(label)
            if field and not data.get(field):
                data[field] = val

    _apply_attrs(c.get('featuredAttributes') or c.get('featured_attributes') or [])
    _apply_attrs(c.get('attributes') or [])

    # Direct flat fields as fallback
    for src, dst in (
        ('year', 'year'), ('model', 'model'), ('mileage', 'mileage'),
        ('color', 'exterior_color'), ('exterior_color', 'exterior_color'),
        ('interior_color', 'interior_color'), ('fuel_type', 'fuel_type'),
        ('transmission', 'transmission'), ('condition', 'condition'),
        ('engine_size', 'engine_size'), ('body_type', 'body_type'),
        ('drive_system', 'drive_system'), ('doors', 'doors'),
        ('cylinders', 'cylinders'), ('chassis_number', 'chassis_number'),
    ):
        if not data.get(dst) and c.get(src):
            data[dst] = _clean(str(c[src]))

    for field, mapping in (
        ('condition',    COND_MAP),
        ('transmission', TRANS_MAP),
        ('fuel_type',    FUEL_MAP),
        ('body_type',    BODY_MAP),
        ('drive_system', DRIVE_MAP),
    ):
        if data.get(field):
            data[field] = _arabic(data[field], mapping)

    images: List[str] = []
    for img in (c.get('images') or c.get('photos') or c.get('media') or []):
        src = (img.get('url') or img.get('src') or img.get('path') or ''
               if isinstance(img, dict) else str(img)).strip()
        if src and src.startswith('http'):
            images.append(src)

    # Enrich from detail — detail must be a dict, data key must also be a dict
    if isinstance(detail, dict):
        data_val = detail.get('data')
        if isinstance(data_val, dict):
            dd = data_val
        elif data_val is None:
            # detail IS the car object directly
            dd = detail if (detail.get('id') or detail.get('slug') or detail.get('title')) else {}
        else:
            dd = {}   # data is a list or something unexpected — skip

        if dd:
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
            seller_ads = seller.get('totalAds') or seller.get('ads_count')
            if seller_ads is not None:
                data['seller_listings'] = str(seller_ads)

            _apply_attrs(dd.get('attributes') or dd.get('featuredAttributes') or [])

            detail_imgs = dd.get('images') or dd.get('photos') or dd.get('media') or []
            if detail_imgs:
                imgs2 = []
                for img in detail_imgs:
                    src = (img.get('url') or img.get('src') or img.get('path') or ''
                           if isinstance(img, dict) else str(img)).strip()
                    if src and src.startswith('http'):
                        imgs2.append(src)
                if imgs2:
                    images = imgs2

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

        # HTTP session for direct API calls (once URL is discovered)
        self.http = req_lib.Session()
        self.http.headers.update({
            'User-Agent': (
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                'AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/120.0.0.0 Safari/537.36'
            ),
            'Accept': 'application/json',
            'Origin': SITE_URL,
            'Referer': SEARCH_URL,
        })

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

    def _sheet_append(self, data: Dict):
        row = [_to_cell(data.get(col)) for col in COLUMNS]
        self.sheet.append_row(row, value_input_option='RAW')

    def _should_stop(self) -> bool:
        if self._stop:
            return True
        if self.deadline and datetime.now() >= self.deadline:
            logger.info('Time limit reached.')
            return True
        return False

    # ── Playwright helpers ────────────────────────────────────────────────────

    async def _playwright_listing_page(
        self, page: Page, page_num: int
    ) -> tuple[List[Dict], Optional[int], Optional[str]]:
        """Navigate to search page; intercept ONLY the listing API response."""
        url      = f'{SEARCH_URL}?page={page_num}'
        items    : List[Dict]    = []
        total    : Optional[int] = None
        api_url  : Optional[str] = None

        async def on_response(resp: Response):
            nonlocal items, total, api_url
            if resp.status != 200:
                return
            if 'json' not in resp.headers.get('content-type', ''):
                return
            try:
                body = await resp.json()
            except Exception:
                return
            if _is_listing_response(resp.url, body):
                found = _extract_items(body)
                if found:
                    items   = found
                    total   = _extract_total(body) or total
                    api_url = resp.url
                    logger.info(f'  Listing API: {resp.url}')
                    logger.info(f'  {len(found)} items, total={total}')

        page.on('response', on_response)
        try:
            await page.goto(url, wait_until='networkidle', timeout=PAGE_TIMEOUT)
        except Exception:
            try:
                await page.goto(url, wait_until='domcontentloaded', timeout=PAGE_TIMEOUT)
                await asyncio.sleep(RESPONSE_WAIT)
            except Exception as exc:
                logger.error(f'  Page load error: {exc}')
        page.remove_listener('response', on_response)
        return items, total, api_url

    async def _playwright_detail_page(
        self, page: Page, car_url: str
    ) -> tuple[Optional[Dict], Dict]:
        """
        Navigate to car detail page.
        Returns (api_response, dom_data) where dom_data has phone, seller_name etc.
        extracted directly from the rendered HTML (more reliable than API for contacts).
        """
        captured: Optional[Dict] = None

        async def on_response(resp: Response):
            nonlocal captured
            if resp.status != 200:
                return
            if 'json' not in resp.headers.get('content-type', ''):
                return
            url_lower = resp.url.lower()
            if any(x in url_lower for x in ('search', 'categor', 'storage', 'static')):
                return
            try:
                body = await resp.json()
            except Exception:
                return
            if not isinstance(body, dict):
                return
            data_val = body.get('data')
            if isinstance(data_val, dict) and (
                data_val.get('id') or data_val.get('slug') or data_val.get('title')
            ):
                captured = body
            elif data_val is None and (
                body.get('id') or body.get('slug') or body.get('title')
            ):
                captured = body

        page.on('response', on_response)
        try:
            await page.goto(car_url, wait_until='networkidle', timeout=PAGE_TIMEOUT)
        except Exception:
            try:
                await page.goto(car_url, wait_until='domcontentloaded', timeout=PAGE_TIMEOUT)
                await asyncio.sleep(RESPONSE_WAIT)
            except Exception as exc:
                logger.error(f'  Detail page error: {exc}')
        page.remove_listener('response', on_response)

        # ── Extract from rendered DOM ────────────────────────────────────────
        dom: Dict = {}
        try:
            # Phone from tel: link (the "اتصل الآن" button)
            for sel in ['a.btn-call[href^="tel:"]', 'a[href^="tel:"]', 'a[href*="tel:"]']:
                els = await page.query_selector_all(sel)
                for el in els:
                    href = (await el.get_attribute('href') or '').strip()
                    if href.startswith('tel:'):
                        dom['phone'] = href.replace('tel:', '').strip()
                        break
                if dom.get('phone'):
                    break

            # WhatsApp number as fallback phone
            if not dom.get('phone'):
                for el in await page.query_selector_all('a[href*="wa.me"]'):
                    href = await el.get_attribute('href') or ''
                    m = re.search(r'wa\.me/(\+?[\d]+)', href)
                    if m:
                        dom['phone'] = m.group(1)
                        break

            # Seller name — Damazzle uses .sideauthor-info p.fw-bold
            for sel in [
                '.sideauthor-info p.fw-bold',
                '.sideauthor-info .fw-bold',
                '.sideauthor-info p',
                'a[href*="/seller/"] .fw-bold',
                'a[href*="/seller/"] p',
            ]:
                try:
                    el = await page.query_selector(sel)
                    if el:
                        txt = (await el.inner_text()).strip()
                        if txt and len(txt) > 1 and 'نشر' not in txt and 'Joined' not in txt:
                            dom['seller_name'] = txt
                            break
                except Exception:
                    pass

            # Spec key-value pairs from rendered DOM
            # Structure: .col-6.col-md-4 (has <p> label) + sibling .col-6.col-md-8 (value)
            try:
                specs_raw: Dict = await page.evaluate("""() => {
                    const result = {};
                    const labelDivs = document.querySelectorAll(
                        '.col-6.col-md-4.text-muted.fw-bold'
                    );
                    for (const div of labelDivs) {
                        const p = div.querySelector('p');
                        if (!p) continue;
                        const label = p.textContent.trim();
                        const valueDiv = div.nextElementSibling;
                        if (!valueDiv) continue;
                        const value = valueDiv.textContent.trim();
                        if (label && value) result[label] = value;
                    }
                    return result;
                }""")
                if isinstance(specs_raw, dict) and specs_raw:
                    dom['specs_raw'] = specs_raw
                    logger.debug(f'  DOM specs: {specs_raw}')
            except Exception as exc:
                logger.debug(f'  DOM spec extraction error: {exc}')

            # Price (sometimes only in DOM)
            if not dom.get('price'):
                for sel in ['[class*="price"]', '[class*="Price"]']:
                    try:
                        el = await page.query_selector(sel)
                        if el:
                            txt = (await el.inner_text()).strip()
                            digits = re.sub(r'[^\d.]', '', txt.replace(',', ''))
                            if digits:
                                dom['price'] = digits
                                break
                    except Exception:
                        pass

        except Exception as exc:
            logger.debug(f'  DOM extraction error: {exc}')

        return captured, dom

    # ── Direct HTTP helper (once URL is known) ────────────────────────────────

    def _direct_listing_page(
        self, listing_api_url: str, page_num: int
    ) -> tuple[List[Dict], Optional[int]]:
        url = _build_page_url(listing_api_url, page_num, PER_PAGE)
        try:
            resp = self.http.get(url, timeout=30)
            resp.raise_for_status()
            body = resp.json()
            items = _extract_items(body)
            total = _extract_total(body)
            logger.info(f'  Direct API → {len(items)} items, total={total}')
            return items, total
        except Exception as exc:
            logger.error(f'  Direct API error: {exc}')
            return [], None

    # ── Car processing ────────────────────────────────────────────────────────

    def _process_car(self, c: Dict, detail: Optional[Dict], dom: Dict) -> bool:
        lid    = str(c.get('id', '') or c.get('_id', '') or '').strip()
        slug   = str(c.get('slug', '') or '').strip()
        car_id = f'damazzle_{lid}' if lid else f'damazzle_{slug}'

        if car_id in self.existing_ids:
            return False

        date_added = _parse_date(
            c.get('createdAt') or c.get('created_at') or c.get('published_date', '')
        )
        if date_added:
            if self.start_date and date_added < self.start_date:
                return False
            if self.end_date and date_added > self.end_date:
                return False

        try:
            data = _parse_car(c, detail)
        except Exception as exc:
            logger.error(f'  Parse error ({car_id}): {exc}')
            return False

        # Merge DOM-extracted fields as fallbacks
        if dom.get('phone') and not data.get('phone'):
            data['phone'] = dom['phone']
        if dom.get('seller_name') and not data.get('seller_name'):
            data['seller_name'] = dom['seller_name']
        if dom.get('price') and not data.get('price'):
            data['price'] = dom['price']

        # Apply DOM-extracted spec pairs (Arabic label → field) as fallbacks
        for arabic_label, raw_value in (dom.get('specs_raw') or {}).items():
            field = LABEL_MAP.get(arabic_label.strip())
            if field and not data.get(field):
                data[field] = _clean(raw_value)

        try:
            self._sheet_append(data)
            _append_jsonl(data)
            self.existing_ids.add(car_id)
            logger.info(f'  ✓  {data.get("ad_title", car_id)!r}  phone={data.get("phone","-")}')
            return True
        except Exception as exc:
            logger.error(f'  Write failed: {exc}')
            return False

    # ── Main loop ─────────────────────────────────────────────────────────────

    def run(self):
        asyncio.run(self._run_async())

    async def _run_async(self):
        progress = self.progress

        if self.full_mode:
            if progress.get('full_scrape_done'):
                logger.info('Full scrape complete. Delete progress file to restart.')
                return
            start_page = progress['last_page'] + 1
            logger.info(f'Full scrape mode — resuming from page {start_page}')
        else:
            start_page = 1
            logger.info('Incremental mode — starting from page 1')

        logger.info('=' * 62)
        logger.info(f'Damazzle raw scraper  {datetime.now().isoformat()}')
        logger.info('=' * 62)

        listing_api_url: Optional[str] = progress.get('listing_api_url')

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
            bpage = await ctx.new_page()

            total_new     = 0
            streak        = 0
            pg            = start_page
            grand_total   : Optional[int] = None

            while True:
                if self._should_stop():
                    break

                logger.info(f'\n[Page {pg}]')

                # Use browser for page 1 (to discover API URL), requests after
                if listing_api_url and pg > 1:
                    items, total = self._direct_listing_page(listing_api_url, pg)
                else:
                    items, total, found_url = await self._playwright_listing_page(bpage, pg)
                    if found_url and not listing_api_url:
                        listing_api_url = found_url
                        progress['listing_api_url'] = found_url
                        logger.info(f'  API URL saved: {found_url}')
                        _save_progress(progress)

                if total and not grand_total:
                    grand_total = total

                if not items:
                    logger.info('  No items — stopping.')
                    if self.full_mode:
                        progress['full_scrape_done'] = True
                        _save_progress(progress)
                    break

                # Stop if all items are before start_date
                if self.start_date:
                    dated = [
                        _parse_date(it.get('createdAt') or it.get('published_date', ''))
                        for it in items
                        if _parse_date(it.get('createdAt') or it.get('published_date', ''))
                    ]
                    if dated and all(d < self.start_date for d in dated):
                        logger.info(f'  All before {self.start_date} — done.')
                        break

                new_items = [
                    it for it in items
                    if (f"damazzle_{it.get('id', '')}"   not in self.existing_ids
                        and f"damazzle_{it.get('slug', '')}" not in self.existing_ids)
                ]
                logger.info(f'  {len(items)} on page | {len(new_items)} new')

                if not new_items:
                    if not self.full_mode:
                        streak += 1
                        if streak >= STOP_FULL_PAGES:
                            logger.info('  Caught up — stopping.')
                            break
                    else:
                        progress['last_page'] = pg
                        _save_progress(progress)
                    await asyncio.sleep(REQUEST_DELAY)
                    pg += 1
                    continue

                streak = 0

                for it in new_items:
                    if self._should_stop():
                        if self.full_mode:
                            progress['last_page'] = pg - 1
                            _save_progress(progress)
                        break

                    slug = str(it.get('slug', '') or '').strip()
                    lid  = str(it.get('id',   '') or '').strip()
                    logger.info(f'  → {slug or lid}')

                    detail, dom = None, {}
                    if slug:
                        car_url        = f'{SITE_URL}/motors/cars/{slug}'
                        detail, dom    = await self._playwright_detail_page(bpage, car_url)
                        await asyncio.sleep(REQUEST_DELAY)

                    ok = self._process_car(it, detail, dom)
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

                if grand_total and pg * PER_PAGE >= grand_total:
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
