"""Edge case tests for Phase 8.4 and V0 required changes.

Validates:
- Empty search results handling
- Unicode / emoji characters preserved correctly
- Very long post body preserved without truncation in both JSON and CSV
- Deduplicator handles corrupted JSON gracefully
"""

import json
import csv
import pytest
from pathlib import Path

from src.collector import PostCollector
from src.deduplicator import Deduplicator
from src.models import EvidenceRecord, PostRecord
from src.reddit_client import RawPost
from src.structurer import DataStructurer


def test_empty_search_results_flow(tmp_path: Path):
    """Empty results should flow through collector and structurer without error."""
    collector = PostCollector()
    records = collector.collect_batch([], search_query="nonexistent_query_xyz")
    assert records == []

    dedup = Deduplicator(index_path=str(tmp_path / "seen.json"))
    unique, dup_count = dedup.filter(records)
    assert unique == []
    assert dup_count == 0

    structurer = DataStructurer(output_dir=str(tmp_path), output_format="both")
    result = structurer.write(unique, metadata={"total_posts": 0})

    json_path = tmp_path / "reddit_evidence.json"
    csv_path = tmp_path / "reddit_evidence.csv"
    assert json_path.exists()
    assert csv_path.exists()

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
        assert data["posts"] == []
        assert data["metadata"]["total_posts"] == 0


def test_unicode_and_emoji_preservation(tmp_path: Path):
    """Emoji, CJK characters, and non-ASCII characters must be preserved without distortion."""
    unicode_title = "Searching for 📸 old photos in 東京 — Hilfe bitte! 🔍"
    unicode_body = "Here is some text: ☕ Cafe in München. 日本語のテスト. Arabic: مرحبا"

    raw = RawPost(
        id="uni_123",
        title=unicode_title,
        selftext=unicode_body,
        author="user_ümlaut_🚀",
        subreddit="photos",
        created_utc=1600000000.0,
        url="https://reddit.com/r/photos/comments/uni_123/test/",
        permalink="https://reddit.com/r/photos/comments/uni_123/test/",
        score=99,
        num_comments=2,
    )

    collector = PostCollector()
    record = collector.collect(raw, search_query="photos")

    assert record is not None
    assert record.title == unicode_title
    assert record.raw_text == unicode_body

    structurer = DataStructurer(output_dir=str(tmp_path), output_format="both")
    structurer.write([record], metadata={"total_posts": 1})

    # Verify JSON retains Unicode
    with open(tmp_path / "reddit_evidence.json", "r", encoding="utf-8") as f:
        data = json.load(f)
        loaded_post = data["posts"][0]
        assert loaded_post["title"] == unicode_title
        assert loaded_post["raw_text"] == unicode_body
        assert "☕" in loaded_post["cleaned_text"]
        assert "📸" in loaded_post["title"]

    # Verify CSV retains Unicode
    with open(tmp_path / "reddit_evidence.csv", "r", encoding="utf-8") as f:
        csv_text = f.read()
        assert "📸" in csv_text
        assert "東京" in csv_text
        assert "München" in csv_text
        assert "日本語のテスト" in csv_text


def test_very_long_post_body_preservation(tmp_path: Path):
    """JSON and CSV outputs must preserve 100% full length of very long selftext (>10,000 chars)."""
    long_text = "Word " * 3000  # 15,000 characters
    post = EvidenceRecord(
        record_id="RD_000001",
        source_id="t3_long_001",
        title="Very Long Post",
        raw_text=long_text,
        author="author1",
        subreddit="test",
        created_at="2020-01-01T00:00:00Z",
        retrieved_at="2026-09-17T00:00:00Z",
        score=10,
        num_comments=0,
        url="https://reddit.com/r/test/comments/long_001/",
        query_used="test",
    )

    structurer = DataStructurer(output_dir=str(tmp_path), output_format="both")
    structurer.write([post], metadata={"total_posts": 1})

    # JSON should have full 15,000 characters
    with open(tmp_path / "reddit_evidence.json", "r", encoding="utf-8") as f:
        data = json.load(f)
        assert data["posts"][0]["raw_text"] == long_text
        assert len(data["posts"][0]["raw_text"]) == len(long_text)

    # CSV must also preserve full text without truncation
    with open(tmp_path / "reddit_evidence.csv", "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        row = next(reader)
        assert len(row["raw_text"]) == len(long_text)
        assert len(row["cleaned_text"]) == len(long_text.strip())
        assert row["preview_text"].endswith("...")


def test_deduplicator_corrupted_json_handled_gracefully(tmp_path: Path):
    """Corrupted seen_ids.json should not crash Deduplicator; it logs warning and starts fresh."""
    corrupt_file = tmp_path / "seen_ids.json"
    corrupt_file.write_text("NOT_VALID_JSON{{{[[", encoding="utf-8")

    dedup = Deduplicator(index_path=str(corrupt_file))
    stats = dedup.stats()
    assert stats["total_seen"] == 0
    assert not dedup.is_duplicate("post_123")

    # Saving will overwrite with valid JSON
    dedup.mark_seen("post_123")
    dedup.save()

    with open(corrupt_file, "r", encoding="utf-8") as f:
        saved = json.load(f)
        assert "post_123" in saved
