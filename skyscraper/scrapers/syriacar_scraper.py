"""
SyriaCar.net Scraper — Two-Stage Architecture
  Stage 1: Selenium — iterates every LOCATION FILTER and infinite-scrolls
            within each one to reach all ~8 900 cars.
            (The homepage caps at ~180 most-recent listings; location filters
             expose the full catalogue.)
  Stage 2: requests + BeautifulSoup — fetch each detail page for extra fields.

Location filter mechanism (confirmed via live DOM inspection):
  • <ul class="ul-scroll"> inside <div id="sidebarlocation">
  • Each <li data-governorate-id="N"> is a clickable location
  • Empty data-governorate-id  ("")  = "All Regions" — skip it
  • After clicking, the listing reloads with only that location's cars
  • Same infinite-scroll mechanism as the homepage applies within each filter

Scroll strategy:
  • Signal: NUMBER OF CAR CARDS (not page height).
  • Fires window.scrollTo + documentElement.scrollTop + scrollBy together.
  • Patience: STABLE_LIMIT consecutive scrolls with no new cards → done.
  • Confirmed timing: new batch every ~3 scrolls at 3 s each.
"""

import logging
import os
import time
from pathlib import Path
from urllib.parse import urljoin
from datetime import datetime
from typing import List, Dict, Any, Optional, Set

import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

from scrapers.base_scraper import CarsScraper
from scrapers import parser as car_parser

logger = logging.getLogger(__name__)

REQUEST_HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    ),
    'Accept-Language': 'ar,en-US;q=0.9,en;q=0.8',
}

# Stop scrolling after this many consecutive stable-count scrolls
STABLE_LIMIT   = 8
# Seconds to wait after each scroll (3 s confirmed sufficient by live test)
SCROLL_WAIT    = 3
# Hard cap per location (safety valve; 600 × 3 s = 30 min per location max)
MAX_SCROLLS    = 600


class SyriaCarScraper(CarsScraper):
    """
    SyriaCar.net two-stage scraper.
    Stage 1 uses Selenium (location-filter + infinite-scroll per location).
    Stage 2 uses requests (SSR detail pages, no browser needed).
    """

    def __init__(self, website_config: Dict[str, Any]):
        super().__init__(website_config)
        self.base_url    = website_config.get('url', 'https://syriacar.net')
        self.image_folder = Path(website_config.get('image_folder', 'images/syriacar'))
        self.image_folder.mkdir(parents=True, exist_ok=True)
        self.driver  = None
        self.session = requests.Session()
        self.session.headers.update(REQUEST_HEADERS)
        logger.info(f"Initialized SyriaCarScraper for {self.website_name}")

    # =========================================================================
    # Driver lifecycle (Stage 1 only)
    # =========================================================================

    def _init_driver(self):
        opts = webdriver.ChromeOptions()
        opts.add_argument("--headless=new")
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
        opts.add_argument("--disable-gpu")
        opts.add_argument("--window-size=1920,1080")
        opts.add_argument(f"--user-agent={REQUEST_HEADERS['User-Agent']}")

        chromedriver = os.path.expanduser(
            "~/.wdm/drivers/chromedriver/win64/147.0.7727.57/"
            "chromedriver-win32/chromedriver.exe"
        )
        if os.path.exists(chromedriver):
            self.driver = webdriver.Chrome(service=Service(chromedriver), options=opts)
        else:
            self.driver = webdriver.Chrome(
                service=Service(ChromeDriverManager().install()), options=opts
            )
        logger.info("Selenium WebDriver initialized (headless:new, 1920×1080)")

    def _close_driver(self):
        if self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass
            self.driver = None
            logger.info("WebDriver closed")

    # =========================================================================
    # Location filter helpers
    # =========================================================================

    def _get_location_filters(self) -> List[Dict]:
        """
        Extract all location filter <li> elements from #sidebarlocation.
        Returns list of {governorate_id, name, count}, sorted by count DESC.
        Skips the "All Regions" entry (empty data-governorate-id).
        """
        locations = self.driver.execute_script("""
            return Array.from(
                document.querySelectorAll('#sidebarlocation li[data-governorate-id]')
            )
            .filter(li => li.getAttribute('data-governorate-id') !== '')
            .map(li => ({
                governorate_id: li.getAttribute('data-governorate-id'),
                name:  (li.querySelector('.span-governorate-name') || li).textContent.trim(),
                count: parseInt(
                    (li.querySelector('.span-number-of-cars') || {textContent:'0'}).textContent.trim()
                ) || 0
            }))
            .filter(l => l.count > 0)
            .sort((a,b) => b.count - a.count);
        """)
        return locations or []

    def _click_location(self, governorate_id: str):
        """Click a location filter <li> and wait for the listing to reload."""
        self.driver.execute_script(
            "document.querySelector("
            f"'#sidebarlocation li[data-governorate-id=\"{governorate_id}\"]'"
            ").click();"
        )
        time.sleep(4)   # let React/JS re-render the filtered list

    # =========================================================================
    # Scroll helper
    # =========================================================================

    def _scroll_all_cars(self, location_label: str = "") -> int:
        """
        Scroll the current page until no new car-card elements appear for
        STABLE_LIMIT consecutive scroll attempts.

        Starts counting from whatever is already in the DOM (so clicking a
        location filter that pre-populates 40 cards won't mislead the counter).

        Returns the final car count.
        """
        # Prime with the current count so we don't falsely tick stable_runs
        prev_count  = self.driver.execute_script(
            "return document.querySelectorAll('div.car-card').length;"
        )
        stable_runs = 0
        scroll_num  = 0

        while scroll_num < MAX_SCROLLS:
            self.driver.execute_script("""
                window.scrollTo(0, document.body.scrollHeight);
                document.documentElement.scrollTop =
                    document.documentElement.scrollHeight;
                window.scrollBy(0, window.innerHeight);
            """)
            time.sleep(SCROLL_WAIT)
            scroll_num += 1

            current_count = self.driver.execute_script(
                "return document.querySelectorAll('div.car-card').length;"
            )

            if current_count == prev_count:
                stable_runs += 1
                if stable_runs >= STABLE_LIMIT:
                    logger.info(
                        f"[Stage 1] [{location_label}] End of list — "
                        f"{current_count} cards in {scroll_num} scrolls"
                    )
                    break
            else:
                logger.info(
                    f"[Stage 1] [{location_label}] Scroll {scroll_num}: "
                    f"{current_count} cards (was {prev_count})"
                )
                stable_runs = 0
                prev_count  = current_count

        return prev_count

    # =========================================================================
    # STAGE 1 — Collect raw card dicts via location-filter + infinite scroll
    # =========================================================================

    def scrape(self) -> List[Dict]:
        """
        Stage 1: for every location filter → click → scroll → collect cards.
        Stage 2: requests → visit each detail page, merge fields, parse to 25 cols.
        """
        raw_cards: List[Dict] = []
        seen_urls: Set[str]   = set()   # deduplication by ad URL

        # ── Stage 1 ──────────────────────────────────────────────────────────
        try:
            self._init_driver()
            logger.info(f"[Stage 1] Loading: {self.base_url}")
            self.driver.get(self.base_url)
            time.sleep(5)

            # Extract all location filters
            locations = self._get_location_filters()
            if not locations:
                logger.warning("[Stage 1] No location filters found — falling back to homepage scroll")
                locations = [{'governorate_id': None, 'name': 'homepage', 'count': 9999}]

            logger.info(
                f"[Stage 1] Found {len(locations)} locations, "
                f"total expected cars: {sum(l['count'] for l in locations)}"
            )

            for loc in locations:
                gov_id = loc['governorate_id']
                label  = loc['name']
                expected = loc['count']
                logger.info(f"[Stage 1] === Location: {label} ({expected} cars) ===")

                # Navigate to homepage fresh for each location
                self.driver.get(self.base_url)
                time.sleep(5)

                # Click location filter (unless we're doing the homepage fallback)
                if gov_id:
                    try:
                        self._click_location(gov_id)
                    except Exception as e:
                        logger.warning(f"[Stage 1] Could not click {label}: {e} — skipping")
                        continue

                # Scroll until end
                final_count = self._scroll_all_cars(label)

                # Parse full DOM
                soup      = BeautifulSoup(self.driver.page_source, 'html.parser')
                car_items = soup.find_all('div', class_='car-card')

                # Extract unique raw cards
                new_this_loc = 0
                for idx, item in enumerate(car_items):
                    try:
                        raw = self._extract_raw(item, len(raw_cards) + idx + 1)
                        if not raw:
                            continue
                        url = raw.get('ad_url') or raw.get('id')
                        if url and url not in seen_urls:
                            seen_urls.add(url)
                            raw_cards.append(raw)
                            new_this_loc += 1
                    except Exception as e:
                        logger.warning(f"[Stage 1] Card extract error: {e}")

                logger.info(
                    f"[Stage 1] {label}: {new_this_loc} new unique cards "
                    f"| total so far: {len(raw_cards)}"
                )

        except Exception as e:
            logger.error(f"[Stage 1] Fatal error: {e}", exc_info=True)
        finally:
            self._close_driver()

        logger.info(f"[Stage 1] Complete — {len(raw_cards)} unique raw cards collected")

        # ── Stage 2 ──────────────────────────────────────────────────────────
        logger.info(f"[Stage 2] Fetching detail pages for {len(raw_cards)} cars...")
        cars:  List[Dict] = []
        total = len(raw_cards)

        for idx, raw in enumerate(raw_cards, 1):
            ad_url = raw.get('ad_url')
            if ad_url:
                try:
                    logger.info(f"[Stage 2] {idx}/{total}: {ad_url}")
                    resp = self.session.get(ad_url, timeout=20)
                    resp.raise_for_status()
                    detail_soup = BeautifulSoup(resp.text, 'html.parser')
                    detail = car_parser.extract_detail_from_soup(detail_soup)
                    raw    = car_parser.merge_detail(raw, detail)
                except Exception as e:
                    logger.warning(f"[Stage 2] Failed {ad_url}: {e}")

            try:
                item = car_parser.parse(raw)
                if item:
                    cars.append(item)
            except Exception as e:
                logger.error(f"[Stage 2] Parse error card {idx}: {e}")

            time.sleep(0.3)

        logger.info(f"[Stage 2] Complete — {len(cars)} cars parsed")
        self.log_scrape_result({
            'total_items': len(cars),
            'new_items':   len(cars),
            'duplicates':  0,
            'duration':    f"{total * 0.3:.0f}s detail",
        })
        return cars

    # =========================================================================
    # Stage 1 extraction helpers
    # =========================================================================

    def _extract_raw(self, item, index: int) -> Optional[Dict[str, Any]]:
        """
        STAGE 1 — Raw extraction only. No interpretation.
        Collects exactly what is on the card — labels and values as-is.
        """
        raw = {
            'source':          self.website_id or 'syriacar',
            'id':              f"{self.website_id or 'syriacar'}_{index}_{int(time.time())}",
            'scraped_at':      datetime.now().isoformat(),
            'listing_type':    'sell',
            'title_raw':       None,
            'price_raw':       None,
            'location_raw':    None,
            'description_raw': None,
            'ad_url':          None,
            'ad_id':           None,
            'specs_raw':       {},
            'images':          [],
            'phones_raw':      [],
            'seller_raw':      None,
        }

        # Link — prefer share-button data-link, fallback to <a href>
        share_button = item.find('button', class_='share-button')
        if share_button and share_button.get('data-link'):
            raw['ad_url'] = share_button['data-link']
        else:
            link_elem = item.find('a')
            if link_elem and link_elem.get('href'):
                href = link_elem['href']
                raw['ad_url'] = (
                    urljoin(self.base_url, href) if href.startswith('/') else href
                )

        # Images
        raw['images'] = self._extract_all_images(item)

        # card-info section
        card_info = item.find('div', class_='card-info')
        if card_info:
            raw['description_raw'] = card_info.get_text(separator=' ', strip=True)

            # h1.car-title = brand (e.g. "كيا Kia")
            title_elem = card_info.find('h1', class_='car-title')
            if title_elem:
                raw['title_raw'] = title_elem.get_text(strip=True)

            # h2.car-sub-title = "Sportage • إس يو في • 2017"
            subtitle_elem = card_info.find('h2', class_='car-sub-title')
            if subtitle_elem:
                parts = [p.strip() for p in subtitle_elem.get_text().split('•') if p.strip()]
                specs = raw['specs_raw']
                if len(parts) >= 1:
                    specs['الموديل']    = parts[0]
                if len(parts) >= 2:
                    specs['نوع الهيكل'] = parts[1]
                if len(parts) >= 3:
                    specs['السنة']      = parts[2]

            # features-a: mileage / location
            # features-b: fuel / origin
            # features-c: transmission / condition
            features_div = card_info.find('div', class_='features')
            if features_div:
                specs = raw['specs_raw']

                fa = features_div.find('div', class_='features-a')
                if fa:
                    divs = fa.find_all('div')
                    if len(divs) >= 1:
                        specs['الكيلومترات'] = divs[0].get_text(strip=True)
                    if len(divs) >= 2:
                        raw['location_raw'] = divs[1].get_text(strip=True)

                fb = features_div.find('div', class_='features-b')
                if fb:
                    divs = fb.find_all('div')
                    if len(divs) >= 1:
                        specs['نوع الوقود'] = divs[0].get_text(strip=True)
                    if len(divs) >= 2:
                        specs['المصدر']     = divs[1].get_text(strip=True)

                fc = features_div.find('div', class_='features-c')
                if fc:
                    divs = fc.find_all('div')
                    if len(divs) >= 1:
                        specs['ناقل الحركة'] = divs[0].get_text(strip=True)
                    if len(divs) >= 2:
                        specs['الحالة']      = divs[1].get_text(strip=True)

        # Price
        price_btn = item.find('button', class_='btn-contact-p')
        if price_btn:
            raw['price_raw'] = price_btn.get_text(strip=True)

        return raw

    def _extract_all_images(self, item) -> List[str]:
        images = []
        try:
            for img in item.find_all('img'):
                src = img.get('src') or img.get('data-src')
                if src:
                    if src.startswith('/'):
                        src = urljoin(self.base_url, src)
                    elif not src.startswith('http'):
                        src = urljoin(self.base_url, src)
                    images.append(src)
        except Exception as e:
            logger.warning(f"Image extract error: {e}")
        return images

    def download_image(self, image_url: str, car_id: str) -> Optional[str]:
        """Download image locally (optional, kept for future use)."""
        try:
            if not image_url:
                return None
            if not image_url.startswith('http'):
                image_url = urljoin(self.base_url, image_url)
            r = self.session.get(image_url, timeout=10)
            r.raise_for_status()
            ext = '.jpg'
            ct  = r.headers.get('content-type', '')
            if 'png'  in ct: ext = '.png'
            elif 'webp' in ct: ext = '.webp'
            fp = self.image_folder / f"car_{car_id}{ext}"
            fp.write_bytes(r.content)
            return str(fp)
        except Exception as e:
            logger.warning(f"Image download failed {image_url}: {e}")
            return None

    # =========================================================================
    # Statistics
    # =========================================================================

    def get_statistics(self, items: List[Dict]) -> Dict[str, Any]:
        if not items:
            return {'total_items': 0, 'price_stats': {}, 'year_stats': {}, 'brand_stats': {}}

        prices = [i.get('price') for i in items if isinstance(i.get('price'), (int, float))]
        years  = [i.get('year')  for i in items if isinstance(i.get('year'),  int)]
        brands = [i.get('brand') for i in items if i.get('brand')]

        return {
            'total_items': len(items),
            'price_stats': {
                'count':   len(prices),
                'average': round(sum(prices) / len(prices), 2) if prices else 0,
                'min':     min(prices) if prices else 0,
                'max':     max(prices) if prices else 0,
            },
            'year_stats': {
                'count':   len(years),
                'average': int(sum(years) / len(years)) if years else 0,
                'min':     min(years) if years else 0,
                'max':     max(years) if years else 0,
            },
            'brand_stats': {b: brands.count(b) for b in set(brands)},
            'items_with_complete_data': sum(
                1 for i in items
                if all([i.get('price'), i.get('brand'), i.get('year'), i.get('location')])
            ),
        }
