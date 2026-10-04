"""Manual Search Trigger Utility.

Allows triggering manual, ad-hoc search queries against Reddit
using the project's RedditClient and PostCollector.

Usage:
    python scripts/manual_search.py --query "Google Photos cant find photo" --subreddit googlephotos --limit 10
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Ensure root is in sys.path
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from src.collector import PostCollector
from src.config_loader import AppConfig, SearchConfig
from src.reddit_client import RedditClient

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def manual_search(query: str, subreddit: str = "googlephotos", limit: int = 10, save: bool = True) -> list:
    print("=" * 80)
    print(f"  🔍 MANUAL SEARCH TRIGGER — QUERY: \"{query}\"")
    print(f"  Subreddit: r/{subreddit} | Max Records: {limit}")
    print("=" * 80)

    # Initialize client & collector
    from src.config_loader import load_config
    config = load_config("config/queries.yaml")
    client = RedditClient(config)
    collector = PostCollector(max_comments=2, run_id="manual_search")

    sub = None if subreddit.lower() in ("all", "global", "none") else subreddit

    print("\n⏳ Fetching live posts from Reddit...")
    try:
        raw_posts = client.search(
            query=query,
            subreddit=sub,
            sort="relevance",
            time_filter="all",
            limit=limit,
        )
    except Exception as e:
        print(f"\n❌ Search failed: {e}")
        return []

    print(f"✓ Retrieved {len(raw_posts)} raw submissions from Reddit.")

    if not raw_posts:
        print("No matching posts found.")
        return []

    # Format into evidence records
    records = []
    for i, p in enumerate(raw_posts, 1):
        rec_id = f"MANUAL_{i:03d}"
        print(f"\n[{rec_id}] r/{p.subreddit} — u/{p.author}")
        print(f"  Title: {p.title}")
        print(f"  URL:   {p.url}")
        text = (p.selftext or "").strip()
        preview = (text[:200] + "...") if len(text) > 200 else (text or "[No self text]")
        print(f"  Preview:\n    {preview.replace(chr(10), chr(10) + '    ')}")
        records.append({
            "source_id": p.id,
            "title": p.title,
            "raw_text": p.selftext or "",
            "url": p.url,
            "author": p.author,
            "subreddit": p.subreddit or sub,
            "created_utc": p.created_utc,
        })

    out_dir = root_dir / "data" / "output"
    out_dir.mkdir(parents=True, exist_ok=True)

    if save:
        out_file = out_dir / "manual_search_results.json"
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump({"query": query, "subreddit": subreddit, "count": len(records), "records": records}, f, indent=2)
        print(f"\n💾 Saved {len(records)} raw search results to {out_file}")

    # Analyze and append to the cumulative stored database
    try:
        from scripts.serve_dashboard import classify_evidence, persist_new_relevant_records, refresh_global_stats, SEARCH_STATE

        refresh_global_stats()
        prev_total = SEARCH_STATE.get("total_records", 0)

        # Classify and filter for relevant records
        relevant_candidates = []
        for r in records:
            analysis = classify_evidence(r["title"], r["raw_text"])
            if analysis["is_relevant"]:
                relevant_candidates.append({
                    "source_id": r["source_id"],
                    "title": r["title"],
                    "raw_text": r["raw_text"],
                    "url": r["url"],
                    "author": r["author"],
                    "subreddit": r["subreddit"],
                    "created_utc": r.get("created_utc"),
                    "analysis": analysis,
                })

        print("\n" + "=" * 80)
        print("  🔬 COGNITIVE TAXONOMY ANALYSIS & CUMULATIVE DATABASE SYNC")
        print("=" * 80)
        print(f"  Total Candidates Analyzed from Reddit: {len(records)}")
        print(f"  Relevant Failure Signals Identified:  {len(relevant_candidates)}")

        if not relevant_candidates:
            print(f"\n  ⚠️  0 relevant records found for '{query}'. (Strict Relevance Guard Active)")
            print(f"  📊 Cumulative Analyzed Database Intact at: {prev_total:,} records.")
        else:
            added = persist_new_relevant_records(relevant_candidates, query_label=f"Manual CLI: {query}")
            refresh_global_stats()
            new_total = SEARCH_STATE.get("total_records", 0)
            if added > 0:
                print(f"\n  ✅ Added +{added} newly analyzed non-duplicate records to persistent database!")
                print(f"  🏆 NEW Cumulative Total Analyzed Records Stored: {new_total:,} (was {prev_total:,})")
            else:
                print(f"\n  ℹ️  All {len(relevant_candidates)} candidates were already present in historical database.")
                print(f"  📊 Cumulative Total Analyzed Records Stored: {new_total:,}")
        print("=" * 80)

    except Exception as e:
        print(f"\n⚠️  Could not automatically sync to cumulative database: {e}")

    print("=" * 80)
    return records


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Trigger a manual search query on Reddit and store to cumulative analyzed database")
    parser.add_argument("--query", "-q", required=True, help="Search query string")
    parser.add_argument("--subreddit", "-s", default="googlephotos", help="Target subreddit (default: googlephotos)")
    parser.add_argument("--limit", "-l", type=int, default=10, help="Number of records to fetch (default: 10)")
    parser.add_argument("--no-save", action="store_true", help="Do not save raw search JSON to disk")
    args = parser.parse_args()

    manual_search(query=args.query, subreddit=args.subreddit, limit=args.limit, save=not args.no_save)
