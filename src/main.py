"""Pipeline Orchestrator — Main entry point for the V0 Reddit Evidence Collection System.

Wires all components together into a single runnable evidence collection pipeline:
Config → Query Engine → Reddit Client → Collector → Deduplicator → Structurer → Quality Reporter
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from src.config_loader import AppConfig, ConfigError, load_config
from src.collector import PostCollector
from src.deduplicator import Deduplicator
from src.groq_client import GroqClient
from src.logger_setup import setup_logging
from src.models import EvidenceRecord
from src.query_engine import QueryEngine
from src.reddit_client import RedditClient, RedditClientError
from src.reporter import CollectionReporter
from src.structurer import DataStructurer

logger = logging.getLogger(__name__)


def main(
    config_path: str = "config/queries.yaml",
    limit_override: int | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Full pipeline orchestration for V0 Evidence Collection.

    Args:
        config_path: Path to YAML configuration file.
        limit_override: Optional limit on results per query for sample runs.
        dry_run: If True, executes collection without writing datasets to disk.

    Returns:
        The generated collection report dictionary.
    """
    run_start = datetime.now(timezone.utc)
    run_id = f"run_{run_start.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"

    # --- 1. Load and validate config ---
    try:
        config = load_config(config_path)
    except ConfigError as e:
        print(f"[FATAL] Configuration error: {e}", file=sys.stderr)
        sys.exit(1)

    # --- 2. Set up logging ---
    setup_logging(
        log_level=config.logging.level,
        log_file=config.logging.log_file,
    )

    logger.info("=" * 70)
    logger.info("V0 Reddit Evidence Collection Pipeline — Run Starting")
    logger.info(f"Run ID:        {run_id}")
    logger.info(f"Config:        {config_path}")
    logger.info(f"Reddit mode:   {config.reddit.mode}")
    logger.info(f"Dry Run:       {dry_run}")
    if limit_override:
        logger.info(f"Limit Override: {limit_override} per query")
    logger.info("=" * 70)

    # --- 3. Initialize components ---
    query_engine = QueryEngine(config)

    try:
        reddit_client = RedditClient(config)
    except RedditClientError as e:
        logger.error(f"Failed to initialize Reddit client: {e}")
        sys.exit(1)

    dedup_index_path = f"{config.pipeline.output_dir}/seen_ids.json"
    deduplicator = Deduplicator(index_path=dedup_index_path)

    # Starting ID continues sequence across runs to keep RD_xxxxxx unique and stable
    starting_id = deduplicator.last_record_number + 1

    collector = PostCollector(
        max_comments=config.pipeline.max_comments_per_post,
        starting_id=starting_id,
        anonymize_authors=config.privacy.anonymize_authors,
        run_id=run_id,
    )

    structurer = DataStructurer(
        output_dir=config.pipeline.output_dir,
        output_format=config.pipeline.output_format,
    )

    reporter = CollectionReporter(output_dir=config.pipeline.output_dir)

    # --- 4. Optional Groq health check (V1 preparation) ---
    if config.groq.enabled and config.groq.api_key:
        try:
            groq_client = GroqClient(
                api_key=config.groq.api_key,
                model=config.groq.model,
            )
            if groq_client.health_check():
                logger.info("Groq health check PASSED — ready for V1 analysis.")
            else:
                logger.warning("Groq health check FAILED — V1 analysis will not be available.")
        except Exception as e:
            logger.warning(f"Groq client initialization failed: {e}. V1 features unavailable.")
    else:
        logger.info("Groq is disabled or API key not set. Skipping health check (V0 mode).")

    # --- 5. Validate Reddit connectivity ---
    logger.info("Validating Reddit connectivity...")
    if reddit_client.validate_connection():
        logger.info("Reddit connection validated successfully.")
    else:
        logger.warning("Reddit connection check failed. Proceeding anyway — individual queries may still work.")

    # --- 6. Generate search tasks ---
    tasks = query_engine.generate_tasks(limit_override=limit_override)
    logger.info(f"Generated {len(tasks)} search tasks.")

    # --- 7. Execute pipeline ---
    all_records: list[EvidenceRecord] = []
    total_duplicates = 0
    total_raw = 0
    tasks_completed = 0
    tasks_failed = 0
    queries_executed: set[str] = set()

    for i, (query, subreddit, params) in enumerate(tasks, 1):
        sub_display = f"r/{subreddit}" if subreddit else "r/all"
        sub_tier = params.get("subreddit_tier", "primary")
        query_limit = params.get("limit", 25)

        logger.info(
            f"[{i}/{len(tasks)}] Searching for '{query}' in {sub_display} "
            f"[{sub_tier}] (limit={query_limit})..."
        )

        try:
            # Search
            raw_posts = reddit_client.search(
                query=query,
                subreddit=subreddit,
                sort=params.get("sort", "relevance"),
                time_filter=params.get("time_filter", "all"),
                limit=query_limit,
            )
            total_raw += len(raw_posts)

            # Collect & normalize into EvidenceRecords (posts and comments)
            records = collector.collect_batch(
                raw_posts,
                search_query=query,
                subreddit_tier=sub_tier,
                include_comments=True,
            )

            # Deduplicate by (source, source_id) while accumulating multi-query matches
            unique, dup_count = deduplicator.filter(records)
            total_duplicates += dup_count

            all_records.extend(unique)
            queries_executed.add(query)
            tasks_completed += 1

            logger.info(
                f"  → {len(unique)} new records collected, {dup_count} duplicates skipped "
                f"(from {len(raw_posts)} raw posts)"
            )

        except Exception as e:
            tasks_failed += 1
            logger.warning(f"  → Task failed for '{query}' in {sub_display}: {e}")
            continue
        finally:
            if i < len(tasks):
                delay = config.pipeline.request_delay_seconds
                if delay > 0:
                    time.sleep(delay)

    # --- 8. Write output (if not dry run) ---
    run_end = datetime.now(timezone.utc)
    duration = (run_end - run_start).total_seconds()

    metadata: dict[str, Any] = {
        "run_id": run_id,
        "generated_at": run_end.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "run_started_at": run_start.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "duration_seconds": round(duration, 2),
        "total_records": len(all_records),
        "queries_executed": len(queries_executed),
        "duplicates_skipped": total_duplicates,
        "tasks_completed": tasks_completed,
        "tasks_failed": tasks_failed,
        "reddit_mode": config.reddit.mode,
        "is_dry_run": dry_run,
    }

    if not dry_run:
        structurer.write(all_records, metadata)
        deduplicator.save()
    else:
        logger.info("[DRY RUN] Skipping file persistence to disk.")

    # --- 9. Quality Reporting ---
    report = reporter.generate_report(
        run_id=run_id,
        records=all_records,
        queries_executed=len(queries_executed),
        total_raw_results=total_raw,
        duplicates_removed=total_duplicates,
        tasks_completed=tasks_completed,
        tasks_failed=tasks_failed,
        duration_seconds=duration,
        is_dry_run=dry_run,
    )

    if not dry_run:
        reporter.save_report(report)

    reporter.print_summary(report)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="V0 Reddit Research Evidence-Collection Pipeline"
    )
    parser.add_argument(
        "--config",
        default="config/queries.yaml",
        help="Path to YAML configuration file (default: config/queries.yaml)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Override max results per query for sample runs (e.g. --limit 10)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run search, collection, and quality reporting without saving files to disk",
    )
    args = parser.parse_args()

    main(
        config_path=args.config,
        limit_override=args.limit,
        dry_run=args.dry_run,
    )
