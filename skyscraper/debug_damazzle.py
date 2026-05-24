#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Debug script — inspect what Playwright actually sees on Damazzle listing page.
Run: python debug_damazzle.py
"""
import sys
import time
sys.stdout.reconfigure(encoding='utf-8')

from playwright.sync_api import sync_playwright

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
      'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')

LISTING_URL = 'https://damazzle.com/motors/cars/search'

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    page = browser.new_page(user_agent=UA)
    page.set_extra_http_headers({'Accept-Language': 'ar,en-US;q=0.9'})

    print(f'Loading {LISTING_URL} ...')
    try:
        page.goto(LISTING_URL, wait_until='domcontentloaded', timeout=30000)
    except Exception as e:
        print(f'goto error: {e}')

    print('Waiting 8 seconds for Angular ...')
    time.sleep(8)

    # ── 1. Page title ──────────────────────────────────────────────────────────
    print(f'\nPage title: {page.title()}')

    # ── 2. All hrefs on the page ───────────────────────────────────────────────
    all_links = page.evaluate("""
        () => [...new Set(
            Array.from(document.querySelectorAll('a[href]'))
                .map(a => a.getAttribute('href'))
                .filter(h => h && h.length > 1)
        )].slice(0, 60)
    """)
    print(f'\n=== ALL HREFS (first 60) ===')
    for h in all_links:
        print(f'  {h}')

    # ── 3. Specific patterns ───────────────────────────────────────────────────
    for pattern in ['/motors/cars/', '/cars/', '/ads/', 'motors', 'mini', 'search']:
        matches = [h for h in all_links if pattern in h]
        if matches:
            print(f'\n=== hrefs containing "{pattern}" ===')
            for m in matches[:10]:
                print(f'  {m}')

    # ── 4. Key selectors ──────────────────────────────────────────────────────
    selectors = [
        'div.col-md-6',
        'div.col-md-6.py-3',
        'h5.product-title',
        '.btn-whatsapp',
        'app-root',
        'app-featuremodule',
        '.product-card',
        '[class*="card"]',
        '[class*="listing"]',
        '[class*="product"]',
    ]
    print('\n=== SELECTOR COUNTS ===')
    for sel in selectors:
        try:
            count = page.evaluate(
                f'() => document.querySelectorAll({repr(sel)}).length'
            )
            print(f'  {sel!r:50s} → {count}')
        except Exception as e:
            print(f'  {sel!r:50s} → ERROR: {e}')

    # ── 5. Body text snippet ──────────────────────────────────────────────────
    body_text = page.evaluate("() => document.body.innerText.substring(0, 500)")
    print(f'\n=== BODY TEXT (first 500 chars) ===')
    print(body_text)

    # ── 6. HTTP status of the page ────────────────────────────────────────────
    # Check if there's a robot/captcha indicator
    html_snippet = page.evaluate("() => document.body.innerHTML.substring(0, 800)")
    print(f'\n=== HTML SNIPPET ===')
    print(html_snippet)

    browser.close()

print('\nDebug done.')
