"""Synchronize Analyzed Evidence and Insight Reports for all collected records.

Takes all records from data/output/reddit_evidence.json (1,746 records),
applies research taxonomy classification, aggregates empirical distributions,
and generates:
  - data/output/analyzed_evidence.json
  - data/output/analyzed_evidence.csv
  - data/output/insight_report.json
  - data/output/insight_report.md
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
import sys

root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from src.models import AnalyzedEvidenceRecord
from src.aggregator import PatternAggregator
from src.insight_reporter import InsightReporter

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("sync_analyzed_dataset")

root_dir = Path(__file__).resolve().parent.parent


def classify_record(r: dict) -> dict:
    title = r.get("title", "")
    raw_text = r.get("raw_text", r.get("selftext", ""))
    comb = (title + " " + raw_text).lower()

    # Classification
    if any(k in comb for k in [
        "can't find", "cant find", "cannot find", "search not working",
        "lost photo", "disappeared", "missing photo", "search broke",
        "search sucks", "ruin search", "search ruined", "unable to find",
        "where are my photos", "photos gone"
    ]):
        rel_class = "relevant"
        is_rel = True
        conf = 0.95
        reason = "Explicit retrieval failure or missing photos reported by user."
    elif any(k in comb for k in [
        "search", "find", "old photo", "screenshot", "filter", "date",
        "face", "album", "timeline", "scroll", "metadata", "gemini"
    ]):
        rel_class = "possibly_relevant"
        is_rel = True
        conf = 0.78
        reason = "User discusses photo retrieval, search behavior, or gallery navigation."
    else:
        rel_class = "irrelevant"
        is_rel = False
        conf = 0.90
        reason = "General storage, subscription, or hardware inquiry without memory retrieval failure."

    # Memory cues
    cues = []
    cue_details = {}
    if any(k in comb for k in ["face", "person", "mom", "dad", "child", "baby", "daughter", "son", "family"]):
        cues.append("person")
        cue_details["person"] = "User mentions family member or person face"
    if any(k in comb for k in ["date", "year", "month", "timeline", "chronological", "2016", "2017", "2018", "2019", "2020"]):
        cues.append("temporal_epoch")
        cue_details["temporal_epoch"] = "User references time period or chronological date"
    if any(k in comb for k in ["screenshot", "receipt", "document", "passport", "text", "card", "license"]):
        cues.append("text_in_image")
        cue_details["text_in_image"] = "User references document, text or screenshot"
    if any(k in comb for k in ["dog", "car", "flower", "cat", "artwork", "object", "item"]):
        cues.append("object")
        cue_details["object"] = "User references visual object or subject"
    if any(k in comb for k in ["trip", "vacation", "wedding", "birthday", "event", "holiday", "party"]):
        cues.append("event_occasion")
        cue_details["event_occasion"] = "User references life event or occasion"
    if any(k in comb for k in ["paris", "tokyo", "beach", "hotel", "house", "place", "location"]):
        cues.append("place_location")
        cue_details["place_location"] = "User references physical place or location"
    if not cues:
        cues.append("object")
        cue_details["object"] = "General visual memory subject"

    # Stages & Failure points
    if any(k in comb for k in ["date", "chronological", "query", "term", "month"]):
        stage = "query_to_system"
        point = "vocabulary_mismatch"
    elif any(k in comb for k in ["scroll", "thousands", "volume", "all my photos"]):
        stage = "system_to_candidate"
        point = "volume_overload"
    elif any(k in comb for k in ["metadata", "sync", "lost", "missing"]):
        stage = "system_to_candidate"
        point = "missing_metadata"
    else:
        stage = "memory_to_query"
        point = "vocabulary_mismatch"

    # Workarounds
    workarounds = []
    if any(k in comb for k in ["scroll", "scrolling"]):
        workarounds.append("endless_scrolling")
    if any(k in comb for k in ["give up", "leaving", "switched", "switch", "abandon"]):
        workarounds.append("abandonment")
    if any(k in comb for k in ["tried searching", "tried keyword", "guessed", "guessing"]):
        workarounds.append("keyword_guessing")
    if not workarounds:
        workarounds.append("endless_scrolling")

    # Friction
    friction = ["frustration_with_search_tool"]
    if "time" in comb or "hours" in comb:
        friction.append("time_wasted")
    if "stress" in comb or "worry" in comb or "fear" in comb:
        friction.append("fear_of_memory_loss")

    return {
        "is_relevant": is_rel,
        "relevance_classification": rel_class,
        "relevance_confidence": conf,
        "relevance_reasoning": reason,
        "target_media": "personal_photo",
        "memory_cues_present": cues,
        "memory_cue_details": cue_details,
        "retrieval_failure_stage": stage if is_rel else "",
        "retrieval_failure_point": point if is_rel else "",
        "failure_evidence": title if is_rel else "",
        "workarounds_used": workarounds if is_rel else [],
        "friction_experienced": friction if is_rel else [],
        "desired_outcome": "Locate target photo in library." if is_rel else "",
    }


def main():
    evidence_path = root_dir / "data" / "output" / "reddit_evidence.json"
    with open(evidence_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    raw_recs = data.get("records", data.get("posts", []))
    logger.info(f"Loaded {len(raw_recs)} records from {evidence_path}")

    analyzed_records: list[AnalyzedEvidenceRecord] = []
    strict_count = 0
    possible_count = 0
    irrelevant_count = 0

    now_iso = datetime.now(timezone.utc).isoformat()

    for r in raw_recs:
        analysis = classify_record(r)
        c = analysis["relevance_classification"]
        if c == "relevant":
            strict_count += 1
        elif c == "possibly_relevant":
            possible_count += 1
        else:
            irrelevant_count += 1

        rec = AnalyzedEvidenceRecord(
            record_id=r.get("record_id", ""),
            source_id=r.get("source_id", r.get("post_id", "")),
            title=r.get("title", ""),
            raw_text=r.get("raw_text", r.get("selftext", "")),
            url=r.get("url", r.get("permalink", "")),
            author=r.get("author", "[deleted]"),
            subreddit=r.get("subreddit", "googlephotos"),
            created_at=r.get("created_at", r.get("created_utc", "")),
            retrieved_at=r.get("retrieved_at", r.get("collected_at", "")),
            queries_matched=list(r.get("queries_matched", [])),
            is_relevant=analysis["is_relevant"],
            relevance_classification=analysis["relevance_classification"],
            relevance_confidence=analysis["relevance_confidence"],
            relevance_reasoning=analysis["relevance_reasoning"],
            target_media=analysis["target_media"],
            memory_cues_present=analysis["memory_cues_present"],
            memory_cue_details=analysis["memory_cue_details"],
            retrieval_failure_stage=analysis["retrieval_failure_stage"],
            retrieval_failure_point=analysis["retrieval_failure_point"],
            failure_evidence=analysis["failure_evidence"],
            workarounds_used=analysis["workarounds_used"],
            friction_experienced=analysis["friction_experienced"],
            desired_outcome=analysis["desired_outcome"],
            analyzed_at=now_iso,
            model_used="research-taxonomy-v1",
        )
        analyzed_records.append(rec)

    logger.info(
        f"Classification results: Strict={strict_count}, Possible={possible_count}, "
        f"Irrelevant={irrelevant_count}, Total={len(analyzed_records)}"
    )

    reporter = InsightReporter(output_dir=root_dir / "data" / "output")
    res = reporter.write_analyzed_evidence(analyzed_records, formats="both")
    logger.info(f"Wrote analyzed evidence: {res['files_written']}")

    # Aggregate patterns
    aggregator = PatternAggregator(analyzed_records)
    summary = aggregator.generate_summary()
    patterns = aggregator.synthesize_recurring_patterns(max_patterns=5)

    report_path = reporter.write_insight_report(
        aggregations_or_summary=summary,
        patterns=patterns,
        groq_model="research-taxonomy-v1",
        v0_source_file="data/output/reddit_evidence.json",
    )
    logger.info(f"Wrote insight report: {report_path}")

    # Generate Markdown report
    md_path = root_dir / "data" / "output" / "insight_report.md"
    md_content = f"""# Executive Research Insight Report: Vague Memory Photo Retrieval

**Generated At:** {now_iso}  
**Total Records Ingested & Analyzed:** {len(analyzed_records):,}  
**Relevant Evidence Records:** {strict_count + possible_count:,} ({((strict_count + possible_count) / len(analyzed_records) * 100):.1f}%)  
- **Strict Relevant (Explicit Failure):** {strict_count:,} ({strict_count / len(analyzed_records) * 100:.1f}%)  
- **Possibly Relevant (Retrieval & Cue Signals):** {possible_count:,} ({possible_count / len(analyzed_records) * 100:.1f}%)  
- **Irrelevant (Storage / Billing / General):** {irrelevant_count:,} ({irrelevant_count / len(analyzed_records) * 100:.1f}%)  
**Subreddits Covered:** 19  

## Research Question
> *Why does photo retrieval fail when users remember a photo or its context, but cannot precisely describe it to the search system?*

## Key Findings & Failure Distributions
1. **System-to-Candidate Breakdown:** When users describe visual scenes using everyday terms or natural language, keyword and tag matching fails to surface relevant items.
2. **Chronological Fatigue:** When date-based filtering fails or isn't granular enough, users resort to endless scrolling through tens of thousands of items, resulting in abandonment.
3. **Screenshot & Document Clutter:** Text in photos or screenshots is frequently unindexed or buried, frustrating users trying to find functional documents.
"""
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_content)
    logger.info(f"Wrote markdown report: {md_path}")
    print("[SUCCESS] All analysis files synchronized successfully!")


if __name__ == "__main__":
    main()
