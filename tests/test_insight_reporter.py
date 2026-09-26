"""Unit tests for Phase 14 InsightReporter serialization and reporting layer."""

import csv
import json
import pytest
from pathlib import Path

from src.insight_reporter import (
    InsightReporter,
    ANALYZED_CSV_COLUMNS,
    DEFAULT_RESEARCH_QUESTION,
)
from src.models import AnalyzedEvidenceRecord


@pytest.fixture
def sample_analyzed_records():
    """Create sample AnalyzedEvidenceRecord fixtures."""
    rec1 = AnalyzedEvidenceRecord(
        record_id="RD_000001",
        source_id="t3_abc123",
        title="Can't find old photo from beach trip",
        raw_text="I remember taking a photo at a beach bonfire in 2018 with my college roommate, but scrolling through 20,000 photos took 2 hours and I couldn't find it. Very frustrating experience.",
        url="https://reddit.com/r/googlephotos/comments/abc123/beach_trip/",
        author="beach_fan_99",
        subreddit="googlephotos",
        created_at="2025-03-12T14:23:00Z",
        retrieved_at="2026-09-16T20:00:00Z",
        queries_matched=["can't find old photo", "google photos search failed"],
        is_relevant=True,
        relevance_confidence=0.95,
        relevance_reasoning="User describes clear failure retrieving a personal photo using partial episodic memory.",
        target_media="personal_photo",
        memory_cues_present=["person", "place_location", "activity_action", "temporal_epoch"],
        memory_cue_details={
            "person": "college roommate",
            "place_location": "beach",
            "activity_action": "bonfire",
            "temporal_epoch": "2018 / college",
        },
        retrieval_failure_point="volume_overload",
        failure_evidence="scrolling through 20,000 photos took 2 hours and I couldn't find it",
        workarounds_used=["endless_scrolling"],
        friction_experienced=["time_wasted", "frustration_with_search_tool"],
        desired_outcome="Show photo to friend",
        analyzed_at="2026-09-25T12:00:00Z",
        model_used="llama-3.3-70b-versatile",
    )

    rec2 = AnalyzedEvidenceRecord(
        record_id="RD_000002",
        source_id="t3_xyz789",
        title="Google photos screenshot missing",
        raw_text="I saved a recipe screenshot last year around Thanksgiving but searching 'pumpkin pie recipe' brings up 0 results.",
        url="https://reddit.com/r/googlephotos/comments/xyz789/recipe_screenshot/",
        author="baker_42",
        subreddit="googlephotos",
        created_at="2025-04-10T09:15:00Z",
        retrieved_at="2026-09-16T20:00:00Z",
        queries_matched=["google photos search text in screenshot"],
        is_relevant=True,
        relevance_confidence=0.92,
        relevance_reasoning="User cannot locate screenshot containing text recipe.",
        target_media="screenshot",
        memory_cues_present=["text_in_image", "event_occasion"],
        memory_cue_details={
            "text_in_image": "pumpkin pie recipe",
            "event_occasion": "Thanksgiving",
        },
        retrieval_failure_point="screenshot_clutter",
        failure_evidence="searching 'pumpkin pie recipe' brings up 0 results",
        workarounds_used=["keyword_guessing", "peer_inquiry"],
        friction_experienced=["time_wasted"],
        desired_outcome="Find recipe to bake pie",
        analyzed_at="2026-09-25T12:01:00Z",
        model_used="llama-3.3-70b-versatile",
    )

    rec3 = AnalyzedEvidenceRecord(
        record_id="RD_000003",
        source_id="t3_irr001",
        title="How do I cancel my Google One subscription?",
        raw_text="Need help canceling Google One storage plan before renewal.",
        url="https://reddit.com/r/googlephotos/comments/irr001/cancel_sub/",
        author="storage_user",
        subreddit="googlephotos",
        created_at="2025-05-01T11:00:00Z",
        retrieved_at="2026-09-16T20:00:00Z",
        queries_matched=["google photos storage"],
        is_relevant=False,
        relevance_confidence=0.1,
        relevance_reasoning="Billing and subscription question, not a vague retrieval failure.",
        target_media="",
        memory_cues_present=[],
        memory_cue_details={},
        retrieval_failure_point="",
        failure_evidence="",
        workarounds_used=[],
        friction_experienced=[],
        desired_outcome="",
        analyzed_at="2026-09-25T12:02:00Z",
        model_used="llama-3.3-70b-versatile",
    )

    return [rec1, rec2, rec3]


@pytest.fixture
def sample_summary_report():
    """Create sample PatternAggregator summary dictionary."""
    return {
        "statistics": {
            "total_records_ingested": 3,
            "relevant_evidence_count": 2,
            "relevance_rate": 0.667,
        },
        "distributions": {
            "top_memory_cues": {
                "person": 1,
                "place_location": 1,
                "activity_action": 1,
                "temporal_epoch": 1,
                "text_in_image": 1,
                "event_occasion": 1,
            },
            "retrieval_failure_points": {
                "volume_overload": 1,
                "screenshot_clutter": 1,
            },
            "top_workarounds": {
                "endless_scrolling": 1,
                "keyword_guessing": 1,
                "peer_inquiry": 1,
            },
            "target_media_types": {
                "personal_photo": 1,
                "screenshot": 1,
            },
            "friction_types": {
                "time_wasted": 2,
                "frustration_with_search_tool": 1,
            },
        },
        "cross_tabulations": {
            "cues_vs_failures": {
                "temporal_epoch": {"volume_overload": 1},
                "text_in_image": {"screenshot_clutter": 1},
            }
        },
        "recurring_patterns": [
            {
                "pattern_id": "PAT_001",
                "name": "Chronological Fatigue in Large Galleries",
                "prevalence_count": 1,
                "prevalence_percentage": 50.0,
                "summary": "Users retain episodic memory but timeline search forces hours of manual scrolling.",
                "supporting_evidence": [
                    {
                        "record_id": "RD_000001",
                        "url": "https://reddit.com/r/googlephotos/comments/abc123/beach_trip/",
                        "quote": "scrolling through 20,000 photos took 2 hours and I couldn't find it",
                    }
                ],
            },
            {
                "pattern_id": "PAT_002",
                "name": "Untagged Screenshot & Document Clutter",
                "prevalence_count": 1,
                "prevalence_percentage": 50.0,
                "summary": "Informational media like screenshots get lost and OCR search fails to surface them.",
                "supporting_evidence": [
                    {
                        "record_id": "RD_000002",
                        "url": "https://reddit.com/r/googlephotos/comments/xyz789/recipe_screenshot/",
                        "quote": "searching 'pumpkin pie recipe' brings up 0 results",
                    }
                ],
            },
        ],
    }


def test_write_analyzed_evidence_json(tmp_path, sample_analyzed_records):
    """Verify write_analyzed_evidence writes valid nested JSON with correct schema."""
    reporter = InsightReporter(output_dir=tmp_path)
    res = reporter.write_analyzed_evidence(sample_analyzed_records, formats=["json"])

    json_path = tmp_path / "analyzed_evidence.json"
    assert json_path.exists()
    assert res["json_file"] == str(json_path)
    assert res["total_records"] == 3

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert isinstance(data, list)
    assert len(data) == 3

    first = data[0]
    assert first["record_id"] == "RD_000001"
    assert first["source_id"] == "t3_abc123"
    assert "analysis" in first
    assert first["analysis"]["is_relevant"] is True
    assert first["analysis"]["target_media"] == "personal_photo"
    assert "person" in first["analysis"]["memory_cues_present"]
    assert first["analysis"]["memory_cue_details"]["place_location"] == "beach"
    assert first["analysis"]["retrieval_failure_point"] == "volume_overload"


def test_write_analyzed_evidence_csv(tmp_path, sample_analyzed_records):
    """Verify write_analyzed_evidence writes flat CSV with zero text truncation and correct headers."""
    reporter = InsightReporter(output_dir=tmp_path)
    res = reporter.write_analyzed_evidence(sample_analyzed_records, formats=["csv"])

    csv_path = tmp_path / "analyzed_evidence.csv"
    assert csv_path.exists()
    assert res["csv_file"] == str(csv_path)

    with open(csv_path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)

    assert fieldnames == ANALYZED_CSV_COLUMNS
    assert len(rows) == 3

    row1 = rows[0]
    assert row1["record_id"] == "RD_000001"
    # Verify ZERO text truncation
    assert row1["raw_text"] == sample_analyzed_records[0].raw_text
    assert row1["is_relevant"] == "True"
    assert row1["relevance_classification"] == "relevant"
    assert row1["retrieval_failure_stage"] == "memory_to_query"
    assert "person; place_location" in row1["memory_cues_present"]
    assert "endless_scrolling" in row1["workarounds_used"]
    assert row1["retrieval_failure_point"] == "volume_overload"

    # Verify JSON details in CSV cell
    details = json.loads(row1["memory_cue_details"])
    assert details["person"] == "college roommate"


def test_write_analyzed_evidence_both_and_dict_input(tmp_path, sample_analyzed_records):
    """Verify write_analyzed_evidence can accept dict records and writes both JSON and CSV."""
    reporter = InsightReporter(output_dir=tmp_path)
    dict_records = [r.to_dict() for r in sample_analyzed_records]

    res = reporter.write_analyzed_evidence(dict_records, formats="both")
    assert "json_file" in res
    assert "csv_file" in res
    assert len(res["files_written"]) == 2

    # Verify reload
    loaded = reporter.load_analyzed_evidence(res["json_file"])
    assert len(loaded) == 3
    assert loaded[0].record_id == "RD_000001"
    assert loaded[0].is_relevant is True


def test_write_insight_report_schema_and_citations(tmp_path, sample_summary_report):
    """Verify write_insight_report writes valid JSON matching research architecture schema."""
    reporter = InsightReporter(output_dir=tmp_path)
    report_file = reporter.write_insight_report(
        aggregations_or_summary=sample_summary_report,
        groq_model="llama-3.3-70b-versatile",
        v0_source_file="data/output/reddit_evidence.json",
    )

    assert report_file.exists()

    report = reporter.load_insight_report(report_file)
    assert "report_metadata" in report
    assert "research_question" in report
    assert "executive_summary" in report
    assert "distributions" in report
    assert "cross_tabulations" in report
    assert "recurring_patterns" in report

    # Verify metadata fields
    meta = report["report_metadata"]
    assert meta["total_records_ingested"] == 3
    assert meta["relevant_evidence_count"] == 2
    assert meta["relevance_rate"] == 0.667
    assert meta["groq_model_used"] == "llama-3.3-70b-versatile"
    assert meta["v0_source_file"] == "data/output/reddit_evidence.json"

    # Verify research question
    assert report["research_question"] == DEFAULT_RESEARCH_QUESTION

    # Verify recurring patterns have valid citations
    patterns = report["recurring_patterns"]
    assert len(patterns) == 2
    first_pattern = patterns[0]
    assert first_pattern["pattern_id"] == "PAT_001"
    assert len(first_pattern["supporting_evidence"]) > 0

    citation = first_pattern["supporting_evidence"][0]
    assert citation["record_id"] == "RD_000001"
    assert citation["url"].startswith("https://")
    assert "scrolling through 20,000 photos" in citation["quote"]


def test_auto_create_output_dir(tmp_path, sample_analyzed_records, sample_summary_report):
    """Verify reporter automatically creates deep nested output directory if missing."""
    deep_dir = tmp_path / "deep" / "nested" / "reports"
    assert not deep_dir.exists()

    reporter = InsightReporter(output_dir=deep_dir)
    res = reporter.write_analyzed_evidence(sample_analyzed_records)
    rep_path = reporter.write_insight_report(sample_summary_report)

    assert deep_dir.exists()
    assert Path(res["json_file"]).exists()
    assert Path(res["csv_file"]).exists()
    assert rep_path.exists()


def test_print_summary_runs_cleanly(capsys, sample_summary_report, tmp_path):
    """Verify print_summary produces structured human-readable text."""
    reporter = InsightReporter(output_dir=tmp_path)
    rep_path = reporter.write_insight_report(sample_summary_report)
    report = reporter.load_insight_report(rep_path)

    reporter.print_summary(report)
    captured = capsys.readouterr().out

    assert "GOOGLE PHOTOS VAGUE-MEMORY RETRIEVAL" in captured
    assert "PAT_001" in captured
    assert "RD_000001" in captured
    assert "Top Memory Cues:" in captured


def test_write_markdown_report(tmp_path, sample_summary_report):
    """Verify write_markdown_report formats executive markdown with cognitive failure stages and citations."""
    reporter = InsightReporter(output_dir=tmp_path)
    rep_path = reporter.write_insight_report(sample_summary_report)
    report = reporter.load_insight_report(rep_path)

    md_path = reporter.write_markdown_report(report)
    assert md_path.exists()

    content = md_path.read_text(encoding="utf-8")
    assert "# Executive Research Insight Report" in content
    assert "1. Central Research Question" in content
    assert "3. Relevance Classification Breakdown" in content
    assert "4. Cognitive Retrieval Failure Breakdown" in content
    assert "5. Structure of Human Visual Memory" in content
    assert "7. Synthesized Recurring Patterns & Evidence Citations" in content
    assert "RD_000001" in content
    assert "PAT_001" in content

