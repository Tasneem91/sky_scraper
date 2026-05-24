"""
Intercept the network request Carsy makes when the contact button is clicked.
This tells us the exact API endpoint for phone numbers.
Usage: python inspect_carsy_contact.py
"""
import sys, json
sys.stdout.reconfigure(encoding='utf-8')

from playwright.sync_api import sync_playwright
import time

UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
CAR_URL = 'https://carsy.app/cars/2043'

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True)
    context = browser.new_context(user_agent=UA)

    # Capture all network requests
    captured = []
    def on_request(req):
        if any(k in req.url for k in ['contact', 'phone', 'call', 'whatsapp', 'api', 'cars']):
            captured.append({'type': 'request', 'method': req.method, 'url': req.url})

    def on_response(resp):
        if any(k in resp.url for k in ['contact', 'phone', 'call', 'whatsapp', 'api', 'cars']):
            try:
                body = resp.body()
                if body and len(body) < 5000:
                    try:
                        data = json.loads(body)
                        captured.append({'type': 'response', 'url': resp.url,
                                         'status': resp.status, 'data': data})
                    except Exception:
                        text = body.decode('utf-8', errors='ignore')
                        if any(c.isdigit() for c in text):
                            captured.append({'type': 'response_text', 'url': resp.url,
                                             'status': resp.status, 'text': text[:500]})
            except Exception:
                pass

    page = context.new_page()
    page.on('request', on_request)
    page.on('response', on_response)

    print(f"Loading {CAR_URL} ...")
    page.goto(CAR_URL, wait_until='load', timeout=30000)
    time.sleep(3)

    # Find and print all buttons on the page
    buttons = page.evaluate("""
        () => Array.from(document.querySelectorAll('button, a'))
              .map(el => ({
                  tag: el.tagName,
                  text: el.textContent.trim().substring(0, 40),
                  href: el.getAttribute('href'),
                  onclick: el.getAttribute('onclick'),
                  classes: el.className.substring(0, 60)
              }))
              .filter(el => el.text.length > 0)
    """)

    print("\n=== ALL BUTTONS/LINKS ===")
    for btn in buttons:
        if any(k in btn['text'] for k in ['اتصل', 'واتساب', 'تواصل', 'هاتف', 'contact', 'call', 'phone', 'whatsapp']):
            print(f"  <{btn['tag']}> '{btn['text']}' href={btn['href']} classes={btn['classes'][:50]}")

    # Clear captured and click each contact button
    captured.clear()

    print("\n=== CLICKING CONTACT BUTTONS ===")
    contact_btns = page.query_selector_all('button')
    for btn in contact_btns:
        try:
            text = btn.inner_text().strip()
            if any(k in text for k in ['اتصل', 'تواصل', 'واتساب', 'هاتف']):
                print(f"  Clicking: '{text}'")
                btn.click()
                time.sleep(2)

                # Check DOM for newly revealed phone
                phone_text = page.evaluate("""
                    () => {
                        // Look for tel: links
                        const tel = document.querySelector('a[href^="tel:"]');
                        if (tel) return 'tel:' + tel.href;

                        // Look for wa.me links
                        const wa = document.querySelector('a[href*="wa.me"]');
                        if (wa) return 'wa:' + wa.href;

                        // Look for any phone-number patterns in DOM text
                        const all = document.body.innerText;
                        const m = all.match(/\\b09\\d{8}\\b|\\+963\\d{9}\\b/);
                        return m ? 'found:' + m[0] : null;
                    }
                """)
                print(f"  Phone in DOM after click: {phone_text}")
        except Exception as e:
            pass

    print(f"\n=== CAPTURED NETWORK CALLS (after button clicks) ===")
    for item in captured:
        if item['type'] == 'request':
            print(f"  REQ  {item['method']} {item['url']}")
        elif item['type'] == 'response':
            print(f"  RESP {item['status']} {item['url']}")
            print(f"       data={str(item['data'])[:200]}")
        elif item['type'] == 'response_text':
            print(f"  RESP {item['status']} {item['url']}")
            print(f"       text={item['text'][:200]}")

    browser.close()

print("\nDone.")
