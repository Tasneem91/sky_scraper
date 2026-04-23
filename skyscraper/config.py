"""
Configuration file for the web scraper
"""
import os
from pathlib import Path

# Project directories
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
IMAGES_DIR = DATA_DIR / "images"
LOGS_DIR = BASE_DIR / "logs"

# Create directories if they don't exist
for directory in [DATA_DIR, IMAGES_DIR, LOGS_DIR]:
    directory.mkdir(parents=True, exist_ok=True)

# Website configuration
WEBSITE_CONFIG = {
    "syriacar": {
        "url": "https://syriacar.net/",
        "name": "Syria Car",
        "selectors": {
            # These will be refined after inspecting the website
            "car_listings": "div.car-item",  # Main container for each car
            "title": "h2.car-title",
            "price": "span.price",
            "description": "p.description",
            "image": "img.car-image",
            "link": "a.car-link",
        },
        "image_folder": str(IMAGES_DIR / "syriacar"),
    }
}

# Google Sheets configuration
GOOGLE_SHEETS_CONFIG = {
    "credentials_file": BASE_DIR / "credentials.json",
    "token_file": BASE_DIR / "token.json",
    "scopes": ["https://www.googleapis.com/auth/spreadsheets"],
}

# Scraper configuration
SCRAPER_CONFIG = {
    "timeout": 30,
    "headless": True,  # Run browser in headless mode
    "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "delay_between_requests": 2,  # seconds
}

# Scheduler configuration
SCHEDULER_CONFIG = {
    "enabled": True,
    "schedule": "cron",
    "day_of_week": "0-6",  # 0=Monday, 6=Sunday (daily)
    "hour": 9,  # Run at 9 AM
    "minute": 0,
}

# Deduplication configuration
DEDUP_CONFIG = {
    "check_by_id": True,
    "check_by_fields": ["title", "price"],  # Fields to compare for duplication
    "id_field": "id",  # Field that contains unique ID
}

# Logging configuration
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
LOG_LEVEL = "INFO"
