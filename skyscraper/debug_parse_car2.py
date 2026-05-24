#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Test the updated detail-fields enrichment logic end-to-end (no Google auth needed)."""
import sys, json, requests, importlib
sys.stdout.reconfigure(encoding='utf-8')

spec = importlib.util.spec_from_file_location('dam', r'D:\sky_scraper\skyscraper\damazzle_standalone.py')
mod  = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

API        = 'https://beta.damazzletech.com/api/api/v1/client'
DETAIL_API = 'https://beta.damazzletech.com/api/api/v1/ads/details-by-slug'
H = {
    'User-Agent': 'Mozilla/5.0',
    'Accept': 'application/json',
    'Origin': 'https://damazzle.com',
    'Referer': 'https://damazzle.com/',
}

FIELDS = ['ad_title', 'date_added', 'price', 'location', 'year', 'mileage',
          'condition', 'transmission', 'fuel_type', 'color', 'engine',
          'model', 'brand', 'seller_name', 'contact']

def fetch_detail_fields(slug):
    if not slug:
        return []
    try:
        r = requests.get(f'{DETAIL_API}/{slug}', headers=H, timeout=15)
        if r.status_code != 200:
            return []
        ad = (r.json().get('data') or {}).get('ad') or {}
        return ad.get('fields') or []
    except Exception as e:
        print(f'  detail fetch error: {e}')
        return []

# Hyundai Avante (424545) is the car from the screenshot with 8 معلومات اضافية fields
for car_id in [424545, 424119, 424031]:
    r = requests.get(f'{API}/ads/{car_id}', headers=H, timeout=15)
    if r.status_code != 200:
        print(f'id={car_id} status={r.status_code}'); continue
    car = r.json().get('data', {})
    slug = car.get('slug', '')

    # Simulate what updated _process_car does:
    # fetch detail fields and prepend to featured_fields
    detail_fields = fetch_detail_fields(slug)
    if detail_fields:
        merged_ff = detail_fields + (car.get('featured_fields') or [])
        car = {**car, 'featured_fields': merged_ff}

    # Parse using module helpers
    data = {}
    numeric_id = car.get('id')
    car_url = car.get('ad_link') or f'https://damazzle.com/ads/{slug}'
    data['id'] = f'damazzle_{numeric_id}'
    data['car_url'] = car_url
    data['date_added'] = mod._parse_iso_date(car.get('published_date', ''))
    title = mod._clean(car.get('title') or '')
    data['ad_title'] = title
    price = mod._parse_price(car.get('price') or car.get('dollar_price'))
    if price: data['price'] = price
    gov = car.get('governorate') or {}
    loc = mod._clean(gov.get('name_ar') or gov.get('name', ''))
    if loc: data['location'] = loc
    cat = car.get('category') or {}
    brand = mod._clean(cat.get('name_ar') or cat.get('name', ''))
    if brand and brand not in ('سيارات', 'Cars', 'Motors'):
        data['brand'] = brand
    mod._extract_from_featured_fields(data, car.get('featured_fields') or [])
    raw_desc = car.get('description') or car.get('description_ar') or ''
    desc = mod._clean_desc(raw_desc)
    if desc:
        data['description'] = desc[:80] + '...'
        mod._parse_description_specs(data, desc)
    customer = car.get('customer') or {}
    data['seller_name'] = mod._clean(customer.get('name', ''))
    phone = str(car.get('phone') or '')
    if phone and phone not in ('None', 'null', '0'):
        data['contact'] = phone

    print(f'\n=== id={car_id}  slug={slug!r} ===')
    print(f'  detail_fields fetched : {len(detail_fields)}')
    for f in FIELDS:
        v = data.get(f, '---')
        print(f'  {f:20s}: {str(v)[:80]}')

print('\nDone.')
