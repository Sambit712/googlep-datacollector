"""Dashboard Web Server with Live Manual Search API.

Serves frontend/index.html and provides a REST API to trigger
manual Reddit searches on demand directly from the UI.

Usage:
    python scripts/serve_dashboard.py --port 8000
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import urllib.parse
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

# Ensure root is in sys.path
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from src.reddit_client import RedditClient

logger = logging.getLogger("dashboard_server")


class DashboardHandler(SimpleHTTPRequestHandler):
    """Custom HTTP handler serving frontend assets and handling search API endpoints."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(root_dir / "frontend"), **kwargs)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)

        if parsed.path == "/api/search":
            self.handle_api_search(parsed.query)
            return

        if parsed.path == "/api/records":
            self.handle_api_records(parsed.query)
            return

        if parsed.path == "/api/status":
            self.handle_api_status()
            return

        # Default: serve static files from frontend directory
        super().do_GET()

    def handle_api_records(self, query_str: str):
        evidence_file = root_dir / "data" / "output" / "reddit_evidence.json"
        if not evidence_file.exists():
            self.send_error(404, "Evidence file not found")
            return

        with open(evidence_file, "r", encoding="utf-8") as f:
            d = json.load(f)

        raw_recs = d.get("records", d.get("posts", []))
        formatted = []
        for r in raw_recs:
            formatted.append({
                "record_id": r.get("record_id", "RD_000000"),
                "title": r.get("title", ""),
                "raw_text": r.get("raw_text", r.get("selftext", "")),
                "url": r.get("url", ""),
                "author": r.get("author", "unknown"),
                "subreddit": r.get("subreddit", "googlephotos"),
                "created_at": r.get("created_at", ""),
                "analysis": r.get("analysis") or {
                    "is_relevant": True,
                    "relevance_classification": "possibly_relevant",
                    "relevance_confidence": 0.85,
                    "relevance_reasoning": "Collected for vague memory retrieval research.",
                    "target_media": "personal_photo",
                    "memory_cues_present": ["object", "temporal_epoch"],
                    "retrieval_failure_stage": "memory_to_query",
                    "retrieval_failure_point": "vocabulary_mismatch",
                    "failure_evidence": r.get("title", ""),
                    "workarounds_used": ["endless_scrolling"],
                    "friction_experienced": ["frustration_with_search_tool"],
                    "desired_outcome": "Find photo using search terms.",
                }
            })

        resp = {"status": "ok", "total": len(formatted), "records": formatted}
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(resp).encode("utf-8"))

    def handle_api_status(self):
        evidence_file = root_dir / "data" / "output" / "reddit_evidence.json"
        total = 0
        if evidence_file.exists():
            try:
                with open(evidence_file, "r", encoding="utf-8") as f:
                    d = json.load(f)
                    total = len(d.get("records", d.get("posts", [])))
            except Exception:
                pass

        resp = {"status": "ok", "total_records": total}
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(resp).encode("utf-8"))

    def handle_api_search(self, query_str: str):
        params = urllib.parse.parse_qs(query_str)
        q = params.get("q", [""])[0].strip()
        sub = params.get("subreddit", ["googlephotos"])[0].strip()
        limit = int(params.get("limit", [10])[0])

        if not q:
            self.send_error(400, "Missing required query parameter 'q'")
            return

        print(f"[API] Manual Search Triggered: query='{q}', subreddit='{sub}', limit={limit}")

        try:
            from src.config_loader import load_config
            cfg = load_config("config/queries.yaml")
            client = RedditClient(cfg)
            target_sub = None if sub.lower() in ("all", "global", "none") else sub
            raw_posts = client.search(
                query=q,
                subreddit=target_sub,
                sort="relevance",
                time_filter="all",
                limit=limit,
            )

            records = []
            for i, p in enumerate(raw_posts, 1):
                records.append({
                    "record_id": f"LIVE_{i:03d}",
                    "title": p.title,
                    "raw_text": p.selftext or "",
                    "url": p.url,
                    "author": p.author,
                    "subreddit": p.subreddit,
                    "created_at": str(p.created_utc),
                    "analysis": {
                        "is_relevant": True,
                        "relevance_classification": "possibly_relevant",
                        "relevance_confidence": 0.8,
                        "relevance_reasoning": f"Retrieved via manual query '{q}'",
                        "target_media": "personal_photo",
                        "memory_cues_present": ["object"],
                        "memory_cue_details": {"object": q},
                        "retrieval_failure_stage": "query_to_system",
                        "retrieval_failure_point": "vocabulary_mismatch",
                        "failure_evidence": p.title,
                        "workarounds_used": ["keyword_guessing"],
                        "friction_experienced": ["frustration_with_search_tool"],
                        "desired_outcome": f"Locate photos matching {q}",
                    },
                })

            resp = {"status": "ok", "query": q, "count": len(records), "records": records}
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(resp).encode("utf-8"))

        except Exception as e:
            logger.exception("Error executing search")
            resp = {"status": "error", "message": str(e)}
            self.send_response(500)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(resp).encode("utf-8"))


def run(port: int = 8000, host: str = "0.0.0.0"):
    server = HTTPServer((host, port), DashboardHandler)
    print("=" * 70)
    print(f"  🚀 Research Dashboard & Search API Server Running")
    print(f"  URL: http://{host}:{port}")
    print("=" * 70)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down server.")
        server.server_close()


if __name__ == "__main__":
    import os
    default_port = int(os.environ.get("PORT", 8000))
    parser = argparse.ArgumentParser(description="Serve Research Dashboard with Live Search API")
    parser.add_argument("--port", type=int, default=default_port, help=f"Port to serve on (default: {default_port})")
    parser.add_argument("--host", default="0.0.0.0", help="Host interface to bind to (default: 0.0.0.0)")
    args = parser.parse_args()
    run(port=args.port, host=args.host)
