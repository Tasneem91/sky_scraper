"""
Carsy.app Scraper — Two-Stage Architecture
  Stage 1: Playwright — click-based pagination to collect all car URLs
            (listing page is React/CSR — needs real browser)
  Stage 2: requests + BeautifulSoup — fetch each detail page
            (detail pages are Next.js SSR — plain HTTP works, no browser needed)

This split gives maximum speed: browser only used for the 50-page listing,
then ~989 detail pages are fetched concurrently-safe with plain requests.

Arabic label mapping (Carsy's reversed naming):
  الموديل  → brand  (e.g. Toyota)
  الماركة  → model  (e.g. Camry)
"""

import logging
import re
import time
import json
import requests
from datetime import datetime
from typing import List, Dict, Any, Optional

from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
from scrapers.parser import CARSY_SPEC_MAP
from scrapers import parser as car_parser

logger = logging.getLogger(__name__)

BASE_URL = "https://carsy.app"

REQUEST_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept-Language': 'ar,en-US;q=0.9,en;q=0.8',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
}


class CarsyScraper:
    """
    Two-stage Carsy.app scraper.
    Stage 1 uses Playwright (React pagination), Stage 2 uses requests (SSR detail pages).
    """

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.base_url = config.get('url', 'https://carsy.app/cars')
        self.items = []
        self.playwright = None
        self.browser = None
        self.page = None

    # =========================================================================
    # Browser lifecycle (Stage 1 only)
    # =========================================================================

    def _init_browser(self):
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(headless=False)
        self.page = self.browser.new_page(
            user_agent=REQUEST_HEADERS['User-Agent']
        )
        self.page.set_extra_http_headers({
            'Accept-Language': REQUEST_HEADERS['Accept-Language'],
            'Accept': REQUEST_HEADERS['Accept'],
        })
        logger.info("Browser initialized (Stage 1 only)")

    def _close_browser(self):
        for obj, method in [(self.page, 'close'), (self.browser, 'close'), (self.playwright, 'stop')]:
            try:
                if obj:
                    getattr(obj, method)()
            except Exception:
                pass
        self.page = self.browser = self.playwright = None
        logger.info("Browser closed")

    def _goto(self, url: str):
        try:
            self.page.goto(url, wait_until='load', timeout=60000)
        except Exception:
            self.page.goto(url, wait_until='networkidle', timeout=60000)

    # =========================================================================
    # STAGE 1 — Collect all car URLs via React click-based pagination
    # =========================================================================
    # Facts confirmed via live DOM inspection:
    #   • Pagination <a> tags have NO href — React state-driven
    #   • URL never changes after clicking
    #   • التالي selector: a[data-slot="pagination-link"][aria-label="الذهاب إلى الصفحة التالية"]
    #   • True disabled = standalone class 'pointer-events-none' (NOT 'disabled:pointer-events-none')
    #   • 50 pages, ~20 cars per page (~989 total)

    def _collect_car_links(self) -> List[Dict[str, Any]]:
        """Click through all pagination pages and collect car links + card metadata."""
        all_cars: Dict[str, Dict] = {}
        page_num = 1

        logger.info(f"[Stage 1] Loading: {self.base_url}")
        self._goto(self.base_url)

        while True:
            # Wait for car cards to render
            try:
                self.page.wait_for_selector("a[href^='/cars/']", timeout=20000)
            except Exception:
                logger.warning(f"[Stage 1] No car links on page {page_num} — stopping")
                break

            time.sleep(2)  # Let React finish rendering

            # Record first car href BEFORE click (used to detect page change)
            first_href_before = self.page.evaluate("""
                () => {
                    const a = Array.from(document.querySelectorAll('a[href]'))
                        .find(a => /^\\/cars\\/\\d+$/.test(a.getAttribute('href')));
                    return a ? a.getAttribute('href') : null;
                }
            """)

            # Extract all car cards on this page
            cards = self.page.evaluate("""
                () => {
                    const anchors = Array.from(document.querySelectorAll('a[href]'))
                        .filter(a => /^\\/cars\\/\\d+$/.test(a.getAttribute('href')));

                    return anchors.map(a => {
                        const titleEl   = a.querySelector('h3');
                        const allSpans  = Array.from(a.querySelectorAll('span'));
                        const priceEl   = allSpans.find(s => s.textContent.includes('$'));
                        const locEl     = a.querySelector('span.capitalize');

                        // Time posted: span next to a clock icon SVG
                        const svgs = Array.from(a.querySelectorAll('svg'));
                        const clockSvg = svgs.find(s => s.querySelector('circle'));
                        const timeSpan = clockSvg ? clockSvg.nextElementSibling : null;

                        return {
                            href:        a.getAttribute('href'),
                            title:       titleEl  ? titleEl.textContent.trim()  : null,
                            price_raw:   priceEl  ? priceEl.textContent.trim()  : null,
                            location:    locEl    ? locEl.textContent.trim()    : null,
                            posted_time: timeSpan ? timeSpan.textContent.trim() : null,
                        };
                    });
                }
            """)

            new_count = 0
            for card in cards:
                href = card.get('href', '')
                m = re.search(r'/cars/(\d+)', href)
                if not m:
                    continue
                car_id = m.group(1)
                if car_id in all_cars:
                    continue
                card['url'] = f"{BASE_URL}{href}"
                card['car_id'] = car_id
                all_cars[car_id] = card
                new_count += 1

            logger.info(f"[Stage 1] Page {page_num}: +{new_count} new | total: {len(all_cars)}")

            if new_count == 0:
                logger.info("[Stage 1] No new cars — done")
                break

            # ----------------------------------------------------------------
            # Click التالي — FIX: use class token split, not substring match.
            # Tailwind puts 'disabled:pointer-events-none' in ALL elements as
            # a conditional modifier. Split by whitespace to find the standalone
            # 'pointer-events-none' token that means it's truly disabled.
            # ----------------------------------------------------------------
            result = self.page.evaluate("""
                () => {
                    function isTrulyDisabled(el) {
                        const tokens = (el.className || '').split(/\\s+/);
                        return tokens.includes('pointer-events-none') ||
                               tokens.includes('opacity-50') ||
                               el.getAttribute('aria-disabled') === 'true';
                    }

                    // Primary: التالي via aria-label (shadcn pagination)
                    let btn = document.querySelector(
                        'a[data-slot="pagination-link"][aria-label="الذهاب إلى الصفحة التالية"]'
                    );
                    if (btn) {
                        if (isTrulyDisabled(btn)) return 'disabled';
                        btn.click();
                        return 'clicked';
                    }

                    // Fallback: any element with exact text التالي
                    const all = Array.from(document.querySelectorAll('a, button'));
                    btn = all.find(el => el.textContent.trim() === 'التالي');
                    if (btn) {
                        if (isTrulyDisabled(btn) || btn.disabled) return 'disabled';
                        btn.click();
                        return 'clicked-fallback';
                    }

                    return 'not-found';
                }
            """)

            logger.info(f"[Stage 1] Next button: {result}")

            if result in ('disabled', 'not-found'):
                logger.info(f"[Stage 1] Last page reached — stopping")
                break

            # Wait for React to re-render (first car href changes, URL stays same)
            try:
                self.page.wait_for_function(
                    """(prev) => {
                        const a = Array.from(document.querySelectorAll('a[href]'))
                            .find(a => /^\\/cars\\/\\d+$/.test(a.getAttribute('href')));
                        return a && a.getAttribute('href') !== prev;
                    }""",
                    arg=first_href_before,
                    timeout=15000
                )
            except Exception:
                logger.warning("[Stage 1] Page change timeout — sleeping 3s")
                time.sleep(3)

            page_num += 1

        logger.info(f"[Stage 1] Complete. Collected {len(all_cars)} car URLs")
        return list(all_cars.values())

    # =========================================================================
    # STAGE 2 — Fetch each detail page via requests (SSR — no browser needed)
    # =========================================================================

    def _scrape_detail_page(self, car_url: str) -> Dict[str, Any]:
        """
        STAGE 1 (detail) — Raw extraction from SSR detail page via requests.
        Returns a raw dict. No interpretation here.
        """
        raw_detail = {
            'title_raw':       None,
            'price_raw':       None,
            'specs_raw':       {},
            'description_raw': None,
            'seller_name':     None,
            'images':          [],
            'phone':           None,
            'whatsapp':        None,
        }

        try:
            resp = requests.get(car_url, headers=REQUEST_HEADERS, timeout=30)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, 'html.parser')

            # Title (h1)
            h1 = soup.find('h1')
            if h1:
                raw_detail['title_raw'] = h1.get_text(strip=True)

            # Price — first h2 that contains $ or digits
            first_h2 = soup.find('h2')
            if first_h2:
                text = first_h2.get_text(strip=True)
                if '$' in text or re.search(r'\d', text):
                    raw_detail['price_raw'] = text

            # Car specs: h2 "معلومات السيارة" → next div → pairs of divs
            # Structure confirmed: [label_div, value_div, label_div, value_div, ...]
            specs_h2 = soup.find('h2', string=re.compile(r'معلومات السيارة'))
            if specs_h2:
                specs_div = specs_h2.find_next('div')
                if specs_div:
                    children = specs_div.find_all('div', recursive=False)
                    for i in range(0, len(children) - 1, 2):
                        key = children[i].get_text(strip=True)
                        val = children[i + 1].get_text(strip=True)
                        if key and val:
                            raw_detail['specs_raw'][key] = val

            # Description: h2 "الوصف" → next div
            desc_h2 = soup.find('h2', string=re.compile(r'الوصف'))
            if desc_h2:
                desc_div = desc_h2.find_next('div')
                if desc_div:
                    raw_detail['description_raw'] = desc_div.get_text(separator=' ', strip=True)

            # Seller: h3 "معلومات البائع" → next div → h4
            seller_h3 = soup.find('h3', string=re.compile(r'معلومات البائع'))
            if seller_h3:
                seller_div = seller_h3.find_next('div')
                if seller_div:
                    h4 = seller_div.find('h4')
                    if h4:
                        raw_detail['seller_name'] = h4.get_text(strip=True)

            # Images
            skip = ('icon', 'logo', 'placeholder', 'avatar', 'flag', 'sprite')
            for img in soup.find_all('img'):
                src = img.get('src') or img.get('data-src') or ''
                if src.startswith('http') and len(src) > 30 and not any(k in src.lower() for k in skip):
                    raw_detail['images'].append(src)
            raw_detail['images'] = list(dict.fromkeys(raw_detail['images']))

            # Contact
            tel = soup.find('a', href=lambda h: h and h.startswith('tel:'))
            if tel:
                raw_detail['phone'] = tel['href'].replace('tel:', '').strip()

            wa = soup.find('a', href=lambda h: h and 'wa.me' in (h or ''))
            if wa:
                m = re.search(r'wa\.me/(\d+)', wa['href'])
                raw_detail['whatsapp'] = m.group(1) if m else wa['href']

        except requests.exceptions.RequestException as e:
            logger.error(f"HTTP error fetching {car_url}: {e}")
        except Exception as e:
            logger.error(f"Parse error on {car_url}: {e}")

        return raw_detail

    # =========================================================================
    # Main scrape() — orchestrates both stages
    # =========================================================================

    def scrape(self) -> List[Dict[str, Any]]:
        """
        Stage 1: Playwright collects all car URLs (React pagination).
        Stage 2: requests fetches each detail page (Next.js SSR).
        Browser is closed between stages — detail scraping needs no browser.
        """
        logger.info(f"Starting Carsy scraper: {self.base_url}")
        self.items = []

        # ---- STAGE 1 ----
        try:
            self._init_browser()
            car_cards = self._collect_car_links()
        finally:
            self._close_browser()  # Browser done after Stage 1

        if not car_cards:
            logger.warning("No car links found in Stage 1")
            return []

        # ---- STAGE 2 ----
        total = len(car_cards)
        logger.info(f"[Stage 2] Fetching {total} detail pages via requests...")

        for idx, card in enumerate(car_cards):
            car_url = card.get('url', '')
            logger.info(f"[Stage 2] {idx + 1}/{total}: {car_url}")

            try:
                detail = self._scrape_detail_page(car_url)
                item = self._build_item(card, detail, car_url)
                if item:
                    self.items.append(item)
            except Exception as e:
                logger.error(f"[Stage 2] Error on {car_url}: {e}")
                continue

            time.sleep(0.3)  # Polite delay between requests

        logger.info(f"Scraping complete. Total items: {len(self.items)}")
        return self.items

    # =========================================================================
    # Item Builder
    # =========================================================================

    def _build_item(self, card: Dict, raw_detail: Dict, car_url: str) -> Optional[Dict[str, Any]]:
        """
        STAGE 2 — Merge Stage 1 card + detail raw data, then run shared parser.
        All interpretation happens in car_parser.parse(), not here.
        """
        try:
            ad_id_m = re.search(r'/cars/(\d+)', car_url)
            ad_id = ad_id_m.group(1) if ad_id_m else None

            # Compose a single raw dict for the parser
            raw = {
                'source':          'carsy',
                'id':              f"carsy_{ad_id}" if ad_id else f"carsy_{int(datetime.now().timestamp())}",
                'ad_id':           ad_id,
                'ad_url':          car_url,
                'scraped_at':      datetime.now().isoformat(),
                'listing_type':    'sell',

                # Prefer detail page title/price (more complete), card as fallback
                'title_raw':       raw_detail.get('title_raw') or card.get('title'),
                'price_raw':       raw_detail.get('price_raw') or card.get('price_raw'),
                'location_raw':    card.get('location'),
                'description_raw': raw_detail.get('description_raw'),
                'posted_date':     card.get('posted_time'),

                # Specs from detail page (Carsy reversed label map applied in parser)
                'specs_raw':       raw_detail.get('specs_raw', {}),

                # Images, contact, seller from detail page
                'images':          raw_detail.get('images', []),
                'seller_name':     raw_detail.get('seller_name'),
                'phone':           raw_detail.get('phone'),
                'whatsapp':        raw_detail.get('whatsapp'),
                'phones_raw':      [],
            }

            # Use CARSY_SPEC_MAP (reversed brand/model naming)
            return car_parser.parse(raw, CARSY_SPEC_MAP)

        except Exception as e:
            logger.error(f"Error building item for {car_url}: {e}")
            return None

    # =========================================================================
    # Helpers
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
