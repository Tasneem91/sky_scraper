#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Intercept Damazzle API calls on a detail page to find the seller contact endpoint.
Run: python debug_damazzle_contact.py
"""
import sys, json, time
sys.stdout.reconfigure(encoding='utf-8')

from playwright.sync_api import sync_playwright

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
      'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')

CAR_URL  = 'https://damazzle.com/ads/mini-cooper-countryman-s-2012'
CAR_URL2 = 'https://damazzle.com/motors/cars/mini/2026-05-07/mini-cooper-countryman-s-2012'

captured_requests  = []
captured_responses = []

def on_request(req):
    url = req.url
    if any(k in url for k in ['api', 'ads', 'phone', 'contact', 'seller', 'call', 'whatsapp']):
        captured_requests.append(f'{req.method} {url}')

def on_response(resp):
    url = resp.url
    if any(k in url for k in ['api', 'ads', 'phone', 'contact', 'seller', 'call', 'whatsapp']):
        try:
            body = resp.body()
            if body and len(body) < 20000:
                try:
                    data = json.loads(body)
                    captured_responses.append({'url': url, 'status': resp.status, 'data': data})
                except Exception:
                    text = body.decode('utf-8', errors='ignore')
                    if any(c.isdigit() for c in text):
                        captured_responses.append({'url': url, 'status': resp.status, 'text': text[:300]})
        except Exception:
            pass

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    page = browser.new_page(user_agent=UA)
    page.set_extra_http_headers({'Accept-Language': 'ar,en-US;q=0.9'})
    page.on('request', on_request)
    page.on('response', on_response)

    print(f'Loading {CAR_URL} ...')
    try:
        page.goto(CAR_URL, wait_until='domcontentloaded', timeout=30000)
    except Exception as e:
        print(f'  goto error: {e}')
    time.sleep(5)

    print(f'\n=== ALL CAPTURED API REQUESTS ===')
    for r in captured_requests:
        print(f'  {r}')

    print(f'\n=== ALL CAPTURED API RESPONSES ===')
    for r in captured_responses:
        print(f'  STATUS {r["status"]} {r["url"]}')
        if 'data' in r:
            s = str(r['data'])
            print(f'  DATA: {s[:400]}')
        else:
            print(f'  TEXT: {r["text"][:200]}')

    # Now find all tel: and wa.me links on the rendered detail page
    print('\n=== TEL / WA LINKS ON RENDERED DETAIL PAGE ===')
    links = page.evaluate("""
        () => Array.from(document.querySelectorAll('a[href^="tel:"], a[href*="wa.me"]'))
                   .map(a => ({ href: a.href, text: a.textContent.trim().substring(0, 40) }))
    """)
    for l in links:
        print(f'  href={l["href"]}  text={l["text"]!r}')

    # Find all buttons related to contact
    print('\n=== CONTACT BUTTONS ===')
    btns = page.evaluate("""
        () => Array.from(document.querySelectorAll('a, button'))
                   .filter(el => {
                       const t = el.textContent.trim();
                       return ['اتصل', 'واتساب', 'تواصل', 'call', 'whatsapp', 'رقم'].some(k => t.includes(k));
                   })
                   .map(el => ({
                       tag: el.tagName,
                       text: el.textContent.trim().substring(0, 30),
                       href: el.getAttribute('href'),
                       class: el.className.substring(0, 60)
                   }))
    """)
    for b in btns:
        print(f'  <{b["tag"]}> {b["text"]!r}  href={b["href"]}')

    # Try clicking the call button and see what happens (network intercept)
    captured_responses.clear()
    captured_requests.clear()
    print('\n=== CLICKING CALL BUTTON ===')
    call_btns = page.query_selector_all('a[href*="extra=call"], button')
    for btn in call_btns:
        try:
            text = btn.inner_text().strip()
            if 'اتصل' in text or 'call' in text.lower():
                print(f'  Clicking: {text!r}')
                btn.click()
                time.sleep(3)
                # Check for any phone numbers that appeared
                phone_in_dom = page.evaluate("""
                    () => {
                        const tel = document.querySelector('a[href^="tel:"]');
                        if (tel) return tel.href;
                        const m = document.body.innerText.match(/09\\d{8}|\\+963\\d{9}/);
                        return m ? m[0] : null;
                    }
                """)
                print(f'  Phone after click: {phone_in_dom}')
                print(f'  New requests: {captured_requests[:5]}')
                for r in captured_responses:
                    print(f'  Response: {r["url"]} → {str(r.get("data",""))[:200]}')
                break
        except Exception as e:
            pass

    browser.close()

print('\nDone.')
