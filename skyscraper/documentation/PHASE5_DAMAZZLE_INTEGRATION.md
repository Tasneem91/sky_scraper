# Phase 5: Damazzle Website Integration - Complete Guide

**Status**: ✅ Implementation Complete  
**Date**: April 23, 2026  
**Duration**: 2-3 days  
**Complexity**: Medium

---

## 📋 Overview

Phase 5 implements scraping for **Damazzle Motors** (https://damazzle.com/motors/cars/search), a Syrian car marketplace. This phase demonstrates:
- Handling Angular-rendered HTML
- Pagination via URL parameters (?page=1, ?page=2, etc.)
- Extracting data in multiple languages (Arabic + English)
- Price parsing with currency conversions
- Multi-field data extraction

---

## 🏗️ Architecture

### Data Flow
```
Damazzle Website
    ↓
DamazzleScraper (pagination loop)
    ↓
BeautifulSoup HTML Parser
    ↓
Extract Fields (price, brand, year, mileage, etc.)
    ↓
Calculate Statistics
    ↓
Write to Google Sheets
    ↓
Store in Database
```

### Pagination Mechanism
```
Page 1: https://damazzle.com/motors/cars/search?page=1
Page 2: https://damazzle.com/motors/cars/search?page=2
Page 3: https://damazzle.com/motors/cars/search?page=3
... continues until no listings found
```

---

## 📁 Files Created/Modified

### New File: `scrapers/damazzle_scraper.py` (400+ lines)

**What It Does**:
1. **Initialization**: Sets up HTTP session with proper headers
2. **Pagination**: Automatically loops through pages (safety limit: 50 pages)
3. **Extraction**: Parses each car listing with BeautifulSoup
4. **Statistics**: Calculates aggregates (price avg/min/max, brand counts, year ranges)
5. **Robustness**: Handles missing data gracefully, logs errors

**Key Methods**:
- `scrape()` - Main loop that fetches all pages
- `_extract_listing()` - Parses a single car listing
- `_clean_price()` - Converts price strings to floats
- `_count_brands()` - Aggregates brand statistics
- `get_statistics()` - Generates summary statistics

### Modified File: `websites_config.json`

Added Damazzle configuration:
```json
{
  "id": "damazzle",
  "name": "Damazzle Motors",
  "description": "Car listings from damazzle.com/motors",
  "url": "https://damazzle.com/motors/cars/search",
  "type": "cars",
  "scraper_class": "DamazzleScraper",
  "scraper_file": "scrapers/damazzle_scraper.py",
  "google_sheet_id": "YOUR-DAMAZZLE-SHEET-ID-HERE",
  "enabled": false,
  "priority": 2
}
```

---

## 🔍 Extracted Fields

### From Each Car Listing:

| Field | Example | Location in HTML |
|-------|---------|-----------------|
| **price** | 17000 | `text-orange` div |
| **price_raw** | "17,000 $" | `text-orange` div |
| **brand** | فورد (Ford) | `bg-purple` span |
| **category** | سيارات (Cars) | `bg-purple` span |
| **year** | 2022 | `<li>` with calendar icon |
| **mileage** | "80,000-100,000كم" | `<li>` with Km icon |
| **title** | "فورد موستنج" | `product-title` h5 |
| **location** | "المزة - دمشق" | `text-muted` div |
| **posted_date** | "منذ يومان" | `text-muted` div |
| **ad_id** | "fwrd-mwstnj" | Button href attribute |
| **ad_url** | "https://damazzle.com/ads/..." | Constructed from ad_id |
| **scraped_at** | ISO timestamp | Generated |
| **source** | "damazzle.com" | Constant |

---

## 🚀 Setup & Configuration

### Step 1: Verify Scraper File
Ensure this file exists:
```
D:\skyscraper\scrapers\damazzle_scraper.py ✅
```

### Step 2: Create Google Sheet for Damazzle
1. Open Google Sheets
2. Create new spreadsheet: "Damazzle Motors - Syria"
3. Share with your service account email
4. Copy the Sheet ID
5. Update `websites_config.json`:
   ```json
   "google_sheet_id": "YOUR-ACTUAL-SHEET-ID"
   ```

### Step 3: Enable Damazzle in Admin Panel
*(Coming in Phase 2)*

Or manually in `websites_config.json`:
```json
"enabled": true
```

### Step 4: Install Dependencies
Ensure these are installed:
```bash
pip install requests beautifulsoup4
```

---

## 🧪 Testing Phase 5

### Manual Test (Command Line)

```python
from scrapers.damazzle_scraper import DamazzleScraper

# Create config
config = {
    'url': 'https://damazzle.com/motors/cars/search',
    'type': 'cars'
}

# Run scraper
scraper = DamazzleScraper(config)
items = scraper.scrape()

# Check results
print(f"Total items scraped: {len(items)}")
print(f"First item: {items[0] if items else 'No items'}")

# Check statistics
stats = scraper.get_statistics(items)
print(f"Statistics: {stats}")
```

### Test Checklist

- [ ] Scraper imports without errors
- [ ] Can fetch page 1 from Damazzle
- [ ] Extracts at least 10 items from page 1
- [ ] All extracted fields are populated (not empty)
- [ ] Pagination works (fetches multiple pages)
- [ ] Stops at last page gracefully
- [ ] Statistics calculated correctly
- [ ] Data written to Google Sheets successfully

### Expected Output

```
Starting Damazzle scraper for: https://damazzle.com/motors/cars/search
Scraping page 1
Extracted 12 items from page 1
Scraping page 2
Extracted 12 items from page 2
Scraping page 3
No listings found on page 3. Stopping.
Scraping complete. Total items: 24

Statistics:
{
  'total_items': 24,
  'price_stats': {
    'average': 18500.5,
    'min': 12000,
    'max': 25000,
    'count': 24
  },
  'year_stats': {
    'average': 2019,
    'min': 2010,
    'max': 2024,
    'count': 24
  },
  'brand_stats': {
    'فورد': 5,
    'تويوتا': 4,
    'BMW': 3,
    ...
  }
}
```

---

## 🔧 Scraper Features

### Robust Pagination
- **Automatic page detection**: Stops when no items found
- **Safety limit**: Max 50 pages (configurable)
- **Error handling**: Continues on single-page errors, stops on critical failures

### Smart Data Extraction
- **Price parsing**: Removes currency symbols, handles decimals
- **Year detection**: Uses regex to find 4-digit year
- **Mileage extraction**: Handles Arabic text (كم) and English (km)
- **Missing data**: Doesn't crash if fields missing, sets to `None`

### Statistics Generation
- **Price analytics**: Average, min, max prices
- **Year ranges**: Distribution of car ages
- **Brand aggregation**: Count of vehicles by brand
- **Data completeness**: Tracks items with all fields

### Error Handling
- Logs warnings for failed extractions
- Continues scraping on single-item errors
- Reports network errors with context
- Safe timeouts (10 seconds per page)

---

## 📊 Integration with Google Sheets

The scraper outputs are compatible with the existing `write_to_google_sheets()` function in `app.py`.

**Headers created in Google Sheet**:
```
price | price_raw | brand | category | year | mileage | title | location | posted_date | ad_id | ad_url | scraped_at | source
```

**Data preservation**:
- Existing data NOT cleared (append mode)
- Timestamps included for tracking
- Source field identifies data origin

---

## 🎯 Success Criteria - Phase 5 Complete

You'll know Phase 5 is complete when:

✅ `scrapers/damazzle_scraper.py` exists and imports successfully  
✅ DamazzleScraper class initializes with config dict  
✅ `scrape()` method returns list of dictionaries  
✅ At least 10+ items extracted from page 1  
✅ All fields extracted (price, brand, year, title, etc.)  
✅ Pagination works (multiple pages fetched)  
✅ Statistics calculated without errors  
✅ Data written to Google Sheet successfully  
✅ Website config updated with damazzle entry  

---

## 🚨 Common Issues & Fixes

### Issue: "unable to connect to damazzle.com"
**Cause**: Website blocking requests  
**Fix**: Check User-Agent header (already in scraper), try from different IP, check if site is up

### Issue: "No listings found on page 1"
**Cause**: HTML structure changed, or page requires JavaScript rendering  
**Fix**: Check if website uses client-side rendering (Angular), may need Selenium

### Issue: "Price is None for all items"
**Cause**: Price CSS selector changed  
**Fix**: Update `_extract_listing()` method with new selector

### Issue: "Only scraping 1 page then stopping"
**Cause**: All pages return same content, or pagination broken  
**Fix**: Manually check page 2 URL in browser, verify ?page=2 works

---

## 🔄 Next: Phase 6

Once Phase 5 is complete, proceed to **Phase 6: Final Polish & Documentation**:
- Admin panel for managing websites
- Advanced statistics visualizations
- Complete setup guide
- Performance optimization
- Security audit

---

## 📝 Technical Details

### HTTP Session Management
```python
self.session = requests.Session()
self.session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)...'
})
```

### BeautifulSoup Parsing
```python
soup = BeautifulSoup(response.content, 'html.parser')
listings = soup.find_all('div', class_='col-md-6')
```

### Regex Patterns
- **Year**: `r'(\d{4})'` - Captures any 4-digit number
- **Price cleanup**: `r'[^\d.]'` - Keeps only digits and decimal points
- **Ad ID**: `r'/ads/([^&?]+)'` - Extracts ID from URL path

### Error Handling
```python
try:
    # Extract data
except RequestException as e:
    logger.error(f"Network error: {e}")
    break
except Exception as e:
    logger.warning(f"Extraction error: {e}")
    continue
```

---

## 📞 Support

**For debugging**:
1. Check logs: Look for "Damazzle" in log files
2. Verify HTML structure: Right-click car listing → Inspect
3. Test regex patterns: Use https://regex101.com/
4. Check Google Sheets: Verify data written successfully

**For modifications**:
- Edit `_extract_listing()` to add new fields
- Edit `_clean_price()` for different price formats
- Adjust `max_pages` limit in `scrape()` method
- Modify selectors in `_extract_listing()` if HTML changes

---

**Phase 5 Status**: ✅ **COMPLETE & READY FOR TESTING**

Now proceed to **test the scraper** with the steps above, then we'll move to Phase 6!
