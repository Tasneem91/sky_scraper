"""
Main orchestration module for the web scraper
Coordinates scraping, deduplication, and Google Sheets updates
"""
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Dict

from scraper import CarScraper
from sheets_integration import GoogleSheetsManager
from deduplication import Deduplicator, prepare_data_for_sheets
from config import WEBSITE_CONFIG, LOGS_DIR

# Setup logging
log_file = LOGS_DIR / f"scraper_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class ScraperOrchestrator:
    """Orchestrate the scraping, deduplication, and sheets update process"""

    def __init__(self, website_key: str = "syriacar", spreadsheet_id: str = None):
        """
        Initialize the orchestrator

        Args:
            website_key: Key of the website to scrape
            spreadsheet_id: ID of the Google Sheet to update
        """
        self.website_key = website_key
        self.spreadsheet_id = spreadsheet_id
        self.scraper = None
        self.sheets_manager = None
        self.scraped_cars = []
        self.unique_cars = []
        self.duplicate_cars = []

        logger.info(f"Initializing ScraperOrchestrator for {website_key}")

    def scrape_website(self) -> List[Dict]:
        """
        Scrape data from the website

        Returns:
            List of scraped car records
        """
        try:
            logger.info(f"Starting scrape for {self.website_key}")
            self.scraper = CarScraper(self.website_key)
            self.scraped_cars = self.scraper.scrape()

            logger.info(f"Successfully scraped {len(self.scraped_cars)} cars")
            return self.scraped_cars

        except Exception as e:
            logger.error(f"Error during scraping: {e}", exc_info=True)
            raise

    def update_sheets(self, test_mode: bool = False) -> Dict:
        """
        Update Google Sheets with new data (after deduplication)

        Args:
            test_mode: If True, don't actually update sheets

        Returns:
            Summary of the update
        """
        try:
            logger.info("Initializing Google Sheets manager")
            self.sheets_manager = GoogleSheetsManager()

            if self.spreadsheet_id:
                self.sheets_manager.set_spreadsheet_id(self.spreadsheet_id)
            else:
                # Create new spreadsheet
                sheet_title = f"{self.website_key.title()} Cars - {datetime.now().strftime('%Y-%m-%d')}"
                self.sheets_manager.create_sheet(sheet_title)
                self.spreadsheet_id = self.sheets_manager.spreadsheet_id

            # Get existing data from sheets
            logger.info("Retrieving existing data from Google Sheets")
            existing_data = self.sheets_manager.get_all_data()

            # Get headers or create new ones
            if existing_data:
                headers = existing_data[0]
            else:
                headers = self._generate_headers()
                logger.info(f"Created new headers: {headers}")

                if not test_mode:
                    self.sheets_manager.append_rows([headers])
                    self.sheets_manager.format_header()

            # Perform deduplication
            logger.info("Performing deduplication")
            deduplicator = Deduplicator(existing_data, headers)
            self.unique_cars, self.duplicate_cars = deduplicator.find_duplicates(self.scraped_cars)

            # Prepare data for sheets
            logger.info("Preparing data for Google Sheets")
            rows_to_add = prepare_data_for_sheets(self.unique_cars, headers)

            # Update sheets if there are new records
            if rows_to_add:
                if test_mode:
                    logger.info(f"[TEST MODE] Would add {len(rows_to_add)} new rows")
                else:
                    logger.info(f"Adding {len(rows_to_add)} new rows to Google Sheets")
                    self.sheets_manager.append_rows(rows_to_add)
            else:
                logger.info("No new unique records to add")

            summary = {
                "website": self.website_key,
                "scraped_count": len(self.scraped_cars),
                "unique_count": len(self.unique_cars),
                "duplicate_count": len(self.duplicate_cars),
                "rows_added": len(rows_to_add),
                "spreadsheet_id": self.spreadsheet_id,
                "timestamp": datetime.now().isoformat(),
                "test_mode": test_mode,
            }

            logger.info(f"Update summary: {summary}")
            return summary

        except Exception as e:
            logger.error(f"Error updating Google Sheets: {e}", exc_info=True)
            raise

    def run(self, test_mode: bool = False) -> Dict:
        """
        Run the complete scraping and update process

        Args:
            test_mode: If True, don't actually update sheets

        Returns:
            Summary of the operation
        """
        try:
            logger.info("=" * 80)
            logger.info(f"Starting scraper run for {self.website_key}")
            logger.info(f"Test mode: {test_mode}")
            logger.info("=" * 80)

            # Step 1: Scrape website
            self.scrape_website()

            if not self.scraped_cars:
                logger.warning("No cars were scraped")
                return {
                    "status": "failed",
                    "error": "No cars scraped",
                    "timestamp": datetime.now().isoformat(),
                }

            # Step 2: Update sheets with deduplication
            summary = self.update_sheets(test_mode=test_mode)

            summary["status"] = "success"

            logger.info("=" * 80)
            logger.info(f"Scraper run completed successfully")
            logger.info(f"Final summary: {summary}")
            logger.info("=" * 80)

            return summary

        except Exception as e:
            logger.error(f"Scraper run failed: {e}", exc_info=True)
            return {
                "status": "failed",
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
            }

    def _generate_headers(self) -> List[str]:
        """
        Generate headers based on scraped data

        Returns:
            List of headers
        """
        if not self.scraped_cars:
            return ["id", "title", "price", "description", "link", "image_path", "website", "scraped_at"]

        # Get all unique keys from all scraped cars
        headers = []
        seen = set()

        for car in self.scraped_cars:
            for key in car.keys():
                if key not in seen:
                    headers.append(key)
                    seen.add(key)

        return headers


if __name__ == "__main__":
    # Example usage
    # IMPORTANT: Create a Google Sheet first, then add its ID here
    SPREADSHEET_ID = "1Oyhm4mrg7zz1pf3I-1_nhddTJsuscN8ppEn-Nr3UCFI"  # ← Just the ID part, no /edit or #gid

    if not SPREADSHEET_ID:
        print("=" * 80)
        print("⚠️  SETUP REQUIRED: Google Sheet ID needed!")
        print("=" * 80)
        print("\n1. Create a new Google Sheet:")
        print("   - Go to https://docs.google.com/spreadsheets")
        print("   - Click 'Create new spreadsheet'")
        print("   - Name it: 'SyriaCar Data'")
        print("\n2. Share with service account:")
        print("   - In credentials.json, find 'client_email'")
        print("   - Share the sheet with that email address")
        print("   - Give it 'Editor' access")
        print("\n3. Get the spreadsheet ID:")
        print("   - Open the sheet")
        print("   - Copy from URL: ...d/{SHEET_ID}/...")
        print("\n4. Update this script:")
        print("   - Set SPREADSHEET_ID = 'YOUR_SHEET_ID'")
        print("\n" + "=" * 80)
        exit(1)

    orchestrator = ScraperOrchestrator(
        website_key="syriacar",
        spreadsheet_id=SPREADSHEET_ID
    )

    # Run in test mode first
    print("Running in TEST MODE (no actual updates will be made)")
    result = orchestrator.run(test_mode=False)
    print(f"\nTest run result: {result}")

    # If test mode looks good, run without test mode
    # result = orchestrator.run(test_mode=False)
    # print(f"\nProduction run result: {result}")
