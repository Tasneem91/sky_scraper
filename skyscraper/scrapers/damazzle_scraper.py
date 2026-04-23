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
        Extract a single car listing from HTML
        Returns all 25 columns from unified schema

        Args:
            listing_div: BeautifulSoup div containing the listing
            primary_image: The primary image URL for this listing

        Returns:
            Dictionary with extracted car data (unified schema)
        """
        try:
            # Initialize with all 25 unified schema fields
            item = {
                'scraped_at': datetime.now().isoformat(),
                'source': 'damazzle',
                'id': None,
                'title': None,
                'price': None,
                'price_raw': None,
                'brand': None,
                'model': None,  # Not available for Damazzle
                'category': None,
                'year': None,
                'mileage': None,
                'location': None,
                'posted_date': None,
                'condition': None,  # Not available for Damazzle
                'fuel_type': None,  # Not available for Damazzle
                'transmission': None,  # Not available for Damazzle
                'body_type': None,  # Not available for Damazzle
                'origin': None,  # Not available for Damazzle
                'image_count': 0,
                'images': '[]',
                'primary_image': primary_image,
                'link': None,
                'ad_id': None,
                'ad_url': None,
                'description': None,  # Not available for Damazzle
                'listing_type': self.listing_type,  # "sell" or "rent"
            }

            # Extract price
            price_elem = listing_div.find('div', class_='text-orange')
            if price_elem:
                price_text = price_elem.get_text(strip=True)
                item['price'] = self._clean_price(price_text)
                item['price_raw'] = price_text

            # Extract brand (first bg-purple span)
            brand_spans = listing_div.find_all('span', class_='bg-purple')
            if brand_spans:
                item['brand'] = brand_spans[0].get_text(strip=True)
                # Extract category if available
                if len(brand_spans) > 1:
                    item['category'] = brand_spans[1].get_text(strip=True)

            # Extract year and mileage from list items
            list_items = listing_div.find_all('li')
            for li in list_items:
                text = li.get_text(strip=True)
                # Check if it's a year (4 digits)
                if re.search(r'\d{4}', text):
                    year_match = re.search(r'(\d{4})', text)
                    if year_match:
                        item['year'] = int(year_match.group(1))
                # Check if it contains 'كم' (km in Arabic)
                elif 'كم' in text or 'km' in text.lower():
                    item['mileage'] = text

            # Extract title
            title_elem = listing_div.find('h5', class_='product-title')
            if title_elem:
                item['title'] = title_elem.get_text(strip=True)

            # Extract location and posted date
            location_div = listing_div.find('div', class_='text-muted')
            if location_div:
                location_text = location_div.get_text(strip=True)
                # Split by |
                parts = location_text.split('|')
                item['location'] = parts[0].strip() if parts else None
                item['posted_date'] = parts[1].strip() if len(parts) > 1 else None

            # Handle images
            if primary_image:
                item['images'] = f'["{primary_image}"]'  # JSON string with one image
                item['image_count'] = 1
            else:
                item['images'] = '[]'
                item['image_count'] = 0

            # Extract ad ID from WhatsApp link
            whatsapp_link = listing_div.find('a', class_='btn-whatsapp')
            if whatsapp_link and whatsapp_link.get('href'):
                href = whatsapp_link.get('href')
                # Extract ID from /ads/xxxx format
                match = re.search(r'/ads/([^&?]+)', href)
                if match:
                    ad_id = match.group(1)
                    item['ad_id'] = ad_id
                    item['ad_url'] = f"https://damazzle.com/ads/{ad_id}"
                    # Create unique ID combining source and ad_id
                    item['id'] = f"damazzle_{ad_id}_{int(datetime.now().timestamp())}"
                    # Create link
                    item['link'] = f"https://damazzle.com/ads/{ad_id}"

            return item

        except Exception as e:
            logger.error(f"Error extracting listing: {e}")
            return None

    def _clean_price(self, price_text: str) -> float:
        """
        Clean and convert price string to float

        Args:
            price_text: Raw price text (e.g., "17,000 $")

        Returns:
            Float price value
        """
        try:
            # Remove spaces, currency symbols, and Arabic text
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
