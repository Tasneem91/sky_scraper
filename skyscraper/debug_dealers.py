#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Inspect the HTML structure of syriacars.net/dealers-list/ using Playwright."""
import sys, re, time
sys.stdout.reconfigure(encoding='utf-8')
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    page = browser.new_page(user_agent=UA)
    page.set_extra_http_headers({'Accept-Language': 'ar,en-US;q=0.9'})

    print('Loading dealers-list ...')
    try:
        page.goto('https://syriacars.net/dealers-list/', wait_until='networkidle', timeout=45000)
    except Exception:
        pass
    time.sleep(5)

    html = page.content()
    print(f'HTML size: {len(html)} bytes')

    soup = BeautifulSoup(html, 'html.parser')

    # 1. Elements with 'dealer' in class
    print('\n=== Elements with "dealer" in class ===')
    dealer_els = soup.find_all(class_=lambda c: c and any('dealer' in x.lower() for x in c))
    print(f'Count: {len(dealer_els)}')
    for d in dealer_els[:3]:
        print(f'  tag={d.name}  class={d.get("class")}')
        print(f'  text: {d.get_text(" ", strip=True)[:150]}')
        print()

    # 2. Repeating card patterns
    print('\n=== Repeating card classes (count >= 5) ===')
    from collections import Counter
    for tag in ['div', 'article', 'li']:
        class_counts = Counter()
        for t in soup.find_all(tag):
            cl = tuple(t.get('class') or [])
            if cl:
                class_counts[cl] += 1
        for cls, count in class_counts.most_common(10):
            if count >= 5:
                print(f'  <{tag} class="{" ".join(cls)}">  x{count}')

    # 3. Phone number patterns
    print('\n=== Phone-number containing elements ===')
    phone_els = soup.find_all(string=re.compile(r'963\*+|963\d{8,}|\+963'))
    print(f'Phone strings found: {len(phone_els)}')
    if phone_els:
        p = phone_els[0]
        parent = p.parent
        print(f'  Direct parent: <{parent.name} class={parent.get("class")}>')
        print(f'  Text: {parent.get_text(" ", strip=True)[:100]}')

    # 4. Print full HTML of first 2 cards
    print('\n=== Raw HTML of first dealer card ===')
    # Find the container with 'سيارة في المعرض' (cars in showroom)
    car_count_els = soup.find_all(string=re.compile(r'سيارة في المعرض|سيارات في المعرض'))
    print(f'Car-count strings: {len(car_count_els)}')
    if car_count_els:
        # Walk up from the car count text to find the card container
        el = car_count_els[0].parent
        for _ in range(8):
            if el is None:
                break
            siblings = list(el.parent.children) if el.parent else []
            similar = [s for s in siblings if hasattr(s, 'get') and s.get('class') == el.get('class')]
            if len(similar) >= 5:
                break
            el = el.parent
        print(f'Card element: <{el.name} class={el.get("class")}>')
        print(str(el)[:2000])

    # 5. Pagination / show-more
    print('\n=== Pagination / show-more ===')
    for a in soup.find_all('a'):
        txt = a.get_text(strip=True)
        href = a.get('href', '')
        if any(w in txt for w in ['المزيد', 'التالي', 'next', 'more', 'page']):
            print(f'  href={href!r}  text={txt!r}')
    # Also look for buttons
    for btn in soup.find_all('button'):
        txt = btn.get_text(strip=True)
        if any(w in txt for w in ['المزيد', 'التالي', 'more']):
            print(f'  <button> text={txt!r}  data={dict(btn.attrs)}')

    # 6. Check if there's an API/AJAX endpoint in page source
    print('\n=== API endpoint hints in JS ===')
    scripts = soup.find_all('script')
    for s in scripts:
        src = s.string or ''
        if 'dealer' in src.lower() and ('fetch' in src.lower() or 'axios' in src.lower() or 'ajax' in src.lower() or 'api' in src.lower()):
            print(src[:500])
            print('---')

    browser.close()

print('\nDone.')
