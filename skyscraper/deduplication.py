"""
Deduplication module for handling duplicate data in Google Sheets
"""
import logging
from typing import List, Dict, Tuple

from config import DEDUP_CONFIG

logger = logging.getLogger(__name__)


class Deduplicator:
    """Handle deduplication of scraped data"""

    def __init__(self, existing_data: List[List[str]], headers: List[str]):
        """
        Initialize deduplicator with existing sheet data

        Args:
            existing_data: List of rows from the sheet
            headers: List of column headers
        """
        self.existing_data = existing_data
        self.headers = headers
        self.existing_records = self._convert_to_records()

    def _convert_to_records(self) -> List[Dict]:
        """
        Convert sheet rows to list of dictionaries

        Returns:
            List of record dictionaries
        """
        records = []

        for row in self.existing_data[1:]:  # Skip header row
            if not row:  # Skip empty rows
                continue

            record = {}
            for i, header in enumerate(self.headers):
                value = row[i] if i < len(row) else ""
                record[header] = value

            records.append(record)

        return records

    def find_duplicates(self, new_data: List[Dict]) -> Tuple[List[Dict], List[Dict]]:
        """
        Find duplicate records in new data

        Args:
            new_data: List of new car records to check

        Returns:
            Tuple of (unique_records, duplicate_records)
        """
        unique_records = []
        duplicate_records = []

        for new_record in new_data:
            if self._is_duplicate(new_record):
                duplicate_records.append(new_record)
                logger.info(f"Found duplicate: {new_record.get('id', 'Unknown ID')}")
            else:
                unique_records.append(new_record)

        logger.info(f"Found {len(unique_records)} unique and {len(duplicate_records)} duplicate records")
        return unique_records, duplicate_records

    def _is_duplicate(self, new_record: Dict) -> bool:
        """
        Check if a record already exists in the sheet

        Args:
            new_record: Record to check

        Returns:
            True if duplicate, False otherwise
        """
        # Check by ID if configured
        if DEDUP_CONFIG.get("check_by_id"):
            id_field = DEDUP_CONFIG.get("id_field", "id")
            new_id = new_record.get(id_field)

            if new_id:
                for existing in self.existing_records:
                    if existing.get(id_field) == new_id:
                        logger.debug(f"Duplicate found by ID: {new_id}")
                        return True

        # Check by field comparison if configured
        if DEDUP_CONFIG.get("check_by_fields"):
            check_fields = DEDUP_CONFIG.get("check_by_fields", [])

            for existing in self.existing_records:
                match = True

                for field in check_fields:
                    new_value = new_record.get(field, "").strip().lower()
                    existing_value = existing.get(field, "").strip().lower()

                    if new_value != existing_value:
                        match = False
                        break

                if match:
                    logger.debug(f"Duplicate found by fields: {check_fields}")
                    return True

        return False

    def get_summary(self) -> Dict:
        """
        Get summary of deduplication results

        Returns:
            Summary dictionary
        """
        return {
            "existing_records_count": len(self.existing_records),
            "check_by_id": DEDUP_CONFIG.get("check_by_id"),
            "check_by_fields": DEDUP_CONFIG.get("check_by_fields"),
        }


def prepare_data_for_sheets(cars: List[Dict], headers: List[str]) -> List[List]:
    """
    Convert car data dictionary to list of lists for Google Sheets

    Args:
        cars: List of car records
        headers: List of column headers

    Returns:
        List of rows ready for Google Sheets
    """
    rows = []

    for car in cars:
        row = []
        for header in headers:
            value = car.get(header, "")
            # Convert value to string and handle None
            row.append(str(value) if value is not None else "")

        rows.append(row)

    return rows


if __name__ == "__main__":
    # Test deduplication
    existing_data = [
        ["id", "title", "price", "link"],
        ["car_1", "Toyota Camry", "15000", "http://example.com/car1"],
        ["car_2", "Honda Civic", "12000", "http://example.com/car2"],
    ]

    headers = ["id", "title", "price", "link"]

    dedup = Deduplicator(existing_data, headers)

    new_cars = [
        {"id": "car_1", "title": "Toyota Camry", "price": "15000", "link": "http://example.com/car1"},  # Duplicate
        {"id": "car_3", "title": "Ford Focus", "price": "11000", "link": "http://example.com/car3"},  # New
    ]

    unique, duplicates = dedup.find_duplicates(new_cars)
    print(f"Unique: {len(unique)}, Duplicates: {len(duplicates)}")
    print(f"Summary: {dedup.get_summary()}")
