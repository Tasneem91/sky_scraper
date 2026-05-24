"""
Shared Parsing & Normalization Layer — Stage 2 of the two-stage pipeline.

OUTPUT SCHEMA — exactly 27 columns, no more, no less:
  Technical (5): scraped_at, source, id, category, images
  Business (22): listing_type, condition, body_type, brand, model,
                 price, location, year, transmission, fuel_type,
                 mileage, engine, cylinders, color, interior_color,
                 doors, vin, description, seller_name, contact,
                 drive_system, ad_title

  contact      = phone number(s) + WhatsApp combined into one text field
  drive_system = نوع الدفع / نظام الدفع (2WD / 4WD / AWD etc.)
  ad_title     = auto-generated Arabic listing title from structured fields
                 e.g. "Toyota Camry 2019 للبيع في دمشق"

DESIGN RULES:
  • parse() returns ONLY the 27 schema columns — zero extra fields
  • All interpretation lives here, zero in individual scrapers
  • Prefer specs_raw (structured) over free text
  • Missing fields → None (never "N/A" or "")
"""

import re
import json
import logging
from datetime import datetime
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)


# ============================================================================
# Spec label → schema field maps
# ============================================================================

# Carsy.app: labels are REVERSED — الموديل = manufacturer, الماركة = car series
CARSY_SPEC_MAP = {
    'الموديل':        'brand',
    'الماركة':        'model',
    'السنة':          'year',
    'الكيلومترات':    'mileage',
    'نوع الوقود':     'fuel_type',
    'المحرك':         'engine',
    'ناقل الحركة':    'transmission',
    'اللون الخارجي':  'color',
    'اللون الداخلي':  'interior_color',
    'الأسطوانات':     'cylinders',
    'المقاعد':        '_seats',       # not in schema — underscore = skip
    'المفاتيح':       '_keys',        # not in schema
    'نظام الدفع':     'drive_system', # e.g. 4WD / AWD / 2WD
    'المصدر':         '_origin',      # not in schema
    'المواصفات':      'specs_category',
    'الحالة':         'condition',
    'نوع الهيكل':     'body_type',
    'عدد الأبواب':    'doors',
    'الأبواب':        'doors',
    'رقم الشاصي':     'vin',
    'VIN':            'vin',
}

# Generic map for all other sites (standard Arabic label naming)
GENERIC_SPEC_MAP = {
    'الماركة':             'brand',
    'ماركة السيارة':       'brand',
    'الصانع':              'brand',
    'الموديل':             'model',
    'موديل السيارة':       'model',
    'السنة':               'year',
    'سنة الصنع':           'year',
    'الكيلومترات':         'mileage',
    'المسافة المقطوعة':    'mileage',
    'عداد المسافة':        'mileage',
    'نوع الوقود':          'fuel_type',
    'الوقود':              'fuel_type',
    'المحرك':              'engine',
    'حجم المحرك':          'engine',
    'سعة المحرك':          'engine',
    'ناقل الحركة':         'transmission',
    'ناقل':                'transmission',
    'نوع الناقل':          'transmission',
    'اللون':               'color',
    'اللون الخارجي':       'color',
    'لون السيارة':         'color',
    'اللون الداخلي':       'interior_color',
    'لون الفرش':           'interior_color',
    'الأسطوانات':          'cylinders',
    'عدد الأسطوانات':      'cylinders',
    'الأبواب':             'doors',
    'عدد الأبواب':         'doors',
    'رقم الشاصي':          'vin',
    'رقم VIN':             'vin',
    'VIN':                 'vin',
    'الشاصي':              'vin',
    'الحالة':              'condition',
    'نوع الهيكل':          'body_type',
    'هيكل السيارة':        'body_type',
    'نوع الجسم':           'body_type',
    'الموقع':              'location',
    'المدينة':             'location',
    'المحافظة':            'location',
    'المنطقة':             'location',
    'المصدر':              '_origin',      # not in schema — underscore = ignore
    'الوارد الإقليمي':     '_origin',      # alternate label for origin
    'المقاعد':             '_seats',      # not in schema
    'عدد المقاعد':         '_seats',      # alternate label
    'جهة القيادة':         '_steering',   # LHD/RHD — not in schema
    'قوة الحصان':          '_horsepower', # not in schema
    'الضمان':              '_warranty',   # not in schema
    'حالة الهيكل':         '_body_cond',  # body/chassis condition — not in schema
    'نظام الدفع':          'drive_system', # e.g. 4WD / AWD / 2WD
    'نوع الدفع':           'drive_system', # same field, alternate label
    # Syriacar-specific label variants
    'جسم المركبة':         'body_type',
    'موديل المركبة':       'model',
    'حالة المركبة':        'condition',
    'رقم الهيكل':          'vin',
}


# ============================================================================
# Keyword normalization maps
# ============================================================================

FUEL_KEYWORDS = {
    'بنزين':    'بنزين',
    'gasoline': 'بنزين',
    'petrol':   'بنزين',
    'ديزل':     'ديزل',
    'diesel':   'ديزل',
    'غاز':      'غاز',
    'lpg':      'غاز',
    'كهرباء':   'كهرباء',
    'كهربائي':  'كهرباء',
    'electric': 'كهرباء',
    'هجين':     'هجين',
    'hybrid':   'هجين',
}

TRANSMISSION_KEYWORDS = {
    'أوتوماتيك':  'أوتوماتيك',
    'اوتوماتيك':  'أوتوماتيك',
    'automatic':  'أوتوماتيك',
    'auto':       'أوتوماتيك',
    'يدوي':       'يدوي',
    'manual':     'يدوي',
    'عادي':       'يدوي',
}

CONDITION_KEYWORDS = {
    'جديدة':    'جديدة',
    'جديد':     'جديدة',
    'new':      'جديدة',
    'مستعملة':  'مستعملة',
    'مستعمل':   'مستعملة',
    'مستخدمة':  'مستعملة',
    'used':     'مستعملة',
}

LISTING_TYPE_MAP = {
    'sell':    'بيع',
    'rent':    'إيجار',
    'بيع':     'بيع',
    'إيجار':   'إيجار',
    'للبيع':   'بيع',
    'للإيجار': 'إيجار',
}

BRAND_ALIASES = {
    'تويوتا': 'Toyota', 'كيا': 'Kia', 'هيونداي': 'Hyundai',
    'هونداي': 'Hyundai', 'نيسان': 'Nissan', 'هوندا': 'Honda',
    'ميتسوبيشي': 'Mitsubishi', 'مرسيدس': 'Mercedes',
    'بي ام دبليو': 'BMW', 'اودي': 'Audi', 'فولكس': 'Volkswagen',
    'فورد': 'Ford', 'شيفروليه': 'Chevrolet', 'جي ام سي': 'GMC',
    'دودج': 'Dodge', 'جيب': 'Jeep', 'لاند روفر': 'Land Rover',
    'لكزس': 'Lexus', 'مازدا': 'Mazda', 'سوزوكي': 'Suzuki',
    'بيجو': 'Peugeot', 'رينو': 'Renault', 'اوبل': 'Opel',
    'فولفو': 'Volvo', 'فيات': 'Fiat', 'انفينيتي': 'Infiniti',
    'شيري': 'Chery', 'جيلي': 'Geely', 'هافال': 'Haval',
}

KNOWN_BRANDS = [
    'Toyota', 'Kia', 'Hyundai', 'Nissan', 'Honda', 'Mitsubishi',
    'Mercedes', 'BMW', 'Audi', 'Volkswagen', 'Ford', 'Chevrolet',
    'GMC', 'Dodge', 'Jeep', 'Land Rover', 'Lexus', 'Mazda', 'Subaru',
    'Suzuki', 'Peugeot', 'Renault', 'Skoda', 'SEAT', 'Opel', 'Volvo',
    'Fiat', 'Alfa', 'Citroen', 'Infiniti', 'Acura', 'Lincoln',
    'Cadillac', 'Buick', 'Chrysler', 'Tesla', 'BYD', 'Geely', 'Chery',
    'Haval', 'MG', 'Isuzu', 'Datsun', 'Porsche', 'Range', 'Isuzu',
]


# ============================================================================
# Shared detail-page extractor (used by scrapers that get SSR HTML)
# ============================================================================

def extract_detail_from_soup(soup) -> Dict[str, Any]:
    """
    Generic SSR detail page parser.
    Tries multiple spec extraction strategies that cover most Arabic car sites.

    Returns a raw_detail dict ready to be merged into a card raw dict.
    """
    detail: Dict[str, Any] = {
        'title_raw':       None,
        'price_raw':       None,
        'specs_raw':       {},
        'description_raw': None,
        'seller_name':     None,
        'images':          [],
        'phone':           None,
        'whatsapp':        None,
    }

    # Title
    h1 = soup.find('h1')
    if h1:
        detail['title_raw'] = h1.get_text(strip=True)

    # Price — any element containing $ or دولار
    for el in soup.find_all(['span', 'div', 'p', 'h2', 'strong']):
        text = el.get_text(strip=True)
        if ('$' in text or 'دولار' in text or 'USD' in text) and re.search(r'\d', text):
            if len(text) < 50:   # ignore long blocks that happen to have $
                detail['price_raw'] = text
                break

    # ── Spec extraction: 4 strategies ──────────────────────────────────────

    specs = detail['specs_raw']

    # Strategy 1: h2/h3 "معلومات السيارة" → next div → alternating label/value divs (Carsy pattern)
    for heading in soup.find_all(['h2', 'h3']):
        if 'معلومات' in heading.get_text():
            container = heading.find_next('div')
            if container:
                children = container.find_all('div', recursive=False)
                for i in range(0, len(children) - 1, 2):
                    k = children[i].get_text(strip=True)
                    v = children[i + 1].get_text(strip=True)
                    if k and v and k != v:
                        specs[k] = v

    # Strategy 2: <dl> / <dt> + <dd> pairs
    for dl in soup.find_all('dl'):
        dts = dl.find_all('dt')
        dds = dl.find_all('dd')
        for dt, dd in zip(dts, dds):
            k = dt.get_text(strip=True)
            v = dd.get_text(strip=True)
            if k and v:
                specs[k] = v

    # Strategy 3: <table> with two-cell rows
    for table in soup.find_all('table'):
        for row in table.find_all('tr'):
            cells = row.find_all(['td', 'th'])
            if len(cells) >= 2:
                k = cells[0].get_text(strip=True)
                v = cells[1].get_text(strip=True)
                if k and v and k != v:
                    specs[k] = v

    # Strategy 4: div pairs with common label/value class names
    for container in soup.find_all('div', class_=re.compile(r'spec|detail|feature|info|prop', re.I)):
        children = container.find_all('div', recursive=False)
        if len(children) == 2:
            k = children[0].get_text(strip=True)
            v = children[1].get_text(strip=True)
            if k and v and k != v and len(k) < 40:
                specs.setdefault(k, v)

    # Strategy 5: paired <ul> lists — syriacar.net accordion pattern.
    # Each accordion section has two side-by-side <ul>s: labels-list + values-list.
    # Sections with an even number of <ul>s are spec tables; odd = feature lists.
    for outer in soup.find_all('div', class_=re.compile(
            r'accordion-\d+-content-details|accordion-inner-details', re.I)):
        all_uls = outer.find_all('ul')
        if len(all_uls) >= 2 and len(all_uls) % 2 == 0:
            for i in range(0, len(all_uls), 2):
                label_items = [li.get_text(strip=True) for li in all_uls[i].find_all('li')]
                value_items = [li.get_text(strip=True) for li in all_uls[i + 1].find_all('li')]
                for k, v in zip(label_items, value_items):
                    if k and v and k != v and len(k) < 40:
                        specs.setdefault(k, v)

    # ── Description ─────────────────────────────────────────────────────────
    for heading in soup.find_all(['h2', 'h3', 'h4']):
        text = heading.get_text(strip=True)
        if 'وصف' in text or 'تفاصيل' in text or 'ملاحظات' in text:
            desc_el = heading.find_next(['div', 'p', 'section'])
            if desc_el:
                detail['description_raw'] = desc_el.get_text(separator=' ', strip=True)
            break

    # ── Seller name ─────────────────────────────────────────────────────────
    # Strategy A: heading (h2/h3/h4) containing بائع/معلن/المالك
    for heading in soup.find_all(['h2', 'h3', 'h4']):
        text = heading.get_text(strip=True)
        if 'بائع' in text or 'معلن' in text or 'المالك' in text or 'صاحب' in text:
            seller_el = heading.find_next(['div', 'p', 'span', 'h4', 'h5'])
            if seller_el:
                detail['seller_name'] = seller_el.get_text(strip=True)[:100]
            break

    # Strategy B: syriacar.net style — box-container-seller-info-desktop contains
    # the seller name as a sibling div between span.span-seller-info and
    # div.div-box-border-seller-details.  Extract by skipping known non-name tokens.
    if not detail['seller_name']:
        _SELLER_SKIP = {
            'المعلن', 'البائع', 'المالك', 'صاحب الإعلان', 'زيارة',
            'حساب تجاري', 'حساب شخصي', 'حساب وكالة',
        }
        for box in soup.find_all('div', class_=re.compile(
                r'box-container-seller-info|seller-info-box|seller-details', re.I)):
            lines = [
                t.strip()
                for t in box.get_text(separator='\n').split('\n')
                if t.strip() and len(t.strip()) > 2
            ]
            candidates = [
                l for l in lines
                if l not in _SELLER_SKIP
                and not re.match(r'^(إعلان|حساب|\d)', l)
                and not re.match(r'^[؀-ۿ]{1,3}$', l)   # skip lone Arabic words
            ]
            if candidates:
                detail['seller_name'] = candidates[0][:100]
                break

    # ── Images ──────────────────────────────────────────────────────────────
    skip = ('icon', 'logo', 'placeholder', 'avatar', 'flag', 'sprite', 'banner')
    for img in soup.find_all('img'):
        src = img.get('src') or img.get('data-src') or img.get('data-lazy') or ''
        src = src.strip()
        if src.startswith('http') and len(src) > 30 and not any(k in src.lower() for k in skip):
            detail['images'].append(src)
    detail['images'] = list(dict.fromkeys(detail['images']))

    # ── Contact ─────────────────────────────────────────────────────────────
    tel = soup.find('a', href=lambda h: h and h.startswith('tel:'))
    if tel:
        detail['phone'] = tel['href'].replace('tel:', '').strip()

    wa = soup.find('a', href=lambda h: h and 'wa.me' in (h or ''))
    if wa:
        m = re.search(r'wa\.me/(\d+)', wa['href'])
        detail['whatsapp'] = m.group(1) if m else wa['href']

    return detail


def merge_detail(raw: Dict, detail: Dict) -> Dict:
    """
    Merge detail page data into a card raw dict.
    Detail wins for specs (more complete); card wins for id/source/etc.
    """
    # Merge specs (detail keys fill in or override card specs)
    raw_specs = raw.get('specs_raw') or {}
    raw_specs.update(detail.get('specs_raw') or {})
    raw['specs_raw'] = raw_specs

    # Prefer detail page values when available
    if detail.get('description_raw'):
        raw['description_raw'] = detail['description_raw']
    if detail.get('images'):
        raw['images'] = detail['images']
    if detail.get('phone'):
        raw['phone'] = detail['phone']
    if detail.get('whatsapp'):
        raw['whatsapp'] = detail['whatsapp']
    if detail.get('seller_name'):
        raw['seller_name'] = detail['seller_name']
    if detail.get('title_raw') and not raw.get('title_raw'):
        raw['title_raw'] = detail['title_raw']
    if detail.get('price_raw') and not raw.get('price_raw'):
        raw['price_raw'] = detail['price_raw']

    return raw


# ============================================================================
# Main entry point
# ============================================================================

def parse(raw: Dict[str, Any], spec_map: Dict[str, str] = None) -> Dict[str, Any]:
    """
    Convert a raw extraction dict into the EXACT 25-column unified schema.

    Args:
        raw: Output of each scraper's raw extraction + optional detail merge.
        spec_map: Label→field mapping. Defaults to GENERIC_SPEC_MAP.
                  Pass CARSY_SPEC_MAP for carsy.app (reversed brand/model).

    Returns:
        Dict with EXACTLY the 25 specified columns. No extra fields.
    """
    if spec_map is None:
        spec_map = GENERIC_SPEC_MAP

    specs = raw.get('specs_raw') or {}
    title = (raw.get('title_raw') or '').strip()
    desc  = (raw.get('description_raw') or '').strip()
    combined = f"{title} {desc}".lower()

    # ── Map spec labels → schema fields (ignore fields starting with _) ────
    mapped: Dict[str, Any] = {}
    for label, value in specs.items():
        field = spec_map.get(label)
        if field and not field.startswith('_') and value:
            mapped[field] = str(value).strip()

    # ── Field resolution (structured → free text fallback) ─────────────────
    brand        = mapped.get('brand') or _extract_brand(title)
    # Normalize Arabic brand names → English (e.g. شيفروليه → Chevrolet)
    if brand and brand in BRAND_ALIASES:
        brand = BRAND_ALIASES[brand]
    model        = mapped.get('model') or _extract_model(title, brand)
    year         = _parse_year(mapped.get('year')) or _extract_year_from_text(title)
    mileage      = mapped.get('mileage') or _extract_mileage(desc) or _extract_mileage(title)
    fuel_type    = mapped.get('fuel_type') or _detect_keyword(combined, FUEL_KEYWORDS)
    transmission = mapped.get('transmission') or _detect_keyword(combined, TRANSMISSION_KEYWORDS)
    condition    = mapped.get('condition') or _detect_keyword(combined, CONDITION_KEYWORDS)
    location     = mapped.get('location') or _clean_text(raw.get('location_raw'))
    body_type    = mapped.get('body_type')
    engine       = mapped.get('engine')
    cylinders    = mapped.get('cylinders')
    color        = mapped.get('color')
    interior_color = mapped.get('interior_color')
    doors        = mapped.get('doors')
    vin          = _validate_vin(mapped.get('vin'))
    category     = mapped.get('specs_category') or raw.get('category')
    drive_system = mapped.get('drive_system')

    # ── Price ─────────────────────────────────────────────────────────────
    price = _parse_price(raw.get('price_raw'))

    # ── Images ────────────────────────────────────────────────────────────
    images = _normalize_images(raw.get('images'))

    # ── Listing type ──────────────────────────────────────────────────────
    listing_type = LISTING_TYPE_MAP.get(
        str(raw.get('listing_type', 'sell')).lower(), 'بيع'
    )

    # ── Ad title (generated from structured fields) ───────────────────────
    ad_title = _build_ad_title(brand, model, year, listing_type, location, condition)

    # ── Contact (phone + WhatsApp combined) ───────────────────────────────
    phone    = raw.get('phone')
    whatsapp = raw.get('whatsapp')
    contact  = _build_contact(phone, whatsapp)

    # ── Return EXACTLY 27 columns ─────────────────────────────────────────
    return {
        # Technical (5)
        'scraped_at':     raw.get('scraped_at') or datetime.now().isoformat(),
        'source':         raw.get('source') or '',
        'id':             raw.get('id') or '',
        'category':       category,
        'images':         json.dumps(images, ensure_ascii=False),

        # Business (22)
        'listing_type':   listing_type,
        'condition':      condition,
        'body_type':      body_type,
        'brand':          brand,
        'model':          model,
        'price':          price,
        'location':       location,
        'year':           year,
        'transmission':   transmission,
        'fuel_type':      fuel_type,
        'mileage':        mileage,
        'engine':         engine,
        'cylinders':      cylinders,
        'color':          color,
        'interior_color': interior_color,
        'doors':          doors,
        'vin':            vin,
        'description':    _clean_text(desc) or None,
        'seller_name':    raw.get('seller_name'),
        'contact':        contact,
        'drive_system':   drive_system,
        'ad_title':       ad_title,
    }


# ============================================================================
# Helpers
# ============================================================================

def _build_contact(phone: Optional[str], whatsapp: Optional[str]) -> Optional[str]:
    """Combine phone and WhatsApp into a single contact field."""
    parts = []
    if phone:
        parts.append(phone)
    if whatsapp and whatsapp != phone:
        parts.append(f"WA:{whatsapp}")
    return ' | '.join(parts) if parts else None


def _parse_price(text: Any) -> Optional[float]:
    if not text:
        return None
    try:
        cleaned = re.sub(r'[^\d.]', '', str(text))
        return float(cleaned) if cleaned else None
    except (ValueError, TypeError):
        return None


def _parse_year(text: Any) -> Optional[int]:
    if not text:
        return None
    m = re.search(r'\b(19[5-9]\d|20[012]\d)\b', str(text))
    return int(m.group(0)) if m else None


def _extract_year_from_text(text: str) -> Optional[int]:
    if not text:
        return None
    m = re.search(r'\b(19[5-9]\d|20[012]\d)\b', text)
    return int(m.group(0)) if m else None


def _extract_mileage(text: str) -> Optional[str]:
    if not text:
        return None
    m = re.search(r'(\+?[\d,]+)\s*(كم|km|كيلو|كيلومتر)?', text, re.IGNORECASE)
    if m:
        num_str = m.group(1).replace(',', '')
        try:
            num = int(num_str)
            if 100 <= num <= 1_000_000:
                unit = m.group(2) or 'كم'
                return f"{m.group(1)} {unit}"
        except ValueError:
            pass
    return None


def _detect_keyword(text: str, keyword_map: Dict[str, str]) -> Optional[str]:
    if not text:
        return None
    for keyword, normalized in keyword_map.items():
        if keyword.lower() in text:
            return normalized
    return None


def _extract_brand(title: str) -> Optional[str]:
    if not title:
        return None
    for brand in KNOWN_BRANDS:
        if re.search(r'\b' + re.escape(brand) + r'\b', title, re.IGNORECASE):
            return brand
    for arabic, english in BRAND_ALIASES.items():
        if arabic in title:
            return english
    m = re.search(r'\b([A-Za-z][A-Za-z\-]{1,})\b', title)
    if m:
        candidate = m.group(1)
        if candidate.lower() not in ('used', 'new', 'for', 'sale', 'rent', 'the', 'and', 'with'):
            return candidate
    return None


def _extract_model(title: str, brand: Optional[str]) -> Optional[str]:
    if not title or not brand:
        return None
    remaining = re.sub(re.escape(brand), '', title, flags=re.IGNORECASE).strip()
    remaining = re.sub(r'\b(19[5-9]\d|20[012]\d)\b', '', remaining).strip()
    remaining = re.sub(r'[؀-ۿ]+', '', remaining).strip()
    parts = remaining.split()
    if parts and len(parts[0]) >= 2:
        return parts[0]
    return None


def _normalize_images(images: Any) -> List[str]:
    if not images:
        return []
    if isinstance(images, str):
        try:
            images = json.loads(images)
        except Exception:
            return []
    if isinstance(images, list):
        return [str(img) for img in images if img]
    return []


def _clean_text(text: Any) -> Optional[str]:
    if not text:
        return None
    cleaned = re.sub(r'\s+', ' ', str(text)).strip()
    return cleaned if cleaned else None


def _build_title(brand: Optional[str], model: Optional[str], year: Optional[int]) -> Optional[str]:
    parts = [str(year or ''), brand or '', model or '']
    title = ' '.join(p for p in parts if p).strip()
    return title if title else None


def _validate_vin(text: Any) -> Optional[str]:
    """
    Return the VIN only if it looks like a real chassis/VIN number.
    Rejects Arabic placeholder phrases like 'متاح عند التواصل'.
    Real VINs are 5–17 alphanumeric characters with no spaces.
    """
    if not text:
        return None
    text = str(text).strip()
    # Reject if it contains 2+ Arabic words (it's a phrase, not a code)
    if len(re.findall(r'[؀-ۿ]+', text)) >= 2:
        return None
    # Reject if suspiciously long or clearly not a code
    if len(text) > 30:
        return None
    return text


def _build_ad_title(
    brand: Optional[str],
    model: Optional[str],
    year: Optional[int],
    listing_type: Optional[str],
    location: Optional[str],
    condition: Optional[str],
) -> Optional[str]:
    """
    Generate a structured Arabic-style listing title from parsed fields.

    Examples:
        Toyota Camry 2019 للبيع في دمشق
        Kia Sportage 2021 جديدة للبيع في حلب
        BMW X5 2020 للإيجار
    """
    parts: List[str] = []

    # Brand + model — avoid duplication when model already starts with brand
    # e.g. brand="Mazda" model="Mazda 6" → emit only "Mazda 6" not "Mazda Mazda 6"
    if brand and model and model.lower().startswith(brand.lower()):
        parts.append(model)
    else:
        if brand:
            parts.append(brand)
        if model:
            parts.append(model)

    # Year
    if year:
        parts.append(str(year))

    # Condition hint — only add for 'جديدة' to keep titles concise
    if condition == 'جديدة':
        parts.append('جديدة')

    # Listing-type suffix (default: للبيع)
    suffix_map = {'بيع': 'للبيع', 'إيجار': 'للإيجار'}
    parts.append(suffix_map.get(listing_type or '', 'للبيع'))

    # Location
    if location:
        parts.append(f'في {location}')

    title = ' '.join(parts).strip()
    return title if title else None
