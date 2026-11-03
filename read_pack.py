#!/usr/bin/env python3
"""Reads a road pack back (the same steps as the apps) and answers a speed limit for a point.

Usage: read_pack.py dist/roads-CH-v1.bin [lat lon]
"""
import math
import struct
import sys
import zlib

from build_pack import CELL_E5, meters


def read_varint(data, pos):
    shift = result = 0
    while True:
        byte = data[pos]
        pos += 1
        result |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return result, pos
        shift += 7


def unzigzag(value):
    return (value >> 1) ^ -(value & 1)


class Pack:
    def __init__(self, path):
        self.data = open(path, "rb").read()
        magic, version, cell, country, date, count = struct.unpack_from("<4sBH2s10sI", self.data, 0)
        assert magic == b"TSRD" and version == 1 and cell == CELL_E5
        self.country, self.date = country.decode(), date.decode()
        self.index = {}
        base = struct.calcsize("<4sBH2s10sI")
        for i in range(count):
            lat_i, lon_i, offset, length = struct.unpack_from("<iiII", self.data, base + i * 16)
            self.index[(lat_i, lon_i)] = (offset, length)

    def cell(self, key):
        if key not in self.index:
            return [], []
        offset, length = self.index[key]
        body = zlib.decompress(self.data[offset:offset + length], -15)
        origin_lat, origin_lon = key[0] * CELL_E5, key[1] * CELL_E5
        pos = 0
        count, pos = read_varint(body, pos)
        roads = []
        for _ in range(count):
            kmh, flags = body[pos], body[pos + 1]
            pos += 2
            n, pos = read_varint(body, pos)
            points, lat, lon = [], origin_lat, origin_lon
            for _ in range(n):
                dlat, pos = read_varint(body, pos)
                dlon, pos = read_varint(body, pos)
                lat += unzigzag(dlat)
                lon += unzigzag(dlon)
                points.append((lat / 1e5, lon / 1e5))
            roads.append((kmh, flags, points))
        count, pos = read_varint(body, pos)
        signs = []
        for _ in range(count):
            kind = body[pos]
            pos += 1
            dlat, pos = read_varint(body, pos)
            dlon, pos = read_varint(body, pos)
            signs.append((kind, (origin_lat + unzigzag(dlat)) / 1e5, (origin_lon + unzigzag(dlon)) / 1e5))
        assert pos == len(body)
        return roads, signs

    def nearest(self, lat, lon):
        key = (math.floor(lat * 1e5 / CELL_E5), math.floor(lon * 1e5 / CELL_E5))
        best = None
        for dlat in (-1, 0, 1):
            for dlon in (-1, 0, 1):
                for kmh, flags, points in self.cell((key[0] + dlat, key[1] + dlon))[0]:
                    for a, b in zip(points, points[1:]):
                        distance = segment_distance(lat, lon, a, b)
                        if best is None or distance < best[0]:
                            best = (distance, kmh, flags)
        return best


def segment_distance(lat, lon, a, b):
    scale = math.cos(math.radians(lat))
    ax, ay = (a[1] - lon) * scale * 111320, (a[0] - lat) * 110540
    bx, by = (b[1] - lon) * scale * 111320, (b[0] - lat) * 110540
    dx, dy = bx - ax, by - ay
    t = 0 if dx == dy == 0 else max(0, min(1, -(ax * dx + ay * dy) / (dx * dx + dy * dy)))
    return math.hypot(ax + t * dx, ay + t * dy)


if __name__ == "__main__":
    pack = Pack(sys.argv[1])
    roads = signs = 0
    for key in pack.index:
        r, s = pack.cell(key)
        roads += len(r)
        signs += len(s)
    print(pack.country, pack.date, "cells", len(pack.index), "pieces", roads, "signs", signs)
    if len(sys.argv) == 4:
        print("nearest", pack.nearest(float(sys.argv[2]), float(sys.argv[3])))
