use serde_json::Value;
use std::time::Duration;

fn client() -> reqwest::Client {
    reqwest::Client::builder()
        .timeout(Duration::from_secs(120))
        .build()
        .unwrap()
}

async fn base() -> String {
    let ws_root = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../..");
    std::env::set_current_dir(&ws_root).ok();
    std::env::set_var("MODEL_OFFLINE", "1");
    simfrancisco::load_dotenv(".env");
    let dir = std::env::temp_dir().join(format!("mumbai_val_{}", std::process::id()));
    std::fs::create_dir_all(&dir).ok();
    let cache_path = dir.join("cache.db");
    let state_path = dir.join("state.db");
    let state = simfrancisco::api::build_state(
        "tiles.db",
        Some(cache_path.to_str().unwrap()),
        state_path.to_str().unwrap(),
    )
    .expect("build_state");

    let app = simfrancisco::api::router(state);
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let addr = listener.local_addr().unwrap();
    tokio::spawn(async move {
        axum::serve(listener, app).await.unwrap();
    });
    tokio::time::sleep(Duration::from_millis(150)).await;
    format!("http://{addr}")
}

#[tokio::test]
async fn test_api_validations_and_errors() {
    let base = base().await;
    let c = client();

    // 1. GET / serves HTML
    let r = c.get(format!("{base}/")).send().await.unwrap();
    assert_eq!(r.status(), 200);
    let body = r.text().await.unwrap();
    assert!(body.contains("<!DOCTYPE html>") || body.contains("<html"));

    // 2. GET /api & /version serve JSON metadata
    let r = c.get(format!("{base}/api")).send().await.unwrap();
    assert_eq!(r.status(), 200);
    let v: Value = r.json().await.unwrap();
    assert_eq!(v["service"], "mumb-ai");

    let r = c.get(format!("{base}/version")).send().await.unwrap();
    assert_eq!(r.status(), 200);
    let v_ver: Value = r.json().await.unwrap();
    assert_eq!(v_ver["service"], "mumb-ai");

    // 3. GET /cities lists 5 Indian cities
    let r_bad_method = c.post(format!("{base}/cities")).send().await.unwrap();
    assert_eq!(r_bad_method.status(), 405);
    let r = c.get(format!("{base}/cities")).send().await.unwrap();
    assert_eq!(r.status(), 200);
    let v_cities: Value = r.json().await.unwrap();
    let slugs: Vec<String> = v_cities["cities"]
        .as_array()
        .unwrap()
        .iter()
        .map(|cc| cc["slug"].as_str().unwrap().to_string())
        .collect();
    assert!(slugs.contains(&"mumbai".to_string()));
    assert!(slugs.contains(&"delhi".to_string()));
    assert!(slugs.contains(&"bangalore".to_string()));
    assert!(slugs.contains(&"kolkata".to_string()));
    assert!(slugs.contains(&"jaipur".to_string()));

    // 4. Invalid city returns 404 for details and news
    let r = c
        .get(format!("{base}/cities/unknown_city"))
        .send()
        .await
        .unwrap();
    assert_eq!(r.status(), 404);

    let r = c
        .get(format!("{base}/cities/unknown_city/news"))
        .send()
        .await
        .unwrap();
    assert_eq!(r.status(), 404);

    // 5. Simulation input validation
    let r = c
        .post(format!("{base}/simulations"))
        .json(&serde_json::json!({"n": 0}))
        .send()
        .await
        .unwrap();
    assert_eq!(r.status(), 400);
    let r = c
        .post(format!("{base}/simulations"))
        .json(&serde_json::json!({"n": 60000}))
        .send()
        .await
        .unwrap();
    assert_eq!(r.status(), 400);

    let r = c
        .post(format!("{base}/simulations"))
        .json(&serde_json::json!({"tick_seconds": 0}))
        .send()
        .await
        .unwrap();
    assert_eq!(r.status(), 400);
    let r = c
        .post(format!("{base}/simulations"))
        .json(&serde_json::json!({"start_datetime": "not-a-date"}))
        .send()
        .await
        .unwrap();
    assert_eq!(r.status(), 400);

    // Valid simulation creation
    let r = c.post(format!("{base}/simulations")).json(&serde_json::json!({"city": "mumbai", "n": 100, "start_datetime": "2026-09-07T08:00:00Z"})).send().await.unwrap();
    assert_eq!(r.status(), 201);
    let v_sim: Value = r.json().await.unwrap();
    let sim_id = v_sim["simulation_id"].as_str().unwrap().to_string();
    let main_branch = v_sim["main_branch"].as_str().unwrap().to_string();

    // 6. Predict market input validation
    let r = c
        .post(format!("{base}/branches/{main_branch}/predict-market"))
        .json(&serde_json::json!({"question": "Will rain fall?"}))
        .send()
        .await
        .unwrap();
    assert_eq!(r.status(), 400);
    let r = c
        .post(format!("{base}/branches/{main_branch}/predict-market"))
        .json(&serde_json::json!({"question": "Will rain fall?", "as_of_date": "invalid-date"}))
        .send()
        .await
        .unwrap();
    assert_eq!(r.status(), 400);
    let r = c
        .post(format!("{base}/branches/{main_branch}/predict-market"))
        .json(&serde_json::json!({"as_of_date": "2026-09-07"}))
        .send()
        .await
        .unwrap();
    assert_eq!(r.status(), 400);

    // 7. Simulation deletion
    let r = c
        .delete(format!("{base}/simulations/{sim_id}"))
        .send()
        .await
        .unwrap();
    assert_eq!(r.status(), 200);
    let r = c
        .delete(format!("{base}/simulations/{sim_id}"))
        .send()
        .await
        .unwrap();
    assert_eq!(r.status(), 404);
}

#[tokio::test]
async fn test_multi_client_sse_isolation() {
    use futures::StreamExt;

    let base = base().await;
    let c = client();

    let r = c
        .post(format!("{}/simulations", base))
        .json(&serde_json::json!({
            "n": 20,
            "start_datetime": "2026-09-07T12:00:00Z",
            "tick_seconds": 60,
            "commit_every": 10
        }))
        .send()
        .await
        .unwrap();
    assert_eq!(r.status(), 201);
    let v: Value = r.json().await.unwrap();
    let main_branch = v["main_branch"].as_str().unwrap();

    let url = format!("{}/branches/{}/stream", base, main_branch);
    let resp1 = c.get(&url).send().await.unwrap();
    let resp2 = c.get(&url).send().await.unwrap();
    assert_eq!(resp1.status(), 200);
    assert_eq!(resp2.status(), 200);

    let mut stream1 = resp1.bytes_stream();
    let mut stream2 = resp2.bytes_stream();

    let chunk1 = tokio::time::timeout(std::time::Duration::from_secs(3), stream1.next())
        .await
        .expect("client 1 received chunk")
        .expect("chunk exists")
        .unwrap();
    let chunk2 = tokio::time::timeout(std::time::Duration::from_secs(3), stream2.next())
        .await
        .expect("client 2 received chunk")
        .expect("chunk exists")
        .unwrap();

    let str1 = String::from_utf8_lossy(&chunk1);
    let str2 = String::from_utf8_lossy(&chunk2);

    assert!(
        str1.contains("event: snapshot"),
        "client 1 receives snapshot"
    );
    assert!(
        str2.contains("event: snapshot"),
        "client 2 receives snapshot"
    );

    let r = c
        .get(format!("{}/branches/{}", base, main_branch))
        .send()
        .await
        .unwrap();
    let v: Value = r.json().await.unwrap();
    let tick_val = v["tick"].as_u64().unwrap();
    assert!(tick_val < 100, "tick rate isolation failed");
}
