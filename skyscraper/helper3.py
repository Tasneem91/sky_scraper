import requests

urls = {
    "page1.html": "https://damazzle.com/motors/cars/search",
    "page2.html": "https://damazzle.com/motors/cars/search?page=2",
}

for filename, url in urls.items():
    response = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
    response.raise_for_status()
    with open(filename, "w", encoding="utf-8") as f:
        f.write(response.text)