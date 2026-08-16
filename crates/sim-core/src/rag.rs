//! Lightweight in-process RAG (Retrieval-Augmented Generation) index.
//! Uses BM25/TF-IDF document scoring over local city news, neighborhood contexts,
//! and policy briefs to inject hyper-relevant facts into prediction and chatter prompts.

use crate::news::CityNews;
use serde::{Deserialize, Serialize};
use std::collections::{HashMap, HashSet};

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct RagDocument {
    pub id: String,
    pub title: String,
    pub content: String,
    pub category: String,
}

#[derive(Clone, Debug, Default)]
pub struct RagIndex {
    pub city: String,
    pub docs: Vec<RagDocument>,
    /// Pre-tokenized word counts per document index.
    doc_tokens: Vec<HashMap<String, usize>>,
    /// Inverse document frequency cache for terms.
    idf: HashMap<String, f64>,
}

impl RagIndex {
    pub fn new(city: &str) -> Self {
        Self {
            city: city.to_string(),
            docs: Vec::new(),
            doc_tokens: Vec::new(),
            idf: HashMap::new(),
        }
    }

    /// Build a RagIndex from a city's news cache and default neighborhood profiles.
    pub fn from_news(city: &str, news: &CityNews) -> Self {
        let mut index = Self::new(city);

        for (i, a) in news.articles.iter().enumerate() {
            index.add_document(RagDocument {
                id: format!("{city}-news-{i}"),
                title: a.headline.clone(),
                content: format!("{}. {}", a.headline, a.summary),
                category: "news".to_string(),
            });
        }

        index.build_stats();
        index
    }

    pub fn add_document(&mut self, doc: RagDocument) {
        let tokens = tokenize(&doc.content);
        let mut counts = HashMap::new();
        for t in tokens {
            *counts.entry(t).or_insert(0) += 1;
        }
        self.doc_tokens.push(counts);
        self.docs.push(doc);
    }

    /// Recompute IDF statistics across all documents.
    pub fn build_stats(&mut self) {
        let n_docs = self.docs.len() as f64;
        if n_docs == 0.0 {
            return;
        }

        let mut doc_freq: HashMap<String, usize> = HashMap::new();
        for counts in &self.doc_tokens {
            for term in counts.keys() {
                *doc_freq.entry(term.clone()).or_insert(0) += 1;
            }
        }

        self.idf.clear();
        for (term, df) in doc_freq {
            // Standard BM25-style IDF formula
            let idf_val = ((n_docs - df as f64 + 0.5) / (df as f64 + 0.5) + 1.0).ln();
            self.idf.insert(term, idf_val.max(0.1));
        }
    }

    /// Retrieve top_k documents most relevant to the user's query string.
    pub fn retrieve(&self, query: &str, top_k: usize) -> Vec<(&RagDocument, f64)> {
        if self.docs.is_empty() {
            return Vec::new();
        }

        let query_tokens = tokenize(query);
        let mut scores: Vec<(usize, f64)> = Vec::new();

        for (idx, doc_counts) in self.doc_tokens.iter().enumerate() {
            let doc_len: usize = doc_counts.values().sum();
            if doc_len == 0 {
                continue;
            }

            let mut score = 0.0;
            for qt in &query_tokens {
                if let Some(&count) = doc_counts.get(qt) {
                    let idf = self.idf.get(qt).copied().unwrap_or(0.5);
                    // TF component with saturation limit (k1 = 1.2)
                    let tf = count as f64 / (count as f64 + 1.2);
                    score += idf * tf;
                }
            }

            if score > 0.0 {
                scores.push((idx, score));
            }
        }

        scores.sort_by(|a, b| b.1.partial_cmp(&a.1).unwrap_or(std::cmp::Ordering::Equal));
        scores.truncate(top_k);

        scores
            .into_iter()
            .map(|(idx, score)| (&self.docs[idx], score))
            .collect()
    }

    /// Format top retrieved documents into a context block ready for LLM prompts.
    pub fn retrieve_context(&self, query: &str, top_k: usize) -> String {
        let results = self.retrieve(query, top_k);
        if results.is_empty() {
            return String::new();
        }

        let mut out = String::from("Retrieved local context & recent news:\n");
        for (doc, _score) in results {
            out.push_str(&format!("- [{}] {}\n", doc.title, doc.content));
        }
        out
    }
}

/// Simple alphanumeric tokenizer that converts text to lowercased terms.
fn tokenize(text: &str) -> Vec<String> {
    let stop_words: HashSet<&str> = [
        "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for", "of", "with", "by",
        "is", "are", "was", "were", "it", "this", "that", "be", "has", "have", "had",
    ]
    .into_iter()
    .collect();

    text.to_lowercase()
        .split(|c: char| !c.is_alphanumeric())
        .filter(|s| !s.is_empty() && s.len() > 1 && !stop_words.contains(s))
        .map(|s| s.to_string())
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::news::Article;

    #[test]
    fn test_rag_retrieval() {
        let news = CityNews {
            city: "mumbai".to_string(),
            date: "2026-08-16".to_string(),
            articles: vec![
                Article {
                    headline: "Coastal Road extension opens in South Mumbai".to_string(),
                    summary: "New arterial route connects Marine Drive to Worli with reduced traffic congestion.".to_string(),
                    topic: "transit".to_string(),
                    salience: "high".to_string(),
                    url: "".to_string(),
                    date: "2026-08-16".to_string(),
                },
                Article {
                    headline: "Monsoon rainfall hits Thane and Navi Mumbai".to_string(),
                    summary: "Heavy downpour causes waterlogging on Central Line local trains.".to_string(),
                    topic: "weather".to_string(),
                    salience: "medium".to_string(),
                    url: "".to_string(),
                    date: "2026-08-16".to_string(),
                },
            ],
        };

        let index = RagIndex::from_news("mumbai", &news);
        let ctx = index.retrieve_context("coastal road traffic", 2);
        assert!(ctx.contains("Coastal Road extension"));
        assert!(!ctx.contains("Monsoon rainfall"));
    }
}
