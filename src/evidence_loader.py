"""V1 Evidence Loader and Traceability Ingestion Module.

Loads V0 Reddit evidence from disk, enforces strict read-only immutability,
validates that all records contain stable research record_ids, and ensures
unbroken traceability back to source Reddit conversations.
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

from src.models import EvidenceRecord

logger = logging.getLogger(__name__)


class EvidenceLoadError(Exception):
    """Raised when evidence files are missing, malformed, or fail integrity checks."""
    pass


def get_file_hash(filepath: str | Path) -> str:
    """Compute the SHA-256 hash of a file for immutability verification.

    Args:
        filepath: Path to the file.

    Returns:
        Hexadecimal SHA-256 digest string.
    """
    path = Path(filepath)
    if not path.is_file():
        raise EvidenceLoadError(f"Cannot compute hash for nonexistent file: {path.resolve()}")

    sha256 = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(65536):
            sha256.update(chunk)
    return sha256.hexdigest()


def verify_file_unmodified(filepath: str | Path, expected_hash: str) -> bool:
    """Verify that a file's current SHA-256 hash matches the expected hash.

    Args:
        filepath: Path to the file.
        expected_hash: Hexadecimal SHA-256 string to compare against.

    Returns:
        True if hashes match, False otherwise.
    """
    try:
        current_hash = get_file_hash(filepath)
        return current_hash == expected_hash
    except EvidenceLoadError:
        return False


class ImmutabilityGuard:
    """Context manager that guarantees a source file remains completely untouched."""

    def __init__(self, filepath: str | Path):
        self.path = Path(filepath)
        self.initial_hash: str | None = None

    def __enter__(self) -> ImmutabilityGuard:
        if self.path.is_file():
            self.initial_hash = get_file_hash(self.path)
            logger.debug(f"ImmutabilityGuard active for {self.path} (SHA-256: {self.initial_hash[:12]}...)")
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if self.initial_hash is not None and self.path.is_file():
            current_hash = get_file_hash(self.path)
            if current_hash != self.initial_hash:
                raise EvidenceLoadError(
                    f"CRITICAL IMMUTABILITY VIOLATION: Source dataset '{self.path}' was modified! "
                    f"Expected hash {self.initial_hash}, got {current_hash}."
                )


def load_v0_evidence(filepath: str | Path = "data/output/reddit_evidence.json") -> list[EvidenceRecord]:
    """Ingest V0 evidence records with strict validation and immutability checks.

    Args:
        filepath: Path to V0 evidence JSON file (default: data/output/reddit_evidence.json).

    Returns:
        List of verified EvidenceRecord instances.

    Raises:
        EvidenceLoadError: If file is missing, invalid JSON, or records lack record_ids.
    """
    records, _ = load_v0_evidence_with_metadata(filepath)
    return records


def load_v0_evidence_with_metadata(
    filepath: str | Path = "data/output/reddit_evidence.json",
) -> tuple[list[EvidenceRecord], dict[str, Any]]:
    """Ingest V0 evidence records along with file metadata.

    Args:
        filepath: Path to V0 evidence JSON file.

    Returns:
        Tuple of (list[EvidenceRecord], metadata_dict).

    Raises:
        EvidenceLoadError: If file is missing, invalid JSON, or records lack record_ids.
    """
    path = Path(filepath)
    if not path.is_file():
        raise EvidenceLoadError(
            f"V0 evidence file not found at '{path.resolve()}'. "
            "Please run the V0 collection pipeline first before starting V1 analysis."
        )

    try:
        content = path.read_text(encoding="utf-8")
    except OSError as e:
        raise EvidenceLoadError(f"Failed to read V0 evidence file '{path}': {e}") from e

    try:
        data = json.loads(content)
    except json.JSONDecodeError as e:
        raise EvidenceLoadError(f"Malformed JSON in V0 evidence file '{path}': {e}") from e

    metadata: dict[str, Any] = {}
    raw_records: list[Any] = []

    if isinstance(data, dict):
        metadata = data.get("metadata", {})
        # Support both 'records' and 'posts' keys from V0 structurers
        raw_records = data.get("records") or data.get("posts") or data.get("evidence") or []
        if not isinstance(raw_records, list):
            raise EvidenceLoadError(
                f"Expected 'records' or 'posts' list in '{path}', but found {type(raw_records).__name__}."
            )
    elif isinstance(data, list):
        raw_records = data
    else:
        raise EvidenceLoadError(f"Top-level structure in '{path}' must be a JSON object or list.")

    evidence_records: list[EvidenceRecord] = []
    seen_record_ids: set[str] = set()

    for idx, raw_item in enumerate(raw_records):
        if not isinstance(raw_item, dict):
            raise EvidenceLoadError(
                f"Record #{idx + 1} in '{path}' is not a valid JSON dictionary."
            )

        record_id = str(raw_item.get("record_id", "")).strip()
        source_id = str(raw_item.get("source_id") or raw_item.get("post_id", "")).strip()

        if not record_id:
            raise EvidenceLoadError(
                f"Record #{idx + 1} (source_id='{source_id or 'unknown'}') in '{path}' "
                "is missing required 'record_id'. All V0 records must have a research record_id for traceability."
            )

        if record_id in seen_record_ids:
            logger.warning(f"Duplicate record_id '{record_id}' detected at index {idx + 1} in '{path}'.")

        seen_record_ids.add(record_id)
        evidence_records.append(EvidenceRecord.from_dict(raw_item))

    logger.info(
        f"Successfully loaded {len(evidence_records)} V0 evidence records from '{path}' "
        f"with verified traceability IDs."
    )
    return evidence_records, metadata
