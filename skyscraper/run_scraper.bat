@echo off
REM Web Scraper Runner - Test Mode
REM This script runs the scraper in test mode (no actual updates)

setlocal enabledelayedexpansion

echo.
echo ========================================
echo    Web Scraper - Test Mode
echo ========================================
echo.

cd /d D:\skyscraper

if not exist "logs" mkdir logs

REM Get current date and time for logging
for /f "tokens=2-4 delims=/ " %%a in ('date /t') do (set mydate=%%c-%%a-%%b)
for /f "tokens=1-2 delims=/:" %%a in ('time /t') do (set mytime=%%a-%%b)

REM Run the scraper
python main.py >> logs\scraper_%mydate%_%mytime%.log 2>&1

if %ERRORLEVEL% EQU 0 (
    echo.
    echo ========================================
    echo    Scraper completed successfully!
    echo ========================================
    echo.
    echo Check logs folder for detailed output.
    echo.
) else (
    echo.
    echo ========================================
    echo    ERROR: Scraper failed!
    echo ========================================
    echo.
)

pause
