"""Unit tests for src/structurer.py."""

import csv
import json
import pytest
from pathlib import Path

from src.models import EvidenceRecord, PostRecord
from src.structurer import DataStructurer, CSV_COLUMNS


def _make_post(post_id: str, selftext: str = "Test body", comments: list[str] | None = None) -> EvidenceRecord:
    """Helper to create an EvidenceRecord for testing."""
    return EvidenceRecord(
        record_id=f"RD_{post_id}",
        source="reddit",
        source_type="reddit",
        content_type="post",
        source_id=post_id,
        title=f"Title for {post_id}",
        raw_text=selftext,
        cleaned_text=selftext,
        author="test_user",
        subreddit="googlephotos",
        created_at="2026-01-01T00:00:00Z",
        retrieved_at="2026-09-17T00:00:00Z",
        score=10,
        num_comments=2,
        url=f"https://reddit.com/r/googlephotos/comments/{post_id}/",
        query_used="test query",
        top_comments=comments or ["comment1", "comment2"],
    )


@pytest.fixture
def sample_posts():
    return [
        _make_post("t3_aaa"),
        _make_post("t3_bbb", selftext="Short body"),
        _make_post("t3_ccc", comments=["only one"]),
    ]


@pytest.fixture
def sample_metadata():
    return {
        "generated_at": "2026-09-17T00:00:00Z",
        "total_posts": 3,
        "queries_used": 2,
        "duplicates_skipped": 1,
    }


def test_write_json_creates_file(tmp_path: Path, sample_posts, sample_metadata):
    structurer = DataStructurer(output_dir=str(tmp_path), output_format="json")
    result = structurer.write(sample_posts, sample_metadata)

    assert (tmp_path / "reddit_evidence.json").is_file()
    assert (tmp_path / "posts.json").is_file()
    assert str(tmp_path / "reddit_evidence.json") in result["files_written"]
    assert str(tmp_path / "posts.json") in result["files_written"]


def test_json_has_metadata_header(tmp_path: Path, sample_posts, sample_metadata):
    structurer = DataStructurer(output_dir=str(tmp_path), output_format="json")
    structurer.write(sample_posts, sample_metadata)

    for fname in ("reddit_evidence.json", "posts.json"):
        with open(tmp_path / fname, "r", encoding="utf-8") as f:
            data = json.load(f)

        assert "metadata" in data
        assert data["metadata"]["total_posts"] == 3
        assert data["metadata"]["queries_used"] == 2
        assert data["metadata"]["duplicates_skipped"] == 1


def test_json_posts_match_input(tmp_path: Path, sample_posts, sample_metadata):
    structurer = DataStructurer(output_dir=str(tmp_path), output_format="json")
    structurer.write(sample_posts, sample_metadata)

    for fname in ("reddit_evidence.json", "posts.json"):
        with open(tmp_path / fname, "r", encoding="utf-8") as f:
            data = json.load(f)

        assert len(data["posts"]) == 3
        assert data["posts"][0]["source_id"] == "t3_aaa"
        assert data["posts"][1]["raw_text"] == "Short body"
        assert data["posts"][2]["top_comments"] == ["only one"]


def test_write_csv_creates_file(tmp_path: Path, sample_posts, sample_metadata):
    structurer = DataStructurer(output_dir=str(tmp_path), output_format="csv")
    result = structurer.write(sample_posts, sample_metadata)

    assert (tmp_path / "reddit_evidence.csv").is_file()
    assert (tmp_path / "posts.csv").is_file()
    assert str(tmp_path / "reddit_evidence.csv") in result["files_written"]
    assert str(tmp_path / "posts.csv") in result["files_written"]


def test_csv_headers_match_schema(tmp_path: Path, sample_posts, sample_metadata):
    structurer = DataStructurer(output_dir=str(tmp_path), output_format="csv")
    structurer.write(sample_posts, sample_metadata)

    for fname in ("reddit_evidence.csv", "posts.csv"):
        with open(tmp_path / fname, "r", encoding="utf-8") as f:
            reader = csv.reader(f)
            headers = next(reader)
        assert headers == CSV_COLUMNS


def test_csv_row_count_matches(tmp_path: Path, sample_posts, sample_metadata):
    structurer = DataStructurer(output_dir=str(tmp_path), output_format="csv")
    structurer.write(sample_posts, sample_metadata)

    for fname in ("reddit_evidence.csv", "posts.csv"):
        with open(tmp_path / fname, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        assert len(rows) == 3


def test_write_both_formats(tmp_path: Path, sample_posts, sample_metadata):
    structurer = DataStructurer(output_dir=str(tmp_path), output_format="both")
    result = structurer.write(sample_posts, sample_metadata)

    assert (tmp_path / "reddit_evidence.json").is_file()
    assert (tmp_path / "reddit_evidence.csv").is_file()
    assert (tmp_path / "posts.json").is_file()
    assert (tmp_path / "posts.csv").is_file()
    assert len(result["files_written"]) == 4
    assert result["total_records"] == 3


def test_output_dir_created_if_missing(tmp_path: Path, sample_posts, sample_metadata):
    nested_dir = tmp_path / "sub1" / "sub2" / "output"
    structurer = DataStructurer(output_dir=str(nested_dir), output_format="both")
    structurer.write(sample_posts, sample_metadata)

    assert nested_dir.is_dir()
    assert (nested_dir / "reddit_evidence.json").is_file()
    assert (nested_dir / "reddit_evidence.csv").is_file()
    assert (nested_dir / "posts.json").is_file()
    assert (nested_dir / "posts.csv").is_file()


def test_empty_posts_produces_valid_output(tmp_path: Path, sample_metadata):
    structurer = DataStructurer(output_dir=str(tmp_path), output_format="both")
    result = structurer.write([], sample_metadata)

    assert result["total_records"] == 0

    # JSON: valid with empty posts array
    data = json.loads((tmp_path / "reddit_evidence.json").read_text(encoding="utf-8"))
    assert data["posts"] == []
    assert "metadata" in data

    # CSV: valid with headers only
    with open(tmp_path / "reddit_evidence.csv", "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    assert len(rows) == 0


def test_csv_zero_truncation_preserves_full_text(tmp_path: Path, sample_metadata):
    long_text = "x" * 600
    posts = [_make_post("t3_long", selftext=long_text)]

    structurer = DataStructurer(output_dir=str(tmp_path), output_format="csv")
    structurer.write(posts, sample_metadata)

    with open(tmp_path / "reddit_evidence.csv", "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        row = next(reader)
    assert len(row["raw_text"]) == 600
    assert len(row["cleaned_text"]) == 600
    assert row["preview_text"].endswith("...")


def test_csv_comments_joined(tmp_path: Path, sample_metadata):
    posts = [_make_post("t3_cmt", comments=["first", "second", "third"])]

    structurer = DataStructurer(output_dir=str(tmp_path), output_format="csv")
    structurer.write(posts, sample_metadata)

    with open(tmp_path / "reddit_evidence.csv", "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        row = next(reader)
    assert row["top_comments"] == "first ||| second ||| third"
