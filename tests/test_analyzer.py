"""Unit tests for Phase 12 V1 Groq AI Multi-Task Analysis Engine."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch
import pytest

from groq import RateLimitError, AuthenticationError
from src.config_loader import load_taxonomy, TaxonomyConfig
from src.groq_client import GroqClient
from src.models import EvidenceRecord, AnalyzedEvidenceRecord
from src.analyzer import AIAnalyzer


@pytest.fixture
def taxonomy() -> TaxonomyConfig:
    """Fixture providing loaded default taxonomy configuration."""
    return load_taxonomy("config/taxonomy.yaml")


@pytest.fixture
def sample_evidence() -> EvidenceRecord:
    """Fixture providing a sample V0 EvidenceRecord."""
    return EvidenceRecord(
        record_id="RD_000042",
        source_id="t3_trip2018",
        title="Can't find beach bonfire photo from 2018",
        raw_text="I remember taking a photo at a beach bonfire in 2018 with my college roommate, but scrolling through 20,000 photos took 2 hours and I couldn't find it.",
        cleaned_text="I remember taking a photo at a beach bonfire in 2018 with my college roommate, but scrolling through 20,000 photos took 2 hours and I couldn't find it.",
        url="https://reddit.com/r/googlephotos/comments/trip2018/",
        author="beach_goer",
        subreddit="googlephotos",
        created_at="2025-03-01T10:00:00Z",
        retrieved_at="2026-09-25T12:00:00Z",
        queries_matched=["can't find old photo"],
        top_comments=["Did you try searching for 'fire' or 'beach'?", "Google Photos search fails on this all the time."],
    )


def test_prompt_construction(taxonomy: TaxonomyConfig, sample_evidence: EvidenceRecord):
    """Verify prompt assembly injects taxonomy rubrics and evidence details."""
    mock_client = MagicMock(spec=GroqClient)
    mock_client.model = "llama-3.3-70b-versatile"
    analyzer = AIAnalyzer(groq_client=mock_client, taxonomy=taxonomy)

    messages = analyzer.build_prompt(sample_evidence)
    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"

    system_content = messages[0]["content"]
    assert "RESEARCH TAXONOMY DEFINITIONS" in system_content
    assert "person" in system_content
    assert "volume_overload" in system_content
    assert "endless_scrolling" in system_content

    user_content = messages[1]["content"]
    assert sample_evidence.title in user_content
    assert "beach bonfire" in user_content
    assert "Contextual Comments" in user_content


def test_parse_clean_json_response(taxonomy: TaxonomyConfig):
    """Verify parsing a clean JSON string response."""
    mock_client = MagicMock(spec=GroqClient)
    analyzer = AIAnalyzer(groq_client=mock_client, taxonomy=taxonomy)

    payload = {
        "is_relevant": True,
        "relevance_confidence": 0.95,
        "relevance_reasoning": "Clear description of vague retrieval failure.",
        "target_media": "personal_photo",
        "memory_cues_present": ["person", "place_location"],
        "memory_cue_details": {"person": "roommate", "place_location": "beach"},
        "retrieval_failure_point": "volume_overload",
        "failure_evidence": "scrolling took 2 hours",
        "workarounds_used": ["endless_scrolling"],
        "friction_experienced": ["time_wasted"],
        "desired_outcome": "Find photo with roommate",
    }
    raw_response = json.dumps(payload)
    parsed = analyzer.parse_analysis_response(raw_response)
    assert parsed["is_relevant"] is True
    assert parsed["target_media"] == "personal_photo"


def test_parse_json_with_markdown_code_fences(taxonomy: TaxonomyConfig):
    """Verify parsing JSON wrapped in markdown code fences."""
    mock_client = MagicMock(spec=GroqClient)
    analyzer = AIAnalyzer(groq_client=mock_client, taxonomy=taxonomy)

    raw_response = """```json
{
  "is_relevant": true,
  "relevance_confidence": 0.9,
  "relevance_reasoning": "User struggled to find screenshot.",
  "target_media": "screenshot",
  "memory_cues_present": ["text_in_image"],
  "memory_cue_details": {"text_in_image": "receipt total"},
  "retrieval_failure_point": "screenshot_clutter",
  "failure_evidence": "lost among memes",
  "workarounds_used": ["keyword_guessing"],
  "friction_experienced": ["cognitive_overload"],
  "desired_outcome": "Submit receipt for expense"
}
```"""
    parsed = analyzer.parse_analysis_response(raw_response)
    assert parsed["is_relevant"] is True
    assert parsed["target_media"] == "screenshot"


def test_parse_json_with_surrounding_commentary(taxonomy: TaxonomyConfig):
    """Verify regex fallback parsing when text surrounds the JSON block."""
    mock_client = MagicMock(spec=GroqClient)
    analyzer = AIAnalyzer(groq_client=mock_client, taxonomy=taxonomy)

    raw_response = """Here is the research analysis you requested:
{"is_relevant": false, "relevance_confidence": 0.1, "relevance_reasoning": "Not about vague retrieval."}
Hope this helps!"""
    parsed = analyzer.parse_analysis_response(raw_response)
    assert parsed["is_relevant"] is False
    assert parsed["relevance_confidence"] == 0.1


def test_parse_malformed_json_raises(taxonomy: TaxonomyConfig):
    """Verify unparseable response raises ValueError."""
    mock_client = MagicMock(spec=GroqClient)
    analyzer = AIAnalyzer(groq_client=mock_client, taxonomy=taxonomy)

    with pytest.raises(ValueError, match="Failed to parse valid JSON"):
        analyzer.parse_analysis_response("This is not JSON at all.")


def test_validate_and_normalize_analysis_taxonomy_filtering(taxonomy: TaxonomyConfig):
    """Verify normalization filters out invalid category IDs and handles edge cases."""
    mock_client = MagicMock(spec=GroqClient)
    analyzer = AIAnalyzer(groq_client=mock_client, taxonomy=taxonomy)

    raw_analysis = {
        "is_relevant": True,
        "relevance_confidence": 1.5,  # Out of range, should clamp to 1.0
        "relevance_reasoning": "Valid reasoning",
        "target_media": "nonexistent_media_type",  # Should fallback to personal_photo
        "memory_cues_present": ["person", "invalid_cue_id"],  # invalid_cue_id should be filtered
        "memory_cue_details": {"person": "grandma", "fake_cue": "something"},
        "retrieval_failure_point": "fake_failure_mode",  # Should fallback to vocabulary_mismatch
        "failure_evidence": "no results",
        "workarounds_used": ["endless_scrolling", "magic_trick"],  # magic_trick filtered
        "friction_experienced": ["time_wasted", "boredom"],  # boredom filtered
        "desired_outcome": "Show family",
    }

    normalized = analyzer.validate_and_normalize_analysis(raw_analysis)
    assert normalized["relevance_confidence"] == 1.0
    assert normalized["target_media"] == "personal_photo"
    assert "person" in normalized["memory_cues_present"]
    assert "invalid_cue_id" not in normalized["memory_cues_present"]
    assert "fake_cue" not in normalized["memory_cue_details"]
    assert normalized["retrieval_failure_point"] == "vocabulary_mismatch"
    assert "endless_scrolling" in normalized["workarounds_used"]
    assert "magic_trick" not in normalized["workarounds_used"]
    assert "time_wasted" in normalized["friction_experienced"]
    assert "boredom" not in normalized["friction_experienced"]


def test_analyze_record_end_to_end_mocked(taxonomy: TaxonomyConfig, sample_evidence: EvidenceRecord):
    """Verify analyze_record produces complete AnalyzedEvidenceRecord with preserved record_id."""
    mock_client = MagicMock(spec=GroqClient)
    mock_client.model = "llama-3.3-70b-versatile"
    mock_client.complete_chat.return_value = json.dumps({
        "is_relevant": True,
        "relevance_confidence": 0.95,
        "relevance_reasoning": "Clear description of vague retrieval failure.",
        "target_media": "personal_photo",
        "memory_cues_present": ["person", "place_location", "activity_action", "temporal_epoch"],
        "memory_cue_details": {"person": "college roommate", "place_location": "beach", "temporal_epoch": "2018"},
        "retrieval_failure_point": "volume_overload",
        "failure_evidence": "scrolling through 20,000 photos took 2 hours and I couldn't find it",
        "workarounds_used": ["endless_scrolling"],
        "friction_experienced": ["time_wasted", "frustration_with_search_tool"],
        "desired_outcome": "Reminisce with roommate",
    })

    analyzer = AIAnalyzer(groq_client=mock_client, taxonomy=taxonomy)
    analyzed = analyzer.analyze_record(sample_evidence)

    assert isinstance(analyzed, AnalyzedEvidenceRecord)
    assert analyzed.record_id == "RD_000042"
    assert analyzed.source_id == "t3_trip2018"
    assert analyzed.is_relevant is True
    assert analyzed.relevance_confidence == 0.95
    assert "person" in analyzed.memory_cues_present
    assert analyzed.retrieval_failure_point == "volume_overload"
    assert "endless_scrolling" in analyzed.workarounds_used
    assert analyzed.model_used == "llama-3.3-70b-versatile"
    assert len(analyzed.analyzed_at) > 0


def test_analyze_record_fallback_on_llm_error(taxonomy: TaxonomyConfig, sample_evidence: EvidenceRecord):
    """Verify analyze_record creates fallback non-relevant record when LLM call fails."""
    mock_client = MagicMock(spec=GroqClient)
    mock_client.model = "llama-3.3-70b-versatile"
    mock_client.complete_chat.side_effect = RuntimeError("Network connection reset")

    analyzer = AIAnalyzer(groq_client=mock_client, taxonomy=taxonomy)
    analyzed = analyzer.analyze_record(sample_evidence)

    assert isinstance(analyzed, AnalyzedEvidenceRecord)
    assert analyzed.record_id == "RD_000042"
    assert analyzed.is_relevant is False
    assert "failed" in analyzed.relevance_reasoning.lower()


def test_analyze_batch_with_progress_callback(taxonomy: TaxonomyConfig, sample_evidence: EvidenceRecord):
    """Verify analyze_batch processes records and triggers callback."""
    mock_client = MagicMock(spec=GroqClient)
    mock_client.model = "llama-3.3-70b-versatile"
    mock_client.complete_chat.return_value = json.dumps({
        "is_relevant": True,
        "relevance_confidence": 0.8,
        "relevance_reasoning": "Relevant test",
        "target_media": "personal_photo",
        "memory_cues_present": ["person"],
        "memory_cue_details": {"person": "someone"},
        "retrieval_failure_point": "temporal_fuzziness",
        "failure_evidence": "can't remember year",
        "workarounds_used": ["endless_scrolling"],
        "friction_experienced": ["time_wasted"],
        "desired_outcome": "find photo",
    })

    analyzer = AIAnalyzer(groq_client=mock_client, taxonomy=taxonomy)
    callback_calls = []

    def callback(idx: int, total: int, rec: AnalyzedEvidenceRecord):
        callback_calls.append((idx, total, rec.record_id))

    records = [sample_evidence, sample_evidence]
    results = analyzer.analyze_batch(records, progress_callback=callback)

    assert len(results) == 2
    assert len(callback_calls) == 2
    assert callback_calls[0] == (1, 2, "RD_000042")
    assert callback_calls[1] == (2, 2, "RD_000042")


@patch("time.sleep")
def test_groq_client_complete_chat_retry_success(mock_sleep):
    """Verify complete_chat retries transient errors and succeeds."""
    mock_groq = MagicMock()
    # Attempt 1 fails with RateLimitError, Attempt 2 succeeds
    mock_error_resp = MagicMock()
    mock_error_resp.status_code = 429
    rate_err = RateLimitError(message="Rate limit exceeded", response=mock_error_resp, body={})

    mock_success_resp = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = '{"is_relevant": true}'
    mock_success_resp.choices = [mock_choice]

    mock_groq.chat.completions.create.side_effect = [rate_err, mock_success_resp]

    client = GroqClient(api_key="gsk_test123")
    client.client = mock_groq

    result = client.complete_chat([{"role": "user", "content": "hi"}], max_retries=2)
    assert result == '{"is_relevant": true}'
    assert mock_groq.chat.completions.create.call_count == 2
    mock_sleep.assert_called_once_with(1)  # 2^0 backoff


def test_groq_client_complete_chat_fatal_error():
    """Verify non-retryable fatal errors raise immediately without retrying."""
    mock_groq = MagicMock()
    mock_error_resp = MagicMock()
    mock_error_resp.status_code = 401
    auth_err = AuthenticationError(message="Invalid API key", response=mock_error_resp, body={})

    mock_groq.chat.completions.create.side_effect = auth_err

    client = GroqClient(api_key="gsk_test123")
    client.client = mock_groq

    with pytest.raises(AuthenticationError):
        client.complete_chat([{"role": "user", "content": "hi"}], max_retries=3)

    assert mock_groq.chat.completions.create.call_count == 1
