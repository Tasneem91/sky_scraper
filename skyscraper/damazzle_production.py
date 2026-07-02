#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Damazzle Production Scraper
============================
Pure-requests, two-stage pipeline:
  1. Listing API  → make, city, price, phone, seller_name
  2. Detail API   → full specs (fuel_type, year, model, color, transmission…)

MANDATORY FIELDS — car is skipped if ANY of these is missing or "غير معروف":
  make, model, year, fuel_type, city, price, phone, seller_name

IMAGE — downloads the cover image (first in gallery) and removes the Damazzle
watermark using corner-brightness detection + OpenCV inpainting.
Requires: pip install opencv-python

OUTPUT
  damazzle_production.jsonl   — one JSON record per valid car
  damazzle_images/{id}.jpg    — watermark-cleaned cover image

USAGE
  python damazzle_production.py                   # incremental (new only)
  python damazzle_production.py --full            # all pages
  python damazzle_production.py --pages 5         # test (5 pages)
  python damazzle_production.py --hours 2         # time-limited
  python damazzle_production.py --skip-images     # skip image download
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
from typing import Any, Dict, List, Optional, Set, Tuple

import requests

# ── Optional: OpenCV for watermark removal ─────────────────────────────────────
try:
    import cv2
    import numpy as np
    _OPENCV = True
except ImportError:
    _OPENCV = False

# ── Logging ───────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)-8s %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('damazzle_production.log', encoding='utf-8'),
    ],
)
logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────────────

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

IMAGES_DIR    = os.path.join(SCRIPT_DIR, 'damazzle_images')
OUTPUT_FILE   = os.path.join(SCRIPT_DIR, 'damazzle_production.jsonl')
PROGRESS_FILE = os.path.join(SCRIPT_DIR, 'damazzle_production_progress.json')

SITE_URL    = 'https://damazzle.com'
LISTING_API = 'https://beta.damazzletech.com/api/api/v1/ads/search/ads'
DETAIL_API  = 'https://beta.damazzletech.com/api/api/v1/ads/details-by-slug'
SOURCE      = 'damazzle'
PER_PAGE    = 20
REQUEST_DELAY   = 1.2   # seconds between cars
DETAIL_DELAY    = 0.4   # extra delay after detail API call
STOP_STREAK     = 3     # incremental: stop after N fully-seen pages

# ── Mandatory fields ──────────────────────────────────────────────────────────

MANDATORY: Set[str] = {
    'make', 'model', 'year', 'fuel_type', 'city', 'price', 'phone', 'seller_name'
}

_SKIP_VALS: Set[str] = {
    '', '-', '—', '–', 'null', 'none', '0',
    'غير معروف', 'غير_معروف', 'غير محدد', 'غير_محدد', 'n/a',
}

# ── Field maps ────────────────────────────────────────────────────────────────

SLUG_MAP: Dict[str, str] = {
    'traveled_distance':   'mileage',
    'year_of_manufacture': 'year',
    'color':               'exterior_color',
    'Color':               'exterior_color',
    'exterior_color':      'exterior_color',
    'interior_color':      'interior_color',
    'fuel_type':           'fuel_type',
    'Fuel_type':           'fuel_type',
    'transmission':        'transmission',
    'Transmission':        'transmission',
    'gearbox':             'transmission',
    'condition':           'condition',
    'Condition':           'condition',
    'car_condition':       'condition',
    'engine_capacity':     'engine_size',
    'engine':              'engine_size',
    'body_type':           'body_type',
    'drive_system':        'drive_system',
    'drive_type':          'drive_system',
    'doors':               'doors',
    'cylinders':           'cylinders',
    'vin':                 'chassis_number',
    'chassis':             'chassis_number',
    'mileage':             'mileage',
    'year':                'year',
    'engine_size':         'engine_size',
    'chassis_number':      'chassis_number',
    'warranty':            'warranty',
    'chassis_condition':   'chassis_condition',
    'horsepower':          'horsepower',
    'seats':               'seats',
    'steering_side':       'steering_side',
    'origin':              'origin',
}

LABEL_MAP: Dict[str, str] = {
    'الكيلومتراج':       'mileage',
    'المسافة المقطوعة':  'mileage',
    'السنة':             'year',
    'سنة الصنع':         'year',
    'اللون الخارجي':     'exterior_color',
    'اللون':             'exterior_color',
    'اللون الداخلي':     'interior_color',
    'الوقود':            'fuel_type',
    'نوع الوقود':        'fuel_type',
    'ناقل الحركة':       'transmission',
    'الغيار':            'transmission',
    'الحالة':            'condition',
    'الشروط':            'condition',
    'المحرك':            'engine_size',
    'نوع الجسم':         'body_type',
    'نظام الدفع':        'drive_system',
    'نوع الدفع':         'drive_system',
    'الأبواب':           'doors',
    'عدد الأبواب':       'doors',
    'السلندرات':         'cylinders',
    'عدد السلندرات':     'cylinders',
    'رقم الهيكل':        'chassis_number',
    'الضمان':            'warranty',
    'حالة الهيكل':       'chassis_condition',
    'قوة الحصان':        'horsepower',
    'المقاعد':           'seats',
    'عدد المقاعد':       'seats',
    'جهة القيادة':       'steering_side',
    'الوارد':            'origin',
}

COND_MAP:  Dict[str, str] = {'used': 'مستعمل', 'new': 'جديد', 'damaged': 'متضرر'}
TRANS_MAP: Dict[str, str] = {
    'automatic': 'أوتوماتيك', 'manual': 'مانيوال', 'cvt': 'CVT', 'dct': 'DCT',
}
FUEL_MAP: Dict[str, str] = {
    'gasoline': 'بنزين', 'petrol': 'بنزين', 'diesel': 'ديزل',
    'electric': 'كهربائي', 'hybrid': 'هايبرد', 'gas': 'غاز',
}
BODY_MAP: Dict[str, str] = {
    'sedan': 'سيدان', 'suv': 'دفع رباعي', 'pickup': 'بيكاب',
    'hatchback': 'هاتشباك', 'coupe': 'كوبيه', 'wagon': 'ستيشن واغن',
    'van': 'فان', 'minivan': 'ميني فان', 'convertible': 'كشف',
    'truck': 'شاحنة', 'bus': 'باص',
}
DRIVE_MAP: Dict[str, str] = {
    'fwd': 'دفع أمامي', 'rwd': 'دفع خلفي',
    '4wd': 'دفع رباعي', 'awd': 'دفع رباعي كامل', '4x4': 'دفع رباعي',
}

# ── Helpers ───────────────────────────────────────────────────────────────────


def _clean(v: Any) -> str:
    if v is None:
        return ''
    t = ' '.join(str(v).split())
    return '' if t.lower() in ('-', '—', '–', '', 'null', 'none') else t


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


def _is_valid(data: Dict) -> Tuple[bool, str]:
    """Returns (True, '') if all mandatory fields are present, else (False, missing_field)."""
    for field in MANDATORY:
        val = str(data.get(field) or '').strip().lower()
        if val in _SKIP_VALS:
            return False, field
    return True, ''


# ── Watermark removal ─────────────────────────────────────────────────────────


def _remove_watermark(img_bytes: bytes) -> bytes:
    """
    Detect the Damazzle watermark logo in image corners and remove it via inpainting.

    Strategy: scan all four corners (25% w × 20% h each). In each corner count
    bright pixels (luminance > 195). The corner with the highest *and* most
    concentrated bright-pixel ratio (but not so high it's just a white car body)
    is the watermark. Dilate the mask and inpaint with INPAINT_TELEA.

    Falls back to original bytes if OpenCV is unavailable or no watermark detected.
    """
    if not _OPENCV:
        return img_bytes
    try:
        nparr = np.frombuffer(img_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            return img_bytes

        h, w = img.shape[:2]
        cw = max(10, w // 4)
        ch = max(10, h // 5)

        corners = [
            (0,      0,      ch,     cw,    'top-left'),
            (0,      w - cw, ch,     w,     'top-right'),
            (h - ch, 0,      h,      cw,    'bottom-left'),
            (h - ch, w - cw, h,      w,     'bottom-right'),
        ]

        best_thresh = None
        best_box    = None
        best_score  = 0.03   # minimum density threshold

        for (y1, x1, y2, x2, name) in corners:
            region = img[y1:y2, x1:x2]
            gray   = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)
            _, thresh = cv2.threshold(gray, 195, 255, cv2.THRESH_BINARY)

            ratio = float(np.sum(thresh > 0)) / thresh.size
            std   = float(np.std(gray))

            # Watermark: has some pattern variation AND bright-pixel ratio is
            # neither too low (not there) nor too high (entire white background).
            if 0.03 < ratio < 0.45 and std > 6 and ratio > best_score:
                best_score  = ratio
                best_thresh = thresh
                best_box    = (y1, x1, y2, x2)
                logger.debug(f'  Watermark candidate: {name} ratio={ratio:.2f} std={std:.1f}')

        if best_box is None:
            logger.debug('  No watermark region detected — saving original.')
            return img_bytes

        y1, x1, y2, x2 = best_box
        kernel      = np.ones((9, 9), np.uint8)
        mask_corner = cv2.dilate(best_thresh, kernel, iterations=2)

        full_mask = np.zeros((h, w), dtype=np.uint8)
        full_mask[y1:y2, x1:x2] = mask_corner

        result = cv2.inpaint(img, full_mask, inpaintRadius=5, flags=cv2.INPAINT_TELEA)
        _, buf = cv2.imencode('.jpg', result, [cv2.IMWRITE_JPEG_QUALITY, 92])
        logger.debug('  Watermark removed via inpainting.')
        return bytes(buf)

    except Exception as exc:
        logger.debug(f'  Watermark removal error: {exc}')
        return img_bytes


def _download_image(session: requests.Session, url: str, car_id: str) -> str:
    """Download cover image, remove watermark, save to IMAGES_DIR. Returns local path or ''."""
    if not url:
        return ''
    try:
        resp = session.get(url, timeout=20)
        if resp.status_code != 200:
            logger.debug(f'  Image {url}: HTTP {resp.status_code}')
            return ''
        img_bytes = _remove_watermark(resp.content)
        path = os.path.join(IMAGES_DIR, f'{car_id}.jpg')
        with open(path, 'wb') as fh:
            fh.write(img_bytes)
        return path
    except Exception as exc:
        logger.debug(f'  Image download error ({car_id}): {exc}')
        return ''


# ── Car parser ────────────────────────────────────────────────────────────────


def _parse_car(c: Dict) -> Dict:
    data: Dict[str, Any] = {
        'scraped_at': datetime.now().isoformat(),
        'source':     SOURCE,
    }

    lid  = str(c.get('id', '')  or c.get('_id', '') or '').strip()
    slug = str(c.get('slug', '') or '').strip()
    data['listing_id'] = lid
    data['id']         = f'damazzle_{lid}' if lid else f'damazzle_{slug}'
    data['slug']       = slug
    data['car_url']    = f'{SITE_URL}/motors/cars/{slug}' if slug else ''

    data['ad_title']     = _clean(c.get('title') or c.get('name') or '')
    data['listing_type'] = 'للبيع'
    data['price']        = _parse_price(c.get('price'))
    data['date_added']   = _parse_date(
        c.get('createdAt') or c.get('created_at') or c.get('published_date') or c.get('date_added')
    )

    # Make: from category.name_ar (Damazzle stores brand as category)
    cat = c.get('category') or {}
    if isinstance(cat, dict):
        data['make'] = _clean(
            cat.get('name_ar') or cat.get('name') or c.get('make') or c.get('brand') or ''
        )
    else:
        data['make'] = _clean(c.get('make') or c.get('brand') or '')

    # City: from governorate.name_ar
    gov = c.get('governorate') or {}
    if isinstance(gov, dict):
        data['city'] = _clean(
            gov.get('name_ar') or gov.get('name') or c.get('city') or ''
        )
    else:
        data['city'] = _clean(c.get('city') or '')

    def _apply_attrs(attrs: Optional[List]) -> None:
        """Apply attribute list — handles both nested (detail-by-slug) and flat (featured_fields) structures."""
        for attr in (attrs or []):
            if not isinstance(attr, dict):
                continue
            tf = attr.get('template_field')
            if isinstance(tf, dict):
                # Nested structure from details-by-slug: {template_field: {slug, field_name_ar}, value: {ar}}
                key     = str(tf.get('slug', '') or '').strip()
                label   = _clean(tf.get('field_name_ar') or tf.get('name_ar') or '')
                val_obj = attr.get('value') or {}
                val     = _clean(
                    val_obj.get('ar') or val_obj.get('en') or ''
                    if isinstance(val_obj, dict) else str(val_obj)
                )
            else:
                # Flat structure from featured_fields / attributes
                key   = str(attr.get('slug', '') or attr.get('key', '') or '').strip()
                label = _clean(attr.get('name_ar') or attr.get('label_ar') or attr.get('name') or '')
                val   = _clean(
                    attr.get('value_ar') or attr.get('value') or
                    attr.get('val') or attr.get('display_value') or ''
                )
            if not val or val in ('غير محدد', 'غير_محدد', '-', ''):
                continue
            field = SLUG_MAP.get(key) or LABEL_MAP.get(label)
            if field and not data.get(field):
                data[field] = val

    # detail_fields must come first — they are the most complete source
    _apply_attrs(c.get('_detail_fields') or [])
    _apply_attrs(c.get('featured_fields') or c.get('featuredAttributes') or c.get('featured_attributes') or [])
    _apply_attrs(c.get('attributes') or [])

    # Phone: listing API has it at top-level car.phone / car.whatsapp
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
            data['seller_name']    = _clean(customer.get('name') or customer.get('full_name') or '')
            data['seller_listings'] = str(customer.get('totalAds') or customer.get('ads_count') or '')

    # Model: from sub_category, or direct field, or title-based fallback
    if not data.get('model'):
        sub_cat = c.get('sub_category') or c.get('subCategory') or {}
        if isinstance(sub_cat, dict):
            data['model'] = _clean(sub_cat.get('name_ar') or sub_cat.get('name') or '')
    if not data.get('model'):
        data['model'] = _clean(c.get('model_ar') or c.get('model') or '')
    if not data.get('model') and data.get('ad_title') and data.get('make'):
        # Last resort: strip make + year from title to get model
        remaining = data['ad_title']
        for token in [data['make'], data.get('year', '')]:
            if token:
                remaining = re.sub(r'\b' + re.escape(token) + r'\b', '', remaining).strip()
        remaining = re.sub(r'\s+', ' ', remaining).strip()
        if remaining and len(remaining) > 1:
            data['model'] = remaining

    # Description
    if not data.get('description'):
        data['description'] = _clean(c.get('description_ar') or c.get('description') or '')

    # Direct flat-field fallbacks
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

    # Translate English enum values to Arabic
    for field, mapping in (
        ('condition',    COND_MAP),
        ('transmission', TRANS_MAP),
        ('fuel_type',    FUEL_MAP),
        ('body_type',    BODY_MAP),
        ('drive_system', DRIVE_MAP),
    ):
        if data.get(field):
            data[field] = _ar(data[field], mapping)

    # Cover image URL — first item in gallery
    cover_url = ''
    for img in (c.get('gallery') or c.get('images') or c.get('photos') or []):
        src = (img.get('src') or img.get('url') or img.get('path') or ''
               if isinstance(img, dict) else str(img)).strip()
        if src and src.startswith('http'):
            cover_url = src
            break
    if not cover_url:
        cover_url = _clean(c.get('cover_image') or c.get('thumbnail') or '')
    data['cover_image_url'] = cover_url

    return data


# ── Progress / JSONL helpers ──────────────────────────────────────────────────


def _load_progress() -> Dict:
    if os.path.exists(PROGRESS_FILE):
        try:
            with open(PROGRESS_FILE, encoding='utf-8') as fh:
                return json.load(fh)
        except Exception:
            pass
    return {'last_page': 0, 'total_scraped': 0, 'full_scrape_done': False}


def _save_progress(p: Dict) -> None:
    tmp = PROGRESS_FILE + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as fh:
        json.dump(p, fh, indent=2, ensure_ascii=False)
    os.replace(tmp, PROGRESS_FILE)


def _append_jsonl(record: Dict) -> None:
    with open(OUTPUT_FILE, 'a', encoding='utf-8') as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + '\n')


def _load_existing_ids() -> Set[str]:
    ids: Set[str] = set()
    if not os.path.exists(OUTPUT_FILE):
        return ids
    try:
        with open(OUTPUT_FILE, encoding='utf-8') as fh:
            for line in fh:
                try:
                    rec = json.loads(line)
                    if rec.get('id'):
                        ids.add(rec['id'])
                except Exception:
                    pass
    except Exception:
        pass
    return ids


# ── Scraper class ─────────────────────────────────────────────────────────────


class DamazzleProductionScraper:

    def __init__(
        self,
        full_mode:   bool           = False,
        max_hours:   Optional[float] = None,
        max_pages:   Optional[int]   = None,
        skip_images: bool            = False,
    ):
        self.full_mode   = full_mode
        self.max_pages   = max_pages
        self.skip_images = skip_images
        self.deadline: Optional[datetime] = (
            datetime.now() + timedelta(hours=max_hours) if max_hours else None
        )
        self._stop = False

        os.makedirs(IMAGES_DIR, exist_ok=True)

        self.http = requests.Session()
        self.http.headers.update({
            'User-Agent': (
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                'AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/120.0.0.0 Safari/537.36'
            ),
            'Accept':   'application/json',
            'Origin':   SITE_URL,
            'Referer':  f'{SITE_URL}/motors/cars/search',
        })

        self.progress     = _load_progress()
        self.existing_ids = _load_existing_ids()

        if not _OPENCV and not skip_images:
            logger.warning(
                'opencv-python not installed — watermark removal disabled.\n'
                '  Run: pip install opencv-python'
            )

        logger.info(f'Existing IDs loaded : {len(self.existing_ids)}')
        logger.info(f'Images dir          : {IMAGES_DIR}')
        logger.info(f'Output file         : {OUTPUT_FILE}')

    def _should_stop(self) -> bool:
        if self._stop:
            return True
        if self.deadline and datetime.now() >= self.deadline:
            logger.info('Time limit reached.')
            return True
        return False

    # ── API calls ─────────────────────────────────────────────────────────────

    def _fetch_listing_page(self, page: int) -> Optional[Dict]:
        params = {'page': page, 'per_page': PER_PAGE}
        try:
            resp = self.http.get(LISTING_API, params=params, timeout=30)
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            logger.error(f'  Listing API error (page {page}): {exc}')
            return None

    def _fetch_detail_fields(self, slug: str) -> List[Dict]:
        if not slug:
            return []
        ad_slug = slug.split('/')[-1] if '/' in slug else slug
        try:
            r = self.http.get(f'{DETAIL_API}/{ad_slug}', timeout=15)
            if r.status_code != 200:
                logger.debug(f'  detail-by-slug {ad_slug}: HTTP {r.status_code}')
                return []
            body = r.json()
            ad   = (body.get('data') or {}).get('ad') or {}
            fields = ad.get('fields') or []
            logger.debug(f'  detail-by-slug {ad_slug}: {len(fields)} fields')
            return fields
        except Exception as exc:
            logger.debug(f'  detail-by-slug error ({ad_slug}): {exc}')
            return []

    # ── Per-car processing ────────────────────────────────────────────────────

    def _process_car(self, listing: Dict) -> bool:
        lid    = str(listing.get('id', '')   or listing.get('_id', '') or '').strip()
        slug   = str(listing.get('slug', '') or '').strip()
        car_id = f'damazzle_{lid}' if lid else f'damazzle_{slug}'

        if car_id in self.existing_ids:
            return False

        # Stage 2: fetch full spec fields from details-by-slug
        c = listing
        if slug:
            detail_fields = self._fetch_detail_fields(slug)
            if detail_fields:
                c = {**listing, '_detail_fields': detail_fields}
            time.sleep(DETAIL_DELAY)

        # Parse
        try:
            data = _parse_car(c)
        except Exception as exc:
            logger.error(f'  Parse error ({car_id}): {exc}')
            return False

        # Mandatory field gate
        valid, missing = _is_valid(data)
        if not valid:
            logger.info(f'  ✗  Skip {car_id} — missing: {missing}')
            return False

        # Cover image
        if not self.skip_images:
            path = _download_image(self.http, data.get('cover_image_url', ''), car_id)
            data['cover_image_local'] = path
        else:
            data['cover_image_local'] = ''

        # Save
        try:
            _append_jsonl(data)
            self.existing_ids.add(car_id)
            logger.info(
                f'  ✓  {data["make"]} {data["model"]} {data["year"]}'
                f' | {data["city"]} | {data["price"]} SYP'
                f' | phone={data["phone"]}'
            )
            return True
        except Exception as exc:
            logger.error(f'  Write failed ({car_id}): {exc}')
            return False

    # ── Main loop ─────────────────────────────────────────────────────────────

    def run(self) -> None:
        progress = self.progress

        if self.full_mode:
            if progress.get('full_scrape_done'):
                logger.info('Full scrape already complete. Delete progress file to restart.')
                return
            start_page = progress['last_page'] + 1
            logger.info(f'Full scrape mode — resuming from page {start_page}')
        else:
            start_page = 1
            logger.info('Incremental mode — starting from page 1')

        logger.info('=' * 62)
        logger.info(f'Damazzle production scraper  {datetime.now().isoformat()}')
        logger.info('=' * 62)

        total_saved = 0
        total_skip  = 0
        streak      = 0
        page        = start_page
        grand_total : Optional[int] = None

        while True:
            if self._should_stop():
                break
            if self.max_pages and page >= start_page + self.max_pages:
                logger.info(f'Reached --pages {self.max_pages} limit — stopping.')
                break

            logger.info(f'\n[Page {page}]')
            payload = self._fetch_listing_page(page)

            if not payload:
                logger.info('  No response — stopping.')
                break

            # Extract items
            items: List[Dict] = []
            for key in ('data', 'ads', 'results', 'items', 'records', 'listings'):
                val = payload.get(key)
                if isinstance(val, list):
                    items = val
                    break
            if not items and isinstance(payload, list):
                items = payload

            # Extract grand total once
            if grand_total is None:
                for key in ('total', 'count', 'totalCount', 'total_count'):
                    v = payload.get(key)
                    if isinstance(v, int):
                        grand_total = v
                        break
                    meta = payload.get('meta') or {}
                    if isinstance(meta.get(key), int):
                        grand_total = meta[key]
                        break
                if grand_total:
                    logger.info(f'  Total listings: {grand_total}')

            if not items:
                logger.info('  No items on page — stopping.')
                if self.full_mode:
                    progress['full_scrape_done'] = True
                    _save_progress(progress)
                break

            new_items = [
                it for it in items
                if (f"damazzle_{it.get('id', '')}"   not in self.existing_ids and
                    f"damazzle_{it.get('slug', '')}" not in self.existing_ids)
            ]
            logger.info(f'  {len(items)} on page | {len(new_items)} new')

            if not new_items:
                if not self.full_mode:
                    streak += 1
                    if streak >= STOP_STREAK:
                        logger.info('  Caught up — stopping.')
                        break
                else:
                    progress['last_page'] = page
                    _save_progress(progress)
                time.sleep(REQUEST_DELAY)
                page += 1
                continue

            streak = 0

            for it in new_items:
                if self._should_stop():
                    if self.full_mode:
                        progress['last_page'] = page - 1
                        _save_progress(progress)
                    break
                saved = self._process_car(it)
                if saved:
                    total_saved += 1
                    progress['total_scraped'] += 1
                else:
                    total_skip += 1
                time.sleep(REQUEST_DELAY)
            else:
                if self.full_mode:
                    progress['last_page'] = page
                    _save_progress(progress)

            if self._should_stop():
                break

            if grand_total and page * PER_PAGE >= grand_total:
                logger.info('  All pages scraped.')
                if self.full_mode:
                    progress['full_scrape_done'] = True
                    _save_progress(progress)
                break

            time.sleep(REQUEST_DELAY)
            page += 1

        _save_progress(progress)

        logger.info('\n' + '=' * 62)
        logger.info(f'Done.  saved={total_saved}  skipped={total_skip}')
        logger.info(f'Output : {OUTPUT_FILE}')
        logger.info(f'Images : {IMAGES_DIR}')
        logger.info('=' * 62)


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Damazzle production scraper')
    parser.add_argument('--full',        action='store_true', help='Scrape all pages (resume from last)')
    parser.add_argument('--hours',       type=float, metavar='N', help='Stop after N hours')
    parser.add_argument('--pages',       type=int,   metavar='N', help='Max pages (test mode)')
    parser.add_argument('--skip-images', action='store_true', help='Skip image download')
    args = parser.parse_args()

    if sys.stdout.encoding != 'utf-8':
        sys.stdout.reconfigure(encoding='utf-8')

    scraper = DamazzleProductionScraper(
        full_mode=args.full,
        max_hours=args.hours,
        max_pages=args.pages,
        skip_images=args.skip_images,
    )

    def _sig(signum, frame):
        scraper._stop = True

    signal.signal(signal.SIGINT,  _sig)
    signal.signal(signal.SIGTERM, _sig)

    scraper.run()
