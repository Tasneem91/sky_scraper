"""
Fetch ONE syriacar.net detail page and dump its spec HTML so we can write
a targeted extractor.
"""
import sys, os, requests, re
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, '.')

# ── grab the first ad_url from a live card ─────────────────────────────────
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from bs4 import BeautifulSoup
from webdriver_manager.chrome import ChromeDriverManager
import time

TARGET = 'https://syriacar.net'
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept-Language': 'ar,en-US;q=0.9',
}

opts = webdriver.ChromeOptions()
opts.add_argument('--headless=new')
opts.add_argument('--no-sandbox')
opts.add_argument('--disable-dev-shm-usage')
opts.add_argument('--window-size=1920,1080')
opts.add_argument(f"--user-agent={HEADERS['User-Agent']}")

chromedriver = os.path.expanduser(
    '~/.wdm/drivers/chromedriver/win64/147.0.7727.57/chromedriver-win32/chromedriver.exe'
)
if os.path.exists(chromedriver):
    driver = webdriver.Chrome(service=Service(chromedriver), options=opts)
else:
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=opts)

print(f"Loading {TARGET} ...")
driver.get(TARGET)
time.sleep(5)

soup0 = BeautifulSoup(driver.page_source, 'html.parser')
driver.quit()

# Find first share-button ad URL
ad_url = None
for btn in soup0.find_all('button', class_='share-button'):
    link = btn.get('data-link')
    if link and 'syriacar.net' in link:
        ad_url = link
        break
if not ad_url:
    a = soup0.find('div', class_='car-card')
    if a:
        link = a.find('a')
        if link:
            href = link.get('href', '')
            ad_url = f"{TARGET}{href}" if href.startswith('/') else href

print(f"\nFetching detail page: {ad_url}\n")

r = requests.get(ad_url, headers=HEADERS, timeout=20)
r.raise_for_status()
soup = BeautifulSoup(r.text, 'html.parser')

# ── 1. Print h1 ──────────────────────────────────────────────────────────────
h1 = soup.find('h1')
print(f"H1: {h1.get_text(strip=True) if h1 else 'none'}\n")

# ── 2. Any element whose text matches known Arabic spec labels ───────────────
spec_labels = [
    'المحرك', 'الأسطوانات', 'اللون', 'اللون الداخلي', 'الأبواب',
    'رقم الشاصي', 'نظام الدفع', 'نوع الدفع', 'البائع', 'المعلن',
    'الماركة', 'الموديل', 'السنة', 'الكيلومترات', 'نوع الوقود',
    'ناقل الحركة', 'الحالة', 'نوع الهيكل',
]
print("=== ELEMENTS MATCHING SPEC LABELS ===")
for label in spec_labels:
    for el in soup.find_all(string=re.compile(re.escape(label))):
        parent = el.parent
        sibling = parent.find_next_sibling() or parent.parent
        print(f"  label '{label}'")
        print(f"    container: <{parent.name}> class='{parent.get('class')}' text='{parent.get_text(strip=True)[:60]}'")
        print(f"    sibling  : <{sibling.name}> class='{sibling.get('class')}' text='{sibling.get_text(strip=True)[:60]}'")
        break   # one hit per label is enough

# ── 3. Print all <ul> lists on the page ─────────────────────────────────────
print("\n=== ALL <ul> LISTS ===")
for ul in soup.find_all('ul'):
    cls = ul.get('class', [])
    items = [li.get_text(strip=True) for li in ul.find_all('li')]
    if items:
        print(f"  <ul class='{cls}'>")
        for it in items[:10]:
            print(f"    • {it[:80]}")

# ── 4. Print all <dl> on the page ───────────────────────────────────────────
print("\n=== ALL <dl> ELEMENTS ===")
for dl in soup.find_all('dl'):
    print(f"  <dl class='{dl.get('class')}'>")
    for dt, dd in zip(dl.find_all('dt'), dl.find_all('dd')):
        print(f"    {dt.get_text(strip=True):30s} → {dd.get_text(strip=True)}")

# ── 5. Print all <table> ─────────────────────────────────────────────────────
print("\n=== ALL <table> ELEMENTS ===")
for tbl in soup.find_all('table'):
    print(f"  <table class='{tbl.get('class')}'>")
    for row in tbl.find_all('tr')[:10]:
        cells = [c.get_text(strip=True) for c in row.find_all(['td','th'])]
        print(f"    {cells}")

# ── 6. Divs with class containing 'spec', 'detail', 'info', 'prop' ──────────
print("\n=== SPEC-LIKE DIV CONTAINERS ===")
seen = set()
for div in soup.find_all('div', class_=re.compile(r'spec|detail|info|prop|feature|car-', re.I)):
    cls_str = ' '.join(div.get('class', []))
    if cls_str in seen or len(cls_str) > 60:
        continue
    seen.add(cls_str)
    text = div.get_text(separator=' | ', strip=True)[:120]
    print(f"  class='{cls_str}'\n    {text}")

# ── 7. Look for phone / WhatsApp links ───────────────────────────────────────
print("\n=== CONTACT LINKS ===")
for a in soup.find_all('a', href=True):
    if a['href'].startswith('tel:') or 'wa.me' in a['href']:
        print(f"  {a['href'][:80]}  text='{a.get_text(strip=True)[:40]}'")

# ── 8. Raw section around "معلومات" heading ──────────────────────────────────
print("\n=== RAW HTML AROUND 'معلومات' HEADING ===")
for h in soup.find_all(['h1','h2','h3','h4']):
    if 'معلومات' in h.get_text():
        print(f"  {h}\n")
        nxt = h.find_next_sibling()
        if nxt:
            print(str(nxt)[:1500])
        break
