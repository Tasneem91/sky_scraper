#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys, json, requests
sys.stdout.reconfigure(encoding='utf-8')

API = 'https://beta.damazzletech.com/api/api/v1/client'
HEADERS = {
    'User-Agent': 'Mozilla/5.0',
    'Accept': 'application/json',
    'Origin': 'https://damazzle.com',
    'Referer': 'https://damazzle.com/',
}

for url in [
    f'{API}/ads?category_id=2&page=1&per_page=3',
    f'{API}/ads?category=motors&sub_category=cars&page=1&per_page=3',
]:
    r = requests.get(url, headers=HEADERS, timeout=15)
    d = r.json()
    items = d.get('data', [])
    print(f'URL: {url}')
    print(f'  status={r.status_code}  items={len(items)}')
    if items:
        car = items[0]
        print(f'  keys: {list(car.keys())}')
        print(f'  id={car.get("id")}  slug={car.get("slug")}')
        print(f'  phone={car.get("phone")}  whatsapp={car.get("whatsapp")}')
        print(f'  published_date={car.get("published_date")}')
        print(f'  images_count={car.get("images_count")}  gallery_in_list={"gallery" in car}')
        ff = car.get('featured_fields', [])
        print(f'  featured_fields count: {len(ff)}')
        for f in ff:
            slug = f.get('template_field', {}).get('slug', '?')
            val_ar = f.get('value', {}).get('ar', '?')
            label_ar = f.get('template_field', {}).get('field_name_ar', '?')
            print(f'    slug={slug!r:30s} label_ar={label_ar!r:25s} val_ar={val_ar!r}')
        print(f'  ad_link={car.get("ad_link")}')
        print(f'  cover_image={str(car.get("cover_image",""))[:80]}')
    meta = d.get('meta', {})
    print(f'  meta: {meta}')
    print()

# Also check second car to see variety of featured_fields
print('=== Second car featured_fields (first URL, 2nd item) ===')
r2 = requests.get(f'{API}/ads?category_id=2&page=1&per_page=3', headers=HEADERS, timeout=15)
items2 = r2.json().get('data', [])
if len(items2) > 1:
    for car in items2[1:]:
        print(f'slug={car.get("slug")}')
        for f in car.get('featured_fields', []):
            slug = f.get('template_field', {}).get('slug', '?')
            val_ar = f.get('value', {}).get('ar', '?')
            label_ar = f.get('template_field', {}).get('field_name_ar', '?')
            print(f'  slug={slug!r:30s} label_ar={label_ar!r:25s} val_ar={val_ar!r}')
        print()

print('Done.')
