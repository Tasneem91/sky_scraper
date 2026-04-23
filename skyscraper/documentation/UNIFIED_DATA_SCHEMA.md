# Unified Data Schema for All Scrapers

**Purpose**: Ensure consistent column names across all data sources for easy merging and comparison

---

## Standard Column Mapping

All scrapers MUST output these columns in this exact order:

| Column Name | Type | Description | Source |
|------------|------|-------------|--------|
| **scraped_at** | String (ISO) | Timestamp when data was extracted | All |
| **source** | String | Website name (syriacar, damazzle, etc.) | All |
| **id** | String | Unique identifier for this listing | All |
| **title** | String | Car title/name (e.g., "Ford Mustang") | All |
| **price** | Float | Price in USD or local currency | All |
| **price_raw** | String | Raw price string with currency | Damazzle |
| **brand** | String | Car manufacturer (Ford, Toyota, etc.) | All |
| **model** | String | Car model (Mustang, Camry, etc.) | SyriaCar |
| **category** | String | Category type (Cars, SUVs, etc.) | Damazzle |
| **year** | Integer | Manufacturing year (2022, 2023, etc.) | All |
| **mileage** | String | Mileage/odometer reading | All |
| **location** | String | City or region where car is listed | All |
| **posted_date** | String | When listing was posted (e.g., "2 days ago") | Damazzle |
| **condition** | String | Condition (New, Used, Excellent, etc.) | SyriaCar |
| **fuel_type** | String | Fuel type (Gasoline, Diesel, etc.) | SyriaCar |
| **transmission** | String | Automatic or Manual | SyriaCar |
| **body_type** | String | Body type (SUV, Sedan, Truck, etc.) | SyriaCar |
| **origin** | String | Car origin (American, Japanese, etc.) | SyriaCar |
| **image_count** | Integer | Number of images available | All |
| **images** | String (JSON) | JSON array of all image URLs | All |
| **primary_image** | String (URL) | First/main image URL | All |
| **link** | String (URL) | Direct link to listing on source website | All |
| **ad_id** | String | Ad/listing ID from source | Damazzle |
| **ad_url** | String (URL) | Direct URL to ad | Damazzle |
| **description** | String | Full description text | SyriaCar |

---

## Implementation Guide

### For Damazzle Scraper

**Output format** (when writing to Google Sheets):
```python
{
  'scraped_at': '2026-04-23T11:30:00',
  'source': 'damazzle',
  'id': 'damazzle_fwrd-mwstnj_1682253000',
  'title': 'فورد موستنج',
  'price': 17000.0,
  'price_raw': '17,000 $',
  'brand': 'فورد',
  'model': None,  # Not available
  'category': 'سيارات',
  'year': 2022,
  'mileage': '80,000-100,000كم',
  'location': 'المزة - دمشق',
  'posted_date': 'منذ يومان',
  'condition': None,
  'fuel_type': None,
  'transmission': None,
  'body_type': None,
  'origin': None,
  'image_count': 3,
  'images': '["url1", "url2", "url3"]',  # JSON string
  'primary_image': 'url1',
  'link': 'https://damazzle.com/ads/fwrd-mwstnj',
  'ad_id': 'fwrd-mwstnj',
  'ad_url': 'https://damazzle.com/ads/fwrd-mwstnj',
  'description': None
}
```

### For SyriaCar Scraper

**Output format** (when writing to Google Sheets):
```python
{
  'scraped_at': '2026-04-23T11:30:00',
  'source': 'syriacar',
  'id': 'syriacar_12345_1682253000',
  'title': 'كيا سبورتاج',
  'price': 25000.0,
  'price_raw': None,  # Not available
  'brand': 'كيا',
  'model': 'Sportage',
  'category': None,  # Not available
  'year': 2021,
  'mileage': '45,000 كم',
  'location': 'دمشق',
  'posted_date': None,  # Not available
  'condition': 'مستعملة',
  'fuel_type': 'بنزين',
  'transmission': 'أوتوماتيك',
  'body_type': 'SUV',
  'origin': 'يابانية',
  'image_count': 5,
  'images': '["url1", "url2", "url3", "url4", "url5"]',  # JSON string
  'primary_image': 'url1',
  'link': 'https://syriacar.net/cars/12345',
  'ad_id': None,  # Not available
  'ad_url': None,  # Not available
  'description': 'Full description text here...'
}
```

---

## Google Sheets Column Order

When writing to Google Sheets, create columns in THIS exact order:

```
A: scraped_at
B: source
C: id
D: title
E: price
F: price_raw
G: brand
H: model
I: category
J: year
K: mileage
L: location
M: posted_date
N: condition
O: fuel_type
P: transmission
Q: body_type
R: origin
S: image_count
T: images
U: primary_image
V: link
W: ad_id
X: ad_url
Y: description
```

**For NULL values**: Use `None` in Python, which will be written as empty cell in Google Sheets

---

## Benefits of Unified Schema

✅ **Easy merging**: Combine Damazzle + SyriaCar data in same Google Sheet or SQL database  
✅ **Consistent analysis**: Run same queries/filters on combined dataset  
✅ **Data comparison**: See differences between sources side-by-side  
✅ **Unified visualizations**: Create charts showing both sources  
✅ **Quality control**: Identify missing/different fields per source  

---

## Notes on Null Handling

| Field | Damazzle | SyriaCar | Combined Sheet |
|-------|----------|----------|-----------------|
| model | Not available | ✅ Yes | Leave empty if from Damazzle |
| category | ✅ Yes | Not available | Leave empty if from SyriaCar |
| condition | Not available | ✅ Yes | Leave empty if from Damazzle |
| fuel_type | Not available | ✅ Yes | Leave empty if from Damazzle |
| transmission | Not available | ✅ Yes | Leave empty if from Damazzle |
| body_type | Not available | ✅ Yes | Leave empty if from Damazzle |
| origin | Not available | ✅ Yes | Leave empty if from Damazzle |
| posted_date | ✅ Yes | Not available | Leave empty if from SyriaCar |
| price_raw | ✅ Yes | Not available | Leave empty if from SyriaCar |
| description | Not available | ✅ Yes | Leave empty if from Damazzle |
| ad_id | ✅ Yes | Not available | Leave empty if from SyriaCar |

---

## Future Expansion

When adding new scrapers (Website 3, Website 4, etc.):

1. Map their fields to this standard schema
2. Add missing columns as empty
3. Follow the same order for consistency
4. Update this document

Example for Website 3:
```python
# Website 3 raw data
{
  'car_name': 'BMW 330i',
  'cost': 45000,
  'maker': 'BMW',
  'age': 2020,
  'km': 80000
}

# Mapped to standard schema
{
  'title': 'BMW 330i',
  'price': 45000.0,
  'brand': 'BMW',
  'year': 2020,
  'mileage': '80,000 كم',
  # ... all other fields set to None
}
```

---

**Status**: ACTIVE - Update when adding new scrapers  
**Last Updated**: April 23, 2026
