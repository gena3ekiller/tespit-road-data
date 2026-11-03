#!/usr/bin/env python3
"""Publishes the road packs in dist/ as one release and writes manifest.json.

- One release per data date (tag data-YYYY-MM-DD, .2, .3 … on the same day); releases are never overwritten and
  stay at least 180 days (ODbL).
- manifest.json carries no URLs; the app builds them from tag and file name and checks size and SHA-256.

publish.py                 release dist/roads-*-v1.bin, write manifest.json (then commit and push)
publish.py --dry-run       only write manifest.json
publish.py --off / --on    emergency switch: enabled=false (the app removes its packs)
publish.py --disable DE    switch single countries off (--enable DE to undo)
"""
import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

B = Path(__file__).resolve().parent
REPO = 'gena3ekiller/tespit-road-data'
DIST = B / 'dist'
MANIFEST = B / 'manifest.json'
MIN_APP_VERSION = '1.1.17'
FORMAT = 1


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def load_manifest():
    if MANIFEST.exists():
        return json.loads(MANIFEST.read_text(encoding='utf-8'))
    return {'schema': 1, 'enabled': True, 'disabledCountries': [], 'minAppVersion': MIN_APP_VERSION, 'format': FORMAT, 'packs': {}}


def write_manifest(manifest):
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=1, sort_keys=True) + '\n', encoding='utf-8')
    print('manifest.json:', {k: v for k, v in manifest.items() if k != 'packs'}, sorted(manifest['packs']))


def existing_tags():
    out = subprocess.run(['gh', 'release', 'list', '--repo', REPO, '--limit', '200', '--json', 'tagName'],
                         capture_output=True, text=True)
    return {r['tagName'] for r in json.loads(out.stdout or '[]')} if out.returncode == 0 else set()


def pack_date(data):
    if data[:4] != b'TSRD' or data[4] != FORMAT:
        sys.exit('not a road pack of format 1')
    return data[9:19].decode()


def publish(dry_run):
    files = sorted(DIST.glob(f'roads-*-v{FORMAT}.bin'))
    if not files:
        sys.exit('dist/ has no packs')
    manifest = load_manifest()
    changed, dates = {}, set()
    for path in files:
        country = re.match(r'roads-([A-Z]{2})-', path.name).group(1)
        data = path.read_bytes()
        entry = {'file': path.name, 'size': len(data), 'sha256': sha256(data), 'dataDate': pack_date(data)}
        if (manifest['packs'].get(country) or {}).get('sha256') == entry['sha256']:
            continue
        changed[country] = (path, entry)
        dates.add(entry['dataDate'])
    if not changed:
        print('Unchanged, no new release')
        return
    date = max(dates)
    tags = existing_tags()
    tag, n = f'data-{date}', 1
    while tag in tags:
        n += 1
        tag = f'data-{date}.{n}'
    for country, (path, entry) in changed.items():
        manifest['packs'][country] = dict(entry, tag=tag)
    if dry_run:
        write_manifest(manifest)
        return
    notes = (f'Road data (speed limits, overtaking bans, stop and give-way signs, level crossings, zebra crossings), '
             f'OpenStreetMap as of {date}: {", ".join(sorted(changed))}.\n\n'
             '© OpenStreetMap contributors, ODbL 1.0 — https://www.openstreetmap.org/copyright')
    subprocess.run(['gh', 'release', 'create', tag, *[str(p) for p, _ in changed.values()], '--repo', REPO,
                    '--title', f'Data {date}', '--notes', notes], check=True)
    write_manifest(manifest)
    print('Now commit and push manifest.json.')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--off', action='store_true')
    parser.add_argument('--on', action='store_true')
    parser.add_argument('--disable')
    parser.add_argument('--enable')
    args = parser.parse_args()
    if args.off or args.on or args.disable or args.enable:
        manifest = load_manifest()
        if args.off:
            manifest['enabled'] = False
        if args.on:
            manifest['enabled'] = True
        countries = set(manifest.get('disabledCountries', []))
        countries |= {c.strip().upper() for c in (args.disable or '').split(',') if c.strip()}
        countries -= {c.strip().upper() for c in (args.enable or '').split(',') if c.strip()}
        manifest['disabledCountries'] = sorted(countries)
        write_manifest(manifest)
        print('Now commit and push manifest.json.')
        return
    publish(args.dry_run)


if __name__ == '__main__':
    main()
