#!/usr/bin/env python3
"""Builds one country's road pack for Tespit: speed limits, overtaking bans and road signs from OSM.

Usage: build_pack.py CC raw/<country>-latest.osm.pbf YYYY-MM-DD

1. `osmium tags-filter` keeps the ways with a speed limit or an overtaking tag and the sign nodes.
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

# Implicit limits written as a country code (wiki „Key:maxspeed“, country defaults for cars).
IMPLICIT = {
    "DE:urban": 50, "DE:rural": 100, "DE:motorway": NO_LIMIT, "DE:zone30": 30, "DE:zone:30": 30, "DE:zone20": 20,
    "DE:zone:20": 20, "DE:bicycle_road": 30,
    "AT:urban": 50, "AT:rural": 100, "AT:trunk": 100, "AT:motorway": 130, "AT:zone30": 30, "AT:zone:30": 30,
    "CH:urban": 50, "CH:rural": 80, "CH:trunk": 100, "CH:motorway": 120, "CH:zone30": 30, "CH:zone:30": 30,
    "CH:zone20": 20, "CH:zone:20": 20,
    "LI:urban": 50, "LI:rural": 80, "LI:zone30": 30, "LI:zone:30": 30,
}


def parse_speed(value):
    """km/h and whether the sign is in mph; None when the value is unknown, variable or a walking pace."""
    if value is None:
        return None
    value = value.strip()
    if value in IMPLICIT:
        return IMPLICIT[value], False
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


def filtered_features(country, pbf, work):
    os.makedirs(work, exist_ok=True)
    filtered = os.path.join(work, f"{country}-filtered.osm.pbf")
    lines = os.path.join(work, f"{country}.geojsonseq")
    run(["osmium", "tags-filter", "--overwrite", "-o", filtered, pbf,
         "w/maxspeed", "w/maxspeed:forward", "w/maxspeed:backward", "w/overtaking", "w/overtaking:forward",
         "w/overtaking:backward", "n/highway=stop,give_way,crossing", "n/railway=level_crossing"])
    run(["osmium", "export", "--overwrite", "-f", "geojsonseq", "--geometry-types=linestring,point", "-o", lines, filtered])
    with open(lines, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip().lstrip("\x1e")
            if line:
                yield json.loads(line)


def build(country, pbf, data_date, out_dir="dist", work="work"):
    cells = {}
    stats = {"roads": 0, "pieces": 0, "signs": 0, "skipped": 0}

    def cell(lon, lat):
        return cells.setdefault(cell_of(lon, lat), {"roads": [], "signs": []})

    for feature in filtered_features(country, pbf, work):
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
            cell(lon, lat)["signs"].append((kind, lon, lat))
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
                target["roads"].append((direction, speed, overtaking, road_class, piece))
                stats["pieces"] += 1

    os.makedirs(out_dir, exist_ok=True)
    keys = sorted(cells)
    blocks = []
    for key in keys:
        origin_lat, origin_lon = key[0] * CELL_E5, key[1] * CELL_E5
        body = bytearray(varint(len(cells[key]["roads"])))
        for direction, speed, overtaking, road_class, piece in cells[key]["roads"]:
            kmh, mph = speed if speed else (255, False)   # 255: no limit known, the piece carries a ban only
            flags = direction | (4 if mph else 0) | (8 if overtaking else 0) | (road_class << 4)
            body += bytes([kmh, flags]) + varint(len(piece))
            last_lat, last_lon = None, None
            for lon, lat in piece:
                lat5, lon5 = e5(lat), e5(lon)
                if last_lat is None:
                    # Relative to the cell's corner; a piece may reach past its cell.
                    body += varint(zigzag(lat5 - origin_lat)) + varint(zigzag(lon5 - origin_lon))
                else:
                    body += varint(zigzag(lat5 - last_lat)) + varint(zigzag(lon5 - last_lon))
                last_lat, last_lon = lat5, lon5
        body += varint(len(cells[key]["signs"]))
        for kind, lon, lat in cells[key]["signs"]:
            body += bytes([kind]) + varint(zigzag(e5(lat) - origin_lat)) + varint(zigzag(e5(lon) - origin_lon))
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
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    build(sys.argv[1].upper(), sys.argv[2], sys.argv[3])
