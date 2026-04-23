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
        Extract data from a single car listing item

        Args:
            item: BeautifulSoup element for the car item
            index: Index number for generating ID

        Returns:
            Dictionary with car data
        """
        try:
            car_data = {
                'id': f"{self.website_id}_{index}_{int(time.time())}",
                'scraped_at': datetime.now().isoformat(),
                'website': self.website_id,
            }

            # Extract link from share button data-link attribute
            share_button = item.find('button', class_='share-button')
            if share_button and share_button.get('data-link'):
                car_data['link'] = share_button['data-link']
            else:
                # Fallback: try to find regular link
                link_elem = item.find('a')
                if link_elem and link_elem.get('href'):
                    link = link_elem['href']
                    if link.startswith('/'):
                        link = urljoin(self.base_url, link)
                    car_data['link'] = link
                else:
                    car_data['link'] = 'N/A'

            # Extract ALL image URLs (not just the first one)
            images = self._extract_all_images(item)
            car_data['images'] = images  # List of all image URLs
            car_data['image_count'] = len(images)
            car_data['image_url'] = images[0] if images else 'N/A'  # Primary image for backward compatibility
            car_data['image_alt'] = 'Car image'

            # Extract card-info section
            card_info = item.find('div', class_='card-info')
            if card_info:
                # Get all text for description
                info_text = card_info.get_text(separator=' | ', strip=True)
                car_data['description'] = info_text

                # Parse pipe-delimited fields
                parsed_fields = self._parse_car_description(info_text)
                car_data.update(parsed_fields)

                # Extract title
                title_elem = card_info.find('h1', class_='car-title')
                if title_elem:
                    car_data['title'] = title_elem.get_text(strip=True)

                # Extract features (mileage, location, fuel type, etc.)
                features_div = card_info.find('div', class_='features')
                if features_div:
                    self._extract_features(features_div, car_data)

            # Extract price from button
            price_button = item.find('button', class_='btn-contact-p')
            if price_button:
                car_data['price'] = price_button.get_text(strip=True)

            # Set defaults for missing fields
            for field in ['title', 'price', 'description', 'link', 'image_url']:
                if field not in car_data or not car_data[field]:
                    car_data[field] = 'N/A'

            # Initialize missing car fields
            for field in ['make', 'model', 'year', 'mileage', 'location', 'fuel_type', 'transmission', 'body_type', 'condition', 'origin']:
                if field not in car_data:
                    car_data[field] = 'N/A'

            logger.debug(f"Extracted car {index}: {car_data.get('title')} - {car_data.get('price')}")
            return car_data

        except Exception as e:
            logger.error(f"Error extracting car data: {e}", exc_info=True)
            return None

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

    def _parse_car_description(self, description_text: str) -> Dict[str, str]:
        """
        Parse pipe-delimited car description text into fields

        Example: "كيا Kia | Sportage | إس يو في | 2017 | 225,000 كم | حلب | بنزين | أمريكية | أوتوماتيك | مستعملة"

        Args:
            description_text: Pipe-delimited description

        Returns:
            Dictionary with parsed fields
        """
        parsed_data = {}

        try:
            # Split by pipe and clean
            segments = [seg.strip() for seg in description_text.split('|')]
            segments = [seg for seg in segments if seg and seg != '•']

            if not segments:
                return {'title': 'N/A'}

            # Initialize all fields
            parsed_data = {
                'title': segments[0],
                'make': 'N/A',
                'model': 'N/A',
                'body_type': 'N/A',
                'year': 'N/A',
                'mileage': 'N/A',
                'location': 'N/A',
                'fuel_type': 'N/A',
                'origin': 'N/A',
                'transmission': 'N/A',
                'condition': 'N/A',
            }

            # Extract make from first segment
            if len(segments) > 0:
                parts = segments[0].split()
                if len(parts) > 0:
                    parsed_data['make'] = parts[-1]

            # Model is typically second segment
            if len(segments) > 1 and segments[1]:
                parsed_data['model'] = segments[1]

            # Body type (check if third segment is a body type)
            if len(segments) > 2 and self._is_body_type(segments[2]):
                parsed_data['body_type'] = segments[2]

            # Year (4-digit number between 1990-2030)
            for seg in segments:
                if self._is_year(seg):
                    parsed_data['year'] = seg
                    break

            # Mileage (number followed by unit)
            for idx, seg in enumerate(segments):
                if self._is_mileage(seg):
                    if idx + 1 < len(segments) and segments[idx + 1] in ['كم', 'km']:
                        parsed_data['mileage'] = f"{seg} {segments[idx + 1]}"
                    else:
                        parsed_data['mileage'] = seg
                    break

            # Fuel type
            fuel_keywords = ['بنزين', 'ديزل', 'Gasoline', 'Diesel', 'LPG', 'غاز']
            for seg in segments:
                if any(fuel in seg for fuel in fuel_keywords):
                    parsed_data['fuel_type'] = seg
                    break

            # Transmission
            trans_keywords = ['أوتوماتيك', 'يدوي', 'Automatic', 'Manual']
            for seg in segments:
                if any(trans in seg for trans in trans_keywords):
                    parsed_data['transmission'] = seg
                    break

            # Condition
            condition_keywords = ['مستعملة', 'جديدة', 'Used', 'New', 'مستخدمة']
            for seg in segments:
                if any(cond in seg for cond in condition_keywords):
                    parsed_data['condition'] = seg
                    break

            # Origin
            origin_keywords = ['أمريكية', 'أوروبية', 'يابانية', 'كورية', 'American', 'European', 'Japanese', 'Korean']
            for seg in segments:
                if any(orig in seg for orig in origin_keywords):
                    parsed_data['origin'] = seg
                    break

            # Location (Arabic city names or near other identifiable fields)
            location_keywords = ['حلب', 'دمشق', 'حمص', 'اللاذقية', 'درعا', 'السويداء', 'طرطوس', 'قامشلي']
            for seg in segments:
                if any(city in seg for city in location_keywords):
                    parsed_data['location'] = seg
                    break

            logger.debug(f"Parsed car description: {parsed_data}")
            return parsed_data

        except Exception as e:
            logger.error(f"Error parsing car description: {e}")
            return {'title': description_text[:100] if description_text else 'N/A'}

    def _extract_features(self, features_div, car_data: Dict):
        """
        Extract features from the features div in card-info

        Structure:
        - features-a: mileage and location
        - features-b: fuel type and origin
        - features-c: transmission and condition

        Args:
            features_div: BeautifulSoup element for features div
            car_data: Dictionary to update with extracted features
        """
        try:
            # Extract features-a (mileage and location)
            features_a = features_div.find('div', class_='features-a')
            if features_a:
                divs = features_a.find_all('div')
                if len(divs) >= 2:
                    mileage_text = divs[0].get_text(strip=True)
                    if mileage_text and mileage_text != 'N/A':
                        car_data['mileage'] = mileage_text

                    location_text = divs[1].get_text(strip=True)
                    if location_text and location_text != 'N/A':
                        car_data['location'] = location_text

            # Extract features-b (fuel type and origin)
            features_b = features_div.find('div', class_='features-b')
            if features_b:
                divs = features_b.find_all('div')
                if len(divs) >= 2:
                    fuel_text = divs[0].get_text(strip=True)
                    if fuel_text and fuel_text != 'N/A':
                        car_data['fuel_type'] = fuel_text

                    origin_text = divs[1].get_text(strip=True)
                    if origin_text and origin_text != 'N/A':
                        car_data['origin'] = origin_text

            # Extract features-c (transmission and condition)
            features_c = features_div.find('div', class_='features-c')
            if features_c:
                divs = features_c.find_all('div')
                if len(divs) >= 2:
                    trans_text = divs[0].get_text(strip=True)
                    if trans_text and trans_text != 'N/A':
                        car_data['transmission'] = trans_text

                    condition_text = divs[1].get_text(strip=True)
                    if condition_text and condition_text != 'N/A':
                        car_data['condition'] = condition_text

            # Extract body type and year from subtitle if available
            parent_card_info = features_div.find_parent('div', class_='card-info')
            if parent_card_info:
                subtitle = parent_card_info.find('h2', class_='car-sub-title')
                if subtitle:
                    subtitle_text = subtitle.get_text(strip=True)
                    # Parse: "Sportage • إس يو في • 2017"
                    parts = [p.strip() for p in subtitle_text.split('•')]
                    if len(parts) >= 3:
                        if car_data.get('model') == 'N/A':
                            car_data['model'] = parts[0]
                        if car_data.get('body_type') == 'N/A':
                            car_data['body_type'] = parts[1]
                        if car_data.get('year') == 'N/A':
                            car_data['year'] = parts[2]

        except Exception as e:
            logger.warning(f"Error extracting features: {e}")

    def _is_year(self, text: str) -> bool:
        """Check if text is a year (1990-2030)"""
        try:
            year = int(text)
            return 1990 <= year <= 2030
        except:
            return False

    def _is_mileage(self, text: str) -> bool:
        """Check if text is a mileage value"""
        try:
            clean_text = text.replace(',', '').replace(' ', '')
            return clean_text.isdigit() and len(clean_text) >= 3
        except:
            return False

    def _is_body_type(self, text: str) -> bool:
        """Check if text is a body type"""
        body_types = ['SUV', 'سيدان', 'sedan', 'Sedan', 'إس يو في', 'عربة', 'truck', 'كوبيه', 'coupe', 'هاتشباك', 'hatchback']
        return any(body in text for body in body_types)
