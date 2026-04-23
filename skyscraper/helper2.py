import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

BASE_URL = "https://syriacar.net"

html = requests.get(BASE_URL).text
soup = BeautifulSoup(html, "html.parser")

links = []

for card in soup.select('[data-link^="/car/details/"]'):
    relative_url = card.get("data-link")
    full_url = urljoin(BASE_URL, relative_url)
    links.append(full_url)

print(len(links))
print(links[:5])