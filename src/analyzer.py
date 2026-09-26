"""V1 AI-Powered Multi-Task Research Analysis Engine.

Orchestrates prompt assembly, sends structured extraction requests to Groq (LLM),
validates classifications against the configurable taxonomy (config/taxonomy.yaml),
and produces AnalyzedEvidenceRecord instances preserving complete V0 traceability.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
import re
from typing import Any, Callable

from src.config_loader import TaxonomyConfig
from src.groq_client import GroqClient
from src.models import EvidenceRecord, AnalyzedEvidenceRecord

logger = logging.getLogger(__name__)

# Pattern to strip markdown json code blocks
_CODE_BLOCK_PATTERN = re.compile(r"```(?:json)?\s*([\s\S]*?)\s*```", re.IGNORECASE)


class AIAnalyzer:
    """Multi-task research analyzer powered by Groq LLM inference and configurable taxonomy."""

    def __init__(self, groq_client: GroqClient, taxonomy: TaxonomyConfig):
        """Initialize the analyzer with a Groq client and research taxonomy.

        Args:
            groq_client: Configured GroqClient instance.
            taxonomy: Loaded TaxonomyConfig instance.
        """
        self.groq_client = groq_client
        self.taxonomy = taxonomy

    def build_prompt(self, evidence: EvidenceRecord) -> list[dict[str, str]]:
        """Construct the multi-task system and user prompts injecting taxonomy rubrics.

        Args:
            evidence: V0 EvidenceRecord to analyze.

        Returns:
            List of message dicts formatted for the Groq Chat Completion API.
        """
        # Format taxonomy definitions for system prompt
        cues_desc = "\n".join(f"  - '{c.id}': {c.description}" for c in self.taxonomy.memory_cues)
        failures_desc = "\n".join(f"  - '{c.id}': {c.description}" for c in self.taxonomy.retrieval_failure_points)
        workarounds_desc = "\n".join(f"  - '{c.id}': {c.description}" for c in self.taxonomy.workaround_types)
        media_desc = ", ".join(f"'{m}'" for m in self.taxonomy.target_media_types)
        friction_desc = ", ".join(f"'{f}'" for f in self.taxonomy.friction_types)
        relevance_desc = "\n".join(f"  * {r}" for r in self.taxonomy.relevance_criteria)

        system_prompt = f"""You are a senior qualitative UX researcher studying how people remember visual memories and why photo retrieval breaks down in photo libraries (e.g. Google Photos, Apple Photos, gallery apps).

Analyze the user's conversation strictly against the provided Research Taxonomy.
Do not hallucinate details not directly stated or clearly implied by the evidence.

### RESEARCH TAXONOMY DEFINITIONS

1. Relevance Criteria:
{relevance_desc}

2. Memory Cues (what partial clues the user remembers):
{cues_desc}

3. Retrieval Failure Points (where photo retrieval broke down):
{failures_desc}

4. Target Media Types (pick one primary):
  [{media_desc}]

5. Workaround Types (what user did when search failed):
{workarounds_desc}

6. Friction Types (experienced pain points):
  [{friction_desc}]

### OUTPUT REQUIREMENTS
You MUST respond with a valid JSON object matching the following structure:
{{
  "is_relevant": <true|false>,
  "relevance_confidence": <float between 0.0 and 1.0>,
  "relevance_reasoning": "<1-2 sentence explanation of why this post is or is not relevant to vague-memory retrieval>",
  "target_media": "<one of target media types above>",
  "memory_cues_present": ["<list of matching memory cue ids>"],
  "memory_cue_details": {{
    "<memory_cue_id>": "<brief excerpt or clue described by user>"
  }},
  "retrieval_failure_point": "<one of failure point ids above>",
  "failure_evidence": "<exact quote or brief summary of where search failed>",
  "workarounds_used": ["<list of matching workaround ids>"],
  "friction_experienced": ["<list of matching friction ids>"],
  "desired_outcome": "<what the user was ultimately attempting to achieve>"
}}
"""

        # Format user prompt with conversation text and context
        text_content = evidence.cleaned_text or evidence.raw_text or evidence.title
        comments_preview = ""
        if evidence.top_comments:
            comments_joined = "\n".join(f"- {c}" for c in evidence.top_comments[:3])
            comments_preview = f"\n\nContextual Comments:\n{comments_joined}"

        user_prompt = f"""Analyze the following Reddit evidence record:

Title: {evidence.title}
Subreddit: r/{evidence.subreddit}
Conversation Text:
{text_content}{comments_preview}

Produce the structured JSON analysis adhering strictly to the taxonomy categories."""

        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

    def parse_analysis_response(self, raw_response: str) -> dict[str, Any]:
        """Clean markdown formatting and parse JSON response.

        Args:
            raw_response: Raw string output from LLM.

        Returns:
            Parsed dictionary.

        Raises:
            ValueError: If JSON cannot be extracted or parsed.
        """
        if not raw_response or not raw_response.strip():
            raise ValueError("Empty response received from LLM.")

        cleaned = raw_response.strip()

        # Strip code block wrappers if present (e.g. ```json ... ```)
        match = _CODE_BLOCK_PATTERN.search(cleaned)
        if match:
            cleaned = match.group(1).strip()

        # Try direct JSON parsing
        try:
            parsed = json.loads(cleaned)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

        # Fallback: regex search for the outermost JSON object
        json_match = re.search(r"\{[\s\S]*\}", cleaned)
        if json_match:
            try:
                parsed = json.loads(json_match.group(0))
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError as e:
                raise ValueError(f"Extracted JSON substring could not be decoded: {e}") from e

        raise ValueError(f"Failed to parse valid JSON from response: {raw_response[:100]}...")

    def validate_and_normalize_analysis(self, raw: dict[str, Any]) -> dict[str, Any]:
        """Validate and normalize raw parsed analysis against taxonomy rules.

        Args:
            raw: Dictionary extracted from LLM JSON response.

        Returns:
            Normalized dictionary conforming to AnalyzedEvidenceRecord schema.
        """
        # Relevance
        is_relevant = bool(raw.get("is_relevant", False))
        try:
            confidence = float(raw.get("relevance_confidence", 0.0))
            confidence = max(0.0, min(1.0, confidence))
        except (ValueError, TypeError):
            confidence = 0.5 if is_relevant else 0.0

        reasoning = str(raw.get("relevance_reasoning", "")).strip()

        # Target Media
        valid_media = set(self.taxonomy.target_media_types)
        media_raw = str(raw.get("target_media", "")).strip()
        target_media = media_raw if media_raw in valid_media else "personal_photo"

        # Memory Cues
        valid_cue_ids = set(self.taxonomy.get_memory_cue_ids())
        raw_cues = raw.get("memory_cues_present", [])
        if not isinstance(raw_cues, list):
            raw_cues = []
        memory_cues_present = [str(c).strip() for c in raw_cues if str(c).strip() in valid_cue_ids]

        # Memory Cue Details
        raw_details = raw.get("memory_cue_details", {})
        memory_cue_details: dict[str, str] = {}
        if isinstance(raw_details, dict):
            for k, v in raw_details.items():
                k_clean = str(k).strip()
                if k_clean in valid_cue_ids and v:
                    memory_cue_details[k_clean] = str(v).strip()

        # Ensure present list matches keys in details if cues were identified
        for k in memory_cue_details:
            if k not in memory_cues_present:
                memory_cues_present.append(k)

        # Retrieval Failure Point
        valid_failure_ids = set(self.taxonomy.get_failure_point_ids())
        failure_raw = str(raw.get("retrieval_failure_point", "")).strip()
        retrieval_failure_point = failure_raw if failure_raw in valid_failure_ids else (
            "vocabulary_mismatch" if is_relevant else ""
        )

        failure_evidence = str(raw.get("failure_evidence", "")).strip()

        # Workarounds
        valid_workaround_ids = set(self.taxonomy.get_workaround_ids())
        raw_workarounds = raw.get("workarounds_used", [])
        if not isinstance(raw_workarounds, list):
            raw_workarounds = []
        workarounds_used = [str(w).strip() for w in raw_workarounds if str(w).strip() in valid_workaround_ids]

        # Friction
        valid_friction = set(self.taxonomy.friction_types)
        raw_friction = raw.get("friction_experienced", [])
        if not isinstance(raw_friction, list):
            raw_friction = []
        friction_experienced = [str(f).strip() for f in raw_friction if str(f).strip() in valid_friction]

        desired_outcome = str(raw.get("desired_outcome", "")).strip()

        return {
            "is_relevant": is_relevant,
            "relevance_confidence": confidence,
            "relevance_reasoning": reasoning,
            "target_media": target_media,
            "memory_cues_present": memory_cues_present,
            "memory_cue_details": memory_cue_details,
            "retrieval_failure_point": retrieval_failure_point,
            "failure_evidence": failure_evidence,
            "workarounds_used": workarounds_used,
            "friction_experienced": friction_experienced,
            "desired_outcome": desired_outcome,
        }

    def analyze_record(self, evidence: EvidenceRecord) -> AnalyzedEvidenceRecord:
        """Execute full multi-task analysis on a single V0 EvidenceRecord.

        Args:
            evidence: V0 EvidenceRecord to analyze.

        Returns:
            AnalyzedEvidenceRecord retaining the exact V0 record_id.
        """
        now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        messages = self.build_prompt(evidence)
        model_name = self.taxonomy.groq_analysis.model or self.groq_client.model

        try:
            raw_response = self.groq_client.complete_chat(
                messages=messages,
                model=model_name,
                temperature=self.taxonomy.groq_analysis.temperature,
                json_mode=True,
                max_retries=self.taxonomy.groq_analysis.max_retries,
                timeout=float(self.taxonomy.groq_analysis.timeout_seconds),
            )
            parsed_json = self.parse_analysis_response(raw_response)
            normalized_analysis = self.validate_and_normalize_analysis(parsed_json)
        except Exception as e:
            logger.warning(
                f"Analysis for record {evidence.record_id} failed or returned invalid response: {e}. "
                "Constructing fallback non-relevant record."
            )
            normalized_analysis = {
                "is_relevant": False,
                "relevance_confidence": 0.0,
                "relevance_reasoning": f"Analysis failed or could not be decoded: {e}",
                "target_media": "personal_photo",
                "memory_cues_present": [],
                "memory_cue_details": {},
                "retrieval_failure_point": "",
                "failure_evidence": "",
                "workarounds_used": [],
                "friction_experienced": [],
                "desired_outcome": "",
            }

        return AnalyzedEvidenceRecord.from_evidence_record(
            evidence=evidence,
            analysis=normalized_analysis,
            model_used=model_name,
            analyzed_at=now_iso,
        )

    def analyze_batch(
        self,
        records: list[EvidenceRecord],
        progress_callback: Callable[[int, int, AnalyzedEvidenceRecord], None] | None = None,
        on_progress: Any | None = None,
    ) -> list[AnalyzedEvidenceRecord]:
        """Analyze a batch of evidence records sequentially.

        Args:
            records: List of V0 EvidenceRecords to analyze.
            progress_callback: Optional callback invoked as (current_index, total, analyzed_record).
            on_progress: Optional callback invoked as (current_index, total) or progress_callback alias.

        Returns:
            List of AnalyzedEvidenceRecord instances.
        """
        callback = progress_callback or on_progress
        analyzed_records: list[AnalyzedEvidenceRecord] = []
        total = len(records)
        logger.info(f"Starting V1 AI analysis on {total} evidence records...")

        for idx, evidence in enumerate(records):
            analyzed = self.analyze_record(evidence)
            analyzed_records.append(analyzed)

            if callback:
                try:
                    callback(idx + 1, total, analyzed)
                except TypeError:
                    try:
                        callback(idx + 1, total)
                    except Exception:
                        pass

            if (idx + 1) % 10 == 0 or (idx + 1) == total:
                logger.info(f"Analyzed [{idx + 1}/{total}] records (Relevant: {analyzed.is_relevant})")

        logger.info(f"Completed V1 AI analysis on {total} records.")
        return analyzed_records
