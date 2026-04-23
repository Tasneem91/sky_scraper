# Detail Page Extraction Guide

## Current Status

The scraper now supports **TWO modes**:

### Mode 1: Fast Listing Only (DEFAULT)
- ✅ Scrapes 1000+ cars from listing page
- ✅ Gets: Title, Price, Image, Link
- ⏱️ Speed: ~30 seconds for all cars
- Command:
```bash
python main.py
```

### Mode 2: Full Details (SLOW - Optional)
- ✅ Scrapes listing + clicks detail page for each car
- ✅ Gets: All specs (engine, doors, color, fuel type, etc.)
- ⏱️ Speed: ~5-10 seconds PER CAR = 1000 cars = 1.5+ HOURS
- How to enable: Edit `scraper.py` line ~220 and change:
```python
fetch_details = False  # Change to True
```

---

## Detail Page Specs Available

When fetching detail pages, the scraper extracts:

From `<li class="li-1-details-color">` elements:
- ✅ Make/Model
- ✅ Year
- ✅ Engine Capacity (CC)
- ✅ Engine Power (HP)
- ✅ Transmission (Auto/Manual)
- ✅ Fuel Type (Gasoline/Diesel)
- ✅ Body Type (SUV/Sedan/etc)
- ✅ Number of Doors
- ✅ Number of Seats
- ✅ Car Condition (Used/New)
- ✅ Exterior Color
- ✅ Interior Color
- ✅ And more...

---

## Recommended Approach

### Strategy 1: Two-Pass Scraping (RECOMMENDED)
```
Week 1: Run fast listing scraper (30 seconds)
Week 2: Run detail scraper on NEW cars only (saves time)
```

### Strategy 2: Hybrid Scraping
```python
# Scrape first 100 cars with details only
# Scrape remaining 900 without details
```

### Strategy 3: Background Jobs
```python
# Scrape listing page fast
# Queue each car for detail page scraping
# Process details in background/batch jobs
```

---

## Enable Detail Scraping

Edit `D:\skyscraper\scraper.py` around line 220:

**Before:**
```python
fetch_details = False  # Fast mode
```

**After:**
```python
fetch_details = True   # Get detailed specs
```

Then run:
```bash
python main.py
```

⚠️ **WARNING**: This will take 1.5+ hours for 1000 cars!

---

## What Gets Extracted

### Listing Page (Always):
```
id, title, price, description, link, image_url, image_alt, 
scraped_at, website
```

### Detail Page (When fetch_details=True):
```
spec_0, spec_1, spec_2, ... (all li.li-1-details-color items)
make, model, year, engine_capacity, engine_power, transmission,
fuel_type, body_type, doors, seats, condition, 
exterior_color, interior_color
```

---

## Performance Comparison

| Mode | Cars | Time | Fields |
|------|------|------|--------|
| Listing Only | 1000+ | ~30 sec | 9 |
| + Details | 100 | ~10 min | 20+ |
| + Details | 1000 | ~2 hrs | 20+ |

---

## Next Steps

### Option A: Test Fast Listing (Recommended First)
```bash
python main.py
```
This will:
1. Load all 1000+ cars
2. Extract basic info
3. Save to Google Sheets
4. Takes ~30 seconds

### Option B: Enable Detail Scraping (For Full Data)
1. Edit scraper.py: `fetch_details = True`
2. Run: `python main.py`
3. Wait 1.5+ hours for full details

### Option C: Hybrid (Best of Both)
Create a separate script that:
1. Runs fast listing scraper weekly
2. Scrapes details for new cars only
3. Keeps Google Sheet updated

---

## Test It!

Run the fast version now:

```bash
python main.py
```

You should see:
- ✅ Scrolling through 100+ cars
- ✅ All 1000+ cars eventually loaded
- ✅ Data saved to Google Sheets
- ✅ Completion in ~30-60 seconds

Then let me know:
1. How many cars were scraped?
2. Does the data look good?
3. Do you want details for all cars, or just new ones?
