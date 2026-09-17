# Google Photos Vague-Memory Research — V0 Data Retriever

The **evidence-collection layer** for the Google Photos research project. It systematically searches public Reddit conversations where users describe struggling to locate old photos, videos, screenshots, or documents because they lack precise retrieval cues (such as exact date, location, folder name, or event details), and organizes those findings into a structured, untruncated evidence dataset.

> **Scope Notice (V0 Boundary):**
> V0 is strictly an **evidence-collection and organization layer**. It does **not** perform AI categorization, embeddings, RAG, clustering, vector searches, or product recommendations. Those capabilities are deferred to downstream V1 modules.

---

## Key Features

1. **Dual Query Strategy (Configurable)**:
   - **Product-Specific**: Targets explicit Google Photos search failures and feature friction (e.g. `"Google Photos search"`, `"Google Photos can't find photo"`, `"Google Photos screenshot search"`).
   - **Behavior-Specific**: Targets human memory lapses and visual-search habits across devices (e.g. `"can't find old photo"`, `"remember a photo but can't find it"`, `"scrolling through photos to find"`).
2. **Subreddit Community Tiering**:
   - **Primary**: `r/googlephotos`, `r/GooglePixel`, `r/Android`, `r/iphone`.
   - **Discovery**: `r/photography`, `r/techsupport` (clearly tagged so Google Photos evidence remains distinct).
3. **Complete Evidence Preservation (Zero Truncation)**:
   - Preserves 100% of the raw post/comment body in `raw_text` and clean normalized text in `cleaned_text`.
   - Generates a separate `preview_text` for quick scanning without sacrificing full evidence.
4. **Stable Research IDs**:
   - Assigns traceable research identifiers (`RD_000001`, `RD_000002`, ...) that persist across runs for reproducible downstream AI analysis.
5. **Multi-Query Tracking**:
   - When a post or comment is surfaced by multiple search queries, all matching queries are accumulated into `queries_matched` rather than overwritten.
6. **Contextual Comment Collection**:
   - Top-level comments are extracted as distinct `comment` records, linked to parent post context (`parent_post_title`, `parent_post_text`).
   - Trivial non-substantive comments (e.g. `"Same here"`, `"+1"`) are automatically filtered out.
7. **Comprehensive Data-Quality Reporting**:
   - Automatically computes and logs a collection quality report with text completeness, URL validity, query yields, and subreddit distributions saved to `collection_report.json`.
8. **Sample & Dry-Run Modes**:
   - Safe, low-cost testing with `--limit N` and `--dry-run` CLI options.
9. **Research Privacy Handling**:
   - Only collects public information.
   - Built-in `anonymize_authors: true` toggle to pseudonymize usernames for ethical research presentation.

---

## V0 Architecture & Pipeline Flow

```text
Config (queries.yaml)
         ↓
    Query Engine (Cartesian product: Queries × Subreddits)
         ↓
  Reddit Client (Dual-Mode: Keyless Public RSS + Authenticated PRAW)
         ↓
Raw Post & Comment Collector (HTML Unescape, Text Normalization, RD_xxxxxx IDs)
         ↓
 Deduplicator (Source + Source_ID Unique Key, Multi-Query Accumulator)
         ↓
Storage Layer (posts.json + posts.csv — Zero Text Truncation)
         ↓
Collection Quality Reporter (collection_report.json)
```

---

## Quick Start

### 1. Prerequisites

- Python 3.10+ (tested on Python 3.11)
- Git

### 2. Setup

```bash
# Clone the repository
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

Edit `.env` (optional for Keyless mode):
```env
# Reddit Credentials (leave blank for zero-key Keyless Public mode)
REDDIT_CLIENT_ID=
REDDIT_CLIENT_SECRET=
REDDIT_USER_AGENT=vague-memory-research/0.1 (non-commercial research)

# Groq API Key (for V1 preparation)
GROQ_API_KEY=your_groq_api_key_here
```

---

## Execution Modes

### 1. Dry-Run Mode (Safe & Inexpensive Testing)
Runs searches, extracts evidence, cleans text, and reports data quality without modifying disk files:
```bash
python -m src.main --dry-run
```

### 2. Sample Mode (Limit Results per Query)
Runs a quick test with a maximum of 5 results per query:
```bash
python -m src.main --limit 5
```

### 3. Full Evidence Collection Run
Executes full collection using default `config/queries.yaml`:
```bash
python -m src.main
```

### 4. Custom Configuration File
```bash
python -m src.main --config config/queries_test.yaml --limit 2
```

---

## Configuration (`config/queries.yaml`)

```yaml
reddit:
  client_id: "${REDDIT_CLIENT_ID}"
  client_secret: "${REDDIT_CLIENT_SECRET}"
  user_agent: "${REDDIT_USER_AGENT}"

search:
  subreddits:
    primary:
      - "googlephotos"
      - "GooglePixel"
      - "Android"
      - "iphone"
    discovery:
      - "photography"
      - "techsupport"

  queries:
    product_specific:
      - "Google Photos search"
      - "Google Photos can't find photo"
      - "Google Photos old photo"
      - "Google Photos screenshot search"
      - "Google Photos search problem"
    behavior_specific:
      - "can't find old photo"
      - "looking for old photo"
      - "remember a photo but can't find it"
      - "can't remember when photo was taken"
      - "can't remember where photo was taken"
      - "find old screenshot"
      - "lost photo in camera roll"
      - "scrolling through photos to find"

  sort: "relevance"                  # relevance | hot | top | new
  time_filter: "all"                 # all | year | month | week | day | hour
  limit_per_query: 25                # max results per search task

pipeline:
  deduplicate_by: "id"
  output_format: "both"              # json | csv | both
  output_dir: "data/output"
  request_delay_seconds: 2.0         # polite delay between requests
  max_comments_per_post: 3           # top-level comments per post

privacy:
  anonymize_authors: false           # set to true to pseudonymize usernames

groq:
  api_key: "${GROQ_API_KEY}"
  model: "llama-3.3-70b-versatile"
  enabled: false                     # V0 health check toggle

logging:
  level: "INFO"
  log_file: "logs/run.log"
```

---

## Record Schema (`EvidenceRecord`)

Every record stored in `data/output/posts.json` and `data/output/posts.csv` adheres to the research schema:

| Field | Type | Description |
|---|---|---|
| `record_id` | `str` | Stable research ID (e.g. `RD_000001`) |
| `source` | `str` | Data source name (`reddit`) |
| `source_type` | `str` | Platform identifier (`reddit`) |
| `content_type` | `str` | Record type (`post` or `comment`) |
| `source_id` | `str` | Reddit fullname (e.g. `t3_abc123` or `t1_xyz456`) |
| `subreddit` | `str` | Subreddit community name |
| `subreddit_tier`| `str` | Community category (`primary` or `discovery`) |
| `title` | `str` | Post title (or parent title for comments) |
| `raw_text` | `str` | Complete, unedited source text (zero truncation) |
| `cleaned_text` | `str` | HTML-unescaped, whitespace-normalized text |
| `preview_text` | `str` | Single-line truncated preview for quick inspection |
| `author` | `str` | Username or pseudonym (`anon_xxxx`) |
| `created_at` | `str` | ISO-8601 UTC creation timestamp |
| `retrieved_at` | `str` | ISO-8601 UTC collection timestamp |
| `url` | `str` | Canonical URL to the post or comment |
| `query_used` | `str` | Primary query that surfaced this record |
| `queries_matched` | `list[str]` | All queries that matched this record across runs |
| `run_id` | `str` | Unique collection run identifier |
| `parent_id` | `str` | Parent submission ID for comments |
| `parent_post_title` | `str` | Parent post title context for comments |
| `parent_post_text` | `str` | Parent post text preview for comments |
| `score` | `int` | Net upvote score |
| `num_comments`| `int` | Total submission comment count |
| `ai_relevance` | `null` | Reserved placeholder for V1 AI analysis |
| `relevance_confidence` | `null` | Reserved placeholder for V1 AI analysis |
| `evidence_status` | `str` | Initially `"unreviewed"` for V1 workflow |

---

## Data-Quality Reporting

At the end of every collection run, `CollectionReporter` generates `data/output/collection_report.json` and prints a summary:

```text
======================================================================
V0 DATA RETRIEVER — COLLECTION QUALITY REPORT (run_20260917_154640_77dff4)
======================================================================
  Queries executed:           2
  Tasks completed:            2 (failed: 0)
  Raw results:                4
  Unique records:             2
  Duplicates removed:         2
  Posts:                      2
  Comments:                   0
  Records successfully saved: 2
  Records with missing text:  0
  Records with missing URLs:  0
  Text completeness:          100.0%
  URL completeness:           100.0%
  Duration:                   18.5s
----------------------------------------------------------------------
  Results by Subreddit:
    - r/googlephotos [primary]: 2
  Results by Query:
    - "Google Photos can't find photo": 2
======================================================================
```

---

## Privacy & Research Ethics

- **Public Data Only**: Collects only publicly accessible submissions and comments.
- **Author Anonymization**: Setting `privacy.anonymize_authors: true` replaces usernames with salted SHA-256 pseudonyms (`anon_a1b2c3d4`) to safeguard user privacy in research presentations.
- **Platform Etiquette**: Respects Reddit rate-limit headers (`x-ratelimit-reset`, `Retry-After`) with adaptive backoff and enforces polite inter-request delays.

---

## Testing

Run the automated test suite (62 tests):
```bash
pytest tests/ -v --tb=short
```

Run the output validation utility:
```bash
python scripts/validate_phase8.py
```
