from playwright.sync_api import sync_playwright

images = []

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page()
    page.goto("https://damazzle.com/motors/cars/search")
    page.wait_for_selector(".product-bg-rtl")

    images = page.evaluate("""
        () => Array.from(document.querySelectorAll(".product-bg-rtl"))
          .map(el => el.style.backgroundImage)
          .filter(Boolean)
          .map(bg => bg.replace(/^url\\(["']?/, "").replace(/["']?\\)$/, ""))
    """)

    browser.close()

for img in images:
    print(img)
