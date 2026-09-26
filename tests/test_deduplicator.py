"""Unit tests for src/deduplicator.py."""

import json
import pytest
from pathlib import Path

from src.deduplicator import Deduplicator
from src.models import PostRecord


def _make_post(post_id: str) -> PostRecord:
    """Helper to create a minimal PostRecord for testing."""
    return PostRecord(
        post_id=post_id,
        title=f"Title for {post_id}",
        selftext="Test body",
        author="test_user",
        subreddit="googlephotos",
        created_utc="2026-01-01T00:00:00Z",
        score=10,
        num_comments=2,
        permalink=f"https://reddit.com/r/googlephotos/comments/{post_id}/",
        search_query="test query",
        collected_at="2026-09-17T00:00:00Z",
        top_comments=[],
    )


def test_new_post_passes_through(tmp_path: Path):
    dedup = Deduplicator(index_path=str(tmp_path / "seen.json"))
    assert dedup.is_duplicate("t3_new123") is False


def test_duplicate_post_filtered(tmp_path: Path):
    dedup = Deduplicator(index_path=str(tmp_path / "seen.json"))
    posts = [_make_post("t3_aaa"), _make_post("t3_bbb"), _make_post("t3_aaa")]

    unique, dup_count = dedup.filter(posts)
    assert len(unique) == 2
    assert dup_count == 1
    assert [p.post_id for p in unique] == ["t3_aaa", "t3_bbb"]


def test_cross_batch_dedup(tmp_path: Path):
    dedup = Deduplicator(index_path=str(tmp_path / "seen.json"))

    batch1 = [_make_post("t3_x1"), _make_post("t3_x2")]
    unique1, dup1 = dedup.filter(batch1)
    assert len(unique1) == 2
    assert dup1 == 0

    batch2 = [_make_post("t3_x2"), _make_post("t3_x3")]
    unique2, dup2 = dedup.filter(batch2)
    assert len(unique2) == 1
    assert dup2 == 1
    assert unique2[0].post_id == "t3_x3"


def test_persistence_load(tmp_path: Path):
    index_file = tmp_path / "seen.json"
    index_file.write_text(json.dumps(["t3_old1", "t3_old2"]), encoding="utf-8")

    dedup = Deduplicator(index_path=str(index_file))
    assert dedup.is_duplicate("t3_old1") is True
    assert dedup.is_duplicate("t3_old2") is True
    assert dedup.is_duplicate("t3_new1") is False


def test_persistence_save(tmp_path: Path):
    index_file = tmp_path / "seen.json"
    dedup = Deduplicator(index_path=str(index_file))

    dedup.mark_seen("t3_save1")
    dedup.mark_seen("t3_save2")
    dedup.save()

    assert index_file.is_file()
    saved_data = json.loads(index_file.read_text(encoding="utf-8"))
    assert isinstance(saved_data, list)
    assert set(saved_data) == {"t3_save1", "t3_save2"}


def test_empty_file_starts_fresh(tmp_path: Path):
    index_file = tmp_path / "nonexistent" / "seen.json"
    dedup = Deduplicator(index_path=str(index_file))
    assert dedup.stats()["total_seen"] == 0
    assert dedup.is_duplicate("t3_anything") is False


def test_filter_returns_correct_counts(tmp_path: Path):
    index_file = tmp_path / "seen.json"
    index_file.write_text(json.dumps(["t3_prev"]), encoding="utf-8")

    dedup = Deduplicator(index_path=str(index_file))
    posts = [
        _make_post("t3_prev"),   # duplicate (from previous run)
        _make_post("t3_new1"),   # unique
        _make_post("t3_new2"),   # unique
        _make_post("t3_new1"),   # duplicate (within same batch)
    ]

    unique, dup_count = dedup.filter(posts)
    assert len(unique) == 2
    assert dup_count == 2
    assert [p.post_id for p in unique] == ["t3_new1", "t3_new2"]

    stats = dedup.stats()
    assert stats["total_seen"] == 3  # t3_prev + t3_new1 + t3_new2
    assert stats["duplicates_this_run"] == 2
