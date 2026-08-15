import json, tomllib, csv, os, glob

print("=== FINAL REPO INTEGRATION VERIFICATION ===")

cities = ['mumbai', 'delhi', 'kolkata', 'bangalore', 'jaipur']
us_cities = ['sf', 'neu_york', 'synth_la', 'cybercago', 'simami']
all_cities = ['sf', 'neu_york', 'synth_la', 'cybercago', 'simami', 'mumbai', 'delhi', 'kolkata', 'bangalore', 'jaipur']

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
for c in cities:
    assert f'"{c}"' in api_code, f"api.rs missing {c}"
print("  api.rs OK - all 5 Indian cities in load_city_runtime loop")

with open("crates/sim-core/src/bin/daemon.rs") as f:
    daemon_code = f.read()
for c in cities:
    assert f'"{c}"' in daemon_code, f"daemon.rs missing {c}"
print("  daemon.rs OK - all 5 Indian cities in CITIES constant")

with open("crates/sim-core/src/bin/server.rs") as f:
    server_code = f.read()
for c in cities:
    assert f'"{c}"' in server_code, f"server.rs missing {c}"
print("  server.rs OK - all 5 Indian cities in CITIES constant")

print("\n=== ALL VERIFICATIONS PASSED SUCCESSFULLY ===")
