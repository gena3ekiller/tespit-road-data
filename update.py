#!/usr/bin/env python3
"""Downloads the extracts, builds the packs, checks them and publishes a release – on this Mac.

The whole world runs on GitHub (.github/workflows/build.yml); this is for single packs by hand.

update.py CH LI          these packs (ids from countries.py)
update.py --no-publish   build and check only
update.py --no-download  use the extracts already in raw/

A pack whose size drops by more than a third against the published one is not published (publish.py).
"""
import argparse
import datetime
import subprocess
import sys
import urllib.request
from pathlib import Path

from build_pack import build
from countries import BY_ID, URL

B = Path(__file__).resolve().parent


def download(path):
    target = B / 'raw' / (path.replace('/', '_') + '-latest.osm.pbf')
    if target.exists() and getattr(download, 'skip', False):
        return target
    part = target.with_suffix('.part')
    target.parent.mkdir(exist_ok=True)
    print('download', URL.format(path), flush=True)
    with urllib.request.urlopen(URL.format(path), timeout=120) as response, open(part, 'wb') as handle:
        while chunk := response.read(1 << 20):
            handle.write(chunk)
    part.replace(target)
    return target


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('packs', nargs='+')
    parser.add_argument('--no-publish', action='store_true')
    parser.add_argument('--no-download', action='store_true')
    args = parser.parse_args()
    download.skip = args.no_download
    date = datetime.date.today().isoformat()
    for pack in (p.upper() for p in args.packs):
        region = BY_ID[pack]
        pbfs = [str(download(path)) for path in region['paths']]
        build(pack, pbfs, date, out_dir=str(B / 'dist'), work=str(B / 'work'))
    if args.no_publish:
        return
    subprocess.run([sys.executable, str(B / 'publish.py')], check=True)
    subprocess.run(['git', '-C', str(B), 'add', 'manifest.json'], check=True)
    if subprocess.run(['git', '-C', str(B), 'diff', '--cached', '--quiet']).returncode != 0:
        subprocess.run(['git', '-C', str(B), 'commit', '-m', f'Data {date}'], check=True)
        subprocess.run(['git', '-C', str(B), 'push', 'origin', 'main'], check=True)


if __name__ == '__main__':
    main()
