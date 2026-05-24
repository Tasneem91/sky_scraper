#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Check if Damazzle's API returns seller contact info without authentication.
Run: python debug_damazzle_api.py
"""
import sys, json, re, time, requests
sys.stdout.reconfigure(encoding='utf-8')
from playwright.sync_api import sync_playwright

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
      'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')

CAR_URL = 'https://damazzle.com/ads/mini-cooper-countryman-s-2012'
API_BASE = 'https://beta.damazzletech.com/api/api/v1/client'

# --- Step 1: find the numeric ad ID from the rendered page -----------------
with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    page    = browser.new_page(user_agent=UA)
    page.set_extra_http_headers({'Accept-Language': 'ar,en-US;q=0.9'})

    # Intercept ALL API responses to find the one that has the ad object
    api_responses = []
    def on_resp(resp):
        if 'damazzletech' in resp.url:
            try:
                body = resp.body()
                if body and len(body) < 50000:
                    api_responses.append({'url': resp.url, 'status': resp.status,
                                          'body': body.decode('utf-8', errors='ignore')})
            except Exception:
                pass
    page.on('response', on_resp)

    page.goto(CAR_URL, wait_until='domcontentloaded', timeout=30000)
    time.sleep(6)

    # Look for numeric ID in page HTML / JS
    html = page.content()
    ids_found = re.findall(r'"id"\s*:\s*(\d{4,7})', html)
    ids_from_url_in_html = re.findall(r'/ads/(\d{4,7})', html)
    print(f'Numeric IDs found in HTML ("id": N): {list(set(ids_found))[:10]}')
    print(f'Numeric IDs in /ads/ URLs in HTML  : {list(set(ids_from_url_in_html))[:10]}')

    # Try to extract from page JS state
    state = page.evaluate("""
        () => {
            // Try to find numeric ID in Angular component state
            const scripts = Array.from(document.querySelectorAll('script'));
            for (const s of scripts) {
                const m = s.textContent.match(/"id"\\s*:\\s*(\\d{5,7})/);
                if (m) return m[1];
            }
            // Try data attributes
            const els = document.querySelectorAll('[data-ad-id], [data-id]');
            for (const el of els) {
                const id = el.getAttribute('data-ad-id') || el.getAttribute('data-id');
                if (id && /^\\d+$/.test(id)) return id;
            }
            return null;
        }
    """)
    print(f'Ad ID from JS state: {state}')

    # Print all damazzletech API calls
    print(f'\n=== ALL damazzletech API RESPONSES ===')
    for r in api_responses:
        print(f'  {r["status"]} {r["url"]}')
        try:
            d = json.loads(r['body'])
            print(f'  JSON keys: {list(d.keys()) if isinstance(d, dict) else type(d).__name__}')
            # Look for phone/contact fields
            body_str = r['body']
            for pattern in [r'"phone"', r'"mobile"', r'"contact"', r'"whatsapp"', r'"tel"', r'09\d{8}', r'\+963\d{9}']:
                if re.search(pattern, body_str):
                    print(f'  *** FOUND {pattern!r} in response! ***')
                    idx = body_str.find('"phone"') if '"phone"' in body_str else body_str.find('"mobile"')
                    if idx >= 0:
                        print(f'  Snippet: {body_str[idx:idx+100]}')
        except Exception:
            pass

    browser.close()

# --- Step 2: try the API directly -----------------------------------------
print('\n=== DIRECT API CALLS (no auth) ===')

known_id = '424119'  # from the POST URL we saw in previous debug

headers = {
    'User-Agent': UA,
    'Accept': 'application/json',
    'Accept-Language': 'ar,en-US;q=0.9',
    'Origin': 'https://damazzle.com',
    'Referer': 'https://damazzle.com/',
}

endpoints = [
    f'{API_BASE}/ads/{known_id}',
    f'{API_BASE}/ads/mini-cooper-countryman-s-2012',
    f'{API_BASE}/ads/{known_id}/contact',
    f'{API_BASE}/ads/{known_id}/phone',
    f'https://beta.damazzletech.com/api/api/v1/ads/{known_id}',
]

for url in endpoints:
    try:
        r = requests.get(url, headers=headers, timeout=10)
        body = r.text[:500]
        has_phone = bool(re.search(r'09\d{8}|\+963\d{9}|"phone"|"mobile"', body))
        print(f'  GET {url}')
        print(f'      status={r.status_code}  has_phone={has_phone}')
        if has_phone or r.status_code == 200:
            print(f'      body={body[:300]}')
    except Exception as e:
        print(f'  GET {url} → ERROR: {e}')

# Also try POST click-button without auth
print(f'\n=== POST click-button WITHOUT AUTH ===')
try:
    r = requests.post(
        f'{API_BASE}/ads/{known_id}/click-button',
        headers={**headers, 'Content-Type': 'application/json'},
        json={'type': 'call'},
        timeout=10,
    )
    print(f'  status={r.status_code}')
    print(f'  body={r.text[:300]}')
except Exception as e:
    print(f'  ERROR: {e}')

print('\nDone.')
