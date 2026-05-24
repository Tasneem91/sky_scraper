#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Deep inspect of dealer cards HTML structure + AJAX show-more."""
import sys, re, json, time
sys.stdout.reconfigure(encoding='utf-8')
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'

ajax_responses = []

def on_response(resp):
    url = resp.url
    if 'admin-ajax' in url or 'dealer' in url.lower():
        try:
            body = resp.body()
            ajax_responses.append({'url': url, 'status': resp.status, 'body': body.decode('utf-8', errors='ignore')})
        except Exception:
            pass

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    page = browser.new_page(user_agent=UA)
    page.set_extra_http_headers({'Accept-Language': 'ar,en-US;q=0.9'})
    page.on('response', on_response)

    print('Loading dealers-list ...')
    try:
        page.goto('https://syriacars.net/dealers-list/', wait_until='networkidle', timeout=45000)
    except Exception:
        pass
    time.sleep(4)

    html = page.content()
    soup = BeautifulSoup(html, 'html.parser')

    # --- 1. Find a card container by walking up from phone div ---
    print('\n=== Card HTML structure (from phone element) ===')
    phone_divs = soup.find_all('div', class_=lambda c: c and 'phone' in c)
    print(f'Phone divs: {len(phone_divs)}')
    if phone_divs:
        p = phone_divs[0]
        # Walk up to find the card wrapper
        el = p
        for _ in range(10):
            if el.parent is None:
                break
            parent = el.parent
            siblings_like = [s for s in parent.children
                             if hasattr(s, 'get') and s.get('class') == el.get('class')]
            if len(siblings_like) >= 5:
                print(f'Card wrapper: <{el.name} class={el.get("class")}>')
                print('First card HTML:')
                print(str(el)[:3000])
                break
            el = parent

    # --- 2. Check .title elements to understand structure ---
    print('\n\n=== .title divs (first 3) ===')
    titles = soup.find_all('div', class_='title')
    for t in titles[:3]:
        print(f'  text={t.get_text(" ", strip=True)[:80]}')
        print(f'  parent: <{t.parent.name} class={t.parent.get("class")}>')
        print()

    # --- 3. Find elements containing car count ---
    print('=== Elements containing "سيارة" ===')
    car_els = soup.find_all(string=re.compile(r'سيارة'))
    for el in car_els[:10]:
        parent = el.parent
        print(f'  tag={parent.name}  class={parent.get("class")}  text={str(el).strip()[:80]}')

    # --- 4. Extract the nonce and "show more" action ---
    print('\n=== Nonce and AJAX info ===')
    nonce_m = re.search(r'stm_security_nonce\s*=\s*["\']([^"\']+)', html)
    if nonce_m:
        print(f'nonce: {nonce_m.group(1)}')
    # Look for the show-more button and its data attributes
    more_btn = soup.find('a', string=re.compile(r'اعرض المزيد'))
    if more_btn:
        print(f'Show-more link attrs: {dict(more_btn.attrs)}')
        parent = more_btn.parent
        print(f'  Parent: <{parent.name} class={parent.get("class")}  data={dict(parent.attrs)}>')

    # --- 5. Click "show more" and capture AJAX request ---
    print('\n=== Clicking show-more button ===')
    try:
        more = page.locator('a:has-text("اعرض المزيد")')
        if more.count() > 0:
            more.first.click()
            time.sleep(4)
            print('Clicked. Waiting for AJAX ...')
        else:
            print('Show-more button not found on page')
    except Exception as e:
        print(f'Click error: {e}')

    browser.close()

# --- 6. Report AJAX responses ---
print(f'\n=== AJAX responses captured: {len(ajax_responses)} ===')
for r in ajax_responses:
    print(f'  {r["status"]}  {r["url"]}')
    print(f'  Body (first 600): {r["body"][:600]}')
    print()

print('Done.')
