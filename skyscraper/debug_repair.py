#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Show what values are in the sheet vs what the normalizer would produce."""
import sys
sys.path.insert(0, '.')
from bazaralsham_scraper import BazarAlshamScraper
from normalizer import normalize_car

NORMALIZABLE = [
    'price', 'engine_size', 'mileage', 'year', 'seats', 'horsepower',
    'cylinders', 'doors', 'fuel_type', 'transmission', 'origin',
    'body_type', 'city', 'exterior_color', 'interior_color', 'condition',
    'make', 'model',
]

s = BazarAlshamScraper()
rows = s.sheet.get_all_rows()
print(f'Total rows: {len(rows)}\n')

issues = []
for row in rows:
    normalized = normalize_car(row)
    diffs = {}
    for col in NORMALIZABLE:
        old = row.get(col, '')
        new = normalized.get(col, '')
        if new and new != old:
            diffs[col] = (old, new)
    if diffs:
        issues.append((row.get('id', '?'), diffs))

if not issues:
    print('No differences found — sheet matches normalizer output.')
    print()
    print('Sample of current values (first 10 rows):')
    for row in rows[:10]:
        print(f"  id={row.get('id','')} make={row.get('make','')} model={row.get('model','')} "
              f"body={row.get('body_type','')} origin={row.get('origin','')} "
              f"price={row.get('price','')} mileage={row.get('mileage','')}")
else:
    print(f'Found {len(issues)} rows with differences:\n')
    for car_id, diffs in issues[:20]:
        print(f'  [{car_id}]')
        for col, (old, new) in diffs.items():
            print(f'    {col}: {old!r} -> {new!r}')

print()
print('--- Unique model values in sheet ---')
models = sorted(set(r.get('model', '') for r in rows if r.get('model')))
for m in models:
    print(f'  {m!r}')
