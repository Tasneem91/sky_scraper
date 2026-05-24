#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Scroll down the dealers list page and find the real load-more button.
Test clicking it and check if more dealers load.
"""
import sys, re, time
sys.stdout.reconfigure(encoding='utf-8')
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=False)   # VISIBLE so we can see what's happening
    page = browser.new_page(user_agent=UA)
    page.set_viewport_size({'width': 1280, 'height': 900})
    page.set_extra_http_headers({'Accept-Language': 'ar,en-US;q=0.9'})

    print('Loading dealers-list ...')
    try:
        page.goto('https://syriacars.net/dealers-list/', wait_until='networkidle', timeout=45000)
    except Exception:
        pass
    time.sleep(4)

    html = page.content()
    soup = BeautifulSoup(html, 'html.parser')
    rows = soup.find_all('tr', class_='stm-single-dealer')
    print(f'Dealers before scroll: {len(rows)}')

    # Find ALL links and buttons on the page
    print('\n=== All buttons and links with Arabic "more" text ===')
    all_btns = page.locator('a, button').all()
    for btn in all_btns:
        try:
            txt = btn.inner_text().strip()
            if txt and any(w in txt for w in ['المزيد', 'أكثر', 'اقرأ', 'تحميل', 'عرض', 'المزيد', 'more', 'load']):
                print(f'  text={txt!r}  visible={btn.is_visible()}  tag={btn.evaluate("el => el.tagName")}')
        except Exception:
            pass

    # Scroll down gradually and print dealer count after each scroll
    print('\n=== Scrolling down progressively ===')
    for i in range(1, 20):
        page.evaluate(f'window.scrollTo(0, {i * 600})')
        time.sleep(0.5)

    time.sleep(3)

    html = page.content()
    soup = BeautifulSoup(html, 'html.parser')
    rows = soup.find_all('tr', class_='stm-single-dealer')
    print(f'Dealers after scrolling: {len(rows)}')

    # Find ALL links/buttons again after scroll
    print('\n=== All links/buttons after scroll ===')
    all_btns = page.locator('a, button').all()
    for btn in all_btns:
        try:
            txt = btn.inner_text().strip()
            href = btn.get_attribute('href') or ''
            if txt and len(txt) < 50:
                is_vis = btn.is_visible()
                if is_vis and any(w in txt for w in ['المزيد', 'أكثر', 'اقرأ', 'تحميل', 'عرض', 'more', 'load', 'المزيد']):
                    print(f'  VISIBLE text={txt!r}  href={href!r}')
        except Exception:
            pass

    # Try scrolling to the bottom of the dealer table and look for the button
    print('\n=== Looking for load-more specifically near dealer table ===')
    table = page.locator('table').first
    if table.count() > 0:
        table.scroll_into_view_if_needed()
        time.sleep(1)
        # Now look for a button below the table
        below = page.evaluate('''() => {
            const tables = document.querySelectorAll("tr.stm-single-dealer");
            if (tables.length > 0) {
                const last = tables[tables.length - 1];
                let next = last.parentElement.nextElementSibling;
                while (next) {
                    const btns = next.querySelectorAll("a, button");
                    for (const b of btns) {
                        if (b.textContent.trim()) {
                            return b.textContent.trim() + " | href=" + (b.href || b.getAttribute("onclick") || "");
                        }
                    }
                    next = next.nextElementSibling;
                }
            }
            return "none found";
        }''')
        print(f'Element after dealer table: {below!r}')

    # Find load-more button by various Arabic text variants
    print('\n=== Trying to find the load-more button ===')
    for text_variant in ['اقرأ المزيد', 'اعرض المزيد', 'عرض المزيد', 'تحميل المزيد', 'المزيد']:
        loc = page.locator(f'a:has-text("{text_variant}"), button:has-text("{text_variant}")')
        count = loc.count()
        if count > 0:
            print(f'  Found {count}x "{text_variant}" button(s)')
            for i in range(count):
                btn = loc.nth(i)
                print(f'    [{i}] visible={btn.is_visible()}  href={btn.get_attribute("href")!r}')
                bbox = btn.bounding_box()
                print(f'    [{i}] bounding_box={bbox}')

    # Scroll to bottom completely
    page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
    time.sleep(3)
    print('\n=== After scrolling to VERY BOTTOM ===')
    for text_variant in ['اقرأ المزيد', 'اعرض المزيد', 'عرض المزيد', 'تحميل المزيد', 'المزيد']:
        loc = page.locator(f'a:has-text("{text_variant}"), button:has-text("{text_variant}")')
        count = loc.count()
        if count > 0:
            print(f'  Found {count}x "{text_variant}"')
            for i in range(count):
                btn = loc.nth(i)
                print(f'    visible={btn.is_visible()}  bbox={btn.bounding_box()}')

    html_bottom = page.content()
    soup_bottom = BeautifulSoup(html_bottom, 'html.parser')
    rows_bottom = soup_bottom.find_all('tr', class_='stm-single-dealer')
    print(f'Dealers after scrolling to bottom: {len(rows_bottom)}')

    # Print ALL text of visible links at the bottom of the page
    print('\n=== All visible links in bottom half of page ===')
    all_links = soup_bottom.find_all('a', href=True)
    for a in all_links[-30:]:
        txt = a.get_text(strip=True)
        href = a.get('href', '')
        if txt and href and 'wp-content' not in href:
            print(f'  text={txt[:50]!r}  href={href[:80]!r}')

    print('\nWaiting 5 seconds so you can see the browser...')
    time.sleep(5)
    browser.close()

print('\nDone.')
