"""
Scheduler module for running the scraper on a weekly basis
"""
import logging
import time
from datetime import datetime
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from main import ScraperOrchestrator
from config import SCHEDULER_CONFIG

logger = logging.getLogger(__name__)


class ScraperScheduler:
    """Manage scheduled execution of the web scraper"""

    def __init__(self, website_key: str = "syriacar", spreadsheet_id: str = None):
        """
        Initialize the scheduler

        Args:
            website_key: Key of the website to scrape
            spreadsheet_id: ID of the Google Sheet to update
        """
        self.website_key = website_key
        self.spreadsheet_id = spreadsheet_id
        self.scheduler = BlockingScheduler()

        logger.info(f"ScraperScheduler initialized for {website_key}")

    def _scraper_job(self):
        """Job function to run the scraper"""
        try:
            logger.info(f"Running scheduled scraper job at {datetime.now()}")

            orchestrator = ScraperOrchestrator(
                website_key=self.website_key,
                spreadsheet_id=self.spreadsheet_id
            )

            result = orchestrator.run(test_mode=False)

            if result.get("status") == "success":
                logger.info(f"Scraper job completed successfully: {result}")
            else:
                logger.error(f"Scraper job failed: {result}")

        except Exception as e:
            logger.error(f"Error in scraper job: {e}", exc_info=True)

    def schedule_weekly(self, day_of_week: str = "mon", hour: int = 9, minute: int = 0):
        """
        Schedule the scraper to run weekly

        Args:
            day_of_week: Day of week (mon, tue, wed, etc.)
            hour: Hour of day (0-23)
            minute: Minute of hour (0-59)
        """
        trigger = CronTrigger(
            day_of_week=day_of_week,
            hour=hour,
            minute=minute
        )

        self.scheduler.add_job(
            self._scraper_job,
            trigger=trigger,
            id=f"scraper_{self.website_key}",
            name=f"Scraper for {self.website_key}",
            replace_existing=True
        )

        logger.info(f"Scheduled scraper to run on {day_of_week} at {hour:02d}:{minute:02d}")

    def schedule_daily(self, hour: int = 9, minute: int = 0):
        """
        Schedule the scraper to run daily

        Args:
            hour: Hour of day (0-23)
            minute: Minute of hour (0-59)
        """
        trigger = CronTrigger(hour=hour, minute=minute)

        self.scheduler.add_job(
            self._scraper_job,
            trigger=trigger,
            id=f"scraper_{self.website_key}",
            name=f"Scraper for {self.website_key}",
            replace_existing=True
        )

        logger.info(f"Scheduled scraper to run daily at {hour:02d}:{minute:02d}")

    def start(self):
        """Start the scheduler (blocking call)"""
        try:
            logger.info("Starting scheduler")
            self.scheduler.start()
        except KeyboardInterrupt:
            logger.info("Scheduler interrupted by user")
            self.stop()

    def stop(self):
        """Stop the scheduler"""
        try:
            self.scheduler.shutdown()
            logger.info("Scheduler stopped")
        except Exception as e:
            logger.error(f"Error stopping scheduler: {e}")


def run_scheduler(website_key: str = "syriacar", spreadsheet_id: str = None):
    """
    Run the scheduler with configuration from config.py

    Args:
        website_key: Key of the website to scrape
        spreadsheet_id: ID of the Google Sheet to update
    """
    scheduler = ScraperScheduler(website_key, spreadsheet_id)

    # Schedule based on configuration
    hour = SCHEDULER_CONFIG.get("hour", 9)
    minute = SCHEDULER_CONFIG.get("minute", 0)

    # Check if daily or weekly
    day_of_week = SCHEDULER_CONFIG.get("day_of_week", "0-6")

    if day_of_week == "0-6" or day_of_week == "*":
        # Daily
        scheduler.schedule_daily(hour, minute)
    else:
        # Weekly
        scheduler.schedule_weekly(day_of_week, hour, minute)

    # Start the scheduler
    scheduler.start()


if __name__ == "__main__":
    # Test run
    logger.info("Starting test run...")

    orchestrator = ScraperOrchestrator(website_key="syriacar")
    result = orchestrator.run(test_mode=True)

    print(f"Test run result: {result}")

    # Uncomment to start the scheduler
    # run_scheduler(website_key="syriacar", spreadsheet_id="YOUR_SHEET_ID")
