# Google Photos Vague-Memory Research Engine (V0 Collector + V1 AI Analyzer)

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Tests Passing](https://img.shields.io/badge/tests-127%20passed-brightgreen.svg)](tests/)
[![Architecture](https://img.shields.io/badge/architecture-V0%20%2B%20V1%20End--to--End-purple.svg)](Docs/architecture.md)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

An end-to-end computational research pipeline investigating why visual photo retrieval fails when users possess episodic, perceptual, or contextual memories of photos, screenshots, or documents, but cannot translate their memory into queries that current photo search engines index.

---

## Repository Status Overview

| Research Layer | Scope & Responsibilities | Status | Output Artifacts |
|---|---|---|---|
| **V0: Evidence Collection Layer** | Multi-subreddit public Reddit collection, dual query strategies, raw text preservation (zero truncation), deduplication, stable `RD_xxxxxx` IDs. | **Complete** (381 records collected across 7 communities) | [`data/output/reddit_evidence.json`](reports/collection_report.json)<br>[`reports/collection_report.json`](reports/collection_report.json) |
| **V1: AI Research Analysis Engine** | ImmutabilityGuard loader, Groq LLM multi-task extraction (`llama-3.3-70b-versatile`), taxonomy classification, Pandas aggregation, and recurring pattern synthesis with unbroken citation traceability. | **Complete** (127 passing automated tests) | [`reports/insight_report.md`](reports/insight_report.md)<br>[`reports/insight_report.json`](reports/insight_report.json)<br>[`reports/analyzed_evidence.json`](reports/analyzed_evidence.json) |

---

## The Central Research Question

> *"Why does personal photo retrieval fail when users have vivid episodic memory of an image (objects, people, life era, text), but cannot translate that memory into terms that current search engines index?"*

---

## End-to-End Architecture & Data Flow

```text
                                 [ V0 COLLECTION LAYER ]
                      Config: config/queries.yaml (Dual query strategy)
                                            ↓
               Query Engine (Cartesian Product: Queries × Subreddit Tiers)
                                            ↓
                Reddit Client (Dual-Mode: Keyless Public RSS + PRAW)
                                            ↓
            Post & Comment Collector (HTML Unescaping, Normalization, Stable RD_xxxxxx IDs)
                                            ↓
              Deduplication Layer (Cross-run persistence, Multi-query tracking)
                                            ↓
               Storage: data/output/reddit_evidence.json & .csv (Zero Truncation)
               Reporting: reports/collection_report.json (Data completeness metrics)

                                            │
                                            ▼
                               [ V1 AI ANALYSIS ENGINE ]
               ImmutabilityGuard (Read-only V0 ingestion, SHA-256 fingerprinting)
                                            ↓
                 Research Taxonomy Configuration (config/taxonomy.yaml)
                                            ↓
             Groq AI Multi-Task Analyzer (Llama-3.3-70b with exponential fallback)
               ├── 1. Relevance Classification (is_relevant, confidence, reasoning)
               ├── 2. Target Media Identification (personal_photo, screenshot, doc)
               ├── 3. Memory Cue Extraction (object, person, text, epoch, location)
               ├── 4. Retrieval Breakdown Point (vocabulary_mismatch, missing_metadata)
               ├── 5. User Workaround Extraction (chronological_scroll, abandonment)
               └── 6. User Friction Experienced (frustration, time_wasted, panic)
                                            ↓
             Pattern Aggregator (Pandas frequency distributions & cross-tabulations)
                                            ↓
             Pattern Discovery & Citation Synthesis (PAT_001 - PAT_004 with Reddit quotes)
                                            ↓
                               [ CANONICAL RESEARCH OUTPUTS ]
         ├── reports/insight_report.md (Executive synthesis report)
         ├── reports/insight_report.json (Canonical structured findings & citations)
         ├── reports/analyzed_evidence.json (Fully enriched research schema)
         └── reports/analyzed_evidence.csv (Flattened analysis export)
```

---

## Key Synthesized Research Findings (V1)

Full executive report available at: [**`reports/insight_report.md`**](reports/insight_report.md)

### 1. The Dominant Breakdown: Vocabulary Mismatch (80.0%)
* **Finding**: 80.0% of analyzed photo retrieval breakdowns stem from **semantic and vocabulary mismatches** (`PAT_002`). Users recall perceptual attributes (*"a picture of my grandma's recipe on yellow paper"*) or emotional concepts, while current keyword search expects literal image tags or OCR matches.
* **Direct Citation**:
  > *"search any of the above and it shows thousands of photos with absolutely no relevance."*  
  > — [Record `RD_000014`](reports/insight_report.md) ([r/googlephotos](https://reddit.com/r/googlephotos/comments/1fvq7hr/why_did_they_ruin_google_photos_search/))

### 2. Chronological Fatigue & Search Abandonment (20.0%)
* **Finding**: When search fails, users fall back to manual chronological scrolling (`PAT_001`). In galleries with 10,000+ items, this causes acute cognitive fatigue and **search abandonment**.
* **Direct Citation**:
  > *"Instead of providing the results by date, it gives me results based on what it thinks is the 'relevance' of each photo. More critically, there is no option to go back to 'show results by date.'"*  
  > — [Record `RD_000021`](reports/insight_report.md) ([r/googlephotos](https://reddit.com/r/googlephotos/comments/1l1ssr7/whoa_google_photos_seriously_wtf/))

### 3. Untagged Screenshot & Document Clutter (`PAT_003`)
* **Finding**: Users treat photo libraries as external memory for screenshots and receipts, but lack OCR-aligned search terms.

### 4. Cross-Platform Metadata Loss (`PAT_004`)
* **Finding**: Cloud migrations (e.g. Google Takeout to iCloud) frequently strip EXIF timestamps, breaking timeline-based retrieval.

---

## Research Taxonomy (`config/taxonomy.yaml`)

The analysis engine categorizes human memory recall and system failure along five dimensions:

1. **Memory Cues**: `person`, `object`, `activity`, `spatial_location`, `temporal_epoch`, `visual_style`, `emotional_state`, `text_in_image`.
2. **Retrieval Failure Points**: `vocabulary_mismatch`, `missing_metadata`, `temporal_amnesia`, `search_algorithm_rigidity`, `media_clutter`, `indexing_delay`.
3. **Workarounds**: `chronological_scroll`, `keyword_guessing`, `external_timeline`, `third_party_tools`, `crowd_sourcing`, `abandonment`.
4. **Friction Types**: `frustration_with_search_tool`, `time_wasted`, `fear_of_memory_loss`, `privacy_concern`, `loss_of_trust`.
5. **Target Media**: `personal_photo`, `screenshot`, `document`, `meme`, `downloaded_image`, `video`.

---

## Dataset & Quality Metrics

Our baseline collection run yielded:
- **381 unique evidence records** across 7 subreddit communities:
  - `r/googlephotos` (62), `r/GooglePixel` (74), `r/Android` (49), `r/iphone` (49) [Primary Tier: 234]
  - `r/photography` (50), `r/techsupport` (49), `r/AskReddit` (48) [Discovery Tier: 147]
- **100% URL completeness** and **zero text truncation** (full untruncated post bodies and comment threads preserved).
- See full collection report in [`reports/collection_report.json`](reports/collection_report.json).

---

## Quick Start & Installation

### 1. Prerequisites
- Python 3.10+
- Git

### 2. Setup
```bash
git clone https://github.com/Sambit712/googlep-datacollector.git
cd googlep-datacollector

# Create and activate virtual environment
python -m venv .venv
.\.venv\Scripts\activate      # Windows PowerShell
# source .venv/bin/activate    # macOS / Linux

# Install dependencies
pip install -r requirements.txt

# Configure environment variables
cp .env.example .env
```

Edit `.env`:
```env
# Reddit Credentials (optional: runs in Keyless Public RSS mode if left blank)
REDDIT_CLIENT_ID=
REDDIT_CLIENT_SECRET=
REDDIT_USER_AGENT=vague-memory-research/1.0 (academic research)

# Groq API Key (required for V1 AI analysis)
GROQ_API_KEY=your_groq_api_key_here
```

---

## Execution Guide

The unified CLI supports three operational modes:

### 1. Run Complete Dual Pipeline (V0 Collection + V1 AI Analysis)
Collects fresh evidence from Reddit, verifies immutability, and runs Groq AI analysis:
```bash
python main.py --mode both --limit 10
```

### 2. Run V1 AI Analysis on Existing Collected Evidence
Ingests previously collected evidence from `data/output/reddit_evidence.json` and generates insight reports:
```bash
# Analyze a sample of 10 records (fast, cost-effective evaluation)
python main.py --mode analyze --sample 10

# Analyze all collected records
python main.py --mode analyze
```

### 3. Run V0 Evidence Collection Only
Executes targeted Reddit collection across configured queries and subreddits:
```bash
# Sample collection
python main.py --mode collect --limit 10

# Full collection run
python main.py --mode collect
```

### 4. Fast Dry-Run Mode
Validates configuration files, Reddit connectivity, and Groq API health without writing data:
```bash
python main.py --dry-run
```

---

## Automated Test Suite (127 Tests)

The repository includes a comprehensive automated test suite with **127 passing tests** verifying both V0 and V1 modules:

```bash
pytest tests/ -v
```

### Test Suite Structure
| Test Module | Tests | Verifies |
|---|---|---|
| `tests/test_traceability.py` | 9 | **End-to-End Traceability**: Unbroken citation chain from `insight_report.json` back to source Reddit URLs and V0 data immutability. |
| `tests/test_analyzer.py` | 11 | **Groq AI Analyzer**: Prompt construction, JSON schema extraction, model fallback, rate limit retries. |
| `tests/test_aggregator.py` | 6 | **Statistical Aggregator**: Frequency distributions, cross-tabulations, pattern citation synthesis. |
| `tests/test_insight_reporter.py` | 6 | **Insight Reporter**: Serialization of canonical JSON, flat CSV, and markdown executive reports. |
| `tests/test_evidence_loader.py` | 8 | **ImmutabilityGuard**: Read-only ingestion, SHA-256 fingerprint verification, schema validation. |
| `tests/test_taxonomy_config.py` | 10 | **Taxonomy Loader**: Schema integrity, category mappings, and fallback handling. |
| `tests/test_main_cli.py` | 10 | **Unified CLI**: Argument parsing, pipeline orchestration for `collect`, `analyze`, and `both`. |
| `tests/test_v0_enhancements.py` | 12 | **V0 Enhancements**: Multi-query tracking, contextual comments, full text preservation. |
| `tests/test_collector.py` | 10 | **Collector**: Post/comment parsing, timestamp normalization, deletion filters. |
| `tests/test_reddit_client.py` | 7 | **Reddit Client**: Keyless RSS parsing, 429 adaptive backoff, PRAW delegation. |
| `tests/test_deduplicator.py` | 7 | **Deduplication**: Persistence, cross-batch deduplication, unique ID indexing. |
| `tests/test_structurer.py` | 11 | **Storage Structurer**: Zero text truncation in CSV/JSON outputs. |
| `tests/test_config_loader.py` | 10 | **Config Loader**: Environment substitution, validation rules. |
| `tests/test_edge_cases.py` | 4 | **Edge Cases**: Unicode, emoji preservation, very long post text. |
| `tests/test_groq_client.py` | 4 | **Groq Client**: API initialization and health checks. |
| **Total** | **127** | **100% Passing** |

---

## Research Ethics & Privacy

- **Public Data Only**: Collects only publicly accessible submissions and comments from open communities.
- **Author Pseudonymization**: Built-in `privacy.anonymize_authors: true` toggle generates salted SHA-256 pseudonyms (`anon_a1b2c3d4`) to safeguard user privacy in research presentations.
- **Polite Crawling**: Enforces request delays and honors Reddit HTTP headers (`x-ratelimit-reset`, `Retry-After`).
- **Data Immutability**: Source evidence datasets are protected by `ImmutabilityGuard` to prevent AI hallucinations or pipeline mutation of raw user quotes.
