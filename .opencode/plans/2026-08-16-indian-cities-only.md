# Plan: Complete "Indian Cities Only" Migration & Map Rendering

## 1. Fix the Map Export (`proj.db` blocker)
The `export_map` binary fails because `proj_create` cannot find its database (`proj.db`).
- **Action**: Locate the `proj` data directory inside the build folder (e.g. `target\release\build\proj-sys-*\out\share\proj`).
- **Action**: Set both `PROJ_DATA` and `PROJ_LIB` environment variables to point to this directory before running map generation scripts.

## 2. Generate Pixel Map Assets for Indian Cities
We need to generate the whole-city pixel art maps for the frontend so they "look just like them" (like the old sim francisco).
- **Action**: Run the `export_map` tool for each of the 5 Indian cities:
  ```powershell
  cargo run -p sim-maps --release --bin export_map -- --config config/cities/mumbai.toml --db server_tiles/mumbai.db --out frontend/assets --name mumbai
  cargo run -p sim-maps --release --bin export_map -- --config config/cities/delhi.toml --db server_tiles/delhi.db --out frontend/assets --name delhi
  cargo run -p sim-maps --release --bin export_map -- --config config/cities/kolkata.toml --db server_tiles/kolkata.db --out frontend/assets --name kolkata
  cargo run -p sim-maps --release --bin export_map -- --config config/cities/bangalore.toml --db server_tiles/bangalore.db --out frontend/assets --name bangalore
  cargo run -p sim-maps --release --bin export_map -- --config config/cities/jaipur.toml --db server_tiles/jaipur.db --out frontend/assets --name jaipur
  ```

## 3. Remove non-Indian Cities (Data & Configs)
The user specified "only indian cities no sim francisco cities".
- **Action**: Delete configuration files for `sf`, `neu_york`, `synth_la`, `cybercago`, `simami` in `config/cities/` and `data/cities/`.
- **Action**: Delete corresponding population data (`data/*_pums.csv` and `data/*_dem.tif`, `.pbf`), test rubrics (`rubric_*.yaml`), and DB tiles (`server_tiles/*.db`).
- **Action**: Remove the generated PNGs for western cities in `frontend/assets/` (`sf_tiles.png`, etc.).

## 4. Unwire Western Cities from Backend
- **Action**: In `crates/sim-core/src/bin/server.rs` and `crates/sim-core/src/bin/daemon.rs`, update the `CITIES` array to contain **only** the 5 Indian cities.
  ```rust
  const CITIES: [(&str, &str); 5] = [
      ("mumbai", "Mumbai"),
      ("delhi", "Delhi"),
      ("kolkata", "Kolkata"),
      ("bangalore", "Bangalore"),
      ("jaipur", "Jaipur"),
  ];
  ```

## 5. Update Frontend Defaults
Make the map default to an Indian city and remove references to "sim francisco".
- **Action**: In `frontend/src/app.js`, change `SF_FALLBACK` to `MUMBAI_FALLBACK` and change `const citySlug = () => state.city?.slug || "mumbai";`.
- **Action**: In `frontend/src/config.js`, change `MAP.base` to `"assets/mumbai_tiles.png"` and update `MAP.bbox` to Mumbai's bounding box (`west: 72.77, south: 18.87, east: 72.99, north: 19.28`).
- **Action**: In `frontend/index.html`, update text `sim francisco` to `sim mumbai` (or similar) in the `<title>`, `<span id="title-current">`, and the About menu text.

## 6. Verification
- **Action**: Run `cargo test` in `sim-core` and `sim-maps` to verify no dependencies remain on `sf`. (We may need to update tests checking for SF chunks).
- **Action**: Run the unified server: `cargo run -p sim-core --release --bin server`.
- **Action**: Verify the frontend loads cleanly with a pixel-based rendered Indian city, checking that character sprites walk correctly on the generated roads.