"""Data models for Reddit Research Evidence-Collection System.

Provides the standardized EvidenceRecord schema for capturing complete,
untruncated research evidence with stable research IDs and multi-query tracking.
"""

from __future__ import annotations

from typing import Any
from src.cleaner import clean_text, generate_preview


class EvidenceRecord:
    """Standardized record representing an individual piece of Reddit evidence (post or comment)."""

    def __init__(
        self,
        record_id: str = "",
        source: str = "reddit",
        source_type: str = "reddit",
        content_type: str = "post",
        source_id: str = "",
        subreddit: str = "",
        subreddit_tier: str = "primary",
        title: str = "",
        raw_text: str = "",
        cleaned_text: str = "",
        preview_text: str = "",
        author: str = "[deleted]",
        created_at: str = "",
        retrieved_at: str = "",
        url: str = "",
        query_used: str = "",
        queries_matched: list[str] | None = None,
        run_id: str = "",
        parent_id: str | None = None,
        parent_post_title: str | None = None,
        parent_post_text: str | None = None,
        score: int = 0,
        num_comments: int = 0,
        top_comments: list[str] | None = None,
        ai_relevance: str | None = None,
        relevance_confidence: float | None = None,
        evidence_status: str | None = None,
        # Legacy parameters for full backwards compatibility
        post_id: str | None = None,
        selftext: str | None = None,
        created_utc: str | None = None,
        collected_at: str | None = None,
        permalink: str | None = None,
        search_query: str | None = None,
        comments: list[str] | None = None,
    ):
        # Resolve source_id vs post_id
        effective_source_id = source_id or post_id or ""
        self.source_id = str(effective_source_id)

        # Resolve raw_text vs selftext
        effective_raw_text = raw_text if raw_text != "" else (selftext or "")
        self.raw_text = str(effective_raw_text)

        # Cleaned text and preview text
        if cleaned_text:
            self.cleaned_text = str(cleaned_text)
        else:
            self.cleaned_text = clean_text(self.raw_text)

        if preview_text:
            self.preview_text = str(preview_text)
        else:
            self.preview_text = generate_preview(self.cleaned_text or title)

        self.record_id = str(record_id)
        self.source = str(source)
        self.source_type = str(source_type)
        self.content_type = str(content_type)
        self.subreddit = str(subreddit)
        self.subreddit_tier = str(subreddit_tier)
        self.title = str(title)
        self.author = str(author)

        # Timestamps
        self.created_at = str(created_at or created_utc or "")
        self.retrieved_at = str(retrieved_at or collected_at or "")

        # URL
        self.url = str(url or permalink or "")

        # Queries
        effective_query = query_used or search_query or ""
        self.query_used = str(effective_query)

        if queries_matched is not None:
            self.queries_matched = list(queries_matched)
        elif self.query_used:
            self.queries_matched = [self.query_used]
        else:
            self.queries_matched = []

        self.run_id = str(run_id)
        self.parent_id = parent_id
        self.parent_post_title = parent_post_title
        self.parent_post_text = parent_post_text
        self.score = int(score)
        self.num_comments = int(num_comments)

        # Top comments
        if top_comments is not None:
            self.top_comments = list(top_comments)
        elif comments is not None:
            self.top_comments = list(comments)
        else:
            self.top_comments = []

        self.ai_relevance = ai_relevance
        self.relevance_confidence = relevance_confidence
        self.evidence_status = evidence_status

    # --- Backward-compatible properties ---

    @property
    def post_id(self) -> str:
        return self.source_id

    @post_id.setter
    def post_id(self, val: str) -> None:
        self.source_id = val

    @property
    def selftext(self) -> str:
        return self.raw_text

    @selftext.setter
    def selftext(self, val: str) -> None:
        self.raw_text = val
        self.cleaned_text = clean_text(val)

    @property
    def created_utc(self) -> str:
        return self.created_at

    @created_utc.setter
    def created_utc(self, val: str) -> None:
        self.created_at = val

    @property
    def collected_at(self) -> str:
        return self.retrieved_at

    @collected_at.setter
    def collected_at(self, val: str) -> None:
        self.retrieved_at = val

    @property
    def permalink(self) -> str:
        return self.url

    @permalink.setter
    def permalink(self, val: str) -> None:
        self.url = val

    @property
    def search_query(self) -> str:
        return self.query_used

    @search_query.setter
    def search_query(self, val: str) -> None:
        self.query_used = val
        if val and val not in self.queries_matched:
            self.queries_matched.append(val)

    @property
    def text_preview(self) -> str:
        return self.preview_text

    @text_preview.setter
    def text_preview(self, val: str) -> None:
        self.preview_text = val

    @property
    def comment_text(self) -> str | None:
        if self.content_type == "comment":
            return self.raw_text
        return None

    @comment_text.setter
    def comment_text(self, val: str) -> None:
        self.raw_text = val
        self.cleaned_text = clean_text(val)

    def to_dict(self) -> dict[str, Any]:
        """Convert record to a comprehensive dictionary containing both new schema and legacy keys."""
        # Canonical multi-query field is queries_matched (list[str]).
        # query_used is retained as a single string for backward compatibility.
        primary_query = self.queries_matched[0] if self.queries_matched else (self.query_used or "")

        return {
            "record_id": self.record_id,
            "source": self.source,
            "source_type": self.source_type,
            "content_type": self.content_type,
            "source_id": self.source_id,
            "post_id": self.source_id,               # legacy key
            "subreddit": self.subreddit,
            "subreddit_tier": self.subreddit_tier,
            "title": self.title,
            "raw_text": self.raw_text,
            "selftext": self.raw_text,               # legacy key
            "cleaned_text": self.cleaned_text,
            "preview_text": self.preview_text,
            "text_preview": self.preview_text,       # requested alias
            "author": self.author,
            "created_at": self.created_at,
            "created_utc": self.created_at,           # legacy key
            "retrieved_at": self.retrieved_at,
            "collected_at": self.retrieved_at,       # legacy key
            "url": self.url,
            "permalink": self.url,                   # legacy key
            "queries_matched": list(self.queries_matched),
            "query_used": primary_query,             # backward compatibility
            "search_query": primary_query,           # legacy key
            "run_id": self.run_id,
            "parent_id": self.parent_id,
            "parent_post_title": self.parent_post_title,
            "parent_post_text": self.parent_post_text,
            "comment_text": self.raw_text if self.content_type == "comment" else None,
            "score": self.score,
            "num_comments": self.num_comments,
            "top_comments": list(self.top_comments),
            "ai_relevance": self.ai_relevance,       # null in V0
            "relevance_confidence": self.relevance_confidence, # null in V0
            "evidence_status": self.evidence_status, # null in V0
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EvidenceRecord:
        """Create an EvidenceRecord from a dictionary."""
        source_id = str(data.get("source_id") or data.get("post_id", ""))
        raw_text = str(data.get("raw_text") or data.get("selftext", "") or data.get("comment_text", ""))
        cleaned = str(data.get("cleaned_text") or clean_text(raw_text))
        preview = str(data.get("preview_text") or data.get("text_preview", "") or generate_preview(cleaned))
        created = str(data.get("created_at") or data.get("created_utc", ""))
        retrieved = str(data.get("retrieved_at") or data.get("collected_at", ""))
        url = str(data.get("url") or data.get("permalink", ""))

        query_field = data.get("query_used") or data.get("search_query", "")
        if isinstance(query_field, list):
            query = query_field[0] if query_field else ""
            queries_matched = list(query_field)
        else:
            query = str(query_field)
            queries_matched = list(data.get("queries_matched", []))
            if query and query not in queries_matched:
                queries_matched.append(query)

        top_cmts = list(data.get("top_comments", data.get("comments", [])))

        return cls(
            record_id=str(data.get("record_id", "")),
            source=str(data.get("source", "reddit")),
            source_type=str(data.get("source_type", "reddit")),
            content_type=str(data.get("content_type", "post")),
            source_id=source_id,
            subreddit=str(data.get("subreddit", "")),
            subreddit_tier=str(data.get("subreddit_tier", "primary")),
            title=str(data.get("title", "")),
            raw_text=raw_text,
            cleaned_text=cleaned,
            preview_text=preview,
            author=str(data.get("author", "[deleted]")),
            created_at=created,
            retrieved_at=retrieved,
            url=url,
            query_used=query,
            queries_matched=queries_matched,
            run_id=str(data.get("run_id", "")),
            parent_id=data.get("parent_id"),
            parent_post_title=data.get("parent_post_title"),
            parent_post_text=data.get("parent_post_text"),
            score=int(data.get("score", 0)),
            num_comments=int(data.get("num_comments", 0)),
            top_comments=top_cmts,
            ai_relevance=data.get("ai_relevance"),
            relevance_confidence=data.get("relevance_confidence"),
            evidence_status=data.get("evidence_status", None),
        )


# Backward compatibility alias
PostRecord = EvidenceRecord
