#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys
sys.path.insert(0, '.')
from bazaralsham_scraper import BazarAlshamScraper

s = BazarAlshamScraper()
rows = s.sheet.get_all_rows()

# Find first 5 cars that have drive image links
found = []
for row in rows:
    drive = row.get('images_drive_links', '').strip()
    orig  = row.get('images_original_links', '').strip()
    if drive and len(found) < 5:
        found.append(row)

print(f'Found {len(found)} cars with Drive links\n')
for r in found:
    print(f"ID: {r.get('id')} | make: {r.get('make')} | model: {r.get('model')}")
    print(f"  Drive links: {r.get('images_drive_links','')[:120]}")
    print(f"  Orig links:  {r.get('images_original_links','')[:120]}")
    print()
