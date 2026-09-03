# mumb-ai — Multi-City Synthetic Population Simulation & Prediction Engine

**Simulate and predict public opinion, policy support, and movement across Indian megacities and beyond.**

- **Live API Endpoint:** `GET /cities`, `GET /health`, `POST /simulations`
- **Supported Indian Cities:** Mumbai, Delhi, Kolkata, Bangalore, Jaipur (plus international profiles)

`mumb-ai` builds distributionally accurate synthetic populations for Indian urban centers — aligned with Census 2011 marginal targets and PUMS-shaped microdata — that can be polled, perturbed with events, and pathfound over spatial collision tiles to produce population-level predictions: election vote shares, major infrastructure and social policy support, counterfactual opinion shifts, and real-time movement simulations.

---

## Key Features

- **Multi-City Architecture (`crates/sim-core/src/city.rs`):** Modular city profiles (`data/cities/*.toml`) enable dynamic city discovery without engine code changes.
- **Census 2011 Aligned Microdata:** Synthetic PUMS person records (`data/*_pums.csv`) match official Census 2011 demographic targets (age, sex ratio, religion, literacy, SC/ST, PUMA/ward distributions).
- **Ground-Truth Benchmarks (`rubric_*.yaml`):** Sourced election results and policy measures for Indian cities:
  - **Mumbai:** 2024 Lok Sabha MVA vs Mahayuti results, Dharavi Slum Redevelopment, Coastal Road Infrastructure.
  - **Delhi:** 2024 Lok Sabha BJP vote share, Free Electricity & Water policy, EV Subsidies.
  - **Kolkata, Bangalore, Jaipur:** Localized policy and political benchmarks.
- **LOD-0 Tile Collision Maps (`server_tiles/*.db`):** Pre-rendered SQLite spatial collision databases for agent pathfinding and spatial simulation.
- **Interactive Multi-City Frontend:** Static web app (`frontend/`) featuring dynamic city switching, 8-bit map rendering, and agent speech/interaction streaming.

---

## Project Structure

```
.
├── Cargo.toml                  # Workspace root (simfrancisco core + sim-maps pipeline)
├── crates/
│   ├── sim-core/               # Core engine, PUMS ingest, prediction engine, server & validate CLI
│   └── sim-maps/               # GIS map tile builder pipeline (OSM/DEM to SQLite tiles)
├── data/
│   ├── cities/                 # City TOML profiles (mumbai, delhi, kolkata, bangalore, jaipur)
│   ├── *_pums.csv              # Synthetic microdata CSVs for each city
│   ├── news/                   # Per-city news cache feeds
│   └── survey/                 # Activity & time-use survey data
├── server_tiles/               # Spatial tile DBs (*.db) for all supported cities
├── rubric_*.yaml               # Evaluation benchmarks per city
└── frontend/                   # Web dashboard & interactive city simulation UI
```

---

## Data & Methodology Note

**Synthetic PUMS Microdata:**
For Indian megacities, synthetic microdata records (`data/mumbai_pums.csv`, `data/delhi_pums.csv`, etc.) match official Census 2011 marginal targets (age groups, sex ratio, religion distributions, literacy, SC/ST proportion, ward/PUMA definitions). The joint distribution across individual variables is synthetically generated via marginal probability sampling, rather than drawn from a single joint microdata survey record (unlike US ACS PUMS).

---

## Quickstart & Reproduction

### Prerequisites
- Rust toolchain (1.80+)
- Python 3 (for synthetic data scripts, optional)

### 1. Run Unit Tests
```bash
cargo test --lib -p simfrancisco
```

### 2. Run Endpoint Contract Tests
```bash
cargo test --test contract --release -p simfrancisco
```

### 3. Run Benchmark Scorecard Validation
Evaluate city predictions against ground-truth benchmarks (e.g. Mumbai):
```bash
# Validate Mumbai benchmarks
cargo run -p simfrancisco --bin validate -- --city mumbai

# Validate Delhi benchmarks
cargo run -p simfrancisco --bin validate -- --city delhi
```

### 4. Launch Local Digital-Twin Server
```bash
cargo run -p simfrancisco --bin server
```
The server will start at `http://127.0.0.1:8080`.
Verify health:
```bash
curl http://127.0.0.1:8080/health
curl http://127.0.0.1:8080/cities
```
