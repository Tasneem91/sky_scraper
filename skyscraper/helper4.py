from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page()
    page.goto("https://damazzle.com/motors/cars/search")
    page.wait_for_selector("div.col-md-6.py-3.px-4.h-100.d-grid")

    html = page.inner_html("div.col-md-6.py-3.px-4.h-100.d-grid")

    with open("car_details.html", "w", encoding="utf-8") as f:
        f.write(html)

    browser.close()
