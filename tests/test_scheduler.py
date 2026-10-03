"""Unit and integration tests for the Scheduled Research Engine (Hourly Search & Analysis)."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.config_loader import load_config
from src.main import main, parse_cli_args
from src.models import AnalyzedEvidenceRecord, EvidenceRecord
from src.scheduler import ScheduledResearchEngine


@pytest.fixture
def mock_evidence_env(tmp_path: Path):
    """Set up temporary directory with valid config and initial evidence."""
    output_dir = tmp_path / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Pre-existing evidence
    initial_record = {
        "record_id": "RD_000001",
        "source": "reddit",
        "source_type": "reddit",
        "content_type": "post",
        "source_id": "t3_existing001",
        "subreddit": "googlephotos",
        "subreddit_tier": "primary",
        "title": "Old existing post",
        "raw_text": "I lost my photo from 2020.",
        "cleaned_text": "I lost my photo from 2020.",
        "preview_text": "I lost my photo...",
        "author": "user_old",
        "created_at": "2025-01-01T00:00:00Z",
        "retrieved_at": "2026-09-01T00:00:00Z",
        "url": "https://reddit.com/r/googlephotos/comments/existing001/",
        "query_used": "lost photo",
        "queries_matched": ["lost photo"],
        "score": 10,
        "num_comments": 1,
        "top_comments": [],
    }
    evidence_file = output_dir / "reddit_evidence.json"
    with open(evidence_file, "w", encoding="utf-8") as f:
        json.dump({"metadata": {"total_records": 1}, "records": [initial_record]}, f)

    seen_file = output_dir / "seen_ids.json"
    with open(seen_file, "w", encoding="utf-8") as f:
        json.dump(["reddit:t3_existing001", "t3_existing001"], f)

    return output_dir


def test_scheduler_initialization_defaults():
    """Verify default scheduler interval is 3600s (1 hour) with auto_analyze and incremental enabled."""
    engine = ScheduledResearchEngine()
    assert engine.interval_seconds == 3600.0
    assert engine.auto_analyze is True
    assert engine.incremental is True
    assert engine.is_running is True


def test_scheduler_custom_interval():
    """Verify custom interval configuration."""
    engine = ScheduledResearchEngine(interval_seconds=7200)
    assert engine.interval_seconds == 7200.0


def test_scheduler_cli_arguments():
    """Verify CLI arguments parsing for recurring schedule mode and intervals."""
    args = parse_cli_args([
        "--mode", "schedule",
        "--interval-hours", "1.5",
        "--max-cycles", "3",
    ])
    assert args.mode == "schedule"
    assert args.interval_hours == 1.5
    assert args.max_cycles == 3


def test_scheduler_run_cycle_dry_run(tmp_path: Path):
    """Dry run should validate planned tasks without writing files."""
    engine = ScheduledResearchEngine(
        dry_run=True,
        output_dir=str(tmp_path),
    )
    result = engine.run_cycle(cycle_number=1)
    assert result["status"] == "dry_run_complete"
    assert result["cycle_number"] == 1
    assert result["new_records_collected"] == 0


def test_scheduler_run_cycle_no_new_records(mock_evidence_env: Path):
    """When Reddit search yields only duplicate or 0 results, historical records are preserved."""
    engine = ScheduledResearchEngine(
        output_dir=str(mock_evidence_env),
        interval_seconds=3600.0,
        limit_override=1,
        skip_delay=True,
    )

    mock_tasks = [("lost photo", "googlephotos", {"limit": 1, "subreddit_tier": "primary"})]
    with patch("src.scheduler.QueryEngine.generate_tasks", return_value=mock_tasks), \
         patch("src.scheduler.RedditClient.search", return_value=[]):
        result = engine.run_cycle(cycle_number=1)

    assert result["new_records_collected"] == 0
    assert result["total_historical_records"] == 1
    assert result["new_relevant_results"] == 0

    # Verify original file untouched
    with open(mock_evidence_env / "reddit_evidence.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    assert len(data.get("records", [])) == 1


def test_scheduler_run_cycle_with_new_records_and_relevance(mock_evidence_env: Path):
    """Verify new records are collected, analyzed with AI, and relevant ones identified."""
    engine = ScheduledResearchEngine(
        output_dir=str(mock_evidence_env),
        interval_seconds=3600.0,
        limit_override=1,
        skip_delay=True,
    )

    # Mock raw Reddit post returned by search
    mock_post = MagicMock()
    mock_post.id = "new_post_999"
    mock_post.title = "Can't find beach picture with red umbrella"
    mock_post.selftext = "I remember a vacation photo with a bright red umbrella on a beach, but keyword search fails."
    mock_post.author = "beach_goer"
    mock_post.subreddit = "googlephotos"
    mock_post.created_utc = 1700000000.0
    mock_post.score = 42
    mock_post.num_comments = 2
    mock_post.permalink = "/r/googlephotos/comments/new_post_999/"
    mock_post.comments = []
    mock_post.removed_by_category = None

    # Mock AI analysis result: classified as 'relevant'
    mock_analyzed = AnalyzedEvidenceRecord(
        record_id="RD_000002",
        source_id="t3_new_post_999",
        title="Can't find beach picture with red umbrella",
        raw_text="I remember a vacation photo with a bright red umbrella...",
        url="https://reddit.com/r/googlephotos/comments/new_post_999/",
        is_relevant=True,
        relevance_classification="relevant",
        relevance_confidence=0.92,
        relevance_reasoning="Clear episodic memory cue failure.",
        target_media="personal_photo",
        memory_cues_present=["object", "visual_detail"],
        retrieval_failure_stage="memory_to_query",
        retrieval_failure_point="vocabulary_mismatch",
        failure_evidence="keyword search fails",
        workarounds_used=["endless_scrolling"],
    )

    mock_tasks = [("beach photo", "googlephotos", {"limit": 1, "subreddit_tier": "primary"})]
    with patch("src.scheduler.QueryEngine.generate_tasks", return_value=mock_tasks), \
         patch("src.scheduler.RedditClient.search", return_value=[mock_post]), \
         patch("src.scheduler.AIAnalyzer.analyze_batch", return_value=[mock_analyzed]):
        result = engine.run_cycle(cycle_number=1)

    assert result["new_records_collected"] == 1
    assert result["total_historical_records"] == 2
    assert result["new_relevant_results"] == 1
    assert result["new_relevant_breakdown"]["relevant"] == 1

    # Verify both historical and new records saved to disk
    with open(mock_evidence_env / "reddit_evidence.json", "r", encoding="utf-8") as f:
        ev_data = json.load(f)
    assert len(ev_data.get("records", [])) == 2

    # Verify analyzed evidence saved
    with open(mock_evidence_env / "analyzed_evidence.json", "r", encoding="utf-8") as f:
        an_data = json.load(f)
    assert len(an_data) >= 1
    assert an_data[-1]["record_id"] == "RD_000002"


def test_scheduler_start_max_cycles(tmp_path: Path):
    """Scheduler loops up to max_cycles with short interval and stops cleanly."""
    engine = ScheduledResearchEngine(
        dry_run=True,
        interval_seconds=0.01,
        output_dir=str(tmp_path),
    )
    history = engine.start(max_cycles=2)
    assert len(history) == 2
    assert history[0]["cycle_number"] == 1
    assert history[1]["cycle_number"] == 2


def test_scheduler_stop_method():
    """Calling stop() sets the stop flag."""
    engine = ScheduledResearchEngine(interval_seconds=3600)
    assert engine.is_running is True
    engine.stop()
    assert engine.is_running is False


def test_main_cli_schedule_mode():
    """Verify main() runs schedule mode with max_cycles."""
    result = main(
        mode="schedule",
        dry_run=True,
        max_cycles=1,
        interval_seconds=0.01,
    )
    assert result["mode"] == "schedule"
    assert result["cycles_completed"] == 1


def test_scheduler_config_loader_integration():
    """Verify AppConfig parses scheduler section with interval_hours."""
    config = load_config("config/queries.yaml")
    assert hasattr(config, "scheduler")
    assert config.scheduler.interval_hours == 1.0
    assert config.scheduler.auto_analyze is True
    assert config.scheduler.incremental is True
