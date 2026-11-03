# tespit-road-data

Road data for the Tespit app, built from OpenStreetMap: speed limits, overtaking bans and road signs
(stop, give way, level crossings, zebra crossings). Separate from the speed camera data (`tespit-map-data`).

- **Data:** each release (tag `data-YYYY-MM-DD`) carries one file per pack, `roads-XX-v1.bin`: the whole world,
  197 packs for 214 countries from the Geofabrik extracts (`countries.py`; a few packs cover several countries,
  such as the Gulf states or Malaysia, Singapore and Brunei). ODbL 1.0, © OpenStreetMap contributors
  (see `DATA-LICENSE.md`).
- **`manifest.json`:** per pack the release tag, file, size, SHA-256, data date, continent and the countries it
  covers, a global `enabled` switch and `disabledCountries` (pack ids). The app only reads it and carries no URLs
  of its own beyond this repository. The user picks the countries in the app; nothing loads by itself.
- **Build:** `.github/workflows/build.yml` builds every pack on GitHub's machines, monthly on the 7th or by hand
  (Actions → Build road packs, optionally only some pack ids), and publishes the changed ones as one release.
  A pack that comes out empty, or more than a third smaller than the published one, is not published.
- **Scripts:** `countries.py` (the packs, their continents and extracts), `build_pack.py` (osmium filter and
  export, simplify, cut, pack), `read_pack.py` (reads a pack back like the apps), `publish.py` (release and
  manifest, emergency switch), `update.py` (single packs on a Mac).
- **What is not in it:** limits that change with time or weather (`maxspeed:conditional`, variable signs),
  walking pace and unknown values. An OSM limit can be wrong or missing; the sign on the road applies.

## Pack format 1

Little endian.

| Part | Content |
| --- | --- |
| Header (23 B) | `TSRD`, format `u8` = 1, cell size `u16` in 1e-5° (5000 = 0.05°), country `2×ASCII`, data date `10×ASCII`, cell count `u32` |
| Index | per cell, sorted by (lat, lon): `i32` lat index, `i32` lon index (floor(degree / 0.05)), `u32` offset, `u32` length |
| Blocks | one raw-deflate block per cell |

A block, after inflating:

- `varint` road piece count, then per piece: speed `u8` (km/h; 0 = no limit, 255 = unknown, the piece carries an
  overtaking ban only), flags `u8` (bits 0–1 direction: 0 both, 1 along the points, 2 against them; bit 2 sign in
  mph; bit 3 no overtaking; bits 4–6 road class: 0 motorway … 7 living street), `varint` point count, points as
  zig-zag `varint` pairs (lat, lon) in 1e-5°: the first relative to the cell's corner, the others to the point
  before. A piece is at most about 800 m long and sits in the cell of its middle point.
- `varint` sign count, then per sign: type `u8` (1 stop, 2 give way, 3 level crossing, 4 zebra crossing) and a
  zig-zag `varint` pair relative to the cell's corner.

Code: MIT. Data: ODbL 1.0.
