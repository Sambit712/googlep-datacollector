"""Data models for Reddit Research Data-Retrieval System."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class PostRecord:
    """Normalized, deduplicable record representing a collected Reddit post."""

    post_id: str                       # Fullname with t3_ prefix, e.g. "t3_abc123"
    title: str
    selftext: str
    author: str
    subreddit: str
    created_utc: str                   # ISO-8601 UTC timestamp, e.g. "2026-03-19T16:20:56Z"
    score: int
    num_comments: int
    permalink: str                     # Full URL, e.g. "https://reddit.com/r/..."
    search_query: str                  # Query string that produced this result
    collected_at: str                  # ISO-8601 UTC timestamp
    top_comments: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert record to a standard dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PostRecord:
        """Create a PostRecord from a dictionary."""
        return cls(
            post_id=str(data["post_id"]),
            title=str(data["title"]),
            selftext=str(data.get("selftext", "")),
            author=str(data.get("author", "[deleted]")),
            subreddit=str(data["subreddit"]),
            created_utc=str(data["created_utc"]),
            score=int(data.get("score", 0)),
            num_comments=int(data.get("num_comments", 0)),
            permalink=str(data["permalink"]),
            search_query=str(data["search_query"]),
            collected_at=str(data["collected_at"]),
            top_comments=list(data.get("top_comments", [])),
        )
