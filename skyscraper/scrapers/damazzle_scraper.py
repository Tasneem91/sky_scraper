"""
Damazzle.com Motors Scraper — Two-Stage Architecture
  Stage 1: Playwright — URL-based pagination → collect raw card dicts + ad URLs
            (listing pages are Angular CSR — needs real browser)
  Stage 2: requests + BeautifulSoup — fetch each detail page
            (detail pages at /ads/{id} — tries plain HTTP first)

Handles:
  SELL listings: https://damazzle.com/motors/cars/search
  RENT listings: https://damazzle.com/motors/cars-for-rent/search
"""

import logging
import re
import time
import requests
from datetime import datetime
from typing import List, Dict, Any, Optional

from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
from scrapers import parser as car_parser

logger = logging.getLogger(__name__)

REQUEST_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept-Language': 'ar,en-US;q=0.9,en;q=0.8',
}


class DamazzleScraper:
    """Scraper for Damazzle Motors website (SELL and RENT listings)."""

    def __init__(self, config: Dict[str, Any], listing_type: str = "sell"):
        self.config = config
        self.listing_type = listing_type

        if listing_type == "rent":
            self.base_url = "https://damazzle.com/motors/cars-for-rent/search"
        else:
            self.base_url = config.get('url', 'https://damazzle.com/motors/cars/search')

        self.items: List[Dict] = []
        self.playwright = None
        self.browser = None
        self.page = None

    # =========================================================================
    # Browser lifecycle (Stage 1 only)
    # =========================================================================

    def _init_browser(self):
        try:
            self.playwright = sync_playwright().start()
            self.browser = self.playwright.chromium.launch()
            self.page = self.browser.new_page(
                user_agent=REQUEST_HEADERS['User-Agent']
            )
            logger.info("Playwright browser initialized")
        except Exception as e:
            logger.error(f"Error initializing Playwright: {e}")
            raise

    def _close_browser(self):
        try:
            if self.page:
                self.page.close()
            if self.browser:
                self.browser.close()
            if self.playwright:
                self.playwright.stop()
        except Exception as e:
            logger.warning(f"Error closing browser: {e}")
        finally:
            self.page = self.browser = self.playwright = None
            logger.info("Playwright browser closed")

    # =========================================================================
    # STAGE 1 — Collect raw card dicts via Playwright pagination
    # =========================================================================

    def scrape(self) -> List[Dict[str, Any]]:
        """
        Stage 1: Playwright URL pagination → collect all raw card dicts (including ad URLs).
        Stage 2: requests → visit each detail URL, merge fields, parse to 25 cols.
        Browser is closed after Stage 1.
        """
        raw_cards: List[Dict] = []

        # ── Stage 1 ──────────────────────────────────────────────────────────
        try:
            self._init_browser()
            logger.info(f"[Stage 1] Starting ({self.listing_type}): {self.base_url}")

            page_num = 1
            max_pages = 500
            consecutive_empty = 0

            while page_num <= max_pages:
                try:
                    logger.info(f"[Stage 1] Page {page_num}")
                    url = f"{self.base_url}?page={page_num}"
                    self.page.goto(url, wait_until='domcontentloaded', timeout=30000)
                    time.sleep(2)   # let Angular finish rendering

                    # Wait for listings to render
                    try:
                        self.page.wait_for_selector(
                            "div.col-md-6.py-3.px-4.h-100.d-grid", timeout=10000
                        )
                    except Exception:
                        consecutive_empty += 1
                        if consecutive_empty >= 3:
                            logger.info("[Stage 1] 3 empty pages — stopping")
                            break
                        page_num += 1
                        continue

                    html_content = self.page.content()
                    soup = BeautifulSoup(html_content, 'html.parser')
                    listings = soup.find_all('div', class_='col-md-6')

                    if not listings:
                        consecutive_empty += 1
                        if consecutive_empty >= 3:
                            break
                        page_num += 1
                        continue

                    consecutive_empty = 0

                    # Extract CSS background images (stored in JS-evaluated style)
                    page_images = self._extract_all_page_images()
                    logger.debug(f"[Stage 1] Page {page_num}: {len(page_images)} images")

                    page_count = 0
                    for idx, listing in enumerate(listings):
                        try:
                            primary_image = page_images[idx] if idx < len(page_images) else None
                            raw = self._extract_raw(listing, primary_image)
                            if raw and raw.get('ad_id'):  # only keep real listings
                                raw_cards.append(raw)
                                page_count += 1
                        except Exception as e:
                            logger.warning(f"[Stage 1] Listing {idx} error: {e}")

                    logger.info(f"[Stage 1] Page {page_num}: +{page_count} | total: {len(raw_cards)}")
                    page_num += 1

                except Exception as e:
                    logger.error(f"[Stage 1] Page {page_num} error: {e}")
                    consecutive_empty += 1
                    if consecutive_empty >= 3:
                        break
                    page_num += 1

        finally:
            self._close_browser()

        logger.info(f"[Stage 1] Complete. {len(raw_cards)} raw cards collected")

        # ── Stage 2 ──────────────────────────────────────────────────────────
        logger.info(f"[Stage 2] Fetching detail pages for {len(raw_cards)} cars...")

        session = requests.Session()
        session.headers.update(REQUEST_HEADERS)

        items: List[Dict] = []
        total = len(raw_cards)

        for idx, raw in enumerate(raw_cards, 1):
            ad_url = raw.get('ad_url')
            if ad_url:
                try:
                    logger.info(f"[Stage 2] {idx}/{total}: {ad_url}")
                    resp = session.get(ad_url, timeout=20)
                    resp.raise_for_status()
                    detail_soup = BeautifulSoup(resp.text, 'html.parser')
                    detail = car_parser.extract_detail_from_soup(detail_soup)
                    raw = car_parser.merge_detail(raw, detail)
                except Exception as e:
                    logger.warning(f"[Stage 2] Failed {ad_url}: {e}")

            try:
                item = car_parser.parse(raw)
                if item:
                    items.append(item)
            except Exception as e:
                logger.error(f"[Stage 2] Parse error: {e}")

            time.sleep(0.3)

        logger.info(f"[Stage 2] Complete. Total: {len(items)}")
        self.items = items
        return items

    # =========================================================================
    # Stage 1 extraction helpers
    # =========================================================================

    def _extract_all_page_images(self) -> List[str]:
        """
        Extract all listing image URLs from the current page via JavaScript.
        Images are stored as CSS background-image on .product-bg-rtl divs.
        """
        try:
            images = self.page.evaluate("""
                () => Array.from(document.querySelectorAll(".product-bg-rtl"))
                  .map(el => el.style.backgroundImage)
                  .filter(Boolean)
                  .map(bg => bg.replace(/^url\\(["']?/, "").replace(/["']?\\)$/, ""))
            """)
            return images if images else []
        except Exception as e:
            logger.error(f"Error extracting page images: {e}")
            return []

    def _extract_raw(self, listing_div, primary_image: Optional[str] = None) -> Dict[str, Any]:
        """
        STAGE 1 — Raw extraction only. No interpretation.
        Puts all Damazzle card data into a neutral raw dict.
        """
        raw = {
            'source':          'damazzle',
            'id':              None,
            'scraped_at':      datetime.now().isoformat(),
            'listing_type':    self.listing_type,
            'title_raw':       None,
            'price_raw':       None,
            'location_raw':    None,
            'description_raw': None,
            'ad_url':          None,
            'ad_id':           None,
            'specs_raw':       {},
            'images':          [primary_image] if primary_image else [],
            'phones_raw':      [],
            'whatsapp':        None,
            'seller_raw':      None,
            'posted_date':     None,
        }

        # Price
        price_elem = listing_div.find('div', class_='text-orange')
        if price_elem:
            raw['price_raw'] = price_elem.get_text(strip=True)

        # Brand + category (bg-purple spans)
        brand_spans = listing_div.find_all('span', class_='bg-purple')
        if brand_spans:
            raw['specs_raw']['الماركة'] = brand_spans[0].get_text(strip=True)
            if len(brand_spans) > 1:
                raw['specs_raw']['الفئة'] = brand_spans[1].get_text(strip=True)

        # Year and mileage from <li> items
        for li in listing_div.find_all('li'):
            text = li.get_text(strip=True)
            if re.search(r'\b\d{4}\b', text):
                raw['specs_raw']['السنة'] = text
            elif 'كم' in text or 'km' in text.lower():
                raw['specs_raw']['الكيلومترات'] = text

        # Title
        title_elem = listing_div.find('h5', class_='product-title')
        if title_elem:
            raw['title_raw'] = title_elem.get_text(strip=True)

        # Location + posted date
        loc_div = listing_div.find('div', class_='text-muted')
        if loc_div:
            parts = loc_div.get_text(strip=True).split('|')
            raw['location_raw'] = parts[0].strip() if parts else None
            raw['posted_date']  = parts[1].strip() if len(parts) > 1 else None

        # Ad ID + WhatsApp from WhatsApp link href
        wa_link = listing_div.find('a', class_='btn-whatsapp')
        if wa_link and wa_link.get('href'):
            href = wa_link['href']
            m = re.search(r'/ads/([^&?]+)', href)
            if m:
                ad_id = m.group(1)
                raw['ad_id']  = ad_id
                raw['ad_url'] = f"https://damazzle.com/ads/{ad_id}"
                raw['id']     = f"damazzle_{ad_id}"
            wa_m = re.search(r'wa\.me/(\d+)', href)
            if wa_m:
                raw['whatsapp'] = wa_m.group(1)

        return raw

    # =========================================================================
    # Statistics
    # =========================================================================

    def get_statistics(self, items: List[Dict]) -> Dict[str, Any]:
        if not items:
            return {'total_items': 0, 'price_stats': {}, 'year_stats': {}, 'brand_stats': {}}

        prices = [i.get('price') for i in items if i.get('price')]
        years  = [i.get('year')  for i in items if i.get('year')]
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
            'brand_stats': self._count_brands(brands),
            'items_with_complete_data': sum(
                1 for i in items
                if all([i.get('price'), i.get('brand'), i.get('year'), i.get('location')])
            ),
        }

    def _count_brands(self, brands: List[str]) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for b in brands:
            counts[b] = counts.get(b, 0) + 1
        return dict(sorted(counts.items(), key=lambda x: x[1], reverse=True))
