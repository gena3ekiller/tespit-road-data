#!/usr/bin/env python3
"""Downloads the country extracts, builds every pack, checks them and publishes a release.

update.py              all countries
update.py CH LI        only these
update.py --no-publish build and check only

A pack whose size drops by more than a third against the published one is not published (a broken extract).
"""
import argparse
import datetime
import json
import subprocess
import sys
import urllib.request
from pathlib import Path

from build_pack import build

B = Path(__file__).resolve().parent
COUNTRIES = {'CH': 'switzerland', 'LI': 'liechtenstein', 'AT': 'austria', 'DE': 'germany'}
URL = 'https://download.geofabrik.de/europe/{}-latest.osm.pbf'


def download(name):
    target = B / 'raw' / f'{name}-latest.osm.pbf'
    part = target.with_suffix('.part')
    target.parent.mkdir(exist_ok=True)
    print('download', URL.format(name), flush=True)
    with urllib.request.urlopen(URL.format(name), timeout=120) as response, open(part, 'wb') as handle:
        while chunk := response.read(1 << 20):
            handle.write(chunk)
    part.replace(target)
    return target


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('countries', nargs='*')
    parser.add_argument('--no-publish', action='store_true')
    parser.add_argument('--no-download', action='store_true')
    args = parser.parse_args()
    countries = [c.upper() for c in args.countries] or list(COUNTRIES)
    date = datetime.date.today().isoformat()
    manifest = json.loads((B / 'manifest.json').read_text()) if (B / 'manifest.json').exists() else {'packs': {}}
    for country in countries:
        name = COUNTRIES[country]
        pbf = B / 'raw' / f'{name}-latest.osm.pbf'
        if not args.no_download or not pbf.exists():
            pbf = download(name)
        stats = build(country, str(pbf), date, out_dir=str(B / 'dist'), work=str(B / 'work'))
        previous = (manifest['packs'].get(country) or {}).get('size')
        if previous and stats['size'] < previous * 2 / 3:
            sys.exit(f'{country}: {stats["size"]} bytes against {previous} published, not publishing')
    if args.no_publish:
        return
    subprocess.run([sys.executable, str(B / 'publish.py')], check=True)
    subprocess.run(['git', '-C', str(B), 'add', 'manifest.json'], check=True)
    if subprocess.run(['git', '-C', str(B), 'diff', '--cached', '--quiet']).returncode != 0:
        subprocess.run(['git', '-C', str(B), 'commit', '-m', f'Data {date}'], check=True)
        subprocess.run(['git', '-C', str(B), 'push', 'origin', 'main'], check=True)


if __name__ == '__main__':
    main()
