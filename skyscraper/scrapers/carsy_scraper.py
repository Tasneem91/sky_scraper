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
    # STAGE 1 — Collect all car links via React click-based pagination
    # =========================================================================
    # KEY FACTS (confirmed via live DOM inspection):
    #   - Pagination <a> tags have NO href — purely React state-driven
    #   - URL never changes after clicking (window.location.search stays "")
    #   - Next button: a[data-slot="pagination-link"][aria-label="الذهاب إلى الصفحة التالية"]
    #   - Disabled state: class includes "pointer-events-none opacity-50"
    #   - 50 total pages (~989 cars, 20 per page)
    #   - Page change detected by watching first car href change in DOM

    def _collect_car_links(self) -> List[Dict[str, Any]]:
        """
        Collect all car links by clicking التالي and waiting for React to re-render.
        Detects page change by monitoring when the first car's href changes.
        """
        all_cars: Dict[str, Dict] = {}
        page_num = 1

        logger.info(f"[Stage 1] Loading listing page: {self.base_url}")
        self._goto(self.base_url)

        while True:
            # Wait for car cards
            try:
                self.page.wait_for_selector("a[href^='/cars/']", timeout=20000)
            except Exception:
                logger.warning(f"[Stage 1] No car links on page {page_num} — stopping")
                break

            # Wait for React to finish rendering
            time.sleep(2)

            # Record first car href BEFORE clicking — used to detect page change
            first_car_href_before = self.page.evaluate("""
                () => {
                    const first = Array.from(document.querySelectorAll('a[href]'))
                        .find(a => /^\\/cars\\/\\d+$/.test(a.getAttribute('href')));
                    return first ? first.getAttribute('href') : null;
                }
            """)

            # Extract all car cards on this page
            cards = self.page.evaluate("""
                () => {
                    const anchors = Array.from(document.querySelectorAll('a[href]'))
                        .filter(a => /^\\/cars\\/\\d+$/.test(a.getAttribute('href')));

                    return anchors.map(a => {
                        // Time posted (next to clock icon)
                        const allSvgs = Array.from(a.querySelectorAll('svg'));
                        const clockSvg = allSvgs.find(s =>
                            s.querySelector('circle') ||
                            (s.className && s.className.toString().includes('clock'))
                        );
                        const timeSpan = clockSvg ? clockSvg.nextElementSibling : null;

                        // Title
                        const titleEl = a.querySelector('h3');

                        // Price
                        const allSpans = Array.from(a.querySelectorAll('span'));
                        const priceEl = allSpans.find(s =>
                            s.textContent.trim().includes('$')
                        );

                        // Location (span.capitalize)
                        const locEl = a.querySelector('span.capitalize');

                        // Mileage (after gauge icon — look for span with +number or number,)
                        const mileageEl = allSpans.find(s =>
                            /^[+]?[\d,]+$/.test(s.textContent.trim()) ||
                            s.textContent.trim().startsWith('+')
                        );

                        return {
                            href:        a.getAttribute('href'),
                            posted_time: timeSpan ? timeSpan.textContent.trim() : null,
                            title:       titleEl  ? titleEl.textContent.trim()  : null,
                            price_raw:   priceEl  ? priceEl.textContent.trim()  : null,
                            location:    locEl    ? locEl.textContent.trim()    : null,
                            mileage:     mileageEl ? mileageEl.textContent.trim() : null,
                        };
                    });
                }
            """)

            # Add new cars to collection
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
                logger.info("[Stage 1] No new cars — done")
                break

            # ------------------------------------------------------------------
            # Click التالي button (exact selector confirmed via live DOM analysis)
            # aria-label="الذهاب إلى الصفحة التالية"
            # Disabled when class includes "pointer-events-none"
            # ------------------------------------------------------------------
            next_available = self.page.evaluate("""
                () => {
                    const btn = document.querySelector(
                        'a[data-slot="pagination-link"][aria-label="الذهاب إلى الصفحة التالية"]'
                    );
                    if (!btn) return 'not-found';
                    if (btn.className.includes('pointer-events-none')) return 'disabled';
                    btn.click();
                    return 'clicked';
                }
            """)

            logger.info(f"[Stage 1] Next button status: {next_available}")

            if next_available != 'clicked':
                logger.info(f"[Stage 1] Stopping — next button: {next_available}")
                break

            # ------------------------------------------------------------------
            # Wait for React to re-render new page content
            # Detect change by watching first car href — it changes when new
            # cars are rendered (URL itself never changes on this site)
            # ------------------------------------------------------------------
            try:
                self.page.wait_for_function(
                    """(prevHref) => {
                        const first = Array.from(document.querySelectorAll('a[href]'))
                            .find(a => /^\\/cars\\/\\d+$/.test(a.getAttribute('href')));
                        return first && first.getAttribute('href') !== prevHref;
                    }""",
                    arg=first_car_href_before,
                    timeout=15000
                )
                logger.info(f"[Stage 1] Page changed — first car href updated")
            except Exception:
                logger.warning("[Stage 1] wait_for_function timed out — sleeping 3s as fallback")
                time.sleep(3)

            page_num += 1

        logger.info(f"[Stage 1] Complete. Total links: {len(all_cars)}")
        return list(all_cars.values())

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
                    //    Strategy A: find every muted label span, get next
                    //    sibling font-medium value span (handles icon wrappers)
                    //    Strategy B: find bg-muted/50 containers directly
                    // -------------------------------------------------------
                    // Strategy A — label spans with text-muted-foreground
                    const labelSpans = Array.from(document.querySelectorAll('span'))
                        .filter(s => s.className &&
                            s.className.includes('muted-foreground') &&
                            s.className.includes('text-sm'));

                    labelSpans.forEach(labelSpan => {
                        const label = labelSpan.textContent.trim();
                        if (!label) return;
                        // Value is next sibling span with font-medium, or
                        // next sibling of label's parent div
                        let valueEl = labelSpan.nextElementSibling;
                        if (!valueEl) {
                            // label might be inside a wrapper div; try parent's next sib
                            const parent = labelSpan.parentElement;
                            valueEl = parent ? parent.nextElementSibling : null;
                        }
                        if (valueEl) {
                            const value = valueEl.textContent.trim();
                            if (value && value !== label) {
                                result.specs[label] = value;
                            }
                        }
                    });

                    // Strategy B — bg-muted containers (spec grid items)
                    const specContainers = Array.from(document.querySelectorAll('div'))
                        .filter(d => d.className && d.className.includes('bg-muted'));
                    specContainers.forEach(container => {
                        const allSpans = Array.from(container.querySelectorAll('span'));
                        const labelEl = allSpans.find(s => s.className && s.className.includes('muted-foreground'));
                        const valueEl = allSpans.find(s => s.className && s.className.includes('font-medium'));
                        if (labelEl && valueEl) {
                            const label = labelEl.textContent.trim();
                            const value = valueEl.textContent.trim();
                            if (label && value && label !== value && !result.specs[label]) {
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
