# Execution Plan: Fix Blue Visuals, Downscale Oversized Maps, & Eliminate Client/Server Crashes

## 1. Root Cause Analysis

### Issue A: Blue & Uneven Map Background
- **Cause**: In `config/cities/*.toml`, `water_max_elev_m = 3.0` causes low-elevation inland terrain in landlocked/inland cities (Delhi, Jaipur, Bangalore, Kolkata) to be classified as ocean water during the tile pipeline rasterization.
- **Frontend Cause**: `COLORS.water` in `frontend/src/config.js` is set to `#215C81` (San Francisco deep ocean blue), causing any unrendered margins or letterboxing to display as bright ocean blue.

### Issue B: Delhi Not Opening / Canvas Memory Crash
- **Cause**: `delhi_tiles.png` was generated at 6528×6944 pixels (45.3 Megapixels, 15.7 MB PNG file size). Decoding a 45 MP uncompressed image buffer into a HTML5 Canvas requires >180 MB GPU/Canvas memory. Many browsers and mobile devices abort canvas allocation for images > 3000px, resulting in blank screens or silent crashes.
- **Frontend Cause**: `frontend/src/map.js` lacks resolution clamping and fails silently when `_buildLandMask()` runs `getImageData` on huge images.

---

## 2. Comprehensive Fix Strategy

### Phase 1: Re-render & Optimize Whole-City Tile PNGs
1. **Update Pipeline Configs (`config/cities/*.toml`)**:
   - Set `water_max_elev_m = 0.0` for landlocked/inland cities (Delhi, Jaipur, Bangalore) so non-water terrain is rendered as land/ground instead of ocean blue.
2. **Re-export Tile Maps at Standard Web Dimensions (Max 3000px)**:
   - Re-run `export_map` or downscale `frontend/assets/*_tiles.png` so no tile image exceeds 3000px on its longest side.
   - Targets:
     - `delhi_tiles.png`: Downscale to ~2448×2604 px (< 5 MB).
     - `bangalore_tiles.png`: Downscale to ~2256×2224 px (< 4 MB).
     - `mumbai_tiles.png`: Keep at ~2280×4392 px (or downscale to max 3000px height).
     - `kolkata_tiles.png`: Keep at ~2000×2144 px.
     - `jaipur_tiles.png`: Keep at ~2244×2376 px.

### Phase 2: Frontend Palette & Letterbox Alignment
1. **Update Canvas Letterbox Color (`frontend/src/config.js`)**:
   - Update `COLORS.water` from `#215C81` to a neutral warm land/dark tone `#1a1c23` or `#141414` that matches the map terrain palette, eliminating ocean blue borders for Indian cities.
2. **Land Mask Tolerance & Fallback (`frontend/src/map.js`)**:
   - In `_buildLandMask()`, add tolerance for non-coastal cities and add a `try...catch` fallback so if land mask generation encounters memory limits, it defaults to full-canvas land bounds without crashing.

### Phase 3: Resilience & City Switching Error Boundary (`frontend/src/app.js`)
1. **City Load Error Handling**:
   - Wrap city asset image loading in a promise timeout (10s max).
   - If image loading fails or aborts, display a toast (`"Could not load city map, reverting to Mumbai"`) and safely fall back to Mumbai without hanging the UI.

### Phase 4: Verification & Deployment Checks
1. **Build & Test**:
   - Re-run `cargo test --workspace`.
   - Verify all 5 Indian city maps load instantly in the browser without memory spikes or crashes.
2. **Deployment Push**:
   - Commit optimized tile images and updated configs to `mumb-ai main`.

---

## 3. Step-by-Step Task Breakdown for Execution

- [ ] Task 1: Update `water_max_elev_m` in `config/cities/{delhi,jaipur,bangalore}.toml` to eliminate inland blue ocean fill.
- [ ] Task 2: Resize/Downscale `frontend/assets/delhi_tiles.png` and `bangalore_tiles.png` to < 3000px max dimension using Python/Pillow or `export_map`.
- [ ] Task 3: Update `COLORS.water` in `frontend/src/config.js` to neutral dark `#141414` / `#1a1c23`.
- [ ] Task 4: Add canvas memory safety and image load timeout handling in `frontend/src/map.js` and `frontend/src/app.js`.
- [ ] Task 5: Verify all 5 cities in browser and push commit to `mumb-ai main`.
