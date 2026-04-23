# SyriaCar Web Scraper - Complete Project Documentation

**Version**: 2.0  
**Status**: Production Ready with Enhanced Data Extraction  
**Last Updated**: April 2026  

---

## 📋 Table of Contents

1. [Project Overview](#project-overview)
2. [Architecture & Data Flow](#architecture--data-flow)
3. [Features](#features)
4. [System Requirements](#system-requirements)
5. [Data Structure](#data-structure)
6. [HTML Structure Analysis](#html-structure-analysis)
7. [Implementation Details](#implementation-details)
8. [Usage Guide](#usage-guide)
9. [Troubleshooting](#troubleshooting)

---

## 📊 Project Overview

This is a **complete, production-ready web scraper** for syriacar.net that:

- **Scrapes 1000+ cars** from listing pages using Selenium and BeautifulSoup
- **Extracts comprehensive data** from both listing and detail pages
- **Downloads all car images** and stores them locally with proper linking
- **Automatically deduplicates** entries based on ID and field comparison
- **Updates Google Sheets** with new cars only (no duplicates)
- **Schedules weekly runs** using Windows Task Scheduler or APScheduler
- **Provides comprehensive logging** for debugging and monitoring

### What Problem Does It Solve?

SyriaCar.net has:
- ✅ **1000+ cars** listed but no easy way to export data
- ✅ **No API** available for bulk data access
- ✅ **Dynamic JavaScript** rendering that requires Selenium
- ✅ **Infinite scroll** pagination instead of traditional pages
- ✅ **Multiple detail pages** with comprehensive specifications

This scraper automates the collection of this data into a **structured Google Sheet**.

---

## 🏗️ Architecture & Data Flow

```
┌─────────────────────────────────────────────────────────────┐
│                      Main Orchestrator                      │
│                    (main.py - Runs weekly)                  │
└────────────────────┬────────────────────────────────────────┘
                     │
         ┌───────────┴──────────┬──────────────┐
         │                      │              │
         ▼                      ▼              ▼
   ┌──────────────┐      ┌────────────┐  ┌─────────────┐
   │   Scraper    │      │ Sheets API │  │ Deduplicator│
   │ (scraper.py) │      │ (sheets.py)│  │ (dedup.py)  │
   └──────────────┘      └────────────┘  └─────────────┘
         │
         └──────────────────────┬──────────────────────┐
                                │                      │
                    ┌───────────┴──────────┐  ┌────────┴─────────┐
                    │                      │  │                  │
                    ▼                      ▼  ▼                  ▼
             [Listing Page]        [Image Downloads]  [Detail Pages]
          (infinite scroll)         (local storage)    (specs extraction)
             1000+ cars
```

### 4-Step Process

**Step 1: Scraping** (`CarScraper.scrape()`)
- Opens browser with Selenium
- Scrolls through entire listing page
- Extracts car data from each card
- Optionally fetches detail pages for comprehensive specs
- Downloads and links images

**Step 2: Deduplication** (`Deduplicator.find_duplicates()`)
- Loads existing Google Sheet data
- Compares new scraped data against existing records
- Identifies unique cars vs. duplicates
- Returns only new, unique records

**Step 3: Google Sheets Update** (`GoogleSheetsManager.append_rows()`)
- Appends unique cars to existing sheet
- Formats headers
- Links images in spreadsheet
- Maintains data integrity

**Step 4: Scheduling** (`Windows Task Scheduler` or `APScheduler`)
- Runs scraper weekly (e.g., every Monday at 9 AM)
- Completely automated with no manual intervention
- Logs all runs for monitoring

---

## ✨ Features

### Core Functionality
✅ **Web Scraping**
- Selenium WebDriver for JavaScript rendering
- BeautifulSoup for HTML parsing
- Infinite scroll detection and auto-loading
- Smart selector detection (multiple fallbacks)

✅ **Data Extraction**
- Listing page: title, price, make, model, year, mileage, location, fuel type, transmission, condition, origin, image URL
- Detail page: comprehensive specifications from accordion sections
- Automatic field parsing from pipe-delimited description text
- JSON-LD structured data extraction (optional)

✅ **Image Management**
- Automatic download and local storage
- Multiple image URLs per car
- Google Sheets image linking
- Fallback image handling
- WebP/PNG/JPG format support

✅ **Data Management**
- Smart deduplication (ID-based and field comparison)
- Prevents duplicate entries on re-runs
- Field-by-field comparison for identifying changes
- Detailed duplicate logging

✅ **Google Sheets Integration**
- OAuth2 authentication
- Service Account credentials support
- Automatic header creation
- Image URL embedding
- Spreadsheet creation and management
- Data formatting and styling

✅ **Automation & Scheduling**
- Weekly scheduled runs via Windows Task Scheduler
- APScheduler for cross-platform scheduling
- Comprehensive logging per run
- Error handling and recovery
- Email notifications (optional)

✅ **Monitoring & Logging**
- Detailed logs for every scrape run
- Timestamps and operation tracking
- Error reporting with stack traces
- Success/failure summaries
- Performance metrics

---

## 🖥️ System Requirements

### Hardware
- **RAM**: 2GB minimum (4GB recommended for 1000+ cars)
- **Storage**: 500MB minimum for images (1000+ cars)
- **CPU**: Dual-core processor minimum
- **Internet**: Stable broadband connection

### Software
- **Python**: 3.8 or higher
- **Browser**: Google Chrome (for Selenium)
- **OS**: Windows 10+ (for Task Scheduler) or Linux/Mac (for APScheduler)
- **Google Account**: For Google Sheets API access

### Python Dependencies
```
selenium>=4.0.0           # Web browser automation
beautifulsoup4>=4.9.0     # HTML parsing
requests>=2.26.0          # HTTP requests
google-auth>=2.0.0        # Google API authentication
google-auth-oauthlib>=0.4.0
google-auth-httplib2>=0.1.0
google-api-python-client>=2.0.0
apscheduler>=3.8.0        # Job scheduling
python-dotenv>=0.19.0     # Environment variable management
webdriver-manager>=3.8.0  # ChromeDriver management
```

---

## 📊 Data Structure

### Listing Page Data (Always Extracted)

```json
{
  "id": "syriacar_1_1713792000",
  "title": "كيا Kia",
  "price": "السعر 17,000 دولار",
  "make": "Kia",
  "model": "Sportage",
  "year": "2017",
  "mileage": "225,000 كم",
  "body_type": "إس يو في",
  "location": "حلب",
  "fuel_type": "بنزين",
  "transmission": "أوتوماتيك",
  "condition": "مستعملة",
  "origin": "أمريكية",
  "image_url": "https://syriacar.net/storage/cars-small/...",
  "image_path": "D:\\skyscraper\\images\\syriacar\\car_1_1713792000.webp",
  "link": "https://syriacar.net/car/details/kia-sportage-2017-hlb-12264",
  "description": "كيا Kia | Sportage | إس يو في | 2017 | 225,000 كم | حلب | بنزين | أمريكية | أوتوماتيك | مستعملة",
  "website": "syriacar",
  "scraped_at": "2026-04-22T14:30:00.000000"
}
```

### Detail Page Data (Optional - when fetch_details=True)

```json
{
  "spec_0": "Make: Kia",
  "spec_1": "Model: Sportage",
  "spec_2": "Year: 2017",
  "make": "Kia",
  "model": "Sportage",
  "year": "2017",
  "engine_capacity": "1600 CC",
  "engine_power": "121 HP",
  "transmission": "أوتوماتيك",
  "fuel_type": "بنزين",
  "body_type": "إس يو في",
  "doors": "4",
  "seats": "5",
  "condition": "مستعملة",
  "exterior_color": "أبيض",
  "interior_color": "بني"
}
```

### Google Sheets Structure

| id | title | price | make | model | year | mileage | body_type | location | fuel_type | transmission | condition | origin | image_url | link | scraped_at | website |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| syriacar_1_... | كيا Kia | السعر 17,000 دولار | Kia | Sportage | 2017 | 225,000 كم | إس يو في | حلب | بنزين | أوتوماتيك | مستعملة | أمريكية | [Image](url) | [Link](url) | 2026-04-22 | syriacar |

---

## 🔍 HTML Structure Analysis

### Listing Page Card Structure

```html
<div class="car-card">
  <div class="card-image">
    <!-- Multiple images with src -->
    <img src="https://syriacar.net/storage/cars-small/..." alt="...">
    
    <!-- Detail page link in data-link attribute -->
    <button class="sharing share-button" 
            data-link="https://syriacar.net/car/details/kia-sportage-2017-hlb-12264">
  </div>
  
  <div class="card-info">
    <!-- Title and basic info -->
    <div class="border-div-title-card-info">
      <h1 class="car-title">كيا Kia</h1>
      <h2 class="car-sub-title">Sportage • إس يو في • 2017</h2>
    </div>
    
    <!-- Features/specs -->
    <div class="features">
      <div class="features-a">
        <!-- Mileage -->
        <div>225,000 <span class="km">كم</span></div>
        <!-- Location -->
        <div>حلب</div>
      </div>
      <div class="features-b">
        <!-- Fuel type -->
        <div>بنزين</div>
        <!-- Origin -->
        <div>أمريكية</div>
      </div>
      <div class="features-c">
        <!-- Transmission -->
        <div>أوتوماتيك</div>
        <!-- Condition -->
        <div>مستعملة</div>
      </div>
    </div>
  </div>
  
  <!-- Price button -->
  <div class="new-card-contact">
    <button class="btn-contact-p" id="request-price">
      السعر 17,000 دولار
    </button>
  </div>
</div>
```

### Key CSS Selectors

| Element | Selector | Content |
|---------|----------|---------|
| Car Card | `div.car-card` | Entire listing card |
| Title | `h1.car-title` | Brand (كيا Kia) |
| Subtitle | `h2.car-sub-title` | Model • Body • Year |
| Price | `button.btn-contact-p` | Price text |
| Mileage | `div.features-a` | Distance in كم |
| Location | `div.features-a span` | City name |
| Fuel | `div.features-b` (first) | Fuel type |
| Origin | `div.features-b` (second) | Country/origin |
| Transmission | `div.features-c` (first) | Auto/Manual |
| Condition | `div.features-c` (second) | Used/New |
| Detail Link | `button.share-button[data-link]` | URL to detail page |
| Images | `img` in card-image | Multiple images |

### Detail Page Structure (When Enabled)

```html
<li class="li-1-details-color">
  <!-- Each spec item -->
  <span>Make: Kia</span>
</li>

<!-- Accordion sections -->
<div class="accordion-content-details">
  <!-- Technical specs in accordion format -->
</div>
```

---

## ⚙️ Implementation Details

### File Structure

```
D:\skyscraper\
├── config.py                    # Configuration (selectors, settings)
├── scraper.py                  # Main scraping logic
├── sheets_integration.py        # Google Sheets API integration
├── deduplication.py            # Duplicate detection
├── main.py                     # Orchestrator (main entry point)
├── scheduler.py                # APScheduler setup
├── requirements.txt            # Python dependencies
├── credentials.json            # Google API credentials (NOT in git)
├── .gitignore                  # Git ignore rules
├── README.md                   # Quick start guide
├── SETUP_INSTRUCTIONS.md       # Detailed setup
├── DEPLOYMENT_GUIDE.md         # Production deployment
└── logs/                       # Scraper logs
    └── scraper_20260422_143000.log
```

### Key Python Classes

#### CarScraper (scraper.py)
- **`__init__(website_key)`** - Initialize scraper
- **`_init_driver()`** - Setup Selenium WebDriver
- **`scrape_syriacar()`** - Main scraping method
- **`_extract_car_data(item, index, fetch_details)`** - Extract from listing card
- **`_parse_car_description(text)`** - Parse pipe-delimited description
- **`_extract_detail_page_specs(url)`** - Get detail page specs
- **`_is_year(text)`**, **`_is_mileage(text)`**, **`_is_body_type(text)`** - Field validation

#### GoogleSheetsManager (sheets_integration.py)
- **`__init__()`** - Initialize with credentials
- **`create_sheet(title)`** - Create new spreadsheet
- **`append_rows(rows)`** - Add data to sheet
- **`get_all_data()`** - Retrieve existing data
- **`format_header()`** - Apply formatting to header row

#### Deduplicator (deduplication.py)
- **`__init__(existing_data, headers)`** - Initialize with existing data
- **`find_duplicates(new_data)`** - Identify unique vs. duplicate cars
- **`_is_duplicate(new_car, existing_car)`** - Compare two records
- **`prepare_data_for_sheets(cars, headers)`** - Format for Google Sheets

#### ScraperOrchestrator (main.py)
- **`run(test_mode)`** - Execute full pipeline
- **`scrape_website()`** - Run scraper
- **`update_sheets(test_mode)`** - Update Google Sheets
- **`_generate_headers()`** - Auto-generate column headers

---

## 🚀 Usage Guide

### Quick Start

1. **Install Dependencies**
   ```bash
   cd D:\skyscraper
   pip install -r requirements.txt
   ```

2. **Setup Google API Credentials**
   - Follow SETUP_INSTRUCTIONS.md Step 2
   - Save `credentials.json` to D:\skyscraper\

3. **Test the Scraper**
   ```bash
   python main.py
   ```
   - Runs in test mode (no actual sheet update)
   - Should show "Successfully scraped X cars"

4. **Production Run**
   ```python
   # In main.py, change:
   test_mode=False
   # And update SPREADSHEET_ID with your actual sheet ID
   
   python main.py
   ```

5. **Schedule Weekly Runs**
   - Follow DEPLOYMENT_GUIDE.md for Windows Task Scheduler setup
   - Or use `python scheduler.py` for APScheduler

### Configuration Options

Edit `config.py`:

```python
# Scraping settings
SCRAPER_CONFIG = {
    "headless": True,              # Run browser in headless mode
    "user_agent": "Mozilla/5.0...", # User agent string
    "timeout": 10,                 # Request timeout in seconds
    "max_scrolls": 50,             # Max scroll attempts
}

# Website specific settings
WEBSITE_CONFIG = {
    "syriacar": {
        "url": "https://syriacar.net",
        "image_folder": "images/syriacar",
        "selectors": { ... }       # CSS selectors
    }
}

# Deduplication settings
DEDUP_CONFIG = {
    "match_by_id_first": True,     # Check ID before field comparison
    "min_matching_fields": 5,      # Minimum fields to match for duplicate
}
```

---

## 🔧 Troubleshooting

### "No cars are being scraped (0 returned)"
- **Cause**: Wrong CSS selectors or page structure changed
- **Solution**: 
  1. Check `page_source.html` for actual HTML structure
  2. Update selectors in `config.py`
  3. Run `python main.py` again

### "All fields showing 'N/A'"
- **Cause**: Parsing logic not finding HTML elements correctly
- **Solution**:
  1. Verify HTML structure matches expected format
  2. Check CSS selector paths
  3. Enable debug logging (`logger.debug()`)

### "Google Sheets authentication fails"
- **Cause**: Invalid or missing credentials.json
- **Solution**:
  1. Re-download credentials from Google Cloud Console
  2. Save as `D:\skyscraper\credentials.json`
  3. Ensure file has correct permissions

### "Images not downloading"
- **Cause**: Network timeout or incorrect image URLs
- **Solution**:
  1. Check image URLs in HTML
  2. Increase timeout in `config.py`
  3. Check disk space (500MB+ for 1000+ cars)

### "ChromeDriver errors"
- **Cause**: Incompatible Chrome version
- **Solution**:
  1. Update Google Chrome to latest version
  2. Remove `~/.wdm/drivers/chromedriver` folder
  3. Re-run scraper (will download correct version)

### "Duplicate detection not working"
- **Cause**: Fields not matching or dedup rules too strict
- **Solution**:
  1. Check DEDUP_CONFIG in config.py
  2. Adjust `min_matching_fields`
  3. Review duplicate logic in deduplication.py

---

## 📈 Performance Metrics

### Timing Expectations

| Operation | Time | Notes |
|-----------|------|-------|
| Fast listing (1000 cars) | ~30-60 sec | Listing data only |
| With images download | ~5-10 min | Depends on image sizes |
| Detail page fetch (1 car) | 5-10 sec | ~5+ hours for 1000 cars |
| Google Sheets update | 10-30 sec | Depends on sheet size |
| **Total run (test)** | ~10 min | Listing + images |

### Optimization Tips

1. **Run in headless mode** - Set `headless: True`
2. **Disable images initially** - Set `fetch_details: False`
3. **Use detail pages selectively** - Only for new cars
4. **Schedule at off-peak hours** - Reduces server load
5. **Monitor memory usage** - Clear browser cache regularly

---

## 📝 Logging & Monitoring

### Log Location
`D:\skyscraper\logs\scraper_YYYYMMDD_HHMMSS.log`

### Log Format
```
2026-04-22 14:30:00 - scraper - INFO - Scraping https://syriacar.net
2026-04-22 14:30:10 - scraper - INFO - Waiting for JavaScript to render content...
2026-04-22 14:30:20 - scraper - INFO - Scroll 1: Page height = 5000
...
2026-04-22 14:32:00 - scraper - INFO - Successfully scraped 1205 cars
```

### Monitoring Commands
```bash
# View recent logs
type D:\skyscraper\logs\*.log | tail -50

# Check if process is running
tasklist | find "python"

# Check scheduled tasks
tasklist /v | find "Task Scheduler"
```

---

## 🔒 Security Considerations

1. **Credentials**: Never commit `credentials.json` to git
2. **Passwords**: Use environment variables, not hardcoded
3. **Data**: Encrypt sensitive fields in Google Sheets if needed
4. **Rate Limiting**: Add delays to avoid overloading server
5. **User Agent**: Always use realistic user agent strings
6. **Proxies**: Use proxy services if IP blocking occurs

---

## 📞 Support & Maintenance

### Regular Maintenance Tasks

- **Weekly**: Monitor logs for errors
- **Monthly**: Update Python dependencies (`pip install --upgrade -r requirements.txt`)
- **Quarterly**: Review and update CSS selectors (website changes)
- **Annually**: Update Chrome browser and ChromeDriver

### When Website Changes

1. Inspect website with developer tools
2. Identify new HTML structure
3. Update CSS selectors in `config.py`
4. Test with `python main.py` (test_mode=True)
5. Verify data extraction works
6. Deploy to production

---

## 📄 License & Attribution

This scraper is built for educational and personal use. Ensure you comply with:
- SyriaCar.net Terms of Service
- Website's `robots.txt`
- Local data protection regulations (GDPR, etc.)
- Rate limiting and responsible scraping practices

---

**Created**: April 2026  
**Maintained**: Open to community contributions  
**Status**: ✅ Production Ready
