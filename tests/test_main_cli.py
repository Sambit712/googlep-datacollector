"""Unit and integration tests for Phase 15 Main CLI and Pipeline Orchestrator."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.main import main, parse_cli_args, run_analysis_pipeline
from src.models import AnalyzedEvidenceRecord, EvidenceRecord


@pytest.fixture
def mock_v0_evidence_file(tmp_path: Path) -> Path:
    """Create a temporary valid V0 evidence JSON file."""
    evidence_path = tmp_path / "reddit_evidence.json"
    records = [
        {
            "record_id": f"RD_{i:06d}",
            "source": "reddit",
            "source_type": "reddit",
            "content_type": "post",
            "source_id": f"t3_test{i}",
            "subreddit": "googlephotos",
            "subreddit_tier": "primary",
            "title": f"Test title {i}",
            "raw_text": f"Raw text content {i} describing vague photo retrieval memory.",
            "cleaned_text": f"Raw text content {i} describing vague photo retrieval memory.",
            "preview_text": f"Raw text content {i}...",
            "author": f"user_{i}",
            "created_at": "2025-01-01T00:00:00Z",
            "retrieved_at": "2026-09-20T00:00:00Z",
            "url": f"https://reddit.com/r/googlephotos/comments/test{i}/",
            "query_used": "can't find photo",
            "queries_matched": ["can't find photo"],
            "score": 10,
            "num_comments": 2,
            "top_comments": [],
        }
        for i in range(1, 6)
    ]
    payload = {
        "metadata": {"total_records": len(records)},
        "records": records,
    }
    with open(evidence_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    return evidence_path


def test_parse_cli_args_defaults():
    """Verify default CLI arguments."""
    args = parse_cli_args([])
    assert args.mode == "collect"
    assert args.config == "config/queries.yaml"
    assert args.taxonomy == "config/taxonomy.yaml"
    assert args.input == "data/output/reddit_evidence.json"
    assert args.sample is None
    assert args.dry_run is False
    assert args.limit is None
    assert args.max_records is None


def test_parse_cli_args_custom():
    """Verify parsing custom CLI arguments."""
    args = parse_cli_args([
        "--mode", "analyze",
        "--sample", "10",
        "--dry-run",
        "--taxonomy", "custom/taxonomy.yaml",
        "--input", "custom/evidence.json",
        "--config", "custom/queries.yaml",
        "--limit", "5",
        "--max-records", "100",
    ])
    assert args.mode == "analyze"
    assert args.sample == 10
    assert args.dry_run is True
    assert args.taxonomy == "custom/taxonomy.yaml"
    assert args.input == "custom/evidence.json"
    assert args.config == "custom/queries.yaml"
    assert args.limit == 5
    assert args.max_records == 100


def test_parse_cli_args_invalid_mode():
    """Verify invalid mode raises system exit with error code."""
    with pytest.raises(SystemExit):
        parse_cli_args(["--mode", "invalid_mode"])


def test_main_invalid_mode_raises():
    """Calling main with unrecognized mode raises ValueError."""
    with pytest.raises(ValueError, match="Invalid mode"):
        main(mode="unsupported")


def test_run_analysis_pipeline_missing_groq_key(monkeypatch, tmp_path):
    """Missing GROQ_API_KEY raises ValueError in analyze mode."""
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    with pytest.raises(ValueError, match="GROQ_API_KEY environment variable is required"):
        run_analysis_pipeline(
            taxonomy_path="config/taxonomy.yaml",
            input_path="data/output/reddit_evidence.json",
        )


def test_run_analysis_pipeline_missing_input_file(monkeypatch, tmp_path):
    """Non-existent input evidence file raises FileNotFoundError."""
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test_key_12345")

    with patch("src.main.GroqClient") as mock_groq_cls:
        mock_client = MagicMock()
        mock_client.health_check.return_value = True
        mock_groq_cls.return_value = mock_client

        with pytest.raises(FileNotFoundError, match="V0 evidence file not found"):
            run_analysis_pipeline(
                taxonomy_path="config/taxonomy.yaml",
                input_path=str(tmp_path / "non_existent.json"),
            )


def test_run_analysis_pipeline_health_check_failure(monkeypatch, mock_v0_evidence_file):
    """Failed Groq health check raises RuntimeError."""
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test_key_12345")

    with patch("src.main.GroqClient") as mock_groq_cls:
        mock_client = MagicMock()
        mock_client.health_check.return_value = False
        mock_groq_cls.return_value = mock_client

        with pytest.raises(RuntimeError, match="Groq API health check failed"):
            run_analysis_pipeline(
                taxonomy_path="config/taxonomy.yaml",
                input_path=str(mock_v0_evidence_file),
            )


def test_run_analysis_pipeline_dry_run_success(monkeypatch, mock_v0_evidence_file, tmp_path):
    """Dry-run analysis completes successfully without persisting files to disk."""
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test_key_12345")
    output_dir = tmp_path / "dry_run_out"

    # Mock GroqClient and AIAnalyzer
    with patch("src.main.GroqClient") as mock_groq_cls:
        mock_client = MagicMock()
        mock_client.health_check.return_value = True
        mock_groq_cls.return_value = mock_client

        with patch("src.main.AIAnalyzer") as mock_analyzer_cls:
            mock_analyzer = MagicMock()

            def mock_analyze_batch(records, on_progress=None):
                return [
                    AnalyzedEvidenceRecord(
                        record_id=r.record_id,
                        source_id=r.source_id,
                        title=r.title,
                        raw_text=r.raw_text,
                        url=r.url,
                        is_relevant=True,
                        relevance_confidence=0.9,
                        relevance_reasoning="Relevant retrieval question",
                        target_media="personal_photo",
                        memory_cues_present=["person", "temporal_epoch"],
                        retrieval_failure_point="volume_overload",
                        failure_evidence="scrolling took hours",
                        workarounds_used=["endless_scrolling"],
                        friction_experienced=["time_wasted"],
                        desired_outcome="find photo",
                    )
                    for r in records
                ]

            mock_analyzer.analyze_batch.side_effect = mock_analyze_batch
            mock_analyzer_cls.return_value = mock_analyzer

            report = run_analysis_pipeline(
                taxonomy_path="config/taxonomy.yaml",
                input_path=str(mock_v0_evidence_file),
                sample=3,
                dry_run=True,
                output_dir=str(output_dir),
            )

            assert report is not None
            assert "report_metadata" in report
            assert report["report_metadata"]["is_dry_run"] is True
            assert report["report_metadata"]["total_records_ingested"] == 3
            assert report["report_metadata"]["relevant_evidence_count"] == 3

            # Ensure no files were written to output_dir
            assert not output_dir.exists()


def test_run_analysis_pipeline_writes_files(monkeypatch, mock_v0_evidence_file, tmp_path):
    """Full analysis writes analyzed_evidence.json, .csv, and insight_report.json."""
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test_key_12345")
    output_dir = tmp_path / "actual_out"

    with patch("src.main.GroqClient") as mock_groq_cls:
        mock_client = MagicMock()
        mock_client.health_check.return_value = True
        mock_groq_cls.return_value = mock_client

        with patch("src.main.AIAnalyzer") as mock_analyzer_cls:
            mock_analyzer = MagicMock()

            def mock_analyze_batch(records, on_progress=None):
                return [
                    AnalyzedEvidenceRecord(
                        record_id=r.record_id,
                        source_id=r.source_id,
                        title=r.title,
                        raw_text=r.raw_text,
                        url=r.url,
                        is_relevant=True,
                        relevance_confidence=0.95,
                        relevance_reasoning="User vague query",
                        target_media="screenshot",
                        memory_cues_present=["text_in_image"],
                        retrieval_failure_point="screenshot_clutter",
                        failure_evidence="could not find screenshot",
                        workarounds_used=["keyword_guessing"],
                        friction_experienced=["time_wasted"],
                        desired_outcome="find screenshot",
                    )
                    for r in records
                ]

            mock_analyzer.analyze_batch.side_effect = mock_analyze_batch
            mock_analyzer_cls.return_value = mock_analyzer

            report = run_analysis_pipeline(
                taxonomy_path="config/taxonomy.yaml",
                input_path=str(mock_v0_evidence_file),
                sample=2,
                dry_run=False,
                output_dir=str(output_dir),
            )

            assert report is not None
            assert (output_dir / "analyzed_evidence.json").exists()
            assert (output_dir / "analyzed_evidence.csv").exists()
            assert (output_dir / "insight_report.json").exists()

            with open(output_dir / "analyzed_evidence.json", "r", encoding="utf-8") as f:
                data = json.load(f)
                assert len(data) == 2


def test_main_mode_both_orchestration(monkeypatch):
    """Verify main with mode='both' triggers collection then analysis."""
    with patch("src.main.run_collection_pipeline") as mock_coll:
        mock_coll.return_value = {"collection_summary": "done"}
        with patch("src.main.run_analysis_pipeline") as mock_ana:
            mock_ana.return_value = {"analysis_summary": "done"}

            res = main(mode="both")

            assert res["mode"] == "both"
            assert res["collection"]["collection_summary"] == "done"
            assert res["analysis"]["analysis_summary"] == "done"
            mock_coll.assert_called_once()
            mock_ana.assert_called_once()
