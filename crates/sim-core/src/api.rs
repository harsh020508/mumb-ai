//! Axum HTTP API. Every documented endpoint (BRIEF §9/§10) with contract-testable
//! request/response shapes. The prediction engine is reachable without the life-sim;
//! the life-sim drives positions + the SSE stream for the frontend.

use crate::agent::Agent;
use crate::city::CityProfile;
use crate::geo::TilesDb;
use crate::model::{Cache, Model, ModelClient};
use crate::persona::{build_population_with, Population};

fn lock_mutex<T>(m: &Mutex<T>) -> std::sync::MutexGuard<'_, T> {
    m.lock().unwrap_or_else(|p| p.into_inner())
}

use crate::predict::{Engine, Event, Framing, Poll};
use crate::pums::PumsRecord;
use crate::sim::{SimEngine, SimEvent};
use crate::state::{AgentState, SimState};
use crate::store::{SimMeta, Store};
use axum::{
    extract::{Path, Query, State},
    http::StatusCode,
    response::sse::{Event as SseEvent, Sse},
    response::IntoResponse,
    routing::{delete, get, post},
    Json, Router,
};
use serde::Deserialize;
use serde_json::{json, Value};
use std::collections::HashMap;
use std::convert::Infallible;
use std::sync::{Arc, Mutex};
use std::time::Duration;

/// Everything needed to run one city: its profile, map tiles, and PUMS records.
pub struct RateLimiter {
    requests: Mutex<HashMap<String, Vec<std::time::Instant>>>,
    max_per_minute: usize,
}

impl RateLimiter {
    pub fn new(max_per_minute: usize) -> Self {
        Self {
            requests: Mutex::new(HashMap::new()),
            max_per_minute,
        }
    }

    pub fn check(&self, client_id: &str) -> bool {
        let now = std::time::Instant::now();
        let mut map = self.requests.lock().unwrap_or_else(|p| p.into_inner());
        let window = std::time::Duration::from_secs(60);
        let timestamps = map.entry(client_id.to_string()).or_insert_with(Vec::new);
        timestamps.retain(|t| now.duration_since(*t) < window);
        if timestamps.len() >= self.max_per_minute {
            false
        } else {
            timestamps.push(now);
            true
        }
    }
}

pub struct CityRuntime {
    pub profile: Arc<CityProfile>,
    pub tiles: Arc<TilesDb>,
    pub records: Arc<Vec<PumsRecord>>,
}

#[derive(Clone)]
pub struct AppState {
    pub client: ModelClient,
    pub engine: Engine,
    /// Default city's tiles/records (used by city-agnostic endpoints like /health).
    pub tiles: Arc<TilesDb>,
    pub records: Arc<Vec<PumsRecord>>,
    /// All loaded cities, keyed by slug.
    pub cities: Arc<HashMap<String, Arc<CityRuntime>>>,
    pub default_city: String,
    pub store: Arc<Store>,
    pub sims: Arc<Mutex<HashMap<String, Arc<SimContext>>>>,
    pub model_ok: Arc<Mutex<Option<bool>>>,
    pub auth_token: Option<String>,
    pub rate_limiter: Arc<RateLimiter>,
}

pub struct SimContext {
    pub id: String,
    pub meta: SimMeta,
    /// The city this simulation belongs to.
    pub city: Arc<CityRuntime>,
    pub population: Arc<Population>,
    pub branches: Mutex<HashMap<String, Arc<BranchState>>>,
    pub counter: Mutex<u64>,
}

pub struct BranchState {
    pub id: String,
    pub sim_id: String,
    pub name: String,
    pub kind: String,
    pub engine: Mutex<SimEngine>,
    pub mode: String,
    pub model: Option<String>,
    pub tx: tokio::sync::broadcast::Sender<SimEvent>,
    // Background tick task for this branch. Stored in a Tokio Mutex for safe async mutation.
    pub ticker: Arc<tokio::sync::Mutex<Option<tokio::task::JoinHandle<()>>>>,
}

async fn auth_and_rate_limit(
    State(st): State<AppState>,
    req: axum::extract::Request,
    next: axum::middleware::Next,
) -> Result<axum::response::Response, (StatusCode, Json<Value>)> {
    let path = req.uri().path().to_string();
    let is_public = path == "/health"
        || path == "/ready"
        || path == "/"
        || path.starts_with("/assets/")
        || path == "/favicon.ico"
        || path == "/index.html";

    if !is_public {
        if let Some(ref expected_token) = st.auth_token {
            let auth_header = req
                .headers()
                .get("Authorization")
                .and_then(|h| h.to_str().ok());
            let api_key_header = req.headers().get("X-API-Key").and_then(|h| h.to_str().ok());
            let mut authorized = false;
            if let Some(auth) = auth_header {
                if auth.strip_prefix("Bearer ").map(|t| t.trim()) == Some(expected_token)
                    || auth == expected_token
                {
                    authorized = true;
                }
            }
            if let Some(key) = api_key_header {
                if key == expected_token {
                    authorized = true;
                }
            }
            if !authorized {
                return Err((
                    StatusCode::UNAUTHORIZED,
                    Json(
                        json!({"error": "unauthorized: valid Bearer token or X-API-Key required"}),
                    ),
                ));
            }
        }
    }

    if path.starts_with("/api/")
        || path == "/simulations"
        || path.starts_with("/simulations/")
        || path.starts_with("/branches/")
        || path == "/parse"
    {
        let client_ip = req
            .headers()
            .get("X-Forwarded-For")
            .and_then(|h| h.to_str().ok())
            .map(|s| s.split(',').next().unwrap_or(s).trim())
            .or_else(|| req.headers().get("X-Real-IP").and_then(|h| h.to_str().ok()))
            .unwrap_or("127.0.0.1");

        if !st.rate_limiter.check(client_ip) {
            return Err((
                StatusCode::TOO_MANY_REQUESTS,
                Json(json!({"error": "rate limit exceeded", "retry_after": 60})),
            ));
        }
    }

    Ok(next.run(req).await)
}

/// Spawn a background ticker for a branch that repeatedly ticks the engine
/// and broadcasts events on the branch's broadcast channel.
/// The task handle is stored inside the branch's `ticker` field for later
/// cancellation (e.g. on branch deletion).
async fn spawn_branch_ticker(bs: Arc<BranchState>) {
    // Clone the broadcast sender for the task.
    let tx = bs.tx.clone();
    // The ticker task runs indefinitely, ticking the engine at a fixed interval.
    let bs_clone = bs.clone();
    let handle = tokio::spawn(async move {
        loop {
            // Generate tick events. The engine is protected by a sync Mutex.
            let events: Vec<SimEvent> = { bs_clone.engine.lock().unwrap().tick() };
            // Broadcast each event.
            for ev in events {
                // Ignore failures if there are no listeners.
                let _ = tx.send(ev);
            }
            // Sleep between ticks. The duration mirrors the previous SSE implementation.
            tokio::time::sleep(Duration::from_millis(400)).await;
        }
    });
    // Store the handle for later cancellation.
    let mut guard = bs.ticker.lock().await;
    *guard = Some(handle);
}

async fn add_security_headers(
    req: axum::extract::Request,
    next: axum::middleware::Next,
) -> axum::response::Response {
    let mut resp = next.run(req).await;
    let headers = resp.headers_mut();
    headers.insert(
        "x-content-type-options",
        axum::http::HeaderValue::from_static("nosniff"),
    );
    headers.insert(
        "x-frame-options",
        axum::http::HeaderValue::from_static("DENY"),
    );
    headers.insert(
        "x-xss-protection",
        axum::http::HeaderValue::from_static("1; mode=block"),
    );
    headers.insert(
        "referrer-policy",
        axum::http::HeaderValue::from_static("strict-origin-when-cross-origin"),
    );
    resp
}

pub fn router(state: AppState) -> Router {
    use axum::extract::DefaultBodyLimit;
    use tower_http::cors::{Any, CorsLayer};
    let cors = CorsLayer::new()
        .allow_origin(Any)
        .allow_methods(Any)
        .allow_headers(Any);
    use tower_http::services::{ServeDir, ServeFile};
    let serve_dir = ServeDir::new("frontend");

    Router::new()
        .route("/health", get(health))
        .route("/ready", get(ready))
        .route(
            "/",
            axum::routing::get_service(ServeFile::new("frontend/index.html")),
        )
        .route("/api", get(root))
        .route("/version", get(root))
        .route("/cities", get(list_cities))
        .route("/cities/:city", get(get_city_details))
        .route("/cities/:city/parse", post(parse_question_handler))
        .route("/cities/:city/news", get(city_news))
        .route("/simulations", post(create_sim))
        .route("/simulations/:id", delete(delete_sim))
        .route("/simulations/:id/demographics", get(demographics))
        .route("/simulations/:id/branches", post(create_branch))
        .route("/simulations/:id/reset-to-main", post(reset_to_main))
        .route("/branches/:bid", get(branch_status))
        .route("/branches/:bid", delete(delete_branch))
        .route("/branches/:bid/agents", get(branch_agents))
        .route("/branches/:bid/chatter", post(branch_chatter))
        .route("/branches/:bid/poll", post(branch_poll))
        .route("/branches/:bid/predict-market", post(predict_market))
        .route("/branches/:bid/stream", get(branch_stream))
        .fallback_service(serve_dir)
        .layer(DefaultBodyLimit::max(2 * 1024 * 1024))
        .layer(axum::middleware::from_fn_with_state(
            state.clone(),
            auth_and_rate_limit,
        ))
        .layer(axum::middleware::from_fn(add_security_headers))
        .layer(cors)
        .with_state(state)
}

async fn root() -> impl IntoResponse {
    Json(json!({
        "service": "mumb-ai",
        "docs": "see INTEGRATION.md",
        "endpoints": [
            "GET /health", "POST /simulations", "GET /simulations/{id}/demographics",
            "POST /simulations/{id}/branches", "GET /branches/{id}",
            "GET /branches/{id}/agents", "POST /branches/{id}/poll",
            "POST /branches/{id}/predict-market", "POST /simulations/{id}/reset-to-main",
            "DELETE /branches/{id}", "GET /branches/{id}/stream"
        ]
    }))
}

async fn ready(State(st): State<AppState>) -> impl IntoResponse {
    const REQUIRED_CITIES: &[&str] = &["mumbai", "delhi", "bangalore", "kolkata", "jaipur"];
    let mut missing = Vec::new();
    for city in REQUIRED_CITIES {
        match st.cities.get(*city) {
            Some(rt) => {
                if rt.records.is_empty() || rt.tiles.manifest.chunks_x == 0 {
                    missing.push(format!("{city} (empty records or tiles)"));
                }
            }
            None => missing.push(city.to_string()),
        }
    }
    if missing.is_empty() {
        (
            StatusCode::OK,
            Json(json!({
                "status": "ready",
                "cities_loaded": st.cities.len(),
                "required_cities": REQUIRED_CITIES,
                "pums_records": st.records.len(),
            })),
        )
            .into_response()
    } else {
        (
            StatusCode::SERVICE_UNAVAILABLE,
            Json(json!({
                "status": "not_ready",
                "cities_loaded": st.cities.len(),
                "missing_cities": missing,
                "required_cities": REQUIRED_CITIES,
            })),
        )
            .into_response()
    }
}

async fn get_city_details(
    State(st): State<AppState>,
    Path(city): Path<String>,
) -> impl IntoResponse {
    let rt = match st.cities.get(&city) {
        Some(rt) => rt,
        None => {
            return (
                StatusCode::NOT_FOUND,
                Json(json!({"error": format!("unknown city: {city}")})),
            )
                .into_response()
        }
    };
    let m = &rt.tiles.manifest;
    let news = crate::news::load(&city);
    Json(json!({
        "slug": rt.profile.slug,
        "display": rt.profile.display,
        "prompt_name": rt.profile.prompt_name,
        "demonym": rt.profile.demonym,
        "bbox": { "west": m.west, "south": m.south, "east": m.east, "north": m.north },
        "n_pums": rt.records.len(),
        "pumas": rt.profile.pumas,
        "neighborhoods": rt.profile.neighborhoods,
        "centroids": rt.profile.centroids,
        "religion_weights": rt.profile.religion_weights,
        "knowledge_date": news.date,
        "default": rt.profile.slug == st.default_city,
    }))
    .into_response()
}

async fn health() -> impl IntoResponse {
    Json(json!({
        "status": "ok",
        "service": "mumb-ai",
        "version": env!("CARGO_PKG_VERSION"),
        "timestamp": chrono::Utc::now().to_rfc3339(),
    }))
}

#[derive(Deserialize)]
struct CreateSimReq {
    #[serde(default)]
    city: Option<String>,
    #[serde(default = "default_n")]
    n: usize,
    #[serde(default = "default_seed")]
    seed: u64,
    #[serde(default = "default_start")]
    start_datetime: String,
    #[serde(default = "default_tick")]
    tick_seconds: i64,
    #[serde(default = "default_commit")]
    commit_every: u64,
    #[serde(default)]
    distributional_params: Option<Value>,
}
fn default_n() -> usize {
    800
}
fn default_seed() -> u64 {
    42
}
fn default_start() -> String {
    "2024-11-01T08:00:00Z".to_string()
}
fn default_tick() -> i64 {
    30
}
fn default_commit() -> u64 {
    20
}

async fn delete_sim(State(st): State<AppState>, Path(id): Path<String>) -> impl IntoResponse {
    let mut sims = lock_mutex(&st.sims);
    if let Some(_ctx) = sims.remove(&id) {
        let _ = st.store.delete_sim(&id);
        return Json(json!({"deleted": id})).into_response();
    }
    (
        StatusCode::NOT_FOUND,
        Json(json!({"error":"simulation not found"})),
    )
        .into_response()
}

async fn create_sim(
    State(st): State<AppState>,
    Json(req): Json<CreateSimReq>,
) -> impl IntoResponse {
    {
        let sims = lock_mutex(&st.sims);
        if sims.len() >= 50 {
            return (
                StatusCode::TOO_MANY_REQUESTS,
                Json(
                    json!({"error": "active simulation limit reached (max 50 active simulations)"}),
                ),
            )
                .into_response();
        }
    }
    if req.n < 1 || req.n > 50_000 {
        return (
            StatusCode::BAD_REQUEST,
            Json(json!({"error": "n must be between 1 and 50000"})),
        )
            .into_response();
    }
    if req.tick_seconds < 1 || req.tick_seconds > 86400 {
        return (
            StatusCode::BAD_REQUEST,
            Json(json!({"error": "tick_seconds must be between 1 and 86400"})),
        )
            .into_response();
    }
    if req.commit_every < 1 || req.commit_every > 1000 {
        return (
            StatusCode::BAD_REQUEST,
            Json(json!({"error": "commit_every must be between 1 and 1000"})),
        )
            .into_response();
    }
    if chrono::DateTime::parse_from_rfc3339(&req.start_datetime).is_err() {
        return (
            StatusCode::BAD_REQUEST,
            Json(json!({"error": "invalid start_datetime (must be valid RFC3339 timestamp)"})),
        )
            .into_response();
    }
    let n = req.n;
    let city_slug = req.city.clone().unwrap_or_else(|| st.default_city.clone());
    let rt = match st.cities.get(&city_slug) {
        Some(r) => r.clone(),
        None => {
            return (
                StatusCode::BAD_REQUEST,
                Json(json!({"error": format!("unknown city: {city_slug}")})),
            )
                .into_response();
        }
    };
    // Build population + engine off the async thread to avoid blocking the tokio runtime
    // (sample_residential_cell does up to 400 SQLite reads per agent).
    let start_secs = parse_iso(&req.start_datetime);
    let rt2 = rt.clone();
    let tick_secs = req.tick_seconds;
    let seed = req.seed;
    let mut profile = (*rt2.profile).clone();
    if let Some(ref params) = req.distributional_params {
        if let Some(arr) = params.get("religion_weights").and_then(|v| v.as_array()) {
            if arr.len() == 9 {
                for (i, v) in arr.iter().enumerate() {
                    if let Some(f) = v.as_f64() {
                        profile.religion_weights[i] = f;
                    }
                }
            }
        }
    }
    let profile_arc = Arc::new(profile);
    let (pop_arc, engine) = tokio::task::spawn_blocking(move || {
        let pop = build_population_with(&rt2.records, n, seed, Some(&rt2.tiles), profile_arc);
        let pop_arc = Arc::new(pop);
        let engine = SimEngine::new(rt2.tiles.clone(), pop_arc.clone(), start_secs, tick_secs);
        (pop_arc, engine)
    })
    .await
    .map_err(|e| {
        (
            StatusCode::INTERNAL_SERVER_ERROR,
            Json(json!({"error": format!("population build failed: {e}")})),
        )
    })
    .unwrap();
    let sim_id = format!(
        "sim-{}-{}-{}-{}",
        city_slug,
        req.seed,
        n,
        short_hash(&format!("{}{}", req.start_datetime, req.tick_seconds))
    );
    let meta = SimMeta {
        seed: req.seed,
        n,
        start_datetime: req.start_datetime.clone(),
        tick_seconds: req.tick_seconds,
        commit_every: req.commit_every,
    };

    // persist static layer + init snapshot for the branching store
    let static_blob = serde_json::to_string(&StaticLayer::from_pop(&pop_arc)).unwrap_or_default();
    let init_state = engine.state.clone();
    let _ = st
        .store
        .create_sim(&sim_id, &meta, &static_blob, &init_state);

    let (tx_main, _) = tokio::sync::broadcast::channel(256);
    let main = Arc::new(BranchState {
        id: format!("{sim_id}:main"),
        sim_id: sim_id.clone(),
        name: "main".into(),
        kind: "main".into(),
        engine: Mutex::new(engine),
        mode: "clean".into(),
        model: None,
        tx: tx_main,
        ticker: Arc::new(tokio::sync::Mutex::new(None)),
    });
    spawn_branch_ticker(main.clone()).await;
    let ctx = Arc::new(SimContext {
        id: sim_id.clone(),
        meta,
        city: rt.clone(),
        population: pop_arc,
        branches: Mutex::new(HashMap::from([(main.id.clone(), main)])),
        counter: Mutex::new(0),
    });
    lock_mutex(&st.sims).insert(sim_id.clone(), ctx);
    let _ = req.distributional_params; // accepted; reserved for per-demographic seeding

    (
        StatusCode::CREATED,
        Json(json!({
            "simulation_id": sim_id,
            "city": city_slug,
            "n": n,
            "main_branch": format!("{sim_id}:main"),
            "start_datetime": req.start_datetime,
        })),
    )
        .into_response()
}

async fn demographics(State(st): State<AppState>, Path(id): Path<String>) -> impl IntoResponse {
    let ctx = match lock_mutex(&st.sims).get(&id).cloned() {
        Some(c) => c,
        None => {
            return (
                StatusCode::NOT_FOUND,
                Json(json!({"error":"simulation not found"})),
            )
                .into_response()
        }
    };
    // target marginals = full SF PUMS (weighted) == ACS; empirical = sampled population.
    let target = marginals_from_records(&ctx.city.records);
    let empirical = marginals_from_agents(&ctx.population.agents);
    let tol = 0.05;
    let mut comparison = serde_json::Map::new();
    let mut all_pass = true;
    for (var, emp) in &empirical {
        let tgt = target.get(var).cloned().unwrap_or_default();
        let dist = tv_dist(emp, &tgt);
        let pass = dist <= tol;
        all_pass &= pass;
        comparison.insert(var.clone(), json!({
            "empirical": emp, "target_acs": tgt, "tv_distance": dist, "pass": pass, "tolerance": tol
        }));
    }
    Json(json!({
        "simulation_id": id,
        "n_agents": ctx.population.agents.len(),
        "total_weight": ctx.population.total_weight(),
        "variables": comparison,
        "all_within_tolerance": all_pass,
    }))
    .into_response()
}

#[derive(Deserialize)]
struct CreateBranchReq {
    #[serde(default)]
    event: Option<BranchEvent>,
    #[serde(default = "default_ticks")]
    ticks: usize,
    #[serde(default)]
    model: Option<String>,
    #[serde(default)]
    mode: Option<String>,
    #[serde(default)]
    name: Option<String>,
}
#[derive(Deserialize)]
struct BranchEvent {
    text: String,
    #[serde(default)]
    progressive_coded: Option<bool>,
}
fn default_ticks() -> usize {
    20
}

async fn create_branch(
    State(st): State<AppState>,
    Path(id): Path<String>,
    Json(req): Json<CreateBranchReq>,
) -> impl IntoResponse {
    let ctx = match lock_mutex(&st.sims).get(&id).cloned() {
        Some(c) => c,
        None => {
            return (
                StatusCode::NOT_FOUND,
                Json(json!({"error":"simulation not found"})),
            )
                .into_response()
        }
    };
    {
        let branches = lock_mutex(&ctx.branches);
        if branches.len() >= 20 {
            return (
                StatusCode::TOO_MANY_REQUESTS,
                Json(
                    json!({"error": "branch limit reached for this simulation (max 20 branches)"}),
                ),
            )
                .into_response();
        }
    }
    let bnum = {
        let mut c = lock_mutex(&ctx.counter);
        *c += 1;
        *c
    };
    let branch_id = format!("{id}:b{bnum}");
    let name = match req.name {
        Some(ref n) => {
            let trimmed = n.trim();
            if trimmed.is_empty() || trimmed.len() > 64 {
                return (
                    StatusCode::BAD_REQUEST,
                    Json(json!({"error": "invalid branch name: must be non-empty and <= 64 characters"})),
                )
                    .into_response();
            }
            trimmed.to_string()
        }
        None => format!("branch-{bnum}"),
    };
    let ticks = req.ticks.clamp(1, 2000);

    // clone main's current state into the new branch engine
    let main_state = {
        let m = lock_mutex(&ctx.branches);
        let main = match m.get(&format!("{id}:main")) {
            Some(main_b) => main_b.clone(),
            None => {
                return (
                    StatusCode::INTERNAL_SERVER_ERROR,
                    Json(json!({"error": "main branch not found"})),
                )
                    .into_response()
            }
        };
        let e = main.engine.lock().unwrap();
        e.state.clone()
    };
    let mut engine = SimEngine::from_state(
        ctx.city.tiles.clone(),
        ctx.population.clone(),
        main_state,
        ctx.meta.tick_seconds,
    );

    // apply the broadcast event (reactions + episodic memory) then run k ticks
    let mut reactions = 0usize;
    let mut event_text = String::new();
    if let Some(ev) = &req.event {
        let prog = ev.progressive_coded.unwrap_or(true);
        let evs = engine.broadcast(&branch_id, prog);
        reactions = evs.len();
        event_text = ev.text.clone();
        // record the event into agents' episodic memory (bounded) so social-mode polls see it
        let tag = format!("heard: {}", truncate_words(&ev.text, 16));
        for a in engine.state.agents.iter_mut() {
            a.memory.push(tag.clone());
            if a.memory.len() > 8 {
                a.memory.remove(0);
            }
        }
    }
    for _ in 0..ticks {
        let _ = engine.tick();
    }

    // persist branch snapshot in the store
    let main_head = st.store.branch_head(&format!("{id}:main")).ok();
    if let Some(head) = main_head {
        if let Ok(info) = st.store.create_branch(&id, head, &branch_id, &name) {
            if let Err(e) = st
                .store
                .commit(&id, &branch_id, &engine.state, "after-ticks")
            {
                return (
                    StatusCode::INTERNAL_SERVER_ERROR,
                    Json(
                        json!({"error": format!("failed to commit branch state to store: {e:#}")}),
                    ),
                )
                    .into_response();
            }
            let _ = info;
        }
    }

    let clock = engine.state.clock_secs;
    let tick = engine.state.tick;
    let (tx_b, _) = tokio::sync::broadcast::channel(256);
    let bs = Arc::new(BranchState {
        id: branch_id.clone(),
        sim_id: id.clone(),
        name: name.clone(),
        kind: "branch".into(),
        engine: Mutex::new(engine),
        mode: req.mode.clone().unwrap_or_else(|| "social".into()),
        model: req.model.clone(),
        tx: tx_b,
        ticker: Arc::new(tokio::sync::Mutex::new(None)),
    });
    spawn_branch_ticker(bs.clone()).await;
    lock_mutex(&ctx.branches).insert(branch_id.clone(), bs);

    (
        StatusCode::CREATED,
        Json(json!({
            "branch_id": branch_id,
            "name": name,
            "ticks_run": ticks,
            "reactions_emitted": reactions,
            "event": event_text,
            "clock": crate::sim::secs_to_iso(clock),
            "tick": tick,
        })),
    )
        .into_response()
}

async fn branch_status(State(st): State<AppState>, Path(bid): Path<String>) -> impl IntoResponse {
    match find_branch(&st, &bid) {
        Some((_ctx, bs)) => {
            let e = bs.engine.lock().unwrap();
            let alive = e.state.agents.iter().filter(|a| a.alive).count();
            Json(json!({
                "branch_id": bs.id,
                "sim_id": bs.sim_id,
                "name": bs.name,
                "kind": bs.kind,
                "mode": bs.mode,
                "status": "ready",
                "tick": e.state.tick,
                "clock": crate::sim::secs_to_iso(e.state.clock_secs),
                "agents_alive": alive,
            }))
            .into_response()
        }
        None => (
            StatusCode::NOT_FOUND,
            Json(json!({"error":"branch not found"})),
        )
            .into_response(),
    }
}

async fn delete_branch(State(st): State<AppState>, Path(bid): Path<String>) -> impl IntoResponse {
    if bid.ends_with(":main") {
        return (
            StatusCode::BAD_REQUEST,
            Json(json!({"error":"cannot delete main"})),
        )
            .into_response();
    }
    if let Some((ctx, _)) = find_branch(&st, &bid) {
        lock_mutex(&ctx.branches).remove(&bid);
        let _ = st.store.delete_branch(&bid);
        return Json(json!({"deleted": bid})).into_response();
    }
    (
        StatusCode::NOT_FOUND,
        Json(json!({"error":"branch not found"})),
    )
        .into_response()
}

async fn reset_to_main(State(st): State<AppState>, Path(id): Path<String>) -> impl IntoResponse {
    let ctx = match lock_mutex(&st.sims).get(&id).cloned() {
        Some(c) => c,
        None => {
            return (
                StatusCode::NOT_FOUND,
                Json(json!({"error":"simulation not found"})),
            )
                .into_response()
        }
    };
    // drop all non-main branches; main is the canonical HEAD
    let removed: Vec<String> = {
        let mut m = lock_mutex(&ctx.branches);
        let keys: Vec<String> = m
            .keys()
            .filter(|k| !k.ends_with(":main"))
            .cloned()
            .collect();
        for k in &keys {
            m.remove(k);
            let _ = st.store.delete_branch(k);
        }
        keys
    };
    let main_tick = {
        let m = lock_mutex(&ctx.branches);
        let main = match m.get(&format!("{id}:main")) {
            Some(main_b) => main_b.clone(),
            None => {
                return (
                    StatusCode::INTERNAL_SERVER_ERROR,
                    Json(json!({"error": "main branch not found"})),
                )
                    .into_response()
            }
        };
        let e = main.engine.lock().unwrap();
        e.state.tick
    };
    Json(json!({"reset_to": format!("{id}:main"), "dropped_branches": removed, "main_tick": main_tick})).into_response()
}

#[derive(Deserialize)]
struct AgentsQuery {
    #[serde(default)]
    filter: Option<String>,
    #[serde(default = "default_limit")]
    limit: usize,
    #[serde(default)]
    offset: usize,
}
fn default_limit() -> usize {
    500
}

async fn branch_agents(
    State(st): State<AppState>,
    Path(bid): Path<String>,
    Query(q): Query<AgentsQuery>,
) -> impl IntoResponse {
    let (ctx, bs) = match find_branch(&st, &bid) {
        Some(x) => x,
        None => {
            return (
                StatusCode::NOT_FOUND,
                Json(json!({"error":"branch not found"})),
            )
                .into_response()
        }
    };
    let filt = parse_filter(q.filter.as_deref());
    let e = bs.engine.lock().unwrap();
    let limit = q.limit.clamp(1, 5000);
    let mut out = Vec::new();
    let mut matched = 0usize;
    for ast in e.state.agents.iter() {
        if !ast.alive {
            continue;
        }
        let agent = match ctx.population.agents.get(ast.id as usize) {
            Some(a) => a,
            None => continue, // born agents have no static persona record
        };
        if !filter_matches(agent, &filt) {
            continue;
        }
        matched += 1;
        if matched <= q.offset {
            continue;
        }
        if out.len() >= limit {
            continue;
        }
        let (lon, lat) = ctx.city.tiles.cell_to_lonlat(ast.pos);
        out.push(json!({
            "id": ast.id,
            "name": agent.name,
            "action": ast.action,
            "alive": ast.alive,
            "cell": [ast.pos.x, ast.pos.y],
            "lonlat": [lon, lat],
            "neighborhood": agent.neighborhood,
            "age": agent.rec.age,
            "race_eth": agent.rec.race_eth(),
            "educ": agent.rec.educ(),
            "values": agent.values,
        }));
    }
    Json(json!({
        "branch_id": bid,
        "total_matched": matched,
        "offset": q.offset,
        "count": out.len(),
        "agents": out,
    }))
    .into_response()
}

#[derive(serde::Deserialize)]
struct ChatterReq {
    #[serde(default)]
    ids: Vec<u32>,
}

/// Ambient sprite chatter for the residents currently on screen — one short,
/// in-character LLM thought per requested resident, batched into a single call.
/// The UI asks only for visible sprites and caches the result, so this is sparse.
async fn branch_chatter(
    State(st): State<AppState>,
    Path(bid): Path<String>,
    Json(req): Json<ChatterReq>,
) -> impl IntoResponse {
    let (ctx, _bs) = match find_branch(&st, &bid) {
        Some(x) => x,
        None => {
            return (
                StatusCode::NOT_FOUND,
                Json(json!({"error":"branch not found"})),
            )
                .into_response()
        }
    };
    let ids: Vec<u32> = req.ids.into_iter().take(16).collect();
    let pairs = st.engine.chatter(&ctx.population, &ids).await;
    let map: serde_json::Map<String, Value> = pairs
        .into_iter()
        .map(|(id, t)| (id.to_string(), Value::String(t)))
        .collect();
    Json(json!({ "chatter": map })).into_response()
}

async fn branch_poll(
    State(st): State<AppState>,
    Path(bid): Path<String>,
    Json(req): Json<Value>,
) -> impl IntoResponse {
    let (ctx, bs) = match find_branch(&st, &bid) {
        Some(x) => x,
        None => {
            return (
                StatusCode::NOT_FOUND,
                Json(json!({"error":"branch not found"})),
            )
                .into_response()
        }
    };
    let mut poll = match poll_from_json(&req) {
        Ok(p) => p,
        Err(e) => return (StatusCode::BAD_REQUEST, Json(json!({"error": e}))).into_response(),
    };
    if poll.model.is_none() {
        poll.model = bs.model.clone();
    }
    match st.engine.run_poll(&ctx.population, &poll).await {
        Ok(res) => Json(json!(res)).into_response(),
        Err(e) => (
            StatusCode::BAD_GATEWAY,
            Json(json!({"error": format!("poll failed: {e}")})),
        )
            .into_response(),
    }
}

async fn predict_market(
    State(st): State<AppState>,
    Path(bid): Path<String>,
    Json(req): Json<Value>,
) -> impl IntoResponse {
    let (ctx, bs) = match find_branch(&st, &bid) {
        Some(x) => x,
        None => {
            return (
                StatusCode::NOT_FOUND,
                Json(json!({"error":"branch not found"})),
            )
                .into_response()
        }
    };
    let question = match req
        .get("question")
        .and_then(|x| x.as_str())
        .map(|s| s.trim())
        .filter(|s| !s.is_empty())
    {
        Some(q) => q.to_string(),
        None => {
            return (
                StatusCode::BAD_REQUEST,
                Json(json!({"error":"question required"})),
            )
                .into_response()
        }
    };
    let as_of = match req
        .get("as_of_date")
        .and_then(|x| x.as_str())
        .map(|s| s.trim())
        .filter(|s| !s.is_empty())
    {
        Some(d) => d.to_string(),
        None => {
            return (
                StatusCode::BAD_REQUEST,
                Json(json!({"error":"as_of_date required"})),
            )
                .into_response()
        }
    };
    if chrono::NaiveDate::parse_from_str(&as_of, "%Y-%m-%d").is_err()
        && chrono::DateTime::parse_from_rfc3339(&as_of).is_err()
    {
        return (
            StatusCode::BAD_REQUEST,
            Json(json!({"error": "invalid as_of_date: must be YYYY-MM-DD or RFC3339"})),
        )
            .into_response();
    }
    let bucket = req
        .get("bucket")
        .and_then(|x| x.as_str())
        .unwrap_or("city_opinion_informative")
        .to_string();
    let model = req
        .get("model")
        .and_then(|x| x.as_str())
        .map(|s| s.to_string())
        .or_else(|| bs.model.clone());
    let poll = Poll {
        question: question.clone(),
        description: req
            .get("description")
            .and_then(|x| x.as_str())
            .unwrap_or("Prediction-market question mapped to a pollable belief.")
            .to_string(),
        framing: Framing::Belief,
        as_of_date: as_of.clone(),
        model,
        population: None,
        event: None,
        options: Vec::new(),
    };
    match st.engine.run_poll(&ctx.population, &poll).await {
        Ok(res) => Json(json!({
            "question": question,
            "as_of_date": as_of,
            "bucket": bucket,
            "sim_probability_yes": res.p_yes,
            "ci": [res.ci_low, res.ci_high],
            "n_agents": res.n_agents,
            "model": res.model,
            "note": "headline market number weights the city_opinion_informative bucket; general_knowledge is reported separately.",
            "live_market_price": req.get("live_market_price"),
        })).into_response(),
        Err(e) => (StatusCode::BAD_GATEWAY, Json(json!({"error": format!("market poll failed: {e}")}))).into_response(),
    }
}

async fn branch_stream(State(st): State<AppState>, Path(bid): Path<String>) -> impl IntoResponse {
    let bs = match find_branch(&st, &bid) {
        Some((_, bs)) => bs,
        None => {
            let s = async_stream::stream! {
                yield Ok::<_, Infallible>(SseEvent::default().event("error").data("{\"error\":\"branch not found\"}"));
            };
            return Sse::new(Box::pin(s)
                as std::pin::Pin<
                    Box<dyn futures::Stream<Item = Result<SseEvent, Infallible>> + Send>,
                >)
            .into_response();
        }
    };
    let stream = async_stream::stream! {
        // initial snapshot so a client sees a typed event immediately.
        // Scope the MutexGuard so it never lives across a yield/await (guards are !Send).
        let snap = {
            let e = bs.engine.lock().unwrap();
            json!({
                "type": "snapshot",
                "tick": e.state.tick,
                "clock": crate::sim::secs_to_iso(e.state.clock_secs),
                "agents_alive": e.state.agents.iter().filter(|a| a.alive).count(),
            })
        };
        yield Ok::<_, Infallible>(SseEvent::default().event("snapshot").data(snap.to_string()));

        // subscribe to branch events
        let mut rx = bs.tx.subscribe();
        while let Ok(ev) = rx.recv().await {
            let data = serde_json::to_string(&ev).unwrap_or_default();
            let name = sse_event_name(&ev);
            yield Ok::<_, Infallible>(SseEvent::default().event(name).data(data));
        }
    };
    Sse::new(Box::pin(stream)
        as std::pin::Pin<
            Box<dyn futures::Stream<Item = Result<SseEvent, Infallible>> + Send>,
        >)
    .keep_alive(axum::response::sse::KeepAlive::default())
    .into_response()
}

fn sse_event_name(ev: &SimEvent) -> &'static str {
    match ev {
        SimEvent::AgentMoved { .. } => "agent_moved",
        SimEvent::AgentSaid { .. } => "agent_said",
        SimEvent::AgentReacted { .. } => "agent_reacted",
        SimEvent::Tick { .. } => "tick",
        SimEvent::Birth { .. } => "birth",
        SimEvent::Death { .. } => "death",
    }
}

// ---- helpers ----

fn find_branch(st: &AppState, bid: &str) -> Option<(Arc<SimContext>, Arc<BranchState>)> {
    let sim_id = bid.split(':').next().map(|s| {
        // sim ids contain ':'? No — sim id is the part before the last ':bN' / ':main'.
        s.to_string()
    });
    let _ = sim_id;
    // sim_id is everything up to the last ':'
    let sim_id = match bid.rfind(':') {
        Some(i) => bid[..i].to_string(),
        None => return None,
    };
    let ctx = lock_mutex(&st.sims).get(&sim_id).cloned()?;
    let bs = lock_mutex(&ctx.branches).get(bid).cloned()?;
    Some((ctx, bs))
}

fn poll_from_json(req: &Value) -> Result<Poll, String> {
    let question = req
        .get("question")
        .and_then(|x| x.as_str())
        .ok_or("question required")?
        .to_string();
    let description = req
        .get("description")
        .and_then(|x| x.as_str())
        .unwrap_or("")
        .to_string();
    let as_of_date = req
        .get("as_of_date")
        .and_then(|x| x.as_str())
        .unwrap_or("2024-01-01")
        .to_string();
    let framing = match req.get("framing").and_then(|x| x.as_str()) {
        Some("belief") => Framing::Belief,
        Some("options") => Framing::Options,
        _ => Framing::Vote,
    };
    let event = req.get("event").and_then(|e| e.as_str()).map(|t| Event {
        text: t.to_string(),
        as_of_date: as_of_date.clone(),
    });
    let options = req
        .get("options")
        .and_then(|x| x.as_array())
        .map(|a| {
            a.iter()
                .filter_map(|v| v.as_str().map(|s| s.to_string()))
                .collect()
        })
        .unwrap_or_default();
    Ok(Poll {
        question,
        description,
        framing,
        as_of_date,
        model: req
            .get("model")
            .and_then(|x| x.as_str())
            .map(|s| s.to_string()),
        population: req
            .get("population")
            .and_then(|x| x.as_str())
            .map(|s| s.to_string()),
        event,
        options,
    })
}

#[derive(Default)]
struct Filter {
    pairs: Vec<(String, String)>,
}
fn parse_filter(s: Option<&str>) -> Filter {
    let mut f = Filter::default();
    if let Some(s) = s {
        for part in s.split([',', '&']) {
            if let Some((k, v)) = part.split_once(['=', ':']) {
                f.pairs.push((k.trim().to_string(), v.trim().to_string()));
            }
        }
    }
    f
}
fn filter_matches(a: &Agent, f: &Filter) -> bool {
    for (k, v) in &f.pairs {
        let ok = match k.as_str() {
            "race" | "race_eth" => a.rec.race_eth() == v,
            "educ" => a.rec.educ() == v,
            "age_band" => a.rec.age_band() == v,
            "puma" => a.rec.puma.to_string() == *v,
            "tenure" => (if a.homeowner { "own" } else { "rent" }) == v,
            "sex" => a.rec.sex.to_string() == *v,
            "religion" => a.religion.label().contains(v.as_str()),
            _ => true,
        };
        if !ok {
            return false;
        }
    }
    true
}

fn marginals_from_records(recs: &[PumsRecord]) -> HashMap<String, HashMap<String, f64>> {
    let mut m: HashMap<String, HashMap<String, f64>> = HashMap::new();
    for r in recs {
        add_marginal(&mut m, "age_band", r.age_band(), r.pwgtp);
        add_marginal(&mut m, "race_eth", r.race_eth(), r.pwgtp);
        add_marginal(&mut m, "educ", r.educ(), r.pwgtp);
        add_marginal(
            &mut m,
            "sex",
            if r.sex == 1 { "male" } else { "female" },
            r.pwgtp,
        );
        add_marginal(
            &mut m,
            "citizen",
            if r.is_citizen() { "yes" } else { "no" },
            r.pwgtp,
        );
    }
    normalize(&mut m);
    m
}
fn marginals_from_agents(agents: &[Agent]) -> HashMap<String, HashMap<String, f64>> {
    let mut m: HashMap<String, HashMap<String, f64>> = HashMap::new();
    for a in agents {
        let w = a.weight();
        add_marginal(&mut m, "age_band", a.rec.age_band(), w);
        add_marginal(&mut m, "race_eth", a.rec.race_eth(), w);
        add_marginal(&mut m, "educ", a.rec.educ(), w);
        add_marginal(
            &mut m,
            "sex",
            if a.rec.sex == 1 { "male" } else { "female" },
            w,
        );
        add_marginal(
            &mut m,
            "citizen",
            if a.rec.is_citizen() { "yes" } else { "no" },
            w,
        );
    }
    normalize(&mut m);
    m
}
fn add_marginal(m: &mut HashMap<String, HashMap<String, f64>>, var: &str, level: &str, w: f64) {
    *m.entry(var.to_string())
        .or_default()
        .entry(level.to_string())
        .or_insert(0.0) += w;
}
fn normalize(m: &mut HashMap<String, HashMap<String, f64>>) {
    for (_, dist) in m.iter_mut() {
        let total: f64 = dist.values().sum();
        if total > 0.0 {
            for v in dist.values_mut() {
                *v /= total;
            }
        }
    }
}
fn tv_dist(a: &HashMap<String, f64>, b: &HashMap<String, f64>) -> f64 {
    let mut keys: std::collections::HashSet<&String> = a.keys().collect();
    keys.extend(b.keys());
    let mut d = 0.0;
    for k in keys {
        d += (a.get(k).copied().unwrap_or(0.0) - b.get(k).copied().unwrap_or(0.0)).abs();
    }
    d / 2.0
}

#[derive(serde::Serialize)]
struct StaticLayer {
    n: usize,
    seed: u64,
}
impl StaticLayer {
    fn from_pop(p: &Population) -> Self {
        StaticLayer {
            n: p.agents.len(),
            seed: p.seed,
        }
    }
}

fn parse_iso(s: &str) -> i64 {
    chrono::DateTime::parse_from_rfc3339(s)
        .map(|dt| dt.timestamp())
        .unwrap_or(1730448000) // 2024-11-01T08:00:00Z fallback
}

fn truncate_words(s: &str, n: usize) -> String {
    s.split_whitespace().take(n).collect::<Vec<_>>().join(" ")
}

fn short_hash(s: &str) -> String {
    use sha2::{Digest, Sha256};
    let mut h = Sha256::new();
    h.update(s.as_bytes());
    hex::encode(&h.finalize()[..4])
}

/// Parse a free-text question into a pollable spec (framing + options), or return a
/// "not supported" reason with example phrasings. One LLM call.
async fn parse_question_handler(
    State(st): State<AppState>,
    Path(city): Path<String>,
    Json(req): Json<Value>,
) -> impl IntoResponse {
    let raw = req
        .get("question")
        .and_then(|x| x.as_str())
        .unwrap_or("")
        .trim()
        .to_string();
    if raw.is_empty() {
        return (
            StatusCode::BAD_REQUEST,
            Json(json!({"error": "question required"})),
        )
            .into_response();
    }
    let name = st
        .cities
        .get(&city)
        .map(|r| r.profile.prompt_name.clone())
        .unwrap_or_else(|| "this city".to_string());
    let model = Model::parse(
        req.get("model")
            .and_then(|x| x.as_str())
            .unwrap_or("claude-sonnet-4-6"),
    );
    let parsed = crate::parse::parse_question(&st.client, &name, &raw, model).await;
    Json(json!(parsed)).into_response()
}

/// Recent news for a city (the frontend news bubble) + the served knowledge date.
async fn city_news(State(st): State<AppState>, Path(city): Path<String>) -> impl IntoResponse {
    if !st.cities.contains_key(&city) {
        return (
            StatusCode::NOT_FOUND,
            Json(json!({"error": format!("unknown city: {city}")})),
        )
            .into_response();
    }
    let news = crate::news::load(&city);
    Json(json!({ "city": city, "date": news.date, "articles": news.articles })).into_response()
}

async fn list_cities(State(st): State<AppState>) -> impl IntoResponse {
    let mut slugs: Vec<&String> = st.cities.keys().collect();
    slugs.sort();
    let cities: Vec<Value> = slugs
        .iter()
        .map(|slug| {
            let rt = &st.cities[*slug];
            let m = &rt.tiles.manifest;
            json!({
                "slug": rt.profile.slug,
                "display": rt.profile.display,
                "prompt_name": rt.profile.prompt_name,
                "bbox": { "west": m.west, "south": m.south, "east": m.east, "north": m.north },
                "n_pums": rt.records.len(),
                "knowledge_date": crate::news::load(&rt.profile.slug).date,
                "default": rt.profile.slug == st.default_city,
            })
        })
        .collect();
    Json(json!({ "cities": cities }))
}

fn load_city_runtime(slug: &str) -> anyhow::Result<CityRuntime> {
    let profile = CityProfile::load(slug)?;
    let tiles = Arc::new(TilesDb::open(&profile.tiles_path)?);
    profile.validate(&tiles.manifest)?;
    let records = Arc::new(crate::pums::load_city(&profile)?);
    if records.is_empty() {
        anyhow::bail!("city {slug} loaded 0 PUMS records");
    }
    Ok(CityRuntime {
        profile: Arc::new(profile),
        tiles,
        records,
    })
}

/// Build the full AppState from environment (loads every available city + opens caches).
pub fn build_state(
    _tiles_path: &str,
    cache_path: Option<&str>,
    state_db: &str,
) -> anyhow::Result<AppState> {
    let cache = match cache_path {
        Some(p) => Some(Arc::new(Cache::open(p)?)),
        None => None,
    };
    let client = ModelClient::from_env(cache)?;
    let engine = Engine::new(client.clone());
    let store = Arc::new(Store::open(state_db)?);

    let mut cities: HashMap<String, Arc<CityRuntime>> = HashMap::new();

    // Dynamically discover all cities from data/cities/*.toml
    let default_city_name = std::env::var("DEFAULT_CITY").unwrap_or_else(|_| "mumbai".to_string());
    let mut slugs = Vec::new();
    if let Ok(entries) = std::fs::read_dir("data/cities") {
        for entry in entries.flatten() {
            let path = entry.path();
            if path.extension().map_or(false, |ext| ext == "toml") {
                if let Some(stem) = path.file_stem().and_then(|s| s.to_str()) {
                    slugs.push(stem.to_string());
                }
            }
        }
    }
    slugs.sort();

    const REQUIRED_CITIES: &[&str] = &["mumbai", "delhi", "kolkata", "bangalore", "jaipur"];
    for req_slug in REQUIRED_CITIES {
        if !slugs.iter().any(|s| s == req_slug) {
            anyhow::bail!("missing required production city profile: data/cities/{req_slug}.toml");
        }
    }

    for slug in &slugs {
        let rt = load_city_runtime(slug)
            .map_err(|e| anyhow::anyhow!("failed to load city '{slug}': {e:#}"))?;
        tracing::info!("loaded city {slug}: {} PUMS records", rt.records.len());
        cities.insert(slug.clone(), Arc::new(rt));
    }

    let default_rt = cities
        .get(&default_city_name)
        .or_else(|| cities.values().next())
        .cloned()
        .ok_or_else(|| anyhow::anyhow!("no valid city loaded (checked {})", default_city_name))?;

    let resolved_default = default_rt.profile.slug.clone();

    let auth_token = std::env::var("AUTH_TOKEN")
        .or_else(|_| std::env::var("BEARER_TOKEN"))
        .or_else(|_| std::env::var("API_KEY"))
        .ok()
        .filter(|t| !t.is_empty());
    let rate_limiter = Arc::new(RateLimiter::new(120));

    Ok(AppState {
        client,
        engine,
        tiles: default_rt.tiles.clone(),
        records: default_rt.records.clone(),
        cities: Arc::new(cities),
        default_city: resolved_default,
        store,
        sims: Arc::new(Mutex::new(HashMap::new())),
        model_ok: Arc::new(Mutex::new(None)),
        auth_token,
        rate_limiter,
    })
}

// silence unused imports used only in some build configs
#[allow(unused_imports)]
use crate::state as _state;
#[allow(dead_code)]
fn _touch(_: AgentState, _: SimState) {}
