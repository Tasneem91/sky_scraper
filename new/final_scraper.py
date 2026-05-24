import requests
from bs4 import BeautifulSoup
import time
import json
import io

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
import gspread

# ================= CONFIG =================

SERVICE_ACCOUNT_FILE = "carsscraper-7213c90db164.json"

SPREADSHEET_URL = "https://docs.google.com/spreadsheets/d/1YIhYXlOVEPXU4052BJWSC3VQnZZBqEQ2aB0YXzwPXlA"
DRIVE_FOLDER_ID = "1rI8q97wUoRqAhZYBSfEmXtH28i2J0QT3"

BASE_URL = "https://syriacars.net"
LIST_URL = "https://syriacars.net/inventory/page/{}/"

HEADERS = {"User-Agent": "Mozilla/5.0"}

SLEEP = 1

# ================= GOOGLE INIT =================

def init_google():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]

    creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=scopes)

    # sheets
    gc = gspread.authorize(creds)
    sheet = gc.open_by_url(SPREADSHEET_URL).sheet1

    # drive
    drive_service = build("drive", "v3", credentials=creds)

    return sheet, drive_service

# ================= HELPERS =================

def get_soup(url):
    res = requests.get(url, headers=HEADERS)
    return BeautifulSoup(res.text, "lxml")

# ================= GET LISTINGS =================

def get_links(page):
    s = get_soup(LIST_URL.format(page))
    items = s.select("div.stm-directory-grid-loop")

    results = []

    for item in items:
        link_tag = item.select_one("a")
        if not link_tag:
            continue

        link = link_tag["href"]
        listing_id = item.get("data-listing-id")

        results.append((listing_id, link))

    return results

# ================= GET PHONE =================

def get_phone(listing_id):
    url = "https://syriacars.net/wp-admin/admin-ajax.php"

    payload = {
        "action": "stm_show_number",
        "listing_id": listing_id
    }

    try:
        res = requests.post(url, data=payload, headers=HEADERS)
        return res.text.strip()
    except:
        return ""

# ================= DRIVE =================

def create_folder(service, name):
    meta = {
        "name": name,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [DRIVE_FOLDER_ID]
    }
    folder = service.files().create(body=meta, fields="id").execute()
    return folder["id"]


def upload_images(service, listing_id, images):
    folder_id = create_folder(service, str(listing_id))

    links = []

    for i, img_url in enumerate(images):
        try:
            res = requests.get(img_url, timeout=10)
            img_data = io.BytesIO(res.content)

            file_meta = {
                "name": f"{listing_id}_{i}.jpg",
                "parents": [folder_id]
            }

            media = MediaIoBaseUpload(img_data, mimetype="image/jpeg")

            file = service.files().create(
                body=file_meta,
                media_body=media,
                fields="id"
            ).execute()

            file_id = file["id"]

            # public access
            service.permissions().create(
                fileId=file_id,
                body={"type": "anyone", "role": "reader"}
            ).execute()

            link = f"https://drive.google.com/uc?id={file_id}"
            links.append(link)

        except Exception as e:
            print("❌ IMG ERROR:", e)

    return links

# ================= SCRAPE CAR =================

def extract_year(text):
    import re
    m = re.search(r"\b(19|20)\d{2}\b", text)
    return m.group(0) if m else ""

def find_keyword(text, words):
    for w in words:
        if w in text:
            return w
    return ""

def scrape_car(listing_id, url):

    s = get_soup(url)

    data = {}
    data["id"] = listing_id
    data["source"] = "syriacars"
    data["scraped_at"] = time.strftime("%Y-%m-%d %H:%M:%S")

    # title
    title = s.select_one("h1")
    data["title"] = title.text.strip() if title else ""

    # price
    price = s.select_one(".single-listing-price-value")
    data["price"] = price.text.strip() if price else ""

    # description
    desc = s.find(string="الوصف")
    if desc:
        data["description"] = desc.find_parent().find_next("div").text.strip()
    else:
        data["description"] = ""

    full_text = s.get_text()

    data["year"] = extract_year(full_text)
    data["fuel"] = find_keyword(full_text, ["بنزين", "مازوت", "كهرباء"])
    data["transmission"] = find_keyword(full_text, ["اوتوماتيك", "يدوي"])
    data["color"] = find_keyword(full_text, ["أسود", "أبيض", "فضي", "أحمر", "أزرق"])

    # images
    images = []
    for img in s.select("img"):
        src = img.get("data-lg-src") or img.get("src")
        if src and "uploads" in src:
            images.append(src)

    data["images"] = list(set(images))

    # phone
    data["phone"] = get_phone(listing_id)

    return data

# ================= SHEETS =================

def get_existing_ids(sheet):
    ids = sheet.col_values(1)
    return set(ids)

def save_row(sheet, car):

    images = "\n".join(car["images_drive"])

    row = [
        car["id"],
        car["title"],
        car["price"],
        car["year"],
        car["fuel"],
        car["transmission"],
        car["color"],
        car["description"],
        car["phone"],
        images,
        car["scraped_at"]
    ]

    sheet.append_row(row)

# ================= MAIN =================

def run():

    sheet, drive = init_google()
    existing_ids = get_existing_ids(sheet)

    print("🚀 START SCRAPER")

    for page in range(1, 5):  # ⚠️ بالبداية خليه قليل

        print(f"\n📄 Page {page}")

        listings = get_links(page)
        if not listings:
            break

        for listing_id, url in listings:

            if listing_id in existing_ids:
                print("⏭ SKIP:", listing_id)
                continue

            print("🚗 SCRAPING:", url)

            car = scrape_car(listing_id, url)

            # upload images
            car["images_drive"] = upload_images(drive, listing_id, car["images"])

            # save
            save_row(sheet, car)

            time.sleep(SLEEP)

        time.sleep(SLEEP)

    print("\n✅ DONE")


if __name__ == "__main__":
    run()