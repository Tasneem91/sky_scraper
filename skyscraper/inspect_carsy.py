"""
Inspect carsy.app — check listing page structure and detail page HTML.
Usage: python inspect_carsy.py
"""
import sys, re, requests
sys.stdout.reconfigure(encoding='utf-8')

from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import time

UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
BASE = 'https://carsy.app'

# ── PART 1: Stage 1 — listing page via Playwright ─────────────────────────
print("=" * 60)
print("PART 1: Listing page via Playwright")
print("=" * 60)

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    page = browser.new_page(user_agent=UA)
    page.goto('https://carsy.app/cars', wait_until='load', timeout=60000)
    time.sleep(3)

    # How many car links?
    car_links = page.evaluate("""
        () => Array.from(document.querySelectorAll('a[href]'))
              .filter(a => /^\\/cars\\/\\d+$/.test(a.getAttribute('href')))
              .map(a => a.getAttribute('href'))
    """)
    print(f"\nCar links found on listing page: {len(car_links)}")
    print(f"First 5: {car_links[:5]}")

    # What does the pagination area look like?
    pagination = page.evaluate("""
        () => {
            const els = Array.from(document.querySelectorAll(
                'a[aria-label], button[aria-label], nav a, nav button'
            ));
            return els.map(e => ({
                tag: e.tagName,
                text: e.textContent.trim().substring(0, 30),
                ariaLabel: e.getAttribute('aria-label'),
                classes: e.className.substring(0, 80),
                href: e.getAttribute('href')
            }));
        }
    """)
    print(f"\nPagination elements:")
    for el in pagination[:15]:
        print(f"  <{el['tag']}> text='{el['text']}' aria='{el['ariaLabel']}' href='{el['href']}'")

    # Grab one real car URL
    first_url = f"{BASE}{car_links[0]}" if car_links else None
    print(f"\nFirst car URL: {first_url}")
    browser.close()

# ── PART 2: Stage 2 — detail page via requests (SSR check) ────────────────
if first_url:
    print("\n" + "=" * 60)
    print("PART 2: Detail page via requests (SSR check)")
    print("=" * 60)

    r = requests.get(first_url, headers={'User-Agent': UA, 'Accept-Language': 'ar'}, timeout=20)
    print(f"HTTP {r.status_code}  content-length={len(r.text)}")
    soup = BeautifulSoup(r.text, 'html.parser')

    # Is there any real content or just a JS shell?
    h1 = soup.find('h1')
    print(f"\nH1: {h1.get_text(strip=True) if h1 else 'NONE — page is a JS shell!'}")

    all_h2 = soup.find_all('h2')
    print(f"\nAll H2 headings: {[h.get_text(strip=True) for h in all_h2]}")

    all_h3 = soup.find_all('h3')
    print(f"All H3 headings: {[h.get_text(strip=True) for h in all_h3]}")

    # Check __NEXT_DATA__ (Next.js baked-in JSON)
    next_data = soup.find('script', id='__NEXT_DATA__')
    if next_data:
        import json
        try:
            data = json.loads(next_data.string)
            # Dig into props for car data
            props = data.get('props', {}).get('pageProps', {})
            print(f"\n__NEXT_DATA__ pageProps keys: {list(props.keys())}")
            # Try to find car details in props
            for key, val in props.items():
                if isinstance(val, dict):
                    print(f"  props['{key}'] keys: {list(val.keys())[:10]}")
                elif isinstance(val, list):
                    print(f"  props['{key}']: list of {len(val)}")
        except Exception as e:
            print(f"  Could not parse __NEXT_DATA__: {e}")
    else:
        print("\nNo __NEXT_DATA__ found")

    # Show spec-like divs
    print("\nSpec-like divs on detail page:")
    for div in soup.find_all('div', class_=re.compile(r'spec|detail|info|car-', re.I))[:8]:
        text = div.get_text(separator=' | ', strip=True)[:100]
        print(f"  class='{' '.join(div.get('class', []))}' → {text}")

    # Contact links
    print("\nContact links:")
    for a in soup.find_all('a', href=True):
        if 'tel:' in a['href'] or 'wa.me' in a['href']:
            print(f"  {a['href']}")

    # Images
    imgs = [img.get('src','') for img in soup.find_all('img') if img.get('src','').startswith('http')]
    print(f"\nImages found: {len(imgs)}")
    for img in imgs[:5]:
        print(f"  {img[:80]}")

print("\nDone.")
