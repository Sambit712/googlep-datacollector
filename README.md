# Vague-Memory Research — V0 Reddit Data Collector

A research data-retrieval system for the Google Photos vague-memory retrieval project. Collects Reddit conversations where users describe struggling to find old photos, videos, or screenshots.

## Quick Start

1. Clone the repo
2. Copy `.env.example` → `.env` and fill in your Reddit credentials + Groq API key
3. Create a virtual environment and install dependencies:
   ```bash
   python -m venv .venv
   .venv\Scripts\activate          # Windows
   pip install -r requirements.txt
   ```
4. Run the pipeline:
   ```bash
   python src/main.py
   ```

## Configuration

Edit `config/queries.yaml` to customise search queries, subreddits, and output settings.

## Output

- `data/output/posts.json` — Structured dataset with metadata
- `data/output/posts.csv` — Flat export for spreadsheets

## Tests

```bash
pytest tests/ -v
```

## Documentation

- [Problem Statement](Docs/problem-statement.txt)
- [Project Context](Docs/context.md)
- [Architecture](Docs/architecture.md)
- [Implementation Plan](Docs/implementation.md)
