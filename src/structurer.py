"""Data Structurer & Storage Layer for Reddit Research Data-Retrieval System.

Serialises deduplicated PostRecord lists into JSON and/or CSV output files
with metadata headers.
"""

from __future__ import annotations

import csv
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.models import PostRecord

logger = logging.getLogger(__name__)

# CSV column order matching the spec
CSV_COLUMNS = [
    "post_id",
    "title",
    "selftext",
    "author",
    "subreddit",
    "created_utc",
    "score",
    "num_comments",
    "permalink",
    "search_query",
    "collected_at",
    "top_comments",
]

# Maximum selftext length in CSV output
CSV_SELFTEXT_MAX_LEN = 500

# Separator for joining top_comments list into a single CSV cell
COMMENT_SEPARATOR = " ||| "


class DataStructurer:
    """Serialises PostRecord lists into JSON and/or CSV files."""

    def __init__(self, output_dir: str, output_format: str = "json"):
        """
        Args:
            output_dir: Directory to write output files to.
            output_format: "json", "csv", or "both".
        """
        self.output_dir = Path(output_dir)
        self.output_format = output_format.lower().strip()
        if self.output_format not in ("json", "csv", "both"):
            raise ValueError(f"Invalid output_format: '{self.output_format}'. Must be 'json', 'csv', or 'both'.")

    def write(self, posts: list[PostRecord], metadata: dict[str, Any]) -> dict[str, Any]:
        """Write all posts to the configured format(s).

        Args:
            posts: List of deduplicated PostRecords.
            metadata: Run metadata (generated_at, total_posts,
                      queries_used, duplicates_skipped).

        Returns:
            dict with keys 'files_written' (list of paths)
                 and 'total_records' (int).
        """
        # Ensure output directory exists
        self.output_dir.mkdir(parents=True, exist_ok=True)

        files_written: list[str] = []

        if self.output_format in ("json", "both"):
            json_path = self._write_json(posts, metadata)
            files_written.append(json_path)

        if self.output_format in ("csv", "both"):
            csv_path = self._write_csv(posts)
            files_written.append(csv_path)

        result = {
            "files_written": files_written,
            "total_records": len(posts),
        }

        logger.info(
            f"DataStructurer wrote {len(posts)} records to {len(files_written)} file(s): "
            f"{', '.join(files_written)}"
        )
        return result

    def _write_json(self, posts: list[PostRecord], metadata: dict[str, Any]) -> str:
        """Write data/output/posts.json with metadata header.

        Returns:
            Absolute path of the written JSON file.
        """
        output_path = self.output_dir / "posts.json"

        output_data = {
            "metadata": metadata,
            "posts": [post.to_dict() for post in posts],
        }

        output_path.write_text(
            json.dumps(output_data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        logger.info(f"Wrote JSON output: {output_path} ({len(posts)} posts)")
        return str(output_path)

    def _write_csv(self, posts: list[PostRecord]) -> str:
        """Write data/output/posts.csv (flat, no nested comments).

        - selftext is truncated to 500 characters.
        - top_comments list is joined with ' ||| ' separator.

        Returns:
            Absolute path of the written CSV file.
        """
        output_path = self.output_dir / "posts.csv"

        with open(output_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS, extrasaction="ignore")
            writer.writeheader()

            for post in posts:
                row = post.to_dict()

                # Truncate selftext for CSV
                selftext = str(row.get("selftext", ""))
                if len(selftext) > CSV_SELFTEXT_MAX_LEN:
                    row["selftext"] = selftext[:CSV_SELFTEXT_MAX_LEN] + "..."

                # Join top_comments list into a single string
                comments = row.get("top_comments", [])
                if isinstance(comments, list):
                    row["top_comments"] = COMMENT_SEPARATOR.join(str(c) for c in comments)
                else:
                    row["top_comments"] = str(comments)

                writer.writerow(row)

        logger.info(f"Wrote CSV output: {output_path} ({len(posts)} posts)")
        return str(output_path)
