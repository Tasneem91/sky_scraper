#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Quick test: navigate Damazzle listing page in Playwright and intercept
the Angular app's own API calls to verify car data is captured.
"""
import sys, json, time, re
sys.stdout.reconfigure(encoding='utf-8')
from playwright.sync_api import sync_playwright

LISTING_URL = 'https://damazzle.com/motors/cars/search'
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
      'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')

captured = []

def on_response(resp):
    url = resp.url
    if 'damazzletech.com' in url and '/ads' in url:
        try:
            body = resp.body()
            if not body or len(body) > 2_000_000:
                return
            d = json.loads(body)
            if isinstance(d, dict) and isinstance(d.get('data'), list):
                for car in d['data']:
                    if isinstance(car, dict) and car.get('id'):
                        captured.append(car)
                print(f'  [intercept] {resp.status} {url[:80]}  → {len(d["data"])} items')
        except Exception as e:
            pass

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    page = browser.new_page(user_agent=UA)
    page.set_extra_http_headers({'Accept-Language': 'ar,en-US;q=0.9'})
    page.on('response', on_response)

    print(f'Loading {LISTING_URL} ...')
    try:
        page.goto(LISTING_URL, wait_until='domcontentloaded', timeout=30000)
    except Exception as e:
        print(f'  goto error: {e}')

    time.sleep(5)
    try:
        page.wait_for_selector('.product-card, h5.product-title', timeout=15000)
    except Exception:
        pass
    time.sleep(2)
    browser.close()

# De-duplicate
seen = set()
unique = []
for car in captured:
    cid = car.get('id')
    if cid not in seen:
        seen.add(cid)
        unique.append(car)

print(f'\nTotal unique cars intercepted: {len(unique)}')
for car in unique[:5]:
    pub = car.get('published_date', '')[:10]
    phone = car.get('phone', '')
    wa = car.get('whatsapp', '')
    title = car.get('title', '')[:40]
    slug = car.get('slug', '')[:40]
    gallery_count = len(car.get('gallery') or [])
    ff_count = len(car.get('featured_fields') or [])
    print(f'  id={car.get("id")}  date={pub}  title={title!r}')
    print(f'    phone={phone}  whatsapp={wa}')
    print(f'    gallery={gallery_count}  featured_fields={ff_count}')
    ff = car.get('featured_fields') or []
    for f in ff:
        sl = (f.get('template_field') or {}).get('slug', '?')
        v = (f.get('value') or {}).get('ar', '?')
        print(f'    ff: slug={sl!r}  val={v!r}')
    print()

print('Done.')
