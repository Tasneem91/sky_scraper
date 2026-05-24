#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Field Normalizer
================
Maps raw scraped values to canonical Sayarti field values defined in sayarti.json.

Rules:
  1. Exact match (after Unicode normalization) → use canonical form from file
  2. Fuzzy match (≥ 75% similarity)            → use closest canonical form
  3. Hard-coded mappings                        → for known structural differences
  4. Fallback                                   → keep raw scraped value as-is

Number fields (price, engine_size, mileage, year, cylinders, seats):
  → digits only, no units, no commas, no currency symbols
"""

import json
import re
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path
from typing import Optional

# ── Load sayarti.json ─────────────────────────────────────────────────────────

_SAYARTI_PATH    = Path(__file__).parent / 'sayarti.json'
_CAR_MODELS_PATH = Path(r'C:\Users\Tasnaim\Downloads\car_models_FULL.json')

# Keys to skip — not real brands
_SKIP_BRANDS = {'ماركة', 'Not set'}

_sayarti: dict = {}

def _load():
    global _sayarti
    if not _sayarti:
        with open(_SAYARTI_PATH, encoding='utf-8') as f:
            _sayarti = json.load(f)
_load()

# ── Load car brands/models from car_models_FULL.json ─────────────────────────

_all_brands:  list = []          # ['أستون مارتن', 'أودي', ...]
_car_models:  dict = {}          # {'أودي': ['A1', 'A3', ...], ...}

def _load_car_models():
    global _all_brands, _car_models
    if _all_brands:
        return
    try:
        with open(_CAR_MODELS_PATH, encoding='utf-8') as f:
            raw: dict = json.load(f)
        for brand, models in raw.items():
            brand = brand.strip()
            if brand in _SKIP_BRANDS or not brand:
                continue
            clean_models = []
            for m in models:
                m = str(m).strip()
                if m and m not in clean_models:
                    clean_models.append(m)
            if brand not in _car_models:
                _car_models[brand] = clean_models
                _all_brands.append(brand)
    except Exception as exc:
        print(f'[normalizer] Could not load car models JSON: {exc}')

_load_car_models()


# ── Arabic text normalization helpers ─────────────────────────────────────────

def _normalize_ar(text: str) -> str:
    """Normalize Arabic string for comparison: strip, unify alef/teh marbuta."""
    text = text.strip()
    # Unify alef variants → ا
    text = re.sub(r'[إأآٱ]', 'ا', text)
    # Unify teh marbuta → ه
    text = text.replace('ة', 'ه')
    # Unify ya → ي
    text = text.replace('ى', 'ي')
    # Remove tatweel
    text = text.replace('ـ', '')
    return text


def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, _normalize_ar(a), _normalize_ar(b)).ratio()


def _best_match(raw: str, candidates: list, threshold: float = 0.75) -> Optional[str]:
    """
    Return the best matching candidate above threshold, or None.
    Also checks substring containment before fuzzy score.
    """
    if not raw:
        return None
    norm_raw = _normalize_ar(raw)

    # 1. Exact match after normalization
    for c in candidates:
        if _normalize_ar(c) == norm_raw:
            return c

    # 2. Substring containment: raw is fully contained inside candidate
    #    (NOT the reverse — avoids short candidates like "ون" matching inside "سونيتا")
    #    Candidate must also be at least as long as raw to be meaningful.
    for c in candidates:
        norm_c = _normalize_ar(c)
        if len(norm_c) >= len(norm_raw) and norm_raw in norm_c:
            return c

    # 3. Fuzzy match
    best_score = 0.0
    best_val   = None
    for c in candidates:
        score = SequenceMatcher(None, norm_raw, _normalize_ar(c)).ratio()
        if score > best_score:
            best_score = score
            best_val   = c
    return best_val if best_score >= threshold else None


def _list_values(key: str) -> list:
    """Get all name values from a sayarti.json list field."""
    return [item['name'] for item in _sayarti.get(key, [])]


# ── Number-only cleaner ───────────────────────────────────────────────────────

def clean_number(raw: str) -> str:
    """
    Extract the first integer from a numeric field.
    '11,800'      → '11800'
    '2000 CC'     → '2000'
    '$15,000'     → '15000'
    '199 خيل'     → '199'
    '199 HP 100'  → '199'   (first number only)
    """
    if not raw:
        return ''
    # Remove commas so '11,800' is treated as one number
    raw = str(raw).replace(',', '')
    m = re.search(r'\d+', raw)
    return m.group(0) if m else ''


# ── Hard-coded mappings ───────────────────────────────────────────────────────
# Used for structural differences that fuzzy matching can't resolve reliably.

_DOORS_MAP = {
    '2': 'بابين',
    'بابين': 'بابين',
    '3': '3 أبواب',
    '4': '4 أبواب',
    '5': '5 أبواب',
}

_FUEL_MAP = {
    'ديزل':       'ديزل / مازوت',
    'مازوت':      'ديزل / مازوت',
    'diesel':     'ديزل / مازوت',
    'petrol':     'بنزين',
    'gasoline':   'بنزين',
    'electric':   'كهربائي',
    'hybrid':     'هجين',
    'كهرباء':     'كهربائي',
}

_DRIVE_MAP = {
    '4x4':         'دفع رباعي',
    '4×4':         'دفع رباعي',
    'awd':         'دفع رباعي',
    '4wd':         'دفع رباعي',
    'fwd':         'دفع أمامي',
    'rwd':         'دفع خلفي',
    'دفع امامي':   'دفع أمامي',
    'دفع خلفي':    'دفع خلفي',
    'دفع رباعي':   'دفع رباعي',
}

_TRANSMISSION_MAP = {
    'automatic':      'أوتوماتيك',
    'auto':           'أوتوماتيك',
    'اوتوماتيك':      'أوتوماتيك',
    'manual':         'يدوي',
    'يدوي':           'يدوي',
    'semi-automatic': 'شبه أوتوماتيك',
    'شبه اوتوماتيك':  'شبه أوتوماتيك',
}

_ORIGIN_MAP = {
    'korean':        'كوري',
    'american':      'أمريكي',
    'european':      'اوروبي',
    'gulf':          'خليجي',
    'canadian':      'كندي',
    'syrian':        'نمرة سورية',
    'امريكي':        'أمريكي',
    'سوري':          'نمرة سورية',
    'سورية':         'نمرة سورية',
    'نمرة سوري':     'نمرة سورية',
    'نمره سورية':    'نمرة سورية',
    'نمره سوريه':    'نمرة سورية',
}

_BODY_MAP = {
    'sedan':       'سيدان',
    'suv':         'SUV',
    'إس يو في':   'SUV',
    'اس يو في':   'SUV',
    'van':         'ڤان',
    'فان':         'ڤان',
    'coupe':       'كوبيه',
    'hatchback':   'هاتشباك',
    'truck':       'نقل',
    'pickup':      'نقل',
    'بيك اب':      'نقل',
    'بيك أب':      'نقل',
}

# Make aliases — map website brand names to canonical Sayarti brand names
_MAKE_MAP = {
    'مرسيدس':        'مرسيدس بنز',
    'mercedes':      'مرسيدس بنز',
    'mercedes-benz': 'مرسيدس بنز',
    'bmw':           'بي ام دبليو',
    'vw':            'فولكس فاجن',
    'volkswagen':    'فولكس فاجن',
    'hyundai':       'هيونداي',
    'kia':           'كيا',
    'toyota':        'تويوتا',
    'nissan':        'نيسان',
    'honda':         'هوندا',
    'chevrolet':     'شيفروليه',
    'chevy':         'شيفروليه',
    'ford':          'فورد',
    'lexus':         'لكزس',
    'audi':          'أودي',
    'mitsubishi':    'ميتسوبيشي',
    'subaru':        'سوبارو',
    'suzuki':        'سوزوكي',
    'mazda':         'مازدا',
    'land rover':    'لاند روفر',
    'cadillac':      'كاديلاك',
    'porsche':       'بورش',
    'maserati':      'مازيراتي',
    'peugeot':       'بيجو',
    'renault':       'رينو',
    'daewoo':        'دايو',
    'chery':         'شيري',
    'haval':         'هافال',
    'mg':            'ام جي',
}

# Model aliases: English/variant name (lowercase) → canonical Sayarti model name
_MODEL_ALIASES = {
    # ── Hyundai ───────────────────────────────────────────────────────────────
    'accent':             'اكسنت',
    'sonata':             'سوناتا',
    'elantra':            'إلنترا',
    'lantra':             'إلنترا',
    'tucson':             'توسان',
    'santa fe':           'سانتا في',
    'santafe':            'سانتافي',
    'maxcruz':            'ماكس كروز',
    'max cruse':          'ماكس كروز',
    'genesis':            'جينسس',
    'starex':             'ستاركس',
    'palisade':           'باليسيد',
    'veloster':           'فوليستر',
    'verna':              'فيرنا',
    'veracruz':           'فيرا كروز',
    'vera cruz':          'فيرا كروز',
    'creta':              'كريتا',
    'kona':               'كونا',
    'staria':             'ستاريا',
    'porter':             'بورتر',
    'ioniq5':             'ايونك 5',
    'ioniq 5':            'ايونك 5',
    'ioniq6':             'أيونيك 6',
    'ioniq 6':            'أيونيك 6',
    'azera':              'ازيرا',
    'avante':             'افانتي',
    'avanti':             'اڤانتي',
    'grandeur':           'غرانديور',
    'equus':              'ايكوس',
    'sentinel':           'سنتينال',
    'click':              'كليك',
    'venue':              'ڤينيو',

    # ── Kia ───────────────────────────────────────────────────────────────────
    'sportage':           'سبورتاج',
    'sorento':            'سورينتو',
    'forte':              'سيراتو',
    'cerato':             'سيراتو',
    'rio':                'ريو',
    'soul':               'سوول',
    'picanto':            'بيكانتو / مورنينغ',
    'morning':            'بيكانتو / مورنينغ',
    'mohave':             'موهاڤي',
    'borrego':            'موهاڤي',
    'carnival':           'كارنڤال',
    'niro':               'نيرو',
    'stinger':            'ستنجر',
    'telluride':          'تيلورايد',
    'sonet':              'سونيت',
    'optima':             'K5 / اوبتيما',
    'ceed':               'سيد',
    'sportswagon':        'سيد',
    'seltos':             'سيلتوس',
    'amanti':             'امانتي',

    # ── Toyota ────────────────────────────────────────────────────────────────
    'camry':              'كامري',
    'corolla':            'كورولا',
    'hilux':              'هايلوكس',
    'land cruiser':       'لاند كروزر',
    'landcruiser':        'لاند كروزر',
    'land cruiser prado': 'برادو',
    'prado':              'برادو',
    'rav4':               'راف 4',
    'rav 4':              'راف 4',
    'prius':              'بريوس',
    'avalon':             'أفالون',
    'highlander':         'هايلاندر',
    'yaris':              'ياريس',
    'tacoma':             'تاكوما',
    'tundra':             'تندرا',
    'c-hr':               'C-HR',

    # ── Nissan ────────────────────────────────────────────────────────────────
    'patrol':             'باترول',
    'altima':             'ألتيما',
    'pathfinder':         'باثفايندر',
    'murano':             'مورانو',
    'armada':             'أرمادا',
    'maxima':             'ماكسيما',
    'sentra':             'سنترا',
    'juke':               'جوك',
    'titan':              'تيتان',
    'rogue':              'روغ',
    'rouge':              'روج',
    'kicks':              'كيكس',
    'versa':              'فيرسا',
    'frontier':           'فرونتير',
    'sunny':              'صاني',
    'leaf':               'لييف',
    'magnite':            'ماجنايت',
    'xterra':             'اكستيرا',
    'sylphy':             'سيلفي',
    'gt-r':               'جي تي آر',

    # ── Chevrolet ─────────────────────────────────────────────────────────────
    'trax':               'تراكس',
    'tahoe':              'تاهو',
    'captiva':            'كابتيفا',
    'aveo':               'أفيو',
    'spark':              'سبارك',
    'malibu':             'ماليبو',
    'silverado':          'سيلفرادو',
    'suburban':           'سوبربان',
    'traverse':           'ترافيرس',
    'sonic':              'سونيك',
    'trailblazer':        'تريل بليزر',
    'trail blazer':       'تريل بليزر',
    'impala':             'إمبالا',
    'cruze':              'كروز',
    'lacetti':            'لاسيتي',
    'optra':              'أوبترا',
    'colorado':           'كولورادو',
    'blazer':             'بلايزر',
    'tusca':              'توسكا',
    'tosca':              'توسكا',
    'montana':            'مونتانا',

    # ── Mercedes-Benz ─────────────────────────────────────────────────────────
    'c-class':            'الفئة C',
    'c class':            'الفئة C',
    'e-class':            'E-class',
    'e class':            'E-class',
    's-class':            'S-class',
    's class':            'S-class',
    'a-class':            'الفئة A',
    'a class':            'الفئة A',
    'b-class':            'الفئة B',
    'b class':            'الفئة B',
    'g-class':            'الفئة G',
    'g class':            'الفئة G',
    'gl-class':           'GLS',
    'gl class':           'GLS',
    'c180':               'الفئة C',
    'c200':               'الفئة C',
    'c250':               'الفئة C',
    'c300':               'الفئة C',
    'c320':               'الفئة C',
    'c350':               'الفئة C',
    'e200':               'E-class',
    'e220':               'E-class',
    'e250':               'E-class',
    'e300':               'E-class',
    'e320':               'E-class',
    'e350':               'E-class',
    'e400':               'E-class',
    's350':               'S-class',
    's450':               'S-class',
    's500':               'S-class',
    's550':               'S-class',
    's600':               'S-class',

    # ── BMW ───────────────────────────────────────────────────────────────────
    '116i': 'الفئة 1', '118i': 'الفئة 1', '120i': 'الفئة 1', '125i': 'الفئة 1', '128i': 'الفئة 1',
    '218i': 'الفئة 2', '220i': 'الفئة 2', '225i': 'الفئة 2', '228i': 'الفئة 2', '230i': 'الفئة 2',
    '316i': 'الفئة 3', '318i': 'الفئة 3', '320i': 'الفئة 3', '325i': 'الفئة 3',
    '328i': 'الفئة 3', '330i': 'الفئة 3', '335i': 'الفئة 3', '340i': 'الفئة 3',
    '420i': 'الفئة 4', '428i': 'الفئة 4', '430i': 'الفئة 4', '435i': 'الفئة 4', '440i': 'الفئة 4',
    '520i': 'الفئة 5', '523i': 'الفئة 5', '525i': 'الفئة 5', '528i': 'الفئة 5',
    '530i': 'الفئة 5', '535i': 'الفئة 5', '540i': 'الفئة 5', '545i': 'الفئة 5',
    '630i': 'الفئة 6', '635i': 'الفئة 6', '640i': 'الفئة 6', '645i': 'الفئة 6', '650i': 'الفئة 6',
    '730i': 'الفئة 7', '735i': 'الفئة 7', '740i': 'الفئة 7', '745i': 'الفئة 7',
    '750i': 'الفئة 7', '760i': 'الفئة 7',

    # ── Honda ─────────────────────────────────────────────────────────────────
    'accord':             'اكورد',
    'civic':              'سيفيك',
    'city':               'سيتي',
    'odyssey':            'أوديسي',
    'pilot':              'بايلوت',
    'jazz':               'جاز',
    'passport':           'باسبورت',
    'ridgeline':          'ريدغلاين',
    'prelude':            'بريلود',
    'insight':            'انسايت',

    # ── Land Rover ────────────────────────────────────────────────────────────
    'range rover sport':  'رنج روفر سبورت',
    'range rover evoque': 'رنج روفر إيفوك',
    'range rover velar':  'رنج روفر فيلار',
    'range rover':        'رينج روفر',
    'discovery sport':    'ديسكفري سبورت',
    'discovery':          'ديسكفري',
    'defender':           'ديفيندر',

    # ── Porsche ───────────────────────────────────────────────────────────────
    'cayenne':            'كايان',
    'panamera':           'Panamera',
    'macan':              'Macan',
    'boxster':            '718 بوكستر',
    'cayman':             '718 كايمان',
    'taycan':             'تايكان',

    # ── Volkswagen ────────────────────────────────────────────────────────────
    'golf':               'جولف',
    'passat':             'باسات',
    'tiguan':             'تيغوان',
    'touareg':            'طوارق',
    'jetta':              'جيتا',
    'polo':               'بولو',
    'bora':               'بورا',
    't-roc':              'تي روك',
    't-cross':            'تي كروس',
    'atlas':              'أطلس',
    'amarok':             'اماروك',

    # ── Mazda ─────────────────────────────────────────────────────────────────
    'mazda 2':            '2',
    'mazda 3':            '3',
    'mazda 6':            '6',
    'mazda2':             '2',
    'mazda3':             '3',
    'mazda6':             '6',
    'cx-3':               'CX-3',
    'cx-5':               'CX-5',
    'cx-9':               'CX-9',
    'cx-30':              'CX-30',
    'tribute':            'تريبيوت',

    # ── Cadillac ──────────────────────────────────────────────────────────────
    'escalade':           'إسكاليد',
    'escalade platinum':  'إسكاليد',
    'eldorado':           'الدورادو',
    'deville':            'ديڤيل',
    'cts':                'CTS',
    'ats':                'ATS',
    'xt5':                'XT5',
    'xt6':                'XT6',

    # ── Maserati ──────────────────────────────────────────────────────────────
    'quattroporte':       'كواتروبورتي',
    'ghibli':             'جيبلي',
    'levante':            'ليفانتي',
    'granturismo':        'جران توريزمو',
    'grecale':            'غريكال',

    # ── Mitsubishi ────────────────────────────────────────────────────────────
    'pajero':             'باجيرو',
    'lancer':             'لانسر',
    'outlander':          'أوتلاندر',
    'eclipse cross':      'اكليبسي كروس',
    'mirage':             'ميراج',

    # ── Peugeot ───────────────────────────────────────────────────────────────
    'peugeot 206':        '206',
    'peugeot 207':        '207',
    'peugeot 208':        '208',
    'peugeot 307':        '307',
    'peugeot 308':        '308',
    'peugeot 405':        '405',
    'peugeot 408':        '408',
    'peugeot 508':        '508',

    # ── Daewoo / Chevrolet ────────────────────────────────────────────────────
    'nexia':              'نكسيا',
    'lacetti':            'لاسيتي',
    'lanos':              'لانوس',
    'nubira':             'نوبيرا',
    'matiz':              'ماتيز',
    'kalos':              'كالوس',
    'leganza':            'ليجانزا',
}

# Brand name prefixes to strip from model strings (e.g. "Toyota Rav4" → "Rav4")
_BRAND_PREFIXES_TO_STRIP = [
    'toyota', 'hyundai', 'kia', 'nissan', 'honda', 'chevrolet',
    'ford', 'volkswagen', 'vw', 'bmw', 'mercedes-benz', 'mercedes',
    'lexus', 'audi', 'porsche', 'peugeot', 'mazda', 'mitsubishi',
    'subaru', 'suzuki', 'land rover', 'saipa', 'daewoo', 'chery',
    'infiniti', 'مرسيدس', 'تويوتا', 'هيونداي', 'كيا', 'نيسان',
]


def _strip_brand_prefix(model: str) -> str:
    """Remove a leading brand name from a model string if present."""
    low = model.strip().lower()
    for prefix in _BRAND_PREFIXES_TO_STRIP:
        if low == prefix:
            return model          # entire string is just the brand — leave as-is
        if low.startswith(prefix + ' ') or low.startswith(prefix + '-'):
            return model[len(prefix):].strip(' -')
    return model


def _strip_lexus_variant(model: str) -> str:
    """Strip trailing number from Lexus model codes: 'IS 300' → 'IS'."""
    m = re.match(r'^([A-Z]{1,3})\s+\d{2,3}$', model.strip(), re.IGNORECASE)
    return m.group(1).upper() if m else model


def _apply_hard_map(raw: str, mapping: dict) -> Optional[str]:
    key = _normalize_ar(raw).lower()
    for k, v in mapping.items():
        if _normalize_ar(k).lower() == key:
            return v
    return None


# ── Per-field normalizer ──────────────────────────────────────────────────────

def normalize(field: str, raw) -> str:
    """
    Normalize a scraped value for a given field name.

    Parameters
    ----------
    field : str   — the sheet column name (e.g. 'fuel_type', 'doors', 'price')
    raw   : any   — the scraped value (will be cast to str)

    Returns
    -------
    str — canonical sayarti value, or cleaned raw value if no match found
    """
    if raw is None:
        return ''
    raw = str(raw).strip()
    if not raw:
        return ''

    # ── Number-only fields ────────────────────────────────────────────────────
    if field in ('price', 'engine_size', 'mileage', 'year', 'seats', 'horsepower'):
        return clean_number(raw)

    if field == 'cylinders':
        # cylinders in sayarti are plain numbers: '4', '6', etc.
        num = clean_number(raw)
        candidates = _list_values('cylinders')
        if num in candidates:
            return num
        return num or raw

    # ── Doors ─────────────────────────────────────────────────────────────────
    if field == 'doors':
        # Try hard map first (handles '2' → 'بابين', '3' → '3 أبواب', etc.)
        result = _apply_hard_map(raw, _DOORS_MAP)
        if result:
            return result
        return _best_match(raw, _list_values('doors')) or raw

    # ── Fuel type ─────────────────────────────────────────────────────────────
    if field == 'fuel_type':
        result = _apply_hard_map(raw, _FUEL_MAP)
        if result:
            return result
        return _best_match(raw, _list_values('fuel_type')) or raw

    # ── Drive / steering ──────────────────────────────────────────────────────
    if field == 'drive_system':
        result = _apply_hard_map(raw, _DRIVE_MAP)
        if result:
            return result
        return _best_match(raw, _list_values('drive_type')) or raw

    # ── Transmission ──────────────────────────────────────────────────────────
    if field == 'transmission':
        result = _apply_hard_map(raw, _TRANSMISSION_MAP)
        if result:
            return result
        return _best_match(raw, _list_values('transmission')) or raw

    # ── Origin / imported ─────────────────────────────────────────────────────
    if field == 'origin':
        result = _apply_hard_map(raw, _ORIGIN_MAP)
        if result:
            return result
        return _best_match(raw, _list_values('imported')) or raw

    # ── Body type ─────────────────────────────────────────────────────────────
    if field == 'body_type':
        result = _apply_hard_map(raw, _BODY_MAP)
        if result:
            return result
        return _best_match(raw, _list_values('vehicle_type')) or raw

    # ── City / location ───────────────────────────────────────────────────────
    if field == 'city':
        return _best_match(raw, _list_values('location')) or raw

    # ── Colors ────────────────────────────────────────────────────────────────
    if field == 'exterior_color':
        return _best_match(raw, _list_values('color')) or raw

    if field == 'interior_color':
        return _best_match(raw, _list_values('interior_color')) or raw

    # ── Condition ─────────────────────────────────────────────────────────────
    if field == 'condition':
        return _best_match(raw, _list_values('condition')) or raw

    # ── Make (brand) ──────────────────────────────────────────────────────────
    if field == 'make':
        if not _all_brands:
            return raw
        # Check hard-coded alias map first
        alias = _apply_hard_map(raw, _MAKE_MAP)
        if alias:
            return alias
        return _best_match(raw, _all_brands) or raw

    # ── Model ─────────────────────────────────────────────────────────────────
    # Note: normalize_car() handles model separately (needs make context).
    # If called standalone, try against all models across all brands.
    if field == 'model':
        all_models = [m for models in _car_models.values() for m in models]
        return _best_match(raw, all_models) or raw

    # ── All other fields: return as-is ────────────────────────────────────────
    return raw


# ── Normalize a full car dict ─────────────────────────────────────────────────

FIELD_MAP = {
    'price':          'price',
    'engine_size':    'engine_size',
    'mileage':        'mileage',
    'year':           'year',
    'seats':          'seats',
    'horsepower':     'horsepower',
    'cylinders':      'cylinders',
    'doors':          'doors',
    'fuel_type':      'fuel_type',
    'transmission':   'transmission',
    'origin':         'origin',
    'body_type':      'body_type',
    'city':           'city',
    'exterior_color': 'exterior_color',
    'interior_color': 'interior_color',
    'condition':      'condition',
    'make':           'make',
    'model':          'model',
}


def normalize_car(car: dict) -> dict:
    """Apply normalize() to all mapped fields in a car dict. Returns a new dict."""
    result = dict(car)

    # Normalize all scalar fields
    for sheet_field, norm_field in FIELD_MAP.items():
        if sheet_field in result and norm_field not in ('make', 'model'):
            result[sheet_field] = normalize(norm_field, result[sheet_field])

    # Normalize make first, then model within that brand's list
    raw_make  = result.get('make', '')
    norm_make = normalize('make', raw_make)
    result['make'] = norm_make

    raw_model = result.get('model', '')
    if raw_model:
        # Step 1: strip leading brand prefix ("Toyota Rav4" → "Rav4")
        clean = _strip_brand_prefix(raw_model)

        # Step 2: for Lexus, strip trailing variant number ("IS 300" → "IS")
        if 'لكزس' in norm_make or 'lexus' in norm_make.lower():
            clean = _strip_lexus_variant(clean)

        # Step 3: check alias map (English → Arabic canonical)
        alias_key = clean.strip().lower()
        norm_model = _MODEL_ALIASES.get(alias_key)

        # Step 4: if no alias, use brand-context fuzzy matching
        if norm_model is None:
            brand_models = _car_models.get(norm_make, [])
            if brand_models:
                norm_model = _best_match(clean, brand_models) or clean
            else:
                all_models = [m for models in _car_models.values() for m in models]
                norm_model = _best_match(clean, all_models) or clean

        result['model'] = norm_model

    return result


# ── Quick test ────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    tests = [
        ('price',          '11,800'),
        ('price',          '$15000'),
        ('engine_size',    '2000 CC'),
        ('engine_size',    '1600 سي سي'),
        ('mileage',        '45,000 كم'),
        ('doors',          '2'),
        ('doors',          '4 أبواب'),
        ('fuel_type',      'ديزل'),
        ('fuel_type',      'بنزين'),
        ('transmission',   'اوتوماتيك'),
        ('origin',         'امريكي'),
        ('origin',         'كوري'),
        ('body_type',      'sedan'),
        ('body_type',      'سيدان'),
        ('city',           'دمشق'),
        ('city',           'حلب'),
        ('exterior_color', 'فضي'),
        ('cylinders',      '4 اسطوانات'),
        ('condition',      'مستعمل'),
        ('make',           'كيا'),
        ('make',           'هيونداي'),
        ('make',           'بي ام دبليو'),
        ('model',          'النترا'),
        ('model',          'كادينزا'),
        ('model',          'سونيتا'),
    ]
    print(f'{"Field":<18} {"Raw":<25} → {"Normalized":<30}')
    print('-' * 78)
    for field, raw in tests:
        result = normalize(field, raw)
        marker = '✓' if result != raw else '~'
        print(f'{field:<18} {raw:<25} → {result:<30} {marker}')

    # Test full car normalization (make + model together)
    print('\n── normalize_car() make+model test ──')
    cars = [
        {'make': 'كيا',      'model': 'كادينزا'},
        {'make': 'هيونداي',  'model': 'النترا'},
        {'make': 'هيونداي',  'model': 'سونيتا'},   # should → سوناتا (not سونيت)
        {'make': 'تويوتا',   'model': 'كامري'},
        {'make': 'نيسان',    'model': 'صاني'},
    ]
    for c in cars:
        n = normalize_car(c)
        print(f"  {c['make']} / {c['model']}  →  {n['make']} / {n['model']}")
