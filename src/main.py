"""Pipeline Orchestrator — Main entry point for the V0 Reddit Research Data-Retrieval System.

Wires all components together into a single runnable pipeline:
Config → Query Engine → Reddit Client → Collector → Deduplicator → Structurer → Output
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timezone
from typing import Any

from src.config_loader import AppConfig, ConfigError, load_config
from src.collector import PostCollector
from src.deduplicator import Deduplicator
from src.groq_client import GroqClient
from src.logger_setup import setup_logging
from src.models import PostRecord
from src.query_engine import QueryEngine
from src.reddit_client import RedditClient, RedditClientError
from src.structurer import DataStructurer

logger = logging.getLogger(__name__)


def main(config_path: str = "config/queries.yaml") -> None:
    """Full pipeline orchestration.

    1. Load and validate config
    2. Set up logging
    3. Initialize components
    4. Generate search tasks
    5. Execute searches, collect, deduplicate
    6. Write output files
    7. Save dedup index
    8. Log run summary
    """
    run_start = datetime.now(timezone.utc)

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

    logger.info("=" * 60)
    logger.info("V0 Reddit Research Data-Retrieval Pipeline — Run Starting")
    logger.info(f"Config: {config_path}")
    logger.info(f"Reddit mode: {config.reddit.mode}")
    logger.info("=" * 60)

    # --- 3. Initialize components ---
    query_engine = QueryEngine(config)

    try:
        reddit_client = RedditClient(config)
    except RedditClientError as e:
        logger.error(f"Failed to initialize Reddit client: {e}")
        sys.exit(1)

    collector = PostCollector(max_comments=5)

    dedup_index_path = f"{config.pipeline.output_dir}/seen_ids.json"
    deduplicator = Deduplicator(index_path=dedup_index_path)

    structurer = DataStructurer(
        output_dir=config.pipeline.output_dir,
        output_format=config.pipeline.output_format,
    )

    # --- 4. Optional Groq health check ---
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
    tasks = query_engine.generate_tasks()
    logger.info(f"Generated {len(tasks)} search tasks.")

    # --- 7. Execute pipeline ---
    all_posts: list[PostRecord] = []
    total_duplicates = 0
    total_raw = 0
    tasks_completed = 0
    tasks_failed = 0
    queries_used: set[str] = set()

    for i, (query, subreddit, params) in enumerate(tasks, 1):
        sub_display = f"r/{subreddit}" if subreddit else "r/all"
        logger.info(f"[{i}/{len(tasks)}] Searching for '{query}' in {sub_display}...")

        try:
            # Search
            raw_posts = reddit_client.search(
                query=query,
                subreddit=subreddit,
                sort=params.get("sort", "relevance"),
                time_filter=params.get("time_filter", "all"),
                limit=params.get("limit", 25),
            )

            # Collect & normalize
            records = collector.collect_batch(raw_posts, search_query=query)
            total_raw += len(records)

            # Deduplicate
            unique, dup_count = deduplicator.filter(records)
            total_duplicates += dup_count

            all_posts.extend(unique)
            queries_used.add(query)
            tasks_completed += 1

            logger.info(
                f"  → {len(unique)} new posts collected, {dup_count} duplicates skipped "
                f"(from {len(raw_posts)} raw results)"
            )

        except Exception as e:
            tasks_failed += 1
            logger.warning(f"  → Task failed for '{query}' in {sub_display}: {e}")
            continue

    # --- 8. Write output ---
    run_end = datetime.now(timezone.utc)
    metadata: dict[str, Any] = {
        "generated_at": run_end.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "run_started_at": run_start.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "total_posts": len(all_posts),
        "queries_used": len(queries_used),
        "duplicates_skipped": total_duplicates,
        "tasks_completed": tasks_completed,
        "tasks_failed": tasks_failed,
        "reddit_mode": config.reddit.mode,
    }

    write_result = structurer.write(all_posts, metadata)

    # --- 9. Save dedup index ---
    deduplicator.save()

    # --- 10. Log run summary ---
    dedup_stats = deduplicator.stats()
    logger.info("=" * 60)
    logger.info("Pipeline Run Complete!")
    logger.info(f"  Tasks completed:    {tasks_completed}/{len(tasks)}")
    logger.info(f"  Tasks failed:       {tasks_failed}")
    logger.info(f"  Total raw posts:    {total_raw}")
    logger.info(f"  Unique posts saved: {len(all_posts)}")
    logger.info(f"  Duplicates skipped: {total_duplicates}")
    logger.info(f"  Total seen (all runs): {dedup_stats['total_seen']}")
    logger.info(f"  Files written:      {write_result['files_written']}")
    logger.info(f"  Duration:           {(run_end - run_start).total_seconds():.1f}s")
    logger.info("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="V0 Reddit Research Data-Retrieval Pipeline"
    )
    parser.add_argument(
        "--config",
        default="config/queries.yaml",
        help="Path to YAML configuration file (default: config/queries.yaml)",
    )
    args = parser.parse_args()
    main(config_path=args.config)
