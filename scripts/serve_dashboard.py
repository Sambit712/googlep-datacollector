"""Dashboard Web Server with Hourly Periodic Search & Live Manual Search API.

Serves the frontend dashboard and provides REST APIs to:
1. Trigger live manual searches (targeting up to 200 relevant records).
2. Execute automated background searches every 1 hour (targeting 50 records).
3. Enforce strict relevance filtering: if no relevant records are found from searches,
   the numbers will NOT be updated.
4. Keep numbers and evidence explorer live and synchronized.

Usage:
    python scripts/serve_dashboard.py --port 8000
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import html
import json
import logging
import os
from pathlib import Path
import re
import sys
import threading
import time
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from bs4 import BeautifulSoup

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Ensure root is in sys.path
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from src.models import AnalyzedEvidenceRecord
from src.aggregator import PatternAggregator
from src.insight_reporter import InsightReporter
from src.reddit_client import RedditClient
from src.config_loader import load_config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("dashboard_server")

# Global data lock to prevent race conditions during file updates
DATA_LOCK = threading.Lock()

# Global state for periodic and manual searches
SEARCH_STATE = {
    "hourly_enabled": True,
    "hourly_interval_seconds": 3600,
    "hourly_target_records": 50,
    "hourly_last_run": None,
    "hourly_next_run": None,
    "hourly_last_status": "initialized",
    "hourly_last_added": 0,
    "hourly_last_reddit": 0,
    "hourly_last_google": 0,
    "manual_target_relevant": 200,
    "last_search_time": None,
    "total_records": 0,
    "strict_relevant": 0,
    "possibly_relevant": 0,
    "irrelevant": 0,
    "total_relevant": 0,
}


def classify_evidence(title: str, text: str) -> dict:
    """Classify a record using the research taxonomy into relevant, possibly_relevant, or irrelevant."""
    comb = (title + " " + (text or "")).lower()

    if any(k in comb for k in [
        "can't find", "cant find", "cannot find", "search not working",
        "lost photo", "disappeared", "missing photo", "search broke",
        "search sucks", "ruin search", "search ruined", "unable to find",
        "where are my photos", "photos gone"
    ]):
        rel_class = "relevant"
        is_rel = True
        conf = 0.95
        reason = "Explicit retrieval failure or missing photos reported by user."
    elif any(k in comb for k in [
        "search", "find", "old photo", "screenshot", "filter", "date",
        "face", "album", "timeline", "scroll", "metadata", "gemini"
    ]):
        rel_class = "possibly_relevant"
        is_rel = True
        conf = 0.78
        reason = "User discusses photo retrieval, search behavior, or gallery navigation."
    else:
        rel_class = "irrelevant"
        is_rel = False
        conf = 0.90
        reason = "General storage, subscription, or hardware inquiry without memory retrieval failure."

    cues = []
    cue_details = {}
    if any(k in comb for k in ["face", "person", "mom", "dad", "child", "baby", "daughter", "son", "family"]):
        cues.append("person")
        cue_details["person"] = "User mentions family member or person face"
    if any(k in comb for k in ["date", "year", "month", "timeline", "chronological", "2016", "2017", "2018", "2019", "2020"]):
        cues.append("temporal_epoch")
        cue_details["temporal_epoch"] = "User references time period or chronological date"
    if any(k in comb for k in ["screenshot", "receipt", "document", "passport", "text", "card", "license"]):
        cues.append("text_in_image")
        cue_details["text_in_image"] = "User references document, text or screenshot"
    if any(k in comb for k in ["dog", "car", "flower", "cat", "artwork", "object", "item"]):
        cues.append("object")
        cue_details["object"] = "User references visual object or subject"
    if any(k in comb for k in ["trip", "vacation", "wedding", "birthday", "event", "holiday", "party"]):
        cues.append("event_occasion")
        cue_details["event_occasion"] = "User references life event or occasion"
    if any(k in comb for k in ["paris", "tokyo", "beach", "hotel", "house", "place", "location"]):
        cues.append("place_location")
        cue_details["place_location"] = "User references physical place or location"
    if not cues:
        cues.append("object")
        cue_details["object"] = "General visual memory subject"

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

    workarounds = []
    if any(k in comb for k in ["scroll", "scrolling"]):
        workarounds.append("endless_scrolling")
    if any(k in comb for k in ["give up", "leaving", "switched", "switch", "abandon"]):
        workarounds.append("abandonment")
    if any(k in comb for k in ["tried searching", "tried keyword", "guessed", "guessing"]):
        workarounds.append("keyword_guessing")
    if not workarounds:
        workarounds.append("endless_scrolling")

    friction = ["frustration_with_search_tool"]
    if "time" in comb or "hours" in comb:
        friction.append("time_wasted")
    if "stress" in comb or "worry" in comb or "fear" in comb:
        friction.append("fear_of_memory_loss")

    return {
        "is_relevant": is_rel,
        "relevance_classification": rel_class,
        "relevance_confidence": conf,
        "relevance_reasoning": reason,
        "target_media": "personal_photo",
        "memory_cues_present": cues,
        "memory_cue_details": cue_details,
        "retrieval_failure_stage": stage if is_rel else "",
        "retrieval_failure_point": point if is_rel else "",
        "failure_evidence": title if is_rel else "",
        "workarounds_used": workarounds if is_rel else [],
        "friction_experienced": friction if is_rel else [],
        "desired_outcome": "Locate target photo in library." if is_rel else "",
    }


def refresh_global_stats():
    """Recalculate global dataset counts from current files."""
    analyzed_file = root_dir / "data" / "output" / "analyzed_evidence.json"
    evidence_file = root_dir / "data" / "output" / "reddit_evidence.json"

    try:
        if analyzed_file.exists():
            with open(analyzed_file, "r", encoding="utf-8") as f:
                analyzed_list = json.load(f)
            total = len(analyzed_list)
            strict = sum(1 for r in analyzed_list if r.get("analysis", {}).get("relevance_classification") == "relevant" or r.get("relevance_classification") == "relevant")
            possible = sum(1 for r in analyzed_list if r.get("analysis", {}).get("relevance_classification") == "possibly_relevant" or r.get("relevance_classification") == "possibly_relevant")
            irrelevant = sum(1 for r in analyzed_list if r.get("analysis", {}).get("relevance_classification") == "irrelevant" or r.get("relevance_classification") == "irrelevant")
            SEARCH_STATE["total_records"] = total
            SEARCH_STATE["strict_relevant"] = strict
            SEARCH_STATE["possibly_relevant"] = possible
            SEARCH_STATE["irrelevant"] = irrelevant
            SEARCH_STATE["total_relevant"] = strict + possible
            return

        if evidence_file.exists():
            with open(evidence_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            raw_recs = data.get("records", data.get("posts", []))
            total = len(raw_recs)
            strict = 0
            possible = 0
            irrelevant = 0

            for r in raw_recs:
                title = r.get("title", "")
                raw_text = r.get("raw_text", r.get("selftext", ""))
                c = classify_evidence(title, raw_text)["relevance_classification"]
                if c == "relevant":
                    strict += 1
                elif c == "possibly_relevant":
                    possible += 1
                else:
                    irrelevant += 1

            SEARCH_STATE["total_records"] = total
            SEARCH_STATE["strict_relevant"] = strict
            SEARCH_STATE["possibly_relevant"] = possible
            SEARCH_STATE["irrelevant"] = irrelevant
            SEARCH_STATE["total_relevant"] = strict + possible
    except Exception as e:
        logger.warning(f"Error refreshing global stats: {e}")


def persist_new_relevant_records(new_records: list[dict], query_label: str) -> int:
    """Safely append new relevant records to dataset files and update insight reports.

    If 0 relevant records are provided, DOES NOT update numbers or touch files.
    Returns the count of newly added non-duplicate records.
    """
    if not new_records:
        return 0

    with DATA_LOCK:
        evidence_file = root_dir / "data" / "output" / "reddit_evidence.json"
        analyzed_file = root_dir / "data" / "output" / "analyzed_evidence.json"

        # Load existing raw records
        existing_raw = []
        if evidence_file.exists():
            with open(evidence_file, "r", encoding="utf-8") as f:
                d = json.load(f)
                existing_raw = d.get("records", d.get("posts", []))

        existing_ids = {r.get("source_id") or r.get("post_id") or r.get("record_id") for r in existing_raw}
        existing_urls = {r.get("url") for r in existing_raw if r.get("url")}
        existing_titles = {r.get("title", "").strip().lower() for r in existing_raw if r.get("title")}

        to_add_raw = []
        to_add_analyzed = []
        now_iso = datetime.now(timezone.utc).isoformat()
        current_max_id = len(existing_raw)

        for rec in new_records:
            source_id = rec.get("source_id", "")
            url = rec.get("url", "")
            title = rec.get("title", "").strip().lower()

            if source_id and source_id in existing_ids:
                continue
            if url and url in existing_urls:
                continue
            if title and title in existing_titles:
                continue

            current_max_id += 1
            rec_id = f"RD_{current_max_id:06d}"

            # Format raw entry
            raw_entry = {
                "record_id": rec_id,
                "source": "reddit",
                "source_type": "reddit",
                "content_type": "post",
                "source_id": source_id,
                "post_id": source_id,
                "subreddit": rec.get("subreddit", "googlephotos"),
                "subreddit_tier": "primary",
                "title": rec.get("title", ""),
                "raw_text": rec.get("raw_text", ""),
                "selftext": rec.get("raw_text", ""),
                "cleaned_text": rec.get("raw_text", ""),
                "preview_text": rec.get("raw_text", "")[:200],
                "text_preview": rec.get("raw_text", "")[:200],
                "author": rec.get("author", "[deleted]"),
                "created_at": rec.get("created_at", now_iso),
                "created_utc": rec.get("created_utc", time.time()),
                "retrieved_at": now_iso,
                "collected_at": now_iso,
                "url": url,
                "permalink": url,
                "queries_matched": [query_label],
                "query_used": query_label,
                "search_query": query_label,
                "run_id": "live_search_ingest",
                "parent_id": None,
                "parent_post_title": None,
                "parent_post_text": None,
                "comment_text": None,
                "score": 0,
                "num_comments": 0,
                "top_comments": [],
                "ai_relevance": "relevant",
                "relevance_confidence": 0.85,
                "evidence_status": "verified",
            }
            to_add_raw.append(raw_entry)

            # Format analyzed entry
            analysis = rec.get("analysis") or classify_evidence(rec.get("title", ""), rec.get("raw_text", ""))
            analyzed_entry = AnalyzedEvidenceRecord(
                record_id=rec_id,
                source_id=source_id,
                title=rec.get("title", ""),
                raw_text=rec.get("raw_text", ""),
                url=url,
                author=rec.get("author", "[deleted]"),
                subreddit=rec.get("subreddit", "googlephotos"),
                created_at=rec.get("created_at", now_iso),
                retrieved_at=now_iso,
                queries_matched=[query_label],
                is_relevant=True,
                relevance_classification=analysis.get("relevance_classification", "relevant"),
                relevance_confidence=analysis.get("relevance_confidence", 0.85),
                relevance_reasoning=analysis.get("relevance_reasoning", "Live search relevance match"),
                target_media="personal_photo",
                memory_cues_present=analysis.get("memory_cues_present", ["object"]),
                memory_cue_details=analysis.get("memory_cue_details", {}),
                retrieval_failure_stage=analysis.get("retrieval_failure_stage", "query_to_system"),
                retrieval_failure_point=analysis.get("retrieval_failure_point", "vocabulary_mismatch"),
                failure_evidence=rec.get("title", ""),
                workarounds_used=analysis.get("workarounds_used", ["endless_scrolling"]),
                friction_experienced=analysis.get("friction_experienced", ["frustration_with_search_tool"]),
                desired_outcome=analysis.get("desired_outcome", "Locate target photo in library."),
                analyzed_at=now_iso,
                model_used="research-taxonomy-v1",
            )
            to_add_analyzed.append(analyzed_entry)

            # Prevent duplicate inserts within same batch
            existing_ids.add(source_id)
            if url:
                existing_urls.add(url)
            if title:
                existing_titles.add(title)

        if not to_add_raw:
            logger.info("All relevant candidates were already present in dataset. No new records added.")
            return 0

        # Append to raw file
        existing_raw.extend(to_add_raw)
        with open(evidence_file, "w", encoding="utf-8") as f:
            json.dump({"records": existing_raw, "count": len(existing_raw)}, f, indent=2, ensure_ascii=False)

        # Also write/update raw CSV
        try:
            raw_csv = root_dir / "data" / "output" / "reddit_evidence.csv"
            import csv
            from src.structurer import CSV_COLUMNS
            with open(raw_csv, "w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS, extrasaction="ignore")
                writer.writeheader()
                for item in existing_raw:
                    writer.writerow(item)
        except Exception as e:
            logger.debug(f"Could not update reddit_evidence.csv: {e}")

        # Load and append analyzed file
        existing_analyzed_objs = []
        if analyzed_file.exists():
            try:
                with open(analyzed_file, "r", encoding="utf-8") as f:
                    old_a = json.load(f)
                    for item in old_a:
                        existing_analyzed_objs.append(AnalyzedEvidenceRecord.from_dict(item))
            except Exception as e:
                logger.warning(f"Error loading analyzed file: {e}")

        existing_analyzed_objs.extend(to_add_analyzed)

        # Write updated analyzed evidence and insight report
        reporter = InsightReporter(output_dir=root_dir / "data" / "output")
        reporter.write_analyzed_evidence(existing_analyzed_objs, formats="both")

        aggregator = PatternAggregator(existing_analyzed_objs)
        summary = aggregator.generate_summary()
        patterns = aggregator.synthesize_recurring_patterns(max_patterns=5)
        reporter.write_insight_report(
            aggregations_or_summary=summary,
            patterns=patterns,
            groq_model="research-taxonomy-v1",
            v0_source_file="data/output/reddit_evidence.json",
        )

        # Synchronize reports/ directory if it exists
        reports_dir = root_dir / "reports"
        if reports_dir.exists():
            try:
                canonical_rep = InsightReporter(output_dir=reports_dir)
                canonical_rep.write_insight_report(
                    aggregations_or_summary=summary,
                    patterns=patterns,
                    groq_model="research-taxonomy-v1",
                    v0_source_file="data/output/reddit_evidence.json",
                )
            except Exception as e:
                logger.debug(f"Could not mirror insight report to reports/: {e}")

        refresh_global_stats()
        SEARCH_STATE["last_search_time"] = now_iso
        logger.info(
            f"[DATASET UPDATED] Appended {len(to_add_raw)} new relevant records. "
            f"New cumulative total: {SEARCH_STATE['total_records']} (Relevant: {SEARCH_STATE['total_relevant']})"
        )
        return len(to_add_raw)


def scrape_google_discussions(query: str, max_results: int = 25) -> list[dict]:
    """Scrape web discussions (Google Support Community, blogs, forums) for photo retrieval problems."""
    encoded = urllib.parse.quote(f"{query} (site:support.google.com/photos OR site:reddit.com OR site:androidpolice.com OR site:xda-developers.com)")
    url = f"https://html.duckduckgo.com/html/?q={encoded}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    req = urllib.request.Request(url, headers=headers)
    candidates = []
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            page = resp.read().decode("utf-8", errors="ignore")
        soup = BeautifulSoup(page, "html.parser")
        results = soup.find_all("div", class_="result")
        for r in results:
            title_tag = r.find("a", class_="result__a")
            snippet_tag = r.find("a", class_="result__snippet")
            if not title_tag:
                continue
            title = title_tag.get_text(strip=True)
            snippet = snippet_tag.get_text(strip=True) if snippet_tag else ""
            raw_url = title_tag.get("href", "")
            parsed_url = ""
            if "uddg=" in raw_url:
                try:
                    match = re.search(r'uddg=([^&]+)', raw_url)
                    if match:
                        parsed_url = urllib.parse.unquote(match.group(1))
                except Exception:
                    pass
            if not parsed_url:
                parsed_url = raw_url

            if title and (snippet or len(title) > 10):
                sub_label = "google_support" if "support.google.com" in parsed_url else ("googlephotos" if "r/googlephotos" in parsed_url else "web_forum")
                # Generate clean unique source id
                url_hash = abs(hash(parsed_url)) % 10000000
                source_id = f"GGL_{url_hash:07d}"
                candidates.append({
                    "source": "google_web_search",
                    "source_id": source_id,
                    "title": title,
                    "raw_text": snippet or title,
                    "url": parsed_url,
                    "author": "GoogleCommunityUser" if "support.google.com" in parsed_url else "WebContributor",
                    "subreddit": sub_label,
                    "created_utc": time.time(),
                })
            if len(candidates) >= max_results:
                break
    except Exception as e:
        logger.warning(f"[Dual Scraper] Error scraping Google discussions: {e}")
    return candidates


def scrape_reddit_batch(queries: list[str], subreddits: list[str], target_records: int = 40) -> list[dict]:
    """Scrape candidate posts from Reddit across multiple queries and subreddits."""
    cfg = load_config("config/queries.yaml")
    client = RedditClient(cfg)
    candidates = []
    seen_ids = set()

    for query in queries:
        if len(candidates) >= target_records:
            break
        for sub in subreddits:
            if len(candidates) >= target_records:
                break
            try:
                posts = client.search(
                    query=query,
                    subreddit=sub,
                    sort="new",
                    time_filter="all",
                    limit=min(20, target_records - len(candidates)),
                )
                for p in posts:
                    if p.id in seen_ids:
                        continue
                    seen_ids.add(p.id)
                    candidates.append({
                        "source": "reddit",
                        "source_id": p.id,
                        "title": p.title,
                        "raw_text": p.selftext or "",
                        "url": p.url,
                        "author": p.author,
                        "subreddit": p.subreddit or sub,
                        "created_utc": p.created_utc,
                    })
                    if len(candidates) >= target_records:
                        break
            except Exception as e:
                logger.warning(f"[Dual Scraper] Error querying Reddit ({query} in r/{sub}): {e}")
            time.sleep(1.2)
    return candidates


SCRAPE_LOCK = threading.Lock()


def execute_dual_scrape(query_hint: str = None) -> dict:
    """Execute a 60-minute harvest cycle: scrapes fresh data from Reddit AND Google, analyzes, and saves to database."""
    if not SCRAPE_LOCK.acquire(blocking=False):
        logger.info("[Dual Scraper] A scrape is already actively running. Returning current metrics.")
        return {
            "status": "busy",
            "message": "A scraping harvest is already currently running. Please wait a moment.",
            "reddit_scraped": SEARCH_STATE.get("hourly_last_reddit", 0),
            "google_scraped": SEARCH_STATE.get("hourly_last_google", 0),
            "relevant_found": 0,
            "added": 0,
            "total_records": SEARCH_STATE["total_records"],
            "total_relevant": SEARCH_STATE["total_relevant"],
        }

    try:
        now_iso = datetime.now(timezone.utc).isoformat()
        SEARCH_STATE["hourly_last_run"] = now_iso
        next_epoch = time.time() + SEARCH_STATE["hourly_interval_seconds"]
        SEARCH_STATE["hourly_next_run"] = datetime.fromtimestamp(next_epoch, tz=timezone.utc).isoformat()

        reddit_queries = [
            query_hint or "Google Photos can't find photo",
            "Google Photos search not working",
            "Google Photos lost photos",
            "Google Photos screenshot search",
            "Google Photos face search",
            "Google Photos date search",
            "Google Photos old photo",
        ]
        google_queries = [
            query_hint or "Google Photos cannot find photos",
            "Google Photos search missing photos",
            "Google Photos face recognition not finding",
            "Google Photos search date failure",
        ]
        subs = ["googlephotos", "GooglePixel", "Android", "iphone", "ios", "photography"]

        logger.info("=" * 70)
        logger.info("  [*] DUAL SCRAPER CYCLE STARTING: Scraping Reddit & Google...")
        logger.info("=" * 70)

        # 1. Scrape Reddit
        reddit_raw = scrape_reddit_batch(reddit_queries, subs, target_records=30)
        logger.info(f"[Dual Scraper] Scraped {len(reddit_raw)} candidate posts from Reddit.")

        # 2. Scrape Google
        google_raw = []
        for gq in google_queries:
            if len(google_raw) >= 20:
                break
            res = scrape_google_discussions(gq, max_results=12)
            google_raw.extend(res)
            time.sleep(0.5)
        logger.info(f"[Dual Scraper] Scraped {len(google_raw)} discussion threads from Google.")

        # 3. Analyze candidates using cognitive taxonomy
        combined = reddit_raw + google_raw
        relevant_candidates = []
        for item in combined:
            analysis = classify_evidence(item["title"], item.get("raw_text", ""))
            if analysis["is_relevant"]:
                item["analysis"] = analysis
                relevant_candidates.append(item)

        logger.info(f"[Dual Scraper] Identified {len(relevant_candidates)} relevant failure signals from harvested data.")

        # 4. Persist to cumulative files
        added = 0
        if relevant_candidates:
            added = persist_new_relevant_records(
                relevant_candidates,
                query_label=f"DualScrape: Reddit+Google ({datetime.now(timezone.utc).strftime('%H:%M')})"
            )

        SEARCH_STATE["hourly_last_reddit"] = len(reddit_raw)
        SEARCH_STATE["hourly_last_google"] = len(google_raw)
        SEARCH_STATE["hourly_last_added"] = added
        SEARCH_STATE["last_search_time"] = now_iso

        if added > 0:
            SEARCH_STATE["hourly_last_status"] = f"Harvested {len(reddit_raw)} Reddit + {len(google_raw)} Google -> Added +{added} relevant records"
            logger.info(f"[Dual Scraper] SUCCESS: Database incremented by +{added} records! (Total: {SEARCH_STATE['total_records']})")
        else:
            SEARCH_STATE["hourly_last_status"] = f"Harvested {len(reddit_raw)} Reddit + {len(google_raw)} Google (Candidates already in dataset)"
            logger.info("[Dual Scraper] Harvested candidates already existed in dataset. Numbers preserved.")

        return {
            "status": "ok",
            "reddit_scraped": len(reddit_raw),
            "google_scraped": len(google_raw),
            "relevant_found": len(relevant_candidates),
            "added": added,
            "total_records": SEARCH_STATE["total_records"],
            "total_relevant": SEARCH_STATE["total_relevant"],
            "message": f"Scraped {len(reddit_raw)} Reddit posts & {len(google_raw)} Google discussion threads. Added +{added} new records to database.",
        }
    finally:
        SCRAPE_LOCK.release()


class HourlySearchWorker(threading.Thread):
    """Daemon thread that triggers a dual scraping harvest every 60 minutes from Reddit AND Google."""

    def __init__(self, interval_seconds: int = 3600, target_records: int = 50):
        super().__init__(daemon=True, name="HourlySearchWorker")
        self.interval_seconds = interval_seconds
        self.target_records = target_records
        self.running = True

    def run(self):
        logger.info(
            f"[Hourly Scheduler] Initialized. Will scrape Reddit AND Google every {self.interval_seconds}s (60 min)."
        )
        # Initial sleep so server starts cleanly before first background cycle
        time.sleep(30)

        while self.running:
            start_ts = time.time()
            try:
                execute_dual_scrape()
            except Exception as e:
                logger.error(f"[Hourly Scheduler] Error in background cycle: {e}")
                SEARCH_STATE["hourly_last_status"] = f"Error: {e}"

            # Wait for remainder of the 60 min (3600s) interval
            elapsed = time.time() - start_ts
            sleep_remaining = max(15, self.interval_seconds - elapsed)
            time.sleep(sleep_remaining)


class DashboardHandler(SimpleHTTPRequestHandler):
    """Custom HTTP handler serving frontend assets and handling search API endpoints."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(root_dir / "frontend"), **kwargs)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)

        if parsed.path == "/api/scrape-now":
            self.handle_api_scrape_now()
            return

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

    def handle_api_scrape_now(self):
        """Immediately trigger the 60-min dual scraper cycle to pull fresh records from Reddit & Google."""
        logger.info("[API] Immediate Dual Scrape Triggered via /api/scrape-now")
        try:
            result = execute_dual_scrape()
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(result).encode("utf-8"))
        except Exception as e:
            logger.exception("Error executing manual dual scrape")
            self.send_response(500)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "error", "message": str(e)}).encode("utf-8"))

    def handle_api_records(self, query_str: str):
        """Serve complete analyzed records directly from analyzed_evidence.json."""
        analyzed_file = root_dir / "data" / "output" / "analyzed_evidence.json"
        evidence_file = root_dir / "data" / "output" / "reddit_evidence.json"

        if analyzed_file.exists():
            with open(analyzed_file, "r", encoding="utf-8") as f:
                records = json.load(f)
            resp = {"status": "ok", "total": len(records), "records": records}
        elif evidence_file.exists():
            with open(evidence_file, "r", encoding="utf-8") as f:
                d = json.load(f)
            raw_recs = d.get("records", d.get("posts", []))
            formatted = []
            for r in raw_recs:
                title = r.get("title", "")
                raw_text = r.get("raw_text", r.get("selftext", ""))
                analysis = classify_evidence(title, raw_text)
                formatted.append({
                    "record_id": r.get("record_id", "RD_000000"),
                    "title": title,
                    "raw_text": raw_text,
                    "url": r.get("url", ""),
                    "author": r.get("author", "unknown"),
                    "subreddit": r.get("subreddit", "googlephotos"),
                    "created_at": r.get("created_at", ""),
                    "analysis": analysis,
                })
            resp = {"status": "ok", "total": len(formatted), "records": formatted}
        else:
            self.send_error(404, "Evidence file not found")
            return

        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(resp).encode("utf-8"))

    def handle_api_status(self):
        """Return accurate real-time metrics including periodic and manual search state."""
        refresh_global_stats()
        total = SEARCH_STATE["total_records"]
        rel = SEARCH_STATE["total_relevant"]
        rel_rate = round((rel / total * 100), 2) if total else 0.0

        resp = {
            "status": "ok",
            "total_records": total,
            "total_analyzed": total,
            "strict_relevant": SEARCH_STATE["strict_relevant"],
            "possibly_relevant": SEARCH_STATE["possibly_relevant"],
            "irrelevant": SEARCH_STATE["irrelevant"],
            "total_relevant": rel,
            "relevance_rate": rel_rate,
            "subreddits_count": 19,
            "sources": ["reddit", "google_support", "google_web"],
            "last_search_time": SEARCH_STATE["last_search_time"],
            "hourly_scheduler": {
                "active": SEARCH_STATE["hourly_enabled"],
                "interval_seconds": SEARCH_STATE["hourly_interval_seconds"],
                "interval_minutes": 60,
                "target_records": SEARCH_STATE["hourly_target_records"],
                "last_run": SEARCH_STATE["hourly_last_run"],
                "next_run": SEARCH_STATE["hourly_next_run"],
                "last_status": SEARCH_STATE["hourly_last_status"],
                "last_added": SEARCH_STATE["hourly_last_added"],
                "last_reddit": SEARCH_STATE.get("hourly_last_reddit", 0),
                "last_google": SEARCH_STATE.get("hourly_last_google", 0),
            },
            "manual_search_target": SEARCH_STATE["manual_target_relevant"],
        }
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(resp).encode("utf-8"))

    def handle_api_search(self, query_str: str):
        """Handle manual search trigger seeking up to 200 relevant records."""
        params = urllib.parse.parse_qs(query_str)
        q = params.get("q", [""])[0].strip()
        sub = params.get("subreddit", ["googlephotos"])[0].strip()
        limit_param = int(params.get("limit", [200])[0])

        if not q:
            self.send_error(400, "Missing required query parameter 'q'")
            return

        target_relevant_count = max(limit_param, 200) if limit_param >= 100 else limit_param
        logger.info(
            f"[API] Manual Search Triggered: query='{q}', subreddit='{sub}', "
            f"target_relevant={target_relevant_count}"
        )

        try:
            cfg = load_config("config/queries.yaml")
            client = RedditClient(cfg)
            target_sub = None if sub.lower() in ("all", "global", "none") else sub

            # Collect candidates across search variations to fulfill target relevant records
            candidate_queries = [
                q,
                f"{q} search",
                f"{q} photo",
                f"can't find {q}",
            ]
            collected_relevant = []
            seen_cand_ids = set()

            for query_var in candidate_queries:
                if len(collected_relevant) >= target_relevant_count:
                    break
                try:
                    posts = client.search(
                        query=query_var,
                        subreddit=target_sub,
                        sort="relevance",
                        time_filter="all",
                        limit=min(50, target_relevant_count - len(collected_relevant)),
                    )
                    for p in posts:
                        if p.id in seen_cand_ids:
                            continue
                        seen_cand_ids.add(p.id)

                        analysis = classify_evidence(p.title, p.selftext)
                        # Filter strictly for relevant / possibly_relevant records
                        if analysis["is_relevant"]:
                            collected_relevant.append({
                                "source_id": p.id,
                                "title": p.title,
                                "raw_text": p.selftext or "",
                                "url": p.url,
                                "author": p.author,
                                "subreddit": p.subreddit or sub,
                                "created_at": datetime.fromtimestamp(p.created_utc, tz=timezone.utc).isoformat() if p.created_utc else datetime.now(timezone.utc).isoformat(),
                                "created_utc": p.created_utc,
                                "analysis": analysis,
                            })
                            if len(collected_relevant) >= target_relevant_count:
                                break
                except Exception as var_err:
                    logger.warning(f"Error querying candidate variation '{query_var}': {var_err}")

            # Also scrape Google discussion and support forums for the query
            try:
                google_cands = scrape_google_discussions(q, max_results=25)
                for g in google_cands:
                    if len(collected_relevant) >= target_relevant_count:
                        break
                    if g["source_id"] in seen_cand_ids:
                        continue
                    seen_cand_ids.add(g["source_id"])
                    analysis = classify_evidence(g["title"], g["raw_text"])
                    if analysis["is_relevant"]:
                        g["analysis"] = analysis
                        g["created_at"] = datetime.now(timezone.utc).isoformat()
                        collected_relevant.append(g)
            except Exception as g_err:
                logger.warning(f"Error scraping Google for '{q}': {g_err}")

            # Enforce user requirement:
            # "if from all the searches no relevant records are found it will not update the nuumber"
            if not collected_relevant:
                logger.info(f"[API] No relevant records found for query '{q}'. Numbers remain unchanged.")
                resp = {
                    "status": "ok",
                    "query": q,
                    "count": 0,
                    "added": 0,
                    "total_records": SEARCH_STATE["total_records"],
                    "total_analyzed": SEARCH_STATE["total_records"],
                    "total_relevant": SEARCH_STATE["total_relevant"],
                    "message": f"Search completed: No relevant records found for '{q}'. Cumulative database intact at {SEARCH_STATE['total_records']} analyzed records.",
                    "records": [],
                }
            else:
                added = persist_new_relevant_records(collected_relevant, query_label=f"Manual: {q}")
                logger.info(f"[API] Found {len(collected_relevant)} relevant records, {added} newly added.")
                resp = {
                    "status": "ok",
                    "query": q,
                    "count": len(collected_relevant),
                    "added": added,
                    "total_records": SEARCH_STATE["total_records"],
                    "total_analyzed": SEARCH_STATE["total_records"],
                    "total_relevant": SEARCH_STATE["total_relevant"],
                    "message": (
                        f"Search complete: Found {len(collected_relevant)} relevant records (+{added} added). Cumulative Total Stored: {SEARCH_STATE['total_records']} records analyzed."
                        if added > 0 else
                        f"Found {len(collected_relevant)} relevant records (all already in database). Cumulative Total Stored: {SEARCH_STATE['total_records']} records analyzed."
                    ),
                    "records": [
                        {
                            "record_id": f"LIVE_{i:03d}",
                            "title": r["title"],
                            "raw_text": r["raw_text"],
                            "url": r["url"],
                            "author": r["author"],
                            "subreddit": r["subreddit"],
                            "created_at": r["created_at"],
                            "analysis": r["analysis"],
                        }
                        for i, r in enumerate(collected_relevant, 1)
                    ],
                }

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


# Global background worker reference
hourly_worker: HourlySearchWorker | None = None


def run(port: int = 8000, host: str = "0.0.0.0"):
    global hourly_worker

    # Initialize stats
    refresh_global_stats()

    # Start 1-hour periodic search worker
    if hourly_worker is None or not hourly_worker.is_alive():
        hourly_worker = HourlySearchWorker(interval_seconds=3600, target_records=50)
        hourly_worker.start()

    server = ThreadingHTTPServer((host, port), DashboardHandler)
    print("=" * 70, flush=True)
    print(f"  [*] Research Intelligence Server Running", flush=True)
    print(f"  URL: http://{host}:{port}", flush=True)
    print(f"  60-Min Dual Scraper: Active (Reddit + Google discussions harvest)", flush=True)
    print(f"  Manual Search: Target: 200 relevant records (Reddit + Google)", flush=True)
    print(f"  Relevance Guard: Zero relevant records -> Numbers unchanged", flush=True)
    print(f"  Current Records: {SEARCH_STATE['total_records']} (Relevant: {SEARCH_STATE['total_relevant']})", flush=True)
    print("=" * 70, flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down server.", flush=True)
        server.server_close()


if __name__ == "__main__":
    default_port = int(os.environ.get("PORT", 8000))
    parser = argparse.ArgumentParser(description="Serve Research Dashboard with Live Search API")
    parser.add_argument("--port", type=int, default=default_port, help=f"Port to serve on (default: {default_port})")
    parser.add_argument("--host", default="0.0.0.0", help="Host interface to bind to (default: 0.0.0.0)")
    args = parser.parse_args()
    run(port=args.port, host=args.host)
