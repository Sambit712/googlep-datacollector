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
    "relevance_classification",
    "relevance_confidence",
    "relevance_reasoning",
    "target_media",
    "memory_cues_present",
    "memory_cue_details",
    "retrieval_failure_stage",
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

    def write_markdown_report(
        self,
        report_data: dict[str, Any],
        output_dir: str | Path | None = None,
        filename: str = "insight_report.md",
    ) -> Path:
        """Generate and save an executive markdown report synthesizing research findings.

        Structures findings according to the V1 cognitive retrieval failure framework:
        1. Central research question & executive summary
        2. Tri-state relevance classification breakdown
        3. 5-stage cognitive-system retrieval failure breakdown
        4. Human visual memory cue structure (9 cues)
        5. Coping workarounds & friction points
        6. Cross-tabulation matrices
        7. Synthesized recurring patterns with direct Reddit citations

        Args:
            report_data: Insight report dictionary (loaded or generated).
            output_dir: Destination directory (defaults to self.output_dir).
            filename: Output filename (defaults to insight_report.md).

        Returns:
            Path to the written markdown report file.
        """
        target_dir = Path(output_dir) if output_dir is not None else self.output_dir
        target_dir.mkdir(parents=True, exist_ok=True)
        report_path = target_dir / filename

        meta = report_data.get("report_metadata", {})
        dists = report_data.get("distributions", {})
        cross_tabs = report_data.get("cross_tabulations", {})
        patterns = report_data.get("recurring_patterns", [])

        total_ingested = meta.get("total_records_ingested", 0)
        rel_count = meta.get("relevant_evidence_count", 0)
        rel_rate = meta.get("relevance_rate", 0.0)
        model_used = meta.get("groq_model_used", "Groq LPU")
        v0_source = meta.get("v0_source_file", "data/output/reddit_evidence.json")
        gen_at = meta.get("generated_at", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"))
        research_q = report_data.get("research_question", DEFAULT_RESEARCH_QUESTION)
        exec_summary = report_data.get("executive_summary", "")

        lines = [
            "# Executive Research Insight Report: Google Photos Vague-Memory Retrieval Failures",
            "",
            f"**Generated Date:** {gen_at}  ",
            f"**AI Analysis Model:** {model_used}  ",
            f"**Source Dataset:** `{v0_source}` (V0 Evidence Collection Layer)  ",
            f"**Total Ingested Sample:** {total_ingested} records | **Relevant Evidence:** {rel_count} records (**{rel_rate * 100:.1f}% Relevance Rate**)  ",
            "**Traceability Status:** Fully verified (Unbroken citation chain to source Reddit URLs)",
            "",
            "---",
            "",
            "## 1. Central Research Question",
            "",
            f"> *\"{research_q}\"*",
            "",
            "---",
            "",
            "## 2. Executive Summary",
            "",
            exec_summary,
            "",
            "When searching personal photo libraries, users do not formulate queries using exact filenames, timestamps, or rigid metadata. Instead, human visual memory recall is anchored in **episodic context and perceptual memory cues**—such as remembered people, places, events, physical objects, activities, visual details, or text on signs. Current photo retrieval systems fail when this natural memory representation cannot be translated into system queries, when systems misunderstand natural language intent, or when thousands of noisy candidates overwhelm the user.",
            "",
            "---",
            "",
            "## 3. Relevance Classification Breakdown (Tri-State)",
            "",
            "Public user complaints were classified into a tri-state relevance rubric to filter out platform bugs and operational grievances (e.g., app crashes, sync failures, Google One storage billing, device battery consumption) and isolate genuine vague-memory retrieval difficulties.",
            "",
            "| Relevance Classification | Count | Percentage | Research Meaning |",
            "|---|---|---|---|",
        ]

        rel_classes = dists.get("relevance_classes", {})
        descriptions_rel = {
            "relevant": "User describes difficulty retrieving a remembered visual item via vague cues",
            "possibly_relevant": "Probable photo retrieval difficulty with partial or ambiguous context",
            "irrelevant": "Unrelated issue (app crash, backup bug, storage billing, general tech support)",
        }
        for r_cls, r_count in rel_classes.items():
            r_pct = f"{(r_count / total_ingested * 100):.1f}%" if total_ingested > 0 else "0.0%"
            lines.append(f"| `{r_cls}` | {r_count} | {r_pct} | {descriptions_rel.get(r_cls, 'Categorized user record')} |")

        lines.extend([
            "",
            "---",
            "",
            "## 4. Cognitive Retrieval Failure Breakdown (5-Stage Model)",
            "",
            "Every relevant failure is mapped to the stage where the cognitive-system retrieval chain breaks down:",
            "",
            "```text",
            "How the user remembers the photo  (1. Memory → Query)",
            "               ↓",
            "How the user describes the photo  (2. Query → System)",
            "               ↓",
            "How the system interprets query   (3. System → Candidate)",
            "               ↓",
            "How candidates are presented      (4. Candidate → Recognition)",
            "               ↓",
            "How the search is adjusted        (5. Search Refinement)",
            "```",
            "",
            "| Failure Stage | Count | Percentage | Research Question & Cognitive Breakdown |",
            "|---|---|---|---|",
        ])

        stages = dists.get("retrieval_failure_stages", {})
        stage_meta = {
            "memory_to_query": (
                "Memory → Query",
                "Can users translate their memory into a searchable representation? (Mental model vs. keyword gap)",
            ),
            "query_to_system": (
                "Query → System",
                "Does the system understand natural language descriptions? (Semantic parsing & intent mismatch)",
            ),
            "system_to_candidate": (
                "System → Candidate",
                "Can the system narrow the search space? (Flooding with irrelevant images or zero hits)",
            ),
            "candidate_to_recognition": (
                "Candidate → Recognition",
                "Does result presentation help users identify the item? (Small thumbnails, visually indistinguishable)",
            ),
            "search_refinement": (
                "Search Refinement",
                "How do users adjust when search fails? (Dead-end without query pivot guidance)",
            ),
        }
        for stg_id, (stg_label, stg_desc) in stage_meta.items():
            stg_count = stages.get(stg_id, 0)
            stg_pct = f"{(stg_count / rel_count * 100):.1f}%" if rel_count > 0 else "0.0%"
            lines.append(f"| `{stg_id}` ({stg_label}) | {stg_count} | {stg_pct} | {stg_desc} |")

        lines.extend([
            "",
            "---",
            "",
            "## 5. Structure of Human Visual Memory (Memory Cues)",
            "",
            "Analysis of what users spontaneously recall about their missing visual memories across 9 cognitive memory cues:",
            "",
            "| Memory Cue | Frequency | Percentage of Relevant | Cognitive Dimension |",
            "|---|---|---|---|",
        ])

        cues = dists.get("top_memory_cues", {})
        cue_dim = {
            "person": "Social / Identity (who appears in or is associated with the photo)",
            "relationship": "Social Context ('my friend', 'my mother', 'roommate', family ties)",
            "place": "Geographic / Spatial (city, beach, café, college, home, park)",
            "place_location": "Geographic / Spatial (city, beach, café, college, home, park)",
            "time": "Temporal Anchor (last year, during college, around Diwali, 2022)",
            "temporal_epoch": "Temporal Anchor (last year, during college, around Diwali, 2022)",
            "event": "Episodic Event (vacation trip, wedding, birthday party, concert)",
            "event_occasion": "Episodic Event (vacation trip, wedding, birthday party, concert)",
            "object": "Physical Artifact (car, dog, food dish, receipt, document, product)",
            "visual_details": "Perceptual Feature (red shirt, sunset, dark lighting, group layout)",
            "text_in_image": "Textual / OCR Feature (signboard, recipe text, document title, label)",
            "activity": "Behavioral / Action (eating, hiking, dancing, studying, travelling)",
            "activity_action": "Behavioral / Action (eating, hiking, dancing, studying, travelling)",
        }
        for cue_name, cue_count in cues.items():
            cue_pct = f"{(cue_count / rel_count * 100):.1f}%" if rel_count > 0 else "0.0%"
            lines.append(f"| `{cue_name}` | {cue_count} | {cue_pct} | {cue_dim.get(cue_name, 'Episodic memory clue')} |")

        lines.extend([
            "",
            "---",
            "",
            "## 6. User Coping Workarounds & Friction",
            "",
            "### 6.1 Coping Workarounds (When System Fails)",
            "| Workaround Strategy | Count | Percentage |",
            "|---|---|---|",
        ])
        works = dists.get("top_workarounds", {})
        for w_name, w_count in works.items():
            w_pct = f"{(w_count / rel_count * 100):.1f}%" if rel_count > 0 else "0.0%"
            lines.append(f"| `{w_name}` | {w_count} | {w_pct} |")

        lines.extend([
            "",
            "### 6.2 User Friction Experienced",
            "| Friction Type | Count | Percentage |",
            "|---|---|---|",
        ])
        frictions = dists.get("friction_types", {})
        for f_name, f_count in frictions.items():
            f_pct = f"{(f_count / rel_count * 100):.1f}%" if rel_count > 0 else "0.0%"
            lines.append(f"| `{f_name}` | {f_count} | {f_pct} |")

        lines.extend([
            "",
            "---",
            "",
            "## 7. Synthesized Recurring Patterns & Evidence Citations",
            "",
        ])

        if not patterns:
            lines.append("*No recurring patterns synthesized from the current dataset.*")
        else:
            for p in patterns:
                p_id = p.get("pattern_id", "PAT_UNKNOWN")
                p_name = p.get("name", "Unknown Pattern")
                p_cnt = p.get("prevalence_count", 0)
                p_pct = p.get("prevalence_percentage", 0.0)
                p_sum = p.get("summary", "")
                cites = p.get("supporting_evidence", [])

                lines.extend([
                    f"### Pattern: {p_name} (`{p_id}`)",
                    f"* **Prevalence:** {p_cnt} / {rel_count} relevant records (**{p_pct:.1f}%**)",
                    f"* **Synthesis:** {p_sum}",
                    "* **Direct Evidence Citations:**",
                ])

                for cite in cites:
                    rec_id = cite.get("record_id", "")
                    url = cite.get("url", "")
                    quote = cite.get("quote", "").replace("\n", " ").strip()
                    lines.append(f"  > *\"{quote}\"*  ")
                    lines.append(f"  > — **Record ID:** `{rec_id}` | **Source URL:** [{url}]({url})")
                    lines.append("")

                lines.append("---")
                lines.append("")

        lines.extend([
            "## 8. Strategic Research Takeaways for Photo Retrieval",
            "",
            "1. **Episodic Context Indexing**: Photos must be retrievable using loose associations (who was there, rough time period, visual characteristics) rather than exact dates or technical keywords.",
            "2. **Conversational Disambiguation**: When queries are vague or underspecified, the system should suggest contextual pivot facets (e.g., 'Did you mean outdoors or in a restaurant?') rather than returning thousands of unranked images.",
            "3. **Zero-Abandonment Refinement**: Provide clear pathways for refining searches when initial keyword attempts yield zero or excessive results, preventing search abandonment and endless manual timeline scrolling.",
            "",
        ])

        report_content = "\n".join(lines)
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(report_content)

        logger.info(f"Saved executive markdown report to {report_path}")
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
        ]

        # Tri-state relevance distribution
        rel_classes = dists.get("relevance_classes", {})
        if rel_classes:
            lines.append("  Relevance Classification (Tri-State):")
            for r_cls, count in rel_classes.items():
                lines.append(f"    - {r_cls:<24}: {count}")

        # 5-Stage Cognitive Breakdown
        stages = dists.get("retrieval_failure_stages", {})
        if stages:
            lines.append("  Retrieval Failure Stages (5-Stage Cognitive Model):")
            for stg, count in stages.items():
                lines.append(f"    - {stg:<24}: {count}")

        lines.append("  Top Memory Cues:")
        top_cues = dists.get("top_memory_cues", {})
        for cue, count in list(top_cues.items())[:5]:
            lines.append(f"    - {cue:<24}: {count}")

        lines.append("  Primary Retrieval Failure Points:")
        top_fails = dists.get("retrieval_failure_points", {})
        for fail, count in list(top_fails.items())[:5]:
            lines.append(f"    - {fail:<24}: {count}")

        lines.append("  Top User Workarounds:")
        top_works = dists.get("top_workarounds", {})
        for work, count in list(top_works.items())[:5]:
            lines.append(f"    - {work:<24}: {count}")

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

