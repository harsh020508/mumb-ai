// ─────────────────────────────────────────────────────────────────────────
// SimFrancisco · pixel-map frontend · configuration
// ─────────────────────────────────────────────────────────────────────────

// Backend (see ../INTEGRATION.md). CORS is wide-open, so browser fetch works.
export const BASE = "https://sf-digital-twin-tp.fly.dev";

// Synthetic population to spin up on load. 5,000 agents → a denser, more diverse
// crowd; poll latency stays bounded because agents are clustered into ≤160 archetypes
// before the LLM is called, so the call count (not N) sets the wait.
export const SIM = {
  n: 10000,
  seed: 42,
  start_datetime: "2026-06-13T08:00:00Z",
  tick_seconds: 30,
};

// Per-prediction branch + poll defaults. Model is Claude Sonnet 4.6 (current-events
// capable); as_of_date is "today" so it reasons about live markets.
export const PREDICT = {
  branch_ticks: 2,
  as_of_date: "2026-06-13",
  model: "claude-sonnet-4-6",
};

// Animation timing (ms).
export const TIMING = {
  revealMs: 3000,         // green/red verdicts accumulate over the crowd
  driftMs: 9000,
  fadeBackMs: 420,
};

// Pixel-art map base (whole-city render from the golden-future-map track) + the
// 16×16 RPG character sprite sheet (01-generic: 10 characters).
export const MAP = {
  base: "assets/mumbai_tiles.png",        // whole-city LOD-4 tile render
  sprites: "assets/sprites.png",      // 240×128, 10 chars in 5×2 blocks of 48×64
  // WGS-84 bbox the base image spans (from tiles.db manifest).
  bbox: { west: 72.77, east: 72.99, south: 18.87, north: 19.28 },
  detailZoomMul: 6.5,                 // click-to-zoom factor over the fit-to-screen zoom
};

// Neutral palette (purple removed). Map colors now come from the pixel image;
// these drive UI chrome + the yes/no verdict markers.
export const COLORS = {
  water:   "#141414",   // neutral dark letterbox tone (matches app background)
  ink:     "#141414",   // primary text / title — near-black
  inkSoft: "#6E7280",   // secondary text / neutral sprites
  accent:  "#141414",   // was violet — now neutral black
  yes:     "#2E9B4E",   // strong yes — green
  no:      "#C0352F",   // strong no — brick red
};
