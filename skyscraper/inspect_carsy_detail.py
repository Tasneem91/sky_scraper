"""
Deep inspection of a single carsy.app detail page.
Shows exact HTML around specs, description, seller, images, contact.
Usage: python inspect_carsy_detail.py
"""
import sys, re, requests, json
sys.stdout.reconfigure(encoding='utf-8')
from bs4 import BeautifulSoup

UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
URL = 'https://carsy.app/cars/2043'

print(f"Fetching {URL}")
r = requests.get(URL, headers={'User-Agent': UA, 'Accept-Language': 'ar'}, timeout=20)
soup = BeautifulSoup(r.text, 'html.parser')

# ── 1. All h1/h2/h3 with their inner HTML (to see if they have child elements) ──
print("\n=== ALL HEADINGS (raw HTML) ===")
for h in soup.find_all(['h1','h2','h3']):
    print(f"  <{h.name}> get_text='{h.get_text(strip=True)[:50]}'  string={repr(h.string)}")

# ── 2. معلومات السيارة section ────────────────────────────────────────────────
print("\n=== SPECS SECTION HTML ===")
for h2 in soup.find_all('h2'):
    if 'معلومات' in h2.get_text():
        print(f"Found h2: '{h2.get_text(strip=True)}'")
        # Print the next sibling div
        nxt = h2.find_next_sibling()
        if nxt:
            print(f"Next sibling: <{nxt.name}> class='{nxt.get('class')}'")
            print(str(nxt)[:2000])
        else:
            # try find_next('div')
            nxt = h2.find_next('div')
            if nxt:
                print(f"Next div: class='{nxt.get('class')}'")
                print(str(nxt)[:2000])
        break

# ── 3. الوصف section ──────────────────────────────────────────────────────────
print("\n=== DESCRIPTION SECTION HTML ===")
for h2 in soup.find_all('h2'):
    if 'الوصف' in h2.get_text():
        nxt = h2.find_next_sibling() or h2.find_next('div')
        if nxt:
            print(str(nxt)[:800])
        break

# ── 4. معلومات البائع section ─────────────────────────────────────────────────
print("\n=== SELLER SECTION HTML ===")
for h in soup.find_all(['h2','h3']):
    if 'البائع' in h.get_text():
        nxt = h.find_next_sibling() or h.find_next('div')
        if nxt:
            print(str(nxt)[:800])
        break

# ── 5. All <img> tags ────────────────────────────────────────────────────────
print("\n=== ALL <img> TAGS ===")
for img in soup.find_all('img')[:10]:
    print(f"  src={img.get('src','')[:80]}  data-src={img.get('data-src','')[:60]}")

# ── 6. All <a href=tel: or wa.me> ────────────────────────────────────────────
print("\n=== CONTACT LINKS ===")
found = False
for a in soup.find_all('a', href=True):
    if 'tel:' in a['href'] or 'wa.me' in a['href']:
        print(f"  {a['href']}")
        found = True
if not found:
    print("  NONE FOUND — checking for phone numbers in text...")
    phones = re.findall(r'\b09\d{8}\b|\b\+963\d{9}\b', r.text)
    print(f"  Phone numbers in raw HTML: {list(set(phones))[:5]}")

# ── 7. Next.js image URLs (often in JSON blobs or data attrs) ────────────────
print("\n=== IMAGE URLS IN PAGE SOURCE ===")
img_urls = re.findall(r'https://[^\s"\']+\.(?:jpg|jpeg|png|webp)', r.text)
img_urls = list(dict.fromkeys(img_urls))  # deduplicate
skip = ('icon','logo','placeholder','avatar','flag','sprite','banner')
img_urls = [u for u in img_urls if not any(k in u.lower() for k in skip)]
print(f"  Found {len(img_urls)} image URLs in source")
for u in img_urls[:8]:
    print(f"  {u[:100]}")
