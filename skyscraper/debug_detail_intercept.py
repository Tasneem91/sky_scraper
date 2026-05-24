#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Navigate to a Damazzle detail page and intercept ALL API responses to find
where اللون / ناقل الحركة / نوع الوقود / الشروط actually come from.
"""
import sys, json, time
sys.stdout.reconfigure(encoding='utf-8')
from playwright.sync_api import sync_playwright

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
      'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')

# Hyundai Avante — the car shown in the screenshot with 8 معلومات اضافية fields
DETAIL_URL = 'https://damazzle.com/ads/hyundai-avante-2011'

captured = []

def on_response(resp):
    url = resp.url
    if 'damazzletech.com' not in url:
        return
    try:
        body = resp.body()
        if not body or len(body) > 3_000_000:
            return
        text = body.decode('utf-8', errors='ignore')
        captured.append({
            'url': url,
            'status': resp.status,
            'text': text,
        })
    except Exception:
        pass

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    page = browser.new_page(user_agent=UA)
    page.set_extra_http_headers({'Accept-Language': 'ar,en-US;q=0.9'})
    page.on('response', on_response)

    print(f'Loading {DETAIL_URL} ...')
    try:
        page.goto(DETAIL_URL, wait_until='domcontentloaded', timeout=30000)
    except Exception as e:
        print(f'  goto error: {e}')

    time.sleep(6)
    try:
        page.wait_for_selector('h1', timeout=10000)
    except Exception:
        pass
    time.sleep(3)
    browser.close()

print(f'\nTotal API responses captured: {len(captured)}')
print()

for r in captured:
    print(f'  {r["status"]}  {r["url"]}')
    try:
        d = json.loads(r['text'])
        car = d.get('data', d)
        if isinstance(car, dict):
            ff = car.get('featured_fields') or []
            if ff:
                print(f'    featured_fields count: {len(ff)}')
                for f in ff:
                    tf = f.get('template_field') or {}
                    slug = tf.get('slug', '?')
                    label_ar = tf.get('field_name_ar', '?')
                    val = (f.get('value') or {}).get('ar', '?')
                    print(f'      slug={slug!r:30s}  label={label_ar!r:25s}  val={val!r}')
            # Check for any other fields that might hold specs
            for key in ['specs', 'fields', 'details', 'attributes', 'extra_fields', 'custom_fields']:
                if car.get(key):
                    print(f'    [{key}]: {json.dumps(car[key], ensure_ascii=False)[:200]}')
    except Exception:
        # Not JSON — show snippet
        snip = r['text'][:150]
        if any(w in snip for w in ['اللون', 'الشروط', 'ناقل', 'وقود']):
            print(f'    *** FOUND SPEC KEYWORD *** snippet: {snip!r}')
        else:
            print(f'    (non-JSON or no specs, {len(r["text"])} bytes)')

print('\nDone.')
