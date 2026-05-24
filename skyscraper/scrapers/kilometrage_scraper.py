"""
Kilometrage.net Motors Scraper — Two-Stage Architecture
  Stage 1: Playwright — URL-based pagination (?page=N) → collect raw card dicts + ad URLs
            (listing page is JS-rendered — needs real browser)
  Stage 2: requests + BeautifulSoup — fetch each detail page
            (detail pages are SSR — plain HTTP works)

Extracts: brand, model, price, location, mileage, year, transmission, fuel
"""

import logging
import re
import time
import requests
from datetime import datetime
from typing import List, Dict, Any, Optional
from urllib.parse import urljoin

from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
from scrapers import parser as car_parser

logger = logging.getLogger(__name__)

BASE_URL = 'https://kilometrage.net'

REQUEST_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept-Language': 'ar,en-US;q=0.9,en;q=0.8',
}


class KilometrageScraper:
    """Scraper for Kilometrage.net Motors website."""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.base_url = config.get('url', 'https://kilometrage.net/ar')
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
            logger.info(f"[Stage 1] Starting: {self.base_url}")

            page_num = 1
            max_pages = 500
            consecutive_empty = 0

            while page_num <= max_pages:
                try:
                    logger.info(f"[Stage 1] Page {page_num}")
                    url = f"{self.base_url}?page={page_num}" if page_num > 1 else self.base_url

                    try:
                        self.page.goto(url, wait_until='load', timeout=60000)
                    except Exception:
                        self.page.goto(url, wait_until='networkidle', timeout=60000)

                    # Wait for car listing cards to render
                    try:
                        self.page.wait_for_selector(".product-card", timeout=10000)
                    except Exception:
                        consecutive_empty += 1
                        if consecutive_empty >= 3:
                            logger.info("[Stage 1] 3 empty pages — stopping")
                            break
                        page_num += 1
                        continue

                    html_content = self.page.content()
                    soup = BeautifulSoup(html_content, 'html.parser')
                    listings = soup.find_all('div', class_='product-card')

                    if not listings:
                        consecutive_empty += 1
                        if consecutive_empty >= 3:
                            break
                        page_num += 1
                        continue

                    consecutive_empty = 0

                    page_count = 0
                    for idx, listing in enumerate(listings):
                        try:
                            raw = self._extract_raw(listing, len(raw_cards))
                            if raw:
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

    def _extract_raw(self, listing_div, card_index: int) -> Dict[str, Any]:
        """
        STAGE 1 — Raw extraction only. No interpretation.
        Collects all Kilometrage card data into a neutral raw dict.
        """
        raw = {
            'source':          'kilometrage',
            'id':              f"kilometrage_{card_index}_{int(datetime.now().timestamp())}",
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
        }

        specs = raw['specs_raw']

        # Brand from h5
        brand_elem = listing_div.find('h5')
        if brand_elem:
            specs['الماركة'] = brand_elem.get_text(strip=True)

        # Model from h6 spans
        model_elem = listing_div.find('h6')
        if model_elem:
            parts = [s.get_text(strip=True) for s in model_elem.find_all('span') if s.get_text(strip=True)]
            if parts:
                specs['الموديل'] = ' '.join(parts)

        # Category from h6.text-primary
        cat_elems = listing_div.find_all('h6', class_='text-primary')
        if cat_elems:
            raw['title_raw'] = cat_elems[0].get_text(strip=True)

        # Price
        price_elem = listing_div.find('span', class_='text-success')
        if price_elem:
            raw['price_raw'] = price_elem.get_text(strip=True)

        # Location / mileage / year (first col-6)
        col_divs = listing_div.find_all('div', class_='col-6')
        if len(col_divs) >= 1:
            col12s = col_divs[0].find_all('div', class_='col-12')
            if len(col12s) >= 1:
                raw['location_raw'] = col12s[0].get_text(strip=True)
            if len(col12s) >= 2:
                specs['الكيلومترات'] = col12s[1].get_text(strip=True)
            if len(col12s) >= 3:
                specs['السنة'] = col12s[2].get_text(strip=True)

        # Transmission / fuel (second col-6)
        if len(col_divs) >= 2:
            col12s = col_divs[1].find_all('div', class_='col-12')
            if len(col12s) >= 1:
                specs['ناقل الحركة'] = col12s[0].get_text(strip=True)
            if len(col12s) >= 2:
                specs['نوع الوقود'] = col12s[1].get_text(strip=True)

        # Image
        img = listing_div.find('img', class_='card-img-top')
        if img and img.get('src'):
            raw['images'] = [img['src']]

        # Link — make absolute if relative
        parent_a = listing_div.find_parent('a')
        if parent_a and parent_a.get('href'):
            href = parent_a['href']
            if href.startswith('/'):
                raw['ad_url'] = urljoin(BASE_URL, href)
            elif href.startswith('http'):
                raw['ad_url'] = href
            else:
                raw['ad_url'] = urljoin(self.base_url, href)

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
