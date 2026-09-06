# mumb-ai — Multi-City Frontend Integration Guide

Everything the map/sprite track needs to connect, with zero backend questions.

- **Base URL (production):** `https://mumbai-digital-twin.fly.dev`
- **Auth:** none for clients. The model API key lives only as a server-side fly secret; you
  never send it. CORS is wide-open (`Access-Control-Allow-Origin: *`), so browser fetch/EventSource work directly.
- **Content type:** all POST bodies are JSON; all responses are JSON except the SSE stream.
- **Health:** `GET /health` → `200` with model/data status.

The backend is two engines over one persona layer:
1. **Prediction engine** — `persona + as-of-date + event → weighted opinion / vote / market probability`. This is the scored core; it runs without the life-sim.
2. **Life simulation** — schedule-driven movement on spatial map grids (Mumbai default, multi-city configurable), collocated chatter, reactions, birth/death. Drives sprites + speech bubbles via the SSE stream.

---

## 1. Connect in 5 minutes

```js
// Discover available cities
const cities = await (await fetch(`${BASE}/cities`)).json();
// Returns: { cities: [{ slug: "mumbai", name: "Mumbai", ... }, ...], default: "mumbai" }
```

```js
const BASE = "https://mumbai-digital-twin.fly.dev";

// 1) create a simulation (synthetic population (Mumbai default or configured city) sampled from real Census PUMS)
const sim = await (await fetch(`${BASE}/simulations`, {
  method: "POST", headers: {"content-type": "application/json"},
  body: JSON.stringify({ n: 1200, seed: 42, start_datetime: "2024-11-01T08:00:00Z", tick_seconds: 30 })
})).json();
const simId = sim.simulation_id;                 // e.g. "sim-42-1200-ab12cd34"

// 2) make a branch (optionally apply an event, run some ticks)
const branch = await (await fetch(`${BASE}/simulations/${simId}/branches`, {
  method: "POST", headers: {"content-type": "application/json"},
  body: JSON.stringify({ ticks: 5, event: { text: "A new transit measure is proposed.", progressive_coded: true } })
})).json();
const branchId = branch.branch_id;               // e.g. "sim-42-1200-ab12cd34:b1"

// 3) fetch agent positions for initial sprite placement
const page = await (await fetch(`${BASE}/branches/${branchId}/agents?limit=1000`)).json();
for (const a of page.agents) placeSprite(a.id, a.cell, a.lonlat, a.action);

// 4) live stream (movement, speech bubbles, reactions, births/deaths)
const es = new EventSource(`${BASE}/branches/${branchId}/stream`);
es.addEventListener("agent_moved", e => moveSprite(JSON.parse(e.data)));
es.addEventListener("agent_said",  e => showBubble(JSON.parse(e.data)));
es.addEventListener("agent_reacted", e => showReaction(JSON.parse(e.data)));   // 👍/👎
es.addEventListener("tick", e => setClock(JSON.parse(e.data).iso));

// 5) poll the electorate (weighted, with per-demographic breakdowns + CI)
const poll = await (await fetch(`${BASE}/branches/${branchId}/poll`, {
  method: "POST", headers: {"content-type": "application/json"},
  body: JSON.stringify({ question: "Do you support more public transit funding?", framing: "vote", as_of_date: "2024-11-01" })
})).json();
console.log(poll.p_yes, poll.ci_low, poll.ci_high, poll.breakdowns.age);
```

---

## 2. Coordinate contract (cell ↔ chunk ↔ UTM ↔ lat/long)

The map comes from `server_tiles/<city>.db` (the map track's artifact). Grid facts are per-city and live in that DB's `meta.manifest`. Mumbai (default):

| quantity | value |
|---|---|
| chunks | **95 × 183** (cx 0..94 east, cy 0..182 south) |
| cells per chunk | **125 × 125** |
| meters per cell | **2.0** (LOD 0) |
| global cell grid | **11875 × 22875** cells |
| CRS | **UTM Zone 43N (EPSG:32643)** |
| UTM bbox | min (265063.85, 2087644.95) → max (288769.97, 2133315.72) |
| WGS84 bbox | W 72.77, E 72.99, S 18.87, N 19.28 |

**Cell (0,0) is the NW corner**, anchored at UTM `(min_x, max_y)`. `+x` is east, `+y` is south. Always read `min_x` / `max_y` / `meters_per_cell` / `cells_per_chunk` from the city's manifest rather than hard-coding SF numbers.

```
# global cell (gx, gy)  ->  UTM (meters), cell CENTER
utm_x = min_x + (gx + 0.5) * meters_per_cell
utm_y = max_y - (gy + 0.5) * meters_per_cell
# UTM -> lon/lat: inverse transverse-Mercator for the city's UTM zone (Mumbai = 43N),
# or just use the `lonlat` field the /agents endpoint already returns.

# global cell -> chunk + in-chunk index into the tiles.db collision grid
cx = gx / cells_per_chunk,  cy = gy / cells_per_chunk
lx = gx % cells_per_chunk,  ly = gy % cells_per_chunk
collision_index = ly * cells_per_chunk + lx
```

Cost values in `chunks.collision`: `0` free (road/sidewalk/plaza), `1`–`4` increasing terrain
penalty, `8` stairs, `255` blocked (water/buildings/cliffs). Sprites only ever sit on cells with
cost `< 255`; pathfinding (A*) guarantees this.

Every agent in `/agents` includes both `cell: [gx, gy]` and `lonlat: [lon, lat]`, so you can
render in grid space or on a geographic map without doing the projection yourself.

---

## 3. Endpoints

### `GET /health`
```json
{ "status": "ok", "model_reachable": true, "has_key": true,
  "map_chunks": 17385, "pums_records": 10000, "usage": { "calls": 0, "cache_hits": 0 } }
```
`model_reachable` is `null` for the first second or two after boot (checked in the background), then `true`/`false`.

### `POST /simulations`
Create a seeded synthetic population sampled from PUMS microdata (Census 2011 targets for Indian cities, ACS PUMS for US cities).
```json
// request (all fields optional; defaults shown)
{ "n": 800, "seed": 42, "start_datetime": "2024-11-01T08:00:00Z",
  "tick_seconds": 30, "commit_every": 20, "distributional_params": null }
// response 201
{ "simulation_id": "sim-42-800-ab12cd34", "n": 800,
  "main_branch": "sim-42-800-ab12cd34:main", "start_datetime": "2024-11-01T08:00:00Z" }
```
`n` is clamped to 1..50000. `distributional_params` is accepted and reserved for per-demographic seeding.

### `GET /simulations/{id}/demographics`
Empirical (PUMS-weighted) marginals of the sampled population **vs target ACS marginals**, with
per-variable distance + pass/fail. (At `n ≥ ~1200` everything is within tolerance; small `n` may not be.)
```json
{ "simulation_id": "...", "n_agents": 1200, "total_weight": 485000.0,
  "variables": {
    "age_band": { "empirical": {"25-34": 0.21, ...}, "target_acs": {"25-34": 0.20, ...},
                  "tv_distance": 0.018, "pass": true, "tolerance": 0.05 },
    "race_eth": { ... }, "educ": { ... }, "sex": { ... }, "citizen": { ... } },
  "all_within_tolerance": true }
```

### `POST /simulations/{id}/branches`
Clone main's current state into a new branch, optionally broadcast an event, run `ticks` ticks.
```json
// request
{ "ticks": 20, "mode": "social",
  "event": { "text": "A major public-safety incident dominates the news.", "progressive_coded": false },
  "model": "gpt-4o", "name": "what-if-crime" }
// response 201
{ "branch_id": "sim-...:b1", "name": "what-if-crime", "ticks_run": 20,
  "reactions_emitted": 1198, "event": "A major public-safety incident...",
  "clock": "2024-11-01T08:10:00Z", "tick": 20 }
```
`progressive_coded` controls whether the 👍/👎 reactions skew toward progressive or moderate agents.

### `GET /branches/{id}`
```json
{ "branch_id": "...", "sim_id": "...", "name": "main", "kind": "main", "mode": "clean",
  "status": "ready", "tick": 20, "clock": "2024-11-01T08:10:00Z", "agents_alive": 1200 }
```

### `GET /branches/{id}/agents?filter=...&limit=500&offset=0`
Paginated agent snapshot for sprites. `filter` is `key=value` (comma-separated); keys:
`race`/`race_eth`, `educ`, `age_band`, `puma`, `tenure` (`own`|`rent`), `sex` (`1`|`2`), `religion`.
```json
{ "branch_id": "...", "total_matched": 742, "offset": 0, "count": 500,
  "agents": [
    { "id": 0, "name": "Mei Chen", "action": "commuting", "alive": true,
      "cell": [4210, 1875], "lonlat": [-122.476, 37.781], "neighborhood": "the Sunset",
      "age": 34, "race_eth": "asian", "educ": "graduate",
      "values": { "economic": -0.31, "social": -0.52, "trust": 0.04, "change": 0.12,
                  "s_housing": 0.78, "s_crime": 0.41, "s_homeless": 0.6, "s_cost": 0.82,
                  "s_environment": 0.66, "s_immigration": 0.35 } } ] }
```

### `POST /branches/{id}/poll`
Poll the synthetic electorate. One batched LLM pass per question; agents are archetype-clustered
and post-stratified with PUMS weights.
```json
// request
{ "question": "California Proposition 36 (2024): do you vote YES?",
  "description": "Increases penalties for certain theft/drug crimes. YES = tougher penalties.",
  "framing": "vote",                  // "vote" (their own ballot) | "belief" (forecast an event)
  "as_of_date": "2024-11-04",
  "model": "gpt-4o",                  // gpt-4o | gpt-5.5 | grok-4.3
  "population": "cvap_likely_voter",  // omit for "all"; cvap_likely_voter applies a turnout model
  "event": "optional broadcast event text the agents are aware of" }
// response 200
{ "question": "...", "as_of_date": "2024-11-04", "model": "gpt-4o",
  "p_yes": 0.642, "ci_low": 0.61, "ci_high": 0.67,
  "n_agents": 980, "n_eff": 612.4, "design_effect": 1.6,
  "n_archetypes": 142, "n_llm_calls": 12,
  "breakdowns": { "age": [ {"key":"65+","yes_share":0.71,"weight":120000,"n":210}, ... ],
                  "race": [...], "educ": [...], "income_q": [...], "puma": [...], "tenure": [...] },
  "sample_rationales": ["frustrated with retail theft", "..."] }
```
`p_yes` is the weighted share (binary yes) / Democratic two-party share (for the president question).
Missing `question` → `400`.

### `POST /branches/{id}/predict-market`
Map a market question to a pollable belief; `sim_probability_yes` is the panel's probability.
```json
// request
{ "question": "Will a Democrat win the 2024 California U.S. Senate seat?",
  "as_of_date": "2024-06-01", "bucket": "sf_opinion_informative", "model": "gpt-4o",
  "live_market_price": 0.94 }     // optional, echoed back for demo agreement
// response 200
{ "question": "...", "as_of_date": "2024-06-01", "bucket": "sf_opinion_informative",
  "sim_probability_yes": 0.97, "ci": [0.95, 0.99], "n_agents": 1200, "model": "gpt-4o",
  "live_market_price": 0.94,
  "note": "headline market number weights the sf_opinion_informative bucket; ..." }
```

### `POST /simulations/{id}/reset-to-main`
Drop all non-main branches and return to main HEAD.
```json
{ "reset_to": "sim-...:main", "dropped_branches": ["sim-...:b1"], "main_tick": 0 }
```

### `DELETE /branches/{id}`
Delete a (non-main) branch → `{ "deleted": "sim-...:b1" }`. Deleting main → `400`.

---

## 4. SSE stream — `GET /branches/{id}/stream`

`Content-Type: text/event-stream`. Each message has an `event:` name and JSON `data:`. The first
message is a `snapshot`; then live ticks every ~400 ms (bounded run). Event schemas:

```
event: snapshot       data: { "type":"snapshot", "tick":20, "clock":"2024-11-01T08:10:00Z", "agents_alive":1200 }
event: agent_moved    data: { "type":"agent_moved", "id":42, "from_cell":[4210,1875], "to_cell":[4214,1879] }
event: agent_said     data: { "type":"agent_said", "id":42, "text":"We need more housing, not less.", "target_id":77 }
event: agent_reacted  data: { "type":"agent_reacted", "id":42, "kind":"up", "event_id":"sim-...:b1" }   // kind: up|down
event: tick           data: { "type":"tick", "clock":1730450400, "tick":21, "iso":"2024-11-01T08:10:30Z" }
event: birth          data: { "type":"birth", "id":1201, "cell":[4100,1800] }
event: death          data: { "type":"death", "id":17 }
```

`from_cell`/`to_cell`/`cell` are `[gx, gy]` global cells (see §2). Speech bubbles come from `agent_said`
(`text`, optional `target_id`); reactions from `agent_reacted` (`kind` = `up`/`down`). Use `tick.iso`
for the in-world clock.

> Note: `agent_moved` reports the start/end cell of a multi-cell step. If you want the smooth
> intermediate path, run A* client-side over the cost grid, or interpolate linearly between cells
> (the backend guarantees both endpoints are walkable and close).

---

## 5. Models, modes, determinism

- **Models:** `gpt-4o` (default; earliest knowledge cutoff → used for counterfactuals + elections to avoid leakage), `gpt-5.5` (higher-stakes), `grok-4.3` (load-balance).
- **Modes:** `clean` (persona + broadcast event only — reproducible, used by `validate`) vs `social`
  (reflects post-conversation drift from the life-sim — richer, for exploration).
- **Determinism:** poll results are cached server-side by `(model, exact prompt)`, so repeating a poll
  is free and identical.

---

## 6. Validation status (for context)

`cargo run --bin validate -- --city mumbai` scores the prediction engine against real public ground
truth (ECI 2024 results, city policy measures, counterfactual directions). See `rubric_<city>.yaml`
+ `NOTES.md` for targets, sources, and methodology.
