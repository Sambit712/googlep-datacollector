# Vague-Memory Research — V0 Reddit Data Collector

A resilient research data-retrieval system built for the Google Photos vague-memory retrieval project. The system searches Reddit for user conversations and troubleshooting threads where people describe struggling to locate old photos, videos, screenshots, or documents, and organizes those conversations into a structured, deduplicated dataset.

---

## Key Features

- **Dual-Mode Reddit Retrieval**:
  - **Keyless Public RSS Backend** (`keyless_rss`): Works out-of-the-box with zero Reddit API credentials using public Reddit Atom feeds. Features automatic rate-limit backoff that detects and respects Reddit's `x-ratelimit-reset` / `Retry-After` headers.
  - **Authenticated PRAW Backend** (`praw`): Activates automatically when Reddit OAuth credentials (`REDDIT_CLIENT_ID` and `REDDIT_CLIENT_SECRET`) are provided in `.env`.
- **Intelligent Query Engine**: Computes Cartesian products of queries and target subreddits, or performs global Reddit searches if no subreddits are specified.
- **Robust Deduplication Layer**: Filters duplicate posts by Reddit ID using an in-memory set backed by a persistent disk index (`seen_ids.json`) across runs.
- **Dual Storage Layer**: Exports structured datasets to metadata-enriched JSON (`data/output/posts.json`) and spreadsheet-ready CSV (`data/output/posts.csv`).
- **Groq AI Client (V1 Preparation)**: Pre-configured Groq SDK integration with API key validation, model health check, and extensible method stubs for downstream semantic extraction in V1.
- **Automated Logging**: Configurable console and file loggers with execution timestamps, task metrics, and rate limit telemetry.

---

## Quick Start

### 1. Prerequisites

- Python 3.10+ (tested on Python 3.11)
- Git

### 2. Installation

1. Clone the repository:
   ```bash
   git clone <repo-url>
   cd "New folder (4)"
   ```

2. Create and activate a Python virtual environment:
   ```bash
   # Windows PowerShell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1

   # macOS / Linux
   python3 -m venv .venv
   source .venv/bin/activate
   ```

3. Install required dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Configure environment variables:
   Copy the example `.env.example` file to `.env`:
   ```bash
   cp .env.example .env
   ```
   Edit `.env` to provide your settings:
   ```env
   # Reddit API Credentials (optional - Keyless RSS mode runs if left blank)
   REDDIT_CLIENT_ID=
   REDDIT_CLIENT_SECRET=
   REDDIT_USER_AGENT=vague-memory-research/0.1 (non-commercial research)

   # Groq API Key (for V1 analysis & V0 health check)
   GROQ_API_KEY=your_groq_api_key_here
   ```

### 3. Running the Pipeline

Run the pipeline using the default configuration:
```bash
python -m src.main
```

Or specify a custom configuration file:
```bash
python -m src.main --config config/queries_test.yaml
```

---

## Configuration

All runtime behavior is controlled via `config/queries.yaml` with environment variable substitution:

```yaml
reddit:
  client_id: "${REDDIT_CLIENT_ID}"
  client_secret: "${REDDIT_CLIENT_SECRET}"
  user_agent: "${REDDIT_USER_AGENT}"

search:
  subreddits:
    - "googlephotos"
    - "photography"
    - "techsupport"
    - "Android"
    - "iphone"
  queries:
    - "can't find old photo"
    - "looking for an old screenshot"
    - "remember a photo but can't find it"
    - "can't remember when I took a photo"
    - "lost photo in gallery"
    - "trying to find a picture I took"
  sort: "relevance"                  # relevance | hot | top | new
  time_filter: "all"                 # all | year | month | week | day | hour
  limit_per_query: 25                # max results per search task

pipeline:
  deduplicate_by: "id"
  output_format: "both"              # json | csv | both
  output_dir: "data/output"
  request_delay_seconds: 2.0         # delay between queries to respect rate limits

groq:
  api_key: "${GROQ_API_KEY}"
  model: "llama-3.3-70b-versatile"
  enabled: false                     # Set to true to execute Groq health check

logging:
  level: "INFO"
  log_file: "logs/run.log"
```

---

## Output Formats & Schemas

### 1. JSON Output (`data/output/posts.json`)

Includes a run metadata header and a list of full `PostRecord` entries:

```json
{
  "metadata": {
    "generated_at": "2026-09-17T15:11:59Z",
    "run_started_at": "2026-09-17T15:10:25Z",
    "total_posts": 10,
    "queries_used": 2,
    "duplicates_skipped": 0,
    "tasks_completed": 2,
    "tasks_failed": 0,
    "reddit_mode": "keyless_rss"
  },
  "posts": [
    {
      "post_id": "t3_itotgx",
      "title": "Lost ? Can't find my google photos from my old Note 8",
      "selftext": "I crushed my phone (note 8) and couldn't retrieve data off the phone...",
      "author": "annilenox",
      "subreddit": "googlephotos",
      "created_utc": "2020-09-16T04:29:49Z",
      "collected_at": "2026-09-17T15:10:59Z",
      "score": 0,
      "num_comments": 0,
      "permalink": "https://reddit.com/r/googlephotos/comments/itotgx/lost_cant_find_my_google_photos_from_my_old_note_8/",
      "search_query": "can't find old photo",
      "top_comments": []
    }
  ]
}
```

### 2. CSV Output (`data/output/posts.csv`)

A flat tabular export suitable for spreadsheet tools (Excel, Google Sheets, Pandas). Selftext is truncated to 500 characters with an ellipsis (`...`), and top comments are concatenated with ` ||| `.

| Column | Description |
|---|---|
| `post_id` | Unique post fullname (e.g. `t3_abc123`) |
| `title` | Full post title |
| `selftext` | Post body (truncated to 500 chars in CSV) |
| `author` | Reddit username (or `[deleted]`) |
| `subreddit` | Subreddit name |
| `created_utc` | ISO-8601 creation timestamp |
| `score` | Post score / upvotes |
| `num_comments`| Number of comments |
| `permalink` | Canonical URL to the post |
| `search_query`| Query string that surfaced the post |
| `collected_at`| ISO-8601 retrieval timestamp |
| `top_comments`| Top-level comments joined by ` \|\|\| ` |

### 3. Deduplication Index (`data/output/seen_ids.json`)

Persistent array of post IDs previously fetched and processed, preventing duplicate records across runs.

---

## Groq — V1 Preparation

The Groq client wrapper is located at `src/groq_client.py`.
- Configure `GROQ_API_KEY` in `.env`.
- Set `groq.enabled: true` in `config/queries.yaml` to run a health check at the start of the pipeline.
- Exposes stubbed methods (`analyze_post`, `classify_memory_type`, `extract_memory_cues`) ready for V1 prompt engineering.

---

## Testing & Validation

The test suite contains 55 unit and edge case tests verifying all pipeline components:

```bash
# Run the complete test suite
pytest tests/ -v --tb=short
```

### Test Breakdown

| Test Suite | Tests | Covers |
|---|---|---|
| `tests/test_config_loader.py` | 10 | YAML parsing, env substitution, mode detection, validation |
| `tests/test_reddit_client.py` | 7 | Keyless RSS parsing, 429 backoff, PRAW client |
| `tests/test_collector.py` | 10 | Submission mapping, comment extraction, ISO-8601 formatting |
| `tests/test_deduplicator.py` | 7 | In-memory filtering, cross-batch dedup, persistent index |
| `tests/test_structurer.py` | 11 | JSON formatting, CSV export, column truncation |
| `tests/test_groq_client.py` | 4 | Client initialization, model configuration, health check |
| `tests/test_query_engine.py` | 2 | Cartesian product calculation, global search fallback |
| `tests/test_edge_cases.py` | 4 | Empty queries, Unicode/emoji preservation, corrupted index |
| **Total** | **55** | **100% Passing** |

### Output Validation Script

Verify generated output against the formal validation checklist:
```bash
python scripts/validate_phase8.py
```

---

## Project Structure

```
project-root/
├── config/
│   ├── queries.yaml          # Primary search configuration
│   └── queries_test.yaml     # Reduced test configuration
├── data/
│   └── output/
│       ├── posts.json        # Output JSON dataset
│       ├── posts.csv         # Output CSV dataset
│       └── seen_ids.json     # Persistent deduplication index
├── Docs/
│   ├── problem-statement.txt # Original research requirements
│   ├── context.md            # Domain context & research objectives
│   ├── architecture.md       # Technical architecture specification
│   └── implementation.md     # Phase-by-phase implementation plan
├── logs/
│   └── run.log               # Pipeline run logs
├── scripts/
│   └── validate_phase8.py    # Schema & output validation utility
├── src/
│   ├── __init__.py           # Package definition
│   ├── collector.py          # Post normalization & comment collector
│   ├── config_loader.py      # Config loading & validation
│   ├── deduplicator.py       # Deduplication layer
│   ├── groq_client.py        # Groq API client wrapper
│   ├── logger_setup.py       # Logging configuration
│   ├── main.py               # Pipeline orchestrator
│   ├── models.py             # Data models (PostRecord)
│   ├── query_engine.py       # Query generation engine
│   ├── reddit_client.py      # Dual-mode Reddit client
│   └── structurer.py         # JSON and CSV storage structurer
├── tests/                    # 55 automated pytest unit & edge case tests
├── .env.example              # Environment variables template
├── .gitignore                # Git exclusions
├── README.md                 # Project documentation
└── requirements.txt          # Python dependencies
```

---

## Project Documentation

- [Problem Statement](Docs/problem-statement.txt)
- [Context](Docs/context.md)
- [Architecture](Docs/architecture.md)
- [Implementation Plan](Docs/implementation.md)
