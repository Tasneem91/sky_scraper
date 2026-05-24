"""Quick verification: scroll 60 times, confirm STABLE_LIMIT=8 captures all batches."""
import sys, time, os
sys.path.insert(0, '.')

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

opts = webdriver.ChromeOptions()
opts.add_argument('--headless=new')
opts.add_argument('--no-sandbox')
opts.add_argument('--disable-dev-shm-usage')
opts.add_argument('--window-size=1920,1080')
opts.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')

chromedriver = os.path.expanduser(
    '~/.wdm/drivers/chromedriver/win64/147.0.7727.57/chromedriver-win32/chromedriver.exe'
)
if os.path.exists(chromedriver):
    driver = webdriver.Chrome(service=Service(chromedriver), options=opts)
else:
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=opts)

print("Loading syriacar.net ...")
driver.get('https://syriacar.net/')
time.sleep(5)

prev   = 0
stable = 0
STABLE_LIMIT = 8

for i in range(1, 61):
    driver.execute_script("""
        window.scrollTo(0, document.body.scrollHeight);
        document.documentElement.scrollTop = document.documentElement.scrollHeight;
        window.scrollBy(0, window.innerHeight);
    """)
    time.sleep(3)

    count = driver.execute_script("return document.querySelectorAll('div.car-card').length;")

    if count != prev:
        stable = 0
        prev   = count
        marker = '  ** NEW BATCH **'
    else:
        stable += 1
        marker = f'  (stable {stable}/{STABLE_LIMIT})'

    print(f"Scroll {i:3d}: {count:4d} cards{marker}")

    if stable >= STABLE_LIMIT:
        print(f"\nSTOPPED after {STABLE_LIMIT} stable scrolls — end of list")
        break

print(f"\nFINAL: {prev} car-cards loaded in {i} scrolls")
driver.quit()
