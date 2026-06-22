#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Run all three raw data scrapers in parallel.

USAGE
-----
  python rawdata_run_all.py               # incremental (page 1 of each)
  python rawdata_run_all.py --full        # full scrape / resume
  python rawdata_run_all.py --hours 4     # stop each after 4 hours
  python rawdata_run_all.py --pages 5     # quick test (syriacars + carsy only)
  python rawdata_run_all.py --start-date 2025-01-01

All flags are forwarded to every scraper that supports them.
Each scraper writes to its own sheet and JSONL file independently.
"""

import subprocess
import sys
import os
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent

SCRAPERS = [
    ('SyriaCars', 'rawdata_syriacars.py'),
    ('Damazzle',  'rawdata_damazzle.py'),
    ('Carsy',     'rawdata_carsy.py'),
]

# Flags that --pages does not apply to (damazzle uses page-count from API total)
PAGES_UNSUPPORTED = {'rawdata_damazzle.py'}


def main():
    extra_args = sys.argv[1:]

    # Build per-scraper arg lists (drop --pages for scrapers that don't support it)
    scraper_args = {}
    for _, script in SCRAPERS:
        args = list(extra_args)
        if script in PAGES_UNSUPPORTED:
            # remove --pages N if present
            filtered = []
            skip_next = False
            for a in args:
                if skip_next:
                    skip_next = False
                    continue
                if a == '--pages':
                    skip_next = True
                    continue
                if a.startswith('--pages='):
                    continue
                filtered.append(a)
            args = filtered
        scraper_args[script] = args

    procs = []
    for name, script in SCRAPERS:
        cmd = [sys.executable, str(SCRIPT_DIR / script)] + scraper_args[script]
        print(f'[launcher] Starting {name} → {" ".join(cmd)}')
        proc = subprocess.Popen(cmd, cwd=str(SCRIPT_DIR))
        procs.append((name, proc))

    print(f'[launcher] All {len(procs)} scrapers started. Waiting …\n')

    exit_codes = {}
    for name, proc in procs:
        proc.wait()
        exit_codes[name] = proc.returncode
        status = 'OK' if proc.returncode == 0 else f'EXIT {proc.returncode}'
        print(f'[launcher] {name}: {status}')

    any_failed = any(c != 0 for c in exit_codes.values())
    sys.exit(1 if any_failed else 0)


if __name__ == '__main__':
    main()
