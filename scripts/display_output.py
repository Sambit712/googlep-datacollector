"""Utility script to display formatted output from data/output/posts.json and posts.csv."""

import csv
import json
from pathlib import Path

def display():
    json_path = Path("data/output/posts.json")
    csv_path = Path("data/output/posts.csv")

    if not json_path.exists():
        print(f"Error: {json_path} does not exist.")
        return

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    meta = data["metadata"]
    posts = data["posts"]

    print("=" * 80)
    print("                    REDDIT RETRIEVAL RUN METADATA")
    print("=" * 80)
    print(f"  Generated At:       {meta.get('generated_at')}")
    print(f"  Reddit Mode:        {meta.get('reddit_mode')}")
    print(f"  Total Posts Saved:  {meta.get('total_posts')}")
    print(f"  Queries Completed:  {meta.get('tasks_completed')}/{meta.get('tasks_completed', 0) + meta.get('tasks_failed', 0)}")
    print(f"  Duplicates Skipped: {meta.get('duplicates_skipped')}")
    print("=" * 80)

    print("\n" + "=" * 80)
    print("                     COLLECTED POST RECORDS")
    print("=" * 80)

    for i, p in enumerate(posts, 1):
        print(f"\n[Post #{i}] {p.get('post_id')} | r/{p.get('subreddit')} | by u/{p.get('author')}")
        print(f"  Search Query: \"{p.get('search_query')}\"")
        print(f"  Created UTC:  {p.get('created_utc')}")
        print(f"  Title:        {p.get('title')}")
        print(f"  Permalink:    {p.get('permalink')}")
        selftext = p.get('selftext', '').strip()
        if len(selftext) > 280:
            preview = selftext[:280] + " ... [truncated]"
        else:
            preview = selftext if selftext else "[No selftext body]"
        print(f"  Selftext:\n    {preview.replace(chr(10), chr(10) + '    ')}")
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
        print(f"  Columns:      {', '.join(headers)}")
        print(f"  Data Rows:    {row_count}")
        print("=" * 80)

if __name__ == "__main__":
    display()
