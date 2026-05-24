#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Explore the Damazzle API fully — car detail, contact, listing endpoint.
Run: python debug_damazzle_api2.py
"""
import sys, json, re, requests
sys.stdout.reconfigure(encoding='utf-8')

API   = 'https://beta.damazzletech.com/api/api/v1/client'
UA    = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
         'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')

HEADERS = {
    'User-Agent': UA,
    'Accept': 'application/json',
    'Accept-Language': 'ar,en-US;q=0.9',
    'Origin': 'https://damazzle.com',
    'Referer': 'https://damazzle.com/',
}

AD_ID   = '424119'
AD_SLUG = 'mini-cooper-countryman-s-2012'

# ── 1. Full car detail API response ────────────────────────────────────────
print('=' * 60)
print('1. GET /ads/{id} — full car detail')
print('=' * 60)
r = requests.get(f'{API}/ads/{AD_ID}', headers=HEADERS, timeout=15)
print(f'Status: {r.status_code}')
data = r.json()
car = data.get('data', {})
print(f'All top-level keys in data: {list(car.keys())}')
print()
# Print every field
for k, v in car.items():
    if isinstance(v, (dict, list)):
        print(f'  {k}: {json.dumps(v, ensure_ascii=False)[:200]}')
    else:
        print(f'  {k}: {v}')

# ── 2. POST click-button with button_type ──────────────────────────────────
print('\n' + '=' * 60)
print('2. POST /ads/{id}/click-button  (call)')
print('=' * 60)
for btype in ['call', 'whatsapp', 'chat']:
    r2 = requests.post(
        f'{API}/ads/{AD_ID}/click-button',
        headers={**HEADERS, 'Content-Type': 'application/json'},
        json={'button_type': btype},
        timeout=10,
    )
    print(f'  button_type={btype!r}  status={r2.status_code}  body={r2.text[:200]}')

# ── 3. Listing / search API ────────────────────────────────────────────────
print('\n' + '=' * 60)
print('3. Listing API candidates')
print('=' * 60)
candidates = [
    f'{API}/ads?page=1&per_page=10',
    f'{API}/ads?page=1',
    f'{API}/ads/search?page=1',
    f'{API}/motors/cars?page=1',
    f'{API}/categories/cars/ads?page=1',
    f'https://beta.damazzletech.com/api/api/v1/client/ads?category=motors&sub_category=cars&page=1',
    f'{API}/ads?category_id=1&page=1',
]
for url in candidates:
    try:
        r3 = requests.get(url, headers=HEADERS, timeout=10)
        body = r3.text[:300]
        print(f'  {r3.status_code}  {url}')
        if r3.status_code == 200:
            try:
                d = r3.json()
                keys = list(d.keys()) if isinstance(d, dict) else '(list)'
                print(f'         keys={keys}')
                # how many ads?
                if isinstance(d, dict) and 'data' in d:
                    print(f'         len(data)={len(d["data"]) if isinstance(d["data"], list) else "?"}')
            except Exception:
                print(f'         body={body}')
    except Exception as e:
        print(f'  ERROR  {url}  {e}')

print('\nDone.')
