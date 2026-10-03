"""Fetch real CDC data and rebuild the committed JavaScript demo snapshot.

Run from the project root: python scripts/update_demo_data.py
This only writes the snapshot after BOTH datasets and all figures succeed.
"""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from flask import Flask
from cache import cache
from public_chart_data import build_chart_payload


def main():
    app = Flask(__name__, root_path=str(ROOT), instance_path=str(ROOT / 'instance'))
    cache.init_app(app)
    with app.app_context():
        payload = {page: build_chart_payload(page) for page in ('diseases', 'vaccinations')}
    destination = ROOT / 'static' / 'js' / 'cdc-demo-data.js'
    destination.write_text(
        '// Real CDC snapshot. Rebuild with scripts/update_demo_data.py; do not edit values by hand.\n'
        + 'window.CDC_DEMO_DATA = ' + json.dumps(payload, separators=(',', ':'), allow_nan=False) + ';\n',
        encoding='utf-8',
    )
    for page, data in payload.items():
        print(page, 'latest reporting period:', data['latest_reporting_period'], 'charts:', len(data['charts']))
    print('Snapshot bytes:', destination.stat().st_size)


if __name__ == '__main__':
    main()
