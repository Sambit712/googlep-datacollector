"""Scheduled Research Engine — Recurring Search & Analysis Pipeline.

Executes periodic (e.g. hourly) Reddit evidence collection across configured
queries and subreddits, deduplicates against historical runs, extracts new
relevant retrieval failure records, executes AI cognitive taxonomy analysis,
and incrementally updates research insight artifacts.
"""

from __future__ import annotations

import json
import logging
import os
import signal
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from src.aggregator import PatternAggregator
from src.analyzer import AIAnalyzer
from src.collector import PostCollector
from src.config_loader import AppConfig, ConfigError, load_config, load_taxonomy
from src.deduplicator import Deduplicator
from src.evidence_loader import load_v0_evidence_with_metadata
from src.groq_client import GroqClient
from src.insight_reporter import InsightReporter
from src.logger_setup import setup_logging
from src.models import AnalyzedEvidenceRecord, EvidenceRecord
from src.query_engine import QueryEngine
from src.reddit_client import RedditClient, RedditClientError
from src.reporter import CollectionReporter
from src.structurer import DataStructurer

logger = logging.getLogger(__name__)


class ScheduledResearchEngine:
    """Orchestrates recurring searches, evidence deduplication, and AI analysis."""

    def __init__(
        self,
        config_path: str = "config/queries.yaml",
        taxonomy_path: str = "config/taxonomy.yaml",
        interval_seconds: float = 3600.0,
        limit_override: int | None = None,
        max_records: int | None = None,
        dry_run: bool = False,
        output_dir: str = "data/output",
        model: str | None = None,
        auto_analyze: bool = True,
        incremental: bool = True,
        skip_delay: bool = False,
    ):
        """Initialize the scheduled research engine.

        Args:
            config_path: Path to queries configuration YAML.
            taxonomy_path: Path to taxonomy configuration YAML.
            interval_seconds: Search and analysis cycle interval in seconds (default: 3600s = 1 hour).
            limit_override: Optional override for query result limit.
            max_records: Optional maximum records to collect per cycle.
            dry_run: If True, executes without persisting files.
            output_dir: Target output directory for evidence and insight reports.
            model: Optional Groq model override.
            auto_analyze: If True, runs AI analysis on new evidence found in each cycle.
            incremental: If True, only analyzes newly discovered records and merges them.
            skip_delay: If True, skips network delay between query tasks (useful for tests).
        """
        self.config_path = config_path
        self.taxonomy_path = taxonomy_path
        self.interval_seconds = max(0.001, float(interval_seconds))
        self.limit_override = limit_override
        self.max_records = max_records
        self.dry_run = dry_run
        self.output_dir = output_dir
        self.model = model
        self.auto_analyze = auto_analyze
        self.incremental = incremental
        self.skip_delay = skip_delay

        self._stop_requested = False
        self._current_cycle = 0
        self._history: list[dict[str, Any]] = []

    def stop(self) -> None:
        """Signal the scheduler loop to stop after the current cycle or sleep."""
        logger.info("Stopping ScheduledResearchEngine...")
        self._stop_requested = True

    @property
    def is_running(self) -> bool:
        """Return True if the scheduler loop is actively running."""
        return not self._stop_requested

    def run_cycle(self, cycle_number: int = 1) -> dict[str, Any]:
        """Execute one complete cycle: Search Reddit -> Filter New -> Analyze Relevant -> Update Reports.

        Args:
            cycle_number: Sequence number of the current cycle.

        Returns:
            Dictionary containing cycle execution metrics, newly collected count,
            relevant results count, and updated dataset totals.
        """
        self._current_cycle = cycle_number
        cycle_start = datetime.now(timezone.utc)
        cycle_id = f"cycle_{cycle_number}_{cycle_start.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:4]}"

        logger.info("=" * 75)
        logger.info(f" SCHEDULED RESEARCH CYCLE #{cycle_number} — {cycle_start.strftime('%Y-%m-%d %H:%M:%S UTC')}")
        logger.info(f" Cycle ID:       {cycle_id}")
        logger.info(f" Interval:       {self.interval_seconds:.0f}s ({self.interval_seconds / 3600:.2f}h)")
        logger.info(f" Output Dir:     {self.output_dir}")
        logger.info(f" Auto-Analyze:   {self.auto_analyze}")
        logger.info("=" * 75)

        # 1. Load config
        config = load_config(self.config_path)
        setup_logging(log_level=config.logging.level, log_file=config.logging.log_file)

        # 2. Initialize search components
        query_engine = QueryEngine(config)
        reddit_client = RedditClient(config)
        dedup_index_path = f"{self.output_dir}/seen_ids.json"
        deduplicator = Deduplicator(index_path=dedup_index_path)

        starting_id = deduplicator.last_record_number + 1
        collector = PostCollector(
            max_comments=config.pipeline.max_comments_per_post,
            starting_id=starting_id,
            anonymize_authors=config.privacy.anonymize_authors,
            run_id=cycle_id,
        )
        structurer = DataStructurer(
            output_dir=self.output_dir,
            output_format=config.pipeline.output_format,
        )
        reporter = CollectionReporter(output_dir=self.output_dir)

        # 3. Read existing historical evidence to ensure append/zero-loss
        evidence_file = Path(self.output_dir) / "reddit_evidence.json"
        existing_records: list[EvidenceRecord] = []
        if evidence_file.is_file():
            try:
                existing_records, _ = load_v0_evidence_with_metadata(evidence_file)
                logger.info(f"Loaded {len(existing_records)} existing evidence records from {evidence_file}")
            except Exception as e:
                logger.warning(f"Could not load existing evidence from {evidence_file}: {e}. Will create fresh.")
                existing_records = []

        # 4. Generate & execute search tasks
        tasks = query_engine.generate_tasks(limit_override=self.limit_override)
        logger.info(f"Generated {len(tasks)} search tasks across configured subreddits.")

        new_records: list[EvidenceRecord] = []
        total_duplicates = 0
        total_raw = 0
        tasks_completed = 0
        tasks_failed = 0
        queries_executed: set[str] = set()

        if self.dry_run:
            logger.info("[DRY RUN] Simulating scheduled cycle tasks without network writes.")
            cycle_end = datetime.now(timezone.utc)
            duration = (cycle_end - cycle_start).total_seconds()
            dry_summary = {
                "cycle_number": cycle_number,
                "cycle_id": cycle_id,
                "status": "dry_run_complete",
                "tasks_planned": len(tasks),
                "new_records_collected": 0,
                "relevant_results_count": 0,
                "total_records": len(existing_records),
                "duration_seconds": round(duration, 2),
            }
            self._history.append(dry_summary)
            return dry_summary

        for i, (query, subreddit, params) in enumerate(tasks, 1):
            if self._stop_requested:
                logger.info("Stop requested. Terminating current search cycle tasks early.")
                break

            sub_display = f"r/{subreddit}" if subreddit else "r/all"
            sub_tier = params.get("subreddit_tier", "primary")
            query_limit = params.get("limit", 25)

            try:
                raw_posts = reddit_client.search(
                    query=query,
                    subreddit=subreddit,
                    sort=params.get("sort", "relevance"),
                    time_filter=params.get("time_filter", "all"),
                    limit=query_limit,
                )
                total_raw += len(raw_posts)

                batch_records = collector.collect_batch(
                    raw_posts,
                    search_query=query,
                    subreddit_tier=sub_tier,
                    include_comments=True,
                )

                unique, dup_count = deduplicator.filter(batch_records)
                total_duplicates += dup_count
                new_records.extend(unique)
                queries_executed.add(query)
                tasks_completed += 1

                if unique:
                    logger.info(f"  [{i}/{len(tasks)}] '{query}' in {sub_display}: Found {len(unique)} NEW record(s)!")

                if self.max_records and len(new_records) >= self.max_records:
                    logger.info(f"Reached max_records limit ({self.max_records}) for this cycle. Halting task loop.")
                    break

            except Exception as e:
                tasks_failed += 1
                logger.warning(f"Task failed for '{query}' in {sub_display}: {e}")

            finally:
                if i < len(tasks) and not self.skip_delay:
                    delay = config.pipeline.request_delay_seconds
                    if delay > 0:
                        time.sleep(min(delay, 0.5 if self.limit_override else delay))

        # 5. Persist collection results if new records were found
        cycle_end = datetime.now(timezone.utc)
        duration = (cycle_end - cycle_start).total_seconds()

        all_collected_records = existing_records + new_records
        metadata: dict[str, Any] = {
            "last_cycle_id": cycle_id,
            "cycle_number": cycle_number,
            "generated_at": cycle_end.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "cycle_started_at": cycle_start.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "duration_seconds": round(duration, 2),
            "new_records_in_cycle": len(new_records),
            "total_records": len(all_collected_records),
            "queries_executed": len(queries_executed),
            "duplicates_skipped": total_duplicates,
            "tasks_completed": tasks_completed,
            "tasks_failed": tasks_failed,
        }

        if new_records:
            logger.info(f"Discovered {len(new_records)} brand new evidence records in Cycle #{cycle_number}!")
            structurer.write(all_collected_records, metadata)
            deduplicator.save()
            report = reporter.generate_report(
                run_id=cycle_id,
                records=all_collected_records,
                queries_executed=len(queries_executed),
                total_raw_results=total_raw,
                duplicates_removed=total_duplicates,
                tasks_completed=tasks_completed,
                tasks_failed=tasks_failed,
                duration_seconds=duration,
            )
            reporter.save_report(report)
        else:
            logger.info(f"Cycle #{cycle_number}: 0 new Reddit posts found matching queries. Historical records intact ({len(existing_records)}).")

        # 6. Automatic AI Relevance Classification & Analysis
        new_analyzed: list[AnalyzedEvidenceRecord] = []
        relevant_records: list[AnalyzedEvidenceRecord] = []
        analysis_summary: dict[str, Any] = {}

        if self.auto_analyze and new_records:
            logger.info(f"Initiating AI research analysis for {len(new_records)} newly discovered records...")
            try:
                new_analyzed, relevant_records, analysis_summary = self._analyze_new_records(
                    new_records=new_records,
                    all_records=all_collected_records,
                )
            except Exception as e:
                logger.error(f"Error during AI analysis phase in cycle #{cycle_number}: {e}", exc_info=True)
        elif self.auto_analyze and not new_records:
            logger.info("Skipping AI analysis this cycle because no new records were collected.")

        cycle_summary = {
            "cycle_number": cycle_number,
            "cycle_id": cycle_id,
            "started_at": cycle_start.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "completed_at": cycle_end.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "duration_seconds": round(duration, 2),
            "new_records_collected": len(new_records),
            "total_historical_records": len(all_collected_records),
            "new_analyzed_count": len(new_analyzed),
            "new_relevant_results": len(relevant_records),
            "new_relevant_breakdown": {
                "relevant": sum(1 for r in new_analyzed if r.relevance_classification == "relevant"),
                "possibly_relevant": sum(1 for r in new_analyzed if r.relevance_classification == "possibly_relevant"),
                "irrelevant": sum(1 for r in new_analyzed if r.relevance_classification == "irrelevant"),
            },
            "tasks_completed": tasks_completed,
            "tasks_failed": tasks_failed,
            "next_run_seconds": self.interval_seconds,
        }

        self._history.append(cycle_summary)
        self._print_cycle_summary(cycle_summary, relevant_records)
        return cycle_summary

    def _analyze_new_records(
        self,
        new_records: list[EvidenceRecord],
        all_records: list[EvidenceRecord],
    ) -> tuple[list[AnalyzedEvidenceRecord], list[AnalyzedEvidenceRecord], dict[str, Any]]:
        """Run Groq AI analysis on newly collected records and merge with historical analysis."""
        taxonomy = load_taxonomy(self.taxonomy_path)
        api_key = os.environ.get("GROQ_API_KEY", "").strip()

        if not api_key:
            logger.warning("GROQ_API_KEY not configured. Skipping AI analysis.")
            return [], [], {}

        chosen_model = self.model or taxonomy.groq_analysis.model
        groq_client = GroqClient(
            api_key=api_key,
            model=chosen_model,
            temperature=taxonomy.groq_analysis.temperature,
            max_retries=taxonomy.groq_analysis.max_retries,
            timeout=taxonomy.groq_analysis.timeout_seconds,
        )

        analyzer = AIAnalyzer(groq_client=groq_client, taxonomy=taxonomy)
        logger.info(f"Running multi-task AI analyzer on {len(new_records)} new records using {chosen_model}...")
        new_analyzed = analyzer.analyze_batch(new_records)

        # Filter relevant results (tri-state: relevant or possibly_relevant)
        relevant_records = [
            r for r in new_analyzed
            if r.relevance_classification in ("relevant", "possibly_relevant")
        ]

        logger.info(
            f"Analysis complete: {len(relevant_records)} relevant/possibly relevant results found "
            f"out of {len(new_analyzed)} new records."
        )

        # Load existing analyzed evidence to merge
        analyzed_json_path = Path(self.output_dir) / "analyzed_evidence.json"
        existing_analyzed: list[AnalyzedEvidenceRecord] = []

        if analyzed_json_path.is_file():
            try:
                with open(analyzed_json_path, "r", encoding="utf-8") as f:
                    raw_list = json.load(f)
                if isinstance(raw_list, list):
                    existing_analyzed = [AnalyzedEvidenceRecord.from_dict(item) for item in raw_list]
                    logger.info(f"Loaded {len(existing_analyzed)} previously analyzed records from {analyzed_json_path}")
            except Exception as e:
                logger.warning(f"Could not load previous analyzed evidence: {e}. Will create fresh.")
                existing_analyzed = []

        # Merge deduplicated by record_id (latest analysis takes precedence)
        analyzed_by_id: dict[str, AnalyzedEvidenceRecord] = {
            r.record_id: r for r in existing_analyzed
        }
        for r in new_analyzed:
            analyzed_by_id[r.record_id] = r

        all_analyzed = list(analyzed_by_id.values())

        # Write merged analyzed evidence
        insight_reporter = InsightReporter(output_dir=self.output_dir)
        insight_reporter.write_analyzed_evidence(all_analyzed, output_dir=self.output_dir)

        # Re-aggregate patterns across all cumulative analyzed evidence
        aggregator = PatternAggregator(all_analyzed)
        summary = aggregator.generate_summary()

        report_file = insight_reporter.write_insight_report(
            aggregations_or_summary=summary,
            output_dir=self.output_dir,
            groq_model=chosen_model,
            v0_source_file=str(Path(self.output_dir) / "reddit_evidence.json"),
        )
        report = insight_reporter.load_insight_report(report_file)
        insight_reporter.write_markdown_report(report, output_dir=self.output_dir)

        # Copy to canonical reports/ folder
        try:
            if Path(self.output_dir).resolve() != Path("reports").resolve():
                insight_reporter.write_markdown_report(report, output_dir="reports")
        except Exception as e:
            logger.debug(f"Markdown report copy to reports/ skipped: {e}")

        return new_analyzed, relevant_records, summary

    def _print_cycle_summary(
        self,
        summary: dict[str, Any],
        relevant_records: list[AnalyzedEvidenceRecord],
    ) -> None:
        """Print clean formatted terminal summary for each scheduled cycle."""
        print("\n" + "=" * 75)
        print(f"  CYCLE #{summary['cycle_number']} SUMMARY REPORT")
        print("=" * 75)
        print(f"  Completed At:             {summary['completed_at']}")
        print(f"  Duration:                 {summary['duration_seconds']}s")
        print(f"  New Records Discovered:   {summary['new_records_collected']}")
        print(f"  Total Evidence in DB:     {summary['total_historical_records']}")
        print(f"  New Relevant Findings:    {summary['new_relevant_results']}")

        breakdown = summary.get("new_relevant_breakdown", {})
        print(f"    - Relevant:             {breakdown.get('relevant', 0)}")
        print(f"    - Possibly Relevant:    {breakdown.get('possibly_relevant', 0)}")
        print(f"    - Irrelevant (Filtered):{breakdown.get('irrelevant', 0)}")

        if relevant_records:
            print("\n  --- Discovered Relevant Retrieval Failures ---")
            for idx, r in enumerate(relevant_records[:5], 1):
                cues = ", ".join(r.memory_cues_present) if r.memory_cues_present else "none"
                stage = r.retrieval_failure_stage or "unspecified"
                print(f"  [{idx}] {r.record_id} ({r.relevance_classification}): \"{r.title[:65]}\"")
                print(f"      Stage: {stage} | Cues: {cues} | r/{r.subreddit}")
                if r.failure_evidence:
                    print(f"      Evidence: \"{r.failure_evidence[:90]}...\"")

        print("=" * 75 + "\n")

    def start(self, max_cycles: int | None = None) -> list[dict[str, Any]]:
        """Start the scheduled search and analysis loop.

        Runs continuously every interval_seconds until interrupted or max_cycles reached.

        Args:
            max_cycles: Optional maximum number of cycles to execute (default: unlimited).

        Returns:
            List of cycle summary reports for all completed cycles.
        """
        self._stop_requested = False

        # Set up signal handlers for graceful exit
        def _handle_signal(signum: int, frame: Any) -> None:
            logger.info("Received interrupt signal. Initiating graceful shutdown of scheduler...")
            self.stop()

        original_sigint = None
        original_sigterm = None
        try:
            original_sigint = signal.signal(signal.SIGINT, _handle_signal)
            if hasattr(signal, "SIGTERM"):
                original_sigterm = signal.signal(signal.SIGTERM, _handle_signal)
        except (ValueError, AttributeError):
            pass

        cycle = 1
        logger.info(
            f"ScheduledResearchEngine activated. Periodic interval: {self.interval_seconds:.0f}s "
            f"({self.interval_seconds / 3600:.2f} hours)."
        )

        try:
            while not self._stop_requested:
                cycle_start_time = time.time()
                try:
                    self.run_cycle(cycle_number=cycle)
                except Exception as e:
                    logger.error(f"Unhandled exception in research cycle #{cycle}: {e}", exc_info=True)
                    print(f"[ERROR] Cycle #{cycle} encountered an error: {e}. Waiting for next scheduled run.")

                if max_cycles is not None and cycle >= max_cycles:
                    logger.info(f"Target max_cycles ({max_cycles}) reached. Stopping scheduler.")
                    break

                if self._stop_requested:
                    break

                elapsed = time.time() - cycle_start_time
                sleep_needed = max(0.0, self.interval_seconds - elapsed)
                next_run_dt = datetime.now(timezone.utc) + timedelta(seconds=sleep_needed)

                logger.info(
                    f"Cycle #{cycle} finished. Next automated search scheduled for: "
                    f"{next_run_dt.strftime('%Y-%m-%d %H:%M:%S UTC')} (sleeping {sleep_needed:.1f}s)..."
                )

                # Sleep in small slices to respond promptly to stop requests or Ctrl+C
                wake_target = time.time() + sleep_needed
                while time.time() < wake_target and not self._stop_requested:
                    time.sleep(min(1.0, wake_target - time.time()))

                cycle += 1

        finally:
            # Restore original signal handlers
            try:
                if original_sigint is not None:
                    signal.signal(signal.SIGINT, original_sigint)
                if original_sigterm is not None and hasattr(signal, "SIGTERM"):
                    signal.signal(signal.SIGTERM, original_sigterm)
            except (ValueError, AttributeError):
                pass

        logger.info(f"ScheduledResearchEngine stopped. Executed {len(self._history)} cycle(s).")
        return self._history
