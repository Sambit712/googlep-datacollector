"""Evidence collector that normalizes submissions and comments into EvidenceRecord instances.

Preserves complete raw evidence, applies non-destructive cleaning, extracts
contextual comments with parent references, and assigns stable research IDs (RD_000001).
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from typing import Any, Iterable

from src.cleaner import clean_text, generate_preview
from src.models import EvidenceRecord

logger = logging.getLogger(__name__)

# Trivial/uninformative comments to filter out unless accompanied by context
_TRIVIAL_COMMENTS = {
    "same",
    "same here",
    "same here!",
    "+1",
    "following",
    "following this",
    "bump",
    "me too",
    "me too!",
    "this",
    "cfbr",
    "same problem",
    "same issue",
    "remindme!",
}


def _anonymize_author(username: str) -> str:
    """Generate a consistent pseudonym for an author username."""
    if not username or username in ("[deleted]", "[removed]", "[unknown]"):
        return "[deleted]"
    h = hashlib.sha256(username.encode("utf-8")).hexdigest()[:8]
    return f"anon_{h}"


class PostCollector:
    """Converts raw Reddit submissions and comments into normalized EvidenceRecord instances."""

    def __init__(
        self,
        max_comments: int = 3,
        starting_id: int = 1,
        anonymize_authors: bool = False,
        run_id: str = "",
    ):
        """
        Args:
            max_comments: Number of top-level comments to collect per post.
            starting_id: Starting integer sequence for research IDs (RD_xxxxxx).
            anonymize_authors: If True, pseudonymizes usernames for research privacy.
            run_id: Unique identifier for the collection run.
        """
        self.max_comments = max_comments
        self._id_counter = starting_id
        self.anonymize_authors = anonymize_authors
        self.run_id = run_id

    def _next_record_id(self) -> str:
        """Generate a stable, human-readable research ID, e.g. RD_000001."""
        rec_id = f"RD_{self._id_counter:06d}"
        self._id_counter += 1
        return rec_id

    @property
    def current_id_counter(self) -> int:
        """Return the next ID counter value."""
        return self._id_counter

    def _is_deleted_or_removed(self, submission: Any) -> bool:
        """Determine if a submission was deleted by user or removed by moderator."""
        if getattr(submission, "removed_by_category", None) is not None:
            return True

        selftext = getattr(submission, "selftext", "") or ""
        if selftext.strip() in ("[deleted]", "[removed]"):
            return True

        title = getattr(submission, "title", "") or ""
        if title.strip() in ("[deleted]", "[removed]"):
            return True

        return False

    def _extract_author(self, submission_or_comment: Any) -> str:
        """Extract author username, defaulting to '[deleted]', with optional anonymization."""
        author_attr = getattr(submission_or_comment, "author", None)
        if author_attr is None:
            return "[deleted]"

        if hasattr(author_attr, "name"):
            name = str(author_attr.name).strip()
        else:
            name = str(author_attr).strip()

        if not name or name in ("[deleted]", "[removed]", "None"):
            return "[deleted]"

        cleaned_name = name.replace("/u/", "").strip()
        if self.anonymize_authors:
            return _anonymize_author(cleaned_name)
        return cleaned_name

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

    def _is_trivial_comment(self, body: str) -> bool:
        """Determine if a comment is uninformative (e.g. 'Same here') without substance."""
        stripped = body.strip().lower().rstrip(".!")
        if len(stripped) < 8:
            return True
        if stripped in _TRIVIAL_COMMENTS:
            return True
        return False

    def _extract_contextual_comments(
        self,
        submission: Any,
        parent_record: EvidenceRecord,
        retrieved_at: str,
    ) -> list[EvidenceRecord]:
        """Extract top-level comments as standalone EvidenceRecords linked to the parent post."""
        if self.max_comments <= 0:
            return []

        comments_attr = getattr(submission, "comments", None)
        if comments_attr is None:
            return []

        if hasattr(comments_attr, "replace_more"):
            try:
                comments_attr.replace_more(limit=0)
            except Exception:
                pass

        comment_records: list[EvidenceRecord] = []
        try:
            for idx, comment in enumerate(comments_attr, 1):
                if len(comment_records) >= self.max_comments:
                    break

                if comment.__class__.__name__ == "MoreComments":
                    continue

                body = getattr(comment, "body", "")
                if not body and isinstance(comment, str):
                    body = comment

                raw_body = str(body).strip()
                if not raw_body or raw_body in ("[deleted]", "[removed]"):
                    continue

                # Filter trivial comments lacking context
                if self._is_trivial_comment(raw_body):
                    continue

                c_id = str(getattr(comment, "id", f"c_{idx}")).strip()
                c_source_id = c_id if c_id.startswith("t1_") else f"t1_{c_id}"
                c_author = self._extract_author(comment)
                c_created = self._format_timestamp(getattr(comment, "created_utc", 0))
                c_permalink = self._format_permalink(str(getattr(comment, "permalink", parent_record.url)))
                c_cleaned = clean_text(raw_body)
                c_preview = generate_preview(c_cleaned)

                rec = EvidenceRecord(
                    record_id=self._next_record_id(),
                    source="reddit",
                    source_type="reddit",
                    content_type="comment",
                    source_id=c_source_id,
                    subreddit=parent_record.subreddit,
                    subreddit_tier=parent_record.subreddit_tier,
                    title=f"Re: {parent_record.title}",
                    raw_text=raw_body,
                    cleaned_text=c_cleaned,
                    preview_text=c_preview,
                    author=c_author,
                    created_at=c_created,
                    retrieved_at=retrieved_at,
                    url=c_permalink,
                    query_used=parent_record.query_used,
                    queries_matched=list(parent_record.queries_matched),
                    run_id=self.run_id,
                    parent_id=parent_record.source_id,
                    parent_post_title=parent_record.title,
                    parent_post_text=parent_record.cleaned_text or parent_record.raw_text,
                    score=int(getattr(comment, "score", 0)),
                    num_comments=0,
                )
                comment_records.append(rec)
        except Exception as e:
            logger.debug(f"Error extracting comments for post {parent_record.source_id}: {e}")

        return comment_records

    def collect(
        self,
        submission: Any,
        search_query: str,
        subreddit_tier: str = "primary",
    ) -> EvidenceRecord | None:
        """Extract and normalize a single submission into an EvidenceRecord.

        Returns:
            EvidenceRecord if valid, or None if deleted or removed.
        """
        if self._is_deleted_or_removed(submission):
            logger.debug(f"Skipping deleted/removed submission {getattr(submission, 'id', 'unknown')}")
            return None

        raw_id = str(getattr(submission, "id", "")).strip()
        if not raw_id:
            return None

        source_id = raw_id if raw_id.startswith("t3_") else f"t3_{raw_id}"
        title = str(getattr(submission, "title", "")).strip()
        raw_selftext = str(getattr(submission, "selftext", "") or "").strip()
        cleaned_selftext = clean_text(raw_selftext)
        preview_text = generate_preview(cleaned_selftext or title)

        author = self._extract_author(submission)
        subreddit = self._extract_subreddit(submission)
        created_at = self._format_timestamp(getattr(submission, "created_utc", 0))
        retrieved_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        score = int(getattr(submission, "score", 0))
        num_comments = int(getattr(submission, "num_comments", 0))
        url = self._format_permalink(str(getattr(submission, "permalink", "")))

        # Also extract raw comment strings for backward-compatibility top_comments
        top_comment_strings: list[str] = []
        comments_attr = getattr(submission, "comments", None)
        if comments_attr and isinstance(comments_attr, list):
            for c in comments_attr[: self.max_comments]:
                c_body = getattr(c, "body", str(c)).strip()
                if c_body and c_body not in ("[deleted]", "[removed]"):
                    top_comment_strings.append(c_body)

        return EvidenceRecord(
            record_id=self._next_record_id(),
            source="reddit",
            source_type="reddit",
            content_type="post",
            source_id=source_id,
            subreddit=subreddit,
            subreddit_tier=subreddit_tier,
            title=title,
            raw_text=raw_selftext,
            cleaned_text=cleaned_selftext,
            preview_text=preview_text,
            author=author,
            created_at=created_at,
            retrieved_at=retrieved_at,
            url=url,
            query_used=search_query,
            queries_matched=[search_query] if search_query else [],
            run_id=self.run_id,
            score=score,
            num_comments=num_comments,
            top_comments=top_comment_strings,
        )

    def collect_with_comments(
        self,
        submission: Any,
        search_query: str,
        subreddit_tier: str = "primary",
    ) -> tuple[EvidenceRecord | None, list[EvidenceRecord]]:
        """Extract a post and its associated contextual comment records.

        Returns:
            Tuple of (post_record, list_of_comment_records).
        """
        post_record = self.collect(submission, search_query=search_query, subreddit_tier=subreddit_tier)
        if post_record is None:
            return None, []

        comment_records = self._extract_contextual_comments(
            submission=submission,
            parent_record=post_record,
            retrieved_at=post_record.retrieved_at,
        )
        return post_record, comment_records

    def collect_batch(
        self,
        submissions: Iterable[Any],
        search_query: str,
        subreddit_tier: str = "primary",
        include_comments: bool = False,
    ) -> list[EvidenceRecord]:
        """Collect and normalize a batch of submissions, optionally collecting comments.

        Returns:
            Flattened list of all valid post and comment EvidenceRecords.
        """
        all_records: list[EvidenceRecord] = []
        skipped = 0

        for sub in submissions:
            if include_comments and self.max_comments > 0:
                post, comments = self.collect_with_comments(
                    sub,
                    search_query=search_query,
                    subreddit_tier=subreddit_tier,
                )
                if post is not None:
                    all_records.append(post)
                    all_records.extend(comments)
                else:
                    skipped += 1
            else:
                post = self.collect(sub, search_query=search_query, subreddit_tier=subreddit_tier)
                if post is not None:
                    all_records.append(post)
                else:
                    skipped += 1

        logger.info(
            f"Collected {len(all_records)} evidence records "
            f"(skipped {skipped} deleted/removed) for query='{search_query}'"
        )
        return all_records
