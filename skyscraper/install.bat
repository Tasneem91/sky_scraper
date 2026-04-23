@echo off
REM Installation Script for Web Scraper
REM This script automates the setup process

setlocal enabledelayedexpansion

echo.
echo ========================================
echo    Web Scraper Installation
echo ========================================
echo.

cd /d D:\skyscraper

REM Check if Python is installed
python --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Python is not installed or not in PATH
    echo Please install Python 3.8+ from https://www.python.org/
    echo Make sure to check "Add Python to PATH" during installation
    echo.
    pause
    exit /b 1
)

echo [1/4] Checking Python installation...
python --version
echo OK
echo.

REM Create necessary directories
echo [2/4] Creating directories...
if not exist "data" mkdir data
if not exist "data\images" mkdir data\images
if not exist "data\images\syriacar" mkdir data\images\syriacar
if not exist "logs" mkdir logs
echo OK - Created data, images, and logs directories
echo.

REM Install Python dependencies
echo [3/4] Installing Python dependencies...
echo This may take a few minutes...
echo.
pip install -r requirements.txt
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Failed to install dependencies
    echo Try running: pip install --upgrade pip
    echo Then: pip install -r requirements.txt
    pause
    exit /b 1
)
echo OK - All dependencies installed
echo.

REM Verify installation
echo [4/4] Verifying installation...
python -c "import selenium; import bs4; import requests; print('All imports successful!')"
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Some packages failed to import
    echo Please check the installation log above
    pause
    exit /b 1
)
echo OK - Installation verified
echo.

echo ========================================
echo    Installation Complete!
echo ========================================
echo.
echo Next steps:
echo.
echo 1. Set up Google Sheets API credentials:
echo    - Read SETUP_INSTRUCTIONS.md
echo.
echo 2. Test the scraper:
echo    - Run: run_scraper.bat
echo    - Or: python main.py
echo.
echo 3. Schedule for production:
echo    - Read SETUP_INSTRUCTIONS.md Section 6
echo.
echo For more details, see README.md or SETUP_INSTRUCTIONS.md
echo.

pause
