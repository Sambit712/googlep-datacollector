"""Data-quality reporting for Reddit Evidence Collection System.

Calculates and formats comprehensive collection quality metrics:
- Queries executed
- Raw results & duplicates removed
- Posts vs comments breakdown
- Missing text / URL checks
- Results by subreddit & results by query
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.models import EvidenceRecord

logger = logging.getLogger(__name__)


class CollectionReporter:
    """Generates and logs comprehensive data-quality metrics for a collection run."""

    def __init__(self, output_dir: str = "data/output"):
        self.output_dir = Path(output_dir)

    def generate_report(
        self,
        run_id: str,
        records: list[EvidenceRecord],
        queries_executed: int,
        total_raw_results: int,
        duplicates_removed: int,
        tasks_completed: int,
        tasks_failed: int,
        duration_seconds: float,
        is_dry_run: bool = False,
    ) -> dict[str, Any]:
        """Compute data-quality metrics and format report.

        Args:
            run_id: Unique identifier for the collection run.
            records: List of successfully collected EvidenceRecords.
            queries_executed: Count of search queries executed.
            total_raw_results: Total raw results retrieved from Reddit.
            duplicates_removed: Number of duplicate submissions/comments filtered out.
            tasks_completed: Number of completed search tasks.
            tasks_failed: Number of failed search tasks.
            duration_seconds: Total pipeline duration in seconds.
            is_dry_run: Whether the run was executed in dry-run mode.

        Returns:
            Dictionary containing all metrics.
        """
        posts_count = sum(1 for r in records if r.content_type == "post")
        comments_count = sum(1 for r in records if r.content_type == "comment")

        missing_text = sum(1 for r in records if not (r.cleaned_text or r.raw_text).strip())
        missing_urls = sum(1 for r in records if not r.url or not r.url.startswith("http"))

        # Breakdowns
        by_subreddit = dict(Counter(r.subreddit for r in records if r.subreddit))
        query_counter: Counter[str] = Counter()
        for r in records:
            if r.queries_matched:
                for q in r.queries_matched:
                    query_counter[q] += 1
            elif r.query_used:
                query_counter[r.query_used] += 1
        by_query = dict(query_counter)
        by_tier = dict(Counter(r.subreddit_tier for r in records if r.subreddit_tier))

        report: dict[str, Any] = {
            "run_id": run_id,
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "duration_seconds": round(duration_seconds, 2),
            "is_dry_run": is_dry_run,
            "summary": {
                "queries_executed": queries_executed,
                "tasks_completed": tasks_completed,
                "tasks_failed": tasks_failed,
                "raw_results": total_raw_results,
                "unique_records": len(records),
                "duplicates_removed": duplicates_removed,
                "posts": posts_count,
                "comments": comments_count,
                "records_successfully_saved": 0 if is_dry_run else len(records),
            },
            "data_quality": {
                "records_with_missing_text": missing_text,
                "records_with_missing_urls": missing_urls,
                "text_completeness_rate": round((len(records) - missing_text) / (len(records) or 1), 4),
                "url_completeness_rate": round((len(records) - missing_urls) / (len(records) or 1), 4),
            },
            "breakdown_by_subreddit": by_subreddit,
            "breakdown_by_subreddit_tier": by_tier,
            "breakdown_by_query": by_query,
        }

        return report

    def save_report(self, report: dict[str, Any]) -> Path:
        """Write the collection report to collection_report.json."""
        self.output_dir.mkdir(parents=True, exist_ok=True)
        report_path = self.output_dir / "collection_report.json"
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        logger.info(f"Saved collection quality report to {report_path}")
        return report_path

    def print_summary(self, report: dict[str, Any]) -> None:
        """Print a human-readable summary table to console and logger."""
        s = report["summary"]
        q = report["data_quality"]

        lines = [
            "=" * 70,
            f"V0 DATA RETRIEVER - COLLECTION QUALITY REPORT ({report['run_id']})",
            "=" * 70,
            f"  Queries executed:           {s['queries_executed']}",
            f"  Tasks completed:            {s['tasks_completed']} (failed: {s['tasks_failed']})",
            f"  Raw results:                {s['raw_results']}",
            f"  Unique records:             {s['unique_records']}",
            f"  Duplicates removed:         {s['duplicates_removed']}",
            f"  Posts:                      {s['posts']}",
            f"  Comments:                   {s['comments']}",
            f"  Records successfully saved: {s['records_successfully_saved']} {'(DRY RUN)' if report['is_dry_run'] else ''}",
            f"  Records with missing text:  {q['records_with_missing_text']}",
            f"  Records with missing URLs:  {q['records_with_missing_urls']}",
            f"  Text completeness:          {q['text_completeness_rate']*100:.1f}%",
            f"  URL completeness:           {q['url_completeness_rate']*100:.1f}%",
            f"  Duration:                   {report['duration_seconds']}s",
            "-" * 70,
            "  Results by Subreddit:",
        ]

        for sub, count in sorted(report["breakdown_by_subreddit"].items(), key=lambda x: x[1], reverse=True):
            tier = report["breakdown_by_subreddit_tier"].get(sub, "")
            tier_str = f" [{tier}]" if tier else ""
            lines.append(f"    - r/{sub}{tier_str}: {count}")

        lines.append("  Results by Query:")
        for query, count in sorted(report["breakdown_by_query"].items(), key=lambda x: x[1], reverse=True):
            lines.append(f"    - \"{query}\": {count}")

        lines.append("=" * 70)

        formatted_report = "\n".join(lines)
        print(formatted_report)
        for l in lines:
            logger.info(l)
