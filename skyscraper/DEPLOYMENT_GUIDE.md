# Deployment Guide - Production Setup

This guide covers setting up the web scraper for production use with Windows Task Scheduler for automated weekly runs.

## Prerequisites

Before deploying to production, ensure:
- ✅ Test run completed successfully
- ✅ Google Sheet created and receiving data
- ✅ All dependencies installed
- ✅ Logs reviewed and no errors
- ✅ Image downloads working correctly

## Step 1: Prepare for Production

### 1.1 Update Configuration

Edit `main.py` and set your spreadsheet ID:

```python
if __name__ == "__main__":
    orchestrator = ScraperOrchestrator(
        website_key="syriacar",
        spreadsheet_id="YOUR_ACTUAL_SHEET_ID"  # ← Update this
    )
    result = orchestrator.run(test_mode=False)  # ← Change to False
```

Get your spreadsheet ID from the Google Sheets URL:
```
https://docs.google.com/spreadsheets/d/1jXrX2L3kZm5n6pQ9r2sT7uV8wX9yZ0aB1cD2eF/edit
                                         ↑ This is your ID
```

### 1.2 Verify Configuration

```bash
cd D:\skyscraper
python main.py  # Run once to verify everything works
```

Check the output:
- Should show scraped count
- Should show unique count
- Should show rows added
- No errors in console

## Step 2: Set Up Windows Task Scheduler

### 2.1 Create Batch File

A batch file has already been created: `run_scraper_production.bat`

Verify it exists and contains:
```batch
@echo off
cd /d D:\skyscraper
python main.py >> logs\scraper_%date%_%time%.log 2>&1
```

### 2.2 Open Task Scheduler

Press `Win + R` and type:
```
taskschd.msc
```

### 2.3 Create Basic Task

1. In the left panel, click "Create Basic Task..."
2. Enter task name: `Car Web Scraper - SyriaCar`
3. Enter description: `Weekly scraper for car data from syriacar.net`
4. Click "Next"

### 2.4 Set Trigger

1. Select "Weekly"
2. Choose:
   - **Start date**: Today's date
   - **Recur every**: 1 week
   - **Day**: Monday (or your preferred day)
   - **Time**: 09:00 (or your preferred time)
3. Click "Next"

### 2.5 Set Action

1. Select "Start a program"
2. Enter:
   - **Program/script**: `C:\Windows\System32\cmd.exe`
   - **Add arguments**: `/c "D:\skyscraper\run_scraper_production.bat"`
   - **Start in**: `D:\skyscraper`
3. Click "Next"

### 2.6 Review and Finish

1. Review all settings
2. Check "Open the Properties dialog for this task when I click Finish"
3. Click "Finish"

### 2.7 Advanced Settings (Properties Dialog)

1. **General tab**:
   - Check "Run with highest privileges"
   - Select "Run whether user is logged in or not"

2. **Triggers tab**:
   - Select your trigger
   - Click "Edit"
   - Check "Enabled"
   - Click "OK"

3. **Conditions tab**:
   - Uncheck "Start the task only if the computer is on AC power"
   - Check "Wake the computer to run this task" (optional)

4. **Settings tab**:
   - Check "Allow task to be run on demand"
   - Check "If the task fails, restart every": 30 minutes
   - Set "Attempt to restart up to": 3 times

5. Click "OK" to save

## Step 3: Test the Scheduled Task

### 3.1 Manual Trigger Test

1. Open Task Scheduler
2. Find your task in the list
3. Right-click and select "Run"
4. Wait 2-5 minutes for completion
5. Check logs folder for new log file
6. Verify Google Sheet was updated

### 3.2 Check Logs

```bash
# View latest log
type "D:\skyscraper\logs\scraper_*.log" | tail -20
```

Or open the logs folder and check the most recent file.

### 3.3 Verify Google Sheet

1. Open your Google Sheet
2. Check for new rows
3. Verify images are linked correctly
4. Check timestamps in "scraped_at" column

## Step 4: Set Up Monitoring

### 4.1 Email Notifications (Optional)

To get email notifications of task completion:

1. In Task Scheduler, right-click your task
2. Select "Properties"
3. Go to "Actions" tab
4. Add a second action:
   - **Action**: "Send an email"
   - **To**: your@email.com
   - **Subject**: "Car Scraper Completed"
   - **Body**: "Web scraper run completed. Check logs for details."
   - **Mail server**: your.smtp.server.com
5. Click "OK"

### 4.2 Monitor Production Log

Create a simple Python script to monitor:

```python
# monitor.py
import os
from pathlib import Path
from datetime import datetime

logs_dir = Path("D:/skyscraper/logs")
log_file = logs_dir / "production.log"

if log_file.exists():
    with open(log_file, 'r') as f:
        lines = f.readlines()
        for line in lines[-20:]:  # Last 20 lines
            print(line.strip())
else:
    print("No production log found yet")
```

Run with:
```bash
python monitor.py
```

### 4.3 Check Task History

In Task Scheduler:
1. Find your task
2. Click "History" tab
3. See all execution records
4. Check for failures or warnings

## Step 5: Production Checklist

Before considering the deployment complete:

- [ ] Initial test run completed successfully
- [ ] Google Sheet created and populated
- [ ] Task Scheduler task created
- [ ] Manual trigger test successful
- [ ] Log file generated in logs folder
- [ ] Google Sheet updated with new data
- [ ] Images downloaded and linked correctly
- [ ] No errors in logs
- [ ] Task scheduled for correct day/time
- [ ] "Run with highest privileges" enabled
- [ ] "Run whether user is logged in" enabled
- [ ] First automatic run completed (wait for scheduled time or test)

## Step 6: Maintenance

### Regular Checks

**Weekly** (after each run):
- [ ] Check latest log file
- [ ] Verify Google Sheet has new data
- [ ] Check for any errors or warnings

**Monthly**:
- [ ] Review log file sizes (archive old logs if needed)
- [ ] Check image folder size (cleanup if needed)
- [ ] Verify deduplication is working

**Quarterly**:
- [ ] Review website structure (selectors might need updating)
- [ ] Check for any API changes
- [ ] Test manual run to ensure system still works

### Log Management

```bash
# Archive old logs (quarterly)
# Compress logs older than 90 days
# Keep recent 10 logs for troubleshooting
```

### Troubleshooting Production Issues

| Issue | Symptoms | Solution |
|-------|----------|----------|
| Task not running | No new sheet data | Check Task Scheduler history for errors |
| Script errors | Error in log file | Check website structure, update selectors |
| No new data | Duplicates detected | Review deduplication logic |
| Permission denied | Log shows access error | Run task with "highest privileges" |
| Network issues | Timeout errors in log | Check internet connection |

## Step 7: Scaling to Multiple Websites

Once the first website is working, you can add more:

### 7.1 Add New Website Configuration

Edit `config.py`:
```python
WEBSITE_CONFIG = {
    "syriacar": { ... },  # Existing
    "newsite": {          # New website
        "url": "https://newsite.com/cars",
        "name": "New Site",
        "selectors": { ... },
        "image_folder": str(IMAGES_DIR / "newsite"),
    }
}
```

### 7.2 Create New Google Sheet

Create separate sheet for each website.

### 7.3 Create New Task

In Task Scheduler:
1. Create another basic task with different name
2. Set different schedule (e.g., Tuesday instead of Monday)
3. Modify `run_scraper_production.bat` or create new version:

```batch
@echo off
cd /d D:\skyscraper
python -c "from main import ScraperOrchestrator; ScraperOrchestrator('newsite', 'SHEET_ID').run()" >> logs\newsite_%date%_%time%.log 2>&1
```

### 7.4 Test Each Website

Run each manually before relying on automation:
```bash
python -c "from main import ScraperOrchestrator; ScraperOrchestrator('newsite', 'SHEET_ID').run(test_mode=False)"
```

## Performance & Optimization

### Current Performance

- **Typical scrape time**: 1-5 minutes (depends on website)
- **Image download**: 10-20 seconds
- **Deduplication**: 1-2 seconds
- **Sheet upload**: 5-10 seconds
- **Total typical run**: 5-10 minutes

### Optimization Tips

1. **Increase delays if hitting rate limits**:
   ```python
   "delay_between_requests": 3,  # Increase from 2
   ```

2. **Reduce image size**:
   - Compress images during download
   - Or skip certain image types

3. **Optimize selectors**:
   - More specific selectors are faster
   - Avoid unnecessary element searches

4. **Batch Google Sheets operations**:
   - Already optimized in current version

## Troubleshooting Deployment

### Task Not Running

1. Check Task Scheduler history
2. Verify user account has permissions
3. Check "Run with highest privileges" is enabled
4. Test manually: right-click task → Run

### No Data in Sheet After Run

1. Check logs folder for error messages
2. Verify spreadsheet ID is correct
3. Verify service account has access
4. Test manual run: `python main.py`

### Images Not Downloading

1. Check image folder permissions
2. Verify website images are public
3. Check logs for specific error messages
4. Test with different User-Agent

### Old Logs Taking Space

Archive strategy:
```bash
# Keep logs for 30 days, archive older ones
# Backup critical production logs
# Monitor logs folder size
```

## Backup & Recovery

### Backup Important Files

Backup weekly to external drive:
- `data/images/` - All downloaded images
- `logs/` - Execution logs
- `config.py` - Your configuration
- Google Sheet itself (export as CSV)

### Recovery Procedure

If something goes wrong:

1. **Lost data**: 
   - Check Google Sheet (typically have backup)
   - Review logs to see what was uploaded

2. **Broken selectors**:
   - Website changed structure
   - Update selectors in config.py
   - Test with new selectors before scheduling

3. **Task not running**:
   - Recreate task in Task Scheduler
   - Use deployment guide steps

## Performance Monitoring

Create a monitoring dashboard (optional):

```python
# analyze_runs.py
import os
from pathlib import Path
from datetime import datetime

logs_dir = Path("D:/skyscraper/logs")

for log_file in sorted(logs_dir.glob("scraper_*.log")):
    with open(log_file) as f:
        content = f.read()
        if "Successfully scraped" in content:
            # Extract metrics
            print(f"{log_file.name}: SUCCESS")
```

## Summary

Your production deployment is now:
✅ **Automated** - Runs on schedule automatically
✅ **Monitored** - All operations logged
✅ **Reliable** - Error handling and recovery
✅ **Scalable** - Easy to add new websites
✅ **Maintained** - Regular checks ensure operation

The scraper will run every week at your specified time, collect new data, prevent duplicates, and keep your Google Sheet updated automatically!

---

## Quick Command Reference

```bash
# Check last run
type D:\skyscraper\logs\production.log

# Manual test
cd D:\skyscraper && python main.py

# View latest log
Get-Content (Get-ChildItem D:\skyscraper\logs\*.log | Sort-Object LastWriteTime -Descending | Select-Object -First 1).FullName -Tail 20

# Check task status
Get-ScheduledTask | Where-Object {$_.TaskName -like "*Scraper*"}
```

