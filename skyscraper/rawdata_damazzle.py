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
from typing import Any, Dict, List, Optional, Set
from urllib.parse import urlencode, urlparse, parse_qs, urlunparse

import requests as req_lib
from bs4 import BeautifulSoup

import gspread
from google.auth.transport.requests import Request
from google.oauth2 import credentials as google_creds_module
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build as google_build
from googleapiclient.http import MediaIoBaseUpload
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

SHEET_ID = '1X31PStrK7lqjdfj2Hy9hypFO4IO7wo_vh49nONSqL-Y'

SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive',
]

SITE_URL          = 'https://damazzle.com'
SEARCH_URL        = 'https://damazzle.com/motors/cars/search'
SOURCE            = 'damazzle'
API_DETAIL_BASE   = 'https://beta.damazzletech.com/api/api/v1/ads/details-by-slug'
PER_PAGE          = 20        # requested from API; site default is 8
PAGE_TIMEOUT      = 30_000    # ms
RESPONSE_WAIT     = 8.0       # seconds to wait after page load
REQUEST_DELAY     = 1.5       # seconds between requests
STOP_FULL_PAGES   = 3         # incremental mode: stop after N all-seen pages

# Substring that identifies the listing API (not categories, not static)
LISTING_API_MARKER = 'search/ads'

DEWATERMARK_URL    = 'https://platform.dewatermark.ai/api/object_removal/v2/erase_watermark'
DRIVE_FOLDER_ID    = '1JrEXZVNlfL54Z22lRWtEDHkT4mnVNCIf'
MIN_YEAR           = 2015

# ── Sheet columns ─────────────────────────────────────────────────────────────

COLUMNS: List[str] = [
    'id', 'source', 'car_url', 'listing_id', 'slug',
    'ad_title', 'listing_type',
    'make', 'model', 'year', 'condition',
    'exterior_color',
    'fuel_type', 'engine_size', 'transmission',
    'city', 'mileage', 'price',
    'date_added', 'scraped_at',
    'phone', 'seller_name',
    'description',
    'cover_image_url', 'image_clean_link',
]

# ── Field maps ────────────────────────────────────────────────────────────────

SLUG_MAP: Dict[str, str] = {
    # API slugs from details-by-slug endpoint (confirmed from damazzle_standalone.py)
    'traveled_distance':    'mileage',
    'year_of_manufacture':  'year',
    'color':                'exterior_color',
    'Color':                'exterior_color',
    'exterior_color':       'exterior_color',
    'interior_color':       'interior_color',
    'fuel_type':            'fuel_type',
    'Fuel_type':            'fuel_type',
    'transmission':         'transmission',
    'Transmission':         'transmission',
    'gearbox':              'transmission',
    'condition':            'condition',
    'Condition':            'condition',
    'car_condition':        'condition',
    'engine_capacity':      'engine_size',
    'engine':               'engine_size',
    'body_type':            'body_type',
    'drive_system':         'drive_system',
    'drive_type':           'drive_system',
    'doors':                'doors',
    'cylinders':            'cylinders',
    'vin':                  'chassis_number',
    'chassis':              'chassis_number',
    # Fallback simple slugs (may appear in featured_fields)
    'mileage':              'mileage',
    'year':                 'year',
    'engine_size':          'engine_size',
    'chassis_number':       'chassis_number',
    'warranty':             'warranty',
    'chassis_condition':    'chassis_condition',
    'horsepower':           'horsepower',
    'seats':                'seats',
    'steering_side':        'steering_side',
    'origin':               'origin',
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
    'المحرك':                   'engine_size',
    'سعة المحرك':              'engine_size',
    'سعة المحرك(سي سي)':      'engine_size',
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

# ── Title parsing: make/model extraction ──────────────────────────────────────

# Multi-word Arabic makes — longer entries first so they match before their prefix
_MULTI_WORD_MAKES = [
    'بي ام دبليو',    # BMW
    'جي ام سي',       # GMC
    'رانج روفر',      # Range Rover
    'لاند روفر',      # Land Rover
    'رولز رويس',      # Rolls Royce
    'أستون مارتن',    # Aston Martin
    'ألفا روميو',     # Alfa Romeo
    'مان تراك',       # MAN
]

# Title prefixes stripped before parsing
_TITLE_PREFIXES = [
    'للبيع سيارة', 'للإيجار سيارة', 'سيارة للبيع',
    'سيارة للإيجار', 'للبيع', 'للإيجار', 'سيارة',
]

# Trailing words that describe condition/status, not model
_TITLE_TRAIL = {'زيرو', 'جديد', 'جديدة', 'مستعمل', 'مستعملة', 'مشابه'}

# Makes that the API returns as "unknown" — trigger title fallback
_BAD_MAKES = {'أخرى', 'أخري', 'اخرى', 'اخري', 'غير محدد', 'غير_محدد', 'other', 'Other', '-'}

# Same set used to replace "أخرى" with "غير ذلك" in non-make fields
_AKHRY = {'أخرى', 'أخري', 'اخرى', 'اخري'}

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


def _strip_km(text: str) -> str:
    """Remove Arabic 'كم' suffix and any surrounding whitespace."""
    return re.sub(r'\s*كم\s*$', '', str(text).strip()).strip()


def _strip_cc(text: str) -> str:
    """Remove Arabic 'سي سي' (cc) suffix from engine size strings."""
    return re.sub(r'\s*سي\s+سي\s*$', '', str(text).strip()).strip()


def _clean_year(text: str) -> str:
    """Extract a 4-digit year (1900-2099). Returns '' if nothing valid found."""
    m = re.search(r'\b(19\d{2}|20\d{2})\b', str(text))
    return m.group(1) if m else ''


def _clean_model_str(model: str) -> str:
    """Strip trailing year and condition words from a raw model string."""
    model = re.sub(r'\s+\d{4}\s*$', '', model).strip()
    words = model.split()
    while words and words[-1] in _TITLE_TRAIL:
        words.pop()
    return ' '.join(words)


def _parse_title(title: str):
    """Return (make, model) extracted from a Damazzle Arabic ad title."""
    text = title.strip()
    for prefix in _TITLE_PREFIXES:
        if text.startswith(prefix):
            text = text[len(prefix):].strip()
            break
    if ' في ' in text:
        text = text[:text.index(' في ')].strip()
    text = _clean_model_str(text)
    if not text:
        return '', ''
    # Check known multi-word makes first (longest match)
    for make in _MULTI_WORD_MAKES:
        if text.startswith(make):
            model = _clean_model_str(text[len(make):].strip())
            return make, model
    # Default: first whitespace-delimited token = make
    parts = text.split(None, 1)
    make  = parts[0]
    model = _clean_model_str(parts[1]) if len(parts) > 1 else ''
    return make, model


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


def _parse_car(c: Dict) -> Dict:
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
        """Handle both flat {slug, name_ar, value_ar} and nested {template_field, value} structures."""
        for attr in (attrs or []):
            if not isinstance(attr, dict):
                continue
            # Nested structure from details-by-slug: {template_field: {slug, field_name_ar}, value: {ar}}
            tf = attr.get('template_field')
            if isinstance(tf, dict):
                key   = str(tf.get('slug', '') or '').strip()
                label = _clean(tf.get('field_name_ar') or tf.get('name_ar') or '')
                val_obj = attr.get('value') or {}
                val   = _clean(
                    val_obj.get('ar') or val_obj.get('en') or ''
                    if isinstance(val_obj, dict) else str(val_obj)
                )
            else:
                # Flat structure from featured_fields / attributes
                key   = str(attr.get('slug', '') or attr.get('key', '') or '').strip()
                label = _clean(attr.get('name_ar') or attr.get('label_ar') or attr.get('name') or '')
                val   = _clean(
                    attr.get('value_ar') or attr.get('value') or attr.get('val') or
                    attr.get('display_value') or ''
                )
            if not val or val in ('غير محدد', 'غير_محدد', '-', ''):
                continue
            field = SLUG_MAP.get(key) or LABEL_MAP.get(label)
            if field and not data.get(field):
                data[field] = val

    # detail_fields from details-by-slug come first (most complete), then featured_fields
    _apply_attrs(c.get('_detail_fields') or [])
    _apply_attrs(c.get('featured_fields') or c.get('featuredAttributes') or c.get('featured_attributes') or [])
    _apply_attrs(c.get('attributes') or [])

    # Phone: listing API has it at top level (car.phone / car.whatsapp)
    if not data.get('phone'):
        phone    = _clean(str(c.get('phone')    or ''))
        whatsapp = _clean(str(c.get('whatsapp') or ''))
        if phone and phone not in ('None', 'null', '0'):
            data['phone'] = phone
        elif whatsapp and whatsapp not in ('None', 'null', '0'):
            data['phone'] = whatsapp

    # Seller: listing API has it at car.customer.name
    if not data.get('seller_name'):
        customer = c.get('customer') or c.get('created_by') or {}
        if isinstance(customer, dict):
            data['seller_name'] = _clean(
                customer.get('name') or customer.get('full_name') or ''
            )
            seller_ads = customer.get('totalAds') or customer.get('ads_count')
            if seller_ads is not None:
                data['seller_listings'] = str(seller_ads)

    # Model — try structured fields first
    if not data.get('model'):
        data['model'] = _clean(c.get('model_ar') or c.get('model') or '')

    # Make/model from title — used when API category is "أخرى" or blank
    if not data.get('make') or data['make'] in _BAD_MAKES:
        t_make, t_model = _parse_title(title)
        if t_make:
            data['make'] = t_make
        if not data.get('model') and t_model:
            data['model'] = t_model
    elif not data.get('model'):
        _, t_model = _parse_title(title)
        if t_model:
            data['model'] = t_model

    # Description
    if not data.get('description'):
        data['description'] = _clean(
            c.get('description_ar') or c.get('description') or ''
        )

    # Direct flat fields as fallback
    for src, dst in (
        ('year', 'year'), ('color', 'exterior_color'),
        ('exterior_color', 'exterior_color'), ('interior_color', 'interior_color'),
        ('fuel_type', 'fuel_type'), ('transmission', 'transmission'),
        ('condition', 'condition'), ('engine_size', 'engine_size'),
        ('body_type', 'body_type'), ('drive_system', 'drive_system'),
        ('doors', 'doors'), ('cylinders', 'cylinders'),
        ('chassis_number', 'chassis_number'), ('mileage', 'mileage'),
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

    # Clean year: extract 4-digit number only (handles "قبل 2000", ranges, etc.)
    if data.get('year'):
        data['year'] = _clean_year(data['year'])

    # Clean mileage: strip "كم" suffix
    if data.get('mileage'):
        data['mileage'] = _strip_km(data['mileage'])

    # Clean engine_size: strip "سي سي" unit suffix
    if data.get('engine_size'):
        data['engine_size'] = _strip_cc(data['engine_size'])

    # Clean model: strip leaked city info like "في دمشق" or "في ريف دمشق"
    if data.get('model'):
        m = data['model'].strip()
        if ' في ' in m:
            m = m[:m.index(' في ')].strip()
        if re.match(r'^في\s', m):
            m = ''
        data['model'] = m

    # Replace "أخرى" with "غير ذلك" in all non-make fields
    for _f in ('condition', 'exterior_color', 'fuel_type', 'engine_size',
               'transmission', 'body_type', 'drive_system', 'city',
               'listing_type', 'model'):
        if data.get(_f) in _AKHRY:
            data[_f] = 'غير ذلك'

    return data


# ── Scraper ───────────────────────────────────────────────────────────────────


class DamazzleRawScraper:

    def __init__(
        self,
        full_mode: bool = False,
        max_hours: Optional[float] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        dewatermark_key: Optional[str] = None,
    ):
        self.full_mode       = full_mode
        self.start_date      = start_date
        self.end_date        = end_date
        self.dewatermark_key = dewatermark_key
        self.deadline: Optional[datetime] = (
            datetime.now() + timedelta(hours=max_hours) if max_hours else None
        )
        self._stop = False

        logger.info('Authenticating with Google APIs …')
        creds      = _get_oauth_credentials()
        self.gc    = gspread.authorize(creds)
        self.sheet = self.gc.open_by_key(SHEET_ID).sheet1

        # Google Drive service (for image uploads)
        self.drive_svc = None
        try:
            self.drive_svc = google_build('drive', 'v3', credentials=creds)
            logger.info('Google Drive service initialized.')
        except Exception as exc:
            logger.warning(f'Could not initialize Drive service: {exc}')

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

    # ── Details-by-slug API (full structured specs) ──────────────────────────

    def _fetch_detail_fields(self, slug: str) -> List[Dict]:
        """
        GET /api/v1/ads/details-by-slug/{slug}
        Returns data.ad.fields — the FULL set of معلومات اضافية specs.
        The listing API only returns 2 featured_fields; this has everything.
        """
        if not slug:
            return []
        # Use just the final slug segment (strip make/date prefix if present)
        ad_slug = slug.split('/')[-1] if '/' in slug else slug
        try:
            r = self.http.get(f'{API_DETAIL_BASE}/{ad_slug}', timeout=15)
            if r.status_code != 200:
                logger.debug(f'  detail-by-slug {ad_slug}: HTTP {r.status_code}')
                return []
            body = r.json()
            ad = (body.get('data') or {}).get('ad') or {}
            fields = ad.get('fields') or []
            logger.debug(f'  detail-by-slug {ad_slug}: {len(fields)} fields')
            return fields
        except Exception as exc:
            logger.debug(f'  detail-by-slug error ({ad_slug}): {exc}')
            return []

    # ── BS4 detail fetcher (SSR endpoint) ────────────────────────────────────

    def _requests_detail(self, slug: str) -> Dict:
        """
        Fetch https://damazzle.com/ads/{slug} with plain requests + BeautifulSoup.
        The /ads/ endpoint is server-side rendered — no Playwright needed.
        Returns a dom dict with: specs_raw, phone, seller_name, description, images.
        """
        # The /ads/ URL uses just the final slug segment (no make/date prefix)
        ad_slug = slug.split('/')[-1] if '/' in slug else slug
        url = f'https://damazzle.com/ads/{ad_slug}'
        dom: Dict = {}
        try:
            resp = self.http.get(url, timeout=20)
            if resp.status_code != 200:
                logger.debug(f'  BS4 detail {url}: HTTP {resp.status_code}')
                return dom
            soup = BeautifulSoup(resp.text, 'html.parser')

            # ── Phone ────────────────────────────────────────────────────────
            tel = soup.find('a', href=lambda h: h and h.startswith('tel:'))
            if tel:
                dom['phone'] = tel['href'].replace('tel:', '').strip()
            if not dom.get('phone'):
                wa = soup.find('a', href=lambda h: h and 'wa.me' in (h or ''))
                if wa:
                    m = re.search(r'wa\.me/(\+?[\d]+)', wa['href'])
                    if m:
                        dom['phone'] = m.group(1)

            # ── Seller name ──────────────────────────────────────────────────
            sinfo = soup.find(class_='sideauthor-info')
            if sinfo:
                for tag in sinfo.find_all('p'):
                    txt = tag.get_text(strip=True)
                    if txt and len(txt) > 1 and 'Join' not in txt and 'نشر' not in txt:
                        dom['seller_name'] = txt
                        break
            if not dom.get('seller_name'):
                for a in soup.find_all('a', href=lambda h: h and '/seller/' in (h or '')):
                    p = a.find('p', class_=lambda c: c and 'fw-bold' in c.split())
                    if not p:
                        p = a.find('p')
                    if p:
                        txt = p.get_text(strip=True)
                        if txt and len(txt) > 1 and 'نشر' not in txt:
                            dom['seller_name'] = txt
                            break

            # ── Specs ────────────────────────────────────────────────────────
            specs: Dict = {}

            # Strategy A: Damazzle Angular .col-6.col-md-4 + sibling .col-6.col-md-8
            for label_div in soup.find_all(
                'div',
                class_=lambda c: c and 'col-6' in c.split() and 'col-md-4' in c.split()
                                  and 'text-muted' in c.split()
            ):
                p = label_div.find('p')
                if not p:
                    continue
                label = p.get_text(strip=True)
                val_div = label_div.find_next_sibling('div')
                if not val_div:
                    continue
                val = val_div.get_text(strip=True)
                if label and val:
                    specs[label] = val

            # Strategy B: <dl> / <dt> + <dd>
            for dl in soup.find_all('dl'):
                for dt, dd in zip(dl.find_all('dt'), dl.find_all('dd')):
                    k, v = dt.get_text(strip=True), dd.get_text(strip=True)
                    if k and v:
                        specs.setdefault(k, v)

            # Strategy C: <table> two-cell rows
            for table in soup.find_all('table'):
                for row in table.find_all('tr'):
                    cells = row.find_all(['td', 'th'])
                    if len(cells) >= 2:
                        k, v = cells[0].get_text(strip=True), cells[1].get_text(strip=True)
                        if k and v and k != v:
                            specs.setdefault(k, v)

            if specs:
                dom['specs_raw'] = specs
                logger.debug(f'  BS4 specs ({ad_slug}): {specs}')

            # ── Images ───────────────────────────────────────────────────────
            skip_kw = ('icon', 'logo', 'placeholder', 'avatar', 'flag', 'sprite')
            imgs = []
            for img in soup.find_all('img'):
                src = (img.get('src') or img.get('data-src') or '').strip()
                if src.startswith('http') and not any(k in src.lower() for k in skip_kw):
                    imgs.append(src)
            if imgs:
                dom['images'] = list(dict.fromkeys(imgs))

            # ── Description ──────────────────────────────────────────────────
            for heading in soup.find_all(['h2', 'h3', 'h4']):
                if any(kw in heading.get_text() for kw in ('وصف', 'تفاصيل', 'ملاحظات')):
                    desc_el = heading.find_next(['div', 'p', 'section'])
                    if desc_el:
                        dom['description'] = desc_el.get_text(separator=' ', strip=True)
                    break

        except Exception as exc:
            logger.error(f'  BS4 detail error ({url}): {exc}')

        return dom

    # ── Image helpers ─────────────────────────────────────────────────────────

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
            fid  = result.get('id', '')
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

    # ── Car processing ────────────────────────────────────────────────────────

    def _process_car(self, c: Dict) -> bool:
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

        # Extract cover image from listing response BEFORE fetching detail page
        cover_url = ''
        for img in (c.get('gallery') or c.get('images') or c.get('photos') or []):
            src = (img.get('src') or img.get('url') or img.get('path') or ''
                   if isinstance(img, dict) else str(img)).strip()
            if src and src.startswith('http'):
                cover_url = src
                break
        if not cover_url:
            raw = c.get('cover_image') or c.get('thumbnail') or ''
            cover_url = raw.strip() if isinstance(raw, str) else ''

        # Fetch ALL structured spec fields from the detail-by-slug endpoint.
        # The listing API only gives 2 featured_fields; the detail API gives everything.
        if slug:
            detail_fields = self._fetch_detail_fields(slug)
            if detail_fields:
                c = {**c, '_detail_fields': detail_fields}

        try:
            data = _parse_car(c)
        except Exception as exc:
            logger.error(f'  Parse error ({car_id}): {exc}')
            return False

        # ── Year filter: skip cars older than MIN_YEAR ──
        year_str = str(data.get('year', '') or '').strip()
        if year_str:
            try:
                if int(year_str) < MIN_YEAR:
                    logger.info(f'  Skip (year {year_str} < {MIN_YEAR}): {car_id}')
                    return False
            except ValueError:
                pass

        data['cover_image_url'] = cover_url

        # ── Download cover image → dewatermark → upload clean to Drive ──
        image_clean_link = ''
        if cover_url and self.dewatermark_key:
            try:
                r = self.http.get(cover_url, timeout=30)
                r.raise_for_status()
                orig_bytes = r.content
                logger.info('  Removing watermark …')
                clean_bytes = self._remove_watermark(orig_bytes)
                if clean_bytes:
                    if self.drive_svc and DRIVE_FOLDER_ID:
                        cl = self._upload_bytes(
                            clean_bytes, 'image/jpeg', f'{car_id}_clean.jpg'
                        )
                        image_clean_link = cl or ''
                        logger.info('  ✓ Clean image uploaded to Drive')
                    else:
                        logger.info('  ✓ Watermark removed (no Drive folder set — skipping upload)')
                else:
                    logger.warning('  Watermark removal returned no image')
            except Exception as exc:
                logger.warning(f'  Image error for {car_id}: {exc}')

        data['image_clean_link'] = image_clean_link

        try:
            self._sheet_append(data)
            _append_jsonl(data)
            self.existing_ids.add(car_id)
            logger.info(
                f'  ✓  {data.get("ad_title", car_id)!r}'
                f'  phone={data.get("phone","-")}'
                f'  year={data.get("year","-")}'
            )
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

                    ok = self._process_car(it)
                    await asyncio.sleep(REQUEST_DELAY)
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

    parser.add_argument('--start-date',      type=_pd, metavar='DATE', default='2026-06-01')
    parser.add_argument('--end-date',        type=_pd, metavar='DATE', default='2026-07-31')
    parser.add_argument('--dewatermark-key', metavar='KEY',
                        help='dewatermark.ai API key for watermark removal')
    args = parser.parse_args()

    if sys.stdout.encoding != 'utf-8':
        sys.stdout.reconfigure(encoding='utf-8')

    scraper = DamazzleRawScraper(
        full_mode=args.full,
        max_hours=args.hours,
        start_date=args.start_date,
        end_date=args.end_date,
        dewatermark_key=args.dewatermark_key,
    )

    def _sig(s, f):
        scraper._stop = True

    signal.signal(signal.SIGINT,  _sig)
    signal.signal(signal.SIGTERM, _sig)

    scraper.run()
