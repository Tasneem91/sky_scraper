#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys, json, requests
sys.stdout.reconfigure(encoding='utf-8')

API = 'https://beta.damazzletech.com/api/api/v1/client'
H = {
    'User-Agent': 'Mozilla/5.0',
    'Accept': 'application/json',
    'Origin': 'https://damazzle.com',
    'Referer': 'https://damazzle.com/',
}

# Try various sort params
for suffix in ['&newest=1', '&sort=newest', '&sort=new', '&sort=recent', '&type=newest']:
    url = f'{API}/ads?category_id=2&page=1&per_page=3{suffix}'
    r = requests.get(url, H, timeout=15)
    if r.status_code == 200:
        items = r.json().get('data', [])
        dates = [c.get('published_date', '')[:10] for c in items]
        print(f'{suffix!r:25s} status=200 dates={dates}')
    else:
        print(f'{suffix!r:25s} status={r.status_code}')

# No category filter — what order does the API return?
print()
r2 = requests.get(f'{API}/ads?page=1&per_page=5', H, timeout=15)
items2 = r2.json().get('data', [])
print('No category filter — first 5:')
for c in items2:
    ad_id    = c.get('id')
    pub_date = c.get('published_date', '')[:10]
    title    = c.get('title', '')[:40]
    print(f'  id={ad_id}  published={pub_date}  title={title!r}')
meta = r2.json().get('meta', {}).get('pagination', {})
print(f'  total={meta.get("total")}  per_page={meta.get("per_page")}')

# Check the unfiltered page WITHOUT any params but sort by id descending (newest by ID)
print()
r3 = requests.get(f'{API}/ads?category_id=2&page=1&per_page=5&sort_by=id&sort_order=desc', H, timeout=15)
items3 = r3.json().get('data', [])
print('Sorted by id DESC — first 5:')
for c in items3:
    ad_id    = c.get('id')
    pub_date = c.get('published_date', '')[:10]
    title    = c.get('title', '')[:40]
    print(f'  id={ad_id}  published={pub_date}  title={title!r}')

print('\nDone.')
