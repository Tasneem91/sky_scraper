#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Intercept the exact AJAX calls for:
  1. 'اعرض المزيد' (show more dealers)
  2. 'إظهار الرقم' (reveal phone number)
"""
import sys, re, time, json
sys.stdout.reconfigure(encoding='utf-8')
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'

ajax_calls = []   # POST requests to admin-ajax.php

def on_request(req):
    if 'admin-ajax' in req.url:
        try:
            ajax_calls.append({
                'url': req.url,
                'method': req.method,
                'post_data': req.post_data or '',
            })
        except Exception:
            pass

ajax_responses = []

def on_response(resp):
    if 'admin-ajax' in resp.url:
        try:
            body = resp.body().decode('utf-8', errors='ignore')
            ajax_responses.append({
                'url': resp.url,
                'status': resp.status,
                'body': body[:800],
            })
        except Exception:
            pass

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    page = browser.new_page(user_agent=UA)
    page.set_extra_http_headers({'Accept-Language': 'ar,en-US;q=0.9'})
    page.on('request', on_request)
    page.on('response', on_response)

    print('Loading dealers-list ...')
    try:
        page.goto('https://syriacars.net/dealers-list/', wait_until='networkidle', timeout=45000)
    except Exception:
        pass
    time.sleep(4)

    html = page.content()
    soup = BeautifulSoup(html, 'html.parser')
    rows = soup.find_all('tr', class_='stm-single-dealer')
    print(f'Dealers on initial load: {len(rows)}')

    # --- Test "show more" button ---
    print('\n--- Clicking "اعرض المزيد" ---')
    more = page.locator('a:has-text("اعرض المزيد")')
    if more.count() > 0:
        more.first.click()
        time.sleep(5)
        print('Clicked show-more')
    else:
        print('No show-more button found')

    html2 = page.content()
    soup2 = BeautifulSoup(html2, 'html.parser')
    rows2 = soup2.find_all('tr', class_='stm-single-dealer')
    print(f'Dealers after show-more click: {len(rows2)}')

    # --- Test "show phone" button for first dealer ---
    print('\n--- Clicking "إظهار الرقم" for first dealer ---')
    show_num = page.locator('span.stm-show-number')
    if show_num.count() > 0:
        dealer_id = show_num.first.get_attribute('data-id')
        print(f'  Clicking show-number for data-id={dealer_id}')
        show_num.first.click()
        time.sleep(3)
        # Check if phone text changed
        phone_div = page.locator('.phone.heading-font').first
        phone_text = phone_div.inner_text()
        print(f'  Phone after click: {phone_text!r}')
    else:
        print('  No show-number spans found')

    browser.close()

print('\n=== AJAX REQUESTS TO admin-ajax.php ===')
for c in ajax_calls:
    print(f'  [{c["method"]}]  {c["url"]}')
    print(f'    POST data: {c["post_data"][:300]}')
    print()

print('\n=== AJAX RESPONSES FROM admin-ajax.php ===')
for r in ajax_responses:
    print(f'  {r["status"]}  {r["url"]}')
    print(f'  Body: {r["body"]}')
    print()

print('Done.')
