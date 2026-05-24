#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Simplified: test phone API and check total dealer count.
"""
import sys, re, time, json
sys.stdout.reconfigure(encoding='utf-8')
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import requests

UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    ctx = browser.new_context(user_agent=UA, extra_http_headers={'Accept-Language': 'ar,en-US;q=0.9'})
    page = ctx.new_page()

    print('Loading dealers-list ...')
    try:
        page.goto('https://syriacars.net/dealers-list/', wait_until='networkidle', timeout=45000)
    except Exception:
        pass
    time.sleep(5)

    html = page.content()
    soup = BeautifulSoup(html, 'html.parser')
    rows = soup.find_all('tr', class_='stm-single-dealer')
    print(f'Dealers on initial load: {len(rows)}')

    # Get nonce
    nonce_m = re.search(r'stm_security_nonce\s*=\s*["\']([^"\']+)', html)
    nonce = nonce_m.group(1) if nonce_m else ''
    print(f'Nonce: {nonce}')

    # Look for total count in HTML
    total_m = re.search(r'(\d+)\s*(?:وكيل|dealer)', html, re.I)
    if total_m:
        print(f'Total dealers mentioned: {total_m.group(0)}')

    # Count all dealers fully
    print('\n--- All Dealers on page ---')
    for i, row in enumerate(rows, 1):
        name = ''
        link = ''
        car_count = ''
        phone = ''
        location = ''
        dealer_id = ''

        title_a = row.select_one('.dealer-info .title a')
        if title_a:
            name = title_a.get_text(strip=True)
            link = title_a.get('href', '')

        count_div = row.select_one('.dealer-labels.heading-font')
        if count_div:
            car_count = count_div.get_text(strip=True)

        phone_div = row.select_one('.phone.heading-font')
        if phone_div:
            phone = phone_div.get_text(strip=True)

        loc_div = row.select_one('.dealer-location-label')
        if loc_div:
            location = loc_div.get_text(strip=True)

        show_span = row.select_one('span.stm-show-number')
        if show_span:
            dealer_id = show_span.get('data-id', '')

        print(f'  {i}. {name!r:35s}  cars={car_count:6s}  phone={phone:12s}  loc={location:15s}  id={dealer_id}')

    # Get session cookies
    cookies = {c['name']: c['value'] for c in ctx.cookies()}
    browser.close()

# Test phone reveal API with requests (using nonce + cookies)
if nonce and rows:
    soup = BeautifulSoup(html, 'html.parser')
    spans = soup.find_all('span', class_='stm-show-number')
    test_ids = [s.get('data-id') for s in spans[:3]]

    print(f'\n--- Testing phone API for IDs: {test_ids} ---')
    sess = requests.Session()
    sess.cookies.update(cookies)
    sess.headers.update({
        'User-Agent': UA,
        'Referer': 'https://syriacars.net/dealers-list/',
        'Accept': 'application/json, text/javascript, */*; q=0.01',
        'X-Requested-With': 'XMLHttpRequest',
    })

    for did in test_ids:
        url = (f'https://syriacars.net/wp-admin/admin-ajax.php'
               f'?phone_owner_id={did}&listing_id=0'
               f'&action=stm_ajax_get_seller_phone&security={nonce}')
        r = sess.get(url, timeout=15)
        print(f'  id={did}  status={r.status_code}  response={r.text[:200]}')

print('\nDone.')
