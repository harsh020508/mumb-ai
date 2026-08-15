"""Clip the all-India OSM PBF to each city's bounding box.
Uses pyosmium's SimpleWriter + apply_file with a bbox filter.
Output: data/<city>.osm.pbf
"""
import os
import osmium

SRC = r"C:\Users\Lucky\orca\simfrancisco\data\india.osm.pbf"
OUT = r"C:\Users\Lucky\orca\simfrancisco\data"

# (west, south, east, north) per city — must match config/cities/*.toml
CITIES = {
    'mumbai':   (72.77, 18.87, 72.99, 19.28),
    'delhi':    (76.84, 28.40, 77.35, 28.88),
    'kolkata':  (88.20, 22.40, 88.50, 22.70),
    'bangalore':(77.46, 12.83, 77.78, 13.14),
    'jaipur':   (75.72, 26.78, 75.95, 27.00),
}


class BboxFilter(osmium.SimpleHandler):
    def __init__(self, bbox, out_path):
        super().__init__()
        self.w, self.s, self.e, self.n = bbox
        self.writer = osmium.SimpleWriter(out_path)
        self.count = 0

    def in_bbox(self, lon, lat):
        return self.w <= lon <= self.e and self.s <= lat <= self.n

    def node(self, n):
        if self.in_bbox(n.location.lon, n.location.lat):
            self.writer.add_node(n)
            self.count += 1

    def way(self, w):
        if any(self.in_bbox(n.lon, n.lat) for n in w.nodes if n.location.valid()):
            self.writer.add_way(w)
            self.count += 1

    def relation(self, r):
        self.writer.add_relation(r)
        self.count += 1

    def close(self):
        self.writer.close()


for city, bbox in CITIES.items():
    out = os.path.join(OUT, f'{city}.osm.pbf')
    handler = BboxFilter(bbox, out)
    print(f'Clipping {city} from {SRC} ...', flush=True)
    handler.apply_file(SRC)
    handler.close()
    print(f'  {city}: {handler.count} objects -> {out}', flush=True)

print('done')
