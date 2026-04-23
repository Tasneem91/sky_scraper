# Multi-Website Scraper Platform - Architecture v2.0

**Status**: Planning Phase  
**Target**: 7 websites (cars + real estate)  
**Tech Stack**: Python + Flask + SQLite + Google Sheets API

---

## 📋 System Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                    Web Application (Flask)                       │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  Dashboard          │ Scraper Control  │ Statistics       │  │
│  │  - Website Selector │ - Run Scraper    │ - Market Trends  │  │
│  │  - Job History      │ - Monitor Status │ - Top Items      │  │
│  │  - Statistics       │ - View Results   │ - Growth Analysis│  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                             │
                ┌────────────┼────────────┐
                │            │            │
                ▼            ▼            ▼
        ┌─────────────┐ ┌──────────┐ ┌──────────┐
        │  Database   │ │  Config  │ │ Analytics│
        │  (SQLite)   │ │  System  │ │ Engine   │
        └─────────────┘ └──────────┘ └──────────┘
                │
    ┌───────────┼───────────┬──────────────┐
    │           │           │              │
    ▼           ▼           ▼              ▼
┌────────┐ ┌────────┐ ┌─────────┐ ┌────────────┐
│ Cars   │ │ Real   │ │ Google  │ │ Scraping   │
│Scrapers│ │Estate  │ │ Sheets  │ │ History    │
│        │ │Scrapers│ │ Manager │ │ & Stats    │
└────────┘ └────────┘ └─────────┘ └────────────┘
    │           │
    ├─Website 1 ├─Website 4
    ├─Website 2 ├─Website 5
    ├─Website 3 ├─Website 6
    └─Website 7
```

---

## 📁 Proposed File Structure

```
D:\skyscraper\
│
├── app.py                          # Flask web application
├── config.py                       # Global configuration
├── requirements.txt                # Dependencies
├── sqlite_db.py                    # Database models & operations
│
├── scrapers/                       # Modular scrapers
│   ├── __init__.py
│   ├── base_scraper.py            # Base class for all scrapers
│   ├── cars_scraper.py            # Base for car websites
│   ├── realestate_scraper.py      # Base for real estate websites
│   │
│   ├── syriacar_scraper.py        # Website 1: SyriaCar (cars)
│   ├── autotrader_scraper.py      # Website 2: Example (cars)
│   ├── syriaproperty_scraper.py   # Website 3: Example (real estate)
│   ├── website4_scraper.py        # Website 4
│   ├── website5_scraper.py        # Website 5
│   ├── website6_scraper.py        # Website 6
│   └── website7_scraper.py        # Website 7
│
├── templates/                      # HTML templates
│   ├── base.html                  # Base template
│   ├── index.html                 # Dashboard/selector
│   ├── scraper_control.html       # Scraper execution
│   ├── statistics.html            # Analytics dashboard
│   └── job_history.html           # Past runs
│
├── static/                         # CSS, JS, images
│   ├── css/
│   │   └── style.css
│   └── js/
│       └── app.js
│
├── websites_config.json           # Website configuration
├── sheets_manager.py              # Google Sheets integration
├── analytics_engine.py            # Statistics & insights
│
├── logs/                          # Scraper logs
│   └── scraper_*.log
│
├── data/                          # Exported data
│   ├── syriacar_export.csv
│   ├── website2_export.csv
│   └── ...
│
└── README.md
```

---

## 🌐 Website Configuration

### websites_config.json

```json
{
  "websites": [
    {
      "id": "syriacar",
      "name": "SyriaCar",
      "url": "https://syriacar.net",
      "type": "cars",
      "scraper_class": "SyriaCarScraper",
      "scraper_file": "scrapers/syriacar_scraper.py",
      "google_sheet_id": "1Oyhm4mrg7zz1pf3I-1_nhddTJsuscN8ppEn-Nr3UCFI",
      "enabled": true,
      "scheduling": {
        "enabled": true,
        "frequency": "weekly",
        "day": "Monday",
        "time": "09:00"
      },
      "image_folder": "images/syriacar"
    },
    {
      "id": "website2",
      "name": "Website 2 - Cars",
      "url": "https://website2.com",
      "type": "cars",
      "scraper_class": "Website2CarScraper",
      "scraper_file": "scrapers/website2_scraper.py",
      "google_sheet_id": "your-sheet-id",
      "enabled": false,
      "scheduling": {
        "enabled": false
      },
      "image_folder": "images/website2"
    },
    {
      "id": "website3",
      "name": "Website 3 - Real Estate",
      "url": "https://website3.com",
      "type": "realestate",
      "scraper_class": "Website3RealEstateScraper",
      "scraper_file": "scrapers/website3_scraper.py",
      "google_sheet_id": "your-sheet-id",
      "enabled": false,
      "scheduling": {
        "enabled": false
      },
      "image_folder": "images/website3"
    }
  ]
}
```

---

## 📊 Database Schema (SQLite)

### Table: websites
```sql
CREATE TABLE websites (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    url TEXT NOT NULL,
    type TEXT NOT NULL,  -- 'cars' or 'realestate'
    scraper_class TEXT,
    google_sheet_id TEXT,
    total_items INTEGER DEFAULT 0,
    new_items_last_run INTEGER DEFAULT 0,
    last_run_timestamp DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

### Table: scraping_jobs
```sql
CREATE TABLE scraping_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    website_id TEXT NOT NULL,
    start_time DATETIME,
    end_time DATETIME,
    status TEXT,  -- 'running', 'success', 'error'
    total_items INTEGER,
    new_items INTEGER,
    duplicate_items INTEGER,
    error_message TEXT,
    FOREIGN KEY(website_id) REFERENCES websites(id)
);
```

### Table: item_statistics
```sql
CREATE TABLE item_statistics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    website_id TEXT NOT NULL,
    item_name TEXT,
    count INTEGER,
    last_seen DATETIME,
    trend TEXT,  -- 'up', 'down', 'stable'
    FOREIGN KEY(website_id) REFERENCES websites(id)
);
```

---

## 🏗️ Base Scraper Architecture

### base_scraper.py
```python
class BaseScraper:
    """Base class for all scrapers"""
    
    def __init__(self, website_config):
        self.config = website_config
        self.website_id = website_config['id']
        self.website_url = website_config['url']
        
    def scrape(self) -> List[Dict]:
        """Override in subclass"""
        raise NotImplementedError
        
    def save_to_sheets(self, items: List[Dict]):
        """Common method to save to Google Sheets"""
        manager = GoogleSheetsManager(self.config['google_sheet_id'])
        manager.append_rows(items)
        
    def get_statistics(self, items: List[Dict]):
        """Calculate statistics from scraped items"""
        stats = {
            'total': len(items),
            'most_common_field': self._analyze_field(items),
            'market_trends': self._detect_trends(items)
        }
        return stats
```

### cars_scraper.py
```python
class CarsScraper(BaseScraper):
    """Base for all car listing scrapers"""
    
    def _parse_car_data(self, item):
        """Common car parsing logic"""
        return {
            'title': item.title,
            'price': item.price,
            'make': item.make,
            'model': item.model,
            'year': item.year,
            # ... other fields
        }
    
    def analyze_market_trends(self, items: List[Dict]):
        """Analyze car market"""
        return {
            'avg_price': self._calc_avg_price(items),
            'most_common_make': self._top_makes(items),
            'avg_year': self._calc_avg_year(items),
            'most_common_body_type': self._top_body_types(items),
        }
```

### realestate_scraper.py
```python
class RealEstateScraper(BaseScraper):
    """Base for all real estate scrapers"""
    
    def _parse_property_data(self, item):
        """Common property parsing logic"""
        return {
            'title': item.title,
            'price': item.price,
            'location': item.location,
            'size': item.size,
            'bedrooms': item.bedrooms,
            # ... other fields
        }
    
    def analyze_market_trends(self, items: List[Dict]):
        """Analyze real estate market"""
        return {
            'avg_price': self._calc_avg_price(items),
            'avg_price_per_sqm': self._calc_price_per_sqm(items),
            'most_common_location': self._top_locations(items),
            'most_common_bedrooms': self._top_bedroom_count(items),
        }
```

---

## 🌐 Web Application (Flask)

### app.py - Main Routes

```python
from flask import Flask, render_template, request, jsonify
import json
from scrapers.syriacar_scraper import SyriaCarScraper
# ... import other scrapers

app = Flask(__name__)

# Load website configuration
with open('websites_config.json') as f:
    WEBSITES_CONFIG = json.load(f)

@app.route('/')
def index():
    """Dashboard with website selector"""
    websites = WEBSITES_CONFIG['websites']
    return render_template('index.html', websites=websites)

@app.route('/api/websites')
def get_websites():
    """API to get all websites"""
    return jsonify(WEBSITES_CONFIG['websites'])

@app.route('/scraper/<website_id>')
def scraper_control(website_id):
    """Scraper control page for specific website"""
    website = next(w for w in WEBSITES_CONFIG['websites'] if w['id'] == website_id)
    return render_template('scraper_control.html', website=website)

@app.route('/api/run-scraper', methods=['POST'])
def run_scraper():
    """Execute scraper for a website"""
    website_id = request.json.get('website_id')
    website = next(w for w in WEBSITES_CONFIG['websites'] if w['id'] == website_id)
    
    # Dynamically load scraper
    scraper_class = get_scraper_class(website['scraper_class'])
    scraper = scraper_class(website)
    
    items = scraper.scrape()
    stats = scraper.get_statistics(items)
    
    return jsonify({
        'status': 'success',
        'items_scraped': len(items),
        'statistics': stats
    })

@app.route('/statistics/<website_id>')
def statistics(website_id):
    """Statistics dashboard for a website"""
    website = next(w for w in WEBSITES_CONFIG['websites'] if w['id'] == website_id)
    stats = get_website_statistics(website_id)
    return render_template('statistics.html', website=website, stats=stats)

@app.route('/api/statistics/<website_id>')
def get_statistics_api(website_id):
    """API endpoint for statistics"""
    stats = {
        'total_items': get_total_items(website_id),
        'new_items_trend': get_items_trend(website_id),
        'most_common_items': get_most_common(website_id),
        'market_analysis': get_market_analysis(website_id),
    }
    return jsonify(stats)

def get_scraper_class(class_name):
    """Dynamically load scraper class"""
    if class_name == 'SyriaCarScraper':
        from scrapers.syriacar_scraper import SyriaCarScraper
        return SyriaCarScraper
    # ... other scrapers
```

---

## 📊 Statistics & Analytics

### analytics_engine.py

```python
class AnalyticsEngine:
    """Calculate statistics and insights"""
    
    def get_market_overview(self, website_id, days=30):
        """Get market overview for last N days"""
        return {
            'total_items': self.get_total_count(website_id),
            'new_items': self.get_new_count(website_id, days),
            'growth_rate': self.calculate_growth(website_id, days),
            'most_common': self.get_most_common_items(website_id),
            'price_trends': self.analyze_price_trends(website_id),
            'market_sentiment': self.calculate_sentiment(website_id),
        }
    
    def get_most_common_items(self, website_id):
        """Top items by frequency"""
        # For cars: Most common makes, models, years
        # For real estate: Most common locations, sizes
        pass
    
    def analyze_price_trends(self, website_id):
        """Price movement analysis"""
        pass
    
    def calculate_growth(self, website_id, days):
        """Calculate growth rate"""
        pass
```

---

## 🎨 Web Interface Wireframe

### Dashboard (index.html)
```
┌─────────────────────────────────────────┐
│          Multi-Website Scraper          │
├─────────────────────────────────────────┤
│                                         │
│  Select Website:  [Dropdown ▼]          │
│                                         │
│  ┌───────────────────────────────────┐  │
│  │  SyriaCar (Cars)                  │  │
│  │  Status: Ready                    │  │
│  │  Last Run: 2 hours ago            │  │
│  │  Items: 1020 cars                 │  │
│  │  [View Statistics] [Run Scraper]  │  │
│  └───────────────────────────────────┘  │
│                                         │
│  ┌───────────────────────────────────┐  │
│  │  Website 2 (Cars) - Disabled      │  │
│  │  Status: Not configured           │  │
│  │  [Configure] [Enable]             │  │
│  └───────────────────────────────────┘  │
│                                         │
│  [Recent Job History] [Settings]        │
│                                         │
└─────────────────────────────────────────┘
```

### Statistics Dashboard (statistics.html)
```
┌─────────────────────────────────────────┐
│  SyriaCar - Market Analysis             │
├─────────────────────────────────────────┤
│                                         │
│  Total Cars:           1020             │
│  New Cars (This Week): 45               │
│  Growth Rate:          8.5% ↑           │
│                                         │
│  Most Common Makes:                     │
│    1. Kia - 150 cars (14.7%)           │
│    2. BMW - 120 cars (11.8%)           │
│    3. Mercedes - 95 cars (9.3%)        │
│                                         │
│  Average Price Trend:                   │
│    [Line Chart: Price over time]       │
│                                         │
│  Most Common Body Types:                │
│    - SUV: 45%                          │
│    - Sedan: 35%                        │
│    - Truck: 20%                        │
│                                         │
│  [Export Data] [Refresh] [Back]        │
│                                         │
└─────────────────────────────────────────┘
```

---

## 🔄 Workflow

### 1. Website Selection
- User selects website from dropdown
- App loads website config

### 2. Scraper Execution
- User clicks "Run Scraper"
- Flask calls appropriate scraper class
- Scraper runs and returns items
- App saves to Google Sheets
- App updates database with stats

### 3. Statistics Display
- User views statistics dashboard
- Shows:
  - Total items count
  - New items added
  - Market trends (makes, models, locations)
  - Growth rate
  - Most common items

### 4. Historical Tracking
- Every scrape is logged to database
- Track changes over time
- Compare week-over-week growth

---

## 🚀 Implementation Phases

### Phase 1: Core Infrastructure (Current)
- [x] Database models
- [ ] Base scraper classes
- [ ] websites_config.json
- [ ] Flask web app skeleton

### Phase 2: First Website (SyriaCar)
- [x] SyriaCar scraper (already done)
- [ ] Integrate with config system
- [ ] Google Sheets integration
- [ ] Basic statistics

### Phase 3: Web Interface
- [ ] Dashboard (website selector)
- [ ] Scraper control panel
- [ ] Statistics dashboard
- [ ] Job history

### Phase 4: Analytics Engine
- [ ] Market trend analysis
- [ ] Growth calculations
- [ ] Most common items analysis
- [ ] Export functionality

### Phase 5: Additional Websites
- [ ] Template for real estate scrapers
- [ ] Add websites 2-7
- [ ] Test each website

### Phase 6: Advanced Features
- [ ] Scheduling (APScheduler)
- [ ] Email notifications
- [ ] API for external integrations
- [ ] Advanced analytics

---

## 📦 Dependencies

```
flask==2.3.0
selenium>=4.0.0
beautifulsoup4>=4.9.0
requests>=2.26.0
google-auth>=2.0.0
google-auth-oauthlib>=0.4.0
google-api-python-client>=2.0.0
apscheduler>=3.8.0
sqlalchemy>=1.4.0
python-dotenv>=0.19.0
```

---

## 🎯 Benefits of This Architecture

1. **Scalability**: Easy to add new websites
2. **Maintainability**: Modular code, separate scraper per website
3. **Flexibility**: Different types (cars, real estate, etc.)
4. **Tracking**: Database tracks all runs and statistics
5. **User-Friendly**: Web interface instead of command line
6. **Analytics**: Built-in statistics and insights
7. **Multi-Sheet**: Each website has its own Google Sheet

---

## Next Steps

1. Create base scraper classes
2. Create Flask app skeleton
3. Integrate SyriaCar scraper with new system
4. Build database layer
5. Create web interface
6. Add analytics engine

This provides a **professional, scalable platform** for managing multiple websites! 🚀
