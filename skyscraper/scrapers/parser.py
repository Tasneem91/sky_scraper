"""
Shared Parsing & Normalization Layer — Stage 2 of the two-stage pipeline.

Each scraper produces a raw dict (dumb extraction, no interpretation).
This module is the single place that interprets raw data into the unified schema.

DESIGN RULES:
  • Never import from individual scrapers (no circular deps)
  • All field interpretation lives here, zero in scrapers
  • Prefer specs_raw (structured) over title/description (free text)
  • Return None for missing fields — never return "N/A" or empty string
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
    'الموديل':        'brand',           # Toyota, Kia, etc.
    'الماركة':        'model',           # Camry, Sportage, etc.
    'السنة':          'year',
    'الكيلومترات':    'mileage',
    'نوع الوقود':     'fuel_type',
    'المحرك':         'engine',
    'ناقل الحركة':    'transmission',
    'اللون الخارجي':  'color',
    'اللون الداخلي':  'interior_color',
    'الأسطوانات':     'cylinders',
    'المفاتيح':       'keys',
    'المقاعد':        'seats',
    'نظام الدفع':     'drive_system',
    'المصدر':         'origin',
    'المواصفات':      'specs_category',
    'الحالة':         'condition',
    'نوع الهيكل':     'body_type',
}

# Generic map for all other sites (standard Arabic label naming)
GENERIC_SPEC_MAP = {
    'الماركة':             'brand',
    'الموديل':             'model',
    'السنة':               'year',
    'سنة الصنع':           'year',
    'الكيلومترات':         'mileage',
    'المسافة المقطوعة':    'mileage',
    'نوع الوقود':          'fuel_type',
    'الوقود':              'fuel_type',
    'المحرك':              'engine',
    'حجم المحرك':          'engine',
    'ناقل الحركة':         'transmission',
    'ناقل':                'transmission',
    'اللون':               'color',
    'اللون الخارجي':       'color',
    'اللون الداخلي':       'interior_color',
    'الأسطوانات':          'cylinders',
    'عدد الأسطوانات':      'cylinders',
    'المقاعد':             'seats',
    'عدد المقاعد':         'seats',
    'نظام الدفع':          'drive_system',
    'نوع الدفع':           'drive_system',
    'المصدر':              'origin',
    'الحالة':              'condition',
    'نوع الهيكل':          'body_type',
    'الموقع':              'location',
    'المدينة':             'location',
    'المحافظة':            'location',
    'المنطقة':             'location',
}


# ============================================================================
# Normalization keyword maps  (value = normalized output)
# ============================================================================

FUEL_KEYWORDS = {
    'بنزين':    'بنزين',
    'gasoline': 'بنزين',
    'petrol':   'بنزين',
    'ديزل':     'ديزل',
    'diesel':   'ديزل',
    'غاز':      'غاز',
    'lpg':      'غاز',
    'كهرباء':   'كهربائي',
    'كهربائي':  'كهربائي',
    'electric': 'كهربائي',
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
    'جديدة':     'جديدة',
    'جديد':      'جديدة',
    'new':       'جديدة',
    'مستعملة':   'مستعملة',
    'مستعمل':    'مستعملة',
    'مستخدمة':   'مستعملة',
    'used':      'مستعملة',
}

LISTING_TYPE_MAP = {
    'sell':    'بيع',
    'rent':    'إيجار',
    'بيع':     'بيع',
    'إيجار':   'إيجار',
    'للبيع':   'بيع',
    'للإيجار': 'إيجار',
}

# Common car brands (Arabic aliases → canonical English name)
BRAND_ALIASES = {
    'تويوتا': 'Toyota',
    'كيا':    'Kia',
    'هيونداي':'Hyundai',
    'هونداي': 'Hyundai',
    'نيسان':  'Nissan',
    'هوندا':  'Honda',
    'ميتسوبيشي': 'Mitsubishi',
    'مرسيدس': 'Mercedes',
    'بي ام دبليو': 'BMW',
    'اودي':   'Audi',
    'فولكس':  'Volkswagen',
    'فورد':   'Ford',
    'شيفروليه': 'Chevrolet',
    'جي ام سي': 'GMC',
    'دودج':   'Dodge',
    'جيب':    'Jeep',
    'لاند روفر': 'Land Rover',
    'لكزس':   'Lexus',
    'مازدا':  'Mazda',
    'سوزوكي': 'Suzuki',
    'بيجو':   'Peugeot',
    'رينو':   'Renault',
    'اوبل':   'Opel',
    'فولفو':  'Volvo',
    'فيات':   'Fiat',
    'انفينيتي': 'Infiniti',
}

KNOWN_BRANDS = [
    'Toyota', 'Kia', 'Hyundai', 'Nissan', 'Honda', 'Mitsubishi',
    'Mercedes', 'BMW', 'Audi', 'Volkswagen', 'Ford', 'Chevrolet',
    'GMC', 'Dodge', 'Jeep', 'Land Rover', 'Lexus', 'Mazda', 'Subaru',
    'Suzuki', 'Peugeot', 'Renault', 'Skoda', 'SEAT', 'Opel', 'Volvo',
    'Fiat', 'Alfa', 'Citroen', 'Infiniti', 'Acura', 'Lincoln',
    'Cadillac', 'Buick', 'Chrysler', 'Tesla', 'BYD', 'Geely', 'Chery',
    'Haval', 'MG', 'Isuzu', 'Datsun', 'Porsche', 'Range',
]


# ============================================================================
# Main entry point
# ============================================================================

def parse(raw: Dict[str, Any], spec_map: Dict[str, str] = None) -> Dict[str, Any]:
    """
    Convert a raw extraction dict into the unified schema.

    Args:
        raw: Output of each scraper's raw extraction stage. Expected keys:
               title_raw, description_raw, specs_raw, price_raw, location_raw,
               images, seller_raw, phones_raw, phone, whatsapp,
               source, ad_url, ad_id, id, scraped_at, listing_type, posted_date
        spec_map: Label→field mapping. Defaults to GENERIC_SPEC_MAP.
                  Pass CARSY_SPEC_MAP for carsy.app (reversed brand/model).

    Returns:
        Unified schema dict. All unknown/missing fields are None (not 'N/A').
    """
    if spec_map is None:
        spec_map = GENERIC_SPEC_MAP

    specs = raw.get('specs_raw') or {}
    title = (raw.get('title_raw') or '').strip()
    desc  = (raw.get('description_raw') or '').strip()
    combined = f"{title} {desc}".lower()

    # ----- Map spec labels to schema fields -----
    mapped: Dict[str, Any] = {}
    for label, value in specs.items():
        field = spec_map.get(label)
        if field and value:
            mapped[field] = str(value).strip()

    # ----- Brand -----
    brand = mapped.get('brand') or _extract_brand(title)

    # ----- Model -----
    model = mapped.get('model') or _extract_model(title, brand)

    # ----- Year -----
    year = _parse_year(mapped.get('year')) or _extract_year_from_text(title)

    # ----- Mileage -----
    mileage = mapped.get('mileage') or _extract_mileage(desc) or _extract_mileage(title)

    # ----- Fuel type -----
    fuel_type = mapped.get('fuel_type') or _detect_keyword(combined, FUEL_KEYWORDS)

    # ----- Transmission -----
    transmission = mapped.get('transmission') or _detect_keyword(combined, TRANSMISSION_KEYWORDS)

    # ----- Condition -----
    condition = mapped.get('condition') or _detect_keyword(combined, CONDITION_KEYWORDS)

    # ----- Location -----
    location = (
        mapped.get('location')
        or _clean_text(raw.get('location_raw'))
        or None
    )

    # ----- Price -----
    price_raw = raw.get('price_raw') or ''
    price = _parse_price(price_raw)

    # ----- Images -----
    images = _normalize_images(raw.get('images'))

    # ----- Listing type -----
    listing_type = LISTING_TYPE_MAP.get(
        str(raw.get('listing_type', 'sell')).lower(), 'بيع'
    )

    # ----- Title -----
    title_final = title or _build_title(brand, model, year)

    # ----- Contact -----
    phones = raw.get('phones_raw') or []
    phone = (phones[0] if phones else None) or raw.get('phone')
    whatsapp = raw.get('whatsapp')

    return {
        # Technical metadata
        'scraped_at':     raw.get('scraped_at') or datetime.now().isoformat(),
        'source':         raw.get('source') or '',
        'id':             raw.get('id') or '',
        'ad_id':          raw.get('ad_id'),
        'ad_url':         raw.get('ad_url'),
        'link':           raw.get('ad_url'),
        'listing_type':   listing_type,

        # Content
        'title':          title_final or None,
        'description':    _clean_text(desc) or None,
        'images':         json.dumps(images, ensure_ascii=False),
        'primary_image':  images[0] if images else None,
        'image_count':    len(images),

        # Car attributes — structured fields first, free-text fallback
        'brand':          brand,
        'model':          model,
        'category':       mapped.get('specs_category') or mapped.get('category'),
        'year':           year,
        'mileage':        mileage,
        'condition':      condition,
        'body_type':      mapped.get('body_type'),
        'fuel_type':      fuel_type,
        'transmission':   transmission,
        'engine':         mapped.get('engine'),
        'cylinders':      mapped.get('cylinders'),
        'color':          mapped.get('color'),
        'interior_color': mapped.get('interior_color'),
        'drive_system':   mapped.get('drive_system'),
        'seats':          mapped.get('seats'),
        'keys':           mapped.get('keys'),
        'origin':         mapped.get('origin'),

        # Price
        'price':          price,
        'price_raw':      price_raw or None,

        # Location
        'location':       location,

        # Seller / contact
        'seller_name':    raw.get('seller_name'),
        'phone':          phone,
        'whatsapp':       whatsapp,

        # Date
        'posted_date':    raw.get('posted_date'),
    }


# ============================================================================
# Helper — price
# ============================================================================

def _parse_price(text: str) -> Optional[float]:
    """Extract numeric price from any string. Returns None if unreadable."""
    if not text:
        return None
    try:
        cleaned = re.sub(r'[^\d.]', '', str(text))
        return float(cleaned) if cleaned else None
    except (ValueError, TypeError):
        return None


# ============================================================================
# Helper — year
# ============================================================================

def _parse_year(text: Any) -> Optional[int]:
    """Parse a year value (already extracted, may need cleaning)."""
    if not text:
        return None
    m = re.search(r'\b(19[5-9]\d|20[012]\d)\b', str(text))
    return int(m.group(0)) if m else None


def _extract_year_from_text(text: str) -> Optional[int]:
    """Find a year (1950–2029) anywhere in free text."""
    if not text:
        return None
    m = re.search(r'\b(19[5-9]\d|20[012]\d)\b', text)
    return int(m.group(0)) if m else None


# ============================================================================
# Helper — mileage
# ============================================================================

def _extract_mileage(text: str) -> Optional[str]:
    """
    Find mileage patterns like:
      '225,000 كم', '85000 km', '150,000', '+200,000'
    Returns raw mileage string as found.
    """
    if not text:
        return None
    # Pattern: optional + sign, digits with optional commas, optional unit
    m = re.search(
        r'(\+?[\d,]+)\s*(كم|km|كيلو|كيلومتر)?',
        text,
        re.IGNORECASE
    )
    if m:
        num_str = m.group(1).replace(',', '')
        try:
            num = int(num_str)
            # Sanity check: valid mileage is 100–1,000,000
            if 100 <= num <= 1_000_000:
                unit = m.group(2) or 'كم'
                return f"{m.group(1)} {unit}"
        except ValueError:
            pass
    return None


# ============================================================================
# Helper — keyword detection (fuel, transmission, condition)
# ============================================================================

def _detect_keyword(text: str, keyword_map: Dict[str, str]) -> Optional[str]:
    """
    Search text for any keyword in keyword_map and return its normalized value.
    text should already be lowercased by caller.
    """
    if not text:
        return None
    for keyword, normalized in keyword_map.items():
        if keyword.lower() in text:
            return normalized
    return None


# ============================================================================
# Helper — brand / model extraction from free text
# ============================================================================

def _extract_brand(title: str) -> Optional[str]:
    """
    Extract brand name from title.

    Strategy:
    1. Match known brand names (English) — most reliable
    2. Translate Arabic brand aliases
    3. Find first Latin-script word as fallback
    """
    if not title:
        return None

    # 1. Known English brand list (case-insensitive word boundary)
    for brand in KNOWN_BRANDS:
        if re.search(r'\b' + re.escape(brand) + r'\b', title, re.IGNORECASE):
            return brand

    # 2. Arabic brand alias lookup
    for arabic, english in BRAND_ALIASES.items():
        if arabic in title:
            return english

    # 3. First Latin-alphabet word (e.g. "كيا Kia Sportage" → "Kia")
    m = re.search(r'\b([A-Za-z][A-Za-z\-]{1,})\b', title)
    if m:
        candidate = m.group(1)
        # Skip common non-brand words
        if candidate.lower() not in ('used', 'new', 'for', 'sale', 'rent', 'the', 'and', 'with'):
            return candidate

    return None


def _extract_model(title: str, brand: Optional[str]) -> Optional[str]:
    """
    Extract model from title after removing the brand name and year.
    Returns first remaining word that looks like a model name.
    """
    if not title or not brand:
        return None
    remaining = re.sub(re.escape(brand), '', title, flags=re.IGNORECASE).strip()
    remaining = re.sub(r'\b(19[5-9]\d|20[012]\d)\b', '', remaining).strip()
    # Remove Arabic words (brands on Arabic sites often have Arabic brand text)
    remaining = re.sub(r'[؀-ۿ]+', '', remaining).strip()
    parts = remaining.split()
    if parts and len(parts[0]) >= 2:
        return parts[0]
    return None


# ============================================================================
# Helper — images
# ============================================================================

def _normalize_images(images: Any) -> List[str]:
    """Accept list, JSON string, or None. Returns clean list of URL strings."""
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


# ============================================================================
# Helper — text cleaning
# ============================================================================

def _clean_text(text: Any) -> Optional[str]:
    """
    Normalize whitespace and newlines.
    Collapses multiple spaces/newlines to a single space.
    Returns None for empty/None input.
    """
    if not text:
        return None
    cleaned = re.sub(r'\s+', ' ', str(text)).strip()
    return cleaned if cleaned else None


# ============================================================================
# Helper — title builder
# ============================================================================

def _build_title(brand: Optional[str], model: Optional[str], year: Optional[int]) -> Optional[str]:
    """Compose a title from known parts if title_raw is empty."""
    parts = [str(year or ''), brand or '', model or '']
    title = ' '.join(p for p in parts if p).strip()
    return title if title else None
