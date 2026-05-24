#!/usr/bin/env python3
import sys, json, requests
sys.stdout.reconfigure(encoding='utf-8')
H = {
    'User-Agent': 'Mozilla/5.0',
    'Accept': 'application/json',
    'Origin': 'https://damazzle.com',
    'Referer': 'https://damazzle.com/motors/cars/search',
}
API = 'https://beta.damazzletech.com/api/api/v1/client'
r = requests.get(f'{API}/search/ads/website?page=1&per_page=8', H, timeout=15)
print('status:', r.status_code)
if r.status_code == 200:
    d = r.json()
    items = d.get('data', [])
    print('items:', len(items))
    for c in items[:4]:
        title = c.get('title', '')[:35]
        phone = c.get('phone', '')
        pub   = str(c.get('published_date', ''))[:10]
        gall  = len(c.get('gallery') or [])
        print(f'  id={c.get("id")}  phone={phone}  date={pub}  gallery={gall}  title={title!r}')
    print('meta:', d.get('meta', {}))
else:
    print('body:', r.text[:300])
