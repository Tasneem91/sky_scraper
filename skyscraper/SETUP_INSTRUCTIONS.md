# Web Scraper Setup Instructions

This guide will help you set up the web scraper for collecting car data and saving it to Google Sheets.

## Prerequisites

- Python 3.8 or higher
- Windows 10/11 (or modify for your OS)
- Google account with access to Google Sheets API
- Chrome browser (for Selenium)

## Step 1: Install Python Dependencies

1. Open Command Prompt and navigate to the project directory:
```bash
cd D:\skyscraper
```

2. Install required Python packages:
```bash
pip install -r requirements.txt
```

If you get permission errors, try:
```bash
pip install --user -r requirements.txt
```

## Step 2: Set Up Google Sheets API

### Option A: Using Service Account (Recommended for automated scripts)

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project (or select existing one)
3. Enable the Google Sheets API:
   - Search for "Sheets API" in the search bar
   - Click "Enable"
4. Create a Service Account:
   - Go to "Credentials" in the left menu
   - Click "Create Credentials" → "Service Account"
   - Fill in the service account name and click "Create and Continue"
   - Grant "Editor" role and click "Continue"
   - Click "Create Key" → JSON
   - Save the JSON file as `credentials.json` in the `D:\skyscraper` folder

5. Share your Google Sheet with the service account email:
   - Open the JSON file and copy the "client_email" value
   - Open your Google Sheet
   - Click "Share" and paste the email
   - Give it "Editor" access

### Option B: Using OAuth2 (For personal use)

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project
3. Enable Google Sheets API
4. Create OAuth2 credentials:
   - Go to "Credentials"
   - Click "Create Credentials" → "OAuth client ID"
   - Select "Desktop application"
   - Download and save as `credentials.json` in `D:\skyscraper`
5. Run the script once - it will prompt you to authorize in your browser

## Step 3: Configure the Scraper

Edit `config.py` to customize:

### Website Configuration
```python
WEBSITE_CONFIG = {
    "syriacar": {
        "url": "https://syriacar.net/",
        "name": "Syria Car",
        # ... selectors (we'll identify these in Step 4)
    }
}
```

### Scheduler Configuration
```python
SCHEDULER_CONFIG = {
    "hour": 9,      # Run at 9 AM
    "minute": 0,    # At 00 minutes
    "day_of_week": "0-6",  # Daily (0-6 = all days, 'mon' for weekly Monday)
}
```

For weekly runs (e.g., every Monday at 9 AM):
```python
"day_of_week": "mon",  # or use '0' for Monday
```

## Step 4: Inspect the Website and Update Selectors

The scraper needs to know which HTML elements to look for.

1. Open the website in Chrome: https://syriacar.net/
2. Right-click on a car listing and select "Inspect"
3. Find the CSS selectors for:
   - Main car container (e.g., `div.car-item`)
   - Title (e.g., `h2.car-title`)
   - Price (e.g., `span.price`)
   - Image (e.g., `img.car-image`)
   - Link to full listing (e.g., `a.car-link`)

4. Update these in `config.py`:
```python
"selectors": {
    "car_listings": "div.car-item",  # Main container
    "title": "h2.car-title",
    "price": "span.price",
    "description": "p.description",
    "image": "img.car-image",
    "link": "a.car-link",
}
```

**Note**: If you can't find exact selectors, use more general ones like:
- `div` for all divs
- `.class-name` for classes
- `#id-name` for IDs

## Step 5: Run the Scraper

### Test Run (No actual updates)

```bash
python main.py
```

This will:
1. Scrape the website
2. Check for duplicates
3. Show what WOULD be added (without actually adding)

Check the output for:
- Number of cars scraped
- Number of unique records
- Number of duplicates
- Spreadsheet ID

### Production Run

Once you've verified the test run:

1. Create a Google Sheet manually or use the one created during test
2. Note the spreadsheet ID (from the URL: `docs.google.com/spreadsheets/d/{SHEET_ID}/...`)
3. Update `main.py` with your spreadsheet ID:

```python
if __name__ == "__main__":
    orchestrator = ScraperOrchestrator(
        website_key="syriacar",
        spreadsheet_id="YOUR_ACTUAL_SHEET_ID"  # Add here
    )
    result = orchestrator.run(test_mode=False)
```

4. Run the production scraper:
```bash
python main.py
```

## Step 6: Schedule Weekly Runs

### Option A: Windows Task Scheduler (Recommended)

1. Create a batch file `run_scraper.bat` in `D:\skyscraper`:
```batch
@echo off
cd /d D:\skyscraper
python main.py >> logs\scraper.log 2>&1
pause
```

2. Open Task Scheduler:
   - Press `Win + R`
   - Type `taskschd.msc`
   - Click "Create Basic Task"

3. Configure:
   - **Name**: "Car Web Scraper"
   - **Trigger**: "Weekly" → Select day and time
   - **Action**: "Start a program" → `C:\path\to\python.exe` (or use batch file)
   - **Program/script**: `D:\skyscraper\main.py`
   - **Add arguments**: (leave empty)
   - **Start in**: `D:\skyscraper`

4. Click "Finish"

### Option B: Using Python Scheduler

Run the scheduler:
```bash
python scheduler.py
```

This will keep the process running and execute jobs at scheduled times.

**Note**: This approach requires the terminal to stay open.

## Step 7: Monitor Logs

Logs are saved in `logs/` folder with timestamps.

To view the latest log:
```bash
type logs\scraper_*.log | tail -20
```

Or open logs in a text editor.

## Troubleshooting

### Error: "Could not import 'selenium'"
```bash
pip install selenium
```

### Error: "credentials.json not found"
- Make sure you created the credentials file in Step 2
- Place it in `D:\skyscraper/credentials.json`

### Error: "spreadsheet not found"
- Check that the spreadsheet ID is correct
- Make sure the service account email has access to the sheet

### Scraper returns 0 cars
- The CSS selectors might be wrong
- Run the inspector and check the actual HTML structure
- Update selectors in `config.py`

### Images not downloading
- Check if the image URLs are correct
- Some websites might block image downloads
- You can modify the User-Agent in `config.py`

## Adding New Websites

To add another website (e.g., "example_cars"):

1. Add configuration to `config.py`:
```python
WEBSITE_CONFIG = {
    "syriacar": { ... },
    "example_cars": {
        "url": "https://example.com/cars",
        "name": "Example Cars",
        "selectors": {
            "car_listings": "div.listing",
            "title": "h3.name",
            "price": "span.cost",
            "image": "img.photo",
            "link": "a.details",
        },
        "image_folder": str(IMAGES_DIR / "example_cars"),
    }
}
```

2. Create a separate spreadsheet for this website
3. Run the scraper:
```bash
python -c "from main import ScraperOrchestrator; ScraperOrchestrator('example_cars', 'SHEET_ID').run()"
```

## Support

If you encounter issues:

1. Check the logs in `logs/` folder
2. Run in test mode to see detailed output
3. Verify website selectors using Chrome Inspector
4. Check Google Sheets API credentials
5. Ensure all dependencies are installed

## Next Steps

- [ ] Set up Google Sheets API credentials
- [ ] Test run the scraper
- [ ] Verify data and deduplication
- [ ] Create the Google Sheet
- [ ] Configure for production
- [ ] Set up Task Scheduler
- [ ] Monitor logs for first run

Good luck! 🚀
