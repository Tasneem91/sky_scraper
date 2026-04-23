"""
Main web scraper module for collecting car data
"""
import logging
import os
import time
import sys
from pathlib import Path
from urllib.parse import urljoin
from datetime import datetime

import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

from config import SCRAPER_CONFIG, WEBSITE_CONFIG

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class CarScraper:
    """Web scraper for car listing websites"""

    def __init__(self, website_key="syriacar"):
        """
        Initialize the scraper

        Args:
            website_key: Key to identify which website to scrape
        """
        self.website_key = website_key
        self.website_config = WEBSITE_CONFIG.get(website_key)

        if not self.website_config:
            raise ValueError(f"Website config not found for {website_key}")

        self.base_url = self.website_config["url"]
        self.image_folder = Path(self.website_config["image_folder"])
        self.image_folder.mkdir(parents=True, exist_ok=True)

        self.driver = None
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": SCRAPER_CONFIG["user_agent"]
        })

    def _init_driver(self):
        """Initialize Selenium WebDriver"""
        try:
            options = webdriver.ChromeOptions()
            if SCRAPER_CONFIG["headless"]:
                options.add_argument("--headless")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--disable-gpu")

            # Try using direct path first, fall back to webdriver-manager
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
            logger.error(f"Trying alternative approach...")
            try:
                # Final fallback: try without Service
                options = webdriver.ChromeOptions()
                options.add_argument("--no-sandbox")
                options.add_argument("--disable-dev-shm-usage")
                options.add_argument("--disable-gpu")
                self.driver = webdriver.Chrome(options=options)
                logger.info("WebDriver initialized with fallback method")
            except Exception as e2:
                logger.error(f"Fallback also failed: {e2}")
                raise

    def _close_driver(self):
        """Close Selenium WebDriver"""
        if self.driver:
            self.driver.quit()
            logger.info("WebDriver closed")

    def download_image(self, image_url, car_id):
        """
        Download image and save it locally

        Args:
            image_url: URL of the image
            car_id: ID of the car for naming the image

        Returns:
            Local path to the saved image or None if failed
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
            if 'png' in response.headers.get('content-type', ''):
                ext = '.png'
            elif 'webp' in response.headers.get('content-type', ''):
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

    def scrape_syriacar(self):
        """
        Scrape data from syriacar.net

        Returns:
            List of car dictionaries with all details
        """
        cars = []

        try:
            self._init_driver()

            logger.info(f"Scraping {self.base_url}")
            self.driver.get(self.base_url)

            # Wait for page to load - JavaScript may take time to render
            logger.info("Waiting for JavaScript to render content...")
            time.sleep(3)  # Initial wait

            # Scroll down to load ALL cars (infinite scroll)
            logger.info("Loading all cars with infinite scroll...")

            last_height = 0
            scroll_count = 0
            max_scrolls = 50  # Prevent infinite loops
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

            # Get page source and parse with BeautifulSoup
            soup = BeautifulSoup(self.driver.page_source, 'html.parser')

            # Debug: Save page source to file for inspection
            debug_file = "page_source.html"
            with open(debug_file, 'w', encoding='utf-8') as f:
                f.write(self.driver.page_source)
            logger.info(f"Page source saved to {debug_file} for debugging")

            # Try different possible selectors
            possible_selectors = [
                ('div.car-card', 'div', 'car-card'),
                ('div.car-item', 'div', 'car-item'),
                ('div.listing', 'div', 'listing'),
                ('div.car', 'div', 'car'),
                ('article.car', 'article', 'car'),
                ('article', 'article', None),
                ('[class*="card"]', None, None),  # Any element with "card" in class
            ]

            car_items = []
            selected_selector = None

            for selector in possible_selectors:
                try:
                    if selector[1]:  # Has tag name
                        if selector[2]:  # Has class name
                            car_items = soup.find_all(selector[1], class_=selector[2])
                        else:
                            car_items = soup.find_all(selector[1])
                    else:
                        car_items = soup.find_all()  # Find all and filter
                        car_items = [el for el in car_items if 'card' in el.get('class', [])]

                    if car_items and len(car_items) > 0:
                        selected_selector = selector[0]
                        logger.info(f"✓ Found {len(car_items)} items using selector: {selector[0]}")
                        break
                except:
                    continue

            if not car_items:
                logger.warning("❌ No car items found with any selector!")
                logger.warning("Page title: " + (soup.title.string if soup.title else "No title"))

                # Try to find ANY divs on page for debugging
                all_divs = soup.find_all('div')[:5]
                logger.warning(f"Found {len(soup.find_all('div'))} total divs. First 5:")
                for i, div in enumerate(all_divs):
                    logger.warning(f"  Div {i}: class={div.get('class')} id={div.get('id')}")

                return []

            logger.info(f"Found {len(car_items)} car listings")

            for idx, item in enumerate(car_items, 1):
                try:
                    # Set fetch_details=True to get full specs from detail page
                    # Warning: This will be SLOW (5-10 seconds per car)
                    fetch_details = False  # Change to True if you want detailed specs

                    car_data = self._extract_car_data(item, idx, fetch_details=fetch_details)
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

            logger.info(f"Successfully scraped {len(cars)} cars")
            return cars

        except Exception as e:
            logger.error(f"Error during scraping: {e}")
            return []

        finally:
            self._close_driver()

    def _extract_car_data(self, item, index, fetch_details=False):
        """
        Extract data from a single car listing item

        Args:
            item: BeautifulSoup element for the car item
            index: Index number for generating ID
            fetch_details: If True, fetch detailed specs from car's detail page

        Returns:
            Dictionary with car data
        """
        try:
            car_data = {
                'id': f"{self.website_key}_{index}_{int(time.time())}",
                'scraped_at': datetime.now().isoformat(),
                'website': self.website_key,
            }

            # Try to find link
            link_elem = item.find('a')
            if link_elem and link_elem.get('href'):
                link = link_elem['href']
                if link.startswith('/'):
                    link = urljoin(self.base_url, link)
                car_data['link'] = link
            else:
                car_data['link'] = 'N/A'

            # Extract image
            img_elem = item.find('img')
            if img_elem:
                car_data['image_url'] = img_elem.get('src')
                car_data['image_alt'] = img_elem.get('alt', 'Car image')

            # Extract card info - look for card-info div
            card_info = item.find('div', class_='card-info')
            if card_info:
                # Get all text from card-info
                info_text = card_info.get_text(separator=' | ', strip=True)
                car_data['description'] = info_text

                # Parse pipe-delimited fields from description
                parsed_fields = self._parse_car_description(info_text)
                car_data.update(parsed_fields)

                # Extract title from h1 if available
                title_elem = card_info.find('h1', class_='car-title')
                if title_elem:
                    car_data['title'] = title_elem.get_text(strip=True)

                # Extract features (mileage, location, fuel type, transmission, condition, origin)
                features_div = card_info.find('div', class_='features')
                if features_div:
                    self._extract_features(features_div, car_data)

            # Extract price from button (outside card-info)
            price_button = item.find('button', class_='btn-contact-p')
            if price_button:
                car_data['price'] = price_button.get_text(strip=True)

            # Extract detail page link from share button
            share_button = item.find('button', class_='share-button')
            if share_button and share_button.get('data-link'):
                car_data['link'] = share_button['data-link']

            # Fallback: get all text from item if no card-info
            if not card_info:
                all_text = item.get_text(separator=' | ', strip=True)
                car_data['title'] = all_text[:100] if all_text else "N/A"
                car_data['description'] = all_text
                car_data['price'] = 'N/A'

            # Set defaults for missing fields
            for field in ['title', 'price', 'description', 'link']:
                if field not in car_data:
                    car_data[field] = 'N/A'

            logger.debug(f"Extracted car {index}: {car_data.get('title', 'Unknown')} - Price: {car_data.get('price', 'N/A')}")
            return car_data

        except Exception as e:
            logger.error(f"Error extracting car data: {e}", exc_info=True)
            return None

    def _parse_car_description(self, description_text):
        """
        Parse pipe-delimited car description text into individual fields

        Example input:
        كيا Kia | Sportage | • | إس يو في | • | 2017 | 225,000 | كم | حلب | بنزين | أمريكية | أوتوماتيك | مستعملة

        Args:
            description_text: Pipe-delimited description string

        Returns:
            Dictionary with extracted fields
        """
        parsed_data = {}

        try:
            # Split by pipe separator and clean each segment
            segments = [seg.strip() for seg in description_text.split('|')]

            # Remove empty segments and bullet points
            segments = [seg for seg in segments if seg and seg != '•']

            if not segments:
                return {'title': 'N/A', 'price': 'N/A'}

            # First segment is typically the brand/model combo (title)
            parsed_data['title'] = segments[0]

            # Initialize with defaults
            parsed_data['price'] = 'N/A'
            parsed_data['make'] = 'N/A'
            parsed_data['model'] = 'N/A'
            parsed_data['body_type'] = 'N/A'
            parsed_data['year'] = 'N/A'
            parsed_data['mileage'] = 'N/A'
            parsed_data['location'] = 'N/A'
            parsed_data['fuel_type'] = 'N/A'
            parsed_data['origin'] = 'N/A'
            parsed_data['transmission'] = 'N/A'
            parsed_data['condition'] = 'N/A'

            # Extract make from first segment if it contains both Arabic and English
            if len(segments) > 0:
                first_seg = segments[0]
                # Split by space to get potential make
                parts = first_seg.split()
                if len(parts) > 0:
                    parsed_data['make'] = parts[-1]  # Usually English part is last

            # Model is typically the second segment
            if len(segments) > 1 and segments[1]:
                parsed_data['model'] = segments[1]

            # Body type is often after model (3rd or 4th segment)
            if len(segments) > 2 and segments[2]:
                # Check if this looks like a body type (contains certain keywords)
                potential_body = segments[2]
                if self._is_body_type(potential_body):
                    parsed_data['body_type'] = potential_body
                    body_idx = 2
                else:
                    body_idx = None
            else:
                body_idx = None

            # Year is typically 4 digits (2010-2030 range)
            year_idx = None
            for idx, seg in enumerate(segments):
                if self._is_year(seg):
                    parsed_data['year'] = seg
                    year_idx = idx
                    break

            # Mileage: number followed by unit (كم)
            for idx, seg in enumerate(segments):
                if self._is_mileage(seg):
                    # Mileage value is current segment, unit might be next
                    if idx + 1 < len(segments) and segments[idx + 1] in ['كم', 'km']:
                        parsed_data['mileage'] = f"{seg} {segments[idx + 1]}"
                    else:
                        parsed_data['mileage'] = seg
                    break

            # Fuel type (بنزين, ديزل, Gasoline, Diesel)
            fuel_keywords = ['بنزين', 'ديزل', 'Gasoline', 'Diesel', 'LPG', 'غاز']
            for seg in segments:
                if any(fuel in seg for fuel in fuel_keywords):
                    parsed_data['fuel_type'] = seg
                    break

            # Transmission (أوتوماتيك, يدوي, Automatic, Manual)
            trans_keywords = ['أوتوماتيك', 'يدوي', 'Automatic', 'Manual']
            for seg in segments:
                if any(trans in seg for trans in trans_keywords):
                    parsed_data['transmission'] = seg
                    break

            # Condition (مستعملة, جديدة, Used, New)
            condition_keywords = ['مستعملة', 'جديدة', 'Used', 'New', 'مستخدمة']
            for seg in segments:
                if any(cond in seg for cond in condition_keywords):
                    parsed_data['condition'] = seg
                    break

            # Origin (أمريكية, أوروبية, يابانية, American, European, Japanese)
            origin_keywords = ['أمريكية', 'أوروبية', 'يابانية', 'كورية', 'American', 'European', 'Japanese', 'Korean']
            for seg in segments:
                if any(orig in seg for orig in origin_keywords):
                    parsed_data['origin'] = seg
                    break

            # Location: typically near the end, Arabic city names
            # Try to find it as the segment before fuel type
            for idx, seg in enumerate(segments):
                # If this segment is not a known type, it might be location
                if (idx < len(segments) - 3 and  # Not too close to end
                    not self._is_year(seg) and
                    not self._is_mileage(seg) and
                    not self._is_body_type(seg) and
                    not any(fuel in seg for fuel in ['بنزين', 'ديزل', 'Gasoline', 'Diesel']) and
                    len(seg) < 20 and  # Location names are typically short
                    idx > 2):  # After make/model
                    # Check if segment before is mileage or year
                    if idx > 0 and (self._is_mileage(segments[idx-1]) or self._is_year(segments[idx-1])):
                        parsed_data['location'] = seg
                        break

            # If no location found, try Arabic city patterns
            if parsed_data['location'] == 'N/A':
                for seg in segments:
                    # Check for common Syrian/Arabic cities
                    if any(city in seg for city in ['حلب', 'دمشق', 'حمص', 'اللاذقية', 'درعا', 'السويداء']):
                        parsed_data['location'] = seg
                        break

            # Look for price (if any segment contains currency indicators)
            for seg in segments:
                if any(indicator in seg for indicator in ['$', 'دولار', 'ل.س', 'ليرة', 'السعر']):
                    parsed_data['price'] = seg
                    break

            logger.debug(f"Parsed car description: {parsed_data}")
            return parsed_data

        except Exception as e:
            logger.error(f"Error parsing car description: {e}")
            return {
                'title': description_text[:100] if description_text else 'N/A',
                'price': 'N/A'
            }

    def _is_year(self, text):
        """Check if text is a year (1990-2030)"""
        try:
            year = int(text)
            return 1990 <= year <= 2030
        except:
            return False

    def _is_mileage(self, text):
        """Check if text is a mileage value (number with optional comma)"""
        try:
            # Remove commas and spaces
            clean_text = text.replace(',', '').replace(' ', '')
            int(clean_text)
            return clean_text.isdigit() and len(clean_text) >= 3
        except:
            return False

    def _is_body_type(self, text):
        """Check if text is a body type"""
        body_types = ['SUV', 'سيدان', 'sedan', 'Sedan', 'إس يو في', 'عربة', 'truck', 'truck', 'كوبيه', 'coupe', 'هاتشباك', 'hatchback']
        return any(body in text for body in body_types)

    def _extract_features(self, features_div, car_data):
        """
        Extract features from the features div in card-info

        Structure:
        <div class="features">
          <div class="features-a">
            <div>225,000 <span class="km">كم</span></div>  # Mileage
            <div>حلب</div>  # Location
          </div>
          <div class="features-b">
            <div>بنزين</div>  # Fuel type
            <div>أمريكية</div>  # Origin
          </div>
          <div class="features-c">
            <div>أوتوماتيك</div>  # Transmission
            <div>مستعملة</div>  # Condition
          </div>
        </div>

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
                    # Mileage
                    mileage_div = divs[0]
                    mileage_text = mileage_div.get_text(strip=True)
                    if mileage_text:
                        car_data['mileage'] = mileage_text

                    # Location
                    location_div = divs[1]
                    location_text = location_div.get_text(strip=True)
                    if location_text:
                        car_data['location'] = location_text

            # Extract features-b (fuel type and origin)
            features_b = features_div.find('div', class_='features-b')
            if features_b:
                divs = features_b.find_all('div')
                if len(divs) >= 2:
                    # Fuel type
                    fuel_div = divs[0]
                    fuel_text = fuel_div.get_text(strip=True)
                    if fuel_text:
                        car_data['fuel_type'] = fuel_text

                    # Origin
                    origin_div = divs[1]
                    origin_text = origin_div.get_text(strip=True)
                    if origin_text:
                        car_data['origin'] = origin_text

            # Extract features-c (transmission and condition)
            features_c = features_div.find('div', class_='features-c')
            if features_c:
                divs = features_c.find_all('div')
                if len(divs) >= 2:
                    # Transmission
                    trans_div = divs[0]
                    trans_text = trans_div.get_text(strip=True)
                    if trans_text:
                        car_data['transmission'] = trans_text

                    # Condition
                    condition_div = divs[1]
                    condition_text = condition_div.get_text(strip=True)
                    if condition_text:
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
                        if not car_data.get('model') or car_data['model'] == 'N/A':
                            car_data['model'] = parts[0]
                        if not car_data.get('body_type') or car_data['body_type'] == 'N/A':
                            car_data['body_type'] = parts[1]
                        if not car_data.get('year') or car_data['year'] == 'N/A':
                            car_data['year'] = parts[2]

        except Exception as e:
            logger.warning(f"Error extracting features: {e}")
            # Continue with what we have, don't fail the whole extraction

    def _extract_detail_page_specs(self, detail_url):
        """
        Extract detailed specifications from a car's detail page

        Args:
            detail_url: URL of the car detail page

        Returns:
            Dictionary with detailed specs
        """
        try:
            logger.info(f"Fetching detail page: {detail_url}")
            self.driver.get(detail_url)
            time.sleep(2)  # Wait for page to load

            specs = {}

            # Parse the page
            soup = BeautifulSoup(self.driver.page_source, 'html.parser')

            # Find all spec list items: li.li-1-details-color
            spec_items = soup.find_all('li', class_='li-1-details-color')

            logger.info(f"Found {len(spec_items)} specs on detail page")

            for item in spec_items:
                text = item.get_text(strip=True)
                # Each li contains: [icon] spec_name spec_value
                # We'll store the full text as is
                if text:
                    specs[f"spec_{len(specs)}"] = text

            # Try to extract specific fields we care about
            all_text = soup.get_text(separator=' | ', strip=True)

            # Look for specific patterns
            spec_dict = {
                'make': self._extract_field(all_text, ['كيا', 'Kia']),
                'model': self._extract_field(all_text, ['Sportage', 'Camry']),
                'year': self._extract_year(all_text),
                'engine_capacity': self._extract_field(all_text, ['CC', 'cc']),
                'engine_power': self._extract_field(all_text, ['HP', 'حصان']),
                'transmission': self._extract_field(all_text, ['أوتوماتيك', 'يدوي', 'Automatic', 'Manual']),
                'fuel_type': self._extract_field(all_text, ['بنزين', 'ديزل', 'Gasoline', 'Diesel']),
                'body_type': self._extract_field(all_text, ['SUV', 'سيدان']),
                'doors': self._extract_field(all_text, ['أبواب', 'doors']),
                'seats': self._extract_field(all_text, ['مقاعد', 'seats']),
                'condition': self._extract_field(all_text, ['مستعملة', 'جديدة', 'Used', 'New']),
                'exterior_color': self._extract_field(all_text, ['اللون الخارجي']),
                'interior_color': self._extract_field(all_text, ['اللون الداخلي']),
            }

            # Add all raw specs
            spec_dict.update(specs)

            return spec_dict

        except Exception as e:
            logger.error(f"Error extracting detail page specs: {e}")
            return {}

    def _extract_field(self, text, keywords):
        """Helper to extract field containing keywords"""
        for keyword in keywords:
            if keyword in text:
                return keyword
        return "N/A"

    def _extract_year(self, text):
        """Helper to extract year (4 digit number between 1990 and 2030)"""
        import re
        years = re.findall(r'\b(19\d{2}|20\d{2})\b', text)
        if years:
            return years[0]
        return "N/A"

    def scrape(self):
        """
        Scrape data based on website configuration

        Returns:
            List of car dictionaries
        """
        if self.website_key == "syriacar":
            return self.scrape_syriacar()
        else:
            raise NotImplementedError(f"Scraper not implemented for {self.website_key}")


if __name__ == "__main__":
    # Test the scraper
    scraper = CarScraper("syriacar")
    cars = scraper.scrape()

    # Print sample data
    if cars:
        print(f"\n=== Scraped {len(cars)} cars ===")
        for car in cars[:3]:  # Show first 3 cars
            print(f"\nCar ID: {car.get('id')}")
            print(f"Title: {car.get('title')}")
            print(f"Price: {car.get('price')}")
            print(f"Image: {car.get('image_path', 'No image')}")
    else:
        print("No cars scraped")
