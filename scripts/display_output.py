"""Utility script to display formatted output from data/output/reddit_evidence.json, reddit_evidence.csv, and collection_report.json."""

import csv
import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

def display():
    json_path = Path("data/output/reddit_evidence.json")
    csv_path = Path("data/output/reddit_evidence.csv")
    report_path = Path("data/output/collection_report.json")

    if report_path.exists():
        with open(report_path, "r", encoding="utf-8") as rf:
            rep = json.load(rf)
        print("=" * 80)
        print(f"         COLLECTION QUALITY REPORT — RUN {rep.get('run_id')}")
        print("=" * 80)
        s = rep.get("summary", {})
        q = rep.get("data_quality", {})
        print(f"  Generated At:       {rep.get('generated_at')}")
        print(f"  Duration:           {rep.get('duration_seconds')}s")
        print(f"  Queries Executed:   {s.get('queries_executed')}")
        print(f"  Raw Results:        {s.get('raw_results')}")
        print(f"  Unique Records:     {s.get('unique_records')}")
        print(f"  Duplicates Removed: {s.get('duplicates_removed')}")
        print(f"  Posts / Comments:   {s.get('posts')} posts, {s.get('comments')} comments")
        print(f"  Saved to Disk:      {s.get('records_successfully_saved')}")
        print(f"  Text Completeness:  {q.get('text_completeness_rate', 1)*100:.1f}%")
        print(f"  URL Completeness:   {q.get('url_completeness_rate', 1)*100:.1f}%")
        print("=" * 80)

    if not json_path.exists():
        print(f"\nNote: {json_path} does not exist yet (run pipeline to generate).")
        return

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    meta = data.get("metadata", {})
    records = data.get("posts", [])

    print("\n" + "=" * 80)
    print("                     COLLECTED EVIDENCE RECORDS")
    print("=" * 80)

    for i, p in enumerate(records, 1):
        rec_id = p.get('record_id') or f"#{i}"
        c_type = p.get('content_type', 'post').upper()
        print(f"\n[{rec_id}] [{c_type}] {p.get('source_id')} | r/{p.get('subreddit')} [{p.get('subreddit_tier', 'primary')}] | by u/{p.get('author')}")
        print(f"  Query:      \"{p.get('query_used')}\"")
        matched = p.get('queries_matched', [])
        if len(matched) > 1:
            print(f"  All Matched: {matched}")
        print(f"  Created:    {p.get('created_at')}")
        print(f"  Title:      {p.get('title')}")
        print(f"  URL:        {p.get('url')}")
        if p.get('parent_id'):
            print(f"  Parent:     {p.get('parent_id')} (\"{p.get('parent_post_title', '')}\")")
        text = p.get('cleaned_text', '').strip() or p.get('raw_text', '').strip()
        preview = (text[:280] + " ... [truncated preview]") if len(text) > 280 else (text or "[No body text]")
        print(f"  Evidence Preview:\n    {preview.replace(chr(10), chr(10) + '    ')}")
        print("-" * 80)

    if csv_path.exists():
        with open(csv_path, "r", encoding="utf-8") as cf:
            reader = csv.reader(cf)
            headers = next(reader)
            row_count = sum(1 for _ in reader)
        print("\n" + "=" * 80)
        print("                     CSV EXPORT SUMMARY")
        print("=" * 80)
        print(f"  File Path:    {csv_path}")
        print(f"  Columns ({len(headers)}):  {', '.join(headers[:8])} ... ({len(headers)-8} more)")
        print(f"  Data Rows:    {row_count} (Full untruncated evidence)")
        print("=" * 80)

if __name__ == "__main__":
    display()
