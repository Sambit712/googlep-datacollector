"""Deduplication layer for Reddit Research Data-Retrieval System.

Filters duplicate PostRecords by post_id using an in-memory set
backed by a persistent JSON index file (seen_ids.json).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from src.models import PostRecord

logger = logging.getLogger(__name__)


class Deduplicator:
    """Filters duplicate PostRecords by post_id using an in-memory set
    backed by a persistent JSON index file."""

    def __init__(self, index_path: str = "data/seen_ids.json"):
        """Load existing seen IDs from index_path (if file exists).
        Initialize in-memory set for O(1) lookups.

        Args:
            index_path: Path to the JSON file storing previously seen post IDs.
        """
        self.index_path = Path(index_path)
        self._seen_ids: set[str] = set()
        self._duplicates_this_run: int = 0
        self._load()

    def _load(self) -> None:
        """Load seen IDs from the persistent index file."""
        if self.index_path.is_file():
            try:
                raw = self.index_path.read_text(encoding="utf-8")
                data = json.loads(raw)
                if isinstance(data, list):
                    self._seen_ids = set(str(item) for item in data)
                    logger.info(f"Loaded {len(self._seen_ids)} previously seen IDs from {self.index_path}")
                else:
                    logger.warning(f"Index file {self.index_path} does not contain a JSON array. Starting fresh.")
                    self._seen_ids = set()
            except (json.JSONDecodeError, OSError) as e:
                logger.warning(f"Failed to load index file {self.index_path}: {e}. Starting fresh.")
                self._seen_ids = set()
        else:
            logger.info(f"No existing index file at {self.index_path}. Starting with empty set.")

    def is_duplicate(self, post_id: str) -> bool:
        """Check if post_id has been seen before."""
        return post_id in self._seen_ids

    def mark_seen(self, post_id: str) -> None:
        """Add post_id to the in-memory set."""
        self._seen_ids.add(post_id)

    def filter(self, posts: list[PostRecord]) -> tuple[list[PostRecord], int]:
        """Filter a list of PostRecords, removing duplicates.

        Returns:
            Tuple of (unique_posts, duplicate_count).
            All unique posts are marked as seen after filtering.
        """
        unique: list[PostRecord] = []
        dup_count = 0

        for post in posts:
            if self.is_duplicate(post.post_id):
                dup_count += 1
                logger.debug(f"Duplicate post filtered: {post.post_id}")
            else:
                self.mark_seen(post.post_id)
                unique.append(post)

        self._duplicates_this_run += dup_count
        logger.info(f"Deduplication: {len(unique)} unique, {dup_count} duplicates filtered")
        return unique, dup_count

    def save(self) -> None:
        """Persist the current seen_ids set to the index file."""
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            sorted_ids = sorted(self._seen_ids)
            self.index_path.write_text(
                json.dumps(sorted_ids, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            logger.info(f"Saved {len(self._seen_ids)} seen IDs to {self.index_path}")
        except OSError as e:
            logger.error(f"Failed to save index file {self.index_path}: {e}")
            raise

    def stats(self) -> dict[str, Any]:
        """Return deduplication statistics.

        Returns:
            Dictionary with 'total_seen' and 'duplicates_this_run' counts.
        """
        return {
            "total_seen": len(self._seen_ids),
            "duplicates_this_run": self._duplicates_this_run,
        }
