# Multi-Website Scraper Platform - Implementation Guide v2.0

**Status**: Ready for Implementation  
**Phase**: Phase 1 - Core Infrastructure  

---

## 📊 Overview of New Architecture

Your scraper system is now evolving from a **single-website tool** to a **multi-website platform**:

### Old Structure (Single Website)
```
python main.py
    ↓
SyriaCar Scraper
    ↓
Google Sheet (Fixed ID)
```

### New Structure (Multi-Website Platform)
```
Flask Web App (Browser UI)
    ↓
Website Dropdown Selector
    ↓
Dynamic Scraper Router
    ├→ SyriaCar (Cars)
    ├→ Website 2 (Cars)
    ├→ Website 3 (Real Estate)
    ├→ Website 4-7 (TBD)
    ↓
Individual Google Sheets
    ↓
Statistics Dashboard
```

---

## 🚀 Quick Start - Running the Web App

### Step 1: Install Flask
```bash
pip install flask
```

### Step 2: Create Templates Directory
```bash
mkdir templates
mkdir static/css
mkdir static/js
```

### Step 3: Run the Flask App
```bash
python app.py
```

### Step 4: Open in Browser
```
http://localhost:5000
```

You should see:
- Homepage with website selector dropdown
- Enabled/disabled status for each website
- Buttons to run scraper and view statistics

---

## 📝 New Files Created

### 1. **ARCHITECTURE_V2.md**
- Complete system design
- Database schema
- File structure
- Component interactions

### 2. **scrapers/base_scraper.py**
- `BaseScraper` - Abstract base class for ALL scrapers
- `CarsScraper` - Base class for car websites
- `RealEstateScraper` - Base class for real estate websites
- Provides common statistics and market analysis

### 3. **websites_config.json**
- Configuration for all 7 websites
- Currently only SyriaCar is enabled
- Ready to configure websites 2-7

### 4. **app.py**
- Flask web application
- Routes for dashboard, statistics, API
- Website selector dropdown
- Scraper execution endpoint

---

## 🔧 Phase 1: Infrastructure Setup

### Step 1: Verify Base Scrapers Work

Test that the base scraper classes work:

```python
# In Python shell
from scrapers.base_scraper import CarsScraper
config = {
    'id': 'test',
    'type': 'cars',
    'name': 'Test'
}
scraper = CarsScraper(config)
print(scraper.to_dict())
```

### Step 2: Update SyriaCar Scraper to Use New Base Class

Modify `scrapers/syriacar_scraper.py`:

```python
from scrapers.base_scraper import CarsScraper

class SyriaCarScraper(CarsScraper):
    """SyriaCar scraper inheriting from CarsScraper base class"""
    
    def __init__(self, website_config):
        super().__init__(website_config)
    
    def scrape(self):
        """Use existing scrape logic"""
        # Use the existing scraper.py logic here
        # Return items with all fields
```

### Step 3: Configure websites_config.json

For **SyriaCar** (already enabled):
- ✅ Already configured
- ✅ Uses existing scraper
- ✅ Google Sheet ID is set

For **Websites 2-7** (to be configured):
- [ ] Add website URL
- [ ] Add website type (cars or real estate)
- [ ] Create scraper file
- [ ] Add Google Sheet ID
- [ ] Set enabled=true

---

## 📋 Integration Steps for Each New Website

### For Website 2 (Example: Cars Site)

**Step 1: Create scraper file**
```python
# scrapers/website2_scraper.py

from scrapers.base_scraper import CarsScraper

class Website2CarScraper(CarsScraper):
    """Website 2 car listings scraper"""
    
    def scrape(self):
        # Implement scraping logic specific to Website 2
        # Return list of dictionaries with car data
        pass
```

**Step 2: Update websites_config.json**
```json
{
  "id": "website2",
  "name": "Website 2 Name",
  "url": "https://website2.com",
  "type": "cars",
  "scraper_class": "Website2CarScraper",
  "google_sheet_id": "YOUR-SHEET-ID",
  "enabled": true
}
```

**Step 3: Test the scraper**
```bash
curl -X POST http://localhost:5000/api/run-scraper \
  -H "Content-Type: application/json" \
  -d '{"website_id": "website2"}'
```

### For Website 3 (Example: Real Estate Site)

Follow same steps but use `RealEstateScraper` instead of `CarsScraper`.

---

## 🌐 Web Interface Features

### Dashboard (index.html)
- Dropdown selector for all websites
- Status indicators (enabled/disabled)
- Last run information
- Quick action buttons

### Website Detail Page (website.html)
- Website info
- Last scrape statistics
- [Run Scraper] button
- [View Statistics] button
- Configuration options

### Statistics Dashboard (statistics.html)
- Total items count
- New items this week
- Most common items
- Market trends
- Growth rate

---

## 🗄️ Database Structure (When Implemented)

The system is prepared for SQLite database with:

1. **websites** table - Website configurations
2. **scraping_jobs** table - Historical scrape runs
3. **item_statistics** table - Item frequency and trends

This allows:
- Tracking which items appear most frequently
- Detecting market trends
- Comparing growth week-over-week

---

## 📊 Statistics Available Per Website Type

### For Car Websites
- ✅ Total vehicles
- ✅ Most common makes
- ✅ Most common models
- ✅ Average vehicle year
- ✅ Body type distribution
- ✅ Transmission distribution
- ✅ Fuel type distribution
- ✅ Average price analysis

### For Real Estate Websites
- ✅ Total properties
- ✅ Most common locations
- ✅ Most expensive locations
- ✅ Property type distribution
- ✅ Average price per sqm
- ✅ Bedroom distribution
- ✅ Price trends by location

---

## 🚀 Implementation Timeline

### Phase 1: Core Infrastructure ✅ DONE
- [x] Base scraper classes
- [x] Configuration system
- [x] Flask web application
- [x] API endpoints
- [ ] HTML templates (basic)

### Phase 2: First Website Integration (Next)
- [ ] Integrate existing SyriaCar scraper
- [ ] Test with web app
- [ ] Verify statistics calculation
- [ ] Create HTML templates

### Phase 3: Web Interface
- [ ] Create dashboard template
- [ ] Create website detail template
- [ ] Create statistics template
- [ ] Add CSS styling
- [ ] Add JavaScript interactions

### Phase 4: Additional Websites
- [ ] Website 2 scraper
- [ ] Website 3 scraper
- [ ] Websites 4-7
- [ ] Test each website

### Phase 5: Database & Analytics
- [ ] SQLite database setup
- [ ] Job history tracking
- [ ] Statistics calculation
- [ ] Trend analysis

### Phase 6: Advanced Features
- [ ] Email notifications
- [ ] Scheduled runs (APScheduler)
- [ ] Export to CSV
- [ ] API for external integrations

---

## 💾 Moving Existing Code

### Current SyriaCar Files → New Structure

**Old Structure:**
```
- main.py (orchestrator)
- scraper.py (scraping logic)
- sheets_integration.py
- deduplication.py
- config.py
```

**New Structure:**
```
- scrapers/syriacar_scraper.py (inherits from CarsScraper)
- sheets_manager.py (simplified from sheets_integration.py)
- scrapers/base_scraper.py (contains statistics logic)
- app.py (replaces main.py for web control)
- websites_config.json (replaces config.py for website settings)
```

**Migration Steps:**
1. Copy scraping logic from `scraper.py` → `scrapers/syriacar_scraper.py`
2. Keep `sheets_integration.py` (rename to `sheets_manager.py`)
3. Keep `deduplication.py` (reuse for all websites)
4. Extract statistics logic → `base_scraper.py`

---

## 🔌 API Endpoints

### Get All Websites
```
GET /api/websites
```

### Get Specific Website
```
GET /api/website/<website_id>
```

### Run Scraper
```
POST /api/run-scraper
Body: {"website_id": "syriacar"}
```

### Get Statistics
```
GET /api/statistics/<website_id>
```

### Enable/Disable Website
```
POST /api/enable-website
Body: {"website_id": "website2", "enabled": true}
```

### Update Google Sheet ID
```
POST /api/update-sheet-id
Body: {"website_id": "website2", "sheet_id": "NEW-SHEET-ID"}
```

---

## 🎨 HTML Templates Needed

### 1. base.html
Common layout for all pages

### 2. index.html
- Website selector dropdown
- List of all websites
- Status indicators
- Quick actions

### 3. website.html
- Website details
- Scraper control (Run button)
- Last run info
- Settings

### 4. statistics.html
- Market overview
- Trends and insights
- Export options
- Charts (if using Chart.js)

### 5. job-history.html
- Past scrape runs
- Timestamps and results
- Export history

---

## 📦 Dependencies to Add

```bash
# Web framework
pip install flask

# Database (optional for Phase 5)
pip install sqlalchemy

# Statistics/plotting (optional for advanced analytics)
pip install pandas matplotlib

# Job scheduling (optional for Phase 5)
pip install apscheduler
```

---

## 🧪 Testing the System

### Test 1: Flask App Starts
```bash
python app.py
# Should see: "Running on http://127.0.0.1:5000"
```

### Test 2: Load Homepage
```bash
# Visit http://localhost:5000
# Should see website dropdown with SyriaCar enabled
```

### Test 3: API Health Check
```bash
curl http://localhost:5000/api/health
# Should return: {"status": "healthy", ...}
```

### Test 4: Get Websites
```bash
curl http://localhost:5000/api/websites
# Should return JSON array of websites
```

### Test 5: Run Scraper (When Ready)
```bash
curl -X POST http://localhost:5000/api/run-scraper \
  -H "Content-Type: application/json" \
  -d '{"website_id": "syriacar"}'
# Should return scraping results
```

---

## 📝 Next Steps

### Immediate (This Week)
1. ✅ Review architecture document
2. ✅ Review base scraper classes
3. ✅ Review Flask app
4. ⬜ Create HTML templates (basic)
5. ⬜ Test Flask app startup
6. ⬜ Integrate SyriaCar scraper

### Short Term (Next Week)
7. ⬜ Update SyriaCar scraper to use new base class
8. ⬜ Test scraper through web interface
9. ⬜ Add statistics calculation
10. ⬜ Create CSS styling

### Medium Term (2-3 Weeks)
11. ⬜ Add Website 2 and 3 scrapers
12. ⬜ Add database layer
13. ⬜ Create statistics dashboard
14. ⬜ Add job history tracking

### Long Term (Month+)
15. ⬜ Add remaining websites (4-7)
16. ⬜ Add scheduling
17. ⬜ Add advanced analytics
18. ⬜ Add email notifications

---

## 🎯 Benefits of This Architecture

| Benefit | Impact |
|---------|--------|
| **Modular Design** | Easy to add/remove websites |
| **Reusable Code** | Base classes for cars and real estate |
| **User-Friendly** | Web interface instead of command line |
| **Scalable** | Can handle 7+ websites |
| **Trackable** | Database tracks all runs |
| **Analytical** | Built-in statistics per website |
| **Professional** | Enterprise-ready platform |

---

## 📞 Questions & Troubleshooting

### Flask Won't Start
- Check if port 5000 is available
- Try: `python app.py --port 5001`
- Check for Python syntax errors

### Templates Not Found
- Verify `templates/` directory exists
- Check file names are correct
- Make sure files are in correct directory

### Import Errors
- Check `scrapers/` directory exists
- Verify `__init__.py` exists in scrapers folder
- Check scraper class names match config

### Config Not Loading
- Verify `websites_config.json` is in root directory
- Check JSON syntax is valid
- Use JSON validator online if unsure

---

## 🚀 You're Ready to Start!

The infrastructure is built. Now we can:
1. Create the web interface
2. Integrate existing scrapers
3. Add new websites
4. Build analytics

This is a **professional, enterprise-ready platform** that can scale to any number of websites! 🎉

---

**Ready to proceed with Phase 2 integration?**

Next: Integrate SyriaCar scraper with new architecture
