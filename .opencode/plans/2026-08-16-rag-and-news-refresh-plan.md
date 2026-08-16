# RAG (Retrieval-Augmented Generation) & Daily News Refresh Plan

## 1. RAG Overview & Architecture
Currently, the simulation uses fixed persona vectors and a simple head-block of news headlines injected into LLM prediction prompts. 
Adding **RAG** allows the synthetic electorate (and individual neighborhood sprites) to draw from targeted, highly relevant local news, policy details, and neighborhood facts when forming opinions or generating speech bubbles.

### Key RAG Components:
1. **Knowledge Store (`crates/sim-core/src/rag.rs`)**:
   - **Document Corpus**:
     - Live News API headlines & summaries (`data/news/<slug>.json`).
     - Neighborhood Profiles (e.g., Dharavi/Bandra in Mumbai, Connaught Place/Dwarka in Delhi, Electronic City in Bangalore).
     - Local Policy & Infrastructure Briefs (Metro expansions, water supply, tax reforms, local elections).
   - **Vector / BM25 Retriever**:
     - Fast keyword/BM25 + TF-IDF cosine similarity index built per city.
     - Zero external DB overhead; runs in-process inside `sim-core`.

2. **Query-Driven Context Retrieval**:
   - When a prediction query comes in (e.g., *"Do residents support the coastal road expansion?"*):
     - Query vector matcher retrieves top-$K$ ($K=3..5$) relevant articles/facts.
     - Constructs a targeted context snippet injected into the archetype LLM prompt.

3. **Persona & Neighborhood RAG Grounding**:
   - When generating speech/thought bubbles for an agent in a specific neighborhood (e.g., Bandra West vs Thane):
     - RAG filters news matching the agent's primary concerns (`s_transit`, `s_housing`, `s_cost`) and neighborhood.
     - Result: Hyper-local, realistic thoughts (e.g., *"Metro 3 delay is ruining my commute to BKC"*).

---

## 2. In-Process Daily News Refresh (NewsAPI)

### Current Implementation & Enhancements:
1. **Automatic Refresh Cycle**:
   - `bin/server.rs` runs a background `tokio` task every $N$ hours (configurable via `NEWS_REFRESH_HOURS`, default 6h).
   - If `NEWS_API_KEY` is present in `.env`, it issues queries to NewsAPI for each city (`"Mumbai"`, `"Delhi"`, `"Kolkata"`, `"Bangalore"`, `"Jaipur"`).
   - Saved into `data/news/<slug>.json`.

2. **RAG Integration Hook**:
   - On each news refresh, the RAG index automatically re-indexes the new articles into memory.
   - The served knowledge clock advances to today's date (`YYYY-MM-DD`).

---

## 3. Implementation Steps

1. **Create `crates/sim-core/src/rag.rs`**:
   - Struct `RagIndex` with document tokenization and TF-IDF / BM25 scoring.
   - `retrieve(query: &str, top_k: usize) -> Vec<Article>` method.
2. **Wire RAG into Prediction Engine (`crates/sim-core/src/predict.rs`)**:
   - Replace standard `news::prompt_block` with `rag_index.retrieve_context(question)`.
3. **Wire RAG into LLM Thought Bubble / Chatter Endpoint (`crates/sim-core/src/api.rs`)**:
   - Ground resident thought generation using neighborhood-specific retrieved context.
4. **Test & Verify**:
   - Test retrieval accuracy against city policy queries.
   - Verify NewsAPI daily refresh updates the index without restarting the server.
