"""
Inspect Damazzle listings page — check correct URL and card selector.
Usage: python inspect_damazzle.py
"""
import sys
sys.stdout.reconfigure(encoding='utf-8')

from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import time

UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'

URLS_TO_TRY = [
    'https://damazzle.com/motors/cars/search',
    'https://damazzle.com/motors/cars/search?page=1',
    'https://damazzle.com/cars',
    'https://damazzle.com',
]

with sync_playwright() as pw:
    browser = pw.chromium.launch()
    page = browser.new_page(user_agent=UA)

    for url in URLS_TO_TRY:
        print(f"\nTrying: {url}")
        try:
            page.goto(url, wait_until='networkidle', timeout=20000)
            time.sleep(2)
            final_url = page.url
            title = page.title()
            print(f"  Final URL : {final_url}")
            print(f"  Title     : {title}")

            soup = BeautifulSoup(page.content(), 'html.parser')

            # Count cards with various selectors
            selectors = [
                'div.col-md-6',
                'div.product-item',
                'div.car-card',
                'div.listing-item',
                'article',
                'div[class*="product"]',
                'div[class*="card"]',
                'div[class*="listing"]',
            ]
            for sel in selectors:
                try:
                    count = len(soup.select(sel))
                    if count > 0:
                        print(f"  {sel:40s} => {count} elements")
                except Exception:
                    pass

            # Show first 5 links that look like listing pages
            links = [a['href'] for a in soup.find_all('a', href=True)
                     if '/ads/' in a.get('href','') or '/car/' in a.get('href','')]
            if links:
                print(f"  Ad links found: {links[:5]}")

        except Exception as e:
            print(f"  ERROR: {e}")

    # Also check the actual listings page with a wait
    print("\n\n=== DEEP CHECK: motors/cars/search ===")
    try:
        page.goto('https://damazzle.com/motors/cars/search', timeout=30000)
        # Try waiting for any card to appear
        for sel in ['div.col-md-6', 'div.product-item', 'div[class*="product"]']:
            try:
                page.wait_for_selector(sel, timeout=8000)
                print(f"  Selector '{sel}' appeared!")
                soup = BeautifulSoup(page.content(), 'html.parser')
                cards = soup.select(sel)
                print(f"  Found {len(cards)} cards")
                if cards:
                    print(f"  First card classes: {cards[0].get('class')}")
                    print(f"  First card text   : {cards[0].get_text(separator=' ', strip=True)[:150]}")
                break
            except Exception:
                print(f"  Selector '{sel}' timed out")
    except Exception as e:
        print(f"  Page load error: {e}")

    browser.close()

print("\nDone.")
