# SyriaCar HTML Structure Reference

**Purpose**: Visual guide showing exact HTML structure and CSS selectors used for data extraction

---

## 📍 Listing Page Card Structure (Full)

```html
<div class="car-card">                           ← CONTAINER FOR ENTIRE CAR
    
    <div class="card-image">                     ← IMAGE SECTION
        <div class="cars-images">
            <!-- Multiple images -->
            <img src="https://syriacar.net/storage/cars-small/April2026/..." 
                 alt="للبيع سيارة في سوريا حلب كيا سبورتاج موديل 2017">
            <img src="https://syriacar.net/storage/cars-small/April2026/..." 
                 alt="...">
        </div>
        
        <!-- DETAIL PAGE LINK (data-link attribute) ✨ KEY FIELD -->
        <button class="sharing hoverable share-button" 
                data-link="https://syriacar.net/car/details/kia-sportage-2017-hlb-12264"
                data-type="car" 
                data-mobile="963993470007" 
                type="button">
            <svg>...</svg>
        </button>
    </div>
    
    <div class="card-info">                      ← MAIN DATA SECTION
        
        <!-- TITLE SECTION -->
        <div class="border-div-title-card-info">
            <h1 class="car-title">
                كيا Kia                          ← TITLE (make + Arabic)
            </h1>
            <h2 class="car-sub-title">
                Sportage • إس يو في • 2017       ← SUBTITLE (model • body • year)
            </h2>
        </div>
        
        <!-- FEATURES SECTION (6 FIELDS) -->
        <div class="features">
            
            <!-- Features A: Mileage & Location -->
            <div class="features-a">
                <div class="div-features-padding">
                    <svg>...</svg>
                    <p title="المسافة المقطوعة">
                        225,000                  ← MILEAGE VALUE
                        <span class="km">كم</span>  ← UNIT (KM)
                    </p>
                </div>
                <div>
                    <svg>...</svg>
                    <span title="المحافظة أو المنطقة التي تتواجد بها السيارة">
                        حلب                      ← LOCATION (City)
                    </span>
                </div>
            </div>
            
            <!-- Features B: Fuel Type & Origin -->
            <div class="features-b">
                <div class="div-features-padding">
                    <svg>...</svg>
                    <span title="نوع الوقود">
                        بنزين                   ← FUEL TYPE
                    </span>
                </div>
                <div>
                    <svg>...</svg>
                    <span title="الوارد الإقليمي للمركبة">
                        أمريكية                 ← ORIGIN
                    </span>
                </div>
            </div>
            
            <!-- Features C: Transmission & Condition -->
            <div class="features-c">
                <div class="div-features-padding">
                    <svg>...</svg>
                    <span title="نوع ناقل الحركة">
                        أوتوماتيك               ← TRANSMISSION
                    </span>
                </div>
                <div>
                    <svg>...</svg>
                    <span title="حالة المركبة">
                        مستعملة                 ← CONDITION
                    </span>
                </div>
            </div>
        </div>
    </div>
    
    <!-- PRICE SECTION (Outside card-info) ✨ KEY FIELD -->
    <div class="new-card-contact">
        <div class="contact-a">
            <button type="button" 
                    class="effectphones btn-contact-p" 
                    id="request-price" 
                    title="سعر المركبة">
                السعر 17,000 دولار              ← PRICE TEXT
            </button>
        </div>
        <div class="contact-b">
            <button type="button" 
                    class="effectphones btn-contact-i" 
                    onclick="window.location='https://syriacar.net/car/details/kia-sportage-2017-hlb-12264'">
                <span class="span-contact-i">تفاصيل</span>
                <svg>...</svg>
            </button>
        </div>
    </div>
</div>
```

---

## 🎯 CSS Selectors Used for Extraction

### All Listing Page Fields

| Field | Selector | Location | HTML Example |
|-------|----------|----------|--------------|
| **Car Card** | `div.car-card` | Container | `<div class="car-card">` |
| **Image URL** | `img` in `.cars-images` | `.card-image` | `<img src="...">` |
| **Detail Link** | `button.share-button[data-link]` | `.card-image` | `data-link="https://..."` |
| **Title** | `h1.car-title` | `.card-info` | `كيا Kia` |
| **Subtitle** | `h2.car-sub-title` | `.card-info` | `Sportage • إس يو في • 2017` |
| **Model** | Extract from subtitle (1st part) | `h2.car-sub-title` | `Sportage` |
| **Body Type** | Extract from subtitle (2nd part) | `h2.car-sub-title` | `إس يو في` |
| **Year** | Extract from subtitle (3rd part) | `h2.car-sub-title` | `2017` |
| **Mileage** | 1st div in `.features-a` | `.features` | `225,000 كم` |
| **Location** | 2nd div in `.features-a` | `.features` | `حلب` |
| **Fuel Type** | 1st div in `.features-b` | `.features` | `بنزين` |
| **Origin** | 2nd div in `.features-b` | `.features` | `أمريكية` |
| **Transmission** | 1st div in `.features-c` | `.features` | `أوتوماتيك` |
| **Condition** | 2nd div in `.features-c` | `.features` | `مستعملة` |
| **Price** | `button.btn-contact-p` | Outside `.card-info` | `السعر 17,000 دولار` |

---

## 🔍 Python Extraction Code

### Key Methods in scraper.py

```python
# 1. Main extraction method
def _extract_car_data(self, item, index, fetch_details=False):
    """Extract car data from listing item"""
    car_data = { ... }
    
    # Extract from card-info
    card_info = item.find('div', class_='card-info')
    
    # Extract title from h1
    title_elem = card_info.find('h1', class_='car-title')
    
    # Extract features
    features_div = card_info.find('div', class_='features')
    self._extract_features(features_div, car_data)
    
    # Extract price (OUTSIDE card-info)
    price_button = item.find('button', class_='btn-contact-p')
    
    # Extract detail link
    share_button = item.find('button', class_='share-button')
    car_data['link'] = share_button.get('data-link')
    
    return car_data

# 2. Features extraction method
def _extract_features(self, features_div, car_data):
    """Extract mileage, location, fuel, transmission, condition, origin"""
    
    # features-a: mileage and location
    features_a = features_div.find('div', class_='features-a')
    divs = features_a.find_all('div')
    car_data['mileage'] = divs[0].get_text(strip=True)
    car_data['location'] = divs[1].get_text(strip=True)
    
    # features-b: fuel and origin
    features_b = features_div.find('div', class_='features-b')
    divs = features_b.find_all('div')
    car_data['fuel_type'] = divs[0].get_text(strip=True)
    car_data['origin'] = divs[1].get_text(strip=True)
    
    # features-c: transmission and condition
    features_c = features_div.find('div', class_='features-c')
    divs = features_c.find_all('div')
    car_data['transmission'] = divs[0].get_text(strip=True)
    car_data['condition'] = divs[1].get_text(strip=True)
    
    # Parse subtitle for model, body_type, year
    subtitle_text = features_div.find_parent('div', class_='card-info').find('h2', class_='car-sub-title').get_text(strip=True)
    parts = subtitle_text.split('•')
    car_data['model'] = parts[0].strip()
    car_data['body_type'] = parts[1].strip()
    car_data['year'] = parts[2].strip()
```

---

## 📋 Field Extraction Examples

### Example 1: Kia Sportage
```
HTML Input:
<h1 class="car-title">كيا Kia</h1>
<h2 class="car-sub-title">Sportage • إس يو في • 2017</h2>
<div class="features-a">
  <div>225,000 <span class="km">كم</span></div>
  <div>حلب</div>
</div>
<div class="features-b">
  <div>بنزين</div>
  <div>أمريكية</div>
</div>
<div class="features-c">
  <div>أوتوماتيك</div>
  <div>مستعملة</div>
</div>
<button class="share-button" data-link="https://syriacar.net/car/details/kia-sportage-2017-hlb-12264"></button>
<button class="btn-contact-p">السعر 17,000 دولار</button>

Extracted Output:
{
  "title": "كيا Kia",
  "model": "Sportage",
  "body_type": "إس يو في",
  "year": "2017",
  "mileage": "225,000 كم",
  "location": "حلب",
  "fuel_type": "بنزين",
  "origin": "أمريكية",
  "transmission": "أوتوماتيك",
  "condition": "مستعملة",
  "link": "https://syriacar.net/car/details/kia-sportage-2017-hlb-12264",
  "price": "السعر 17,000 دولار"
}
```

### Example 2: Chevrolet Traverse
```
HTML Input:
<h1 class="car-title">Chevrolet شفروليه</h1>
<h2 class="car-sub-title">Traverse • سيدان • 2023</h2>
<div class="features-a">
  <div>100,000 <span class="km">كم</span></div>
  <div>ريف دمشق</div>
</div>
<div class="features-b">
  <div>بنزين</div>
  <div>أمريكية</div>
</div>
<div class="features-c">
  <div>أوتوماتيك</div>
  <div>مستعملة</div>
</div>
<button class="btn-contact-p">السعر 20,000 دولار</button>

Extracted Output:
{
  "title": "Chevrolet شفروليه",
  "model": "Traverse",
  "body_type": "سيدان",
  "year": "2023",
  "mileage": "100,000 كم",
  "location": "ريف دمشق",
  "fuel_type": "بنزين",
  "origin": "أمريكية",
  "transmission": "أوتوماتيك",
  "condition": "مستعملة",
  "price": "السعر 20,000 دولار"
}
```

---

## 🔧 Configuration in config.py

```python
# Current CSS selectors used:
WEBSITE_CONFIG = {
    "syriacar": {
        "url": "https://syriacar.net",
        "image_folder": "images/syriacar",
        "selectors": {
            "car_card": "div.car-card",
            "card_info": "div.card-info",
            "car_title": "h1.car-title",
            "car_subtitle": "h2.car-sub-title",
            "features": "div.features",
            "features_a": "div.features-a",
            "features_b": "div.features-b",
            "features_c": "div.features-c",
            "price_button": "button.btn-contact-p",
            "share_button": "button.share-button",
            "image": "img",
        }
    }
}
```

---

## ⚠️ What Happens If HTML Changes

### If Website Updates HTML Structure

1. **Check what changed**
   - Open browser inspector (F12)
   - Look for changed CSS classes or structure
   - Save updated HTML to `page_source_new.html`

2. **Update selectors**
   - Identify new CSS class names
   - Update `WEBSITE_CONFIG` in `config.py`
   - Test with small run

3. **Example**: If price button changes to `class="price-info"`
   ```python
   # Old:
   price_button = item.find('button', class_='btn-contact-p')
   
   # New:
   price_button = item.find('button', class_='price-info')
   ```

4. **Test the change**
   ```bash
   python main.py  # Should show correct prices
   ```

---

## 🎯 Field Presence Guarantees

### Always Available (From Listing Page)
✅ title - From h1.car-title  
✅ model - From h2.car-sub-title (split by •)  
✅ body_type - From h2.car-sub-title (split by •)  
✅ year - From h2.car-sub-title (split by •)  
✅ mileage - From features-a first div  
✅ location - From features-a second div  
✅ fuel_type - From features-b first div  
✅ origin - From features-b second div  
✅ transmission - From features-c first div  
✅ condition - From features-c second div  
✅ price - From button.btn-contact-p  
✅ link - From button.share-button[data-link]  

### Sometimes Available (Depends on Content)
⚠️ image_url - If image exists  
⚠️ image_path - If image downloads successfully  

### Only Available (Detail Page Fetch)
❓ engine_capacity - From detail page (if fetch_details=True)  
❓ engine_power - From detail page (if fetch_details=True)  
❓ door_count - From detail page (if fetch_details=True)  
❓ seats - From detail page (if fetch_details=True)  
❓ colors - From detail page (if fetch_details=True)  

---

## 📱 Mobile vs Desktop

Both mobile and desktop render the same card structure, so extraction works on both!

---

## 🐛 Debug Tips

If extraction isn't working:

1. **Save page_source.html**
   - Already done in scraper.py line ~211
   - Check D:\skyscraper\page_source.html

2. **Search for selectors**
   ```bash
   grep "car-card" page_source.html   # Find cars
   grep "car-title" page_source.html  # Find titles
   grep "btn-contact-p" page_source.html  # Find prices
   ```

3. **Check extracted data**
   - Look at Google Sheet
   - Compare with expected values
   - Check logs in logs/ folder

4. **Inspect with browser**
   - Right-click → Inspect
   - Copy selector path
   - Test in scraper

---

## ✅ Validation Checklist

After running scraper, verify:

- [ ] Price column populated (not "N/A")
- [ ] Mileage shows distances (e.g., "225,000 كم")
- [ ] Locations match cities (حلب, دمشق, etc.)
- [ ] Transmission shows values (أوتوماتيك, يدوي)
- [ ] Condition shows values (مستعملة, جديدة)
- [ ] Origin shows values (أمريكية, أوروبية)
- [ ] Links clickable to detail pages
- [ ] Images embedded in sheet

If any field shows mostly "N/A", check:
1. HTML selector in config.py
2. CSS class names haven't changed
3. Element structure matches this document

---

**Last Updated**: April 22, 2026  
**Verified Against**: SyriaCar.net current HTML structure
