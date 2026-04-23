# Google Sheets Integration - Quick Start (5 Steps)

**Goal**: Get scraper writing data to Google Sheets in 15 minutes

---

## ✅ Step 1: Install Dependencies (2 minutes)

```bash
pip install google-auth-oauthlib google-auth-httplib2 google-api-python-client
```

---

## ✅ Step 2: Get Credentials File (5 minutes)

### 2A: Create Google Cloud Project
1. Go to: https://console.cloud.google.com
2. Create new project (name: "Scraper")
3. Enable Google Sheets API:
   - Search "Google Sheets API"
   - Click "Enable"

### 2B: Create Service Account Key
1. Go to "Credentials" 
2. Click "Create Credentials" → "Service Account"
3. Name: "scraper"
4. Click "Create and Continue" → "Done"
5. Go to Service Accounts, click your account
6. Go to "Keys" tab
7. "Add Key" → "Create new key" → "JSON"
8. Download the file

### 2C: Add Credentials to Project
1. Rename downloaded file to `credentials.json`
2. Copy to: `D:\skyscraper\credentials.json`

---

## ✅ Step 3: Create Google Sheet (3 minutes)

1. Go to: https://sheets.google.com
2. Create new spreadsheet: "SyriaCar"
3. In first row, add headers:
   ```
   id | website | scraped_at | title | price | make | model | year | mileage | location | fuel_type | transmission | body_type | condition | origin | link | description | image_url | image_alt
   ```
4. Get Sheet ID from URL:
   - URL: `https://docs.google.com/spreadsheets/d/1ABC2DEF3GHIJ4KLM/edit`
   - ID: `1ABC2DEF3GHIJ4KLM` (copy this)

---

## ✅ Step 4: Share Sheet with Service Account (2 minutes)

1. In Google Sheet, click "Share"
2. Copy service account email from `credentials.json`:
   - Open file: `D:\skyscraper\credentials.json`
   - Find: `"client_email": "..."`
   - Copy the email (looks like: `scraper-platform@project.iam.gserviceaccount.com`)
3. Paste email in Share dialog
4. Change permission to "Editor"
5. Uncheck "Notify people"
6. Click "Share"

---

## ✅ Step 5: Update Configuration (2 minutes)

Edit `D:\skyscraper\websites_config.json`:

Find the SyriaCar section:
```json
{
  "id": "syriacar",
  "name": "SyriaCar",
  "google_sheet_id": "YOUR-SHEET-ID-HERE",  ← CHANGE THIS
  ...
}
```

Replace with your Sheet ID:
```json
{
  "id": "syriacar",
  "name": "SyriaCar",
  "google_sheet_id": "1ABC2DEF3GHIJ4KLM",  ← YOUR REAL ID
  ...
}
```

---

## 🚀 Test It!

### Via Web Interface:
```bash
# 1. Start Flask
python app.py

# 2. Open browser
http://localhost:5000/website/syriacar

# 3. Click "Run Scraper Now"

# 4. Wait 2-3 minutes for completion

# 5. Check Google Sheet - data should be there!
```

### Via API:
```bash
curl -X POST http://localhost:5000/api/run-scraper \
  -H "Content-Type: application/json" \
  -d '{"website_id": "syriacar"}'
```

**Expected**: 
- `"sheets_written": true`
- `"status": "success"`
- Data in Google Sheet

---

## 🆘 Quick Troubleshooting

| Problem | Solution |
|---------|----------|
| "No module google.auth" | Run: `pip install google-auth*` |
| "credentials.json not found" | Copy file to `D:\skyscraper\credentials.json` |
| "403 Forbidden" | Share Google Sheet with service account email (Editor role) |
| "No valid Sheet ID" | Update `websites_config.json` with real Sheet ID (not placeholder) |
| "Data not appearing" | Check `sheets_written: true` in API response |

---

## ✨ Done!

Your scraper now writes data to Google Sheets automatically! 🎉

**Next**: Read full guide at `GOOGLE_SHEETS_SETUP.md` for advanced options and tips.
