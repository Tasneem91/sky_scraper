"""
Kilometrage.net Motors Scraper
Scrapes car listings from https://kilometrage.net/ar
Handles pagination via ?page=1, ?page=2, etc.
Uses Playwright for JavaScript rendering
Extracts structured car data: brand, model, location, mileage, year, transmission, fuel, price
"""

import logging
import re
from datetime import datetime
from typing import List, Dict, Any

from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
from scrapers import parser as car_parser

logger = logging.getLogger(__name__)


class KilometrageScraper:
    """Scraper for Kilometrage.net Motors website"""

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize scraper with configuration

        Args:
            config: Website configuration dictionary
        """
        self.config = config
        self.base_url = config.get('url', 'https://kilometrage.net/ar')
        self.items = []
        self.playwright = None
        self.browser = None
        self.page = None

    def _init_browser(self):
        """Initialize Playwright browser"""
        try:
            self.playwright = sync_playwright().start()
            self.browser = self.playwright.chromium.launch()
            # Add user-agent to avoid blocking
            self.page = self.browser.new_page(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            )
            logger.info("Playwright browser initialized with user-agent")
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
        Scrape all pages from Kilometrage using Playwright

        Returns:
            List of car listing dictionaries with unified schema (25 columns)
        """
        logger.info(f"Starting Kilometrage scraper for: {self.base_url}")
        self.items = []

        try:
            self._init_browser()

            page = 1
            max_pages = 500  # Safety limit
            consecutive_empty_pages = 0

            while page <= max_pages:
                try:
                    logger.info(f"Scraping page {page}")
                    url = f"{self.base_url}?page={page}" if page > 1 else self.base_url

                    # Navigate to page with increased timeout and different wait strategy
                    # Try 'load' first (faster), fallback to 'networkidle' if needed
                    try:
                        self.page.goto(url, wait_until='load', timeout=60000)
                    except Exception as load_error:
                        logger.warning(f"'load' strategy timeout, trying 'networkidle': {load_error}")
                        self.page.goto(url, wait_until='networkidle', timeout=60000)

                    # Wait for car listings to render
                    try:
                        self.page.wait_for_selector(
                            ".product-card",
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
                    listings = soup.find_all('div', class_='product-card')

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

                    # Extract each listing
                    page_items = 0
                    for idx, listing in enumerate(listings):
                        try:
                            item = self._extract_listing(listing)
                            if item:
                                self.items.append(item)
                                page_items += 1
                        except Exception as e:
                            logger.warning(f"Error extracting listing {idx} on page {page}: {e}")
                            continue

                    logger.info(f"Extracted {page_items} items from page {page}")
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

    def _extract_listing(self, listing_div) -> Dict[str, Any]:
        """Stage 1 (raw) + Stage 2 (parse) for a single Kilometrage card."""
        try:
            raw = self._extract_raw(listing_div)
            if not raw:
                return None
            return car_parser.parse(raw)
        except Exception as e:
            logger.error(f"Error extracting listing: {e}")
            return None

    def _extract_raw(self, listing_div) -> Dict[str, Any]:
        """STAGE 1 — Raw extraction only. Collects labels/values as-is."""
        raw = {
            'source':      'kilometrage',
            'id':          f"kilometrage_{len(self.items)}_{int(datetime.now().timestamp())}",
            'scraped_at':  datetime.now().isoformat(),
            'listing_type': 'sell',
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

        # Category
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

        # Link
        parent_a = listing_div.find_parent('a')
        if parent_a and parent_a.get('href'):
            raw['ad_url'] = parent_a['href']

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
