"""Reddit client supporting Dual-Mode data retrieval:
1. Keyless Public RSS mode (via Reddit Atom/RSS search feeds with request throttling)
2. Authenticated PRAW mode (via official Reddit OAuth2 API)
"""

from __future__ import annotations

import logging
import re
import time
import urllib.parse
import xml.etree.ElementTree as ET
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import requests
from bs4 import BeautifulSoup

from src.config_loader import AppConfig

logger = logging.getLogger(__name__)

ATOM_NS = "{http://www.w3.org/2005/Atom}"


class RedditClientError(Exception):
    """Base exception for Reddit client errors."""
    pass


class AuthenticationError(RedditClientError):
    """Raised when authentication fails."""
    pass


class RateLimitError(RedditClientError):
    """Raised when rate limit is exceeded."""
    pass


class SearchError(RedditClientError):
    """Raised when a search query fails."""
    pass


@dataclass
class RawPost:
    """Normalized representation of a retrieved Reddit post."""
    id: str
    title: str
    selftext: str
    author: str
    created_utc: float
    url: str
    permalink: str
    subreddit: str
    score: int = 0
    num_comments: int = 0


class BaseRedditBackend(ABC):
    """Abstract interface for Reddit retrieval backends."""

    @abstractmethod
    def search(
        self,
        query: str,
        subreddit: str | None = None,
        sort: str = "relevance",
        time_filter: str = "all",
        limit: int = 25,
    ) -> list[RawPost]:
        """Execute a search and return a list of RawPost objects."""
        pass

    @abstractmethod
    def validate_connection(self) -> bool:
        """Verify network connectivity / credentials."""
        pass


class KeylessRSSBackend(BaseRedditBackend):
    """Keyless data retrieval backend using public Reddit Atom/RSS search feeds."""

    def __init__(
        self,
        user_agent: str,
        request_delay_seconds: float = 2.0,
        max_retries: int = 3,
        timeout: int = 15,
        session: requests.Session | None = None,
    ):
        self.user_agent = user_agent
        self.request_delay_seconds = request_delay_seconds
        self.max_retries = max_retries
        self.timeout = timeout
        self.session = session or requests.Session()
        self._last_request_time: float = 0.0

    def _throttle(self) -> None:
        """Ensure polite delay between consecutive unauthenticated requests."""
        elapsed = time.monotonic() - self._last_request_time
        if elapsed < self.request_delay_seconds:
            sleep_time = self.request_delay_seconds - elapsed
            time.sleep(sleep_time)
        self._last_request_time = time.monotonic()

    def _parse_entry(self, entry: ET.Element, fallback_subreddit: str) -> RawPost:
        """Parse a single Atom XML entry into a RawPost dataclass."""
        # 1. Post ID
        raw_id = entry.findtext(f"{ATOM_NS}id") or ""
        post_id = raw_id.replace("t3_", "").strip()

        # 2. Title
        title = (entry.findtext(f"{ATOM_NS}title") or "").strip()

        # 3. Link / Permalink
        link_elem = entry.find(f"{ATOM_NS}link")
        url = link_elem.attrib.get("href", "") if link_elem is not None else ""
        parsed_url = urllib.parse.urlparse(url)
        permalink = parsed_url.path

        # 4. Published timestamp (ISO8601 -> Unix timestamp)
        pub_text = entry.findtext(f"{ATOM_NS}published") or entry.findtext(f"{ATOM_NS}updated")
        created_utc = 0.0
        if pub_text:
            try:
                dt = datetime.fromisoformat(pub_text.replace("Z", "+00:00"))
                created_utc = dt.timestamp()
            except Exception:
                created_utc = time.time()

        # 5. Author
        author_name = entry.findtext(f"{ATOM_NS}author/{ATOM_NS}name") or ""
        author = author_name.replace("/u/", "").strip()

        # 6. Subreddit
        category_elem = entry.find(f"{ATOM_NS}category")
        subreddit = fallback_subreddit
        if category_elem is not None and "term" in category_elem.attrib:
            subreddit = category_elem.attrib["term"]
        elif not subreddit:
            # Try extract from permalink e.g. /r/googlephotos/
            sub_match = re.search(r"/r/([A-Za-z0-9_]+)/", permalink)
            if sub_match:
                subreddit = sub_match.group(1)

        # 7. Content / Selftext
        content_html = entry.findtext(f"{ATOM_NS}content") or ""
        selftext = ""
        if content_html:
            soup = BeautifulSoup(content_html, "html.parser")
            # If author was empty, check HTML for submitted by /u/...
            if not author:
                user_anchor = soup.find("a", href=re.compile(r"/user/"))
                if user_anchor and user_anchor.text:
                    author = user_anchor.text.replace("/u/", "").strip()

            md_div = soup.find("div", class_="md")
            if md_div:
                selftext = md_div.get_text("\n").strip()

        return RawPost(
            id=post_id,
            title=title,
            selftext=selftext,
            author=author or "[unknown]",
            created_utc=created_utc,
            url=url,
            permalink=permalink,
            subreddit=subreddit,
            score=0,
            num_comments=0,
        )

    def search(
        self,
        query: str,
        subreddit: str | None = None,
        sort: str = "relevance",
        time_filter: str = "all",
        limit: int = 25,
    ) -> list[RawPost]:
        """Search Reddit using public search RSS/Atom feed."""
        encoded_q = urllib.parse.quote_plus(query)
        if subreddit and subreddit.lower() != "all":
            endpoint = f"https://www.reddit.com/r/{subreddit}/search.rss?q={encoded_q}&restrict_sr=1&sort={sort}&t={time_filter}"
            target_sub = subreddit
        else:
            endpoint = f"https://www.reddit.com/search.rss?q={encoded_q}&sort={sort}&t={time_filter}"
            target_sub = "all"

        user_agent = self.user_agent
        if "Mozilla" not in user_agent:
            user_agent = f"{user_agent} Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko)"

        headers = {
            "User-Agent": user_agent,
            "Accept": "application/atom+xml,application/xml,text/xml",
        }

        posts: list[RawPost] = []
        attempt = 0
        backoff = 2.0

        while attempt < self.max_retries:
            attempt += 1
            self._throttle()
            try:
                response = self.session.get(endpoint, headers=headers, timeout=self.timeout)
                if response.status_code == 429:
                    # Check for rate limit reset headers from Reddit
                    reset_header = None
                    if hasattr(response, "headers") and isinstance(response.headers, (dict, requests.structures.CaseInsensitiveDict)):
                        reset_header = response.headers.get("x-ratelimit-reset") or response.headers.get("Retry-After")
                    try:
                        wait_sec = float(reset_header) + 1.0 if reset_header is not None else backoff
                    except (ValueError, TypeError):
                        wait_sec = backoff
                    wait_sec = max(wait_sec, backoff)
                    logger.warning(f"Rate limited (429) on RSS search query '{query}'. Backing off {wait_sec:.1f}s...")
                    time.sleep(wait_sec)
                    backoff *= 2.0
                    continue

                if response.status_code == 403:
                    raise SearchError(f"HTTP 403 Forbidden while querying Reddit RSS at {endpoint}.")

                response.raise_for_status()

                root = ET.fromstring(response.content)
                entries = root.findall(f"{ATOM_NS}entry")

                for entry in entries[:limit]:
                    post = self._parse_entry(entry, fallback_subreddit=target_sub)
                    if post.id and post.title:
                        posts.append(post)

                logger.info(f"Keyless RSS search found {len(posts)} posts for query='{query}' in r/{target_sub}")
                return posts

            except requests.exceptions.RequestException as e:
                logger.warning(f"Network error on attempt {attempt}/{self.max_retries} for query '{query}': {e}")
                if attempt >= self.max_retries:
                    raise SearchError(f"Failed to execute search after {self.max_retries} attempts: {e}") from e
                time.sleep(backoff)
                backoff *= 2.0
            except ET.ParseError as e:
                raise SearchError(f"Failed to parse XML from Reddit RSS response: {e}") from e

        return posts

    def validate_connection(self) -> bool:
        """Verify connectivity to Reddit public feeds."""
        self._throttle()
        try:
            url = "https://www.reddit.com/r/googlephotos/search.rss?q=photo&restrict_sr=1&limit=1"
            user_agent = self.user_agent
            if "Mozilla" not in user_agent:
                user_agent = f"{user_agent} Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko)"
            headers = {"User-Agent": user_agent}
            resp = self.session.get(url, headers=headers, timeout=self.timeout)
            return resp.status_code == 200
        except Exception as e:
            logger.warning(f"Connection check failed: {e}")
            return False


class PRAWBackend(BaseRedditBackend):
    """Authenticated Reddit API backend using PRAW."""

    def __init__(self, client_id: str, client_secret: str, user_agent: str):
        try:
            import praw
        except ImportError as e:
            raise RedditClientError("PRAW is not installed. Install with `pip install praw`.") from e

        self.client_id = client_id
        self.client_secret = client_secret
        self.user_agent = user_agent

        try:
            self.reddit = praw.Reddit(
                client_id=client_id,
                client_secret=client_secret,
                user_agent=user_agent,
            )
            self.reddit.read_only = True
        except Exception as e:
            raise AuthenticationError(f"Failed to initialize PRAW client: {e}") from e

    def search(
        self,
        query: str,
        subreddit: str | None = None,
        sort: str = "relevance",
        time_filter: str = "all",
        limit: int = 25,
    ) -> list[RawPost]:
        """Search Reddit using PRAW."""
        try:
            sub = self.reddit.subreddit(subreddit or "all")
            submissions = sub.search(query, sort=sort, time_filter=time_filter, limit=limit)
            results: list[RawPost] = []
            for s in submissions:
                author_str = str(s.author) if s.author else "[deleted]"
                results.append(
                    RawPost(
                        id=s.id,
                        title=s.title,
                        selftext=s.selftext or "",
                        author=author_str,
                        created_utc=float(s.created_utc),
                        url=s.url,
                        permalink=s.permalink,
                        subreddit=str(s.subreddit),
                        score=int(getattr(s, "score", 0)),
                        num_comments=int(getattr(s, "num_comments", 0)),
                    )
                )
            return results
        except Exception as e:
            raise SearchError(f"PRAW search failed for query '{query}': {e}") from e

    def validate_connection(self) -> bool:
        """Verify PRAW credentials by performing a light test query."""
        try:
            sub = self.reddit.subreddit("test")
            # Fetch 1 submission title
            for _ in sub.hot(limit=1):
                pass
            return True
        except Exception as e:
            logger.warning(f"PRAW connection validation failed: {e}")
            return False


class RedditClient:
    """Unified Reddit Client facade supporting both Keyless RSS and PRAW backends."""

    def __init__(self, config: AppConfig, backend: BaseRedditBackend | None = None):
        self.config = config
        if backend is not None:
            self.backend = backend
        elif config.reddit.mode == "praw" and config.reddit.client_id and config.reddit.client_secret:
            logger.info("Initializing Reddit client in authenticated PRAW mode.")
            self.backend = PRAWBackend(
                client_id=config.reddit.client_id,
                client_secret=config.reddit.client_secret,
                user_agent=config.reddit.user_agent,
            )
        else:
            logger.info("Initializing Reddit client in Keyless Public RSS mode.")
            self.backend = KeylessRSSBackend(
                user_agent=config.reddit.user_agent,
                request_delay_seconds=config.pipeline.request_delay_seconds,
            )

    @property
    def backend_mode(self) -> str:
        """Return the current backend mode name."""
        return "praw" if isinstance(self.backend, PRAWBackend) else "keyless_rss"

    def search(
        self,
        query: str,
        subreddit: str | None = None,
        sort: str | None = None,
        time_filter: str | None = None,
        limit: int | None = None,
    ) -> list[RawPost]:
        """Execute a search query using the configured backend."""
        s = sort or self.config.search.sort
        tf = time_filter or self.config.search.time_filter
        lim = limit or self.config.search.limit_per_query
        return self.backend.search(query, subreddit=subreddit, sort=s, time_filter=tf, limit=lim)

    def validate_connection(self) -> bool:
        """Validate connection using the configured backend."""
        return self.backend.validate_connection()
