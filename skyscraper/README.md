# Web Scraper for Car Data Collection

A Python-based web scraper that automatically collects car information from websites, downloads images, and saves data to Google Sheets with automatic deduplication.

## Features

✨ **Key Features:**
- 🕷️ Web scraping with Selenium and BeautifulSoup
- 📸 Automatic image download and storage
- 📊 Google Sheets integration
- 🔍 Smart deduplication (by ID and field comparison)
- ⏰ Weekly scheduled runs
- 📝 Comprehensive logging
- 🔄 Reusable design for multiple websites
- 🛡️ Error handling and retry logic

## Project Structure

```
D:\skyscraper\
├── config.py                    # Configuration file
├── scraper.py                   # Web scraping logic
├── sheets_integration.py        # Google Sheets API integration
├── deduplication.py            # Deduplication logic
├── main.py                     # Main orchestration
├── scheduler.py                # Weekly scheduler
├── requirements.txt            # Python dependencies
├── SETUP_INSTRUCTIONS.md       # Detailed setup guide
├── QUICK_START.md             # Quick start guide
├── README.md                   # This file
├── data/                       # Data directory
│   └── images/                 # Downloaded images
│       └── syriacar/           # Website-specific images
└── logs/                       # Execution logs
```

## Quick Start

### 1. Install Dependencies
```bash
cd D:\skyscraper
pip install -r requirements.txt
```

### 2. Set Up Google Sheets API
See `SETUP_INSTRUCTIONS.md` for detailed steps.

### 3. Test Run
```bash
python main.py
```

### 4. Schedule Weekly Runs
See `SETUP_INSTRUCTIONS.md` for Task Scheduler setup.

## Configuration

Edit `config.py` to customize:

### Website Configuration
```python
WEBSITE_CONFIG = {
    "syriacar": {
        "url": "https://syriacar.net/",
        "selectors": {
            "car_listings": "div.car-item",
            "title": "h2.car-title",
            "price": "span.price",
            # ... more selectors
        }
    }
}
```

### Schedule Configuration
```python
SCHEDULER_CONFIG = {
    "hour": 9,           # 9 AM
    "minute": 0,         # 00 minutes
    "day_of_week": "0-6", # Daily (or specific day like "mon")
}
```

## Usage

### Test Run (Dry Run)
```bash
python main.py
```
Shows what would be added without actually updating Google Sheets.

### Production Run
```python
from main import ScraperOrchestrator

orchestrator = ScraperOrchestrator(
    website_key="syriacar",
    spreadsheet_id="YOUR_SHEET_ID"
)
result = orchestrator.run(test_mode=False)
```

### Run Scheduler
```bash
python scheduler.py
```

### Scrape Single Website
```python
from scraper import CarScraper

scraper = CarScraper("syriacar")
cars = scraper.scrape()
```

## How It Works

1. **Scraping**: Selenium and BeautifulSoup extract car data from the website
2. **Image Download**: Images are downloaded and stored locally
3. **Deduplication**: New data is compared against existing sheets
4. **Upload**: Only new unique records are added to Google Sheets
5. **Logging**: All operations are logged with timestamps

## Data Collected

For each car, the scraper collects:
- **ID**: Unique identifier
- **Title**: Car name/model
- **Price**: Listing price
- **Description**: Additional details
- **Link**: Direct link to listing
- **Image Path**: Path to downloaded image
- **Website**: Source website
- **Scraped At**: Timestamp

## Deduplication

The scraper prevents duplicates by:
1. Checking unique ID
2. Comparing key fields (title, price)
3. Marking as duplicate if both match
4. Only adding truly new records to Google Sheets

## Logs

Logs are saved with timestamps:
- Location: `logs/scraper_YYYYMMDD_HHMMSS.log`
- Levels: INFO, WARNING, ERROR
- Contains: Scraping progress, duplicates found, upload status

## Troubleshooting

### Common Issues

**Q: No cars are being scraped**
- Check website selectors in `config.py`
- Verify website structure hasn't changed
- Inspect element to find correct CSS selectors

**Q: Images not downloading**
- Some websites block image downloads
- Check logs for specific errors
- Verify image URLs in browser

**Q: Google Sheets authentication fails**
- Verify credentials.json is in correct location
- Check service account has access to spreadsheet
- Regenerate credentials if needed

**Q: Duplicates still appearing**
- Check deduplication fields in config
- Verify ID field matches actual data
- Review logs to see deduplication process

## Adding New Websites

1. Update `config.py` with new website configuration
2. Inspect website HTML for correct selectors
3. Add new key to `WEBSITE_CONFIG`
4. Create new spreadsheet for website
5. Run scraper with new website key:

```python
orchestrator = ScraperOrchestrator(
    website_key="new_site",
    spreadsheet_id="NEW_SHEET_ID"
)
```

## API Integration

### Google Sheets API

The scraper uses Google Sheets API v4 for:
- Creating spreadsheets
- Reading existing data
- Appending new rows
- Formatting headers

### Selenium WebDriver

Uses Chrome WebDriver for:
- JavaScript rendering
- Dynamic content loading
- Image lazy-loading handling

## Performance

- **Typical scrape time**: 1-5 minutes (depends on website size)
- **Image download**: ~10-20 seconds (depends on image count)
- **Deduplication**: ~1-2 seconds
- **Google Sheets upload**: ~5-10 seconds

## Security

- Credentials stored locally (credentials.json)
- OAuth2 tokens are encrypted
- No sensitive data in logs
- User-Agent rotation support

## Limitations

- Requires JavaScript rendering (uses Selenium)
- Large image files may impact storage
- Rate limiting should be considered for large-scale use
- Website structure changes require selector updates

## Future Enhancements

- [ ] Proxy support
- [ ] CAPTCHA handling
- [ ] Distributed scraping
- [ ] Database backend option
- [ ] Email notifications
- [ ] Web dashboard
- [ ] Advanced filtering
- [ ] Multi-language support

## License

Private project - Internal use only

## Support

For issues or questions, check:
1. `SETUP_INSTRUCTIONS.md` - Detailed setup guide
2. `logs/` - Execution logs
3. Browser console - Website structure issues

---

Happy scraping! 🚀
