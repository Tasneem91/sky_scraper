"""
Carsy.app Scraper — Three-Stage Architecture
  Stage 1: Playwright — click-based pagination to collect all car URLs
            (listing page is React/CSR — needs real browser)
  Stage 2: requests + BeautifulSoup — fetch each detail page
            (detail pages are Next.js SSR — plain HTTP works, no browser needed)
  Stage 3: Contact extraction — probes known API patterns first (fast, no browser),
            falls back to Playwright button-click + DOM/network interception if needed

Phone numbers on Carsy are hidden behind a "اتصل بنا" button click — they are not
present in the SSR HTML. Stage 3 handles this by:
  1. Trying a set of candidate REST API URLs (instantaneous via requests)
  2. Auto-discovering the real endpoint from the first Playwright-captured response
  3. Switching all remaining cars to direct API calls once the endpoint is found

Arabic label mapping (Carsy's reversed naming):
  الموديل  → brand  (e.g. Toyota)
  الماركة  → model  (e.g. Camry)
"""

import logging
import re
import time
import json
import requests
from urllib.parse import unquote
from datetime import datetime
from typing import List, Dict, Any, Optional

from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
from scrapers.parser import CARSY_SPEC_MAP
from scrapers import parser as car_parser

logger = logging.getLogger(__name__)

BASE_URL = "https://carsy.app"

REQUEST_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept-Language': 'ar,en-US;q=0.9,en;q=0.8',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
}

# Candidate REST endpoints for contact/phone. Tried in order; first 200+phone wins.
# {base} → BASE_URL, {id} → car ID string.
# Once one works, it is cached in self._contact_api_url for all subsequent cars.
CONTACT_API_CANDIDATES = [
    "{base}/api/cars/{id}/contact",
    "{base}/api/cars/{id}/phone",
    "{base}/api/ads/{id}/contact",
    "{base}/api/listings/{id}/contact",
    "{base}/api/contact?car_id={id}",
    "https://app.carsy.app/api/cars/{id}/contact",
    "https://app.carsy.app/api/cars/{id}/phone",
    "https://app.carsy.app/api/ads/{id}/contact",
    "https://app.carsy.app/api/listings/{id}/contact",
]

# Arabic text that appears on contact/phone reveal buttons
CONTACT_BUTTON_KEYWORDS = ['اتصل', 'تواصل', 'واتساب', 'هاتف', 'أرقام', 'اعرض الرقم', 'رقم']


class CarsyScraper:
    """
    Two-stage Carsy.app scraper.
    Stage 1 uses Playwright (React pagination), Stage 2 uses requests (SSR detail pages).
    """

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.base_url = config.get('url', 'https://carsy.app/cars')
        self.items = []
        self.playwright = None
        self.browser = None
        self.page = None
        # Stage 3: discovered/cached contact API endpoint template
        # e.g. "https://carsy.app/api/cars/{id}/contact"
        self._contact_api_url: Optional[str] = None

    # =========================================================================
    # Browser lifecycle (Stage 1 only)
    # =========================================================================

    def _init_browser(self):
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(headless=True)
        self.page = self.browser.new_page(
            user_agent=REQUEST_HEADERS['User-Agent']
        )
        self.page.set_extra_http_headers({
            'Accept-Language': REQUEST_HEADERS['Accept-Language'],
            'Accept': REQUEST_HEADERS['Accept'],
        })
        logger.info("Browser initialized (Stage 1 only)")

    def _close_browser(self):
        for obj, method in [(self.page, 'close'), (self.browser, 'close'), (self.playwright, 'stop')]:
            try:
                if obj:
                    getattr(obj, method)()
            except Exception:
                pass
        self.page = self.browser = self.playwright = None
        logger.info("Browser closed")

    def _goto(self, url: str):
        try:
            self.page.goto(url, wait_until='load', timeout=60000)
        except Exception:
            self.page.goto(url, wait_until='networkidle', timeout=60000)

    # =========================================================================
    # STAGE 1 — Collect all car URLs via React click-based pagination
    # =========================================================================
    # Facts confirmed via live DOM inspection:
    #   • Pagination <a> tags have NO href — React state-driven
    #   • URL never changes after clicking
    #   • التالي selector: a[data-slot="pagination-link"][aria-label="الذهاب إلى الصفحة التالية"]
    #   • True disabled = standalone class 'pointer-events-none' (NOT 'disabled:pointer-events-none')
    #   • 50 pages, ~20 cars per page (~989 total)

    def _collect_car_links(self) -> List[Dict[str, Any]]:
        """Click through all pagination pages and collect car links + card metadata."""
        all_cars: Dict[str, Dict] = {}
        page_num = 1

        logger.info(f"[Stage 1] Loading: {self.base_url}")
        self._goto(self.base_url)

        while True:
            # Wait for car cards to render — wait for first card, then
            # wait for networkidle so ALL cards finish rendering
            try:
                self.page.wait_for_selector("a[href^='/cars/']", timeout=20000)
            except Exception:
                logger.warning(f"[Stage 1] No car links on page {page_num} — stopping")
                break
            try:
                self.page.wait_for_load_state('networkidle', timeout=8000)
            except Exception:
                pass   # networkidle is best-effort; continue anyway

            # Scroll to bottom then back to top — triggers lazy-loaded cards to render
            self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(1)
            self.page.evaluate("window.scrollTo(0, 0)")
            time.sleep(1)

            # Record first car href BEFORE click (used to detect page change)
            first_href_before = self.page.evaluate("""
                () => {
                    const a = Array.from(document.querySelectorAll('a[href]'))
                        .find(a => /^\\/cars\\/\\d+$/.test(a.getAttribute('href')));
                    return a ? a.getAttribute('href') : null;
                }
            """)

            # Extract all car cards on this page
            cards = self.page.evaluate("""
                () => {
                    const anchors = Array.from(document.querySelectorAll('a[href]'))
                        .filter(a => /^\\/cars\\/\\d+$/.test(a.getAttribute('href')));

                    return anchors.map(a => {
                        const titleEl  = a.querySelector('h3');
                        const allSpans = Array.from(a.querySelectorAll('span'));
                        const priceEl  = allSpans.find(s => s.textContent.includes('$'));

                        // Location: Arabic-only span that is not a time/date indicator.
                        // More robust than span.capitalize (class can change with Tailwind updates).
                        const arabicOnly = /^[؀-ۿ\s،؍]+$/;
                        const timeWords  = ['منذ', 'أمس', 'اليوم', 'ساعة', 'ساعات', 'يوم', 'أيام'];
                        const locEl = allSpans.find(s => {
                            const t = s.textContent.trim();
                            return t.length > 1 &&
                                   arabicOnly.test(t) &&
                                   !timeWords.some(w => t.includes(w));
                        });

                        // Time posted: span next to a clock icon SVG
                        const svgs = Array.from(a.querySelectorAll('svg'));
                        const clockSvg = svgs.find(s => s.querySelector('circle'));
                        const timeSpan = clockSvg ? clockSvg.nextElementSibling : null;

                        return {
                            href:        a.getAttribute('href'),
                            title:       titleEl  ? titleEl.textContent.trim()  : null,
                            price_raw:   priceEl  ? priceEl.textContent.trim()  : null,
                            location:    locEl    ? locEl.textContent.trim()    : null,
                            posted_time: timeSpan ? timeSpan.textContent.trim() : null,
                        };
                    });
                }
            """)

            new_count = 0
            for card in cards:
                href = card.get('href', '')
                m = re.search(r'/cars/(\d+)', href)
                if not m:
                    continue
                car_id = m.group(1)
                if car_id in all_cars:
                    continue
                card['url'] = f"{BASE_URL}{href}"
                card['car_id'] = car_id
                all_cars[car_id] = card
                new_count += 1

            logger.info(f"[Stage 1] Page {page_num}: +{new_count} new | total: {len(all_cars)}")

            if new_count == 0:
                logger.info("[Stage 1] No new cars — done")
                break

            # ----------------------------------------------------------------
            # Click التالي — FIX: use class token split, not substring match.
            # Tailwind puts 'disabled:pointer-events-none' in ALL elements as
            # a conditional modifier. Split by whitespace to find the standalone
            # 'pointer-events-none' token that means it's truly disabled.
            # ----------------------------------------------------------------
            result = self.page.evaluate("""
                () => {
                    function isTrulyDisabled(el) {
                        const tokens = (el.className || '').split(/\\s+/);
                        return tokens.includes('pointer-events-none') ||
                               tokens.includes('opacity-50') ||
                               el.getAttribute('aria-disabled') === 'true';
                    }

                    // Primary: التالي via aria-label (shadcn pagination)
                    let btn = document.querySelector(
                        'a[data-slot="pagination-link"][aria-label="الذهاب إلى الصفحة التالية"]'
                    );
                    if (btn) {
                        if (isTrulyDisabled(btn)) return 'disabled';
                        btn.click();
                        return 'clicked';
                    }

                    // Fallback: any element with exact text التالي
                    const all = Array.from(document.querySelectorAll('a, button'));
                    btn = all.find(el => el.textContent.trim() === 'التالي');
                    if (btn) {
                        if (isTrulyDisabled(btn) || btn.disabled) return 'disabled';
                        btn.click();
                        return 'clicked-fallback';
                    }

                    return 'not-found';
                }
            """)

            logger.info(f"[Stage 1] Next button: {result}")

            if result in ('disabled', 'not-found'):
                logger.info(f"[Stage 1] Last page reached — stopping")
                break

            # Wait for React to re-render (first car href changes, URL stays same)
            try:
                self.page.wait_for_function(
                    """(prev) => {
                        const a = Array.from(document.querySelectorAll('a[href]'))
                            .find(a => /^\\/cars\\/\\d+$/.test(a.getAttribute('href')));
                        return a && a.getAttribute('href') !== prev;
                    }""",
                    arg=first_href_before,
                    timeout=15000
                )
            except Exception:
                logger.warning("[Stage 1] Page change timeout — sleeping 3s")
                time.sleep(3)

            page_num += 1

        logger.info(f"[Stage 1] Complete. Collected {len(all_cars)} car URLs")
        return list(all_cars.values())

    # =========================================================================
    # STAGE 2 — Fetch each detail page via requests (SSR — no browser needed)
    # =========================================================================

    def _scrape_detail_page(self, car_url: str) -> Dict[str, Any]:
        """
        STAGE 1 (detail) — Raw extraction from SSR detail page via requests.
        Returns a raw dict. No interpretation here.
        """
        raw_detail = {
            'title_raw':       None,
            'price_raw':       None,
            'specs_raw':       {},
            'description_raw': None,
            'seller_name':     None,
            'images':          [],
            'phone':           None,
            'whatsapp':        None,
        }

        try:
            resp = requests.get(car_url, headers=REQUEST_HEADERS, timeout=30)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, 'html.parser')
            page_text = resp.text

            # ── Title (h1) ────────────────────────────────────────────────
            h1 = soup.find('h1')
            if h1:
                raw_detail['title_raw'] = h1.get_text(strip=True)

            # ── Price — first span/div containing $ ──────────────────────
            for el in soup.find_all(['span', 'div', 'p', 'h2']):
                text = el.get_text(strip=True)
                if '$' in text and re.search(r'\d', text) and len(text) < 50:
                    raw_detail['price_raw'] = text
                    break

            # ── Specs: h2 "معلومات السيارة" → grid div → spec cards ──────
            # Each card: <div class="flex items-center ...">
            #               <svg/>
            #               <div>
            #                 <p class="text-sm text-muted-foreground">LABEL</p>
            #                 <p class="font-medium capitalize">VALUE</p>
            #               </div>
            #            </div>
            specs_h2 = next(
                (h for h in soup.find_all('h2') if 'معلومات' in h.get_text()), None
            )
            if specs_h2:
                specs_div = specs_h2.find_next_sibling('div') or specs_h2.find_next('div')
                if specs_div:
                    for card in specs_div.find_all('div', recursive=False):
                        ps = card.find_all('p')
                        if len(ps) >= 2:
                            key = ps[0].get_text(strip=True)
                            val = ps[1].get_text(strip=True)
                            if key and val and key != val:
                                raw_detail['specs_raw'][key] = val

            # ── Description: h2 "الوصف" → immediate <p> sibling ─────────
            desc_h2 = next(
                (h for h in soup.find_all('h2') if 'الوصف' in h.get_text()), None
            )
            if desc_h2:
                # Prefer <p> directly after the heading (not a big wrapper div)
                desc_el = desc_h2.find_next(['p', 'div'])
                if desc_el:
                    raw_detail['description_raw'] = desc_el.get_text(separator=' ', strip=True)

            # ── Seller: h3 "معلومات البائع" → first <p class="font-medium"> ──
            seller_h3 = next(
                (h for h in soup.find_all('h3') if 'البائع' in h.get_text()), None
            )
            if seller_h3:
                seller_div = seller_h3.find_next_sibling('div') or seller_h3.find_next('div')
                if seller_div:
                    # Seller name is in <p class="font-medium"> (NOT h4 anymore)
                    name_p = seller_div.find('p', class_=re.compile(r'font-medium'))
                    if name_p:
                        raw_detail['seller_name'] = name_p.get_text(strip=True)

            # ── Images: Next.js wraps real URLs as /_next/image?url=<encoded> ──
            skip_kw = ('icon', 'logo', 'placeholder', 'avatar', 'flag', 'sprite', 'banner')
            seen_imgs: set = set()
            for img in soup.find_all('img'):
                src = img.get('src') or ''
                # Decode Next.js image optimization wrapper
                if '/_next/image' in src and 'url=' in src:
                    m = re.search(r'url=([^&]+)', src)
                    if m:
                        src = unquote(m.group(1))
                if src.startswith('http') and len(src) > 30 \
                        and not any(k in src.lower() for k in skip_kw) \
                        and src not in seen_imgs:
                    seen_imgs.add(src)
                    raw_detail['images'].append(src)

            # Fallback: find image URLs directly in page source (catches lazy-loaded)
            if not raw_detail['images']:
                found = re.findall(
                    r'https://app\.carsy\.app/uploads/[^\s"\'\\]+\.(?:jpg|jpeg|png|webp)',
                    page_text
                )
                raw_detail['images'] = list(dict.fromkeys(found))

            # ── Contact ───────────────────────────────────────────────────
            tel = soup.find('a', href=lambda h: h and h.startswith('tel:'))
            if tel:
                raw_detail['phone'] = tel['href'].replace('tel:', '').strip()

            wa = soup.find('a', href=lambda h: h and 'wa.me' in (h or ''))
            if wa:
                m = re.search(r'wa\.me/(\d+)', wa['href'])
                raw_detail['whatsapp'] = m.group(1) if m else wa['href']

        except requests.exceptions.RequestException as e:
            logger.error(f"HTTP error fetching {car_url}: {e}")
        except Exception as e:
            logger.error(f"Parse error on {car_url}: {e}")

        return raw_detail

    # =========================================================================
    # STAGE 3 — Contact extraction (phone / whatsapp)
    # Phone numbers are NOT in the SSR HTML; they require a button click which
    # triggers a hidden API call.  We first try a list of candidate API URLs
    # (pure requests, very fast).  If all return 404/empty we launch a browser,
    # click the button, and capture the real endpoint from the network response —
    # after which all remaining cars switch back to fast API calls.
    # =========================================================================

    def _parse_contact_from_json(self, data: Any) -> Dict[str, Optional[str]]:
        """
        Extract phone / whatsapp from various JSON response shapes.
        Handles nested containers: {car: {...}}, {data: {...}}, {result: {...}}.
        """
        result: Dict[str, Optional[str]] = {'phone': None, 'whatsapp': None}
        if not isinstance(data, dict):
            return result

        # Flatten common nested wrapper keys
        for wrap in ('car', 'data', 'result', 'listing', 'item', 'ad'):
            nested = data.get(wrap)
            if isinstance(nested, dict):
                data = {**data, **nested}

        phone_keys = ('phone', 'mobile', 'telephone', 'phoneNumber', 'phone_number',
                      'contact_number', 'contactNumber', 'tel')
        wa_keys    = ('whatsapp', 'wa', 'wa_number', 'whatsapp_number', 'whatsappNumber')

        for k in phone_keys:
            v = data.get(k)
            if v and str(v).strip():
                result['phone'] = str(v).strip()
                break
        for k in wa_keys:
            v = data.get(k)
            if v and str(v).strip():
                result['whatsapp'] = str(v).strip()
                break

        return result

    def _try_contact_api(self, car_id: str) -> Dict[str, Optional[str]]:
        """
        Try the cached API endpoint (if known) or probe all candidates.
        Returns {'phone': ..., 'whatsapp': ...} on first success, else both None.
        """
        empty = {'phone': None, 'whatsapp': None}

        candidates = (
            [self._contact_api_url] if self._contact_api_url else CONTACT_API_CANDIDATES
        )

        for template in candidates:
            url = template.replace('{id}', car_id).replace('{base}', BASE_URL)
            try:
                resp = requests.get(url, headers=REQUEST_HEADERS, timeout=10)
                if resp.status_code == 200:
                    try:
                        data = resp.json()
                    except Exception:
                        continue
                    contact = self._parse_contact_from_json(data)
                    if contact.get('phone') or contact.get('whatsapp'):
                        if not self._contact_api_url:
                            self._contact_api_url = template
                            logger.info(f"[Contact API] Endpoint discovered: {url}")
                        return contact
            except Exception:
                pass

        return empty

    def _click_and_get_contact(
        self, page, car_url: str, car_id: str
    ) -> Dict[str, Optional[str]]:
        """
        Playwright helper: load a detail page, click every contact-reveal button,
        then read phone from:
          1. DOM (tel: / wa.me links, or Syrian-number regex in page text)
          2. Intercepted API response JSON

        Also auto-discovers the real contact API endpoint from network traffic
        so subsequent cars can use fast direct requests instead.
        """
        captured: List[Dict] = []

        def on_response(resp):
            url = resp.url
            # Only care about JSON API responses that might carry contact data
            if resp.status != 200:
                return
            if resp.request.resource_type in ('image', 'stylesheet', 'font', 'media'):
                return
            if any(k in url.lower() for k in ('contact', 'phone', 'mobile', 'reveal', 'api')) \
               or car_id in url:
                try:
                    body = resp.body()
                    if body and len(body) < 20000:
                        try:
                            captured.append({'url': url, 'data': json.loads(body)})
                        except Exception:
                            pass
                except Exception:
                    pass

        page.on('response', on_response)

        try:
            page.goto(car_url, wait_until='load', timeout=30000)
            time.sleep(1.5)

            # Scroll to mid-page to trigger lazy rendering
            page.evaluate("window.scrollTo(0, document.body.scrollHeight * 0.4)")
            time.sleep(0.5)

            # Click every Arabic contact-keyword button
            for btn in page.query_selector_all('button, a'):
                try:
                    text = btn.inner_text().strip()
                    if any(k in text for k in CONTACT_BUTTON_KEYWORDS):
                        btn.scroll_into_view_if_needed()
                        btn.click()
                        time.sleep(1.5)
                except Exception:
                    pass

            # Read phone numbers from live DOM
            dom = page.evaluate(r"""
                () => {
                    const telEl = document.querySelector('a[href^="tel:"]');
                    const waEl  = document.querySelector('a[href*="wa.me"]');
                    const phone    = telEl ? telEl.href.replace('tel:', '').trim() : null;
                    const waMatch  = waEl  ? (waEl.href.match(/wa\.me\/(\d+)/) || [])[1] : null;
                    // Syrian mobile numbers: 09XXXXXXXX  or +963 9XXXXXXXX
                    const text = document.body.innerText;
                    const re   = /(?:^|\D)(09\d{8}|\+963\s?9\d{8}|963\s?9\d{8})(?:\D|$)/;
                    const fromText = (text.match(re) || [])[1] || null;
                    return { phone: phone || fromText, whatsapp: waMatch };
                }
            """)

            phone    = dom.get('phone')
            whatsapp = dom.get('whatsapp')

            # Fall back to intercepted API JSON
            if not phone and not whatsapp:
                for call in captured:
                    contact = self._parse_contact_from_json(call.get('data') or {})
                    if contact.get('phone') or contact.get('whatsapp'):
                        phone    = contact['phone']
                        whatsapp = contact['whatsapp']
                        # Cache the API endpoint for future direct calls
                        if not self._contact_api_url and car_id in call['url']:
                            self._contact_api_url = call['url'].replace(car_id, '{id}')
                            logger.info(
                                f"[Contact] API auto-discovered: {self._contact_api_url}"
                            )
                        break

            return {'phone': phone, 'whatsapp': whatsapp}

        finally:
            page.remove_listener('response', on_response)

    def _scrape_contacts_stage3(self, car_cards: List[Dict]) -> Dict[str, Dict]:
        """
        Stage 3 orchestrator.

        Pass 1 — fast API probe (requests, no browser):
            For every car, try candidate API URLs.  Most will 404 or return no
            phone; that's fine — we just collect the ones that succeed.

        Pass 2 — Playwright fallback for remaining cars:
            Open ONE browser.  For each car still missing contact:
              • Navigate, click button, capture from DOM / network.
              • If we discover the real API endpoint during pass 2,
                immediately switch the rest to direct API calls.
        """
        contacts: Dict[str, Dict] = {}
        empty = {'phone': None, 'whatsapp': None}
        total = len(car_cards)

        logger.info(f"[Stage 3] Contact extraction started for {total} cars.")

        # ── Pass 1: API probe ──────────────────────────────────────────────
        needs_playwright: List[Dict] = []
        for card in car_cards:
            car_id = card.get('car_id', '')
            if not car_id:
                continue
            contact = self._try_contact_api(car_id)
            if contact.get('phone') or contact.get('whatsapp'):
                contacts[car_id] = contact
            else:
                needs_playwright.append(card)

        api_found = sum(1 for c in contacts.values() if c.get('phone') or c.get('whatsapp'))
        logger.info(
            f"[Stage 3] API pass: {api_found} found | "
            f"{len(needs_playwright)} still need Playwright"
        )

        # ── Pass 2: Playwright for remaining cars ──────────────────────────
        if needs_playwright:
            with sync_playwright() as pw:
                browser = pw.chromium.launch(headless=True)
                ctx = browser.new_context(user_agent=REQUEST_HEADERS['User-Agent'])
                ctx.set_extra_http_headers({'Accept-Language': 'ar'})
                page = ctx.new_page()

                remaining = list(needs_playwright)   # mutable copy for early exit
                idx = 0

                while idx < len(remaining):
                    card   = remaining[idx]
                    car_url = card.get('url', '')
                    car_id  = card.get('car_id', '')
                    idx += 1

                    if not car_url or not car_id:
                        contacts[car_id] = empty
                        continue

                    try:
                        contact = self._click_and_get_contact(page, car_url, car_id)
                        contacts[car_id] = contact
                    except Exception as e:
                        logger.warning(f"[Stage 3] Playwright error on {car_url}: {e}")
                        contacts[car_id] = empty

                    # If we just auto-discovered the API endpoint, switch
                    # all remaining cars to fast direct requests.
                    if self._contact_api_url and idx < len(remaining):
                        still_todo = remaining[idx:]
                        logger.info(
                            f"[Stage 3] API endpoint now known — switching "
                            f"{len(still_todo)} remaining cars to direct API calls."
                        )
                        for todo_card in still_todo:
                            tid = todo_card.get('car_id', '')
                            if tid:
                                contacts[tid] = self._try_contact_api(tid)
                        break   # skip the rest of the while loop

                    if idx % 20 == 0:
                        found_now = sum(
                            1 for c in contacts.values()
                            if c.get('phone') or c.get('whatsapp')
                        )
                        logger.info(
                            f"[Stage 3] Progress {idx}/{len(needs_playwright)} | "
                            f"found: {found_now}"
                        )

                    time.sleep(0.5)

                browser.close()

        found_total = sum(1 for c in contacts.values() if c.get('phone') or c.get('whatsapp'))
        logger.info(f"[Stage 3] Done. Contacts found: {found_total}/{total}")
        return contacts

    # =========================================================================
    # Main scrape() — orchestrates all three stages
    # =========================================================================

    def scrape(self) -> List[Dict[str, Any]]:
        """
        Stage 1: Playwright collects all car URLs (React pagination).
        Stage 2: requests fetches each detail page (Next.js SSR).
        Stage 3: Contact extraction — API probe first, Playwright fallback.
        Browser is closed between stages; Stage 3 reopens one if needed.
        """
        logger.info(f"Starting Carsy scraper: {self.base_url}")
        self.items = []

        # ---- STAGE 1 ----
        try:
            self._init_browser()
            car_cards = self._collect_car_links()
        finally:
            self._close_browser()  # Browser done after Stage 1

        if not car_cards:
            logger.warning("No car links found in Stage 1")
            return []

        # ---- STAGE 2 ----
        total = len(car_cards)
        logger.info(f"[Stage 2] Fetching {total} detail pages via requests...")

        for idx, card in enumerate(car_cards):
            car_url = card.get('url', '')
            logger.info(f"[Stage 2] {idx + 1}/{total}: {car_url}")

            try:
                detail = self._scrape_detail_page(car_url)
                item = self._build_item(card, detail, car_url)
                if item:
                    self.items.append(item)
            except Exception as e:
                logger.error(f"[Stage 2] Error on {car_url}: {e}")
                continue

            time.sleep(0.3)  # Polite delay between requests

        # ---- STAGE 3: Contact extraction ----
        if car_cards and self.items:
            contacts = self._scrape_contacts_stage3(car_cards)

            # Merge contact info into final items
            for item in self.items:
                item_id = item.get('id', '')
                m = re.search(r'carsy_(\d+)', item_id)
                if not m:
                    continue
                car_id = m.group(1)
                c = contacts.get(car_id, {})
                # Only overwrite if Stage 2 didn't already find a contact
                if not item.get('contact'):
                    phone    = c.get('phone')
                    whatsapp = c.get('whatsapp')
                    if phone or whatsapp:
                        item['contact'] = phone or whatsapp

        logger.info(f"Scraping complete. Total items: {len(self.items)}")
        return self.items

    # =========================================================================
    # Item Builder
    # =========================================================================

    def _build_item(self, card: Dict, raw_detail: Dict, car_url: str) -> Optional[Dict[str, Any]]:
        """
        STAGE 2 — Merge Stage 1 card + detail raw data, then run shared parser.
        All interpretation happens in car_parser.parse(), not here.
        """
        try:
            ad_id_m = re.search(r'/cars/(\d+)', car_url)
            ad_id = ad_id_m.group(1) if ad_id_m else None

            # Compose a single raw dict for the parser
            raw = {
                'source':          'carsy',
                'id':              f"carsy_{ad_id}" if ad_id else f"carsy_{int(datetime.now().timestamp())}",
                'ad_id':           ad_id,
                'ad_url':          car_url,
                'scraped_at':      datetime.now().isoformat(),
                'listing_type':    'sell',

                # Card price is the clean "$2,500" span — prefer it over detail page
                # (detail page search can accidentally grab year + price together)
                'title_raw':       raw_detail.get('title_raw') or card.get('title'),
                'price_raw':       card.get('price_raw') or raw_detail.get('price_raw'),
                'location_raw':    card.get('location'),
                'description_raw': raw_detail.get('description_raw'),
                'posted_date':     card.get('posted_time'),

                # Specs from detail page (Carsy reversed label map applied in parser)
                'specs_raw':       raw_detail.get('specs_raw', {}),

                # Images, contact, seller from detail page
                'images':          raw_detail.get('images', []),
                'seller_name':     raw_detail.get('seller_name'),
                'phone':           raw_detail.get('phone'),
                'whatsapp':        raw_detail.get('whatsapp'),
                'phones_raw':      [],
            }

            # Use CARSY_SPEC_MAP (reversed brand/model naming)
            return car_parser.parse(raw, CARSY_SPEC_MAP)

        except Exception as e:
            logger.error(f"Error building item for {car_url}: {e}")
            return None

    # =========================================================================
    # Helpers
    # =========================================================================

    def get_statistics(self, items: List[Dict]) -> Dict[str, Any]:
        if not items:
            return {'total_items': 0, 'price_stats': {}, 'year_stats': {}, 'brand_stats': {}}

        prices = [i.get('price') for i in items if i.get('price')]
        years  = [i.get('year')  for i in items if i.get('year')]
        brands = [i.get('brand') for i in items if i.get('brand')]

        return {
            'total_items': len(items),
            'price_stats': {
                'count':   len(prices),
                'average': round(sum(prices) / len(prices), 2) if prices else 0,
                'min':     min(prices) if prices else 0,
                'max':     max(prices) if prices else 0,
            },
            'year_stats': {
                'count':   len(years),
                'average': int(sum(years) / len(years)) if years else 0,
                'min':     min(years) if years else 0,
                'max':     max(years) if years else 0,
            },
            'brand_stats': self._count_brands(brands),
            'items_with_complete_data': sum(
                1 for i in items
                if all([i.get('price'), i.get('brand'), i.get('year'), i.get('location')])
            ),
        }

    def _count_brands(self, brands: List[str]) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for b in brands:
            counts[b] = counts.get(b, 0) + 1
        return dict(sorted(counts.items(), key=lambda x: x[1], reverse=True))
