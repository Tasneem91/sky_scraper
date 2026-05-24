#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys
sys.path.insert(0, '.')
from bazaralsham_scraper import BazarAlshamScraper

s = BazarAlshamScraper()
rows = s.sheet.get_all_rows()
print(f'Total rows: {len(rows)}\n')

fields = ['id', 'make', 'model', 'fuel_type', 'transmission', 'origin', 'body_type', 'doors', 'price', 'mileage', 'engine_size']
header = ' | '.join(f'{f[:13]:<13}' for f in fields)
print(header)
print('-' * len(header))
for row in rows[:20]:
    line = ' | '.join(f'{str(row.get(f, ""))[:13]:<13}' for f in fields)
    print(line)

print('\n--- Unique values per field ---')
check_fields = ['fuel_type', 'transmission', 'origin', 'body_type', 'doors', 'condition', 'exterior_color', 'city']
for f in check_fields:
    vals = sorted(set(str(r.get(f, '')) for r in rows if r.get(f)))
    print(f'\n{f}: {vals}')
