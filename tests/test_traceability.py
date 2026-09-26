"""Traceability, Schema Conformance, and Invariant Verification Test Suite.

Validates the unbroken verification chain:
Research Insight (insight_report.json)
  -> V1 Analysis Record (analyzed_evidence.json)
  -> V0 Source Evidence (reddit_evidence.json)
  -> Raw Reddit Text & URL

Also verifies zero-mutation immutability guarantees for V0 datasets.
"""

import hashlib
import json
import re
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from src.evidence_loader import get_file_hash, load_v0_evidence
from src.main import run_analysis_pipeline
from src.models import AnalyzedEvidenceRecord


def verify_traceability_chain(
    insight_report: dict[str, Any],
    analyzed_records: list[dict[str, Any]],
    v0_records: list[dict[str, Any]],
) -> tuple[bool, list[str]]:
    """Verify the 5-stage traceability chain across all V1 research artifacts.

    Returns:
        (is_valid, list_of_errors)
    """
    errors: list[str] = []

    # Map records by record_id
    analyzed_map: dict[str, dict[str, Any]] = {
        r.get("record_id", ""): r for r in analyzed_records if r.get("record_id")
    }
    v0_map: dict[str, dict[str, Any]] = {
        r.get("record_id", ""): r for r in v0_records if r.get("record_id")
    }

    # 1. Verify every cited record_id in insight_report exists in analyzed_evidence.json
    patterns = insight_report.get("recurring_patterns", [])
    for p in patterns:
        p_id = p.get("pattern_id", "UNKNOWN")
        citations = p.get("supporting_evidence", [])
        if not citations:
            errors.append(f"Pattern {p_id} has no supporting evidence citations.")

        for c in citations:
            rec_id = c.get("record_id", "")
            if not rec_id:
                errors.append(f"Pattern {p_id} citation missing record_id: {c}")
                continue

            if rec_id not in analyzed_map:
                errors.append(
                    f"Pattern {p_id} cites record_id '{rec_id}' not found in analyzed_evidence.json"
                )
                continue

            analyzed_rec = analyzed_map[rec_id]

            # 2. Verify cited record_id exists in v0_records
            if rec_id not in v0_map:
                errors.append(
                    f"Analyzed record '{rec_id}' cited by {p_id} not found in source reddit_evidence.json"
                )
                continue

            v0_rec = v0_map[rec_id]

            # 3. Verify URLs match and are valid Reddit URLs
            cite_url = c.get("url", "")
            v0_url = v0_rec.get("url", "") or v0_rec.get("permalink", "")
            if cite_url and v0_url and cite_url != v0_url:
                errors.append(
                    f"URL mismatch for '{rec_id}': citation has '{cite_url}', source has '{v0_url}'"
                )

            if not (v0_url.startswith("https://") and "reddit.com" in v0_url):
                errors.append(f"Source URL for '{rec_id}' is not a valid Reddit URL: {v0_url}")

            # 4. Verify citation quote is substantiated by source text
            quote = c.get("quote", "").strip()
            if quote:
                raw_text = v0_rec.get("raw_text", "") or v0_rec.get("selftext", "")
                title = v0_rec.get("title", "")
                failure_ev = (
                    analyzed_rec.get("analysis", {}).get("failure_evidence", "")
                    if "analysis" in analyzed_rec
                    else analyzed_rec.get("failure_evidence", "")
                )
                combined = f"{title} {raw_text} {failure_ev}".lower()
                # Check that at least significant tokens of the quote appear in source text
                quote_words = [w.lower() for w in re.findall(r"\w+", quote) if len(w) > 3]
                if quote_words:
                    matched = sum(1 for w in quote_words if w in combined)
                    if matched / len(quote_words) < 0.3:
                        errors.append(
                            f"Quote for '{rec_id}' not substantiated in source text: '{quote}'"
                        )

    # 5. Verify every record in analyzed_evidence maps to v0_evidence
    for rec_id, a_rec in analyzed_map.items():
        if rec_id not in v0_map:
            errors.append(f"Analyzed record '{rec_id}' has no matching V0 evidence record.")

    return len(errors) == 0, errors


@pytest.fixture
def mock_dataset(tmp_path: Path):
    """Fixture providing a mock V0 dataset, V1 analyzed records, and insight report."""
    v0_file = tmp_path / "reddit_evidence.json"
    v0_data = [
        {
            "record_id": f"RD_{i:06d}",
            "source_id": f"t3_post{i}",
            "title": f"Can't locate photo {i}",
            "raw_text": f"Looking for beach bonfire photo taken in 2018 with my friend. Scrolled for hours without finding it.",
            "url": f"https://www.reddit.com/r/googlephotos/comments/post{i}/cant_find/",
            "author": f"user_{i}",
            "subreddit": "googlephotos",
            "created_at": "2025-01-01T12:00:00Z",
            "retrieved_at": "2026-09-16T12:00:00Z",
            "queries_matched": ["can't find photo"],
        }
        for i in range(1, 4)
    ]

    with open(v0_file, "w", encoding="utf-8") as f:
        json.dump({"records": v0_data}, f, indent=2)

    analyzed_data = [
        {
            "record_id": r["record_id"],
            "source_id": r["source_id"],
            "title": r["title"],
            "raw_text": r["raw_text"],
            "url": r["url"],
            "author": r["author"],
            "subreddit": r["subreddit"],
            "created_at": r["created_at"],
            "retrieved_at": r["retrieved_at"],
            "queries_matched": r["queries_matched"],
            "analyzed_at": "2026-09-25T12:00:00Z",
            "model_used": "llama-3.3-70b-versatile",
            "analysis": {
                "is_relevant": True,
                "relevance_confidence": 0.95,
                "relevance_reasoning": "Clear retrieval failure",
                "target_media": "personal_photo",
                "memory_cues_present": ["person", "place_location", "temporal_epoch"],
                "memory_cue_details": {"place_location": "beach bonfire"},
                "retrieval_failure_point": "volume_overload",
                "failure_evidence": "Scrolled for hours without finding it",
                "workarounds_used": ["endless_scrolling"],
                "friction_experienced": ["time_wasted"],
                "desired_outcome": "find photo",
            },
        }
        for r in v0_data
    ]

    insight_data = {
        "report_metadata": {
            "generated_at": "2026-09-25T12:00:00Z",
            "v0_source_file": str(v0_file),
            "total_records_ingested": 3,
            "relevant_evidence_count": 3,
            "relevance_rate": 1.0,
            "groq_model_used": "llama-3.3-70b-versatile",
        },
        "research_question": "Why does photo retrieval fail when users remember a photo but cannot precisely describe it?",
        "executive_summary": "Users struggle with large libraries.",
        "distributions": {
            "top_memory_cues": {"person": 3, "place_location": 3},
            "retrieval_failure_points": {"volume_overload": 3},
            "top_workarounds": {"endless_scrolling": 3},
        },
        "cross_tabulations": {},
        "recurring_patterns": [
            {
                "pattern_id": "PAT_001",
                "name": "Chronological Fatigue",
                "prevalence_count": 3,
                "prevalence_percentage": 100.0,
                "summary": "Users scroll endlessly for hours.",
                "supporting_evidence": [
                    {
                        "record_id": "RD_000001",
                        "url": "https://www.reddit.com/r/googlephotos/comments/post1/cant_find/",
                        "quote": "Scrolled for hours without finding it",
                    }
                ],
            }
        ],
    }

    return v0_file, v0_data, analyzed_data, insight_data


def test_traceability_chain_valid(mock_dataset):
    """Verify unbroken 5-stage traceability chain on valid dataset."""
    _, v0_data, analyzed_data, insight_data = mock_dataset
    is_valid, errors = verify_traceability_chain(insight_data, analyzed_data, v0_data)
    assert is_valid, f"Traceability chain failed: {errors}"
    assert len(errors) == 0


def test_traceability_flags_orphan_citation(mock_dataset):
    """Verify broken link is detected when an insight pattern cites a non-existent record_id."""
    _, v0_data, analyzed_data, insight_data = mock_dataset

    # Introduce fabricated citation
    insight_data["recurring_patterns"][0]["supporting_evidence"].append({
        "record_id": "RD_999999",
        "url": "https://www.reddit.com/r/googlephotos/comments/fake/",
        "quote": "completely fake quote",
    })

    is_valid, errors = verify_traceability_chain(insight_data, analyzed_data, v0_data)
    assert not is_valid
    assert any("RD_999999" in err for err in errors)


def test_traceability_flags_v0_mismatch(mock_dataset):
    """Verify broken link is detected when analyzed record has no matching V0 record."""
    _, v0_data, analyzed_data, insight_data = mock_dataset

    # Add orphan record in analyzed_evidence
    analyzed_data.append({
        "record_id": "RD_000888",
        "source_id": "t3_unknown",
        "url": "https://reddit.com/r/test",
    })

    is_valid, errors = verify_traceability_chain(insight_data, analyzed_data, v0_data)
    assert not is_valid
    assert any("RD_000888" in err for err in errors)


def test_traceability_flags_invalid_reddit_url(mock_dataset):
    """Verify non-Reddit URLs in citations trigger traceability error."""
    _, v0_data, analyzed_data, insight_data = mock_dataset

    # Change URL to an invalid external link
    v0_data[0]["url"] = "https://example.com/not_reddit"
    analyzed_data[0]["url"] = "https://example.com/not_reddit"
    insight_data["recurring_patterns"][0]["supporting_evidence"][0]["url"] = (
        "https://example.com/not_reddit"
    )

    is_valid, errors = verify_traceability_chain(insight_data, analyzed_data, v0_data)
    assert not is_valid
    assert any("not a valid Reddit URL" in err for err in errors)


def test_v0_source_data_immutability(tmp_path: Path, mock_dataset, monkeypatch):
    """Verify that running V1 analysis does NOT mutate the source V0 evidence file."""
    v0_file, _, _, _ = mock_dataset
    output_dir = tmp_path / "v1_output"

    # Compute initial SHA-256 hash of V0 source file
    initial_hash = get_file_hash(v0_file)
    initial_mtime = v0_file.stat().st_mtime_ns

    monkeypatch.setenv("GROQ_API_KEY", "gsk_test_key_12345")

    with patch("src.main.GroqClient") as mock_groq_cls:
        mock_client = MagicMock()
        mock_client.health_check.return_value = True
        mock_groq_cls.return_value = mock_client

        with patch("src.main.AIAnalyzer") as mock_analyzer_cls:
            mock_analyzer = MagicMock()
            mock_analyzer.analyze_batch.return_value = [
                AnalyzedEvidenceRecord(
                    record_id="RD_000001",
                    source_id="t3_post1",
                    title="Test",
                    raw_text="Test",
                    url="https://www.reddit.com/r/googlephotos/comments/post1/",
                    is_relevant=True,
                )
            ]
            mock_analyzer_cls.return_value = mock_analyzer

            run_analysis_pipeline(
                taxonomy_path="config/taxonomy.yaml",
                input_path=str(v0_file),
                sample=1,
                dry_run=False,
                output_dir=str(output_dir),
            )

    # Recompute hash after analysis run
    final_hash = get_file_hash(v0_file)
    final_mtime = v0_file.stat().st_mtime_ns

    # Assert 100% byte-level immutability
    assert initial_hash == final_hash, "V0 source evidence file was modified during V1 analysis!"
    assert initial_mtime == final_mtime, "V0 source file modification time was altered!"


def test_live_v0_evidence_integrity():
    """Verify data integrity of the repository's primary V0 evidence dataset."""
    primary_v0_path = Path("data/output/reddit_evidence.json")
    if not primary_v0_path.exists():
        pytest.skip("data/output/reddit_evidence.json not present in repo")

    records = load_v0_evidence(str(primary_v0_path))
    assert len(records) > 0, "Primary V0 evidence dataset is empty"

    seen_ids: set[str] = set()
    for r in records:
        # Check record_id format RD_XXXXXX
        assert re.match(r"^RD_\d{6}$", r.record_id), (
            f"Invalid record_id format: '{r.record_id}'"
        )
        assert r.record_id not in seen_ids, f"Duplicate record_id detected: {r.record_id}"
        seen_ids.add(r.record_id)

        # Check source_id
        assert r.source_id, f"Missing source_id on record {r.record_id}"

        # Check url
        assert r.url and r.url.startswith("http"), (
            f"Invalid URL on record {r.record_id}: {r.url}"
        )

        # Check text presence
        assert (r.raw_text or r.cleaned_text), (
            f"Record {r.record_id} has neither raw_text nor cleaned_text"
        )


def test_schema_conformance_analyzed_evidence(tmp_path: Path, mock_dataset):
    """Validate JSON schema structure of analyzed_evidence.json."""
    _, _, analyzed_data, _ = mock_dataset
    out_file = tmp_path / "analyzed_evidence.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(analyzed_data, f, indent=2)

    with open(out_file, "r", encoding="utf-8") as f:
        loaded = json.load(f)

    assert isinstance(loaded, list)
    for item in loaded:
        assert "record_id" in item
        assert "source_id" in item
        assert "title" in item
        assert "raw_text" in item
        assert "url" in item
        assert "analysis" in item

        analysis = item["analysis"]
        assert "is_relevant" in analysis
        assert "relevance_confidence" in analysis
        assert "target_media" in analysis
        assert "memory_cues_present" in analysis
        assert "retrieval_failure_point" in analysis
        assert "workarounds_used" in analysis
        assert "friction_experienced" in analysis


def test_schema_conformance_insight_report(tmp_path: Path, mock_dataset):
    """Validate JSON schema structure of insight_report.json."""
    _, _, _, insight_data = mock_dataset
    out_file = tmp_path / "insight_report.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(insight_data, f, indent=2)

    with open(out_file, "r", encoding="utf-8") as f:
        loaded = json.load(f)

    assert "report_metadata" in loaded
    assert "research_question" in loaded
    assert "distributions" in loaded
    assert "recurring_patterns" in loaded

    meta = loaded["report_metadata"]
    assert "generated_at" in meta
    assert "v0_source_file" in meta
    assert "total_records_ingested" in meta
    assert "relevant_evidence_count" in meta
    assert "relevance_rate" in meta
    assert "groq_model_used" in meta

    for pattern in loaded["recurring_patterns"]:
        assert "pattern_id" in pattern
        assert "name" in pattern
        assert "prevalence_count" in pattern
        assert "prevalence_percentage" in pattern
        assert "summary" in pattern
        assert "supporting_evidence" in pattern
        for cite in pattern["supporting_evidence"]:
            assert "record_id" in cite
            assert "url" in cite
            assert "quote" in cite


def test_live_generated_artifacts_traceability():
    """Verify traceability of actual generated artifacts on disk in data/output/."""
    report_file = Path("data/output/insight_report.json")
    analyzed_file = Path("data/output/analyzed_evidence.json")
    v0_file = Path("data/output/reddit_evidence.json")

    if not (report_file.exists() and analyzed_file.exists() and v0_file.exists()):
        pytest.skip("Output artifacts not generated yet")

    with open(report_file, "r", encoding="utf-8") as f:
        report = json.load(f)
    with open(analyzed_file, "r", encoding="utf-8") as f:
        analyzed = json.load(f)
    with open(v0_file, "r", encoding="utf-8") as f:
        v0 = json.load(f).get("records", [])

    is_valid, errors = verify_traceability_chain(report, analyzed, v0)
    assert is_valid, f"Traceability errors in generated artifacts: {errors}"

