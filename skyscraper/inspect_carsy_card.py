"""
Inspect a single Carsy listing card and detail page to find
location + condition + body_type label names.
Usage: python inspect_carsy_card.py
"""
import sys, re, requests
sys.stdout.reconfigure(encoding='utf-8')
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import time

UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    page = browser.new_page(user_agent=UA)
    page.goto('https://carsy.app/cars', wait_until='load', timeout=60000)
    time.sleep(3)

    # Dump the first card's full HTML
    first_card_html = page.evaluate("""
        () => {
            const a = Array.from(document.querySelectorAll('a[href]'))
                .find(a => /^\\/cars\\/\\d+$/.test(a.getAttribute('href')));
            return a ? a.outerHTML.substring(0, 3000) : 'NOT FOUND';
        }
    """)
    print("=== FIRST CARD HTML (first 3000 chars) ===")
    print(first_card_html)

    # Get location text from various selectors
    location_attempts = page.evaluate("""
        () => {
            const a = Array.from(document.querySelectorAll('a[href]'))
                .find(a => /^\\/cars\\/\\d+$/.test(a.getAttribute('href')));
            if (!a) return {};
            return {
                span_capitalize: a.querySelector('span.capitalize')?.textContent,
                all_spans: Array.from(a.querySelectorAll('span')).map(s => s.textContent.trim()).filter(Boolean),
                all_text: a.innerText.substring(0, 200)
            };
        }
    """)
    print("\n=== LOCATION SELECTORS ===")
    print(f"  span.capitalize: {location_attempts.get('span_capitalize')}")
    print(f"  all spans: {location_attempts.get('all_spans')}")
    print(f"  all text: {location_attempts.get('all_text')}")

    browser.close()

# Now check detail page for condition / body_type label names
print("\n=== DETAIL PAGE ALL SPEC LABELS (car/2043) ===")
r = requests.get('https://carsy.app/cars/2043',
                 headers={'User-Agent': UA, 'Accept-Language': 'ar'}, timeout=20)
soup = BeautifulSoup(r.text, 'html.parser')

specs_h2 = next((h for h in soup.find_all('h2') if 'معلومات' in h.get_text()), None)
if specs_h2:
    specs_div = specs_h2.find_next_sibling('div') or specs_h2.find_next('div')
    if specs_div:
        for card in specs_div.find_all('div', recursive=False):
            ps = card.find_all('p')
            if len(ps) >= 2:
                print(f"  '{ps[0].get_text(strip=True)}' → '{ps[1].get_text(strip=True)}'")
