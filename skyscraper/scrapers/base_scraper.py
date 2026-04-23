"""
Base Scraper Class - Foundation for all website scrapers
Provides common functionality for scraping and data management
"""
import logging
from abc import ABC, abstractmethod
from typing import List, Dict, Any
from datetime import datetime
import json

logger = logging.getLogger(__name__)


class BaseScraper(ABC):
    """
    Abstract base class for all website scrapers.

    Each scraper should:
    1. Inherit from this class
    2. Implement the scrape() method
    3. Override website-specific parsing methods
    """

    def __init__(self, website_config: Dict[str, Any]):
        """
        Initialize scraper with website configuration

        Args:
            website_config: Configuration dict with:
                - id: website identifier
                - name: human-readable name
                - url: base URL to scrape
                - type: 'cars', 'realestate', etc.
                - google_sheet_id: sheet to save data to
                - image_folder: where to store images
        """
        self.config = website_config
        self.website_id = website_config.get('id')
        self.website_name = website_config.get('name')
        self.website_url = website_config.get('url')
        self.website_type = website_config.get('type')
        self.sheet_id = website_config.get('google_sheet_id')
        self.image_folder = website_config.get('image_folder', 'images/default')

        logger.info(f"Initialized {self.__class__.__name__} for {self.website_name}")

    @abstractmethod
    def scrape(self) -> List[Dict]:
        """
        Main scraping method - must be implemented by subclasses

        Returns:
            List of dictionaries with scraped data
        """
        raise NotImplementedError("Subclasses must implement scrape() method")

    def get_statistics(self, items: List[Dict]) -> Dict[str, Any]:
        """
        Calculate statistics from scraped items

        Args:
            items: List of scraped items

        Returns:
            Dictionary with statistics
        """
        stats = {
            'total_items': len(items),
            'scraped_at': datetime.now().isoformat(),
            'items_by_field': self._analyze_field_distribution(items),
        }

        # Add type-specific statistics
        if self.website_type == 'cars':
            stats.update(self._get_car_statistics(items))
        elif self.website_type == 'realestate':
            stats.update(self._get_realestate_statistics(items))

        return stats

    def _analyze_field_distribution(self, items: List[Dict]) -> Dict[str, int]:
        """
        Analyze distribution of fields across items

        Returns how many items have each field populated
        """
        if not items:
            return {}

        field_counts = {}
        for field in items[0].keys():
            count = sum(1 for item in items if item.get(field) and item.get(field) != 'N/A')
            field_counts[field] = count

        return field_counts

    def _get_car_statistics(self, items: List[Dict]) -> Dict[str, Any]:
        """Statistics specific to car listings"""
        if not items:
            return {}

        stats = {}

        # Most common makes
        makes = {}
        for item in items:
            make = item.get('make', 'N/A')
            if make != 'N/A':
                makes[make] = makes.get(make, 0) + 1

        if makes:
            top_makes = sorted(makes.items(), key=lambda x: -x[1])[:5]
            stats['top_makes'] = [{'name': name, 'count': count} for name, count in top_makes]

        # Average year
        years = [int(item.get('year', 0)) for item in items if item.get('year', '').isdigit()]
        if years:
            stats['avg_year'] = sum(years) / len(years)
            stats['year_range'] = {'min': min(years), 'max': max(years)}

        # Price analysis
        prices = []
        for item in items:
            price_str = item.get('price', '')
            # Extract numeric value from price
            price_val = self._extract_price_value(price_str)
            if price_val:
                prices.append(price_val)

        if prices:
            stats['price_stats'] = {
                'avg': sum(prices) / len(prices),
                'min': min(prices),
                'max': max(prices),
            }

        # Body types
        body_types = {}
        for item in items:
            body = item.get('body_type', 'N/A')
            if body != 'N/A':
                body_types[body] = body_types.get(body, 0) + 1

        if body_types:
            stats['body_type_distribution'] = body_types

        return stats

    def _get_realestate_statistics(self, items: List[Dict]) -> Dict[str, Any]:
        """Statistics specific to real estate listings"""
        if not items:
            return {}

        stats = {}

        # Most common locations
        locations = {}
        for item in items:
            location = item.get('location', 'N/A')
            if location != 'N/A':
                locations[location] = locations.get(location, 0) + 1

        if locations:
            top_locs = sorted(locations.items(), key=lambda x: -x[1])[:5]
            stats['top_locations'] = [{'name': name, 'count': count} for name, count in top_locs]

        # Price per sqm analysis
        prices_sqm = []
        for item in items:
            price = self._extract_price_value(item.get('price', ''))
            size = self._extract_size_value(item.get('size', ''))
            if price and size and size > 0:
                prices_sqm.append(price / size)

        if prices_sqm:
            stats['avg_price_per_sqm'] = sum(prices_sqm) / len(prices_sqm)

        # Bedroom distribution
        bedrooms = {}
        for item in items:
            bed_count = item.get('bedrooms', 'N/A')
            if bed_count != 'N/A':
                bedrooms[str(bed_count)] = bedrooms.get(str(bed_count), 0) + 1

        if bedrooms:
            stats['bedroom_distribution'] = bedrooms

        return stats

    def _extract_price_value(self, price_str: str) -> float:
        """
        Extract numeric price value from string

        Examples:
            "السعر 17,000 دولار" -> 17000.0
            "$25,000" -> 25000.0
        """
        import re
        if not price_str:
            return None

        # Remove non-numeric characters except dots and commas
        numbers = re.findall(r'[\d,]+', price_str)
        if numbers:
            # Take the first number, remove commas
            return float(numbers[0].replace(',', ''))

        return None

    def _extract_size_value(self, size_str: str) -> float:
        """
        Extract numeric size value from string

        Examples:
            "150 sqm" -> 150.0
            "150 متر" -> 150.0
        """
        import re
        if not size_str:
            return None

        numbers = re.findall(r'[\d,]+', size_str)
        if numbers:
            return float(numbers[0].replace(',', ''))

        return None

    def log_scrape_result(self, result: Dict[str, Any]) -> None:
        """Log scraping result with statistics"""
        logger.info(f"""
        Scrape completed for {self.website_name}:
        - Total items: {result.get('total_items', 0)}
        - New items: {result.get('new_items', 0)}
        - Duplicates: {result.get('duplicates', 0)}
        - Duration: {result.get('duration', 'N/A')}
        """)

    def to_dict(self) -> Dict:
        """Convert scraper config to dictionary"""
        return {
            'id': self.website_id,
            'name': self.website_name,
            'url': self.website_url,
            'type': self.website_type,
            'sheet_id': self.sheet_id,
            'class': self.__class__.__name__,
        }


class CarsScraper(BaseScraper):
    """
    Base class for car listing scrapers
    Provides common functionality for all car-related websites
    """

    def __init__(self, website_config: Dict[str, Any]):
        super().__init__(website_config)
        assert website_config.get('type') == 'cars', "CarsScraper requires type='cars'"

    def get_market_analysis(self, items: List[Dict]) -> Dict[str, Any]:
        """
        Analyze car market from scraped items

        Returns insights about:
        - Popular makes and models
        - Price trends
        - Age of vehicles
        - Body types and transmissions
        """
        return {
            'total_vehicles': len(items),
            'statistics': self.get_statistics(items),
            'market_insights': self._calculate_market_insights(items),
        }

    def _calculate_market_insights(self, items: List[Dict]) -> Dict[str, Any]:
        """Calculate market-specific insights"""
        insights = {}

        if not items:
            return insights

        # Most common combinations
        brand_models = {}
        for item in items:
            make = item.get('make', 'Unknown')
            model = item.get('model', 'Unknown')
            key = f"{make} {model}"
            brand_models[key] = brand_models.get(key, 0) + 1

        if brand_models:
            top_combos = sorted(brand_models.items(), key=lambda x: -x[1])[:10]
            insights['most_common_models'] = [
                {'model': name, 'count': count} for name, count in top_combos
            ]

        # Fuel type distribution
        fuel_types = {}
        for item in items:
            fuel = item.get('fuel_type', 'Unknown')
            fuel_types[fuel] = fuel_types.get(fuel, 0) + 1

        if fuel_types:
            insights['fuel_type_distribution'] = fuel_types

        # Transmission distribution
        transmissions = {}
        for item in items:
            trans = item.get('transmission', 'Unknown')
            transmissions[trans] = transmissions.get(trans, 0) + 1

        if transmissions:
            insights['transmission_distribution'] = transmissions

        return insights


class RealEstateScraper(BaseScraper):
    """
    Base class for real estate scrapers
    Provides common functionality for all real estate websites
    """

    def __init__(self, website_config: Dict[str, Any]):
        super().__init__(website_config)
        assert website_config.get('type') == 'realestate', "RealEstateScraper requires type='realestate'"

    def get_market_analysis(self, items: List[Dict]) -> Dict[str, Any]:
        """
        Analyze real estate market from scraped items

        Returns insights about:
        - Popular locations
        - Price trends by area
        - Property types
        - Sizes and bedroom counts
        """
        return {
            'total_properties': len(items),
            'statistics': self.get_statistics(items),
            'market_insights': self._calculate_market_insights(items),
        }

    def _calculate_market_insights(self, items: List[Dict]) -> Dict[str, Any]:
        """Calculate market-specific insights"""
        insights = {}

        if not items:
            return insights

        # Price by location
        price_by_location = {}
        for item in items:
            location = item.get('location', 'Unknown')
            price = self._extract_price_value(item.get('price', ''))

            if price:
                if location not in price_by_location:
                    price_by_location[location] = []
                price_by_location[location].append(price)

        # Calculate average price per location
        avg_by_location = {}
        for location, prices in price_by_location.items():
            avg_by_location[location] = sum(prices) / len(prices)

        if avg_by_location:
            sorted_locs = sorted(avg_by_location.items(), key=lambda x: -x[1])[:10]
            insights['most_expensive_locations'] = [
                {'location': name, 'avg_price': price} for name, price in sorted_locs
            ]

        # Property type distribution
        prop_types = {}
        for item in items:
            ptype = item.get('property_type', 'Unknown')
            prop_types[ptype] = prop_types.get(ptype, 0) + 1

        if prop_types:
            insights['property_type_distribution'] = prop_types

        return insights
