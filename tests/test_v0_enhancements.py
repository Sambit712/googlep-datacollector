"""Tests for V0 Data Retriever required changes and enhancements.

Validates:
- Full EvidenceRecord schema and stable research IDs (RD_xxxxxx)
- Text cleaning utility (HTML unescaping, whitespace, markdown artifact removal)
- Multi-query accumulation upon deduplication
- Contextual comment extraction with parent context
- Filtering of trivial non-substantive comments
- Data-quality reporting metrics calculation
- CLI options (--limit and --dry-run)
- Privacy / author anonymization
"""

import csv
import json
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from src.cleaner import clean_text, generate_preview
from src.collector import PostCollector
from src.deduplicator import Deduplicator
from src.models import EvidenceRecord
from src.reporter import CollectionReporter
from src.main import main


class MockSubmissionWithComments:
    def __init__(
        self,
        id="sub_100",
        title="Can't find old photo from vacation",
        selftext="&lt;p&gt;Looking for a photo I took in 2021 &amp;amp; can&#39;t find it.&lt;/p&gt;",
        author="traveler_jane",
        subreddit="googlephotos",
        created_utc=1650000000.0,
        score=25,
        num_comments=3,
        permalink="/r/googlephotos/comments/sub_100/cant_find_old_photo/",
        comments=None,
    ):
        self.id = id
        self.title = title
        self.selftext = selftext
        mock_author = MagicMock()
        mock_author.name = author
        self.author = mock_author
        mock_sub = MagicMock()
        mock_sub.display_name = subreddit
        self.subreddit = mock_sub
        self.created_utc = created_utc
        self.score = score
        self.num_comments = num_comments
        self.permalink = permalink
        self.removed_by_category = None

        if comments is not None:
            self.comments = comments
        else:
            # 1 informative comment, 1 trivial comment, 1 deleted comment
            c1 = MagicMock(
                id="cmt_001",
                body="Did you check Google Photos Archive or trash folder?",
                author=MagicMock(name="helper_bob"),
                created_utc=1650000100.0,
                score=5,
                permalink="/r/googlephotos/comments/sub_100/comment/cmt_001/",
            )
            c2 = MagicMock(
                id="cmt_002",
                body="Same here",  # Trivial: should be filtered
                author=MagicMock(name="user_same"),
                created_utc=1650000200.0,
                score=1,
                permalink="/r/googlephotos/comments/sub_100/comment/cmt_002/",
            )
            c3 = MagicMock(
                id="cmt_003",
                body="[deleted]",  # Deleted: should be filtered
                author=None,
                created_utc=1650000300.0,
                score=0,
                permalink="/r/googlephotos/comments/sub_100/comment/cmt_003/",
            )
            self.comments = [c1, c2, c3]


def test_clean_text_unescapes_and_normalizes():
    """clean_text must unescape HTML entities and strip Reddit markdown artifacts."""
    raw = "&lt;!-- SC_OFF --&gt;I took a photo &amp;amp; can&#39;t find it.\n\n\n\nCheck here: https://example.com"
    cleaned = clean_text(raw)

    assert "<!-- SC_OFF -->" not in cleaned
    assert "photo & can't find it" in cleaned
    assert "https://example.com" in cleaned
    assert "\n\n\n" not in cleaned


def test_evidence_record_schema_and_id():
    """EvidenceRecord must contain all required research fields."""
    rec = EvidenceRecord(
        record_id="RD_000001",
        source="reddit",
        source_type="reddit",
        content_type="post",
        source_id="t3_abc123",
        subreddit="googlephotos",
        subreddit_tier="primary",
        title="Sample Title",
        raw_text="Sample raw text",
        cleaned_text="Sample raw text",
        preview_text="Sample raw text",
        author="user1",
        created_at="2026-01-01T00:00:00Z",
        retrieved_at="2026-09-17T00:00:00Z",
        url="https://reddit.com/r/googlephotos/comments/abc123/",
        query_used="Google Photos search",
    )

    d = rec.to_dict()
    required_keys = [
        "record_id",
        "source",
        "source_type",
        "content_type",
        "source_id",
        "subreddit",
        "subreddit_tier",
        "title",
        "raw_text",
        "cleaned_text",
        "preview_text",
        "text_preview",
        "author",
        "created_at",
        "retrieved_at",
        "url",
        "query_used",
        "queries_matched",
        "parent_id",
        "parent_post_title",
        "parent_post_text",
        "ai_relevance",
        "relevance_confidence",
        "evidence_status",
    ]
    for k in required_keys:
        assert k in d, f"Missing required key: {k}"

    assert rec.text_preview == rec.preview_text
    assert d["text_preview"] == rec.preview_text
    assert d["ai_relevance"] is None
    assert d["relevance_confidence"] is None
    assert d["evidence_status"] == "unreviewed"


def test_collector_extracts_contextual_comments_and_filters_trivial():
    """Collector extracts substantive comments with parent context and filters trivial ones."""
    collector = PostCollector(max_comments=3, starting_id=1)
    sub = MockSubmissionWithComments()

    records = collector.collect_batch([sub], search_query="vacation photo", include_comments=True)

    # Should have 2 records: 1 post + 1 substantive comment (trivial and deleted filtered)
    assert len(records) == 2

    post_rec = records[0]
    assert post_rec.content_type == "post"
    assert post_rec.record_id == "RD_000001"
    assert post_rec.source_id == "t3_sub_100"
    assert "2021 & can't find it" in post_rec.cleaned_text

    comment_rec = records[1]
    assert comment_rec.content_type == "comment"
    assert comment_rec.record_id == "RD_000002"
    assert comment_rec.parent_id == "t3_sub_100"
    assert comment_rec.parent_post_title == post_rec.title
    assert "Google Photos Archive" in comment_rec.raw_text
    assert comment_rec.comment_text == comment_rec.raw_text
    assert comment_rec.to_dict()["comment_text"] == comment_rec.raw_text


def test_multi_query_tracking_accumulation():
    """Deduplicator must accumulate all queries that matched a post across iterations."""
    dedup = Deduplicator(index_path="nonexistent_seen.json")

    rec1 = EvidenceRecord(
        record_id="RD_000001",
        source_id="t3_same_post",
        title="Can't find screenshot",
        query_used="can't find old photo",
    )
    rec2 = EvidenceRecord(
        record_id="RD_000002",
        source_id="t3_same_post",
        title="Can't find screenshot",
        query_used="Google Photos screenshot search",
    )

    unique, dup_count = dedup.filter([rec1])
    assert len(unique) == 1
    assert dup_count == 0
    assert unique[0].queries_matched == ["can't find old photo"]
    assert unique[0].to_dict()["query_used"] == "can't find old photo"

    # Second encounter with different query
    unique2, dup_count2 = dedup.filter([rec2])
    assert len(unique2) == 0
    assert dup_count2 == 1

    # First record should now have BOTH queries and serialize query_used as a list!
    assert "can't find old photo" in unique[0].queries_matched
    assert "Google Photos screenshot search" in unique[0].queries_matched
    serialized = unique[0].to_dict()
    assert isinstance(serialized["query_used"], list)
    assert serialized["query_used"] == ["can't find old photo", "Google Photos screenshot search"]


def test_author_anonymization():
    """When anonymize_authors=True, usernames must be pseudonymized."""
    collector = PostCollector(anonymize_authors=True)
    sub = MockSubmissionWithComments(author="real_sensitive_user")
    rec = collector.collect(sub, search_query="test")

    assert rec is not None
    assert rec.author != "real_sensitive_user"
    assert rec.author.startswith("anon_")


def test_collection_reporter_metrics(tmp_path: Path):
    """CollectionReporter must correctly compute all required quality metrics."""
    reporter = CollectionReporter(output_dir=str(tmp_path))

    rec1 = EvidenceRecord(
        record_id="RD_000001",
        source_id="t3_1",
        content_type="post",
        subreddit="googlephotos",
        subreddit_tier="primary",
        raw_text="Some text",
        cleaned_text="Some text",
        url="https://reddit.com/r/googlephotos/comments/1",
        query_used="query_a",
    )
    rec2 = EvidenceRecord(
        record_id="RD_000002",
        source_id="t1_2",
        content_type="comment",
        subreddit="Android",
        subreddit_tier="primary",
        raw_text="Comment text",
        cleaned_text="Comment text",
        url="https://reddit.com/r/Android/comments/2",
        query_used="query_b",
    )

    report = reporter.generate_report(
        run_id="test_run_01",
        records=[rec1, rec2],
        queries_executed=2,
        total_raw_results=5,
        duplicates_removed=3,
        tasks_completed=2,
        tasks_failed=0,
        duration_seconds=12.5,
        is_dry_run=False,
    )

    summary = report["summary"]
    assert summary["queries_executed"] == 2
    assert summary["raw_results"] == 5
    assert summary["unique_records"] == 2
    assert summary["duplicates_removed"] == 3
    assert summary["posts"] == 1
    assert summary["comments"] == 1
    assert summary["records_successfully_saved"] == 2

    assert report["breakdown_by_subreddit"]["googlephotos"] == 1
    assert report["breakdown_by_subreddit"]["Android"] == 1
    assert report["breakdown_by_query"]["query_a"] == 1
    assert report["breakdown_by_query"]["query_b"] == 1

    report_path = reporter.save_report(report)
    assert report_path.is_file()


def test_main_dry_run_mode(tmp_path: Path):
    """Running main with dry_run=True must execute pipeline without writing posts.json."""
    mock_reddit_client = MagicMock()
    mock_reddit_client.validate_connection.return_value = True
    mock_reddit_client.search.return_value = []

    with patch("src.main.RedditClient", return_value=mock_reddit_client):
        report = main(
            config_path="config/queries_test.yaml",
            limit_override=1,
            dry_run=True,
        )
        assert report["is_dry_run"] is True
        assert report["summary"]["records_successfully_saved"] == 0


def test_reddit_evidence_output_generation_and_schema(tmp_path: Path):
    """DataStructurer must generate reddit_evidence.csv, reddit_evidence.json, and preserve schema."""
    from src.structurer import DataStructurer

    rec = EvidenceRecord(
        record_id="RD_000001",
        source="reddit",
        source_type="reddit",
        content_type="post",
        source_id="t3_evid1",
        subreddit="googlephotos",
        subreddit_tier="primary",
        title="Can't find photo",
        raw_text="Long text describing vague photo memory",
        cleaned_text="Long text describing vague photo memory",
        preview_text="Long text describing...",
        author="user_evidence",
        created_at="2026-01-01T12:00:00Z",
        retrieved_at="2026-09-18T10:00:00Z",
        url="https://reddit.com/r/googlephotos/comments/evid1/",
        query_used="Google Photos search",
        queries_matched=["Google Photos search", "can't find old photo"],
        run_id="run_test_123",
        ai_relevance=None,
        relevance_confidence=None,
    )

    metadata = {"run_id": "run_test_123", "total_records": 1}
    structurer = DataStructurer(output_dir=str(tmp_path), output_format="both")
    result = structurer.write([rec], metadata)

    # 1. Verify reddit_evidence.json exists and has correct schema & null AI fields
    json_path = tmp_path / "reddit_evidence.json"
    assert json_path.is_file()
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert "metadata" in data
    assert "records" in data
    item = data["records"][0]
    assert item["record_id"] == "RD_000001"
    assert item["source_type"] == "reddit"
    assert item["content_type"] == "post"
    assert item["run_id"] == "run_test_123"
    assert item["retrieved_at"] == "2026-09-18T10:00:00Z"
    assert item["ai_relevance"] is None
    assert item["relevance_confidence"] is None

    # 2. Verify reddit_evidence.csv exists and has correct columns
    csv_path = tmp_path / "reddit_evidence.csv"
    assert csv_path.is_file()
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    assert len(rows) == 1
    r = rows[0]
    assert r["record_id"] == "RD_000001"
    assert r["source_type"] == "reddit"
    assert r["content_type"] == "post"
    assert r["run_id"] == "run_test_123"
    assert r["retrieved_at"] == "2026-09-18T10:00:00Z"


def test_parent_context_full_text_preservation():
    """Collector must preserve full parent post text without truncation."""
    long_body = "Parent post content with crucial detail. " * 20
    sub = MockSubmissionWithComments(selftext=long_body)
    collector = PostCollector(max_comments=1)
    records = collector.collect_batch([sub], search_query="test query", include_comments=True)

    assert len(records) == 2
    post_rec, cmt_rec = records[0], records[1]
    assert cmt_rec.content_type == "comment"
    assert cmt_rec.parent_post_text == post_rec.cleaned_text
    assert len(cmt_rec.parent_post_text) == len(post_rec.cleaned_text)


def test_config_queries_yaml_v0_categories_and_subreddits():
    """config/queries.yaml must define product-specific and behavior-specific queries and tiered subreddits."""
    from src.config_loader import load_config
    cfg = load_config("config/queries.yaml")

    assert "product_specific" in cfg.search.query_categories
    assert "behavior_specific" in cfg.search.query_categories
    assert len(cfg.search.query_categories["product_specific"]) >= 5
    assert len(cfg.search.query_categories["behavior_specific"]) >= 5

    assert "primary" in cfg.search.subreddit_tiers
    assert "discovery" in cfg.search.subreddit_tiers
    assert "googlephotos" in cfg.search.subreddit_tiers["primary"]

