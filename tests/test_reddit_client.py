"""Unit tests for src/reddit_client.py."""

from unittest.mock import MagicMock, patch
import pytest
import requests

from src.config_loader import (
    AppConfig,
    RedditConfig,
    SearchConfig,
    PipelineConfig,
    GroqConfig,
    LoggingConfig,
)
from src.reddit_client import (
    KeylessRSSBackend,
    PRAWBackend,
    RawPost,
    RedditClient,
    SearchError,
)

SAMPLE_ATOM_FEED = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>r/googlephotos search: find old photo</title>
  <entry>
    <id>t3_test123</id>
    <title>Cannot find old photos from 2018</title>
    <link href="https://www.reddit.com/r/googlephotos/comments/test123/cannot_find_old_photos_from_2018/" />
    <published>2026-03-15T12:00:00+00:00</published>
    <author>
      <name>/u/sample_photographer</name>
    </author>
    <category term="googlephotos" label="r/googlephotos" />
    <content type="html">&lt;!-- SC_OFF --&gt;&lt;div class="md"&gt;&lt;p&gt;I remember taking photos in Paris but searching Paris brings up nothing.&lt;/p&gt;&lt;/div&gt;&lt;!-- SC_ON --&gt; submitted by &lt;a href="https://www.reddit.com/user/sample_photographer"&gt;/u/sample_photographer&lt;/a&gt;</content>
  </entry>
  <entry>
    <id>t3_test456</id>
    <title>Looking for screenshot of receipt</title>
    <link href="https://www.reddit.com/r/googlephotos/comments/test456/looking_for_screenshot_of_receipt/" />
    <published>2026-03-16T14:30:00+00:00</published>
    <author>
      <name>/u/receipt_hunter</name>
    </author>
    <category term="googlephotos" label="r/googlephotos" />
    <content type="html">&lt;!-- SC_OFF --&gt;&lt;div class="md"&gt;&lt;p&gt;Lost a receipt screenshot from last month.&lt;/p&gt;&lt;/div&gt;&lt;!-- SC_ON --&gt;</content>
  </entry>
</feed>
"""


@pytest.fixture
def dummy_app_config():
    return AppConfig(
        reddit=RedditConfig(
            client_id=None,
            client_secret=None,
            user_agent="test-agent/0.1",
            mode="keyless_rss",
        ),
        search=SearchConfig(
            queries=["test query"],
            subreddits=["googlephotos"],
            sort="relevance",
            time_filter="all",
            limit_per_query=25,
        ),
        pipeline=PipelineConfig(
            deduplicate_by="id",
            output_format="json",
            output_dir="data/output",
            request_delay_seconds=0.01,
        ),
        groq=GroqConfig(),
        logging=LoggingConfig(),
    )


def test_keyless_rss_backend_parses_atom_feed():
    mock_session = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.content = SAMPLE_ATOM_FEED.encode("utf-8")
    mock_session.get.return_value = mock_resp

    backend = KeylessRSSBackend(
        user_agent="test-agent/0.1",
        request_delay_seconds=0.0,
        session=mock_session,
    )

    posts = backend.search("find old photo", subreddit="googlephotos", limit=5)
    assert len(posts) == 2

    p1 = posts[0]
    assert p1.id == "test123"
    assert p1.title == "Cannot find old photos from 2018"
    assert "Paris" in p1.selftext
    assert p1.author == "sample_photographer"
    assert p1.subreddit == "googlephotos"
    assert p1.permalink == "/r/googlephotos/comments/test123/cannot_find_old_photos_from_2018/"

    p2 = posts[1]
    assert p2.id == "test456"
    assert p2.title == "Looking for screenshot of receipt"
    assert "receipt screenshot" in p2.selftext
    assert p2.author == "receipt_hunter"


def test_keyless_rss_backend_handles_429_retry():
    mock_session = MagicMock()
    resp_429 = MagicMock(status_code=429)
    resp_200 = MagicMock(status_code=200, content=SAMPLE_ATOM_FEED.encode("utf-8"))
    mock_session.get.side_effect = [resp_429, resp_200]

    with patch("time.sleep", return_value=None):
        backend = KeylessRSSBackend(
            user_agent="test-agent/0.1",
            request_delay_seconds=0.0,
            session=mock_session,
        )
        posts = backend.search("find old photo", subreddit="googlephotos")

    assert len(posts) == 2
    assert mock_session.get.call_count == 2


def test_keyless_rss_backend_empty_feed():
    mock_session = MagicMock()
    empty_feed = """<?xml version="1.0" encoding="UTF-8"?>
    <feed xmlns="http://www.w3.org/2005/Atom">
      <title>empty</title>
    </feed>
    """
    mock_resp = MagicMock(status_code=200, content=empty_feed.encode("utf-8"))
    mock_session.get.return_value = mock_resp

    backend = KeylessRSSBackend(
        user_agent="test-agent/0.1",
        request_delay_seconds=0.0,
        session=mock_session,
    )
    posts = backend.search("nonexistent", subreddit="googlephotos")
    assert posts == []


def test_keyless_rss_backend_network_failure_raises():
    mock_session = MagicMock()
    mock_session.get.side_effect = requests.exceptions.ConnectionError("Connection failed")

    with patch("time.sleep", return_value=None):
        backend = KeylessRSSBackend(
            user_agent="test-agent/0.1",
            request_delay_seconds=0.0,
            session=mock_session,
            max_retries=2,
        )
        with pytest.raises(SearchError, match="Failed to execute search"):
            backend.search("test")


def test_reddit_client_initialization_keyless(dummy_app_config):
    client = RedditClient(dummy_app_config)
    assert client.backend_mode == "keyless_rss"
    assert isinstance(client.backend, KeylessRSSBackend)


def test_reddit_client_initialization_praw():
    praw_cfg = AppConfig(
        reddit=RedditConfig(
            client_id="mock_id",
            client_secret="mock_secret",
            user_agent="test-agent/0.1",
            mode="praw",
        ),
        search=SearchConfig(queries=["test"]),
        pipeline=PipelineConfig(),
        groq=GroqConfig(),
        logging=LoggingConfig(),
    )

    with patch("src.reddit_client.PRAWBackend") as mock_praw_backend:
        client = RedditClient(praw_cfg)
        assert mock_praw_backend.called


def test_reddit_client_search_delegation(dummy_app_config):
    mock_backend = MagicMock()
    mock_backend.search.return_value = [
        RawPost(
            id="p1",
            title="Title",
            selftext="Text",
            author="User",
            created_utc=1000.0,
            url="https://reddit.com/r/test/comments/p1",
            permalink="/r/test/comments/p1",
            subreddit="test",
        )
    ]

    client = RedditClient(dummy_app_config, backend=mock_backend)
    results = client.search("query 1", subreddit="test")

    assert len(results) == 1
    assert results[0].id == "p1"
    mock_backend.search.assert_called_once_with(
        "query 1",
        subreddit="test",
        sort="relevance",
        time_filter="all",
        limit=25,
    )
