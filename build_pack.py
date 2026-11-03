#!/usr/bin/env python3
"""Builds one country's road pack for Tespit: speed limits, overtaking bans and road signs from OSM.

Usage: build_pack.py CC YYYY-MM-DD raw/<extract>-latest.osm.pbf [more extracts of the same pack …]

1. `osmium tags-filter` keeps the ways with a speed limit or an overtaking tag and the sign nodes; several
   extracts (Spain and the Canary Islands) are merged after filtering.
2. `osmium export` turns them into GeoJSON lines.
3. The roads are simplified, cut into pieces of at most ~800 m and sorted into cells of 0.05°; each
   cell is one raw-deflate block, so the app reads only the cells around the car (format in README).

Code MIT, data ODbL 1.0 (© OpenStreetMap contributors).
"""
import hashlib
import json
import math
import os
import re
import struct
import subprocess
import sys
import zlib

FORMAT_VERSION = 1
CELL_E5 = 5000          # 0.05° in 1e-5 degrees
CELL_DEG = CELL_E5 / 1e5
MAX_PIECE_M = 800.0
SIMPLIFY_M = 3.0

ROAD_CLASSES = {
    "motorway": 0, "motorway_link": 0, "trunk": 1, "trunk_link": 1, "primary": 2, "primary_link": 2,
    "secondary": 3, "secondary_link": 3, "tertiary": 4, "tertiary_link": 4,
    "unclassified": 5, "residential": 6, "living_street": 7,
}

# Sign types, the same numbers in both apps.
SIGN_STOP, SIGN_GIVE_WAY, SIGN_LEVEL_CROSSING, SIGN_ZEBRA = 1, 2, 3, 4

NO_LIMIT = 0            # "none": a German motorway without limit

# Implicit limits written as a country code (wiki „Key:maxspeed“ and „Default speed limits“, cars). Only the
# clear ones: a code whose value depends on time, season or region (NL:motorway, FI:motorway) stays unknown.
# „XX:zone30“ and „XX:zone:30“ are read from the number (ZONE below).
IMPLICIT = {
    "DE:urban": 50, "DE:rural": 100, "DE:motorway": NO_LIMIT, "DE:bicycle_road": 30,
    "AT:urban": 50, "AT:rural": 100, "AT:trunk": 100, "AT:motorway": 130,
    "CH:urban": 50, "CH:rural": 80, "CH:trunk": 100, "CH:motorway": 120,
    "LI:urban": 50, "LI:rural": 80,
    "BE:urban": 50, "BE-VLG:rural": 70, "BE-WAL:rural": 90, "BE:motorway": 120,
    "BG:urban": 50, "BG:rural": 90, "BG:motorway": 140,
    "BY:urban": 60, "BY:rural": 90, "BY:motorway": 120,
    "CZ:urban": 50, "CZ:rural": 90, "CZ:motorway": 130,
    "DK:urban": 50, "DK:rural": 80, "DK:motorway": 130,
    "EE:urban": 50, "EE:rural": 90,
    "ES:urban": 50, "ES:rural": 90, "ES:motorway": 120,
    "FI:urban": 50, "FI:rural": 80,
    "FR:urban": 50, "FR:rural": 80, "FR:motorway": 130,
    "GB:nsl_restricted": (30, True), "GB:nsl_single": (60, True), "GB:nsl_dual": (70, True), "GB:motorway": (70, True),
    "GR:urban": 50, "GR:rural": 90, "GR:motorway": 130,
    "HR:urban": 50, "HR:rural": 90, "HR:motorway": 130,
    "HU:urban": 50, "HU:rural": 90, "HU:motorway": 130,
    "IE:urban": 50, "IE:rural": 80, "IE:national": 100, "IE:motorway": 120,
    "IT:urban": 50, "IT:rural": 90, "IT:trunk": 110, "IT:motorway": 130,
    "LT:urban": 50, "LT:rural": 90,
    "LU:urban": 50, "LU:rural": 90, "LU:motorway": 130,
    "LV:urban": 50, "LV:rural": 90,
    "NL:urban": 50, "NL:rural": 80, "NL:trunk": 100,
    "NO:urban": 50, "NO:rural": 80,
    "PL:urban": 50, "PL:rural": 90, "PL:expressway": 120, "PL:motorway": 140,
    "PT:urban": 50, "PT:rural": 90, "PT:motorway": 120,
    "RO:urban": 50, "RO:rural": 90, "RO:motorway": 130,
    "RS:urban": 50, "RS:rural": 80, "RS:motorway": 130,
    "RU:urban": 60, "RU:rural": 90, "RU:motorway": 110,
    "SE:urban": 50, "SE:rural": 70,
    "SI:urban": 50, "SI:rural": 90, "SI:motorway": 130,
    "SK:urban": 50, "SK:rural": 90, "SK:motorway": 130,
    "TR:urban": 50, "TR:rural": 90, "TR:motorway": 120,
    "UA:urban": 50, "UA:rural": 90, "UA:motorway": 130,
    "AU:urban": 50, "AU:rural": 100,
    "NZ:urban": 50, "NZ:rural": 100,
    "JP:nsl": 60, "JP:motorway": 100,
    "ZA:urban": 60, "ZA:rural": 100, "ZA:motorway": 120,
}
ZONE = re.compile(r"[A-Z]{2}(-[A-Z0-9]{1,3})?:zone:?(\d{1,2})")


def parse_speed(value):
    """km/h and whether the sign is in mph; None when the value is unknown, variable or a walking pace."""
    if value is None:
        return None
    value = value.strip()
    if value in IMPLICIT:
        implicit = IMPLICIT[value]
        if isinstance(implicit, tuple):
            return round(implicit[0] * 1.609344), True
        return implicit, False
    zone = ZONE.fullmatch(value)
    if zone:
        number = int(zone.group(2))
        return (number, False) if 5 <= number <= 80 else None
    if value == "none":
        return NO_LIMIT, False
    match = re.fullmatch(r"(\d{1,3})(\s*mph)?", value)
    if not match:
        return None
    number = int(match.group(1))
    if match.group(2):
        kmh = round(number * 1.609344)
        return (kmh, True) if 5 <= kmh <= 200 else None
    return (number, False) if 5 <= number <= 200 else None


def meters(lat1, lon1, lat2, lon2):
    x = math.radians(lon2 - lon1) * math.cos(math.radians((lat1 + lat2) / 2))
    y = math.radians(lat2 - lat1)
    return math.hypot(x, y) * 6371000.0


def simplify(points, tolerance):
    """Douglas-Peucker on a local flat projection."""
    if len(points) < 3:
        return points
    lat0 = math.radians(points[0][1])
    xy = [(lon * 111320.0 * math.cos(lat0), lat * 110540.0) for lon, lat in points]
    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]
    while stack:
        first, last = stack.pop()
        ax, ay = xy[first]
        bx, by = xy[last]
        dx, dy = bx - ax, by - ay
        length = math.hypot(dx, dy)
        best, index = -1.0, -1
        for i in range(first + 1, last):
            px, py = xy[i]
            if length == 0:
                distance = math.hypot(px - ax, py - ay)
            else:
                distance = abs(dy * px - dx * py + bx * ay - by * ax) / length
            if distance > best:
                best, index = distance, i
        if best > tolerance and index > 0:
            keep[index] = True
            stack.append((first, index))
            stack.append((index, last))
    return [p for p, k in zip(points, keep) if k]


def pieces(points):
    """Cuts a line into pieces of at most MAX_PIECE_M; neighbours share their end point."""
    out, current, length = [], [points[0]], 0.0
    for previous, point in zip(points, points[1:]):
        step = meters(previous[1], previous[0], point[1], point[0])
        if length + step > MAX_PIECE_M and len(current) > 1:
            out.append(current)
            current, length = [previous], 0.0
        current.append(point)
        length += step
    if len(current) > 1:
        out.append(current)
    return out


def varint(value):
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)


def zigzag(value):
    return (value << 1) ^ (value >> 63)


def cell_of(lon, lat):
    return math.floor(lat / CELL_DEG), math.floor(lon / CELL_DEG)


def e5(value):
    return int(round(value * 1e5))


def run(cmd):
    print("+", " ".join(cmd), flush=True)
    subprocess.run(cmd, check=True)


FILTER = ["w/maxspeed", "w/maxspeed:forward", "w/maxspeed:backward", "w/overtaking", "w/overtaking:forward",
          "w/overtaking:backward", "n/highway=stop,give_way,crossing", "n/railway=level_crossing"]


def filtered_features(country, pbfs, work):
    os.makedirs(work, exist_ok=True)
    lines = os.path.join(work, f"{country}.geojsonseq")
    parts = []
    for number, pbf in enumerate(pbfs):
        part = os.path.join(work, f"{country}-filtered-{number}.osm.pbf")
        run(["osmium", "tags-filter", "--overwrite", "-o", part, pbf, *FILTER])
        parts.append(part)
    filtered = parts[0]
    if len(parts) > 1:
        filtered = os.path.join(work, f"{country}-filtered.osm.pbf")
        run(["osmium", "merge", "--overwrite", "-o", filtered, *parts])
    run(["osmium", "export", "--overwrite", "-f", "geojsonseq", "--geometry-types=linestring,point", "-o", lines, filtered])
    with open(lines, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip().lstrip("\x1e")
            if line:
                yield json.loads(line)


def build(country, pbfs, data_date, out_dir="dist", work="work"):
    # Each piece and sign is written into its cell's bytes at once, so Germany fits in memory.
    cells = {}
    stats = {"roads": 0, "pieces": 0, "signs": 0, "skipped": 0}

    def cell(lon, lat):
        key = cell_of(lon, lat)
        entry = cells.get(key)
        if entry is None:
            entry = cells[key] = {"key": key, "roads": bytearray(), "road_count": 0, "signs": bytearray(), "sign_count": 0}
        return entry

    def add_road(target, direction, speed, overtaking, road_class, piece):
        origin_lat, origin_lon = target["key"][0] * CELL_E5, target["key"][1] * CELL_E5
        kmh, mph = speed if speed else (255, False)   # 255: no limit known, the piece carries a ban only
        flags = direction | (4 if mph else 0) | (8 if overtaking else 0) | (road_class << 4)
        body = target["roads"]
        body += bytes([kmh, flags]) + varint(len(piece))
        last_lat, last_lon = origin_lat, origin_lon
        for lon, lat in piece:
            # The first point relative to the cell's corner (a piece may reach past its cell), then deltas.
            lat5, lon5 = e5(lat), e5(lon)
            body += varint(zigzag(lat5 - last_lat)) + varint(zigzag(lon5 - last_lon))
            last_lat, last_lon = lat5, lon5
        target["road_count"] += 1

    def add_sign(kind, lon, lat):
        target = cell(lon, lat)
        origin_lat, origin_lon = target["key"][0] * CELL_E5, target["key"][1] * CELL_E5
        target["signs"] += bytes([kind]) + varint(zigzag(e5(lat) - origin_lat)) + varint(zigzag(e5(lon) - origin_lon))
        target["sign_count"] += 1

    for feature in filtered_features(country, pbfs, work):
        tags = feature.get("properties") or {}
        geometry = feature.get("geometry") or {}
        if geometry.get("type") == "Point":
            lon, lat = geometry["coordinates"]
            kind = None
            if tags.get("highway") == "stop":
                kind = SIGN_STOP
            elif tags.get("highway") == "give_way":
                kind = SIGN_GIVE_WAY
            elif tags.get("railway") == "level_crossing":
                kind = SIGN_LEVEL_CROSSING
            elif tags.get("highway") == "crossing" and (tags.get("crossing") in ("zebra", "uncontrolled", "marked")
                                                         or tags.get("crossing_ref") == "zebra"):
                kind = SIGN_ZEBRA
            if kind is None:
                continue
            add_sign(kind, lon, lat)
            stats["signs"] += 1
            continue
        if geometry.get("type") != "LineString":
            continue
        road_class = ROAD_CLASSES.get(tags.get("highway"))
        if road_class is None:
            continue
        points = geometry["coordinates"]
        if len(points) < 2:
            continue
        both = parse_speed(tags.get("maxspeed"))
        forward = parse_speed(tags.get("maxspeed:forward")) or both
        backward = parse_speed(tags.get("maxspeed:backward")) or both
        no_overtaking = tags.get("overtaking") == "no"
        overtaking_fw = no_overtaking or tags.get("overtaking:forward") == "no"
        overtaking_bw = no_overtaking or tags.get("overtaking:backward") == "no"
        oneway = tags.get("oneway") in ("yes", "1", "true") or tags.get("highway") in ("motorway", "motorway_link") \
            or tags.get("junction") == "roundabout"
        reverse = tags.get("oneway") == "-1"
        entries = []
        if forward == backward and overtaking_fw == overtaking_bw:
            if forward or overtaking_fw:
                entries.append((0, forward, overtaking_fw))
        else:
            if forward or overtaking_fw:
                entries.append((1, forward, overtaking_fw))
            if not oneway and (backward or overtaking_bw):
                entries.append((2, backward, overtaking_bw))
        if not entries:
            stats["skipped"] += 1
            continue
        if reverse:
            points = list(reversed(points))
        stats["roads"] += 1
        simple = simplify(points, SIMPLIFY_M)
        for piece in pieces(simple):
            mid = piece[len(piece) // 2]
            target = cell(mid[0], mid[1])
            for direction, speed, overtaking in entries:
                add_road(target, direction, speed, overtaking, road_class, piece)
                stats["pieces"] += 1

    os.makedirs(out_dir, exist_ok=True)
    keys = sorted(cells)
    blocks = []
    for key in keys:
        entry = cells[key]
        body = varint(entry["road_count"]) + bytes(entry["roads"]) + varint(entry["sign_count"]) + bytes(entry["signs"])
        compressor = zlib.compressobj(9, zlib.DEFLATED, -15)
        blocks.append(compressor.compress(bytes(body)) + compressor.flush())

    header = b"TSRD" + struct.pack("<BH2s10sI", FORMAT_VERSION, CELL_E5, country.encode(), data_date.encode(), len(keys))
    index_size = len(keys) * 16
    offset = len(header) + index_size
    index = bytearray()
    for key, block in zip(keys, blocks):
        index += struct.pack("<iiII", key[0], key[1], offset, len(block))
        offset += len(block)
    path = os.path.join(out_dir, f"roads-{country}-v{FORMAT_VERSION}.bin")
    with open(path, "wb") as handle:
        handle.write(header)
        handle.write(index)
        for block in blocks:
            handle.write(block)
    data = open(path, "rb").read()
    stats.update(cells=len(keys), size=len(data), sha256=hashlib.sha256(data).hexdigest(), file=os.path.basename(path))
    print(json.dumps(stats), flush=True)
    return stats


if __name__ == "__main__":
    if len(sys.argv) < 4 or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", sys.argv[2]):
        sys.exit(__doc__)
    build(sys.argv[1].upper(), sys.argv[3:], sys.argv[2])
