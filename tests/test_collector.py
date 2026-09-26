"""Unit tests for src/models.py and src/collector.py."""

from unittest.mock import MagicMock
import pytest

from src.collector import PostCollector
from src.models import PostRecord
from src.reddit_client import RawPost


class MockSubmission:
    """Mock object mimicking a PRAW Submission."""

    def __init__(
        self,
        id="abc123",
        title="Can't find old photo",
        selftext="I took a picture in 2019 but can't find it.",
        author="test_user",
        subreddit="googlephotos",
        created_utc=1577836800.0,  # 2020-01-01 00:00:00 UTC
        score=42,
        num_comments=5,
        permalink="/r/googlephotos/comments/abc123/cant_find_old_photo/",
        removed_by_category=None,
        comments=None,
    ):
        self.id = id
        self.title = title
        self.selftext = selftext
        if author is not None:
            mock_author = MagicMock()
            mock_author.name = author
            self.author = mock_author
        else:
            self.author = None

        mock_sub = MagicMock()
        mock_sub.display_name = subreddit
        self.subreddit = mock_sub

        self.created_utc = created_utc
        self.score = score
        self.num_comments = num_comments
        self.permalink = permalink
        self.removed_by_category = removed_by_category

        if comments is not None:
            self.comments = comments
        else:
            c1 = MagicMock(body="Check the archive folder")
            c2 = MagicMock(body="Did you have backup turned on?")
            self.comments = [c1, c2]


def test_collect_valid_post():
    collector = PostCollector(max_comments=2)
    sub = MockSubmission()
    record = collector.collect(sub, search_query="can't find old photo")

    assert record is not None
    assert record.post_id == "t3_abc123"
    assert record.title == "Can't find old photo"
    assert "2019" in record.selftext
    assert record.author == "test_user"
    assert record.subreddit == "googlephotos"
    assert record.score == 42
    assert record.num_comments == 5
    assert record.permalink == "https://reddit.com/r/googlephotos/comments/abc123/cant_find_old_photo/"
    assert record.search_query == "can't find old photo"
    assert len(record.top_comments) == 2
    assert "archive folder" in record.top_comments[0]


def test_deleted_post_returns_none():
    collector = PostCollector()
    sub = MockSubmission(selftext="[deleted]")
    assert collector.collect(sub, "query") is None


def test_removed_post_returns_none():
    collector = PostCollector()
    sub1 = MockSubmission(selftext="[removed]")
    assert collector.collect(sub1, "query") is None

    sub2 = MockSubmission(removed_by_category="moderator")
    assert collector.collect(sub2, "query") is None


def test_timestamp_iso_format():
    collector = PostCollector()
    sub = MockSubmission(created_utc=1577836800.0)
    record = collector.collect(sub, "query")
    assert record is not None
    assert record.created_utc == "2020-01-01T00:00:00Z"


def test_permalink_full_url():
    collector = PostCollector()
    sub = MockSubmission(permalink="/r/test/comments/123/")
    record = collector.collect(sub, "query")
    assert record is not None
    assert record.permalink.startswith("https://reddit.com/r/test/comments/123/")


def test_top_comments_limit():
    comments = [MagicMock(body=f"Comment {i}") for i in range(10)]
    sub = MockSubmission(comments=comments)

    collector = PostCollector(max_comments=3)
    record = collector.collect(sub, "query")
    assert record is not None
    assert len(record.top_comments) == 3
    assert record.top_comments == ["Comment 0", "Comment 1", "Comment 2"]


def test_collect_batch_filters_deleted():
    collector = PostCollector()
    submissions = [
        MockSubmission(id="post1"),
        MockSubmission(id="post2", selftext="[deleted]"),
        MockSubmission(id="post3", removed_by_category="automod_filtered"),
        MockSubmission(id="post4"),
    ]
    records = collector.collect_batch(submissions, search_query="batch query")
    assert len(records) == 2
    assert [r.post_id for r in records] == ["t3_post1", "t3_post4"]


def test_author_deleted_fallback():
    collector = PostCollector()
    sub = MockSubmission(author=None)
    record = collector.collect(sub, "query")
    assert record is not None
    assert record.author == "[deleted]"


def test_post_record_serialization_roundtrip():
    collector = PostCollector()
    sub = MockSubmission()
    record = collector.collect(sub, "test query")
    assert record is not None

    data = record.to_dict()
    assert isinstance(data, dict)
    assert data["post_id"] == "t3_abc123"

    restored = PostRecord.from_dict(data)
    assert restored.post_id == record.post_id
    assert restored.title == record.title
    assert restored.created_utc == record.created_utc
    assert restored.top_comments == record.top_comments


def test_collect_raw_post_dataclass():
    """Verify collector works with RawPost instances from keyless client."""
    collector = PostCollector()
    raw = RawPost(
        id="keyless1",
        title="Keyless post title",
        selftext="Body text here",
        author="keyless_user",
        created_utc=1700000000.0,
        url="https://reddit.com/r/googlephotos/comments/keyless1",
        permalink="/r/googlephotos/comments/keyless1",
        subreddit="googlephotos",
        score=0,
        num_comments=0,
    )
    record = collector.collect(raw, search_query="rss query")
    assert record is not None
    assert record.post_id == "t3_keyless1"
    assert record.author == "keyless_user"
    assert record.subreddit == "googlephotos"
    assert record.permalink == "https://reddit.com/r/googlephotos/comments/keyless1"
