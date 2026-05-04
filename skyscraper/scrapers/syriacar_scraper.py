"""
SyriaCar.net Scraper - Car listings website scraper
Inherits from CarsScraper base class
"""

import logging
import os
import time
from pathlib import Path
from urllib.parse import urljoin
from datetime import datetime
from typing import List, Dict, Any

import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

from scrapers.base_scraper import CarsScraper
from scrapers import parser as car_parser

logger = logging.getLogger(__name__)


class SyriaCarScraper(CarsScraper):
    """
    SyriaCar.net car listings scraper
    Handles scraping and data extraction from syriacar.net
    """

    def __init__(self, website_config: Dict[str, Any]):
        """
        Initialize the SyriaCar scraper

        Args:
            website_config: Website configuration dictionary
        """
        super().__init__(website_config)

        # SyriaCar-specific configuration
        self.base_url = website_config.get('url', 'https://syriacar.net')
        self.image_folder = Path(website_config.get('image_folder', 'images/syriacar'))
        self.image_folder.mkdir(parents=True, exist_ok=True)

        self.driver = None
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })

        logger.info(f"Initialized SyriaCarScraper for {self.website_name}")

    def scrape(self) -> List[Dict]:
        """
        Main scraping method - scrapes all cars from syriacar.net

        Returns:
            List of car dictionaries with all extracted data
        """
        cars = []

        try:
            self._init_driver()

            logger.info(f"Scraping {self.base_url}")
            self.driver.get(self.base_url)

            # Wait for JavaScript to render content
            logger.info("Waiting for JavaScript to render content...")
            time.sleep(3)

            # Load all cars with infinite scroll
            logger.info("Loading all cars with infinite scroll...")
            cars_before_scroll = 0
            last_height = 0
            scroll_count = 0
            max_scrolls = 50
            no_new_cars_count = 0

            while scroll_count < max_scrolls:
                # Get current page height
                new_height = self.driver.execute_script("return document.body.scrollHeight")

                if new_height == last_height:
                    no_new_cars_count += 1
                    logger.info(f"No new content after scroll {scroll_count} (attempt {no_new_cars_count}/3)")
                    if no_new_cars_count >= 3:
                        logger.info("Reached end of list - no more cars to load")
                        break
                else:
                    no_new_cars_count = 0

                # Scroll down
                self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                last_height = new_height

                # Wait for content to load
                time.sleep(2)
                scroll_count += 1

                logger.info(f"Scroll {scroll_count}: Page height = {new_height}")

            logger.info(f"Scrolling complete after {scroll_count} scrolls")

            # Scroll back to top
            self.driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(1)

            # Parse page with BeautifulSoup
            soup = BeautifulSoup(self.driver.page_source, 'html.parser')

            # Find all car card elements
            car_items = soup.find_all('div', class_='car-card')

            if not car_items:
                logger.warning("No car items found with selector 'div.car-card'")
                logger.warning("Trying alternative selectors...")

                possible_selectors = [
                    ('div.car-item', 'div', 'car-item'),
                    ('div.listing', 'div', 'listing'),
                    ('article.car', 'article', 'car'),
                ]

                for selector in possible_selectors:
                    try:
                        if selector[1]:
                            if selector[2]:
                                car_items = soup.find_all(selector[1], class_=selector[2])
                            else:
                                car_items = soup.find_all(selector[1])

                        if car_items and len(car_items) > 0:
                            logger.info(f"Found {len(car_items)} items using selector: {selector[0]}")
                            break
                    except:
                        continue

            if not car_items:
                logger.warning("No car items found with any selector!")
                return []

            logger.info(f"Found {len(car_items)} car listings")

            # Extract data from each car item
            for idx, item in enumerate(car_items, 1):
                try:
                    car_data = self._extract_car_data(item, idx)
                    if car_data:
                        cars.append(car_data)

                        # Download image if available
                        image_url = item.find('img', class_='car-image')
                        if image_url:
                            img_src = image_url.get('src') or image_url.get('data-src')
                            if img_src:
                                image_path = self.download_image(img_src, car_data.get('id'))
                                if image_path:
                                    car_data['image_path'] = image_path

                except Exception as e:
                    logger.warning(f"Error extracting data from car item {idx}: {e}")
                    continue

            logger.info(f"Successfully scraped {len(cars)} cars from syriacar.net")

            # Log scraping result
            self.log_scrape_result({
                'total_items': len(cars),
                'new_items': len(cars),
                'duplicates': 0,
                'duration': f"{scroll_count * 2} seconds"
            })

            return cars

        except Exception as e:
            logger.error(f"Error during scraping: {e}", exc_info=True)
            return []

        finally:
            self._close_driver()

    def _init_driver(self):
        """Initialize Selenium WebDriver"""
        try:
            options = webdriver.ChromeOptions()
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--disable-gpu")

            # Try to use local ChromeDriver first
            chromedriver_path = os.path.expanduser(
                "~/.wdm/drivers/chromedriver/win64/147.0.7727.57/chromedriver-win32/chromedriver.exe"
            )

            if os.path.exists(chromedriver_path):
                logger.info(f"Using ChromeDriver from: {chromedriver_path}")
                self.driver = webdriver.Chrome(
                    service=Service(chromedriver_path),
                    options=options
                )
            else:
                logger.info("Using ChromeDriver from webdriver-manager")
                self.driver = webdriver.Chrome(
                    service=Service(ChromeDriverManager().install()),
                    options=options
                )

            logger.info("WebDriver initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize WebDriver: {e}")
            raise

    def _close_driver(self):
        """Close Selenium WebDriver"""
        if self.driver:
            self.driver.quit()
            logger.info("WebDriver closed")

    def download_image(self, image_url: str, car_id: str) -> str:
        """
        Download image and save it locally

        Args:
            image_url: URL of the image
            car_id: ID of the car for naming

        Returns:
            Local path to saved image or None if failed
        """
        try:
            if not image_url:
                return None

            # Make absolute URL if relative
            if image_url.startswith('/'):
                image_url = urljoin(self.base_url, image_url)
            elif not image_url.startswith('http'):
                image_url = urljoin(self.base_url, image_url)

            response = self.session.get(image_url, timeout=10)
            response.raise_for_status()

            # Determine file extension
            ext = '.jpg'
            content_type = response.headers.get('content-type', '')
            if 'png' in content_type:
                ext = '.png'
            elif 'webp' in content_type:
                ext = '.webp'

            # Save image
            filename = f"car_{car_id}{ext}"
            filepath = self.image_folder / filename

            with open(filepath, 'wb') as f:
                f.write(response.content)

            logger.info(f"Downloaded image for car {car_id}: {filename}")
            return str(filepath)

        except Exception as e:
            logger.warning(f"Failed to download image from {image_url}: {e}")
            return None

    def _extract_car_data(self, item, index: int) -> Dict[str, Any]:
        """
        Stage 1 (raw) + Stage 2 (parse) for a single car card.
        Raw extraction is dumb — just collect text as-is.
        Interpretation is delegated to car_parser.parse().
        """
        try:
            raw = self._extract_raw(item, index)
            if not raw:
                return None
            return car_parser.parse(raw)
        except Exception as e:
            logger.error(f"Error extracting car data: {e}", exc_info=True)
            return None

    def _extract_raw(self, item, index: int) -> Dict[str, Any]:
        """
        STAGE 1 — Raw extraction only. No interpretation.
        Collects exactly what is on the card — labels and values as-is.
        """
        raw = {
            'source':      self.website_id,
            'id':          f"{self.website_id}_{index}_{int(time.time())}",
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
            'seller_raw':      None,
        }

        # Link
        share_button = item.find('button', class_='share-button')
        if share_button and share_button.get('data-link'):
            raw['ad_url'] = share_button['data-link']
        else:
            link_elem = item.find('a')
            if link_elem and link_elem.get('href'):
                href = link_elem['href']
                raw['ad_url'] = urljoin(self.base_url, href) if href.startswith('/') else href

        # Images
        raw['images'] = self._extract_all_images(item)

        # card-info section
        card_info = item.find('div', class_='card-info')
        if card_info:
            # Full card text → description_raw
            raw['description_raw'] = card_info.get_text(separator=' ', strip=True)

            # Title: h1.car-title = brand name (e.g. "كيا Kia")
            title_elem = card_info.find('h1', class_='car-title')
            if title_elem:
                raw['title_raw'] = title_elem.get_text(strip=True)

            # Subtitle: "Sportage • إس يو في • 2017" → model, body_type, year
            subtitle_elem = card_info.find('h2', class_='car-sub-title')
            if subtitle_elem:
                parts = [p.strip() for p in subtitle_elem.get_text().split('•')]
                parts = [p for p in parts if p]
                specs = raw['specs_raw']
                if len(parts) >= 1:
                    specs['الموديل'] = parts[0]   # model name
                if len(parts) >= 2:
                    specs['نوع الهيكل'] = parts[1]  # body type
                if len(parts) >= 3:
                    specs['السنة'] = parts[2]       # year

            # Features divs: mileage, location, fuel, origin, transmission, condition
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
                        specs['المصدر'] = divs[1].get_text(strip=True)

                fc = features_div.find('div', class_='features-c')
                if fc:
                    divs = fc.find_all('div')
                    if len(divs) >= 1:
                        specs['ناقل الحركة'] = divs[0].get_text(strip=True)
                    if len(divs) >= 2:
                        specs['الحالة'] = divs[1].get_text(strip=True)

        # Price button
        price_btn = item.find('button', class_='btn-contact-p')
        if price_btn:
            raw['price_raw'] = price_btn.get_text(strip=True)

        return raw

    def _extract_all_images(self, item) -> List[str]:
        """
        Extract ALL image URLs from a car listing item
        Handles cases with 0, 1, or multiple images

        Args:
            item: BeautifulSoup element for the car item

        Returns:
            List of image URLs
        """
        images = []
        try:
            # Find all img tags in the item
            img_tags = item.find_all('img')

            for img in img_tags:
                # Get src or data-src (for lazy-loaded images)
                src = img.get('src') or img.get('data-src')

                if src:
                    # Convert relative URLs to absolute
                    if src.startswith('/'):
                        src = urljoin(self.base_url, src)
                    elif not src.startswith('http'):
                        src = urljoin(self.base_url, src)

                    images.append(src)

            logger.debug(f"Extracted {len(images)} images from car listing")
            return images

        except Exception as e:
            logger.warning(f"Error extracting images: {e}")
            return []

    def get_statistics(self, items: List[Dict]) -> Dict[str, Any]:
        """Calculate statistics from scraped items."""
        if not items:
            return {'total_items': 0, 'price_stats': {}, 'year_stats': {}, 'brand_stats': {}}

        prices = [i.get('price') for i in items if isinstance(i.get('price'), (int, float))]
        years  = [i.get('year')  for i in items if isinstance(i.get('year'), int)]
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
