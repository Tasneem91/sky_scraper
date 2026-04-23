# Quick Start Guide

Get the scraper running in 10 minutes!

## Prerequisites Checklist
- [ ] Python 3.8+ installed
- [ ] Google account
- [ ] Chrome browser
- [ ] D:\skyscraper folder created

## Step-by-Step

### 1. Install Python Packages (2 minutes)

Open Command Prompt:
```
Win + R → cmd
```

Go to project folder and install:
```bash
cd D:\skyscraper
pip install -r requirements.txt
```

### 2. Get Google Credentials (5 minutes)

#### Option A: Service Account (Recommended)
1. Go to https://console.cloud.google.com/
2. Create new project → Enable Sheets API
3. Create Service Account credentials
4. Download JSON and save as `credentials.json` in D:\skyscraper
5. Share your Google Sheet with the service account email

#### Option B: OAuth2 (Simpler)
1. Same steps but choose "OAuth client ID" instead
2. Save as `credentials.json` in D:\skyscraper
3. First run will ask you to authorize

### 3. Test the Scraper (1-2 minutes)

```bash
python main.py
```

This will:
- Scrape the website
- Check for duplicates
- Show what would be saved
- **Not** make any actual updates

You should see output like:
```
INFO - Found 50 car listings
INFO - Found 50 unique and 0 duplicate records
INFO - [TEST MODE] Would add 50 new rows
```

### 4. Go Live

Once test run looks good:

1. Create a Google Sheet (optional - script can create one)
2. Get the spreadsheet ID from URL: `docs.google.com/spreadsheets/d/{THIS_ID}/...`
3. Update `main.py`:
```python
orchestrator = ScraperOrchestrator(
    website_key="syriacar",
    spreadsheet_id="YOUR_SHEET_ID_HERE"  # ← Add here
)
result = orchestrator.run(test_mode=False)  # ← Change to False
```

4. Run it:
```bash
python main.py
```

### 5. Schedule for Weekly (Optional)

See `SETUP_INSTRUCTIONS.md` for:
- Windows Task Scheduler setup
- Automatic weekly runs
- Log monitoring

## That's It! 🎉

Your scraper is now:
- ✅ Collecting car data
- ✅ Downloading images
- ✅ Saving to Google Sheets
- ✅ Preventing duplicates

## Next Steps

- [ ] Verify first run completed
- [ ] Check Google Sheets for data
- [ ] Set up weekly schedule
- [ ] Monitor logs for issues

## Quick Troubleshooting

| Problem | Solution |
|---------|----------|
| "Module not found" | Run `pip install -r requirements.txt` again |
| Auth fails | Check credentials.json location and content |
| No cars found | Run inspector on website, update selectors in config.py |
| Images not saving | Check D:\skyscraper\data\images folder permissions |

## Common Commands

```bash
# Test run (dry run)
python main.py

# View logs
type logs\*.log

# Check installed packages
pip list | find "selenium"

# Update all packages
pip install --upgrade -r requirements.txt
```

## Files to Know

- `config.py` - All settings go here
- `main.py` - The main script to run
- `SETUP_INSTRUCTIONS.md` - Detailed guide
- `logs/` - Check here for issues

## Questions?

Check the detailed guide: `SETUP_INSTRUCTIONS.md`

Good luck! 🚀
