#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
1. Use page.evaluate to call phone API from within browser (correct session)
2. Check "show more" total dealer count
3. Inspect dealer profile page for unmasked phone
"""
import sys, re, time, json
sys.stdout.reconfigure(encoding='utf-8')
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    page = browser.new_page(user_agent=UA)
    page.set_extra_http_headers({'Accept-Language': 'ar,en-US;q=0.9'})

    print('=== Loading dealers-list ===')
    try:
        page.goto('https://syriacars.net/dealers-list/', wait_until='networkidle', timeout=45000)
    except Exception:
        pass
    time.sleep(5)

    html = page.content()
    soup = BeautifulSoup(html, 'html.parser')
    rows = soup.find_all('tr', class_='stm-single-dealer')
    print(f'Dealers on initial load: {len(rows)}')

    nonce_m = re.search(r'stm_security_nonce\s*=\s*["\']([^"\']+)', html)
    nonce = nonce_m.group(1) if nonce_m else ''
    print(f'Nonce: {nonce}')

    # 1. Call phone API from inside the browser
    spans = soup.find_all('span', class_='stm-show-number')
    dealer_ids = [s.get('data-id') for s in spans]
    print(f'Dealer IDs: {dealer_ids}')

    print('\n=== Phone API calls (from browser JS) ===')
    for did in dealer_ids[:5]:
        result = page.evaluate(f"""async () => {{
            const resp = await fetch(
                '/wp-admin/admin-ajax.php?phone_owner_id={did}&listing_id=0&action=stm_ajax_get_seller_phone&security={nonce}',
                {{headers: {{'X-Requested-With': 'XMLHttpRequest'}}}}
            );
            return await resp.text();
        }}""")
        print(f'  id={did}: {result!r}')

    # 2. Keep clicking "show more" until gone
    print('\n=== Clicking show-more repeatedly ===')
    for attempt in range(20):
        more = page.locator('a:has-text("اعرض المزيد")')
        if more.count() == 0:
            print(f'  No more button after {attempt} clicks')
            break
        more.first.click()
        time.sleep(3)
        html_now = page.content()
        soup_now = BeautifulSoup(html_now, 'html.parser')
        count_now = len(soup_now.find_all('tr', class_='stm-single-dealer'))
        print(f'  Click {attempt+1}: {count_now} dealers')
        if count_now == len(soup.find_all('tr', class_='stm-single-dealer')):
            print('  Count unchanged — no more dealers loaded')
            break
        soup = soup_now

    # Final count after show-more
    html_final = page.content()
    soup_final = BeautifulSoup(html_final, 'html.parser')
    rows_final = soup_final.find_all('tr', class_='stm-single-dealer')
    print(f'\nTotal dealers after all show-more clicks: {len(rows_final)}')

    # 3. Check a dealer profile page for unmasked phone
    profile_urls = []
    for row in rows_final[:3]:
        a = row.select_one('.dealer-info .title a')
        if a:
            profile_urls.append(a.get('href', ''))

    print('\n=== Dealer profile pages ===')
    for url in profile_urls:
        print(f'\nLoading: {url}')
        try:
            page.goto(url, wait_until='networkidle', timeout=30000)
        except Exception:
            pass
        time.sleep(3)
        profile_html = page.content()
        psoup = BeautifulSoup(profile_html, 'html.parser')

        # Look for phone elements
        phone_els = psoup.find_all(class_=lambda c: c and 'phone' in ' '.join(c).lower())
        for p in phone_els[:5]:
            txt = p.get_text(strip=True)
            print(f'  phone-class element: {txt!r}')

        # Look for any phone patterns
        phone_matches = re.findall(r'(?:\+963|963|0)[\s\-]?\d[\d\s\-]{7,12}', profile_html)
        if phone_matches:
            print(f'  Phone patterns found: {phone_matches[:5]}')
        else:
            print('  No phone patterns found')

        # Look for contact info section
        contact_section = psoup.select('.stm-dealer-single-phone, .dealer-phone, [class*="contact"], [class*="phone"]')
        for el in contact_section[:5]:
            print(f'  contact el: {el.get_text(strip=True)[:100]!r}')

        # Look for reveal phone button
        show_spans = psoup.find_all('span', class_='stm-show-number')
        for s in show_spans[:3]:
            did = s.get('data-id', '')
            print(f'  show-number span: data-id={did}')

        # Get profile page nonce
        p_nonce_m = re.search(r'stm_security_nonce\s*=\s*["\']([^"\']+)', profile_html)
        if p_nonce_m:
            p_nonce = p_nonce_m.group(1)
            # Try phone API from this page context
            for did in [show_spans[0].get('data-id')] if show_spans else []:
                result = page.evaluate(f"""async () => {{
                    const resp = await fetch(
                        '/wp-admin/admin-ajax.php?phone_owner_id={did}&listing_id=0&action=stm_ajax_get_seller_phone&security={p_nonce}',
                        {{headers: {{'X-Requested-With': 'XMLHttpRequest'}}}}
                    );
                    return await resp.text();
                }}""")
                print(f'  Phone API on profile page: {result!r}')

    browser.close()

print('\nDone.')
