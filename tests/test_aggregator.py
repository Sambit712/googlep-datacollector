"""Unit tests for Phase 13 V1 Statistical Aggregation & Pattern Engine."""

from __future__ import annotations

import pytest
from src.models import AnalyzedEvidenceRecord
from src.aggregator import PatternAggregator


@pytest.fixture
def mock_analyzed_records() -> list[AnalyzedEvidenceRecord]:
    """Fixture providing deterministic sample of AnalyzedEvidenceRecord instances."""
    return [
        AnalyzedEvidenceRecord(
            record_id="RD_000001",
            source_id="t3_p1",
            title="Lost beach photo",
            raw_text="Can't find beach picture with roommate from 2018 in my 30k library.",
            url="https://reddit.com/r/googlephotos/comments/p1/",
            author="u1",
            subreddit="googlephotos",
            is_relevant=True,
            relevance_confidence=0.95,
            target_media="personal_photo",
            memory_cues_present=["person", "place_location", "temporal_epoch"],
            retrieval_failure_point="volume_overload",
            failure_evidence="scrolling took 2 hours through 30k photos",
            workarounds_used=["endless_scrolling"],
            friction_experienced=["time_wasted"],
            desired_outcome="Show friend",
        ),
        AnalyzedEvidenceRecord(
            record_id="RD_000002",
            source_id="t3_p2",
            title="Looking for goofy selfie",
            raw_text="Trying to search for silly face but Google Photos only recognizes smile.",
            url="https://reddit.com/r/googlephotos/comments/p2/",
            author="u2",
            subreddit="googlephotos",
            is_relevant=True,
            relevance_confidence=0.88,
            target_media="personal_photo",
            memory_cues_present=["person", "visual_details"],
            retrieval_failure_point="vocabulary_mismatch",
            failure_evidence="query for silly face returned zero hits",
            workarounds_used=["keyword_guessing"],
            friction_experienced=["frustration_with_search_tool"],
            desired_outcome="Share funny memory",
        ),
        AnalyzedEvidenceRecord(
            record_id="RD_000003",
            source_id="t3_p3",
            title="Missing receipt screenshot",
            raw_text="Need my store receipt from last month but it's buried in memes.",
            url="https://reddit.com/r/techsupport/comments/p3/",
            author="u3",
            subreddit="techsupport",
            is_relevant=True,
            relevance_confidence=0.92,
            target_media="screenshot",
            memory_cues_present=["text_in_image", "temporal_epoch"],
            retrieval_failure_point="screenshot_clutter",
            failure_evidence="buried under thousands of saved memes",
            workarounds_used=["endless_scrolling", "peer_inquiry"],
            friction_experienced=["time_wasted", "cognitive_overload"],
            desired_outcome="File expense report",
        ),
        AnalyzedEvidenceRecord(
            record_id="RD_000004",
            source_id="t3_p4",
            title="How do I change my profile pic?",
            raw_text="Just asking how to change avatar.",
            url="https://reddit.com/r/techsupport/comments/p4/",
            author="u4",
            subreddit="techsupport",
            is_relevant=False,
            relevance_confidence=0.05,
            target_media="personal_photo",
            memory_cues_present=["person"],  # Should NOT be counted in distributions because is_relevant is False
            retrieval_failure_point="",
            failure_evidence="",
            workarounds_used=[],
            friction_experienced=[],
            desired_outcome="",
        ),
    ]


def test_aggregator_empty_records():
    """Verify aggregator handles empty dataset without crashing."""
    aggregator = PatternAggregator([])
    assert aggregator.total_records == 0
    assert aggregator.relevant_records == 0
    assert aggregator.relevance_rate == 0.0

    assert aggregator.compute_memory_cue_distribution() == {}
    assert aggregator.compute_failure_point_distribution() == {}
    assert aggregator.compute_workaround_distribution() == {}
    assert aggregator.compute_media_type_distribution() == {}
    assert aggregator.compute_friction_distribution() == {}
    assert aggregator.compute_cross_tabulations() == {
        "memory_cues_vs_failure_points": {},
        "target_media_vs_workarounds": {},
    }
    assert aggregator.synthesize_recurring_patterns() == []


def test_aggregator_no_relevant_records():
    """Verify aggregator handles dataset where no records are relevant."""
    records = [
        AnalyzedEvidenceRecord(
            record_id="RD_000099",
            source_id="t3_test",
            is_relevant=False,
            relevance_confidence=0.1,
        )
    ]
    aggregator = PatternAggregator(records)
    assert aggregator.total_records == 1
    assert aggregator.relevant_records == 0
    assert aggregator.relevance_rate == 0.0
    assert aggregator.compute_memory_cue_distribution() == {}


def test_aggregator_distributions(mock_analyzed_records: list[AnalyzedEvidenceRecord]):
    """Verify frequency distributions accurately count only relevant evidence."""
    aggregator = PatternAggregator(mock_analyzed_records)
    assert aggregator.total_records == 4
    assert aggregator.relevant_records == 3
    assert aggregator.relevance_rate == 0.75

    # Memory cues: person (2), temporal_epoch (2), place_location (1), visual_details (1), text_in_image (1)
    # Notice that record 4's 'person' cue is not counted because is_relevant == False!
    cues = aggregator.compute_memory_cue_distribution()
    assert cues["person"] == 2
    assert cues["temporal_epoch"] == 2
    assert cues["place_location"] == 1
    assert cues["text_in_image"] == 1

    # Retrieval failure points
    failures = aggregator.compute_failure_point_distribution()
    assert failures["volume_overload"] == 1
    assert failures["vocabulary_mismatch"] == 1
    assert failures["screenshot_clutter"] == 1

    # Workarounds
    workarounds = aggregator.compute_workaround_distribution()
    assert workarounds["endless_scrolling"] == 2
    assert workarounds["keyword_guessing"] == 1
    assert workarounds["peer_inquiry"] == 1

    # Media types
    media = aggregator.compute_media_type_distribution()
    assert media["personal_photo"] == 2
    assert media["screenshot"] == 1

    # Friction
    friction = aggregator.compute_friction_distribution()
    assert friction["time_wasted"] == 2
    assert friction["frustration_with_search_tool"] == 1
    assert friction["cognitive_overload"] == 1


def test_aggregator_cross_tabulations(mock_analyzed_records: list[AnalyzedEvidenceRecord]):
    """Verify bivariate cross-tabulations."""
    aggregator = PatternAggregator(mock_analyzed_records)
    cross_tabs = aggregator.compute_cross_tabulations()

    assert "memory_cues_vs_failure_points" in cross_tabs
    assert "target_media_vs_workarounds" in cross_tabs

    # In mock data, personal_photo co-occurred with endless_scrolling and keyword_guessing
    media_work = cross_tabs["target_media_vs_workarounds"]
    assert "personal_photo" in media_work
    assert media_work["personal_photo"]["endless_scrolling"] == 1
    assert media_work["personal_photo"]["keyword_guessing"] == 1


def test_aggregator_recurring_patterns_citations(mock_analyzed_records: list[AnalyzedEvidenceRecord]):
    """Verify synthesized patterns contain valid IDs, percentages, and evidence citations."""
    aggregator = PatternAggregator(mock_analyzed_records)
    patterns = aggregator.synthesize_recurring_patterns()

    assert len(patterns) > 0
    for p in patterns:
        assert p["pattern_id"].startswith("PAT_")
        assert len(p["name"]) > 0
        assert p["prevalence_count"] > 0
        assert 0 < p["prevalence_percentage"] <= 100
        assert len(p["summary"]) > 0
        assert len(p["supporting_evidence"]) > 0

        # Verify evidence citations
        citation = p["supporting_evidence"][0]
        assert citation["record_id"].startswith("RD_")
        assert citation["url"].startswith("https://reddit.com")
        assert len(citation["quote"]) > 0


def test_aggregator_summary_generation(mock_analyzed_records: list[AnalyzedEvidenceRecord]):
    """Verify generate_summary schema matches expected research report format."""
    aggregator = PatternAggregator(mock_analyzed_records)
    summary = aggregator.generate_summary()

    assert "statistics" in summary
    assert summary["statistics"]["total_records_ingested"] == 4
    assert summary["statistics"]["relevant_evidence_count"] == 3
    assert summary["statistics"]["relevance_rate"] == 0.75

    assert "distributions" in summary
    assert "top_memory_cues" in summary["distributions"]
    assert "retrieval_failure_points" in summary["distributions"]

    assert "cross_tabulations" in summary
    assert "recurring_patterns" in summary
    assert len(summary["recurring_patterns"]) > 0
