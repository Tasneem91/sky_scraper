"""
Damazzle.com Motors Scraper
Scrapes car listings from https://damazzle.com/motors/cars/search (SELL)
Scrapes car listings from https://damazzle.com/motors/cars-for-rent/search (RENT)
Handles pagination via ?page=1, ?page=2, etc.
Uses Playwright for JavaScript rendering (Angular)
Extracts images from CSS background-image styles
"""

import logging
import re
from datetime import datetime
from typing import List, Dict, Any

from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
from scrapers import parser as car_parser

logger = logging.getLogger(__name__)


class DamazzleScraper:
    """Scraper for Damazzle Motors website (both SELL and RENT)"""

    def __init__(self, config: Dict[str, Any], listing_type: str = "sell"):
        """
        Initialize scraper with configuration

        Args:
            config: Website configuration dictionary
            listing_type: Either "sell" or "rent"
        """
        self.config = config
        self.listing_type = listing_type  # "sell" or "rent"

        if listing_type == "rent":
            self.base_url = "https://damazzle.com/motors/cars-for-rent/search"
        else:
            self.base_url = config.get('url', 'https://damazzle.com/motors/cars/search')

        self.items = []
        self.playwright = None
        self.browser = None
        self.page = None

    def _init_browser(self):
        """Initialize Playwright browser"""
        try:
            self.playwright = sync_playwright().start()
            self.browser = self.playwright.chromium.launch()
            self.page = self.browser.new_page()
            logger.info("Playwright browser initialized")
        except Exception as e:
            logger.error(f"Error initializing Playwright: {e}")
            raise

    def _close_browser(self):
        """Close Playwright browser"""
        try:
            if self.page:
                self.page.close()
            if self.browser:
                self.browser.close()
            if self.playwright:
                self.playwright.stop()
            logger.info("Playwright browser closed")
        except Exception as e:
            logger.warning(f"Error closing browser: {e}")

    def scrape(self) -> List[Dict[str, Any]]:
        """
        Scrape all pages from Damazzle using Playwright

        Returns:
            List of car listing dictionaries with unified schema (25 columns)
        """
        logger.info(f"Starting Damazzle scraper ({self.listing_type}) for: {self.base_url}")
        self.items = []

        try:
            self._init_browser()

            page = 1
            max_pages = 500  # Increased to handle all 4152 cars
            consecutive_empty_pages = 0

            while page <= max_pages:
                try:
                    logger.info(f"Scraping page {page}")
                    url = f"{self.base_url}?page={page}"

                    # Navigate to page
                    self.page.goto(url, wait_until='networkidle', timeout=30000)

                    # Wait for car listings to render
                    try:
                        self.page.wait_for_selector(
                            "div.col-md-6.py-3.px-4.h-100.d-grid",
                            timeout=10000
                        )
                    except Exception as e:
                        logger.info(f"No listings found on page {page}.")
                        consecutive_empty_pages += 1
                        if consecutive_empty_pages >= 3:
                            logger.info("3 consecutive empty pages - stopping.")
                            break
                        page += 1
                        continue

                    # Get rendered HTML
                    html_content = self.page.content()

                    # Parse HTML
                    soup = BeautifulSoup(html_content, 'html.parser')

                    # Find all car listing containers
                    listings = soup.find_all('div', class_='col-md-6')

                    if not listings:
                        logger.info(f"No listings found on page {page}.")
                        consecutive_empty_pages += 1
                        if consecutive_empty_pages >= 3:
                            logger.info("3 consecutive empty pages - stopping.")
                            break
                        page += 1
                        continue

                    # Reset consecutive empty counter
                    consecutive_empty_pages = 0

                    # Extract ALL images from the page (GLOBAL extraction using JavaScript)
                    page_images = self._extract_all_page_images()
                    logger.debug(f"Extracted {len(page_images)} images from page {page}")

                    # Extract each listing
                    page_items = 0
                    for idx, listing in enumerate(listings):
                        try:
                            # Use corresponding image from page_images if available
                            primary_image = page_images[idx] if idx < len(page_images) else None

                            item = self._extract_listing(listing, primary_image)
                            if item:
                                self.items.append(item)
                                page_items += 1
                        except Exception as e:
                            logger.warning(f"Error extracting listing {idx} on page {page}: {e}")
                            continue

                    logger.info(f"Extracted {page_items} items from page {page} (with {len(page_images)} images)")

                    page += 1

                except Exception as e:
                    logger.error(f"Error processing page {page}: {e}")
                    consecutive_empty_pages += 1
                    if consecutive_empty_pages >= 3:
                        break
                    page += 1

        finally:
            self._close_browser()

        logger.info(f"Scraping complete. Total items: {len(self.items)}")
        return self.items

    def _extract_all_page_images(self) -> List[str]:
        """
        Extract ALL image URLs from the current page using JavaScript
        Images are stored in CSS background-image styles on .product-bg-rtl divs
        Uses the exact same approach as the provided code example

        Returns:
            List of image URLs in order
        """
        try:
            images = self.page.evaluate("""
                () => Array.from(document.querySelectorAll(".product-bg-rtl"))
                  .map(el => el.style.backgroundImage)
                  .filter(Boolean)
                  .map(bg => bg.replace(/^url\\(["']?/, "").replace(/["']?\\)$/, ""))
            """)

            logger.info(f"Successfully extracted {len(images)} images from page")

            # Log first few images for debugging
            if images:
                logger.debug(f"First image: {images[0]}")

            return images if images else []
        except Exception as e:
            logger.error(f"Error extracting page images: {e}")
            return []

    def _extract_listing(self, listing_div, primary_image: str = None) -> Dict[str, Any]:
        """
        Stage 1 (raw extraction) + Stage 2 (parse) for a single Damazzle card.
        Raw extraction collects labels/values as-is; parser interprets them.
        """
        try:
            raw = self._extract_raw(listing_div, primary_image)
            if not raw:
                return None
            return car_parser.parse(raw)
        except Exception as e:
            logger.error(f"Error extracting listing: {e}")
            return None

    def _extract_raw(self, listing_div, primary_image: str = None) -> Dict[str, Any]:
        """
        STAGE 1 — Raw extraction only. No interpretation.
        Puts all Damazzle card data into a neutral raw dict.
        """
        raw = {
            'source':      'damazzle',
            'id':          None,
            'scraped_at':  datetime.now().isoformat(),
            'listing_type': self.listing_type,
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

        # Location + posted date (text-muted div: "حلب | منذ 3 أيام")
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
            # Extract WhatsApp number from wa.me link
            wa_m = re.search(r'wa\.me/(\d+)', href)
            if wa_m:
                raw['whatsapp'] = wa_m.group(1)

        return raw

    def get_statistics(self, items: List[Dict]) -> Dict[str, Any]:
        """
        Calculate statistics from scraped items

        Args:
            items: List of scraped items

        Returns:
            Dictionary with statistics
        """
        if not items:
            return {
                'total_items': 0,
                'price_stats': {},
                'year_stats': {},
                'brand_stats': {},
            }

        # Extract prices (filter out None values)
        prices = [item.get('price') for item in items if item.get('price')]
        years = [item.get('year') for item in items if item.get('year')]
        brands = [item.get('brand') for item in items if item.get('brand')]

        stats = {
            'total_items': len(items),
            'price_stats': {
                'average': sum(prices) / len(prices) if prices else 0,
                'min': min(prices) if prices else 0,
                'max': max(prices) if prices else 0,
                'count': len(prices),
            },
            'year_stats': {
                'average': int(sum(years) / len(years)) if years else 0,
                'min': min(years) if years else 0,
                'max': max(years) if years else 0,
                'count': len(years),
            },
            'brand_stats': self._count_brands(brands),
            'items_with_complete_data': sum(
                1 for item in items
                if all([
                    item.get('price'),
                    item.get('brand'),
                    item.get('year'),
                    item.get('title'),
                    item.get('location'),
                ])
            ),
        }

        return stats

    def _count_brands(self, brands: List[str]) -> Dict[str, int]:
        """Count occurrences of each brand"""
        brand_counts = {}
        for brand in brands:
            brand_counts[brand] = brand_counts.get(brand, 0) + 1

        # Sort by count descending
        return dict(sorted(brand_counts.items(), key=lambda x: x[1], reverse=True))
