"""V1 Serialization & Insight Reporting Layer.

Serializes analyzed evidence records to `analyzed_evidence.json` (canonical nested format)
and `analyzed_evidence.csv` (flattened tabular view with zero text truncation).
Compiles and exports the aggregated research summary to `insight_report.json` with
full traceability citations back to source Reddit evidence.
"""

from __future__ import annotations

import csv
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.models import AnalyzedEvidenceRecord

logger = logging.getLogger(__name__)

DEFAULT_RESEARCH_QUESTION = (
    "Why does photo retrieval fail when users remember a photo or its context, "
    "but cannot precisely describe it to the search system?"
)

DEFAULT_V0_SOURCE_FILE = "data/output/reddit_evidence.json"
DEFAULT_GROQ_MODEL = "llama-3.3-70b-versatile"

# Column order for analyzed_evidence.csv
ANALYZED_CSV_COLUMNS = [
    "record_id",
    "source_id",
    "title",
    "raw_text",
    "url",
    "author",
    "subreddit",
    "created_at",
    "retrieved_at",
    "queries_matched",
    "analyzed_at",
    "model_used",
    "is_relevant",
    "relevance_confidence",
    "relevance_reasoning",
    "target_media",
    "memory_cues_present",
    "memory_cue_details",
    "retrieval_failure_point",
    "failure_evidence",
    "workarounds_used",
    "friction_experienced",
    "desired_outcome",
]

LIST_SEPARATOR = "; "


class InsightReporter:
    """Serializes V1 analyzed evidence and formats executive insight reports."""

    def __init__(self, output_dir: str | Path = "data/output"):
        self.output_dir = Path(output_dir)

    def write_analyzed_evidence(
        self,
        records: list[AnalyzedEvidenceRecord | dict[str, Any]],
        output_dir: str | Path | None = None,
        formats: list[str] | str = "both",
    ) -> dict[str, Any]:
        """Serialize analyzed evidence records to JSON and/or CSV.

        Args:
            records: List of AnalyzedEvidenceRecord objects or dictionary equivalents.
            output_dir: Target directory (defaults to self.output_dir).
            formats: "json", "csv", or "both" (or list containing ["json", "csv"]).

        Returns:
            Dictionary containing written file paths and record count.
        """
        target_dir = Path(output_dir) if output_dir is not None else self.output_dir
        target_dir.mkdir(parents=True, exist_ok=True)

        # Normalize formats
        if isinstance(formats, str):
            fmt_str = formats.lower().strip()
            format_set = {"json", "csv"} if fmt_str == "both" else {fmt_str}
        else:
            format_set = {f.lower().strip() for f in formats}

        # Normalize records to AnalyzedEvidenceRecord objects
        norm_records: list[AnalyzedEvidenceRecord] = []
        for r in records:
            if isinstance(r, AnalyzedEvidenceRecord):
                norm_records.append(r)
            elif isinstance(r, dict):
                norm_records.append(AnalyzedEvidenceRecord.from_dict(r))
            else:
                raise TypeError(f"Expected AnalyzedEvidenceRecord or dict, got {type(r)}")

        files_written: list[str] = []
        json_path: Path | None = None
        csv_path: Path | None = None

        if "json" in format_set:
            json_path = target_dir / "analyzed_evidence.json"
            self._write_json(norm_records, json_path)
            files_written.append(str(json_path))

        if "csv" in format_set:
            csv_path = target_dir / "analyzed_evidence.csv"
            self._write_csv(norm_records, csv_path)
            files_written.append(str(csv_path))

        logger.info(
            f"InsightReporter wrote {len(norm_records)} analyzed records to "
            f"{len(files_written)} file(s): {', '.join(files_written)}"
        )

        result: dict[str, Any] = {
            "total_records": len(norm_records),
            "files_written": files_written,
        }
        if json_path is not None:
            result["json_file"] = str(json_path)
        if csv_path is not None:
            result["csv_file"] = str(csv_path)

        return result

    def _write_json(self, records: list[AnalyzedEvidenceRecord], path: Path) -> Path:
        """Write canonical nested JSON array of analyzed records."""
        payload = [r.to_dict(nested_analysis=True) for r in records]
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
        logger.info(f"Wrote canonical analyzed evidence JSON: {path} ({len(records)} records)")
        return path

    def _write_csv(self, records: list[AnalyzedEvidenceRecord], path: Path) -> Path:
        """Write flattened CSV view with zero text truncation."""
        with open(path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=ANALYZED_CSV_COLUMNS,
                extrasaction="ignore",
                quoting=csv.QUOTE_MINIMAL,
            )
            writer.writeheader()

            for r in records:
                flat_row = r.to_flat_dict()

                # Delimit list fields
                for list_field in (
                    "queries_matched",
                    "memory_cues_present",
                    "workarounds_used",
                    "friction_experienced",
                ):
                    val = flat_row.get(list_field)
                    if isinstance(val, list):
                        flat_row[list_field] = LIST_SEPARATOR.join(str(item) for item in val)

                # Format dictionary fields safely
                details_val = flat_row.get("memory_cue_details")
                if isinstance(details_val, dict):
                    flat_row["memory_cue_details"] = json.dumps(details_val, ensure_ascii=False)

                writer.writerow(flat_row)

        logger.info(f"Wrote flattened analyzed evidence CSV: {path} ({len(records)} records, zero truncation)")
        return path

    def write_insight_report(
        self,
        aggregations_or_summary: dict[str, Any],
        patterns: list[dict[str, Any]] | None = None,
        metadata: dict[str, Any] | None = None,
        output_dir: str | Path | None = None,
        filename: str = "insight_report.json",
        groq_model: str = DEFAULT_GROQ_MODEL,
        v0_source_file: str = DEFAULT_V0_SOURCE_FILE,
        research_question: str | None = None,
        executive_summary: str | None = None,
    ) -> Path:
        """Format and write executive research insight report.

        Args:
            aggregations_or_summary: Aggregation summary dictionary (as returned by
                PatternAggregator.generate_summary()) or univariate distributions.
            patterns: Optional list of recurring patterns with citations (overrides summary).
            metadata: Optional report metadata dictionary (overrides defaults).
            output_dir: Target directory (defaults to self.output_dir).
            filename: Output filename (defaults to insight_report.json).
            groq_model: LLM model identifier used for analysis.
            v0_source_file: Relative path to source V0 evidence dataset.
            research_question: Central research question string.
            executive_summary: High-level overview narrative.

        Returns:
            Path to written insight_report.json file.
        """
        target_dir = Path(output_dir) if output_dir is not None else self.output_dir
        target_dir.mkdir(parents=True, exist_ok=True)
        report_path = target_dir / filename

        # Extract distributions, cross-tabulations, patterns, and stats
        distributions = aggregations_or_summary.get("distributions", aggregations_or_summary)
        cross_tabulations = aggregations_or_summary.get("cross_tabulations", {})

        recurring_patterns = (
            patterns
            if patterns is not None
            else aggregations_or_summary.get("recurring_patterns", [])
        )

        stats = aggregations_or_summary.get("statistics", {})
        total_ingested = stats.get("total_records_ingested", 0)
        relevant_count = stats.get("relevant_evidence_count", 0)
        relevance_rate = stats.get("relevance_rate", 0.0)

        # Build report_metadata
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        report_metadata: dict[str, Any] = {
            "generated_at": now_iso,
            "v0_source_file": v0_source_file,
            "total_records_ingested": total_ingested,
            "relevant_evidence_count": relevant_count,
            "relevance_rate": relevance_rate,
            "groq_model_used": groq_model,
        }

        if metadata:
            report_metadata.update(metadata)

        # Build executive summary narrative if not explicitly provided
        exec_summary = executive_summary or self._generate_default_executive_summary(
            report_metadata, distributions, recurring_patterns
        )

        report_payload: dict[str, Any] = {
            "report_metadata": report_metadata,
            "research_question": research_question or DEFAULT_RESEARCH_QUESTION,
            "executive_summary": exec_summary,
            "distributions": distributions,
            "cross_tabulations": cross_tabulations,
            "recurring_patterns": recurring_patterns,
        }

        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report_payload, f, indent=2, ensure_ascii=False)

        logger.info(f"Saved executive insight report to {report_path}")
        return report_path

    def _generate_default_executive_summary(
        self,
        metadata: dict[str, Any],
        distributions: dict[str, Any],
        recurring_patterns: list[dict[str, Any]],
    ) -> str:
        """Compose a concise narrative synthesizing the research findings."""
        rel_count = metadata.get("relevant_evidence_count", 0)
        total_count = metadata.get("total_records_ingested", 0)
        rel_rate = metadata.get("relevance_rate", 0.0)

        # Identify top cue and failure point
        top_cues = distributions.get("top_memory_cues", {})
        top_failures = distributions.get("retrieval_failure_points", {})
        top_workarounds = distributions.get("top_workarounds", {})

        top_cue_name = next(iter(top_cues.keys())) if top_cues else "temporal_epoch"
        top_fail_name = next(iter(top_failures.keys())) if top_failures else "temporal_fuzziness"
        top_workaround_name = next(iter(top_workarounds.keys())) if top_workarounds else "endless_scrolling"

        narrative = (
            f"Out of {total_count} ingested evidence records, {rel_count} ({rel_rate * 100:.1f}%) "
            f"demonstrated clear vague-memory photo retrieval failures. "
            f"The primary memory cue recalled by users was '{top_cue_name}', while the dominant retrieval breakdown "
            f"was '{top_fail_name}'. Users frequently resorted to coping strategies such as '{top_workaround_name}'. "
            f"Synthesized analysis identified {len(recurring_patterns)} recurring failure patterns with full citation traceability."
        )
        return narrative

    @classmethod
    def load_analyzed_evidence(cls, path: str | Path) -> list[AnalyzedEvidenceRecord]:
        """Read and parse analyzed evidence records from JSON file.

        Supports both raw list format and wrapped dictionary format.
        """
        file_path = Path(path)
        if not file_path.exists():
            raise FileNotFoundError(f"Analyzed evidence file not found: {file_path}")

        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        records_data = data if isinstance(data, list) else data.get("records", data.get("posts", []))
        return [AnalyzedEvidenceRecord.from_dict(item) for item in records_data]

    @classmethod
    def load_insight_report(cls, path: str | Path) -> dict[str, Any]:
        """Read and parse insight report from JSON file."""
        file_path = Path(path)
        if not file_path.exists():
            raise FileNotFoundError(f"Insight report file not found: {file_path}")

        with open(file_path, "r", encoding="utf-8") as f:
            report: dict[str, Any] = json.load(f)

        return report

    def print_summary(self, report: dict[str, Any]) -> None:
        """Print formatted executive summary to console and log."""
        meta = report.get("report_metadata", {})
        dists = report.get("distributions", {})
        patterns = report.get("recurring_patterns", [])

        lines = [
            "=" * 76,
            "GOOGLE PHOTOS VAGUE-MEMORY RETRIEVAL — V1 INSIGHT REPORT",
            "=" * 76,
            f"  Generated At:          {meta.get('generated_at', '')}",
            f"  Model Used:            {meta.get('groq_model_used', '')}",
            f"  V0 Source:             {meta.get('v0_source_file', '')}",
            f"  Total Ingested:        {meta.get('total_records_ingested', 0)}",
            f"  Relevant Evidence:     {meta.get('relevant_evidence_count', 0)} ({meta.get('relevance_rate', 0.0)*100:.1f}%)",
            "-" * 76,
            f"  Research Question:     {report.get('research_question', '')}",
            "-" * 76,
            "  Top Memory Cues:",
        ]

        top_cues = dists.get("top_memory_cues", {})
        for cue, count in list(top_cues.items())[:5]:
            lines.append(f"    - {cue:<26}: {count}")

        lines.append("  Primary Retrieval Failure Points:")
        top_fails = dists.get("retrieval_failure_points", {})
        for fail, count in list(top_fails.items())[:5]:
            lines.append(f"    - {fail:<26}: {count}")

        lines.append("  Top User Workarounds:")
        top_works = dists.get("top_workarounds", {})
        for work, count in list(top_works.items())[:5]:
            lines.append(f"    - {work:<26}: {count}")

        lines.append("-" * 76)
        lines.append(f"  Recurring Problem Patterns Identified ({len(patterns)} total):")
        for p in patterns:
            prev = f"{p.get('prevalence_count', 0)} ({p.get('prevalence_percentage', 0.0)}%)"
            lines.append(f"    [{p.get('pattern_id', '')}] {p.get('name', '')} — Prevalence: {prev}")
            lines.append(f"          Summary: {p.get('summary', '')}")
            citations = p.get("supporting_evidence", [])
            if citations:
                sample_cite = citations[0]
                lines.append(f"          Sample Cite: [{sample_cite.get('record_id', '')}] \"{sample_cite.get('quote', '')}\"")

        lines.append("=" * 76)

        formatted = "\n".join(lines)
        print(formatted)
        for line in lines:
            logger.info(line)
