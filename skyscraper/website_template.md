# Website Configuration Template

Use this template to add new websites to the scraper.

## Step 1: Inspect the Website

1. Open the website in Chrome
2. Right-click on a car listing
3. Select "Inspect Element"
4. Find the CSS selectors for each piece of data

## Step 2: Document CSS Selectors

Create a document like this for your website:

```
Website: [Name]
URL: [Main URL]

Main listing container: div.car-item
Car title: h2.car-title
Car price: span.price
Car description: p.description
Car image: img.car-image
Car link: a.car-link

Notes:
- Images are lazy-loaded
- Need to scroll to load more listings
- Price includes currency symbol
```

## Step 3: Update config.py

Add your website to `config.py`:

```python
WEBSITE_CONFIG = {
    "syriacar": { ... },  # Existing
    "mywebsite": {        # New website
        "url": "https://example.com/cars",
        "name": "My Website",
        "selectors": {
            "car_listings": "div.car-item",      # Main container
            "title": "h2.car-title",              # Title selector
            "price": "span.price",                # Price selector
            "description": "p.description",       # Description selector
            "image": "img.car-image",             # Image selector
            "link": "a.car-link",                 # Link selector
        },
        "image_folder": str(IMAGES_DIR / "mywebsite"),
    }
}
```

## Step 4: Test the Scraper

1. Run in test mode:
```bash
python -c "from main import ScraperOrchestrator; ScraperOrchestrator('mywebsite').run(test_mode=True)"
```

2. If it fails, check:
   - Selectors are correct
   - Website structure matches
   - No authentication required
   - Browser can access the site

## Step 5: Create Spreadsheet

1. Create new Google Sheet
2. Note the spreadsheet ID
3. Share with service account email (if using service account)

## Step 6: Go Live

```bash
python -c "from main import ScraperOrchestrator; ScraperOrchestrator('mywebsite', 'SHEET_ID').run(test_mode=False)"
```

## Common CSS Selectors

### Class selectors
```
.class-name          → Elements with class "class-name"
div.car              → Divs with class "car"
```

### ID selectors
```
#unique-id           → Element with ID "unique-id"
```

### Attribute selectors
```
[data-id="123"]      → Elements with data-id="123"
a[href*="cars"]      → Links containing "cars" in href
```

### Combinators
```
div > span           → Span directly inside div
div span             → Span anywhere inside div
```

## Troubleshooting

### No results found
- Check if selectors are correct
- Website might use JavaScript - this scraper can handle that
- Try more generic selectors (e.g., `div` instead of `div.specific`)

### Partial results
- Some data might be missing
- Check if required selectors exist in all listings
- Make selectors more specific if needed

### Slow scraping
- Large websites may take time
- Can add delay between requests in `config.py`
- Consider filtering by date/price on the website first

## Example: Adding "CarsPlus"

Website: https://carsplus.example.com/

1. Inspect the site and find:
   - Listings: `div.listing`
   - Title: `h3.listing-title`
   - Price: `span.listing-price`
   - Image: `img.listing-photo`
   - Link: `a.listing-link`

2. Add to config.py:
```python
"carsplus": {
    "url": "https://carsplus.example.com/",
    "name": "Cars Plus",
    "selectors": {
        "car_listings": "div.listing",
        "title": "h3.listing-title",
        "price": "span.listing-price",
        "description": "p.listing-desc",
        "image": "img.listing-photo",
        "link": "a.listing-link",
    },
    "image_folder": str(IMAGES_DIR / "carsplus"),
}
```

3. Test:
```bash
python main.py  # Edit to use "carsplus"
```

4. Create sheet and run:
```bash
python main.py  # With test_mode=False and sheet ID
```

## Need Help?

1. Check the website's HTML structure
2. Look at existing configurations in config.py
3. Use browser DevTools to inspect elements
4. Check logs for error messages

Good luck! 🚀
