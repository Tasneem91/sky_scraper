#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Deep inspect of ONE dealer profile page to understand all available fields."""
import sys, re, time
sys.stdout.reconfigure(encoding='utf-8')
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'

PROFILE_URL = 'https://syriacars.net/dealer/reemrorita5gmail-com/'   # ALHAMZA CARS

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    page = browser.new_page(user_agent=UA)
    page.set_extra_http_headers({'Accept-Language': 'ar,en-US;q=0.9'})

    try:
        page.goto(PROFILE_URL, wait_until='networkidle', timeout=40000)
    except Exception:
        pass
    time.sleep(4)

    html = page.content()
    browser.close()

soup = BeautifulSoup(html, 'html.parser')
print(f'HTML size: {len(html)}')

# 1. Find key sections
print('\n=== Key HTML sections ===')

# Logo image
logo = soup.select_one('.dealer-single-logo img, .stm-dealer-logo img, img[class*="logo"]')
print(f'Logo: {logo.get("src", "") if logo else "not found"}')

# Dealer name
name_el = soup.select_one('h1, h2, .stm-dealer-name, [class*="dealer-name"], .entry-title')
if name_el:
    print(f'Name: {name_el.get_text(strip=True)!r}')

# Car count on profile page
cars_el = soup.select_one('.dealer-labels, [class*="cars-count"], [class*="listing-count"]')
if cars_el:
    print(f'Car count el: {cars_el.get_text(strip=True)!r}')

# WhatsApp links
wa_links = soup.find_all('a', href=re.compile(r'wa\.me|whatsapp', re.I))
print(f'\nWhatsApp links: {len(wa_links)}')
for a in wa_links:
    print(f'  href={a.get("href")}  text={a.get_text(strip=True)!r}')

# Social links
social_links = soup.find_all('a', href=re.compile(r'facebook|instagram|twitter|youtube|tiktok|telegram', re.I))
print(f'\nSocial links: {len(social_links)}')
for a in social_links[:8]:
    print(f'  {a.get("href")!r}')

# Email
emails = re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', html)
emails = [e for e in emails if 'syriacars' not in e.lower() and 'wp-' not in e.lower()]
print(f'\nEmails: {emails[:5]}')

# Location/address
loc_els = soup.find_all(class_=lambda c: c and any(x in ' '.join(c).lower() for x in ['location', 'address', 'city', 'region']))
print(f'\nLocation elements: {len(loc_els)}')
for el in loc_els[:5]:
    print(f'  class={el.get("class")}  text={el.get_text(strip=True)[:80]!r}')

# Description
desc_els = soup.select('.stm-dealer-description, [class*="description"], .entry-content, .dealer-bio')
print(f'\nDescription elements: {len(desc_els)}')
for d in desc_els[:3]:
    print(f'  class={d.get("class")}  text={d.get_text(strip=True)[:150]!r}')

# Rating
rating_el = soup.select_one('.stm-rate-sum, [class*="rating"]')
if rating_el:
    print(f'\nRating: {rating_el.get_text(strip=True)!r}')

# Working hours
hours_els = soup.find_all(string=re.compile(r'ساعات|hours|working|يوم|الأحد|الاثنين', re.I))
print(f'\nWorking hours strings: {len(hours_els)}')
for h in hours_els[:5]:
    print(f'  {str(h).strip()[:80]!r}')

# Print ALL divs with meaningful content for analysis
print('\n=== All unique class patterns with content ===')
from collections import Counter
class_counter = Counter()
for el in soup.find_all(['div', 'section', 'aside']):
    cl = ' '.join(el.get('class') or [])
    if cl and el.get_text(strip=True) and len(el.get_text(strip=True)) > 5:
        class_counter[cl] += 1
for cl, cnt in class_counter.most_common(30):
    sample_el = soup.find(class_=cl.split()[0])
    txt = sample_el.get_text(strip=True)[:60] if sample_el else ''
    print(f'  x{cnt}  .{cl[:50]:50s}  -> {txt!r}')

print('\nDone.')
