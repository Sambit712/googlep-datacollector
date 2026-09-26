"""Pipeline Orchestrator — Unified CLI entry point for Reddit Research System.

Supports:
- V0 Evidence Collection (--mode collect)
- V1 AI Analysis & Insight Reporting (--mode analyze)
- End-to-End Pipeline (--mode both)
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Ensure project root is on sys.path when invoked directly as python src/main.py
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from dotenv import load_dotenv

from src.aggregator import PatternAggregator
from src.analyzer import AIAnalyzer
from src.config_loader import AppConfig, ConfigError, load_config, load_taxonomy
from src.collector import PostCollector
from src.deduplicator import Deduplicator
from src.evidence_loader import ImmutabilityGuard, load_v0_evidence
from src.groq_client import GroqClient
from src.insight_reporter import InsightReporter, DEFAULT_RESEARCH_QUESTION
from src.logger_setup import setup_logging
from src.models import EvidenceRecord
from src.query_engine import QueryEngine
from src.reddit_client import RedditClient, RedditClientError
from src.reporter import CollectionReporter
from src.structurer import DataStructurer

# Load environment variables (.env)
load_dotenv()

logger = logging.getLogger(__name__)


def parse_cli_args(args: list[str] | None = None) -> argparse.Namespace:
    """Parse and validate command-line arguments.

    Args:
        args: List of argument strings (defaults to sys.argv[1:]).

    Returns:
        Parsed Namespace object.
    """
    parser = argparse.ArgumentParser(
        description="Google Photos Vague-Memory Retrieval Research Pipeline (V0 Collection & V1 Analysis)"
    )
    parser.add_argument(
        "--mode",
        choices=["collect", "analyze", "both"],
        default="collect",
        help="Pipeline execution mode: 'collect' (V0), 'analyze' (V1), or 'both' (default: collect)",
    )
    parser.add_argument(
        "--config",
        default="config/queries.yaml",
        help="Path to queries/V0 YAML configuration file (default: config/queries.yaml)",
    )
    parser.add_argument(
        "--taxonomy",
        default="config/taxonomy.yaml",
        help="Path to taxonomy/V1 YAML configuration file (default: config/taxonomy.yaml)",
    )
    parser.add_argument(
        "--input",
        default="data/output/reddit_evidence.json",
        help="Path to V0 evidence JSON file for analysis (default: data/output/reddit_evidence.json)",
    )
    parser.add_argument(
        "--sample",
        type=int,
        default=None,
        help="Limit V1 analysis to first N records for rapid validation (e.g. --sample 5)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate configurations, connections, and pipeline without writing files to disk",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Override max results per query for sample runs (e.g. --limit 10)",
    )
    parser.add_argument(
        "--max-records",
        type=int,
        default=None,
        help="Stop collection early after reaching target raw record count (e.g. --max-records 500)",
    )
    return parser.parse_args(args)


def run_collection_pipeline(
    config_path: str = "config/queries.yaml",
    limit_override: int | None = None,
    dry_run: bool = False,
    max_records: int | None = None,
) -> dict[str, Any]:
    """Execute V0 Evidence Collection Pipeline."""
    run_start = datetime.now(timezone.utc)
    run_id = f"run_{run_start.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"

    # 1. Load and validate config
    try:
        config = load_config(config_path)
    except ConfigError as e:
        print(f"[FATAL] Configuration error: {e}", file=sys.stderr)
        sys.exit(1)

    # 2. Set up logging
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

    # 3. Initialize components
    query_engine = QueryEngine(config)

    try:
        reddit_client = RedditClient(config)
    except RedditClientError as e:
        logger.error(f"Failed to initialize Reddit client: {e}")
        sys.exit(1)

    dedup_index_path = f"{config.pipeline.output_dir}/seen_ids.json"
    deduplicator = Deduplicator(index_path=dedup_index_path)
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

    # 4. Optional Groq health check (V1 preparation)
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

    # 5. Validate Reddit connectivity
    logger.info("Validating Reddit connectivity...")
    if reddit_client.validate_connection():
        logger.info("Reddit connection validated successfully.")
    else:
        logger.warning("Reddit connection check failed. Proceeding anyway — individual queries may still work.")

    # 6. Generate search tasks
    tasks = query_engine.generate_tasks(limit_override=limit_override)
    logger.info(f"Generated {len(tasks)} search tasks.")

    # 6b. Dry-Run Mode
    if dry_run:
        product_queries = config.search.query_categories.get("product_specific", [])
        behavior_queries = config.search.query_categories.get("behavior_specific", [])
        primary_subs = config.search.subreddit_tiers.get("primary", config.search.subreddits)
        discovery_subs = config.search.subreddit_tiers.get("discovery", [])

        print("\n" + "=" * 70)
        print(" [DRY RUN] Configuration & Execution Plan Validation")
        print("=" * 70)
        print(f" * Run ID:               {run_id}")
        print(f" * Config Path:          {config_path}")
        print(f" * Reddit Mode:          {config.reddit.mode}")
        print(f" * Product Queries ({len(product_queries)}):")
        for q in product_queries:
            print(f"     - [product]  \"{q}\"")
        print(f" * Behavior Queries ({len(behavior_queries)}):")
        for q in behavior_queries:
            print(f"     - [behavior] \"{q}\"")
        print(f" * Primary Subreddits:   {', '.join('r/' + s for s in primary_subs)}")
        print(f" * Discovery Subreddits: {', '.join('r/' + s for s in discovery_subs)}")
        print(f" * Planned Tasks:        {len(tasks)} search task(s)")
        for idx, (query, sub, params) in enumerate(tasks, 1):
            sub_str = f"r/{sub}" if sub else "r/all"
            print(f"     [{idx:02d}] '{query}' in {sub_str} (tier={params.get('subreddit_tier', 'primary')}, limit={params.get('limit')})")
        print(f" * Output Directory:     {config.pipeline.output_dir}")
        print(f" * Output Formats:       {config.pipeline.output_format}")
        print(f" * Author Privacy:       {'Anonymized (author_xxxxxx)' if config.privacy.anonymize_authors else 'Public usernames'}")
        print(f" * Comments Enabled:     True (max {config.pipeline.max_comments_per_post} per post with parent context)")
        print("=" * 70)
        print(" [DRY RUN] Configuration valid. No data was collected or written.")
        print("=" * 70 + "\n")

        run_end = datetime.now(timezone.utc)
        duration = (run_end - run_start).total_seconds()
        report = reporter.generate_report(
            run_id=run_id,
            records=[],
            queries_executed=len(tasks),
            total_raw_results=0,
            duplicates_removed=0,
            tasks_completed=len(tasks),
            tasks_failed=0,
            duration_seconds=duration,
            is_dry_run=True,
        )
        reporter.print_summary(report)
        return report

    # 7. Execute collection
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
            raw_posts = reddit_client.search(
                query=query,
                subreddit=subreddit,
                sort=params.get("sort", "relevance"),
                time_filter=params.get("time_filter", "all"),
                limit=query_limit,
            )
            total_raw += len(raw_posts)

            records = collector.collect_batch(
                raw_posts,
                search_query=query,
                subreddit_tier=sub_tier,
                include_comments=True,
            )

            unique, dup_count = deduplicator.filter(records)
            total_duplicates += dup_count

            all_records.extend(unique)
            queries_executed.add(query)
            tasks_completed += 1

            logger.info(
                f"  -> {len(unique)} new records collected, {dup_count} duplicates skipped "
                f"(from {len(raw_posts)} raw posts)"
            )

            if max_records and (total_raw >= max_records or len(all_records) >= max_records):
                logger.info(
                    f"Target record threshold reached ({total_raw} raw / {len(all_records)} unique records). Finalizing collection."
                )
                break

        except Exception as e:
            tasks_failed += 1
            logger.warning(f"  -> Task failed for '{query}' in {sub_display}: {e}")
            continue
        finally:
            if i < len(tasks):
                delay = config.pipeline.request_delay_seconds
                if delay > 0:
                    time.sleep(delay)

    # 8. Write output
    run_end = datetime.now(timezone.utc)
    duration = (run_end - run_start).total_seconds()

    metadata: dict[str, Any] = {
        "run_id": run_id,
        "generated_at": run_end.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "run_started_at": run_start.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "duration_seconds": round(duration, 2),
        "total_records": len(all_records),
        "total_posts": len(all_records),
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

    # 9. Quality Reporting
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


def run_analysis_pipeline(
    taxonomy_path: str = "config/taxonomy.yaml",
    input_path: str = "data/output/reddit_evidence.json",
    sample: int | None = None,
    dry_run: bool = False,
    output_dir: str = "data/output",
    model: str | None = None,
) -> dict[str, Any]:
    """Execute V1 AI-Powered Research Analysis Pipeline.

    Args:
        taxonomy_path: Path to taxonomy YAML configuration file.
        input_path: Path to V0 evidence JSON file.
        sample: Optional limit on number of records to analyze.
        dry_run: If True, executes analysis without persisting files to disk.
        output_dir: Output directory for analyzed artifacts.
        model: Optional LLM model override.

    Returns:
        Executive research insight report dictionary.
    """
    logger.info("=" * 70)
    logger.info("V1 AI Analysis Pipeline — Starting")
    logger.info(f"Taxonomy:      {taxonomy_path}")
    logger.info(f"Input:         {input_path}")
    logger.info(f"Sample Limit:  {sample if sample is not None else 'All records'}")
    logger.info(f"Dry Run:       {dry_run}")
    logger.info("=" * 70)

    # 1. Load taxonomy configuration
    try:
        taxonomy = load_taxonomy(taxonomy_path)
    except Exception as e:
        logger.error(f"Failed to load taxonomy configuration from {taxonomy_path}: {e}")
        raise

    # 2. Check GROQ API credentials
    api_key = os.environ.get("GROQ_API_KEY", "").strip()
    if not api_key:
        raise ValueError(
            "GROQ_API_KEY environment variable is required for V1 analysis mode. "
            "Please configure GROQ_API_KEY in your environment or .env file."
        )

    chosen_model = model or taxonomy.groq_analysis.model
    groq_client = GroqClient(
        api_key=api_key,
        model=chosen_model,
        temperature=taxonomy.groq_analysis.temperature,
        max_retries=taxonomy.groq_analysis.max_retries,
        timeout=taxonomy.groq_analysis.timeout_seconds,
    )

    # 3. Perform Groq API health check
    logger.info("Performing Groq API health check...")
    if not groq_client.health_check():
        raise RuntimeError(
            "Groq API health check failed. Verify your GROQ_API_KEY and network connectivity."
        )
    logger.info(f"Groq API health check PASSED (model: {chosen_model}).")

    # 4. Ingest V0 evidence with immutability guarantees
    input_file = Path(input_path)
    if not input_file.exists():
        raise FileNotFoundError(
            f"V0 evidence file not found at '{input_path}'. "
            "Please run V0 collection first ('python src/main.py --mode collect') or provide a valid --input path."
        )

    with ImmutabilityGuard(input_file):
        evidence_records = load_v0_evidence(str(input_file))
        total_found = len(evidence_records)

        if sample is not None and sample > 0:
            logger.info(f"Sampling {sample} of {total_found} evidence records for analysis.")
            evidence_records = evidence_records[:sample]
        else:
            logger.info(f"Loaded {total_found} evidence records for analysis.")

        # 5. Multi-task AI Analysis
        analyzer = AIAnalyzer(groq_client=groq_client, taxonomy=taxonomy)
        logger.info(f"Starting AI analysis of {len(evidence_records)} records...")
        analyzed_records = analyzer.analyze_batch(
            evidence_records,
            on_progress=lambda cur, tot: logger.info(f"Analyzed {cur}/{tot} records...")
            if cur % 10 == 0 or cur == tot
            else None,
        )

        # 6. Statistical Aggregation & Pattern Synthesis
        logger.info("Aggregating research statistics and synthesizing recurring patterns...")
        aggregator = PatternAggregator(analyzed_records)
        summary = aggregator.generate_summary()

    # 7. Serialization & Insight Reporting
    reporter = InsightReporter(output_dir=output_dir)

    if not dry_run:
        reporter.write_analyzed_evidence(analyzed_records, output_dir=output_dir)
        report_file = reporter.write_insight_report(
            aggregations_or_summary=summary,
            output_dir=output_dir,
            groq_model=chosen_model,
            v0_source_file=str(input_path),
        )
        report = reporter.load_insight_report(report_file)
        # Write executive markdown report to output directory and reports/
        reporter.write_markdown_report(report, output_dir=output_dir)
        try:
            if Path(output_dir).resolve() != Path("reports").resolve():
                reporter.write_markdown_report(report, output_dir="reports")
        except Exception as e:
            logger.warning(f"Could not copy markdown report to reports/: {e}")

        reporter.print_summary(report)
        return report
    else:
        logger.info("[DRY RUN] Analysis complete. Skipping persistence of output files to disk.")
        report_metadata = {
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "v0_source_file": str(input_path),
            "total_records_ingested": len(evidence_records),
            "relevant_evidence_count": summary["statistics"]["relevant_evidence_count"],
            "relevance_rate": summary["statistics"]["relevance_rate"],
            "groq_model_used": chosen_model,
            "is_dry_run": True,
        }
        report = {
            "report_metadata": report_metadata,
            "research_question": DEFAULT_RESEARCH_QUESTION,
            "distributions": summary["distributions"],
            "cross_tabulations": summary["cross_tabulations"],
            "recurring_patterns": summary["recurring_patterns"],
        }
        reporter.print_summary(report)
        return report


def main(
    config_path: str = "config/queries.yaml",
    limit_override: int | None = None,
    dry_run: bool = False,
    max_records: int | None = None,
    mode: str = "collect",
    taxonomy_path: str = "config/taxonomy.yaml",
    input_path: str = "data/output/reddit_evidence.json",
    sample: int | None = None,
    output_dir: str | None = None,
) -> dict[str, Any]:
    """Unified entry point for both V0 Collection and V1 Analysis pipelines.

    Args:
        config_path: Path to queries configuration file.
        limit_override: Override max results per query for sample runs.
        dry_run: If True, execute pipeline without persisting files to disk.
        max_records: Stop collection early after reaching record count threshold.
        mode: Execution mode ('collect', 'analyze', or 'both').
        taxonomy_path: Path to taxonomy configuration file.
        input_path: Path to V0 evidence JSON file for analysis.
        sample: Limit analysis to first N records for rapid validation.
        output_dir: Output directory for generated artifacts.

    Returns:
        Report dictionary corresponding to executed mode.
    """
    normalized_mode = mode.lower().strip()

    if normalized_mode == "collect":
        return run_collection_pipeline(
            config_path=config_path,
            limit_override=limit_override,
            dry_run=dry_run,
            max_records=max_records,
        )
    elif normalized_mode == "analyze":
        return run_analysis_pipeline(
            taxonomy_path=taxonomy_path,
            input_path=input_path,
            sample=sample,
            dry_run=dry_run,
            output_dir=output_dir or "data/output",
        )
    elif normalized_mode == "both":
        logger.info("Executing Mode: BOTH (V0 Collection followed by V1 Analysis)")
        collection_report = run_collection_pipeline(
            config_path=config_path,
            limit_override=limit_override,
            dry_run=dry_run,
            max_records=max_records,
        )
        analysis_report = run_analysis_pipeline(
            taxonomy_path=taxonomy_path,
            input_path=input_path,
            sample=sample,
            dry_run=dry_run,
            output_dir=output_dir or "data/output",
        )
        return {
            "mode": "both",
            "collection": collection_report,
            "analysis": analysis_report,
        }
    else:
        raise ValueError(
            f"Invalid mode: '{mode}'. Must be one of: 'collect', 'analyze', 'both'."
        )


if __name__ == "__main__":
    args = parse_cli_args()
    main(
        config_path=args.config,
        limit_override=args.limit,
        dry_run=args.dry_run,
        max_records=args.max_records,
        mode=args.mode,
        taxonomy_path=args.taxonomy,
        input_path=args.input,
        sample=args.sample,
    )
