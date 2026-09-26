"""V1 Statistical Aggregation & Pattern Engine.

Processes AnalyzedEvidenceRecord datasets using Pandas to compute quantitative distributions,
multi-dimensional cross-tabulations, and recurring problem pattern clusters across users.
"""

from __future__ import annotations

import logging
from typing import Any
import pandas as pd

from src.models import AnalyzedEvidenceRecord

logger = logging.getLogger(__name__)


class PatternAggregator:
    """Aggregates research evidence and synthesizes empirical patterns using Pandas."""

    def __init__(self, records: list[AnalyzedEvidenceRecord] | list[dict[str, Any]]):
        """Initialize the aggregator with analyzed evidence records.

        Args:
            records: List of AnalyzedEvidenceRecord objects or flat/nested dictionaries.
        """
        # Convert records to flat dictionaries for DataFrame ingestion
        flat_records: list[dict[str, Any]] = []
        for rec in records:
            if isinstance(rec, AnalyzedEvidenceRecord):
                flat_records.append(rec.to_flat_dict())
            elif isinstance(rec, dict):
                if "analysis" in rec and isinstance(rec["analysis"], dict):
                    # Flatten nested dict
                    flat = {k: v for k, v in rec.items() if k != "analysis"}
                    flat.update(rec["analysis"])
                    flat_records.append(flat)
                else:
                    flat_records.append(dict(rec))

        self.df_all = pd.DataFrame(flat_records)

        # Standardize required columns if DataFrame is empty
        required_cols = [
            "record_id", "source_id", "title", "raw_text", "url", "author", "subreddit",
            "is_relevant", "relevance_confidence", "target_media",
            "memory_cues_present", "retrieval_failure_point", "failure_evidence",
            "workarounds_used", "friction_experienced", "desired_outcome"
        ]
        for col in required_cols:
            if col not in self.df_all.columns:
                self.df_all[col] = [] if col in ("memory_cues_present", "workarounds_used", "friction_experienced") else None

        # Filter for relevant records
        if not self.df_all.empty and "is_relevant" in self.df_all.columns:
            self.df_relevant = self.df_all[self.df_all["is_relevant"] == True].copy()
        else:
            self.df_relevant = pd.DataFrame(columns=self.df_all.columns)

        self.total_records = len(self.df_all)
        self.relevant_records = len(self.df_relevant)
        self.relevance_rate = (
            round(self.relevant_records / self.total_records, 4) if self.total_records > 0 else 0.0
        )

        logger.info(
            f"PatternAggregator initialized with {self.total_records} total records "
            f"({self.relevant_records} relevant, rate: {self.relevance_rate * 100:.1f}%)"
        )

    def compute_memory_cue_distribution(self) -> dict[str, int]:
        """Compute frequency distribution of memory cues retained by users."""
        if self.df_relevant.empty or "memory_cues_present" not in self.df_relevant.columns:
            return {}

        cues_series = self.df_relevant["memory_cues_present"].dropna()
        exploded = cues_series.explode()
        exploded = exploded[exploded.notna() & (exploded != "")]
        if exploded.empty:
            return {}
        counts = exploded.value_counts().to_dict()
        return {str(k): int(v) for k, v in counts.items()}

    def compute_failure_point_distribution(self) -> dict[str, int]:
        """Compute frequency distribution of retrieval breakdown points."""
        if self.df_relevant.empty or "retrieval_failure_point" not in self.df_relevant.columns:
            return {}

        failures = self.df_relevant["retrieval_failure_point"].dropna()
        failures = failures[failures.astype(str).str.strip() != ""]
        if failures.empty:
            return {}
        counts = failures.value_counts().to_dict()
        return {str(k): int(v) for k, v in counts.items()}

    def compute_workaround_distribution(self) -> dict[str, int]:
        """Compute frequency distribution of coping workarounds used by users."""
        if self.df_relevant.empty or "workarounds_used" not in self.df_relevant.columns:
            return {}

        workarounds = self.df_relevant["workarounds_used"].dropna()
        exploded = workarounds.explode()
        exploded = exploded[exploded.notna() & (exploded != "")]
        if exploded.empty:
            return {}
        counts = exploded.value_counts().to_dict()
        return {str(k): int(v) for k, v in counts.items()}

    def compute_media_type_distribution(self) -> dict[str, int]:
        """Compute frequency distribution of target media types."""
        if self.df_relevant.empty or "target_media" not in self.df_relevant.columns:
            return {}

        media = self.df_relevant["target_media"].dropna()
        media = media[media.astype(str).str.strip() != ""]
        if media.empty:
            return {}
        counts = media.value_counts().to_dict()
        return {str(k): int(v) for k, v in counts.items()}

    def compute_friction_distribution(self) -> dict[str, int]:
        """Compute frequency distribution of friction types experienced."""
        if self.df_relevant.empty or "friction_experienced" not in self.df_relevant.columns:
            return {}

        friction = self.df_relevant["friction_experienced"].dropna()
        exploded = friction.explode()
        exploded = exploded[exploded.notna() & (exploded != "")]
        if exploded.empty:
            return {}
        counts = exploded.value_counts().to_dict()
        return {str(k): int(v) for k, v in counts.items()}

    def compute_cross_tabulations(self) -> dict[str, Any]:
        """Compute multi-dimensional cross-tabulations between research categories."""
        cross_tabs: dict[str, Any] = {
            "memory_cues_vs_failure_points": {},
            "target_media_vs_workarounds": {},
        }

        if self.df_relevant.empty:
            return cross_tabs

        # 1. memory_cues vs retrieval_failure_point
        try:
            df_cues = self.df_relevant[["memory_cues_present", "retrieval_failure_point"]].explode("memory_cues_present")
            df_cues = df_cues.dropna()
            df_cues = df_cues[(df_cues["memory_cues_present"] != "") & (df_cues["retrieval_failure_point"] != "")]
            if not df_cues.empty:
                crosstab_cues = pd.crosstab(df_cues["memory_cues_present"], df_cues["retrieval_failure_point"])
                cross_tabs["memory_cues_vs_failure_points"] = {
                    str(cue): {str(fp): int(count) for fp, count in row.items() if count > 0}
                    for cue, row in crosstab_cues.iterrows()
                }
        except Exception as e:
            logger.warning(f"Failed to compute memory_cues_vs_failure_points cross-tab: {e}")

        # 2. target_media vs workarounds_used
        try:
            df_work = self.df_relevant[["target_media", "workarounds_used"]].explode("workarounds_used")
            df_work = df_work.dropna()
            df_work = df_work[(df_work["target_media"] != "") & (df_work["workarounds_used"] != "")]
            if not df_work.empty:
                crosstab_work = pd.crosstab(df_work["target_media"], df_work["workarounds_used"])
                cross_tabs["target_media_vs_workarounds"] = {
                    str(media): {str(w): int(count) for w, count in row.items() if count > 0}
                    for media, row in crosstab_work.iterrows()
                }
        except Exception as e:
            logger.warning(f"Failed to compute target_media_vs_workarounds cross-tab: {e}")

        return cross_tabs

    def synthesize_recurring_patterns(self, max_patterns: int = 5) -> list[dict[str, Any]]:
        """Cluster co-occurring breakdown patterns and extract supporting evidence citations.

        Args:
            max_patterns: Maximum number of patterns to return.

        Returns:
            List of recurring pattern dictionaries with citations.
        """
        if self.df_relevant.empty:
            return []

        patterns: list[dict[str, Any]] = []

        # Candidate pattern definitions with matching criteria functions
        candidate_definitions = [
            {
                "name": "Chronological Fatigue in Large Galleries",
                "summary": "Users retain episodic memory (who, where, rough era) but lack exact timestamps; timeline search forces hours of manual scrolling that leads to fatigue or abandonment.",
                "matcher": lambda row: (
                    row.get("retrieval_failure_point") in ("volume_overload", "temporal_fuzziness")
                    or "endless_scrolling" in (row.get("workarounds_used") or [])
                    or "temporal_epoch" in (row.get("memory_cues_present") or [])
                ),
            },
            {
                "name": "Vocabulary & Semantic Label Mismatch",
                "summary": "Users search using abstract concepts, emotions, or everyday descriptions that do not match the system's metadata or image labels.",
                "matcher": lambda row: (
                    row.get("retrieval_failure_point") in ("vocabulary_mismatch", "visual_semantic_gap")
                    or "keyword_guessing" in (row.get("workarounds_used") or [])
                ),
            },
            {
                "name": "Untagged Screenshot & Document Clutter",
                "summary": "Informational visual media (receipts, screenshots, memes) get drowned in photo feeds, making them unretrievable when exact text isn't indexed.",
                "matcher": lambda row: (
                    row.get("retrieval_failure_point") == "screenshot_clutter"
                    or row.get("target_media") in ("screenshot", "document_receipt", "meme_saved_image")
                    or "text_in_image" in (row.get("memory_cues_present") or [])
                ),
            },
            {
                "name": "Social & Peer Dependency Workarounds",
                "summary": "When search engines in personal libraries fail, users depend on asking friends, family, or searching social media messaging histories for sent copies.",
                "matcher": lambda row: (
                    "peer_inquiry" in (row.get("workarounds_used") or [])
                    or "external_social_backup" in (row.get("workarounds_used") or [])
                ),
            },
            {
                "name": "Missing Metadata & Device Migration Loss",
                "summary": "Photos transferred across devices, platforms, or cloud syncs lose timestamps or geotags, breaking timeline navigation and causing search abandonment.",
                "matcher": lambda row: (
                    row.get("retrieval_failure_point") == "missing_metadata"
                    or "abandonment" in (row.get("workarounds_used") or [])
                ),
            },
        ]

        pattern_idx = 1
        for candidate in candidate_definitions:
            matching_rows = []
            for _, row in self.df_relevant.iterrows():
                try:
                    if candidate["matcher"](row):
                        matching_rows.append(row)
                except Exception:
                    continue

            count = len(matching_rows)
            if count > 0:
                pct = round((count / self.relevant_records) * 100, 1)

                # Extract supporting evidence citations (up to 3 diverse quotes)
                citations: list[dict[str, str]] = []
                for m_row in matching_rows[:3]:
                    quote = (
                        str(m_row.get("failure_evidence") or "").strip()
                        or str(m_row.get("raw_text") or "")[:120].strip()
                    )
                    citations.append({
                        "record_id": str(m_row.get("record_id", "")),
                        "url": str(m_row.get("url", "")),
                        "quote": quote,
                    })

                patterns.append({
                    "pattern_id": f"PAT_{pattern_idx:03d}",
                    "name": candidate["name"],
                    "prevalence_count": count,
                    "prevalence_percentage": pct,
                    "summary": candidate["summary"],
                    "supporting_evidence": citations,
                })
                pattern_idx += 1

        # Sort patterns by prevalence descending
        patterns.sort(key=lambda p: p["prevalence_count"], reverse=True)
        return patterns[:max_patterns]

    def generate_summary(self) -> dict[str, Any]:
        """Generate comprehensive aggregated research report dictionary."""
        distributions = {
            "top_memory_cues": self.compute_memory_cue_distribution(),
            "retrieval_failure_points": self.compute_failure_point_distribution(),
            "top_workarounds": self.compute_workaround_distribution(),
            "target_media_types": self.compute_media_type_distribution(),
            "friction_types": self.compute_friction_distribution(),
        }

        cross_tabs = self.compute_cross_tabulations()
        recurring_patterns = self.synthesize_recurring_patterns()

        return {
            "statistics": {
                "total_records_ingested": self.total_records,
                "relevant_evidence_count": self.relevant_records,
                "relevance_rate": self.relevance_rate,
            },
            "distributions": distributions,
            "cross_tabulations": cross_tabs,
            "recurring_patterns": recurring_patterns,
        }
