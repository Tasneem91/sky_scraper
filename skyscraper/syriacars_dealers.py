#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SyriaCarsDealers — Standalone Scraper  (v2)
============================================
Extracts ALL dealer profiles from https://syriacars.net/dealers-list/
and writes them to a "Dealers" tab in Google Sheets.

HOW IT LOADS ALL DEALERS
-------------------------
The page loads 12 dealers initially.  A hidden AJAX endpoint returns 12
more per call (offset=12, 24, 36 …).  This script calls that endpoint
directly until the response is empty — no repeated clicking needed.

PHONE NUMBERS
-------------
The site masks phones (963*******).  Full numbers are unlocked after login.
Pass --username / --password to log in automatically; the script will then
reveal every phone via admin-ajax.php before saving.

SETUP
-----
pip install requests gspread google-auth google-auth-oauthlib
pip install google-api-python-client playwright
playwright install chromium

USAGE
-----
  python syriacars_dealers.py
  python syriacars_dealers.py --username me@mail.com --password secret123
"""

import argparse
import io
import json
import logging
import os
import re
import sys
import time
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import requests as _requests
import gspread
from google.auth.transport.requests import Request
from google.oauth2 import credentials as google_creds_module
from google_auth_oauthlib.flow import InstalledAppFlow
from playwright.sync_api import sync_playwright, Page
from bs4 import BeautifulSoup

# ── Logging ───────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)-8s %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('syriacars_dealers.log', encoding='utf-8'),
    ],
)
logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────────────

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

OAUTH_CLIENT_FILE = os.path.join(
    SCRIPT_DIR,
    'client_secret_798447276011-9bfpmjkfo8et8c2r4omri13kbh7h5202.apps.googleusercontent.com.json',
)
OAUTH_TOKEN_FILE = os.path.join(SCRIPT_DIR, 'oauth_token.json')

SHEET_ID    = '1TGaxrXEjiwihwceN2LBiS6BrR0E3rUjnaBJxI7a9mBo'
DEALERS_TAB = 'Dealers'

LIST_URL    = 'https://syriacars.net/dealers-list/'
LOGIN_URL   = 'https://syriacars.net/my-account/'
AJAX_URL    = 'https://syriacars.net/wp-admin/admin-ajax.php'
BATCH_SIZE  = 12   # dealers per API call (site default)

UA = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
    'AppleWebKit/537.36 (KHTML, like Gecko) '
    'Chrome/120.0.0.0 Safari/537.36'
)

SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
]

# ── Sheet columns ─────────────────────────────────────────────────────────────

COLUMNS: List[str] = [
    'scraped_at',
    'dealer_name',
    'cars_count',
    'phone',          # real phone (after login) or empty
    'phone_masked',   # public prefix, e.g. "963*******"
    'location',
    'profile_url',
    'dealer_id',
]

# ── OAuth2 ────────────────────────────────────────────────────────────────────


def _get_oauth_credentials():
    creds = None
    if os.path.exists(OAUTH_TOKEN_FILE):
        try:
            with open(OAUTH_TOKEN_FILE, encoding='utf-8') as fh:
                creds = google_creds_module.Credentials.from_authorized_user_info(
                    json.load(fh), SCOPES
                )
        except Exception as exc:
            logger.warning(f'Could not load cached token: {exc}')
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(OAUTH_CLIENT_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(OAUTH_TOKEN_FILE, 'w', encoding='utf-8') as fh:
            fh.write(creds.to_json())
    return creds


# ── HTML parsing helpers ──────────────────────────────────────────────────────


def _clean(text) -> str:
    if not text:
        return ''
    return ' '.join(str(text).split())


def _parse_dealer_row(row) -> Dict:
    """Parse one <tr class='stm-single-dealer'> into a dict."""
    d: Dict = {}

    title_a = row.select_one('.dealer-info .title a')
    if title_a:
        d['dealer_name'] = _clean(title_a.get_text())
        d['profile_url'] = title_a.get('href', '')

    count_div = row.select_one('.dealer-labels.heading-font')
    d['cars_count'] = _clean(count_div.get_text()) if count_div else ''

    phone_div = row.select_one('.phone.heading-font')
    d['phone_masked'] = _clean(phone_div.get_text()) if phone_div else ''

    loc_div = row.select_one('.dealer-location-label')
    loc = _clean(loc_div.get_text()) if loc_div else ''
    d['location'] = '' if loc in ('غير معروف', 'غير_معروف', 'Unknown', '-') else loc

    span = row.select_one('span.stm-show-number')
    d['dealer_id'] = span.get('data-id', '') if span else ''

    d['phone'] = ''   # filled later if logged in
    return d


# ── Page loading & nonce extraction ──────────────────────────────────────────


def _load_page_and_get_nonces(page: Page) -> Tuple[str, str, str]:
    """
    Load the dealers list page and return (sec_nonce, form_nonce, html).
    sec_nonce  = stm_security_nonce  (JS variable)
    form_nonce = _wpnonce            (hidden form field)
    """
    logger.info(f'Loading {LIST_URL} …')
    try:
        page.goto(LIST_URL, wait_until='networkidle', timeout=45000)
    except Exception:
        try:
            page.goto(LIST_URL, wait_until='domcontentloaded', timeout=30000)
        except Exception:
            pass
    time.sleep(4)
    html = page.content()

    sec_nonce  = ''
    form_nonce = ''

    m = re.search(r'stm_security_nonce\s*=\s*["\']([^"\']+)', html)
    if m:
        sec_nonce = m.group(1)

    # _wpnonce is inside the hidden dealer filter form
    m2 = re.search(r'name="_wpnonce"\s+value="([^"]+)"', html)
    if m2:
        form_nonce = m2.group(1)

    logger.info(f'Nonces: security={sec_nonce!r}  wpnonce={form_nonce!r}')
    return sec_nonce, form_nonce, html


# ── Fetch ALL dealers via AJAX ────────────────────────────────────────────────


def _fetch_all_dealers(page: Page, sec_nonce: str, form_nonce: str, initial_html: str) -> List[Dict]:
    """
    1. Parse the initial 12 dealers from the page HTML.
    2. Keep calling the AJAX load-more endpoint (offset=12, 24, …) until empty.
    Returns a deduplicated list of dealer dicts.
    """
    all_dealers: List[Dict] = []
    seen_ids: set = set()

    def _add_from_soup(soup):
        rows = soup.find_all('tr', class_='stm-single-dealer')
        for row in rows:
            d = _parse_dealer_row(row)
            did = d.get('dealer_id', '') or d.get('dealer_name', '')
            if did and did not in seen_ids:
                seen_ids.add(did)
                all_dealers.append(d)
        return len(rows)

    # Initial page dealers
    soup0 = BeautifulSoup(initial_html, 'html.parser')
    initial_count = _add_from_soup(soup0)
    logger.info(f'Initial page: {initial_count} dealers')

    # Build session from Playwright cookies
    cookies = {c['name']: c['value'] for c in page.context.cookies()}
    sess = _requests.Session()
    sess.cookies.update(cookies)
    sess.headers.update({
        'User-Agent': UA,
        'Referer': LIST_URL,
        'Accept': 'application/json, text/javascript, */*; q=0.01',
        'X-Requested-With': 'XMLHttpRequest',
        'Accept-Language': 'ar,en-US;q=0.9',
    })

    offset = BATCH_SIZE
    while True:
        params = {
            'stm_dealer_show_taxonomies': '',
            'stm_sort_by': 'cars',
            '_wpnonce': form_nonce,
            '_wp_http_referer': '/dealers-list/',
            'loc': '',
            'offset': offset,
            'ajax_action': 'stm_load_dealers_list',
            'security': sec_nonce,
        }
        try:
            r = sess.get(LIST_URL, params=params, timeout=20)
            if r.status_code != 200:
                logger.warning(f'  offset={offset}  status={r.status_code} — stopping')
                break
            data = r.json()
            html_chunk = data.get('user_html', '')
            if not html_chunk or html_chunk.strip() == '':
                logger.info(f'  offset={offset}  → empty response — all dealers loaded')
                break
            chunk_soup = BeautifulSoup(html_chunk, 'html.parser')
            added = _add_from_soup(chunk_soup)
            logger.info(f'  offset={offset}  → +{added} dealers (total so far: {len(all_dealers)})')
            if added == 0:
                break
            offset += BATCH_SIZE
            time.sleep(1.0)
        except Exception as exc:
            logger.error(f'  AJAX error at offset={offset}: {exc}')
            break

    logger.info(f'Total dealers fetched: {len(all_dealers)}')
    return all_dealers


# ── Login & phone reveal ──────────────────────────────────────────────────────


def _login(page: Page, username: str, password: str) -> bool:
    """Log in to SyriasCars; return True on success."""
    logger.info(f'Logging in as {username!r} …')
    try:
        page.goto(LOGIN_URL, wait_until='networkidle', timeout=30000)
    except Exception:
        pass
    time.sleep(3)

    try:
        # Fill username / email
        page.fill('input[name="username"], input[name="email"], input[type="email"], #username', username)
        time.sleep(0.5)
        # Fill password
        page.fill('input[name="password"], input[type="password"], #password', password)
        time.sleep(0.5)
        # Submit
        page.click('button[type="submit"], input[type="submit"], .login-submit button')
        time.sleep(4)
    except Exception as exc:
        logger.warning(f'Login form interaction error: {exc}')
        return False

    # Check if login succeeded (URL changed away from login page or user menu appears)
    current_url = page.url
    html = page.content()
    if 'logout' in html.lower() or 'my-account' not in current_url:
        logger.info('Login successful.')
        return True
    else:
        logger.warning('Login may have failed — check credentials.')
        return False


def _reveal_phones(page: Page, dealers: List[Dict]) -> None:
    """
    For each dealer, call the WordPress AJAX phone-reveal endpoint.
    Requires the Playwright browser to already be logged in.
    """
    # Refresh nonce from the page context (nonce may change after login)
    html = page.content()
    m = re.search(r'stm_security_nonce\s*=\s*["\']([^"\']+)', html)
    sec_nonce = m.group(1) if m else ''

    if not sec_nonce:
        # Navigate to dealers list to get fresh nonce
        try:
            page.goto(LIST_URL, wait_until='networkidle', timeout=30000)
        except Exception:
            pass
        time.sleep(3)
        html = page.content()
        m = re.search(r'stm_security_nonce\s*=\s*["\']([^"\']+)', html)
        sec_nonce = m.group(1) if m else ''

    logger.info(f'Revealing phones with nonce={sec_nonce!r} …')

    revealed = 0
    for i, dealer in enumerate(dealers, 1):
        did = dealer.get('dealer_id', '')
        name = dealer.get('dealer_name', '?')
        if not did:
            continue
        try:
            result = page.evaluate(f"""async () => {{
                const resp = await fetch(
                    '{AJAX_URL}?phone_owner_id={did}&listing_id=0' +
                    '&action=stm_ajax_get_seller_phone&security={sec_nonce}',
                    {{headers: {{'X-Requested-With': 'XMLHttpRequest'}}}}
                );
                return await resp.text();
            }}""")
            # Response is a JSON-encoded string: "\"963945273368\"" or "\"\""
            phone = result.strip().strip('"').strip()
            if phone and phone not in ('', 'null', 'false', '0'):
                dealer['phone'] = '+' + phone if not phone.startswith('+') else phone
                revealed += 1
                logger.info(f'  [{i}] {name:35s} → {dealer["phone"]}')
            else:
                logger.info(f'  [{i}] {name:35s} → (no phone returned)')
        except Exception as exc:
            logger.warning(f'  [{i}] {name}: phone reveal error: {exc}')
        time.sleep(0.5)

    logger.info(f'Phone numbers revealed: {revealed}/{len(dealers)}')


# ── Google Sheets helpers ─────────────────────────────────────────────────────


def _get_or_create_dealers_tab(gc) -> gspread.Worksheet:
    spreadsheet = gc.open_by_key(SHEET_ID)
    try:
        ws = spreadsheet.worksheet(DEALERS_TAB)
        logger.info(f'Using existing "{DEALERS_TAB}" tab.')
    except gspread.exceptions.WorksheetNotFound:
        logger.info(f'Creating "{DEALERS_TAB}" tab …')
        ws = spreadsheet.add_worksheet(title=DEALERS_TAB, rows=500, cols=len(COLUMNS))
    return ws


def _write_to_sheet(ws: gspread.Worksheet, dealers: List[Dict]):
    # Write headers
    ws.update([COLUMNS], 'A1')
    # Write data
    scraped_at = datetime.now().isoformat()
    rows = []
    for d in dealers:
        d['scraped_at'] = scraped_at
        row = [str(d.get(col, '') or '') for col in COLUMNS]
        rows.append(row)
    if rows:
        ws.batch_clear(['A2:Z1000'])
        ws.update(rows, 'A2', value_input_option='RAW')
    logger.info(f'Wrote {len(rows)} rows to "{DEALERS_TAB}" tab.')


# ── Main ──────────────────────────────────────────────────────────────────────


def main(username: Optional[str] = None, password: Optional[str] = None):
    logger.info('=' * 62)
    logger.info(f'SyriaCarsDealers v2  {datetime.now().isoformat()}')
    logger.info('=' * 62)

    # Google auth
    logger.info('Authenticating with Google …')
    creds = _get_oauth_credentials()
    gc = gspread.authorize(creds)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page(user_agent=UA)
        page.set_viewport_size({'width': 1280, 'height': 900})
        page.set_extra_http_headers({'Accept-Language': 'ar,en-US;q=0.9'})

        # Step 1: Load page, get nonces, get initial 12 dealers
        sec_nonce, form_nonce, initial_html = _load_page_and_get_nonces(page)

        if not sec_nonce or not form_nonce:
            logger.error('Could not extract nonces from page — aborting.')
            browser.close()
            return

        # Step 2: Fetch all dealers via AJAX
        dealers = _fetch_all_dealers(page, sec_nonce, form_nonce, initial_html)

        if not dealers:
            logger.error('No dealers found.')
            browser.close()
            return

        # Step 3 (optional): Login + reveal phone numbers
        if username and password:
            logged_in = _login(page, username, password)
            if logged_in:
                _reveal_phones(page, dealers)
            else:
                logger.warning('Skipping phone reveal (login failed).')
        else:
            logger.info('No credentials provided — phones will be masked only.')
            logger.info('Run with --username EMAIL --password PASS to reveal phones.')

        browser.close()

    # Step 4: Write to Google Sheets
    logger.info('\nWriting to Google Sheets …')
    ws = _get_or_create_dealers_tab(gc)
    _write_to_sheet(ws, dealers)

    # Summary
    logger.info('\n' + '=' * 62)
    logger.info('DEALER SUMMARY')
    logger.info('=' * 62)
    for d in dealers:
        phone_display = d.get('phone') or d.get('phone_masked', '—')
        logger.info(
            f'  {d.get("dealer_name","?"):40s} '
            f'cars={d.get("cars_count","?"):6s}  '
            f'phone={phone_display:15s}  '
            f'loc={d.get("location","—")}'
        )
    logger.info(f'\nTotal: {len(dealers)} dealers')
    logger.info(f'Sheet: https://docs.google.com/spreadsheets/d/{SHEET_ID}')


if __name__ == '__main__':
    if sys.stdout.encoding != 'utf-8':
        sys.stdout.reconfigure(encoding='utf-8')

    parser = argparse.ArgumentParser(description='SyriaCarsDealers scraper v2')
    parser.add_argument('--username', metavar='EMAIL',
                        help='SyriaCars account email (to reveal full phone numbers)')
    parser.add_argument('--password', metavar='PASS',
                        help='SyriaCars account password')
    args = parser.parse_args()

    if not os.path.exists(OAUTH_CLIENT_FILE):
        print(f'ERROR: OAuth2 client secret not found:\n  {OAUTH_CLIENT_FILE}')
        sys.exit(1)

    main(username=args.username, password=args.password)
