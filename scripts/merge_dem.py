"""Merge Copernicus 1-degree DEM tiles and crop to each city bbox.
Output: Float32 EPSG:4326 GeoTIFF (uncompressed) at data/<city>_dem.tif,
readable by the sim-maps `tiff` crate (ModelPixelScaleTag + ModelTiepointTag).
"""
import os
import numpy as np
import tifffile

DEM_SRC = r"C:\Users\Lucky\AppData\Local\Temp\opencode\dem"
OUT = r"C:\Users\Lucky\orca\simfrancisco\data"

# (west, south, east, north) per city from config/cities/*.toml
CITIES = {
    'mumbai':   {'bbox': (72.77, 18.87, 72.99, 19.28), 'tiles': ['N18_00_E072_00', 'N19_00_E072_00']},
    'delhi':    {'bbox': (76.84, 28.40, 77.35, 28.88), 'tiles': ['N28_00_E076_00', 'N28_00_E077_00']},
    'kolkata':  {'bbox': (88.20, 22.40, 88.50, 22.70), 'tiles': ['N22_00_E088_00']},
    'bangalore':{'bbox': (77.46, 12.83, 77.78, 13.14), 'tiles': ['N12_00_E077_00', 'N13_00_E077_00']},
    'jaipur':   {'bbox': (75.72, 26.78, 75.95, 27.00), 'tiles': ['N26_00_E075_00']},
}

# Copernicus 30m: 3600x3600 px per 1-degree tile, Float32, north-up.
PX = 1.0 / 3600.0


def tile_origin(name):
    """Return (west_lon, north_lat) for a tile like N28_00_E076_00."""
    parts = name.split('_')
    lat = int(parts[0][1:])
    lon = int(parts[2][1:])
    return lon, lat + 1  # north edge


for city, cfg in CITIES.items():
    west, south, east, north = cfg['bbox']
    # collect each needed tile
    arrays, geos = {}, {}
    for name in cfg['tiles']:
        p = os.path.join(DEM_SRC, f'{name}_DEM.tif')
        arr = tifffile.imread(p)
        wlon, nlat = tile_origin(name)
        arrays[name] = arr
        geos[name] = (wlon, nlat)
    # build a canvas covering the union
    lon0 = min(g[0] for g in geos.values())
    lon1 = max(g[0] + 1 for g in geos.values())
    lat1 = max(g[1] for g in geos.values())
    lat0 = min(g[1] - 1 for g in geos.values())
    cols = int(round((lon1 - lon0) / PX))
    rows = int(round((lat1 - lat0) / PX))
    canvas = np.full((rows, cols), np.nan, dtype=np.float32)
    for name, (wlon, nlat) in geos.items():
        arr = arrays[name]
        r0 = int(round((lat1 - nlat) / PX))
        c0 = int(round((wlon - lon0) / PX))
        canvas[r0:r0 + 3600, c0:c0 + 3600] = arr
    # crop to bbox (north-up: row index grows southward)
    c0 = int(round((west - lon0) / PX))
    c1 = int(round((east - lon0) / PX))
    r1 = int(round((lat1 - north) / PX))  # row of north edge
    r0 = int(round((lat1 - south) / PX))  # row of south edge
    crop = canvas[r1:r0, c0:c1]
    if crop.shape[0] < 1 or crop.shape[1] < 1:
        raise SystemExit(f'{city}: empty crop {crop.shape}')
    crop = np.nan_to_num(crop, nan=-10000.0, posinf=-10000.0, neginf=-10000.0)
    # write with tiepoint at the crop's top-left
    top_left_lon = lon0 + c0 * PX
    top_left_lat = lat1 - r1 * PX
    out = os.path.join(OUT, f'{city}_dem.tif')
    tifffile.imwrite(
        out, crop.astype(np.float32),
        photometric='minisblack',
        resolution=(1.0 / PX, 1.0 / PX),
        metadata=None,
        extratags=[
            (33922, 'd', 6, (0.0, 0.0, 0.0, top_left_lon, top_left_lat, 0.0)),
            (33550, 'd', 3, (PX, PX, 0.0)),
        ],
        compression=None,
    )
    print(f'{city}: crop {crop.shape} -> {out}')
print('done')
