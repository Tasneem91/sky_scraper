@echo off
REM Web Scraper Runner - Production Mode
REM This script runs the scraper and actually updates Google Sheets
REM Used by Windows Task Scheduler for weekly automated runs

setlocal enabledelayedexpansion

cd /d D:\skyscraper

if not exist "logs" mkdir logs

REM Get current date and time for logging
for /f "tokens=2-4 delims=/ " %%a in ('date /t') do (set mydate=%%c-%%a-%%b)
for /f "tokens=1-2 delims=/:" %%a in ('time /t') do (set mytime=%%a-%%b)

REM Log start
echo [%mydate% %mytime%] Starting web scraper (production mode) >> logs\production.log

REM Run the scraper
python main.py >> logs\scraper_%mydate%_%mytime%.log 2>&1

if %ERRORLEVEL% EQU 0 (
    echo [%mydate% %mytime%] Scraper completed successfully >> logs\production.log
) else (
    echo [%mydate% %mytime%] ERROR: Scraper failed with code %ERRORLEVEL% >> logs\production.log
)

REM Don't pause in production mode (scheduled task)
exit /b %ERRORLEVEL%
