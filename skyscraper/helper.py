from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page()
    page.goto("https://syriacar.net/car/details/kia-sportage-2017-hlb-12264")
    html = page.content()

    with open("page.html", "w", encoding="utf-8") as f:
        f.write(html)

    browser.close()
