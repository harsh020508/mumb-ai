#!/usr/bin/env python3
"""Build geographically correct LOD-0 collision tiles for each Indian city.

The committed server_tiles/*.db files were byte-identical copies of the San
Francisco map (EPSG:32610, WGS-84 bbox around -122.5/37.7). This rebuilds each
city's DB with the city's real WGS-84 bbox and UTM zone from
config/cities/<slug>.toml, a land/water mask that follows that city's
coastline/rivers, and a walkable road grid on land so pathfinding has somewhere
to go.

Schema matches sim-maps / geo.rs (LOD-0 collision + manifest). Render blobs are
1-byte placeholders (the backend never reads them; see tools/slim_tiles.sh).
"""
from __future__ import annotations

import json
import math
import os
import sqlite3
import tomllib

import zstandard as zstd

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CPC = 125
MPC = 2.0
CHUNK_M = 250.0
LODS = 6

ROAD = 0
GRASS = 2
BLOCKED = 255

CITIES = {
    "mumbai": {
        "neighborhoods": {
            2700100: (72.832, 18.932),
            2700105: (72.840, 19.060),
            2700106: (72.847, 19.119),
            2700107: (72.849, 19.166),
            2700108: (72.856, 19.230),
            2700110: (72.899, 19.062),
            2700111: (72.908, 19.103),
            2700114: (72.857, 19.044),
        },
    },
    "delhi": {
        "neighborhoods": {
            700700: (77.209, 28.656),
            700701: (77.230, 28.613),
            700702: (77.185, 28.570),
            700703: (77.102, 28.704),
            700704: (77.229, 28.628),
        },
    },
    "kolkata": {
        "neighborhoods": {
            1901900: (88.351, 22.572),
            1901901: (88.363, 22.545),
            1901902: (88.392, 22.595),
            1901903: (88.345, 22.620),
            1901904: (88.370, 22.530),
        },
    },
    "bangalore": {
        "neighborhoods": {
            2902900: (77.594, 12.972),
            2902901: (77.640, 12.978),
            2902902: (77.620, 12.930),
            2902903: (77.550, 12.920),
            2902904: (77.580, 13.035),
        },
    },
    "jaipur": {
        "neighborhoods": {
            800800: (75.787, 26.912),
            800801: (75.820, 26.900),
            800802: (75.805, 26.880),
            800803: (75.760, 26.920),
            800804: (75.850, 26.850),
        },
    },
}


def lonlat_to_utm(lon_deg: float, lat_deg: float, zone: float) -> tuple[float, float]:
    a = 6378137.0
    f = 1.0 / 298.257223563
    k0 = 0.9996
    e2 = f * (2.0 - f)
    ep2 = e2 / (1.0 - e2)
    lon0 = ((zone - 1.0) * 6.0 - 180.0 + 3.0) * math.pi / 180.0
    phi = lat_deg * math.pi / 180.0
    lam = lon_deg * math.pi / 180.0
    n = a / math.sqrt(1.0 - e2 * math.sin(phi) ** 2)
    t = math.tan(phi) ** 2
    c = ep2 * math.cos(phi) ** 2
    aa = math.cos(phi) * (lam - lon0)
    m = a * (
        (1.0 - e2 / 4.0 - 3.0 * e2 * e2 / 64.0 - 5.0 * e2**3 / 256.0) * phi
        - (3.0 * e2 / 8.0 + 3.0 * e2 * e2 / 32.0 + 45.0 * e2**3 / 1024.0) * math.sin(2.0 * phi)
        + (15.0 * e2 * e2 / 256.0 + 45.0 * e2**3 / 1024.0) * math.sin(4.0 * phi)
        - (35.0 * e2**3 / 3072.0) * math.sin(6.0 * phi)
    )
    easting = (
        k0
        * n
        * (
            aa
            + (1.0 - t + c) * aa**3 / 6.0
            + (5.0 - 18.0 * t + t * t + 72.0 * c - 58.0 * ep2) * aa**5 / 120.0
        )
        + 500_000.0
    )
    northing = k0 * (
        m
        + n
        * math.tan(phi)
        * (
            aa * aa / 2.0
            + (5.0 - t + 9.0 * c + 4.0 * c * c) * aa**4 / 24.0
            + (61.0 - 58.0 * t + t * t + 600.0 * c - 330.0 * ep2) * aa**6 / 720.0
        )
    )
    return easting, northing


def utm_to_lonlat(easting: float, northing: float, zone: float) -> tuple[float, float]:
    a = 6378137.0
    f = 1.0 / 298.257223563
    k0 = 0.9996
    e2 = f * (2.0 - f)
    ep2 = e2 / (1.0 - e2)
    lon0 = ((zone - 1.0) * 6.0 - 180.0 + 3.0) * math.pi / 180.0
    x = easting - 500_000.0
    y = northing
    m = y / k0
    e1 = (1.0 - math.sqrt(1.0 - e2)) / (1.0 + math.sqrt(1.0 - e2))
    mu = m / (a * (1.0 - e2 / 4.0 - 3.0 * e2 * e2 / 64.0 - 5.0 * e2**3 / 256.0))
    phi1 = (
        mu
        + (3.0 * e1 / 2.0 - 27.0 * e1**3 / 32.0) * math.sin(2.0 * mu)
        + (21.0 * e1 * e1 / 16.0 - 55.0 * e1**4 / 32.0) * math.sin(4.0 * mu)
        + (151.0 * e1**3 / 96.0) * math.sin(6.0 * mu)
        + (1097.0 * e1**4 / 512.0) * math.sin(8.0 * mu)
    )
    sin_p = math.sin(phi1)
    cos_p = math.cos(phi1)
    tan_p = math.tan(phi1)
    n1 = a / math.sqrt(1.0 - e2 * sin_p * sin_p)
    t1 = tan_p * tan_p
    c1 = ep2 * cos_p * cos_p
    r1 = a * (1.0 - e2) / (1.0 - e2 * sin_p * sin_p) ** 1.5
    d = x / (n1 * k0)
    lat = phi1 - (n1 * tan_p / r1) * (
        d * d / 2.0
        - (5.0 + 3.0 * t1 + 10.0 * c1 - 4.0 * c1 * c1 - 9.0 * ep2) * d**4 / 24.0
        + (61.0 + 90.0 * t1 + 298.0 * c1 + 45.0 * t1 * t1 - 252.0 * ep2 - 3.0 * c1 * c1)
        * d**6
        / 720.0
    )
    lon = lon0 + (
        d
        - (1.0 + 2.0 * t1 + c1) * d**3 / 6.0
        + (5.0 - 2.0 * c1 + 28.0 * t1 - 3.0 * c1 * c1 + 8.0 * ep2 + 24.0 * t1 * t1) * d**5 / 120.0
    ) / cos_p
    return lon * 180.0 / math.pi, lat * 180.0 / math.pi


def reproject_bbox(west, south, east, north, zone):
    xs, ys = [], []
    for lon, lat in ((west, south), (east, south), (west, north), (east, north)):
        x, y = lonlat_to_utm(lon, lat, zone)
        xs.append(x)
        ys.append(y)
    return min(xs), min(ys), max(xs), max(ys)


def utm_zone_from_epsg(epsg: str) -> float:
    return float(int(epsg.rsplit(":", 1)[-1]) - 32600)


def mumbai_land(lon, lat) -> bool:
    if lat < 18.890 or lat > 19.280:
        return False
    if lon < 72.775 or lon > 72.985:
        return False
    if lat < 18.950:
        return 72.805 <= lon <= 72.848
    if lat < 19.000:
        return 72.795 <= lon <= 72.870
    if lat < 19.040:
        return 72.790 <= lon <= 72.888
    if lon < 72.905:
        return lon >= 72.782
    if lon > 72.938:
        return lat >= 19.015
    return False


def delhi_land(lon, lat) -> bool:
    if 77.228 <= lon <= 77.268:
        return False
    return True


def kolkata_land(lon, lat) -> bool:
    if lon < 88.315:
        return False
    return True


def bangalore_land(lon, lat) -> bool:
    lakes = (
        (77.619, 12.983, 0.012),
        (77.667, 12.935, 0.018),
        (77.598, 12.950, 0.008),
    )
    for cx, cy, r in lakes:
        if (lon - cx) ** 2 + (lat - cy) ** 2 < r * r:
            return False
    return True


def jaipur_land(lon, lat) -> bool:
    if (lon - 75.847) ** 2 + (lat - 26.896) ** 2 < 0.008**2:
        return False
    return True


LAND_FN = {
    "mumbai": mumbai_land,
    "delhi": delhi_land,
    "kolkata": kolkata_land,
    "bangalore": bangalore_land,
    "jaipur": jaipur_land,
}


def classify_chunk(land_fn, min_x, max_y, cx, cy, zone) -> str:
    """all_water / all_land / mixed, from 3x3 samples across the chunk."""
    hits = 0
    n = 0
    for i in (0.1, 0.5, 0.9):
        for j in (0.1, 0.5, 0.9):
            ux = min_x + (cx + i) * CHUNK_M
            uy = max_y - (cy + j) * CHUNK_M
            lon, lat = utm_to_lonlat(ux, uy, zone)
            n += 1
            if land_fn(lon, lat):
                hits += 1
    if hits == 0:
        return "water"
    if hits == n:
        return "land"
    return "mixed"


def fill_pattern(kind: str, land_fn, min_x, max_y, cx, cy, zone) -> bytes:
    grid = bytearray(CPC * CPC)
    if kind == "water":
        grid[:] = bytes([BLOCKED]) * (CPC * CPC)
        return bytes(grid)
    # land or mixed: stamp a 50 m road grid; mixed re-checks land per 5-cell block
    for row in range(CPC):
        base = row * CPC
        road_row = row % 25 == 0
        grass_row = row % 25 < 3
        for col in range(CPC):
            if kind == "mixed" and row % 5 == 0 and col % 5 == 0:
                ux = min_x + (cx * CPC + col + 2.5) * MPC
                uy = max_y - (cy * CPC + row + 2.5) * MPC
                lon, lat = utm_to_lonlat(ux, uy, zone)
                land = land_fn(lon, lat)
                val = ROAD if land and (road_row or col % 25 == 0) else (
                    GRASS if land and (grass_row or col % 25 < 3) else (BLOCKED if not land else BLOCKED)
                )
                # fill 5x5
                for dr in range(5):
                    rr = row + dr
                    if rr >= CPC:
                        break
                    b = rr * CPC
                    rr_road = rr % 25 == 0
                    rr_grass = rr % 25 < 3
                    for dc in range(5):
                        cc = col + dc
                        if cc >= CPC:
                            break
                        if not land:
                            bval = BLOCKED
                        elif rr_road or cc % 25 == 0:
                            bval = ROAD
                        elif rr_grass or cc % 25 < 3:
                            bval = GRASS
                        else:
                            bval = BLOCKED
                        grid[b + cc] = bval
            elif kind == "land":
                if road_row or col % 25 == 0:
                    grid[base + col] = ROAD
                elif grass_row or col % 25 < 3:
                    grid[base + col] = GRASS
                else:
                    grid[base + col] = BLOCKED
    return bytes(grid)


def load_city_cfg(slug: str) -> dict:
    with open(os.path.join(REPO, "config", "cities", f"{slug}.toml"), "rb") as f:
        return tomllib.load(f)


def build_city(slug: str) -> dict:
    cfg = load_city_cfg(slug)
    bb = cfg["bbox_wgs84"]
    epsg = cfg["crs"]["utm_epsg"]
    zone = utm_zone_from_epsg(epsg)
    min_x, min_y, max_x, max_y = reproject_bbox(bb["west"], bb["south"], bb["east"], bb["north"], zone)
    nx = int(math.ceil((max_x - min_x) / CHUNK_M))
    ny = int(math.ceil((max_y - min_y) / CHUNK_M))
    land_fn = LAND_FN[slug]
    cctx = zstd.ZstdCompressor(level=3)

    out = os.path.join(REPO, "server_tiles", f"{slug}.db")
    tmp = out + ".new"
    if os.path.exists(tmp):
        os.remove(tmp)
    con = sqlite3.connect(tmp)
    con.execute("PRAGMA journal_mode=OFF")
    con.execute("PRAGMA synchronous=OFF")
    con.execute(
        """CREATE TABLE chunks (
             cx INTEGER NOT NULL, cy INTEGER NOT NULL, lod INTEGER NOT NULL,
             render BLOB NOT NULL, collision BLOB NOT NULL,
             w INTEGER NOT NULL, h INTEGER NOT NULL,
             PRIMARY KEY (cx, cy, lod))"""
    )
    con.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    con.execute(
        """CREATE TABLE buildings (
             cx INTEGER NOT NULL, cy INTEGER NOT NULL,
             cell_x REAL NOT NULL, cell_y REAL NOT NULL,
             cell_w REAL NOT NULL, cell_h REAL NOT NULL,
             tier INTEGER NOT NULL,
             PRIMARY KEY (cx, cy, cell_x, cell_y))"""
    )
    manifest = {
        "crs": epsg,
        "bbox_wgs84": {
            "west": bb["west"],
            "south": bb["south"],
            "east": bb["east"],
            "north": bb["north"],
        },
        "bbox_utm": {"min_x": min_x, "min_y": min_y, "max_x": max_x, "max_y": max_y},
        "meters_per_cell": MPC,
        "chunk_meters": CHUNK_M,
        "cells_per_chunk": CPC,
        "lod_levels": LODS,
        "atlas": {"columns": 47, "path": "assets/atlas.png", "tile_height": 32, "tile_width": 32},
        "city": slug,
    }
    con.execute(
        "INSERT INTO meta(key, value) VALUES(?, ?)",
        ("manifest", json.dumps(manifest, separators=(",", ":"))),
    )

    placeholder = b"\x00"
    water_blob = cctx.compress(bytes([BLOCKED]) * (CPC * CPC))
    land_blob = cctx.compress(fill_pattern("land", land_fn, min_x, max_y, 0, 0, zone))

    rows = []
    n_land = n_water = n_mixed = 0
    for cy in range(ny):
        for cx in range(nx):
            kind = classify_chunk(land_fn, min_x, max_y, cx, cy, zone)
            if kind == "water":
                blob = water_blob
                n_water += 1
            elif kind == "land":
                blob = land_blob
                n_land += 1
            else:
                blob = cctx.compress(fill_pattern("mixed", land_fn, min_x, max_y, cx, cy, zone))
                n_mixed += 1
            rows.append((cx, cy, 0, placeholder, blob, CPC, CPC))
        if len(rows) >= 256:
            con.executemany(
                "INSERT INTO chunks(cx, cy, lod, render, collision, w, h) VALUES(?,?,?,?,?,?,?)",
                rows,
            )
            rows.clear()
        if (cy + 1) % 40 == 0 or cy + 1 == ny:
            print(f"  {slug}: {cy + 1}/{ny}  land={n_land} water={n_water} mixed={n_mixed}", flush=True)
    if rows:
        con.executemany(
            "INSERT INTO chunks(cx, cy, lod, render, collision, w, h) VALUES(?,?,?,?,?,?,?)",
            rows,
        )
    con.commit()
    con.close()
    os.replace(tmp, out)

    centroids = []
    for puma, (lon, lat) in CITIES[slug]["neighborhoods"].items():
        ux, uy = lonlat_to_utm(lon, lat, zone)
        cx = int(round((ux - min_x) / CHUNK_M))
        cy = int(round((max_y - uy) / CHUNK_M))
        cx = max(0, min(nx - 1, cx))
        cy = max(0, min(ny - 1, cy))
        centroids.append((puma, cx, cy, 12))

    size = os.path.getsize(out)
    print(f"{slug}: {nx}x{ny} chunks land={n_land} water={n_water} mixed={n_mixed} {size / 1e6:.1f} MB")
    return {
        "slug": slug,
        "nx": nx,
        "ny": ny,
        "min_x": min_x,
        "min_y": min_y,
        "max_x": max_x,
        "max_y": max_y,
        "epsg": epsg,
        "centroids": centroids,
        "bbox": bb,
        "n_land": n_land,
        "n_water": n_water,
        "n_mixed": n_mixed,
    }


def main():
    os.makedirs(os.path.join(REPO, "server_tiles"), exist_ok=True)
    slugs = list(CITIES)
    if os.environ.get("CITIES"):
        slugs = [s for s in os.environ["CITIES"].split(",") if s]
    info = {}
    for slug in slugs:
        info[slug] = build_city(slug)
    print(json.dumps(info, indent=2, default=str))


if __name__ == "__main__":
    main()
