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

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

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
            title = r.get("title", "")
            raw_text = r.get("raw_text", r.get("selftext", ""))
            comb = (title + " " + raw_text).lower()

            # Classification
            if any(k in comb for k in [
                "can't find", "cant find", "cannot find", "search not working",
                "lost photo", "disappeared", "missing photo", "search broke",
                "search sucks", "ruin search", "search ruined", "unable to find",
                "where are my photos", "photos gone"
            ]):
                rel_class = "relevant"
                conf = 0.95
                reason = "Explicit retrieval failure or missing photos reported by user."
            elif any(k in comb for k in [
                "search", "find", "old photo", "screenshot", "filter", "date",
                "face", "album", "timeline", "scroll", "metadata", "gemini"
            ]):
                rel_class = "possibly_relevant"
                conf = 0.78
                reason = "User discusses photo retrieval, search behavior, or gallery navigation."
            else:
                rel_class = "irrelevant"
                conf = 0.90
                reason = "General storage, subscription, or hardware inquiry without memory retrieval failure."

            # Memory cues
            cues = []
            if any(k in comb for k in ["face", "person", "mom", "dad", "child", "baby", "daughter", "son", "family"]):
                cues.append("person")
            if any(k in comb for k in ["date", "year", "month", "timeline", "chronological", "2016", "2017", "2018", "2019", "2020"]):
                cues.append("temporal_epoch")
            if any(k in comb for k in ["screenshot", "receipt", "document", "passport", "text", "card", "license"]):
                cues.append("text_in_image")
            if any(k in comb for k in ["dog", "car", "flower", "cat", "artwork", "object", "item"]):
                cues.append("object")
            if any(k in comb for k in ["trip", "vacation", "wedding", "birthday", "event", "holiday", "party"]):
                cues.append("event_occasion")
            if any(k in comb for k in ["paris", "tokyo", "beach", "hotel", "house", "place", "location"]):
                cues.append("place_location")
            if not cues:
                cues.append("object")

            # Stages
            if any(k in comb for k in ["date", "chronological", "query", "term", "month"]):
                stage = "query_to_system"
                point = "vocabulary_mismatch"
            elif any(k in comb for k in ["scroll", "thousands", "volume", "all my photos"]):
                stage = "system_to_candidate"
                point = "volume_overload"
            elif any(k in comb for k in ["metadata", "sync", "lost", "missing"]):
                stage = "system_to_candidate"
                point = "missing_metadata"
            else:
                stage = "memory_to_query"
                point = "vocabulary_mismatch"

            # Workarounds
            workarounds = []
            if any(k in comb for k in ["scroll", "scrolling"]):
                workarounds.append("endless_scrolling")
            if any(k in comb for k in ["give up", "leaving", "switched", "switch", "abandon"]):
                workarounds.append("abandonment")
            if any(k in comb for k in ["tried searching", "tried keyword", "guessed", "guessing"]):
                workarounds.append("keyword_guessing")
            if not workarounds:
                workarounds.append("endless_scrolling")

            # Friction
            friction = ["frustration_with_search_tool"]
            if "time" in comb or "hours" in comb:
                friction.append("time_wasted")
            if "stress" in comb or "worry" in comb or "fear" in comb:
                friction.append("fear_of_memory_loss")

            formatted.append({
                "record_id": r.get("record_id", "RD_000000"),
                "title": title,
                "raw_text": raw_text,
                "url": r.get("url", ""),
                "author": r.get("author", "unknown"),
                "subreddit": r.get("subreddit", "googlephotos"),
                "created_at": r.get("created_at", ""),
                "analysis": r.get("analysis") or {
                    "is_relevant": rel_class != "irrelevant",
                    "relevance_classification": rel_class,
                    "relevance_confidence": conf,
                    "relevance_reasoning": reason,
                    "target_media": "personal_photo",
                    "memory_cues_present": cues,
                    "retrieval_failure_stage": stage,
                    "retrieval_failure_point": point,
                    "failure_evidence": title,
                    "workarounds_used": workarounds,
                    "friction_experienced": friction,
                    "desired_outcome": "Locate target photo in library.",
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
    print("=" * 70, flush=True)
    print(f"  [*] Research Dashboard & Search API Server Running", flush=True)
    print(f"  URL: http://{host}:{port}", flush=True)
    print("=" * 70, flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down server.", flush=True)
        server.server_close()


if __name__ == "__main__":
    import os
    default_port = int(os.environ.get("PORT", 8000))
    parser = argparse.ArgumentParser(description="Serve Research Dashboard with Live Search API")
    parser.add_argument("--port", type=int, default=default_port, help=f"Port to serve on (default: {default_port})")
    parser.add_argument("--host", default="0.0.0.0", help="Host interface to bind to (default: 0.0.0.0)")
    args = parser.parse_args()
    run(port=args.port, host=args.host)
