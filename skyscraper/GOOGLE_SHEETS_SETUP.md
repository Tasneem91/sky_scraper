# Google Sheets Integration Setup Guide

**Status**: Google Sheets writing is now integrated into the scraper platform  
**Last Updated**: April 23, 2026  

---

## 🎯 What Changed

The Flask app now automatically writes all scraped data to Google Sheets after each scrape run:

1. ✅ Scraper runs and collects data
2. ✅ Data is converted to Google Sheets format
3. ✅ Headers are written/updated in first row
4. ✅ Data rows are appended starting from row 2
5. ✅ Header row is formatted (bold, colored background)
6. ✅ Success/failure message returned in API response

---

## 📋 Requirements

To write to Google Sheets, you need:

1. **Google Cloud Project** with Sheets API enabled
2. **Service Account credentials** (or OAuth2 token)
3. **Google Sheet ID** for each website in `websites_config.json`
4. **Python libraries**:
   ```bash
   pip install google-auth-oauthlib google-auth-httplib2 google-api-python-client
   ```

---

## 🔧 Setup Steps

### Step 1: Create Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create a new project (name: "Scraper Platform")
3. Enable the **Google Sheets API**:
   - Click "Enable APIs and Services"
   - Search for "Google Sheets API"
   - Click "Enable"

### Step 2: Create Service Account

1. Go to **Credentials** in Cloud Console
2. Click **Create Credentials** → **Service Account**
3. Fill in:
   - Service account name: `scraper-platform`
   - Service account ID: auto-generated
   - Click "Create and Continue"
4. Grant roles:
   - Click "Continue" (no additional roles needed for sheets)
   - Click "Done"

### Step 3: Create and Download Key

1. In Cloud Console, go to **Service Accounts**
2. Click on the service account you created
3. Go to **Keys** tab
4. Click **Add Key** → **Create new key**
5. Choose **JSON** format
6. Click **Create**
7. A JSON file will download (keep it safe!)

### Step 4: Add Credentials File to Project

1. Rename the downloaded JSON file to `credentials.json`
2. Copy it to your project root:
   ```
   D:\skyscraper\credentials.json
   ```

File should contain:
```json
{
  "type": "service_account",
  "project_id": "your-project",
  "private_key_id": "...",
  "private_key": "...",
  "client_email": "scraper-platform@...",
  "client_id": "...",
  ...
}
```

### Step 5: Create Google Sheets

Create a Google Sheet for each website you want to scrape:

#### For SyriaCar:
1. Go to [Google Sheets](https://sheets.google.com)
2. Create new spreadsheet: "SyriaCar Listings"
3. Add header row with columns:
   ```
   id | website | scraped_at | title | price | make | model | year | mileage | location | fuel_type | transmission | body_type | condition | origin | link | description | image_url | image_alt
   ```
4. Get the Sheet ID from URL:
   - URL: `https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit`
   - Copy the `{SHEET_ID}` part

### Step 6: Share Sheet with Service Account

1. Open your Google Sheet
2. Click **Share**
3. Enter the service account email (from credentials.json: `client_email`)
4. Give it **Editor** permission
5. Uncheck "Notify people"
6. Click **Share**

### Step 7: Update websites_config.json

Update the SyriaCar entry with your Sheet ID:

```json
{
  "id": "syriacar",
  "name": "SyriaCar",
  "google_sheet_id": "YOUR-ACTUAL-SHEET-ID-HERE",
  ...
}
```

Example (yours will be different):
```json
{
  "id": "syriacar",
  "name": "SyriaCar",
  "google_sheet_id": "1Oyhm4mrg7zz1pf3I-1_nhddTJsuscN8ppEn-Nr3UCFI",
  ...
}
```

### Step 8: Install Dependencies

```bash
pip install google-auth-oauthlib google-auth-httplib2 google-api-python-client
```

---

## ✅ Test the Integration

### Method 1: Via Web Interface
1. Start Flask: `python app.py`
2. Go to `http://localhost:5000/website/syriacar`
3. Click "Run Scraper Now"
4. Wait for completion
5. Check response for `sheets_written: true`
6. Open your Google Sheet - data should be there!

### Method 2: Via API
```bash
curl -X POST http://localhost:5000/api/run-scraper \
  -H "Content-Type: application/json" \
  -d '{"website_id": "syriacar"}'
```

**Expected Response**:
```json
{
  "status": "success",
  "items_scraped": 1020,
  "duration_seconds": 125.5,
  "sheets_written": true,
  "sheets_message": "Data successfully written to Google Sheet ID: ...",
  "statistics": {...}
}
```

---

## 🚨 Common Issues & Solutions

### Issue 1: "ModuleNotFoundError: No module named 'google.auth'"
**Solution**: Install Google libraries
```bash
pip install google-auth-oauthlib google-auth-httplib2 google-api-python-client
```

---

### Issue 2: "No valid Google Sheet ID configured"
**Solution**: Update `websites_config.json` with real Sheet ID
```json
{
  "id": "syriacar",
  "google_sheet_id": "1Oyhm4mrg7zz1pf3I-1_nhddTJsuscN8ppEn-Nr3UCFI"  ← Real ID
}
```

Do NOT use placeholder like `YOUR-SHEET-ID-HERE`

---

### Issue 3: "Error writing to Google Sheets: 403 Forbidden"
**Solution**: The service account doesn't have access to the sheet

1. Open your Google Sheet
2. Click **Share**
3. Check if service account email is shared
4. Make sure it has **Editor** permission
5. Try again

---

### Issue 4: "credentials.json not found"
**Solution**: Make sure file is in project root
```
D:\skyscraper\credentials.json
```

File should exist before running Flask.

---

### Issue 5: "Authentication failed"
**Solution**: Check credentials.json format

Must contain:
```json
{
  "type": "service_account",
  "project_id": "...",
  "private_key": "...",
  "client_email": "...",
  ...
}
```

---

## 📊 What Gets Written to Google Sheets

Each scraped car item has these fields:

| Field | Example | Description |
|-------|---------|-------------|
| id | syriacar_1_1713868800 | Unique identifier |
| website | syriacar | Source website |
| scraped_at | 2026-04-23T10:30:45 | When scraped |
| title | كيا Kia Sportage | Car title |
| price | 17,000 USD | Listing price |
| make | Kia | Car brand |
| model | Sportage | Car model |
| year | 2017 | Year manufactured |
| mileage | 225,000 كم | Distance traveled |
| location | حلب | City/location |
| fuel_type | بنزين | Gasoline/Diesel |
| transmission | أوتوماتيك | Manual/Automatic |
| body_type | إس يو في | SUV/Sedan/etc |
| condition | مستعملة | Used/New |
| origin | أمريكية | American/European/etc |
| link | https://syriacar.net/... | Detail page URL |
| description | Pipe-delimited text | Full description |
| image_url | https://... | Main image URL |
| image_alt | Car image | Image alt text |

---

## 🔄 How It Works

### Data Flow:
```
1. User clicks "Run Scraper"
                ↓
2. SyriaCarScraper.scrape() runs
   - Loads all 1020 cars
   - Extracts data from each car
   - Returns list of 1020 car dicts
                ↓
3. app.py converts to Google Sheets format:
   - Row 1: Headers
   - Rows 2-1021: Car data
                ↓
4. write_to_google_sheets() writes:
   - Updates headers in Sheet1!A1
   - Appends data starting Sheet1!A2
   - Formats header row (bold, colored)
                ↓
5. Response to browser:
   {
     "status": "success",
     "items_scraped": 1020,
     "sheets_written": true,
     ...
   }
                ↓
6. User opens Google Sheet
   - Sees all 1020 cars with data
```

---

## 💡 Tips & Best Practices

### Tip 1: Create Separate Sheets for Each Website
One Google Sheet per website makes it easier to manage data:
- SyriaCar Cars → `1Oyhm4mrg7zz1pf3I-1_nhddTJsuscN8ppEn-Nr3UCFI`
- Website 2 Cars → (separate Sheet ID)
- Website 3 Real Estate → (separate Sheet ID)

### Tip 2: Headers First
Always add header row before first scrape run with columns you want to track.

### Tip 3: Shared Folder
Create a shared folder in Google Drive for all scraper-related sheets:
- Right-click folder → Share with service account email
- All sheets in folder inherit permissions

### Tip 4: Regular Backups
Google Sheets auto-saves, but consider:
- Exporting to CSV weekly
- Archiving old sheet copies
- Using Google Sheets version history

### Tip 5: Monitor Writes
Watch for:
- `sheets_written: true` in API responses
- Data appearing in Google Sheet within seconds
- No "403 Forbidden" errors in logs

---

## 🔐 Security Notes

1. **Keep credentials.json safe**
   - Never commit to Git
   - Never share
   - Treat like password

2. **Service Account Permissions**
   - Only give Sheets API access
   - No other services needed

3. **Sheet Sharing**
   - Don't share the spreadsheet publicly
   - Only share with service account email
   - Use "Editor" role (allows data appending)

4. **Rotation**
   - Regenerate service account keys monthly
   - Delete old keys
   - Update credentials.json

---

## 📞 Troubleshooting Checklist

Before running scraper, verify:

- [ ] `credentials.json` exists in `D:\skyscraper\`
- [ ] credentials.json has valid JSON format
- [ ] Google Sheets API enabled in Cloud Console
- [ ] Service account created with Sheets API access
- [ ] Google Sheet created for SyriaCar
- [ ] Service account email has access to Sheet (Editor role)
- [ ] `websites_config.json` has real Sheet ID (not placeholder)
- [ ] Python dependencies installed: `pip install google-auth*`
- [ ] Flask app starts: `python app.py` (no import errors)
- [ ] API endpoint works: `curl http://localhost:5000/api/health`

---

## 📈 Next Steps

Once Google Sheets is working:

1. **Add more websites** (Website 2-7)
   - Create separate Google Sheets for each
   - Update `websites_config.json` with Sheet IDs
   - Enable websites one at a time

2. **Set up scheduling** (Phase 3)
   - Run scraper automatically (weekly, daily, etc.)
   - Use APScheduler for automation

3. **Create analytics** (Phase 3)
   - Analyze trends in Google Sheets
   - Add formulas for insights
   - Create dashboards

4. **Implement database** (Phase 4)
   - Use SQLite for historical data
   - Track price changes over time
   - Identify market trends

---

## ✨ Summary

Google Sheets integration is now active:

✅ Scraper collects data  
✅ Data automatically written to Google Sheet  
✅ Headers formatted automatically  
✅ API returns success/failure status  
✅ Data appears in Sheet within seconds  

**You're ready to scrape!** 🚀

Just make sure:
1. credentials.json is in place
2. Google Sheet is created and shared
3. Sheet ID is in websites_config.json
4. Dependencies are installed

Then run the scraper and watch the data flow into your Google Sheet!
