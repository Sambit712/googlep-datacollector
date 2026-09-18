"""Data Structurer & Storage Layer for Reddit Research Evidence-Collection System.

Serializes deduplicated EvidenceRecord lists into JSON and CSV output files
with ZERO text truncation, preserving full raw and cleaned evidence.
"""

from __future__ import annotations

import csv
import json
import logging
from pathlib import Path
from typing import Any

from src.models import EvidenceRecord

logger = logging.getLogger(__name__)

# Complete evidence CSV column order
CSV_COLUMNS = [
    "record_id",
    "source",
    "source_type",
    "content_type",
    "source_id",
    "subreddit",
    "subreddit_tier",
    "title",
    "raw_text",
    "cleaned_text",
    "preview_text",
    "text_preview",
    "author",
    "created_at",
    "retrieved_at",
    "url",
    "queries_matched",
    "query_used",
    "run_id",
    "parent_id",
    "parent_post_title",
    "parent_post_text",
    "comment_text",
    "score",
    "num_comments",
    "top_comments",
    "ai_relevance",
    "relevance_confidence",
    "evidence_status",
]

# Separators for multi-value list fields in CSV
LIST_SEPARATOR = " ; "
COMMENT_SEPARATOR = " ||| "


class DataStructurer:
    """Serializes EvidenceRecord lists into JSON and/or CSV files with zero truncation."""

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

    def write(self, posts: list[EvidenceRecord], metadata: dict[str, Any]) -> dict[str, Any]:
        """Write all evidence records to the configured format(s).

        Preserves 100% of the raw and cleaned text without truncation.

        Args:
            posts: List of EvidenceRecords to serialize.
            metadata: Metadata dictionary to include with the dataset.

        Returns:
            Dictionary with paths to the written files and record count.
        """
        self.output_dir.mkdir(parents=True, exist_ok=True)
        files_written: list[str] = []

        if self.output_format in ("json", "both"):
            json_file = self.output_dir / "reddit_evidence.json"
            legacy_json = self.output_dir / "posts.json"
            self._write_json(posts, metadata, json_file)
            self._write_json(posts, metadata, legacy_json)
            files_written.append(str(json_file))
            files_written.append(str(legacy_json))

        if self.output_format in ("csv", "both"):
            csv_file = self.output_dir / "reddit_evidence.csv"
            legacy_csv = self.output_dir / "posts.csv"
            self._write_csv(posts, csv_file)
            self._write_csv(posts, legacy_csv)
            files_written.append(str(csv_file))
            files_written.append(str(legacy_csv))

        logger.info(f"DataStructurer wrote {len(posts)} records to {len(files_written)} file(s): {', '.join(files_written)}")
        return {
            "files_written": files_written,
            "total_records": len(posts),
        }

    def _write_json(self, posts: list[EvidenceRecord], metadata: dict[str, Any], path: Path) -> None:
        """Write records and metadata to a JSON file."""
        records_list = [p.to_dict() for p in posts]
        payload = {
            "metadata": metadata,
            "posts": records_list,
            "records": records_list,  # alias for clarity
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
        logger.info(f"Wrote JSON output: {path} ({len(posts)} records)")

    def _write_csv(self, posts: list[EvidenceRecord], path: Path) -> None:
        """Write records to a flat CSV file with zero text truncation."""
        with open(path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=CSV_COLUMNS,
                extrasaction="ignore",
                quoting=csv.QUOTE_MINIMAL,
            )
            writer.writeheader()

            for p in posts:
                row = p.to_dict()
                if isinstance(row.get("query_used"), list):
                    row["query_used"] = LIST_SEPARATOR.join(row["query_used"])
                if isinstance(row.get("queries_matched"), list):
                    row["queries_matched"] = LIST_SEPARATOR.join(row["queries_matched"])
                if isinstance(row.get("top_comments"), list):
                    row["top_comments"] = COMMENT_SEPARATOR.join(row["top_comments"])
                writer.writerow(row)

        logger.info(f"Wrote CSV output: {path} ({len(posts)} records, zero truncation)")
