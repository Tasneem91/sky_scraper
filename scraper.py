import os
import time
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

BASE_URL = "https://carsy.app"
LIST_URL = "https://carsy.app/cars?page={}"


headers = {
    "User-Agent": "Mozilla/5.0"
}


# ✅ إنشاء مجلد الصور
def create_dir(path):
    if not os.path.exists(path):
        os.makedirs(path)


# ✅ تحميل صورة
def download_image(url, folder):
    try:
        filename = url.split("/")[-1].split("?")[0]
        filepath = os.path.join(folder, filename)

        res = requests.get(url, headers=headers, timeout=10)

        if res.status_code == 200:
            with open(filepath, "wb") as f:
                f.write(res.content)

    except:
        pass


# ✅ استخراج روابط السيارات من صفحة
def get_listing_links(page):
    url = LIST_URL.format(page)

    res = requests.get(url, headers=headers)
    if res.status_code != 200:
        return []

    soup = BeautifulSoup(res.text, "lxml")

    links = []
    for a in soup.find_all("a", href=True):
        if "/cars/" in a["href"]:
            full_url = urljoin(BASE_URL, a["href"])
            if full_url not in links:
                links.append(full_url)

    return links


# ✅ استخراج تفاصيل السيارة
def scrape_car(url):
    res = requests.get(url, headers=headers)
    if res.status_code != 200:
        return None

    soup = BeautifulSoup(res.text, "lxml")

    data = {}
    data["url"] = url

    # ✅ العنوان
    title = soup.find("h1")
    data["title"] = title.get_text(strip=True) if title else None

    # ✅ السعر
    price = soup.find(string=lambda x: "$" in x if x else False)
    data["price"] = price.strip() if price else None

    # ✅ الهاتف
    phone_tag = soup.find("a", href=lambda x: x and x.startswith("tel:"))
    data["phone"] = phone_tag["href"].replace("tel:", "") if phone_tag else None

    # ✅ واتساب
    whatsapp_tag = soup.find("a", href=lambda x: x and "wa.me" in x)
    data["whatsapp"] = whatsapp_tag["href"] if whatsapp_tag else None

    # ✅ المواصفات (الجدول)
    specs = {}
    for div in soup.find_all("div"):
        text = div.get_text(strip=True)
        if ":" in text and len(text) < 50:
            parts = text.split(":")
            if len(parts) == 2:
                specs[parts[0]] = parts[1]

    data["specs"] = specs

    # ✅ الوصف
    desc = soup.find(string="الوصف")
    if desc:
        parent = desc.find_parent()
        if parent:
            data["description"] = parent.find_next("div").get_text(strip=True)
    else:
        data["description"] = None

    # ✅ الصور
    images = []
    for img in soup.find_all("img"):
        src = img.get("src")
        if src and "cars" in src:
            full_url = urljoin(BASE_URL, src)

            if full_url not in images:
                images.append(full_url)

    data["images"] = images

    return data


# ✅ تشغيل السكربر
def run_scraper():
    all_links = []

    print("🔍 جلب روابط السيارات...")

    # ✅ عدد الصفحات (من الصورة: 988 سيارة / 20 لكل صفحة ≈ 50)
    for page in range(1, 60):
        print(f"📄 صفحة {page}")
        links = get_listing_links(page)

        if not links:
            break

        all_links.extend(links)
        time.sleep(1)

    print(f"\n✅ تم العثور على {len(all_links)} سيارة")

    results = []

    # ✅ فحص كل سيارة
    for i, link in enumerate(all_links):
        print(f"🚗 [{i+1}/{len(all_links)}] {link}")

        data = scrape_car(link)
        if data:
            results.append(data)

            # ✅ تحميل الصور
            folder = f"images/car_{i+1}"
            create_dir(folder)

            for img_url in data["images"]:
                download_image(img_url, folder)

        time.sleep(1)

    # ✅ حفظ JSON
    import json
    with open("cars.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print("\n✅ انتهى ✅ تم حفظ cars.json")


if __name__ == "__main__":
    run_scraper()
