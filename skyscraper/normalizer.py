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
_CAR_MODELS_PATH = Path(r'C:\Users\alkha\OneDrive\Desktop\SKYSCRAPER\sky_scraper\skyscraper\car_models_FULL.json')

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


# ── Unknown values tracking ───────────────────────────────────────────────────
# Every time the normalizer can't match a value it falls back to the raw string.
# Those raw strings are saved here so you can review and extend the alias maps.

_UNKNOWN_FILE = Path(__file__).parent / 'unknown_values.json'
_unknown: dict = {}


def _load_unknown():
    global _unknown
    try:
        if _UNKNOWN_FILE.exists():
            with open(_UNKNOWN_FILE, encoding='utf-8') as f:
                _unknown = json.load(f)
    except Exception:
        _unknown = {}


_load_unknown()


def _record_unknown(field: str, value: str) -> None:
    """Append an unmatched value to unknown_values.json for periodic review."""
    if not field or not value:
        return
    value = value.strip()
    if not value:
        return
    if field not in _unknown:
        _unknown[field] = []
    if value not in _unknown[field]:
        _unknown[field].append(value)
        try:
            with open(_UNKNOWN_FILE, 'w', encoding='utf-8') as f:
                json.dump(_unknown, f, ensure_ascii=False, indent=2)
        except Exception:
            pass


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
    'صينية':         'صيني',
    'يابانية':       'ياباني',
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
    'بيك أب':       'نقل',
    'شاحنة خفيفة':  'نقل',
    'مركبة ثقيلة':  'نقل',
    'باص':           'نقل',
    'شاحنة بيك أب': 'نقل',
    'شاحنة بيكآب':  'نقل',
    'كروس أوفر':    'كروس',
    'ستيشن واجن':   'واجن',
    'كشف':           'كوبيه',
    'مايكرو فان':   'ميني فان',
    'فاتسباك':      'هاتشبك',
    'فاستباك':      'هاتشبك',
}

# Make aliases — map website brand names to canonical Sayarti brand names
_MAKE_MAP = {
    'مرسيدس':        'مرسيدس',
    'مرسيدس بنز':    'مرسيدس',
    'mercedes':      'مرسيدس',
    'mercedes-benz': 'مرسيدس',
    'سامسونغ':       'رينو سامسونج',
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

    # ── BYD (بي واي دي) ───────────────────────────────────────────────────────
    # Arabic models in car_models_FULL.json — cross-script fuzzy matching
    # can't reach them from English input, so we map explicitly.
    # Arabic names verified directly from car_models_FULL.json.
    'qin plus':           'كين بلس',
    'han':                'هان',
    'tang':               'تانغ',
    'song plus':          'سونغ بلس',
    'dolphin':            'دولفين',
    'seal':               'سيل',
    'seal 05':            'سيل05',
    'seagull':            'سيجل',
    'shark':              'شارك',
    'destroyer':          'دستروير',       # ← دستروير (not ديستروير)
    'destroyer 05':       'دستروير 05',
    'yuan plus':          'يان بلس',       # ← يان (not يوان)
    'freegate 07':        'فريغات 07',

    # ── Chery (شيري) ─────────────────────────────────────────────────────────
    # File only has one generic entry: تيغو (no numbered variants)
    'tiggo':              'تيغو',

    # ── Haval (هافال) ─────────────────────────────────────────────────────────
    'jolion':             'جوليون',
    'bigdog':             'بيغ دوغ',
    'big dog':            'بيغ دوغ',

    # ── Jeep ──────────────────────────────────────────────────────────────────
    'wrangler':           'رانجلر',
    'gladiator':          'غلادييتر',
    'grand cherokee':     'جراند شيروكي',
    'cherokee':           'شيروكي',
    'grand wagoneer':     'جراند واجونير',
    'wagoneer':           'واجونير',
    'renegade':           'رينيغارد',
    'compass':            'كامبوس',
    'avenger':            'افينجر',
    'recon':              'ريكون',

    # ── Ford ──────────────────────────────────────────────────────────────────
    'explorer':           'إكسبلورر',
    'expedition':         'إكسبيديشن',
    'ecosport':           'إيكو سبورت',
    'eco sport':          'إيكو سبورت',
    'escape':             'اسكيب',
    'edge':               'ايدج',
    'bronco sport':       'برونكو سبورت',
    'bronco':             'برونكو',
    'transit connect':    'ترانزيت كونكت',
    'transit':            'ترانزيت',
    'ranger':             'رانجر',
    'focus':              'فوكس',
    'fiesta':             'فيستا',
    'fusion':             'فيوجن',
    'kuga':               'كوجا',
    'maverick':           'ماڤيريك',
    'mustang mach-e':     'موستانج ماخ إي',
    'mustang mach e':     'موستانج ماخ إي',
    'mustang':            'موستانج',
    'mondeo':             'مونديو',

    # ── Opel / Vauxhall ───────────────────────────────────────────────────────
    'astra':              'أسترا',
    'omega':              'أوميغا',
    'insignia':           'انستيغيا',
    'grandland':          'جراندلاند',
    'crossland':          'كروسلاند',
    'corsa':              'كورسا',
    'mokka':              'موكا',
    'vectra':             'فيكترا',
    'vivaro':             'فيفارو',
    'movano':             'موفانو',

    # ── Renault ───────────────────────────────────────────────────────────────
    'arkana':             'أركانا',
    'austral':            'اوسترال',
    'talisman':           'تاليسمان',
    'traffic':            'ترافيك',
    'trafic':             'ترافيك',
    'zoe':                'زوي',
    'symbol':             'سيمبول',
    'fluence':            'فلوينس',
    'captur':             'كابتور',
    'capture':            'كابتشر',
    'kangoo':             'كانجو',
    'clio':               'كليو',
    'koleos':             'كوليوس',
    'master':             'ماستر',
    'megane':             'ميجان',

    # ── GMC ───────────────────────────────────────────────────────────────────
    'acadia':             'أكاديا',
    'terrain':            'تيريان',
    'sierra':             'سييرا',
    'canyon':             'كانيون',
    'yukon':              'يوكون',

    # ── Chrysler ──────────────────────────────────────────────────────────────
    'pacifica':           'باسيفيكا',
    'voyager':            'فوييجر',

    # ── Geely ─────────────────────────────────────────────────────────────────
    'atlas':              'أطلس',
    'okavango':           'أوكافانغو',
    'emgrand':            'إمجراند',
    'preface':            'بريفايس',
    'coolray':            'كولراي',
    'tugella':            'توجيلا',
    'azkarra':            'ازكارا',
}

# City overrides — map sub-city / small-town names to their parent region.
# Applied before fuzzy match so these explicit mappings take priority.
_CITY_MAP = {
    'النبك':    'ريف دمشق',
    'محردة':    'ريف دمشق',
    'دوما':     'ريف دمشق',
    'السلمية':  'حماه',
    'أعزاز':    'حلب',
    'الطبقة':   'الرقة',
    'صافيتا':   'طرطوس',
}

# Model aliases conditioned on make — checked before the global _MODEL_ALIASES.
# Keys are lowercase (same convention as _MODEL_ALIASES).
_MODEL_MAKE_ALIASES: dict = {
    'أودي': {
        'a5 coupe':    'A5',
        'a6 3.0 tfsi': 'A6',
        'a3 sedan':    'A3',
        'a5 2.0t':     'A5',
        's8':          'نماذج RS',
        'a7 3.0t':     'A7',
        'q7 3.0 tfsi': 'Q7',
        'a8 3.0 tdi':  'A8',
        'a4 2.0t':     'A4',
    },
    'بروتون': {
        'بروتون ساجا':  'ساجا',
        'proton gen-2': 'جين 2',
    },
    'بي ام دبليو': {
        '130i':     'الفئة 1',
        '316':      'الفئة 3',
        '320d':     'الفئة 3',
        '420d':     'الفئة 4',
        '520d':     'الفئة 5',
        '530d':     'الفئة 5',
        '550i':     'الفئة 5',
        'm3':       'M',
        'm3 e36':   'M',
        'm5':       'M',
        'm5 e34':   'M',
        'series 7': 'الفئة 7',
        'x3 m':     'XM',
        'x6 m':     'XM',
    },
    'تسلا': {
        'تسلا مودل ي': 'الموديل Y',
    },
    'الفا روميو': {
        'جيوليتتا': 'جولييتا',
    },
    'تويوتا': {
        'افانزا': 'أفانزا',
        'الفارد': 'ألفارد',
        'هياك':   'هايس',
    },
    'جاكوار': {
        'jaguar 5': 'جاكوار 5',
    },
    'جيلي': {
        'geely ck1': 'CK1',
        'geely ck2': 'CK2',
    },
    'داسيا': {
        'لوجان': 'لوغان',
    },
    'دودج': {
        'ram': 'رام',
    },
    'سكودا': {
        'سوبرب':         'سوبيرب',
        'وكتافيا':       'اوكتافيا',
        'وكتافيا لجانك': 'اوكتافيا',
    },
    'سوبارو': {
        'يمبرزا': 'امبريزا',
    },
    'سوزوكي': {
        'التو': 'ألتو',
    },
    'سيات': {
        'لون': 'ليون',
    },
    'سيتروين': {
        'برلينجو': 'بيرلينجو',
    },
    'شيري': {
        'tiggo 3': 'تيغو',
    },
    'شيفروليه': {
        'silverado 1500': 'سيلفارادو',
        'silverado z71':  'سيلفارادو',
        'tahoe z71':      'تاهو',
        'تاهو برمير':     'تاهو',
        'ماليبو لت':      'ماليبو',
    },
    'فولفو': {
        'volvo v40': 'V40',
    },
    'فيات': {
        'سينا': 'سينيا',
    },
    'كيا': {
        'سبورتاج جت-لين': 'سبورتاج',
        'سدونا':           'سيدونا',
    },
    'مرسيدس': {
        '190':        'الفئة C',
        '200':        'الفئة C',
        '240':        'الفئة C',
        '300':        'الفئة E',
        '320':        'الفئة E',
        '350':        'الفئة S',
        '400':        'الفئة S',
        '420':        'الفئة S',
        '450':        'الفئة S',
        '500':        'الفئة S',
        '600':        'الفئة S',
        's-class':    'الفئة S',
        'م-كلاسس':    'الفئة M',
        'amg a 45':   'AMG',
        'amg c 43':   'AMG',
        'amg c 63':   'AMG',
        'amg e 43':   'AMG',
        'amg gle 53': 'AMG',
        'amg s 63':   'AMG',
        'amg sl 55':  'AMG',
    },
    'ميني': {
        'كوبر':       'كومنتري مان',
        'كوبر س':     'كومنتري مان',
        'كوونتريمان': 'كومنتري مان',
    },
    'نيسان': {
        'كس-ترايل': 'اكس ترايل',
    },
    'هوندا': {
        'h-1 grand starex': 'ستاركس',
    },
    'هيونداي': {
        'سانتافي':       'سانتا في',
        'جنسيس كووب':    'جينسس',
        'فلوستر ن':      'فوليستر',
        'كسكل':          'إكسل',
        'لافستا':        'لافيستا',
        'لانترا هيبريد': 'هيونداي إلنترا',
        'يونيك':         'أيونيك',
    },
}

# When the canonical make name (output) differs from the key in car_models_FULL.json,
# map canonical → file key so model lookup still works correctly.
_MAKE_FILE_KEY: dict = {
    'مرسيدس': 'مرسيدس بنز',
}

# Post-normalization make overrides — applied after alias+fuzzy match.
# Catches cases where fuzzy match returns a file brand name that differs
# from the canonical output name we want (e.g. fuzzy → 'مرسيدس بنز' → 'مرسيدس').
_MAKE_POST_MAP: dict = {
    'مرسيدس بنز': 'مرسيدس',
}

# Brand name prefixes to strip from model strings (e.g. "Toyota Rav4" → "Rav4")
_BRAND_PREFIXES_TO_STRIP = [
    'toyota', 'hyundai', 'kia', 'nissan', 'honda', 'chevrolet',
    'ford', 'volkswagen', 'vw', 'bmw', 'mercedes-benz', 'mercedes',
    'lexus', 'audi', 'porsche', 'peugeot', 'mazda', 'mitsubishi',
    'subaru', 'suzuki', 'land rover', 'saipa', 'daewoo', 'chery',
    'infiniti', 'مرسيدس', 'تويوتا', 'هيونداي', 'كيا', 'نيسان',
]


def _is_arabic(text: str) -> bool:
    """Returns True if the string contains Arabic characters."""
    return bool(re.search(r'[؀-ۿ]', text))


# Latin → Arabic transliteration table (digraphs before single chars)
_LATIN_TO_AR = [
    ('ch', 'تش'), ('sh', 'ش'), ('th', 'ث'), ('ph', 'ف'),
    ('gh', 'غ'), ('kh', 'خ'), ('ck', 'ك'), ('qu', 'كو'),
    ('oo', 'و'),  ('ee', 'ي'),
    ('a', 'ا'), ('b', 'ب'), ('c', 'ك'), ('d', 'د'),
    ('e', ''),   ('f', 'ف'), ('g', 'ج'), ('h', 'ه'),
    ('i', 'ي'), ('j', 'ج'), ('k', 'ك'), ('l', 'ل'),
    ('m', 'م'), ('n', 'ن'), ('o', 'و'), ('p', 'ب'),
    ('q', 'ك'), ('r', 'ر'), ('s', 'س'), ('t', 'ت'),
    ('u', 'و'), ('v', 'ف'), ('w', 'و'), ('x', 'كس'),
    ('y', 'ي'), ('z', 'ز'),
]


def _latin_to_arabic(text: str) -> str:
    """
    Rough Latin → Arabic transliteration for unknown car model names.
    Not perfect, but produces readable Arabic text instead of leaving
    the name in English.  Result is still recorded in unknown_values.json
    so aliases can be added for models that need exact canonical names.
    """
    result = ''
    low = text.strip().lower()
    i = 0
    while i < len(low):
        ch = low[i]
        if not ch.isalpha():
            result += ch
            i += 1
            continue
        matched = False
        for latin, arabic in _LATIN_TO_AR:
            if low[i:i + len(latin)] == latin:
                result += arabic
                i += len(latin)
                matched = True
                break
        if not matched:
            i += 1
    return result.strip()


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


def _is_short_or_numeric(text: str) -> bool:
    """
    Returns True for model codes that must stay as ENGLISH CAPITALS and must NOT
    be fuzzy-matched into Arabic names.

    Rules (from ROADMAP §6):
      • 3 characters or fewer  → e.g. IS, X5, GLE, C63 → too short to fuzzy-match
      • Contains any digit     → e.g. C63, 330i, XT6, K5 — alphanumeric codes

    Known named models (rio, golf, …) are handled earlier via _MODEL_ALIASES so
    they never reach this function.
    """
    t = text.strip()
    return len(t) <= 3 or bool(re.search(r'\d', t))


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
        matched = _best_match(raw, _list_values('fuel_type'))
        if matched:
            return matched
        _record_unknown('fuel_type', raw)
        return raw

    # ── Drive / steering ──────────────────────────────────────────────────────
    if field == 'drive_system':
        result = _apply_hard_map(raw, _DRIVE_MAP)
        if result:
            return result
        matched = _best_match(raw, _list_values('drive_type'))
        if matched:
            return matched
        _record_unknown('drive_system', raw)
        return raw

    # ── Transmission ──────────────────────────────────────────────────────────
    if field == 'transmission':
        result = _apply_hard_map(raw, _TRANSMISSION_MAP)
        if result:
            return result
        matched = _best_match(raw, _list_values('transmission'))
        if matched:
            return matched
        _record_unknown('transmission', raw)
        return raw

    # ── Origin / imported ─────────────────────────────────────────────────────
    if field == 'origin':
        result = _apply_hard_map(raw, _ORIGIN_MAP)
        if result:
            return result
        matched = _best_match(raw, _list_values('imported'))
        if matched:
            return matched
        _record_unknown('origin', raw)
        return raw

    # ── Body type ─────────────────────────────────────────────────────────────
    if field == 'body_type':
        result = _apply_hard_map(raw, _BODY_MAP)
        if result:
            return result
        matched = _best_match(raw, _list_values('vehicle_type'))
        if matched:
            return matched
        _record_unknown('body_type', raw)
        return raw

    # ── City / location ───────────────────────────────────────────────────────
    if field == 'city':
        result = _apply_hard_map(raw, _CITY_MAP)
        if result:
            return result
        matched = _best_match(raw, _list_values('location'))
        if matched:
            return matched
        _record_unknown('city', raw)
        return raw

    # ── Colors ────────────────────────────────────────────────────────────────
    if field == 'exterior_color':
        matched = _best_match(raw, _list_values('color'))
        if matched:
            return matched
        _record_unknown('exterior_color', raw)
        return raw

    if field == 'interior_color':
        matched = _best_match(raw, _list_values('interior_color'))
        if matched:
            return matched
        _record_unknown('interior_color', raw)
        return raw

    # ── Condition ─────────────────────────────────────────────────────────────
    if field == 'condition':
        matched = _best_match(raw, _list_values('condition'))
        if matched:
            return matched
        _record_unknown('condition', raw)
        return raw

    # ── Make (brand) ──────────────────────────────────────────────────────────
    if field == 'make':
        # Alias map always takes priority, even when the JSON file is absent
        alias = _apply_hard_map(raw, _MAKE_MAP)
        if alias:
            return alias
        if not _all_brands:
            return raw
        matched = _best_match(raw, _all_brands)
        if matched:
            return matched
        _record_unknown('make', raw)
        return raw

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
    norm_make = _MAKE_POST_MAP.get(norm_make, norm_make)
    result['make'] = norm_make

    raw_model = result.get('model', '')
    if raw_model:
        # Step 1: strip leading brand prefix ("Toyota Rav4" → "Rav4")
        clean = _strip_brand_prefix(raw_model)

        # Step 2: for Lexus, strip trailing variant number ("IS 300" → "IS")
        if 'لكزس' in norm_make or 'lexus' in norm_make.lower():
            clean = _strip_lexus_variant(clean)

        # Step 3: check alias maps — make-specific first, then global
        alias_key = clean.strip().lower()
        norm_model = (
            _apply_hard_map(clean, _MODEL_MAKE_ALIASES.get(norm_make, {}))
            or _MODEL_ALIASES.get(alias_key)
        )

        if norm_model is not None:
            # Known alias → use canonical name from alias map
            result['model'] = norm_model

        else:
            # Step 4: fuzzy match against car_models_FULL.json (primary reference).
            # The file's form is always canonical — Arabic or English, whatever is
            # stored there.  We check the file BEFORE applying any fallback rule.
            file_key = _MAKE_FILE_KEY.get(norm_make, norm_make)
            brand_models = _car_models.get(file_key, [])
            if brand_models:
                matched = _best_match(clean, brand_models)
            else:
                all_models = [m for models in _car_models.values() for m in models]
                matched = _best_match(clean, all_models)

            if matched:
                # Found in car_models_FULL.json → use the file's canonical form
                result['model'] = matched

            elif _is_short_or_numeric(clean):
                # Step 4b (ROADMAP §6): NOT in file AND short code / has digit
                # → keep as ENGLISH CAPITALS (e.g. X5, GLE, C63, K5).
                # Only reached when the file has no matching entry at all.
                result['model'] = clean.upper()

            elif _is_arabic(clean):
                # Already Arabic but no match in file → keep as-is
                _record_unknown('model', clean)
                result['model'] = clean

            else:
                # English full word not in file → transliterate to Arabic.
                # Result is approximate; original is saved in unknown_values.json
                # so the correct alias can be added later if needed.
                ar = _latin_to_arabic(clean)
                _record_unknown('model', clean)
                result['model'] = ar if ar else clean

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
