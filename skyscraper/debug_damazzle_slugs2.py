#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Check featured_fields slugs and description format across several cars via detail API."""
import sys, json, re, collections, requests
sys.stdout.reconfigure(encoding='utf-8')

API = 'https://beta.damazzletech.com/api/api/v1/client'
H = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept': 'application/json',
    'Origin': 'https://damazzle.com',
    'Referer': 'https://damazzle.com/',
}

# Use IDs from the working listing intercept (pages 1-2)
CAR_IDS = [424119, 424031, 424545, 424544, 424432, 424557, 424558, 424559]

slug_counter = collections.Counter()
slug_examples = {}

for car_id in CAR_IDS:
    r = requests.get(f'{API}/ads/{car_id}', H, timeout=15)
    if r.status_code != 200:
        print(f'  id={car_id}  status={r.status_code}')
        continue
    car = r.json().get('data', {})
    title = car.get('title', '')[:40]
    print(f'\n=== id={car_id}  title={title!r} ===')

    ff_list = car.get('featured_fields') or []
    print(f'  featured_fields count: {len(ff_list)}')
    for ff in ff_list:
        tf = ff.get('template_field') or {}
        slug = tf.get('slug', '?')
        label_ar = tf.get('field_name_ar', '?')
        val_ar = (ff.get('value') or {}).get('ar', '')
        print(f'    slug={slug!r:30s}  label_ar={label_ar!r:25s}  val={val_ar!r}')
        slug_counter[slug] += 1
        if slug not in slug_examples:
            slug_examples[slug] = {'label_ar': label_ar, 'example': val_ar}

    desc = car.get('description') or car.get('description_ar') or ''
    print(f'  description (first 300): {repr(desc[:300])}')

print('\n\n=== ALL SLUGS FOUND ===')
for slug, cnt in slug_counter.most_common():
    ex = slug_examples[slug]
    print(f'  {cnt}x  slug={slug!r:30s}  label_ar={ex["label_ar"]!r:25s}  e.g.={ex["example"]!r}')

print('\nDone.')
