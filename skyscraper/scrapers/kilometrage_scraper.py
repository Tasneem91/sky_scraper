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

                    # Navigate to page
                    self.page.goto(url, wait_until='networkidle', timeout=30000)

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
        """
        Extract a single car listing from HTML
        Returns all 25 columns from unified schema

        Args:
            listing_div: BeautifulSoup div containing the listing

        Returns:
            Dictionary with extracted car data (unified schema)
        """
        try:
            # Initialize with all 25 unified schema fields
            item = {
                'scraped_at': datetime.now().isoformat(),
                'source': 'kilometrage',
                'id': None,
                'title': None,
                'price': None,
                'price_raw': None,
                'brand': None,
                'model': None,
                'category': None,
                'year': None,
                'mileage': None,
                'location': None,
                'posted_date': None,
                'condition': None,  # Not available for Kilometrage
                'fuel_type': None,
                'transmission': None,
                'body_type': None,  # Not available for Kilometrage
                'origin': None,  # Not available for Kilometrage
                'image_count': 0,
                'images': '[]',
                'primary_image': None,
                'link': None,
                'ad_id': None,
                'ad_url': None,
                'description': None,  # Not available for Kilometrage
                'listing_type': 'sell',
            }

            # Extract brand from h5
            brand_elem = listing_div.find('h5')
            if brand_elem:
                item['brand'] = brand_elem.get_text(strip=True)

            # Extract model from h6 (contains multiple spans)
            model_elem = listing_div.find('h6')
            if model_elem:
                model_spans = model_elem.find_all('span')
                if model_spans:
                    model_parts = []
                    for span in model_spans:
                        text = span.get_text(strip=True)
                        if text:
                            model_parts.append(text)
                    if model_parts:
                        item['model'] = ' '.join(model_parts)

            # Extract category from h6 with text-primary class (if exists)
            category_elems = listing_div.find_all('h6', class_='text-primary')
            if category_elems:
                item['category'] = category_elems[0].get_text(strip=True)

            # Extract price from text-success span
            price_elem = listing_div.find('span', class_='text-success')
            if price_elem:
                price_text = price_elem.get_text(strip=True)
                item['price_raw'] = price_text
                item['price'] = self._clean_price(price_text)

            # Extract location, mileage, year, transmission, fuel from col-6 divs
            col_divs = listing_div.find_all('div', class_='col-6')

            if len(col_divs) >= 2:
                # First col-6 contains: location, mileage, year
                first_col = col_divs[0]
                col_12s_first = first_col.find_all('div', class_='col-12')

                if len(col_12s_first) >= 1:
                    # Location (first col-12)
                    location_text = col_12s_first[0].get_text(strip=True)
                    if location_text:
                        item['location'] = location_text

                if len(col_12s_first) >= 2:
                    # Mileage (second col-12)
                    mileage_text = col_12s_first[1].get_text(strip=True)
                    if mileage_text:
                        item['mileage'] = mileage_text

                if len(col_12s_first) >= 3:
                    # Year (third col-12)
                    year_text = col_12s_first[2].get_text(strip=True)
                    if year_text:
                        year_match = re.search(r'\d{4}', year_text)
                        if year_match:
                            item['year'] = int(year_match.group(0))

                # Second col-6 contains: transmission, fuel, views
                second_col = col_divs[1]
                col_12s_second = second_col.find_all('div', class_='col-12')

                if len(col_12s_second) >= 1:
                    # Transmission (first col-12)
                    transmission_text = col_12s_second[0].get_text(strip=True)
                    if transmission_text:
                        item['transmission'] = transmission_text

                if len(col_12s_second) >= 2:
                    # Fuel (second col-12)
                    fuel_text = col_12s_second[1].get_text(strip=True)
                    if fuel_text:
                        item['fuel_type'] = fuel_text

            # Extract image
            img_elem = listing_div.find('img', class_='card-img-top')
            if img_elem and img_elem.get('src'):
                primary_image = img_elem.get('src')
                item['primary_image'] = primary_image
                item['images'] = f'["{primary_image}"]'
                item['image_count'] = 1

            # Extract link from parent anchor tag
            parent_link = listing_div.find_parent('a')
            if parent_link and parent_link.get('href'):
                link = parent_link.get('href')
                item['link'] = link
                item['ad_url'] = link
                # Create a unique ID
                item['id'] = f"kilometrage_{len(self.items)}_{int(datetime.now().timestamp())}"

            # Create title from brand and model
            if item['brand'] and item['model']:
                item['title'] = f"{item['brand']} {item['model']}"
            elif item['brand']:
                item['title'] = item['brand']

            return item

        except Exception as e:
            logger.error(f"Error extracting listing: {e}")
            return None

    def _clean_price(self, price_text: str) -> float:
        """
        Clean and convert price string to float

        Args:
            price_text: Raw price text (e.g., "17,000$")

        Returns:
            Float price value
        """
        try:
            # Remove spaces, currency symbols, and commas
            cleaned = re.sub(r'[^\d.]', '', price_text)
            if cleaned:
                return float(cleaned)
            return None
        except (ValueError, TypeError):
            return None

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
