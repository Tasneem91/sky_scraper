#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generate Sayarti-compatible CSV for WP All Import
==================================================
Reads N cars from our Google Sheet and outputs a CSV
in the exact format expected by sayartionline.com (WP All Import).

USAGE
-----
  python generate_sayarti_csv.py            # 5 cars (default)
  python generate_sayarti_csv.py --count 10
  python generate_sayarti_csv.py --ids 16025,16024,16023
"""

import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, '.')
sys.stdout.reconfigure(encoding='utf-8')

from bazaralsham_scraper import BazarAlshamScraper

# ── Config ────────────────────────────────────────────────────────────────────

OUTPUT_FILE   = Path(r'D:\sky_scraper\skyscraper\sayarti_import.csv')
AUTHOR_ID     = '733'
AUTHOR_USER   = 'TasnaimTest'
DEFAULT_COUNT = 5


def convert_image_urls(raw: str) -> str:
    """
    Clean up comma-separated original image URLs.
    Vehica's image field expects comma-separated URLs (one per line or comma-separated).
    We use images_original_links (direct syriacars.net URLs) — NOT Google Drive links.
    """
    if not raw:
        return ''
    urls = [u.strip() for u in raw.split(',') if u.strip()]
    return ','.join(urls)


# ── Title generator ───────────────────────────────────────────────────────────

def make_title(car: dict) -> str:
    parts = [car.get('make', ''), car.get('model', ''), car.get('year', '')]
    return ' '.join(p for p in parts if p).strip()


# ── Field mapping ─────────────────────────────────────────────────────────────

def car_to_sayarti_row(car: dict) -> dict:
    """Map our normalized car dict to Sayarti CSV columns."""
    return {
        # WordPress core fields
        'Title':                        make_title(car),
        'Content':                      car.get('description_original', ''),
        'Date':                         car.get('date_added', ''),
        'Post Type':                    'العروض',
        'Status':                       'pending',
        'Author ID':                    AUTHOR_ID,
        'Author Username':              AUTHOR_USER,
        'Comment Status':               'closed',
        'Ping Status':                  'closed',

        # Image — use original syriacars.net URLs (comma-separated for Vehica)
        'Image URL':                    convert_image_urls(car.get('images_original_links', '')),

        # Sayarti listing fields (Arabic)
        'نوع الإعلان':                  'للبيع',
        'حالة المركبة':                 car.get('condition', ''),
        'وارد المركبة':                 car.get('origin', ''),
        'نوع هيكل المركبة':             car.get('body_type', ''),
        'ماركة':                        car.get('make', ''),
        'الموديل':                      car.get('model', ''),
        'المحافظة':                     car.get('city', ''),
        'نوع الدفع':                    car.get('drive_system', ''),
        'نوع ناقل الحركة':              car.get('transmission', ''),
        'نوع الوقود':                   car.get('fuel_type', ''),
        'عدد الأسطوانات':               car.get('cylinders', ''),
        'لون المركبة الخارجي':          car.get('exterior_color', ''),
        'لون فرش المركبة':              car.get('interior_color', ''),
        'عدد الأبواب':                  car.get('doors', ''),
        'ميزات':                        '',   # not scraped yet
        'ميزات السلامة':                '',   # not scraped yet

        # Vehica custom meta fields
        'vehica_currency_6656_2316':    car.get('price', ''),
        'vehica_14696':                 car.get('year', ''),
        'vehica_6664':                  car.get('mileage', ''),
        'vehica_6665':                  car.get('engine_size', ''),
        'vehica_6671':                  car.get('chassis_number', ''),
        'vehica_approved':              '0',
        'vehica_featured':              '0',
        'vehica_source':                car.get('source', 'syriacars'),

        # Source tracking
        'vehica_18820':                 '',

        # SEO / misc (leave empty)
        'Excerpt':                      '',
        'vehica_16721_vehica_address':  '',
        'vehica_16721_vehica_lat':      '',
        'vehica_16721_vehica_lng':      '',
    }


# ── CSV column order (matches Sayarti export) ─────────────────────────────────

COLUMNS = [
    'Title', 'Content', 'Excerpt', 'Date', 'Post Type', 'Status',
    'Author ID', 'Author Username', 'Comment Status', 'Ping Status',
    'Image URL',
    'نوع الإعلان', 'حالة المركبة', 'وارد المركبة', 'نوع هيكل المركبة',
    'ماركة', 'الموديل', 'المحافظة', 'نوع الدفع', 'نوع ناقل الحركة',
    'نوع الوقود', 'عدد الأسطوانات', 'لون المركبة الخارجي', 'لون فرش المركبة',
    'عدد الأبواب', 'ميزات', 'ميزات السلامة',
    'vehica_currency_6656_2316', 'vehica_14696', 'vehica_6664', 'vehica_6665',
    'vehica_6671', 'vehica_approved', 'vehica_featured', 'vehica_source',
    'vehica_18820',
    'vehica_16721_vehica_address', 'vehica_16721_vehica_lat', 'vehica_16721_vehica_lng',
    'Excerpt',
]

# Deduplicate while preserving order
seen = set()
COLUMNS = [c for c in COLUMNS if not (c in seen or seen.add(c))]


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='Generate Sayarti import CSV')
    parser.add_argument('--count', type=int, default=DEFAULT_COUNT,
                        help=f'Number of cars to export (default {DEFAULT_COUNT})')
    parser.add_argument('--ids', type=str, default='',
                        help='Comma-separated car IDs to export specifically')
    args = parser.parse_args()

    print('Connecting to Google Sheet…')
    s = BazarAlshamScraper()
    rows = s.sheet.get_all_rows()
    print(f'Sheet has {len(rows)} cars.')

    # Filter by IDs if specified
    if args.ids:
        target_ids = {i.strip() for i in args.ids.split(',')}
        selected = [r for r in rows if str(r.get('id', '')) in target_ids]
    else:
        # Pick first N cars that have original image links
        selected = []
        for r in rows:
            if r.get('images_original_links', '').strip():
                selected.append(r)
            if len(selected) >= args.count:
                break

    if not selected:
        print('No cars found with Drive image links.')
        return

    print(f'\nExporting {len(selected)} cars:')
    for r in selected:
        print(f"  [{r.get('id')}] {r.get('make')} {r.get('model')} {r.get('year')} — {r.get('city')}")

    # Write CSV
    with open(OUTPUT_FILE, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS, extrasaction='ignore')
        writer.writeheader()
        for car in selected:
            row = car_to_sayarti_row(car)
            writer.writerow(row)

    print(f'\nCSV saved to: {OUTPUT_FILE}')
    print(f'Ready to import via WP All Import → New Import → Upload this file.')
    print(f'\nReminder:')
    print(f'  Status      : pending (not published)')
    print(f'  Author      : {AUTHOR_USER} (ID {AUTHOR_ID})')
    print(f'  vehica_approved: 0 (needs manual approval)')


if __name__ == '__main__':
    main()
