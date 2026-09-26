"""Unit tests for Phase 11 V1 Data Models and Evidence Loader."""

from __future__ import annotations

import json
from pathlib import Path
import pytest

from src.models import EvidenceRecord, AnalyzedEvidenceRecord
from src.evidence_loader import (
    EvidenceLoadError,
    load_v0_evidence,
    load_v0_evidence_with_metadata,
    get_file_hash,
    verify_file_unmodified,
    ImmutabilityGuard,
)


def test_load_v0_evidence_success(tmp_path: Path):
    """Verify loading valid V0 evidence JSON file."""
    sample_data = {
        "metadata": {
            "total_records": 2,
            "generated_at": "2026-09-25T12:00:00Z",
        },
        "records": [
            {
                "record_id": "RD_000001",
                "source_id": "t3_abc123",
                "title": "Can't find a photo from 2018",
                "raw_text": "I remember taking a picture at the beach with John...",
                "url": "https://reddit.com/r/googlephotos/comments/abc123/",
                "subreddit": "googlephotos",
                "author": "user1",
                "created_at": "2025-01-01T00:00:00Z",
                "retrieved_at": "2026-09-25T12:00:00Z",
                "queries_matched": ["can't find old photo"],
            },
            {
                "record_id": "RD_000002",
                "source_id": "t3_def456",
                "title": "Looking for old screenshot",
                "raw_text": "Had a receipt screenshot from last month...",
                "url": "https://reddit.com/r/techsupport/comments/def456/",
                "subreddit": "techsupport",
                "author": "user2",
                "created_at": "2025-02-01T00:00:00Z",
                "retrieved_at": "2026-09-25T12:00:00Z",
                "queries_matched": ["looking for an old screenshot"],
            },
        ],
    }
    file_path = tmp_path / "test_evidence.json"
    file_path.write_text(json.dumps(sample_data), encoding="utf-8")

    records, meta = load_v0_evidence_with_metadata(file_path)
    assert len(records) == 2
    assert meta["total_records"] == 2
    assert records[0].record_id == "RD_000001"
    assert records[0].source_id == "t3_abc123"
    assert records[1].record_id == "RD_000002"
    assert records[1].subreddit == "techsupport"


def test_load_v0_evidence_from_existing_repo_data():
    """Verify loading real repo evidence file if it exists."""
    real_file = Path("data/output/reddit_evidence.json")
    if real_file.is_file():
        records = load_v0_evidence(real_file)
        assert len(records) > 0
        for r in records[:10]:
            assert r.record_id.startswith("RD_")
            assert len(r.source_id) > 0


def test_load_v0_evidence_file_not_found():
    """Verify missing evidence file raises EvidenceLoadError."""
    with pytest.raises(EvidenceLoadError, match="V0 evidence file not found"):
        load_v0_evidence("nonexistent/data/path.json")


def test_load_v0_evidence_malformed_json(tmp_path: Path):
    """Verify malformed JSON raises EvidenceLoadError."""
    bad_file = tmp_path / "bad.json"
    bad_file.write_text("{ unclosed json: ", encoding="utf-8")
    with pytest.raises(EvidenceLoadError, match="Malformed JSON"):
        load_v0_evidence(bad_file)


def test_load_v0_evidence_missing_record_id(tmp_path: Path):
    """Verify records missing record_id raise EvidenceLoadError."""
    invalid_data = {
        "records": [
            {
                "source_id": "t3_xyz789",
                "title": "Missing record ID post",
                "raw_text": "Some text",
            }
        ]
    }
    p = tmp_path / "invalid.json"
    p.write_text(json.dumps(invalid_data), encoding="utf-8")
    with pytest.raises(EvidenceLoadError, match="missing required 'record_id'"):
        load_v0_evidence(p)


def test_load_v0_evidence_invalid_top_level(tmp_path: Path):
    """Verify scalar top-level JSON raises EvidenceLoadError."""
    p = tmp_path / "scalar.json"
    p.write_text('"just a string"', encoding="utf-8")
    with pytest.raises(EvidenceLoadError, match="must be a JSON object or list"):
        load_v0_evidence(p)


def test_file_hash_and_immutability(tmp_path: Path):
    """Verify SHA-256 calculation and immutability guard."""
    test_file = tmp_path / "immutable.json"
    test_file.write_text('{"records": []}', encoding="utf-8")

    initial_hash = get_file_hash(test_file)
    assert len(initial_hash) == 64
    assert verify_file_unmodified(test_file, initial_hash) is True

    # ImmutabilityGuard succeeds when file is unchanged
    with ImmutabilityGuard(test_file):
        _ = load_v0_evidence(test_file)

    assert verify_file_unmodified(test_file, initial_hash) is True

    # ImmutabilityGuard raises if file is modified within context
    with pytest.raises(EvidenceLoadError, match="IMMUTABILITY VIOLATION"):
        with ImmutabilityGuard(test_file):
            test_file.write_text('{"tampered": true}', encoding="utf-8")


def test_analyzed_evidence_record_from_evidence_record():
    """Verify AnalyzedEvidenceRecord construction and serialization."""
    evidence = EvidenceRecord(
        record_id="RD_000042",
        source_id="t3_trip2018",
        title="Can't find beach bonfire",
        raw_text="Bonfire with roommate in 2018...",
        url="https://reddit.com/r/googlephotos/comments/trip2018/",
        author="traveler",
        subreddit="googlephotos",
        created_at="2025-03-01T10:00:00Z",
        retrieved_at="2026-09-25T12:00:00Z",
        queries_matched=["can't find old photo"],
    )

    analysis_data = {
        "is_relevant": True,
        "relevance_confidence": 0.95,
        "relevance_reasoning": "Clear description of vague retrieval failure.",
        "target_media": "personal_photo",
        "memory_cues_present": ["person", "place_location", "activity_action", "temporal_epoch"],
        "memory_cue_details": {"person": "roommate", "place_location": "beach", "activity_action": "bonfire"},
        "retrieval_failure_point": "volume_overload",
        "failure_evidence": "scrolling through 20k photos took hours",
        "workarounds_used": ["endless_scrolling"],
        "friction_experienced": ["time_wasted"],
        "desired_outcome": "Reminisce with roommate",
    }

    analyzed = AnalyzedEvidenceRecord.from_evidence_record(
        evidence=evidence,
        analysis=analysis_data,
        model_used="llama-3.3-70b-versatile",
        analyzed_at="2026-09-25T14:00:00Z",
    )

    assert analyzed.record_id == "RD_000042"
    assert analyzed.is_relevant is True
    assert analyzed.target_media == "personal_photo"
    assert "person" in analyzed.memory_cues_present
    assert analyzed.memory_cue_details["place_location"] == "beach"
    assert analyzed.model_used == "llama-3.3-70b-versatile"

    # Nested JSON dictionary
    nested_dict = analyzed.to_dict(nested_analysis=True)
    assert nested_dict["record_id"] == "RD_000042"
    assert "analysis" in nested_dict
    assert nested_dict["analysis"]["is_relevant"] is True
    assert nested_dict["analysis"]["retrieval_failure_point"] == "volume_overload"

    # Flat CSV dictionary
    flat_dict = analyzed.to_flat_dict()
    assert flat_dict["record_id"] == "RD_000042"
    assert "analysis" not in flat_dict
    assert flat_dict["is_relevant"] is True
    assert flat_dict["retrieval_failure_point"] == "volume_overload"

    # Roundtrip from nested dictionary
    restored = AnalyzedEvidenceRecord.from_dict(nested_dict)
    assert restored.record_id == analyzed.record_id
    assert restored.is_relevant == analyzed.is_relevant
    assert restored.memory_cue_details == analyzed.memory_cue_details
    assert restored.failure_evidence == analyzed.failure_evidence
