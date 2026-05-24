#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Find what JS handles the load-more click and intercept ALL network requests.
Also check the exact button HTML and try clicking via JS.
"""
import sys, re, time
sys.stdout.reconfigure(encoding='utf-8')
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'

all_requests = []

def on_request(req):
    # Capture everything except images/css/fonts
    url = req.url
    if not any(ext in url for ext in ['.png', '.jpg', '.gif', '.css', '.woff', '.ttf', '.svg', '.ico']):
        try:
            all_requests.append({
                'url': url,
                'method': req.method,
                'post': (req.post_data_buffer or b'')[:300],
            })
        except Exception:
            pass

all_responses = []

def on_response(resp):
    url = resp.url
    if not any(ext in url for ext in ['.png', '.jpg', '.gif', '.css', '.woff', '.ttf', '.svg', '.ico', '.js']):
        try:
            body = resp.body()[:500]
            all_responses.append({'url': url, 'status': resp.status, 'body': body.decode('utf-8', errors='ignore')})
        except Exception:
            pass

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    page = browser.new_page(user_agent=UA)
    page.set_viewport_size({'width': 1280, 'height': 900})
    page.set_extra_http_headers({'Accept-Language': 'ar,en-US;q=0.9'})
    page.on('request', on_request)
    page.on('response', on_response)

    print('Loading dealers-list ...')
    try:
        page.goto('https://syriacars.net/dealers-list/', wait_until='networkidle', timeout=45000)
    except Exception:
        pass
    time.sleep(4)

    html = page.content()
    soup = BeautifulSoup(html, 'html.parser')
    rows = soup.find_all('tr', class_='stm-single-dealer')
    print(f'Dealers on load: {len(rows)}')

    # Find the exact HTML of the load-more button
    print('\n=== Load-more button HTML ===')
    more_btn = soup.find('a', string=re.compile(r'اعرض المزيد|اقرأ المزيد'))
    if more_btn:
        print(str(more_btn))
        print(f'Parent: {str(more_btn.parent)[:300]}')
        print(f'Grandparent class: {more_btn.parent.parent.get("class")}')

    # Get all JS event data from the page about this button
    print('\n=== JS click handler on the button ===')
    js_info = page.evaluate('''() => {
        const btn = document.querySelector('a.stm-load-more-dealers, [class*="load-more"], a[href="#"]');
        // Try to find by text
        const allLinks = document.querySelectorAll('a');
        let targetBtn = null;
        for (const a of allLinks) {
            if (a.textContent.trim() === 'اعرض المزيد' || a.textContent.trim() === 'اقرأ المزيد') {
                targetBtn = a;
                break;
            }
        }
        if (!targetBtn) return 'button not found';
        return {
            tagName: targetBtn.tagName,
            className: targetBtn.className,
            id: targetBtn.id,
            outerHTML: targetBtn.outerHTML,
            parentHTML: targetBtn.parentElement.outerHTML.substring(0, 300),
            grandparentClass: targetBtn.parentElement.parentElement.className,
        };
    }''')
    print(f'Button info: {js_info}')

    # Scroll to the button and click via JS trigger
    print('\n=== Scrolling to button and clicking via JS ===')
    page.evaluate('''() => {
        const allLinks = document.querySelectorAll("a");
        for (const a of allLinks) {
            if (a.textContent.trim() === "اعرض المزيد" || a.textContent.trim() === "اقرأ المزيد") {
                a.scrollIntoView();
                a.click();
                return;
            }
        }
    }''')
    time.sleep(6)

    html2 = page.content()
    soup2 = BeautifulSoup(html2, 'html.parser')
    rows2 = soup2.find_all('tr', class_='stm-single-dealer')
    print(f'Dealers after JS click: {len(rows2)}')

    # Clear and try Playwright click
    all_requests.clear()
    all_responses.clear()

    print('\n=== Scrolling to button and using Playwright click ===')
    btn_loc = page.locator('a').filter(has_text='اعرض المزيد').first
    if btn_loc.count() > 0:
        btn_loc.scroll_into_view_if_needed()
        time.sleep(1)
        btn_loc.click(force=True)
        time.sleep(6)

    html3 = page.content()
    soup3 = BeautifulSoup(html3, 'html.parser')
    rows3 = soup3.find_all('tr', class_='stm-single-dealer')
    print(f'Dealers after Playwright forced click: {len(rows3)}')

    browser.close()

print('\n=== Network requests after button click ===')
for r in all_requests:
    print(f'  [{r["method"]}] {r["url"]}')
    if r['post']:
        print(f'        POST: {r["post"]}')

print('\n=== Network responses after button click ===')
for r in all_responses:
    if r['status'] != 200 or 'dealer' in r['url'].lower() or 'ajax' in r['url'].lower():
        print(f'  [{r["status"]}] {r["url"]}')
        print(f'  body: {r["body"][:300]}')

print('\nDone.')
