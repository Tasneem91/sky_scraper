#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Sample 30 cars from the listing intercept and collect all unique featured_fields slugs."""
import sys, json, time, re, collections
sys.stdout.reconfigure(encoding='utf-8')
from playwright.sync_api import sync_playwright

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
      'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')

captured = []

def on_response(resp):
    if 'damazzletech.com' in resp.url and '/ads' in resp.url:
        try:
            body = resp.body()
            d = json.loads(body)
            if isinstance(d, dict) and isinstance(d.get('data'), list):
                captured.extend(d['data'])
        except Exception:
            pass

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    page = browser.new_page(user_agent=UA)
    page.set_extra_http_headers({'Accept-Language': 'ar,en-US;q=0.9'})
    page.on('response', on_response)
    for pg in range(1, 5):   # pages 1-4
        url = f'https://damazzle.com/motors/cars/search?page={pg}'
        print(f'Loading page {pg} ...')
        try:
            page.goto(url, wait_until='domcontentloaded', timeout=30000)
        except Exception as e:
            print(f'  error: {e}')
        time.sleep(6)
    browser.close()

# De-duplicate
seen = set(); unique = []
for car in captured:
    cid = car.get('id')
    if cid and cid not in seen:
        seen.add(cid); unique.append(car)

print(f'\nTotal unique cars: {len(unique)}')

# Collect all featured_fields slugs + labels
slug_counter = collections.Counter()
slug_examples = {}
for car in unique:
    for ff in (car.get('featured_fields') or []):
        tf = ff.get('template_field') or {}
        slug = tf.get('slug', '?')
        label_ar = tf.get('field_name_ar', '?')
        val_ar = (ff.get('value') or {}).get('ar', '')
        slug_counter[slug] += 1
        if slug not in slug_examples:
            slug_examples[slug] = {'label_ar': label_ar, 'example': val_ar}

print('\nAll featured_fields slugs found:')
for slug, count in slug_counter.most_common():
    ex = slug_examples[slug]
    print(f'  {count:3d}x  slug={slug!r:35s}  label_ar={ex["label_ar"]!r:25s}  e.g.={ex["example"]!r}')

# Also show a sample description
print('\n=== Sample descriptions (first 3 cars) ===')
for car in unique[:3]:
    desc = car.get('description') or car.get('description_ar') or ''
    print(f'--- {car.get("title","")} ---')
    print(repr(desc[:300]))
    print()

print('Done.')
