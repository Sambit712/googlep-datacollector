"""Deduplication layer for Reddit Research Evidence-Collection System.

Ensures evidence uniqueness by (source, source_id) while tracking all search queries
that surfaced a given record across multiple query iterations.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from src.models import EvidenceRecord

logger = logging.getLogger(__name__)


class Deduplicator:
    """Filters duplicate EvidenceRecords by source + source_id while accumulating all matching queries."""

    def __init__(self, index_path: str = "data/seen_ids.json"):
        """Initialize in-memory deduplication set and load persistent index.

        Args:
            index_path: Path to the persistent JSON index file.
        """
        self.index_path = Path(index_path)
        self._seen_keys: set[str] = set()
        self._unique_records_by_key: dict[str, EvidenceRecord] = {}
        self._duplicates_this_run: int = 0
        self.last_record_number: int = 0
        self._load()

    def _normalize_key(self, source_id: str, source: str = "reddit") -> str:
        """Create a composite uniqueness key."""
        clean_id = str(source_id).strip()
        clean_source = str(source).strip().lower()
        if ":" in clean_id:
            return clean_id
        return f"{clean_source}:{clean_id}"

    def _extract_id_from_key(self, key: str) -> str:
        """Extract clean source_id from composite key."""
        if ":" in key:
            return key.split(":", 1)[1]
        return key

    def _load(self) -> None:
        """Load seen keys and ID sequence from the persistent index file."""
        if self.index_path.is_file():
            try:
                raw = self.index_path.read_text(encoding="utf-8")
                data = json.loads(raw)
                if isinstance(data, list):
                    for item in data:
                        raw_str = str(item).strip()
                        norm_key = self._normalize_key(raw_str)
                        self._seen_keys.add(norm_key)
                        self._seen_keys.add(self._extract_id_from_key(norm_key))
                    self.last_record_number = len(data)
                    logger.info(f"Loaded {len(data)} previously seen IDs from {self.index_path}")
                elif isinstance(data, dict):
                    seen_list = data.get("seen_keys", data.get("seen_ids", []))
                    for item in seen_list:
                        raw_str = str(item).strip()
                        norm_key = self._normalize_key(raw_str)
                        self._seen_keys.add(norm_key)
                        self._seen_keys.add(self._extract_id_from_key(norm_key))
                    self.last_record_number = int(data.get("last_record_number", len(seen_list)))
                    logger.info(f"Loaded {len(seen_list)} previously seen IDs from {self.index_path}")
                else:
                    logger.warning(f"Index file {self.index_path} has unexpected format. Starting fresh.")
                    self._seen_keys = set()
            except (json.JSONDecodeError, OSError) as e:
                logger.warning(f"Failed to load index file {self.index_path}: {e}. Starting fresh.")
                self._seen_keys = set()
        else:
            logger.info(f"No existing index file at {self.index_path}. Starting with empty deduplication set.")

    def is_duplicate(self, source_id: str, source: str = "reddit") -> bool:
        """Check if source_id has been seen before."""
        key = self._normalize_key(source_id, source)
        raw_id = self._extract_id_from_key(source_id)
        return key in self._seen_keys or raw_id in self._seen_keys

    def mark_seen(self, source_id: str, source: str = "reddit") -> None:
        """Add source_id to the in-memory set."""
        key = self._normalize_key(source_id, source)
        raw_id = self._extract_id_from_key(source_id)
        self._seen_keys.add(key)
        self._seen_keys.add(raw_id)

    def filter(self, records: list[EvidenceRecord]) -> tuple[list[EvidenceRecord], int]:
        """Filter duplicate records while accumulating queries for repeated matches.

        If a record was already accepted during the current run, its queries_matched
        list is updated with any new query that found it.

        Args:
            records: Batch of EvidenceRecords to process.

        Returns:
            Tuple of (unique_records, duplicates_filtered_count).
        """
        unique: list[EvidenceRecord] = []
        dup_count = 0

        for record in records:
            key = self._normalize_key(record.source_id, record.source)
            raw_id = self._extract_id_from_key(record.source_id)

            if key in self._seen_keys or raw_id in self._seen_keys:
                dup_count += 1
                self._duplicates_this_run += 1
                # If this record was already collected in the current run, append new query to it
                existing = self._unique_records_by_key.get(key)
                if existing is not None and record.query_used:
                    if record.query_used not in existing.queries_matched:
                        existing.queries_matched.append(record.query_used)
            else:
                self._seen_keys.add(key)
                self._seen_keys.add(raw_id)
                self._unique_records_by_key[key] = record
                unique.append(record)

                # Track highest research ID number
                if record.record_id and record.record_id.startswith("RD_"):
                    try:
                        seq_num = int(record.record_id.split("_")[1])
                        if seq_num > self.last_record_number:
                            self.last_record_number = seq_num
                    except (IndexError, ValueError):
                        pass

        logger.info(f"Deduplication: {len(unique)} unique, {dup_count} duplicates filtered")
        return unique, dup_count

    def save(self) -> None:
        """Persist seen IDs to the index file as a JSON list."""
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        # Save unique clean raw IDs for clean formatting
        raw_ids = sorted({self._extract_id_from_key(k) for k in self._seen_keys})
        self.index_path.write_text(json.dumps(raw_ids, indent=2), encoding="utf-8")
        logger.info(f"Saved {len(raw_ids)} seen IDs to {self.index_path}")

    def stats(self) -> dict[str, int]:
        """Return deduplication statistics."""
        raw_ids = {self._extract_id_from_key(k) for k in self._seen_keys}
        return {
            "total_seen": len(raw_ids),
            "duplicates_this_run": self._duplicates_this_run,
            "last_record_number": self.last_record_number,
        }
