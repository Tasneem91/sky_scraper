#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Find the DEALER-SPECIFIC contact section HTML on a profile page.
Look for: phone (unmasked or WA), links specific to this dealer, description.
"""
import sys, re, time
sys.stdout.reconfigure(encoding='utf-8')
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'

SITES_WA = '+963945273368'  # SyriaCars platform's own WA — exclude this

def inspect_profile(page, url):
    print(f'\n{"="*60}')
    print(f'URL: {url}')
    try:
        page.goto(url, wait_until='networkidle', timeout=40000)
    except Exception:
        pass
    time.sleep(4)
    html = page.content()
    soup = BeautifulSoup(html, 'html.parser')

    # 1. Find the section containing "اظهر الرقم" or "إظهار الرقم"
    show_span = soup.find('span', class_='stm-show-number')
    if show_span:
        did = show_span.get('data-id', '')
        print(f'show-number span data-id={did}')
        # Walk up to find the card/contact block
        el = show_span
        for _ in range(8):
            el = el.parent
            if el is None:
                break
            if el.name in ('div', 'section', 'article') and el.get('class'):
                text = el.get_text(separator=' ', strip=True)
                if len(text) > 20:
                    print(f'\nContact block <{el.name} class={el.get("class")}>:')
                    print(str(el)[:2000])
                    break

    # 2. All wa.me links and their context
    print('\n--- wa.me links ---')
    wa_links = soup.find_all('a', href=re.compile(r'wa\.me', re.I))
    for a in wa_links:
        href = a.get('href', '')
        parent_text = a.parent.get_text(strip=True)[:100] if a.parent else ''
        parent_class = a.parent.get('class') if a.parent else []
        print(f'  href={href!r}  parent_class={parent_class}  parent_text={parent_text!r}')

    # 3. All links that look dealer-specific (not site-wide nav/footer)
    print('\n--- All unique external links (non-syriacars) ---')
    seen = set()
    for a in soup.find_all('a', href=True):
        href = a.get('href', '')
        if ('syriacars.net' not in href and
            href.startswith('http') and
            href not in seen and
            'google' not in href and
            'facebook.com/syriacars' not in href and
            'instagram.com/syriacars' not in href and
            'youtube.com/channel/UC9eFI' not in href):
            seen.add(href)
            text = a.get_text(strip=True)
            print(f'  {href!r:60s}  text={text!r}')

    # 4. Phone patterns in the whole HTML (not just 963*)
    print('\n--- Phone-like patterns in HTML ---')
    phones = re.findall(r'(?:\+?\d[\d\s\-]{8,15}\d)', html)
    # Filter out obviously non-phone numbers (timestamps, IDs, etc.)
    for p in set(phones):
        digits = re.sub(r'\D', '', p)
        if 9 <= len(digits) <= 13 and digits[:3] in ('963', '090', '091', '966', '971', '972', '351', '353'):
            print(f'  {p!r}  ({digits})')

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    page = browser.new_page(user_agent=UA)
    page.set_extra_http_headers({'Accept-Language': 'ar,en-US;q=0.9'})

    # Check 3 different dealers
    profiles = [
        'https://syriacars.net/dealer/reemrorita5gmail-com/',    # ALHAMZA CARS
        'https://syriacars.net/dealer/al-asaad/',               # شركة علي الاسعد (Idlib)
        'https://syriacars.net/dealer/abo-omarr/',              # الباز (non-Syrian prefix?)
    ]
    for url in profiles:
        inspect_profile(page, url)

    browser.close()

print('\nDone.')
