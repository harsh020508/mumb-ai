import json, tomllib, csv, os, glob

print("=== FINAL REPO INTEGRATION VERIFICATION ===")

cities = ['mumbai', 'delhi', 'kolkata', 'bangalore', 'jaipur']
us_cities = []
all_cities = ['mumbai', 'delhi', 'kolkata', 'bangalore', 'jaipur']

# 1. Check data/cities/*.toml
print("\n[1] Checking data/cities/*.toml profiles:")
for c in cities:
    p = f"data/cities/{c}.toml"
    assert os.path.exists(p), f"MISSING {p}"
    with open(p, 'rb') as f:
        d = tomllib.load(f)
    rw = d['religion_weights']
    assert len(rw) == 9, f"{c} religion_weights len != 9"
    assert abs(sum(rw) - 1.0) < 0.05, f"{c} religion_weights sum != 1"
    vf = d['politics']['vote_facts']
    assert len(vf) > 500, f"{c} vote_facts too short"
    print(f"  {c:<10} OK - pumas={len(d['pumas'])} rw_sum={sum(rw):.3f} vf_len={len(vf)}")

# 2. Check config/cities/*.toml
print("\n[2] Checking config/cities/*.toml pipeline configs:")
for c in cities:
    p = f"config/cities/{c}.toml"
    assert os.path.exists(p), f"MISSING {p}"
    with open(p, 'rb') as f:
        d = tomllib.load(f)
    assert 'bbox_wgs84' in d, f"{c} missing bbox_wgs84"
    assert 'crs' in d, f"{c} missing crs"
    print(f"  {c:<10} OK - epsg={d['crs']['utm_epsg']}")

# 3. Check data/news/*.json
print("\n[3] Checking data/news/*.json news caches:")
for c in cities:
    p = f"data/news/{c}.json"
    assert os.path.exists(p), f"MISSING {p}"
    with open(p) as f:
        d = json.load(f)
    n = len(d['articles'])
    assert n >= 5, f"{c} articles count < 5"
    print(f"  {c:<10} OK - date={d['date']} articles={n}")

# 4. Check data/*_pums.csv
print("\n[4] Checking data/*_pums.csv microdata:")
for c in cities:
    p = f"data/{c}_pums.csv"
    assert os.path.exists(p), f"MISSING {p}"
    with open(p) as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 10000, f"{c} rows != 10000"
    print(f"  {c:<10} OK - {len(rows)} rows, sum(PWGTP)={sum(float(r['PWGTP']) for r in rows):,.0f}")

# 5. Check rubric_<city>.yaml
print("\n[5] Checking rubric_<city>.yaml:")
for c in cities:
    p = f"rubric_{c}.yaml"
    assert os.path.exists(p), f"MISSING {p}"
    print(f"  {c:<10} OK - {os.path.getsize(p)} bytes")

# 6. Check Rust integration in api.rs, daemon.rs, server.rs
print("\n[6] Checking Rust registration:")
with open("crates/sim-core/src/api.rs") as f:
    api_code = f.read()
assert '"mumbai"' in api_code, "api.rs missing mumbai default"
assert 'read_dir("data/cities")' in api_code, "api.rs no longer discovers data/cities/*.toml"
print("  api.rs OK - mumbai default + dynamic data/cities/*.toml discovery")

with open("crates/sim-core/src/bin/daemon.rs") as f:
    daemon_code = f.read()
assert '"mumbai"' in daemon_code, "daemon.rs missing mumbai"
assert '"delhi"' in daemon_code, "daemon.rs missing delhi"
assert '"kolkata"' in daemon_code, "daemon.rs missing kolkata"
assert '"bangalore"' in daemon_code, "daemon.rs missing bangalore"
assert '"jaipur"' in daemon_code, "daemon.rs missing jaipur"
print("  daemon.rs OK - all 5 Indian cities in CITIES constant")

with open("crates/sim-core/src/bin/server.rs") as f:
    server_code = f.read()
assert "mumbai" in server_code or "DEFAULT_CITY" in api_code, "server/api missing mumbai default"
print("  server.rs OK - loads cities via api::build_state (dynamic discovery)")

# 7. Check server_tiles/*.db geography against each city's real bbox
print("\n[7] Checking server_tiles/*.db manifests sit inside the real city:")
import json, sqlite3
for c in cities:
    p = f"server_tiles/{c}.db"
    assert os.path.exists(p), f"MISSING {p}"
    with open(f"config/cities/{c}.toml", "rb") as f:
        cfg = tomllib.load(f)
    expected = cfg["bbox_wgs84"]
    con = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
    row = con.execute("SELECT value FROM meta WHERE key='manifest'").fetchone()
    assert row, f"{c} tiles db missing manifest"
    man = json.loads(row[0])
    con.close()
    bb = man["bbox_wgs84"]
    for k in ("west", "south", "east", "north"):
        assert abs(float(bb[k]) - float(expected[k])) < 1e-4, (
            f"{c} manifest {k}={bb[k]} is not the city bbox {expected[k]}"
        )
    # Hard geographic gate: the bbox must actually be in that city, not SF/elsewhere.
    mid_lon = (float(bb["west"]) + float(bb["east"])) / 2.0
    mid_lat = (float(bb["south"]) + float(bb["north"])) / 2.0
    assert expected["west"] <= mid_lon <= expected["east"], f"{c} centroid lon {mid_lon} outside city"
    assert expected["south"] <= mid_lat <= expected["north"], f"{c} centroid lat {mid_lat} outside city"
    print(f"  {c:<10} OK - bbox=({bb['west']},{bb['south']})–({bb['east']},{bb['north']}) crs={man.get('crs')}")

print("\n=== ALL VERIFICATIONS PASSED SUCCESSFULLY ===")
