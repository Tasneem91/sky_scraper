#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Quick test: parse 3 real cars through the new _parse_car logic."""
import sys, json, requests
sys.stdout.reconfigure(encoding='utf-8')

# Patch imports so we can import just the helpers without running the whole scraper
import importlib, types

# Load helpers from damazzle_standalone without running __main__
spec = importlib.util.spec_from_file_location('dam', r'D:\sky_scraper\skyscraper\damazzle_standalone.py')
mod  = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

API = 'https://beta.damazzletech.com/api/api/v1/client'
H = {
    'User-Agent': 'Mozilla/5.0',
    'Accept': 'application/json',
    'Origin': 'https://damazzle.com',
    'Referer': 'https://damazzle.com/',
}

FIELDS = ['ad_title', 'date_added', 'price', 'location', 'year', 'mileage',
          'condition', 'transmission', 'fuel_type', 'color', 'engine',
          'model', 'brand', 'seller_name', 'contact']

for car_id in [424119, 424031, 424432]:
    r = requests.get(f'{API}/ads/{car_id}', H, timeout=15)
    if r.status_code != 200:
        print(f'id={car_id} status={r.status_code}'); continue
    car = r.json().get('data', {})

    # Run parse inline using the module's helper functions
    data = {}
    numeric_id = car.get('id')
    slug = car.get('slug', '')
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
    if brand and brand not in ('سيارات', 'Cars', 'Motors'): data['brand'] = brand
    mod._extract_from_featured_fields(data, car.get('featured_fields') or [])
    raw_desc = car.get('description') or car.get('description_ar') or ''
    desc = mod._clean_desc(raw_desc)
    if desc:
        data['description'] = desc[:100] + '…'
        mod._parse_description_specs(data, desc)
    customer = car.get('customer') or {}
    data['seller_name'] = mod._clean(customer.get('name', ''))
    data['contact'] = mod._clean(str(car.get('phone') or ''))
    data['whatsapp'] = mod._clean(str(car.get('whatsapp') or ''))

    print(f'\n=== id={car_id} ===')
    for f in FIELDS:
        v = data.get(f, '—')
        print(f'  {f:20s}: {str(v)[:80]}')

print('\nDone.')
