"""Raw post collector that normalizes submissions into PostRecord instances."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Iterable

from src.models import PostRecord

logger = logging.getLogger(__name__)


class PostCollector:
    """Converts raw Reddit submissions (PRAW or RawPost) into normalized PostRecord instances."""

    def __init__(self, max_comments: int = 5):
        """
        Args:
            max_comments: Number of top-level comments to collect per post.
        """
        self.max_comments = max_comments

    def _is_deleted_or_removed(self, submission: Any) -> bool:
        """Determine if a submission was deleted by user or removed by moderator."""
        # 1. Direct flags
        if getattr(submission, "removed_by_category", None) is not None:
            return True

        # 2. Selftext markers
        selftext = getattr(submission, "selftext", "") or ""
        if selftext.strip() in ("[deleted]", "[removed]"):
            return True

        # 3. Title markers
        title = getattr(submission, "title", "") or ""
        if title.strip() in ("[deleted]", "[removed]"):
            return True

        return False

    def _extract_author(self, submission: Any) -> str:
        """Extract author username, defaulting to '[deleted]'."""
        author_attr = getattr(submission, "author", None)
        if author_attr is None:
            return "[deleted]"

        if hasattr(author_attr, "name"):
            name = str(author_attr.name).strip()
            return name if name else "[deleted]"

        name_str = str(author_attr).strip()
        if not name_str or name_str in ("[deleted]", "[removed]"):
            return "[deleted]"

        # Strip /u/ if present
        return name_str.replace("/u/", "").strip()

    def _extract_subreddit(self, submission: Any) -> str:
        """Extract subreddit display name."""
        sub_attr = getattr(submission, "subreddit", "")
        if hasattr(sub_attr, "display_name"):
            return str(sub_attr.display_name)
        sub_str = str(sub_attr).strip()
        return sub_str.replace("r/", "").strip()

    def _format_timestamp(self, ts: Any) -> str:
        """Format a timestamp into ISO-8601 UTC string ending in 'Z'."""
        if isinstance(ts, (int, float)):
            dt = datetime.fromtimestamp(ts, tz=timezone.utc)
            return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        elif isinstance(ts, str):
            if ts.endswith("Z"):
                return ts
            try:
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            except Exception:
                pass
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def _format_permalink(self, permalink: str) -> str:
        """Ensure permalink is a full URL starting with https://reddit.com."""
        clean = (permalink or "").strip()
        if not clean:
            return ""
        if clean.startswith("http://") or clean.startswith("https://"):
            return clean
        if not clean.startswith("/"):
            clean = "/" + clean
        return f"https://reddit.com{clean}"

    def _extract_top_comments(self, submission: Any) -> list[str]:
        """Extract up to max_comments top-level comment strings."""
        if self.max_comments <= 0:
            return []

        comments_attr = getattr(submission, "comments", None)
        if comments_attr is None:
            return []

        # If PRAW CommentForest, safely replace_more with limit=0
        if hasattr(comments_attr, "replace_more"):
            try:
                comments_attr.replace_more(limit=0)
            except Exception:
                pass

        collected: list[str] = []
        try:
            for comment in comments_attr:
                if len(collected) >= self.max_comments:
                    break

                # Skip MoreComments instances
                if comment.__class__.__name__ == "MoreComments":
                    continue

                body = getattr(comment, "body", "")
                if not body and isinstance(comment, str):
                    body = comment

                body_str = str(body).strip()
                if body_str and body_str not in ("[deleted]", "[removed]"):
                    collected.append(body_str)
        except Exception as e:
            logger.debug(f"Error extracting comments: {e}")

        return collected

    def collect(self, submission: Any, search_query: str) -> PostRecord | None:
        """Extract and normalize fields from a single submission.

        Returns:
            PostRecord if valid, or None if deleted or removed.
        """
        if self._is_deleted_or_removed(submission):
            logger.debug(f"Skipping deleted/removed submission {getattr(submission, 'id', 'unknown')}")
            return None

        raw_id = str(getattr(submission, "id", "")).strip()
        if not raw_id:
            return None

        post_id = raw_id if raw_id.startswith("t3_") else f"t3_{raw_id}"
        title = str(getattr(submission, "title", "")).strip()
        selftext = str(getattr(submission, "selftext", "") or "").strip()
        author = self._extract_author(submission)
        subreddit = self._extract_subreddit(submission)
        created_utc = self._format_timestamp(getattr(submission, "created_utc", 0))
        score = int(getattr(submission, "score", 0))
        num_comments = int(getattr(submission, "num_comments", 0))
        permalink = self._format_permalink(str(getattr(submission, "permalink", "")))
        top_comments = self._extract_top_comments(submission)
        collected_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        return PostRecord(
            post_id=post_id,
            title=title,
            selftext=selftext,
            author=author,
            subreddit=subreddit,
            created_utc=created_utc,
            score=score,
            num_comments=num_comments,
            permalink=permalink,
            search_query=search_query,
            collected_at=collected_at,
            top_comments=top_comments,
        )

    def collect_batch(self, submissions: Iterable[Any], search_query: str) -> list[PostRecord]:
        """Process an iterable of submissions into a list of valid PostRecords.

        Skips any deleted or removed posts and logs statistics.
        """
        records: list[PostRecord] = []
        skipped = 0

        for s in submissions:
            rec = self.collect(s, search_query=search_query)
            if rec is not None:
                records.append(rec)
            else:
                skipped += 1

        logger.info(
            f"Collected {len(records)} valid records (skipped {skipped} deleted/removed) "
            f"for query='{search_query}'"
        )
        return records
