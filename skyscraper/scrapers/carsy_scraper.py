"""
Carsy.app Scraper — Complete Rewrite
Two-stage scraping:
  Stage 1: Collect ALL car links using click-based pagination (Playwright)
  Stage 2: Visit each detail page — extract specs via page.evaluate() (JavaScript)

Key design decisions:
  - Click-based pagination: carsy.app is a React app; URL ?page=N does NOT work
  - page.evaluate(): runs inside the browser after React renders — reliable selector matching
  - brand/model mapping: on Carsy الموديل=Manufacturer, الماركة=Car series (reversed from standard)
  - Description: newlines replaced with spaces to prevent Google Sheets row overflow
"""

import logging
import re
import time
import json
from datetime import datetime
from typing import List, Dict, Any, Optional

from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

BASE_URL = "https://carsy.app"

# Carsy Arabic label → our schema field
# NOTE: Carsy uses الموديل for manufacturer (Toyota) and الماركة for model name (Camry)
SPEC_MAP = {
    'الموديل':          'brand',           # Toyota, Honda, etc.
    'الماركة':          'model',           # Camry, Corolla, etc.
    'السنة':            'year',
    'الكيلومترات':      'mileage',
    'نوع الوقود':       'fuel_type',
    'المحرك':           'engine',
    'ناقل الحركة':      'transmission',
    'اللون الخارجي':    'color',
    'اللون الداخلي':    'interior_color',
    'الأسطوانات':       'cylinders',
    'المفاتيح':         'keys',
    'المقاعد':          'seats',
    'نظام الدفع':       'drive_system',
    'المصدر':           'origin',
    'المواصفات':        'specs_category',
    'الحالة':           'condition',
    'نوع الهيكل':       'body_type',
}


class CarsyScraper:
    """Two-stage Carsy.app scraper using Playwright + JavaScript evaluation"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.base_url = config.get('url', 'https://carsy.app/cars')
        self.items = []
        self.playwright = None
        self.browser = None
        self.page = None

    # =========================================================================
    # Browser Management
    # =========================================================================

    def _init_browser(self):
        """Initialize Playwright with anti-bot headers"""
        try:
            self.playwright = sync_playwright().start()
            self.browser = self.playwright.chromium.launch(headless=True)
            self.page = self.browser.new_page(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            )
            self.page.set_extra_http_headers({
                'Accept-Language': 'ar,en-US;q=0.9,en;q=0.8',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            })
            logger.info("Browser initialized")
        except Exception as e:
            logger.error(f"Browser init error: {e}")
            raise

    def _close_browser(self):
        """Safely close all browser resources"""
        for obj, method in [(self.page, 'close'), (self.browser, 'close'), (self.playwright, 'stop')]:
            try:
                if obj:
                    getattr(obj, method)()
            except Exception:
                pass
        logger.info("Browser closed")

    def _goto(self, url: str):
        """Navigate with load → networkidle fallback, 60s timeout"""
        try:
            self.page.goto(url, wait_until='load', timeout=60000)
        except Exception:
            try:
                self.page.goto(url, wait_until='networkidle', timeout=60000)
            except Exception as e:
                raise Exception(f"Cannot load {url}: {e}")

    # =========================================================================
    # STAGE 1 — Collect all car links via click-based pagination
    # =========================================================================

    def _collect_car_links(self) -> List[Dict[str, Any]]:
        """
        Navigate the listing pages by clicking the Next button.
        Returns list of dicts: {url, title, price_raw, location, mileage, posted_time}
        """
        all_cars: Dict[str, Dict] = {}   # car_id → card data
        page_num = 1

        logger.info(f"[Stage 1] Loading: {self.base_url}")
        self._goto(self.base_url)

        while True:
            # Wait for car cards to appear
            try:
                self.page.wait_for_selector("a[href^='/cars/']", timeout=20000)
            except Exception:
                logger.warning(f"[Stage 1] No car links on page {page_num} — stopping")
                break

            # Let React finish rendering
            time.sleep(1.5)

            # Extract card data using JavaScript (runs after React renders)
            cards = self.page.evaluate("""
                () => {
                    const anchors = Array.from(document.querySelectorAll('a[href]'))
                        .filter(a => /^\\/cars\\/\\d+$/.test(a.getAttribute('href')));

                    return anchors.map(a => {
                        // Posted time
                        const clockEl = a.querySelector('[class*="lucide-clock"], svg[class*="clock"]');
                        const timeSpan = clockEl ? clockEl.nextElementSibling : null;

                        // Title
                        const titleEl = a.querySelector('h3');

                        // Price (look for $ sign or text-primary span)
                        const priceSpans = Array.from(a.querySelectorAll('span'));
                        const priceEl = priceSpans.find(s =>
                            s.textContent.includes('$') || s.className.includes('text-primary')
                        );

                        // Location (after map-pin icon)
                        const mapEl = a.querySelector('[class*="lucide-map-pin"], svg[class*="map-pin"]');
                        const locSpan = mapEl ? mapEl.nextElementSibling : null;

                        // Mileage (after gauge icon)
                        const gaugeEl = a.querySelector('[class*="lucide-gauge"], svg[class*="gauge"]');
                        const milSpan = gaugeEl ? gaugeEl.nextElementSibling : null;

                        return {
                            href: a.getAttribute('href'),
                            posted_time: timeSpan ? timeSpan.textContent.trim() : null,
                            title: titleEl ? titleEl.textContent.trim() : null,
                            price_raw: priceEl ? priceEl.textContent.trim() : null,
                            location: locSpan ? locSpan.textContent.trim() : null,
                            mileage: milSpan ? milSpan.textContent.trim() : null,
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
                all_cars[car_id] = card
                new_count += 1

            logger.info(f"[Stage 1] Page {page_num}: +{new_count} new cars (total: {len(all_cars)})")

            if new_count == 0:
                logger.info("[Stage 1] No new cars — stopping pagination")
                break

            # Try to click next page button
            if not self._click_next_page():
                logger.info("[Stage 1] No next page button found — all pages done")
                break

            page_num += 1

        logger.info(f"[Stage 1] Done. Total links collected: {len(all_cars)}")
        return list(all_cars.values())

    def _click_next_page(self) -> bool:
        """
        Find and click the next-page button using JavaScript.
        Returns True if successfully clicked, False if no button found.
        """
        clicked = self.page.evaluate("""
            () => {
                // Try aria-label selectors first
                const ariaSelectors = [
                    'button[aria-label*="next" i]',
                    'button[aria-label*="التالي"]',
                    'a[aria-label*="next" i]',
                    'button[aria-label*="Next"]',
                ];
                for (const sel of ariaSelectors) {
                    const el = document.querySelector(sel);
                    if (el && !el.disabled && !el.hasAttribute('disabled')) {
                        el.click();
                        return true;
                    }
                }

                // Look for buttons containing التالي (Arabic "Next")
                const allBtns = Array.from(document.querySelectorAll('button, a[role="button"]'));
                const nextBtn = allBtns.find(b =>
                    (b.textContent.trim() === 'التالي' ||
                     b.textContent.trim() === 'Next' ||
                     b.getAttribute('aria-label') === 'التالي') &&
                    !b.disabled && !b.hasAttribute('disabled') &&
                    b.offsetParent !== null   // visible
                );
                if (nextBtn) {
                    nextBtn.click();
                    return true;
                }

                // Try SVG chevron-right button (common in pagination)
                const chevronBtns = Array.from(document.querySelectorAll('button'));
                const chevronBtn = chevronBtns.find(b => {
                    const svg = b.querySelector('svg');
                    return svg && (
                        svg.className.toString().includes('chevron-right') ||
                        svg.className.toString().includes('ChevronRight') ||
                        b.querySelector('[class*="chevron-right"]')
                    ) && !b.disabled && !b.hasAttribute('disabled');
                });
                if (chevronBtn) {
                    chevronBtn.click();
                    return true;
                }

                return false;
            }
        """)

        if clicked:
            try:
                self.page.wait_for_load_state('networkidle', timeout=15000)
            except Exception:
                time.sleep(2)
            return True
        return False

    # =========================================================================
    # STAGE 2 — Scrape each car detail page via JavaScript
    # =========================================================================

    def _scrape_detail_page(self, car_url: str) -> Dict[str, Any]:
        """
        Visit a car detail page and extract all data using page.evaluate().
        JavaScript runs after React renders — reliable DOM access.
        """
        detail = {}

        try:
            self._goto(car_url)

            # Wait for the car info grid to render
            try:
                self.page.wait_for_selector('[class*="grid"]', timeout=15000)
            except Exception:
                logger.warning(f"Timeout waiting for detail page content: {car_url}")

            time.sleep(1.5)  # Allow React to finish rendering

            # Run JavaScript to extract everything at once
            data = self.page.evaluate("""
                () => {
                    const result = {
                        specs: {},
                        description: null,
                        images: [],
                        phone: null,
                        whatsapp: null,
                    };

                    // -------------------------------------------------------
                    // 1. Extract all spec items
                    //    Each spec: <div class="flex flex-col gap-1 ...">
                    //                 <span class="...muted...">LABEL</span>
                    //                 <span class="font-medium">VALUE</span>
                    //               </div>
                    // -------------------------------------------------------
                    const allDivs = Array.from(document.querySelectorAll('div'));
                    allDivs.forEach(div => {
                        const spans = Array.from(div.children).filter(el => el.tagName === 'SPAN');
                        if (spans.length === 2) {
                            const label = spans[0].textContent.trim();
                            const value = spans[1].textContent.trim();
                            if (label && value && label !== value) {
                                result.specs[label] = value;
                            }
                        }
                    });

                    // -------------------------------------------------------
                    // 2. Extract description (الوصف section)
                    // -------------------------------------------------------
                    const headings = Array.from(document.querySelectorAll('h2, h3, h4'));
                    const descHeading = headings.find(h => h.textContent.trim().includes('الوصف'));
                    if (descHeading) {
                        // Try next sibling element first
                        let next = descHeading.nextElementSibling;
                        if (next) {
                            result.description = next.textContent.trim().replace(/\\n+/g, ' ').replace(/\\s+/g, ' ');
                        }
                    }

                    // -------------------------------------------------------
                    // 3. Extract images from carousel/gallery
                    // -------------------------------------------------------
                    const imgElements = Array.from(document.querySelectorAll('img'));
                    const imgSrcs = imgElements
                        .map(img => img.src || img.getAttribute('src') || '')
                        .filter(src =>
                            src.startsWith('http') &&
                            !src.includes('icon') &&
                            !src.includes('logo') &&
                            !src.includes('placeholder') &&
                            !src.includes('avatar') &&
                            !src.includes('flag') &&
                            src.length > 30
                        );
                    result.images = [...new Set(imgSrcs)];

                    // -------------------------------------------------------
                    // 4. Extract contact info
                    // -------------------------------------------------------
                    const telLink = document.querySelector('a[href^="tel:"]');
                    if (telLink) {
                        result.phone = telLink.getAttribute('href').replace('tel:', '').trim();
                    }

                    const waLink = document.querySelector('a[href*="wa.me"]');
                    if (waLink) {
                        const waHref = waLink.getAttribute('href');
                        const waMatch = waHref.match(/wa\\.me\\/(\\d+)/);
                        result.whatsapp = waMatch ? waMatch[1] : waHref;
                    }

                    return result;
                }
            """)

            detail = data or {}

        except Exception as e:
            logger.error(f"Error scraping detail page {car_url}: {e}")

        return detail

    # =========================================================================
    # Main scrape() method
    # =========================================================================

    def scrape(self) -> List[Dict[str, Any]]:
        """
        Full two-stage scrape:
          Stage 1 → All car links + card info (click pagination)
          Stage 2 → Each detail page (JavaScript extraction)
        """
        logger.info(f"Starting Carsy scraper: {self.base_url}")
        self.items = []

        try:
            self._init_browser()

            # ---- STAGE 1 ----
            car_cards = self._collect_car_links()

            if not car_cards:
                logger.warning("No car links found in Stage 1")
                return []

            # ---- STAGE 2 ----
            total = len(car_cards)
            logger.info(f"[Stage 2] Scraping {total} detail pages...")

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

                # Polite delay between requests
                time.sleep(0.5)

        finally:
            self._close_browser()

        logger.info(f"Scraping complete. Total items: {len(self.items)}")
        return self.items

    # =========================================================================
    # Item Builder — merges card + detail into unified schema
    # =========================================================================

    def _build_item(self, card: Dict, detail: Dict, car_url: str) -> Optional[Dict[str, Any]]:
        """
        Merge Stage 1 card data + Stage 2 detail data into the unified schema
        + extra Carsy-specific fields.
        """
        try:
            specs = detail.get('specs', {})
            images = detail.get('images', [])

            # Map Arabic spec labels to schema fields
            mapped = {}
            for arabic_label, schema_field in SPEC_MAP.items():
                if arabic_label in specs:
                    mapped[schema_field] = specs[arabic_label]

            # Year: extract 4-digit number
            year_raw = mapped.get('year')
            year = None
            if year_raw:
                m = re.search(r'\d{4}', str(year_raw))
                if m:
                    year = int(m.group(0))

            # Price: clean to float
            price_raw = card.get('price_raw')
            price = self._clean_price(price_raw)

            # Mileage: prefer detail page value, fallback to card
            mileage = mapped.get('mileage') or card.get('mileage')

            # Build title from card (already has year+brand+model) or compose
            title = card.get('title')
            if not title:
                parts = [str(year or ''), mapped.get('brand', ''), mapped.get('model', '')]
                title = ' '.join(p for p in parts if p).strip()

            # Ad ID from URL
            ad_id_match = re.search(r'/cars/(\d+)', car_url)
            ad_id = ad_id_match.group(1) if ad_id_match else None

            # Images
            images_json = json.dumps(images, ensure_ascii=False)

            item = {
                # ---- Unified 25-column schema ----
                'scraped_at':     datetime.now().isoformat(),
                'source':         'carsy',
                'id':             f"carsy_{ad_id}" if ad_id else f"carsy_{int(datetime.now().timestamp())}",
                'title':          title,
                'price':          price,
                'price_raw':      price_raw,
                'brand':          mapped.get('brand'),
                'model':          mapped.get('model'),
                'category':       mapped.get('specs_category'),
                'year':           year,
                'mileage':        mileage,
                'location':       card.get('location'),
                'posted_date':    card.get('posted_time'),
                'condition':      mapped.get('condition'),
                'fuel_type':      mapped.get('fuel_type'),
                'transmission':   mapped.get('transmission'),
                'body_type':      mapped.get('body_type'),
                'origin':         mapped.get('origin'),
                'image_count':    len(images),
                'images':         images_json,
                'primary_image':  images[0] if images else None,
                'link':           car_url,
                'ad_id':          ad_id,
                'ad_url':         car_url,
                'description':    detail.get('description'),
                'listing_type':   'sell',

                # ---- Extra Carsy-specific fields ----
                'color':          mapped.get('color'),
                'interior_color': mapped.get('interior_color'),
                'engine':         mapped.get('engine'),
                'cylinders':      mapped.get('cylinders'),
                'seats':          mapped.get('seats'),
                'keys':           mapped.get('keys'),
                'drive_system':   mapped.get('drive_system'),
                'phone':          detail.get('phone'),
                'whatsapp':       detail.get('whatsapp'),
            }

            return item

        except Exception as e:
            logger.error(f"Error building item for {car_url}: {e}")
            return None

    # =========================================================================
    # Helpers
    # =========================================================================

    def _clean_price(self, price_text: str) -> Optional[float]:
        """Extract numeric price from raw string like '$4,000'"""
        if not price_text:
            return None
        try:
            cleaned = re.sub(r'[^\d.]', '', str(price_text))
            return float(cleaned) if cleaned else None
        except (ValueError, TypeError):
            return None

    def get_statistics(self, items: List[Dict]) -> Dict[str, Any]:
        """Calculate summary statistics from scraped items"""
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
