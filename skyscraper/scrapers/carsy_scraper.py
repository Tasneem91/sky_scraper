"""
Carsy.app Scraper
Scrapes car listings from https://carsy.app/cars
Two-stage scraping:
  Stage 1: Collect all car links from listing pages (~50 pages, 20 cars each)
  Stage 2: Visit each car detail page for full specs, images, description, contacts

Uses Playwright for JavaScript rendering (React/Next.js app)
"""

import logging
import re
import time
from datetime import datetime
from typing import List, Dict, Any, Optional

from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

BASE_URL = "https://carsy.app"


class CarsyScraper:
    """Scraper for Carsy.app - two-stage scraping (listing + detail pages)"""

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize scraper with configuration

        Args:
            config: Website configuration dictionary
        """
        self.config = config
        self.base_url = config.get('url', 'https://carsy.app/cars')
        self.items = []
        self.playwright = None
        self.browser = None
        self.page = None

    def _init_browser(self):
        """Initialize Playwright browser with anti-bot headers"""
        try:
            self.playwright = sync_playwright().start()
            self.browser = self.playwright.chromium.launch(headless=True)
            self.page = self.browser.new_page(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            )
            # Set extra headers to appear more like a real browser
            self.page.set_extra_http_headers({
                'Accept-Language': 'ar,en-US;q=0.9,en;q=0.8',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            })
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

    def _goto(self, url: str):
        """
        Navigate to URL with fallback wait strategies and 60s timeout
        """
        try:
            self.page.goto(url, wait_until='load', timeout=60000)
        except Exception:
            try:
                self.page.goto(url, wait_until='networkidle', timeout=60000)
            except Exception as e:
                raise Exception(f"Failed to load {url}: {e}")

    # =========================================================================
    # STAGE 1: Collect car links from listing pages
    # =========================================================================

    def _collect_car_links(self) -> List[Dict[str, Any]]:
        """
        Stage 1: Scrape all listing pages and collect car links + basic info.

        Returns:
            List of dicts: {url, title, price, location, mileage, posted_time}
        """
        car_cards = []
        page_num = 1
        consecutive_empty = 0
        seen_urls = set()

        while True:
            try:
                url = f"{self.base_url}?page={page_num}" if page_num > 1 else self.base_url
                logger.info(f"[Stage 1] Listing page {page_num}: {url}")

                self._goto(url)

                # Wait for car cards
                try:
                    self.page.wait_for_selector("a[href^='/cars/']", timeout=15000)
                except Exception:
                    logger.info(f"No car links found on listing page {page_num}")
                    consecutive_empty += 1
                    if consecutive_empty >= 3:
                        logger.info("3 consecutive empty pages — stopping Stage 1")
                        break
                    page_num += 1
                    continue

                soup = BeautifulSoup(self.page.content(), 'html.parser')

                # Find all car anchor tags
                anchors = soup.find_all('a', href=re.compile(r'^/cars/\d+$'))

                if not anchors:
                    consecutive_empty += 1
                    if consecutive_empty >= 3:
                        break
                    page_num += 1
                    continue

                consecutive_empty = 0
                new_this_page = 0

                for anchor in anchors:
                    href = anchor.get('href', '')
                    full_url = f"{BASE_URL}{href}"

                    if full_url in seen_urls:
                        continue
                    seen_urls.add(full_url)

                    # Extract quick info from listing card
                    card_info = self._extract_card_info(anchor)
                    card_info['url'] = full_url
                    car_cards.append(card_info)
                    new_this_page += 1

                logger.info(f"[Stage 1] Page {page_num}: {new_this_page} new cars (total: {len(car_cards)})")

                # Stop if no new cars were added (last page)
                if new_this_page == 0:
                    logger.info("No new cars on this page — all cars collected")
                    break

                page_num += 1

            except Exception as e:
                logger.error(f"[Stage 1] Error on listing page {page_num}: {e}")
                consecutive_empty += 1
                if consecutive_empty >= 3:
                    break
                page_num += 1

        logger.info(f"[Stage 1] Complete. Collected {len(car_cards)} car links")
        return car_cards

    def _extract_card_info(self, anchor_tag) -> Dict[str, Any]:
        """
        Extract quick info from a listing card anchor tag.
        Captures: title, price, location, mileage, posted_time
        """
        info = {
            'title': None,
            'price': None,
            'price_raw': None,
            'location': None,
            'mileage': None,
            'posted_time': None,
        }

        try:
            # Posted time: span inside flex container with lucide-clock svg
            clock_svg = anchor_tag.find('svg', class_=re.compile(r'lucide-clock'))
            if clock_svg:
                time_span = clock_svg.find_next_sibling('span')
                if time_span:
                    info['posted_time'] = time_span.get_text(strip=True)

            # Title: h3.font-semibold
            title_elem = anchor_tag.find('h3', class_=re.compile(r'font-semibold'))
            if title_elem:
                info['title'] = title_elem.get_text(strip=True)

            # Price: span.text-primary with text-2xl
            price_elem = anchor_tag.find('span', class_=re.compile(r'text-primary'))
            if price_elem:
                price_text = price_elem.get_text(strip=True)
                info['price_raw'] = price_text
                info['price'] = self._clean_price(price_text)

            # Location: span.capitalize inside map-pin container
            map_svg = anchor_tag.find('svg', class_=re.compile(r'lucide-map-pin'))
            if map_svg:
                loc_span = map_svg.find_next_sibling('span')
                if loc_span:
                    info['location'] = loc_span.get_text(strip=True)

            # Mileage: span after lucide-gauge svg
            gauge_svg = anchor_tag.find('svg', class_=re.compile(r'lucide-gauge'))
            if gauge_svg:
                mil_span = gauge_svg.find_next_sibling('span')
                if mil_span:
                    info['mileage'] = mil_span.get_text(strip=True)

        except Exception as e:
            logger.warning(f"Error extracting card info: {e}")

        return info

    # =========================================================================
    # STAGE 2: Visit each car detail page for full specs
    # =========================================================================

    def _scrape_detail_page(self, car_url: str) -> Dict[str, Any]:
        """
        Stage 2: Visit a car detail page and extract all available information.

        Returns:
            Dict with all extracted fields (unified schema)
        """
        detail = {
            'brand': None,
            'model': None,
            'year': None,
            'mileage_detail': None,
            'transmission': None,
            'fuel_type': None,
            'body_type': None,
            'color': None,
            'engine': None,
            'condition': None,
            'origin': None,
            'description': None,
            'images': '[]',
            'primary_image': None,
            'image_count': 0,
            'phone': None,
            'whatsapp': None,
            'ad_id': None,
        }

        try:
            self._goto(car_url)

            # Wait for car info section to load
            try:
                self.page.wait_for_selector("div.grid", timeout=15000)
            except Exception:
                logger.warning(f"Timeout waiting for detail page: {car_url}")
                return detail

            soup = BeautifulSoup(self.page.content(), 'html.parser')

            # --- Extract ad ID from URL ---
            id_match = re.search(r'/cars/(\d+)', car_url)
            if id_match:
                detail['ad_id'] = id_match.group(1)

            # --- Extract specs from معلومات السيارة grid ---
            # Each spec is: <span class="text-muted-foreground text-sm">LABEL</span>
            #               <span class="font-medium">VALUE</span>
            spec_labels = soup.find_all('span', class_=re.compile(r'text-muted-foreground.*text-sm|text-sm.*text-muted-foreground'))
            for label_span in spec_labels:
                label = label_span.get_text(strip=True)
                value_span = label_span.find_next_sibling('span', class_=re.compile(r'font-medium'))
                if not value_span:
                    continue
                value = value_span.get_text(strip=True)
                if not value:
                    continue

                # Map Arabic labels to schema fields
                if 'الماركة' in label or 'ماركة' in label:
                    detail['brand'] = value
                elif 'الموديل' in label or 'موديل' in label:
                    detail['model'] = value
                elif 'سنة الصنع' in label or 'السنة' in label:
                    year_match = re.search(r'\d{4}', value)
                    if year_match:
                        detail['year'] = int(year_match.group(0))
                elif 'المسافة المقطوعة' in label or 'الكيلومترات' in label:
                    detail['mileage_detail'] = value
                elif 'ناقل الحركة' in label or 'الناقل' in label or 'قير' in label:
                    detail['transmission'] = value
                elif 'الوقود' in label or 'نوع الوقود' in label:
                    detail['fuel_type'] = value
                elif 'نوع الهيكل' in label or 'الهيكل' in label:
                    detail['body_type'] = value
                elif 'اللون' in label:
                    detail['color'] = value
                elif 'المحرك' in label:
                    detail['engine'] = value
                elif 'الحالة' in label:
                    detail['condition'] = value
                elif 'المنشأ' in label or 'الأصل' in label:
                    detail['origin'] = value

            # --- Extract description ---
            desc_heading = soup.find(lambda tag: tag.name in ['h2', 'h3'] and 'الوصف' in tag.get_text())
            if desc_heading:
                desc_p = desc_heading.find_next('p')
                if desc_p:
                    detail['description'] = desc_p.get_text(strip=True)

            # --- Extract images ---
            images = []
            # Look for carousel/gallery images (aspect-video container)
            img_containers = soup.find_all('div', class_=re.compile(r'aspect-video'))
            for container in img_containers:
                img = container.find('img')
                if img and img.get('src'):
                    src = img.get('src')
                    if src.startswith('http') and src not in images:
                        images.append(src)

            # Fallback: look for any img with alt matching car name or large images
            if not images:
                for img in soup.find_all('img'):
                    src = img.get('src', '')
                    if src.startswith('http') and ('upload' in src or 'car' in src.lower() or 'image' in src.lower()):
                        if src not in images:
                            images.append(src)

            if images:
                detail['primary_image'] = images[0]
                detail['images'] = str(images).replace("'", '"')
                detail['image_count'] = len(images)

            # --- Extract phone number ---
            tel_link = soup.find('a', href=re.compile(r'^tel:'))
            if tel_link:
                detail['phone'] = tel_link.get('href', '').replace('tel:', '').strip()

            # --- Extract WhatsApp number ---
            wa_link = soup.find('a', href=re.compile(r'wa\.me'))
            if wa_link:
                wa_href = wa_link.get('href', '')
                wa_match = re.search(r'wa\.me/(\d+)', wa_href)
                if wa_match:
                    detail['whatsapp'] = wa_match.group(1)

        except Exception as e:
            logger.error(f"Error scraping detail page {car_url}: {e}")

        return detail

    # =========================================================================
    # MAIN SCRAPE METHOD
    # =========================================================================

    def scrape(self) -> List[Dict[str, Any]]:
        """
        Full two-stage scrape:
          Stage 1 → Collect all car links + basic card info
          Stage 2 → Visit each detail page for full specs

        Returns:
            List of unified 25-column schema dicts
        """
        logger.info(f"Starting Carsy scraper for: {self.base_url}")
        self.items = []

        try:
            self._init_browser()

            # --- STAGE 1: Collect all car links ---
            car_cards = self._collect_car_links()

            if not car_cards:
                logger.warning("No car links collected in Stage 1")
                return []

            logger.info(f"[Stage 2] Visiting {len(car_cards)} car detail pages...")

            # --- STAGE 2: Visit each detail page ---
            for idx, card in enumerate(car_cards):
                car_url = card.get('url')
                logger.info(f"[Stage 2] Car {idx + 1}/{len(car_cards)}: {car_url}")

                try:
                    detail = self._scrape_detail_page(car_url)

                    # Merge card info with detail info → unified schema
                    item = self._build_item(card, detail, car_url, idx)
                    if item:
                        self.items.append(item)

                    # Small delay to be respectful to the server
                    time.sleep(0.5)

                except Exception as e:
                    logger.error(f"[Stage 2] Error on car {car_url}: {e}")
                    continue

        finally:
            self._close_browser()

        logger.info(f"Scraping complete. Total items: {len(self.items)}")
        return self.items

    def _build_item(self, card: Dict, detail: Dict, car_url: str, idx: int) -> Optional[Dict[str, Any]]:
        """
        Merge Stage 1 card data + Stage 2 detail data into unified 25-column schema
        """
        try:
            # Use detail mileage if available, fallback to card mileage
            mileage = detail.get('mileage_detail') or card.get('mileage')

            # Build title from brand + model if not in card
            title = card.get('title')
            if not title and detail.get('brand'):
                year = detail.get('year', '')
                brand = detail.get('brand', '')
                model = detail.get('model', '')
                title = f"{year} {brand} {model}".strip()

            ad_id = detail.get('ad_id') or re.search(r'/cars/(\d+)', car_url).group(1)

            item = {
                'scraped_at': datetime.now().isoformat(),
                'source': 'carsy',
                'id': f"carsy_{ad_id}",
                'title': title,
                'price': card.get('price'),
                'price_raw': card.get('price_raw'),
                'brand': detail.get('brand'),
                'model': detail.get('model'),
                'category': None,
                'year': detail.get('year'),
                'mileage': mileage,
                'location': card.get('location'),
                'posted_date': card.get('posted_time'),
                'condition': detail.get('condition'),
                'fuel_type': detail.get('fuel_type'),
                'transmission': detail.get('transmission'),
                'body_type': detail.get('body_type'),
                'origin': detail.get('origin'),
                'image_count': detail.get('image_count', 0),
                'images': detail.get('images', '[]'),
                'primary_image': detail.get('primary_image'),
                'link': car_url,
                'ad_id': ad_id,
                'ad_url': car_url,
                'description': detail.get('description'),
                'listing_type': 'sell',
            }

            return item

        except Exception as e:
            logger.error(f"Error building item for {car_url}: {e}")
            return None

    # =========================================================================
    # HELPERS
    # =========================================================================

    def _clean_price(self, price_text: str) -> Optional[float]:
        """Clean price string to float"""
        try:
            cleaned = re.sub(r'[^\d.]', '', price_text)
            return float(cleaned) if cleaned else None
        except (ValueError, TypeError):
            return None

    def get_statistics(self, items: List[Dict]) -> Dict[str, Any]:
        """Calculate statistics from scraped items"""
        if not items:
            return {'total_items': 0, 'price_stats': {}, 'year_stats': {}, 'brand_stats': {}}

        prices = [item.get('price') for item in items if item.get('price')]
        years = [item.get('year') for item in items if item.get('year')]
        brands = [item.get('brand') for item in items if item.get('brand')]

        return {
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
                if all([item.get('price'), item.get('brand'), item.get('year'), item.get('location')])
            ),
        }

    def _count_brands(self, brands: List[str]) -> Dict[str, int]:
        """Count brand occurrences, sorted descending"""
        counts = {}
        for brand in brands:
            counts[brand] = counts.get(brand, 0) + 1
        return dict(sorted(counts.items(), key=lambda x: x[1], reverse=True))
