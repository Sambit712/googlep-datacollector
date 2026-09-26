"""Configuration loader for the Reddit Research Evidence-Collection System.

Loads YAML configuration, performs environment-variable substitution,
validates required fields, detects Reddit access mode (keyless_rss vs praw),
parses query categories and subreddit tiers, and returns an immutable AppConfig.
"""

from __future__ import annotations

import os
import re
import logging
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Pattern for ${VAR_NAME} environment variable placeholders
_ENV_VAR_PATTERN = re.compile(r"\$\{([A-Za-z0-9_]+)\}")


class ConfigError(Exception):
    """Raised when configuration is missing, malformed, or fails validation."""
    pass


@dataclass(frozen=True)
class RedditConfig:
    client_id: str | None
    client_secret: str | None
    user_agent: str
    mode: str = "keyless_rss"  # "keyless_rss" or "praw"


@dataclass(frozen=True)
class SearchConfig:
    queries: list[str]
    subreddits: list[str] = field(default_factory=list)
    sort: str = "relevance"
    time_filter: str = "all"
    limit_per_query: int = 25
    query_categories: dict[str, list[str]] = field(default_factory=dict)
    query_to_category: dict[str, str] = field(default_factory=dict)
    subreddit_tiers: dict[str, list[str]] = field(default_factory=dict)
    subreddit_to_tier: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class PipelineConfig:
    deduplicate_by: str = "id"
    output_format: str = "json"
    output_dir: str = "data/output"
    request_delay_seconds: float = 2.0
    max_comments_per_post: int = 3


@dataclass(frozen=True)
class PrivacyConfig:
    anonymize_authors: bool = False


@dataclass(frozen=True)
class GroqConfig:
    api_key: str | None = None
    model: str = "llama-3.3-70b-versatile"
    enabled: bool = False


@dataclass(frozen=True)
class LoggingConfig:
    level: str = "INFO"
    log_file: str = "logs/run.log"


@dataclass(frozen=True)
class AppConfig:
    reddit: RedditConfig
    search: SearchConfig
    pipeline: PipelineConfig
    groq: GroqConfig
    logging: LoggingConfig
    privacy: PrivacyConfig = field(default_factory=PrivacyConfig)

    @property
    def queries(self) -> dict[str, list[str]]:
        return self.search.query_categories

    @property
    def subreddits(self) -> dict[str, list[str]]:
        return self.search.subreddit_tiers


@dataclass(frozen=True)
class TaxonomyCategory:
    id: str
    description: str


@dataclass(frozen=True)
class GroqAnalysisConfig:
    model: str = "llama-3.3-70b-versatile"
    temperature: float = 0.1
    max_retries: int = 3
    timeout_seconds: int = 30
    batch_size: int = 1


DEFAULT_FAILURE_STAGES = [
    TaxonomyCategory("memory_to_query", "Memory → Query: User remembers photo details but cannot convert memory into searchable terms"),
    TaxonomyCategory("query_to_system", "Query → System: User provides reasonable natural description but system misinterprets intent"),
    TaxonomyCategory("system_to_candidate", "System → Candidate: System returns too many, too few, or completely unrelated candidates"),
    TaxonomyCategory("candidate_to_recognition", "Candidate → Recognition: User struggles to distinguish the target item among candidates in gallery"),
    TaxonomyCategory("search_refinement", "Search Refinement: Initial search fails and user lacks cues/controls to iteratively steer search"),
]

DEFAULT_RELEVANCE_CLASSES = [
    TaxonomyCategory("relevant", "Direct vague-memory retrieval failure or friction with recalled episodic fragments"),
    TaxonomyCategory("possibly_relevant", "Retrieval issue implied, ambiguous, or combined with broader album organization complaints"),
    TaxonomyCategory("irrelevant", "App crashes, sync/backup errors, subscription/billing, or non-retrieval complaints"),
]


@dataclass(frozen=True)
class TaxonomyConfig:
    version: str
    description: str
    relevance_criteria: list[str]
    memory_cues: list[TaxonomyCategory]
    retrieval_failure_points: list[TaxonomyCategory]
    target_media_types: list[str]
    workaround_types: list[TaxonomyCategory]
    friction_types: list[str]
    groq_analysis: GroqAnalysisConfig = field(default_factory=GroqAnalysisConfig)
    retrieval_failure_stages: list[TaxonomyCategory] = field(default_factory=list)
    relevance_classes: list[TaxonomyCategory] = field(default_factory=list)

    def get_memory_cue_ids(self) -> list[str]:
        return [c.id for c in self.memory_cues]

    def get_failure_point_ids(self) -> list[str]:
        return [c.id for c in self.retrieval_failure_points]

    def get_workaround_ids(self) -> list[str]:
        return [c.id for c in self.workaround_types]

    def get_failure_stage_ids(self) -> list[str]:
        return [c.id for c in self.retrieval_failure_stages]

    def get_relevance_class_ids(self) -> list[str]:
        return [c.id for c in self.relevance_classes]

    def is_valid_memory_cue(self, cue_id: str) -> bool:
        return cue_id in self.get_memory_cue_ids()

    def is_valid_failure_point(self, failure_id: str) -> bool:
        return failure_id in self.get_failure_point_ids()

    def is_valid_failure_stage(self, stage_id: str) -> bool:
        return stage_id in self.get_failure_stage_ids()

    def is_valid_relevance_class(self, class_id: str) -> bool:
        return class_id in self.get_relevance_class_ids()

    def is_valid_target_media(self, media_type: str) -> bool:
        return media_type in self.target_media_types

    def is_valid_workaround(self, workaround_id: str) -> bool:
        return workaround_id in self.get_workaround_ids()

    def is_valid_friction(self, friction: str) -> bool:
        return friction in self.friction_types

    def get_cue_description(self, cue_id: str) -> str | None:
        for c in self.memory_cues:
            if c.id == cue_id:
                return c.description
        return None

    def get_failure_description(self, failure_id: str) -> str | None:
        for c in self.retrieval_failure_points:
            if c.id == failure_id:
                return c.description
        return None

    def get_failure_stage_description(self, stage_id: str) -> str | None:
        for c in self.retrieval_failure_stages:
            if c.id == stage_id:
                return c.description
        return None

    def get_workaround_description(self, workaround_id: str) -> str | None:
        for c in self.workaround_types:
            if c.id == workaround_id:
                return c.description
        return None



def _substitute_env_vars(raw_text: str) -> str:
    """Replace ${VAR_NAME} placeholders with values from os.environ."""
    def _repl(match: re.Match[str]) -> str:
        var_name = match.group(1)
        return os.environ.get(var_name, "")

    return _ENV_VAR_PATTERN.sub(_repl, raw_text)


def _is_placeholder_or_empty(val: Any) -> bool:
    """Check if value is None, empty string, or placeholder."""
    if val is None:
        return True
    s = str(val).strip()
    return not s or s.startswith("your_")


def load_config(config_path: str | Path = "config/queries.yaml") -> AppConfig:
    """Load, substitute env vars, validate, and return frozen AppConfig.

    Args:
        config_path: Path to YAML configuration file.

    Returns:
        AppConfig instance.

    Raises:
        ConfigError: If configuration is missing, unparseable, or invalid.
    """
    # 1. Load environment variables from .env
    load_dotenv()

    # 2. Check file existence
    path = Path(config_path)
    if not path.is_file():
        raise ConfigError(f"Configuration file not found: {path.resolve()}")

    # 3. Read and substitute environment variables
    try:
        raw_text = path.read_text(encoding="utf-8")
    except OSError as e:
        raise ConfigError(f"Failed to read configuration file {path}: {e}") from e

    substituted_text = _substitute_env_vars(raw_text)

    # 4. Parse YAML
    try:
        data = yaml.safe_load(substituted_text)
    except yaml.YAMLError as e:
        raise ConfigError(f"Malformed YAML in {path}: {e}") from e

    if not isinstance(data, dict):
        raise ConfigError(f"Configuration file {path} must contain a top-level dictionary/mapping.")

    # --- 1. Reddit Section ---
    reddit_raw = data.get("reddit")
    if not isinstance(reddit_raw, dict):
        raise ConfigError("Missing required 'reddit' section in configuration.")

    user_agent = str(reddit_raw.get("user_agent", "")).strip()
    if not user_agent or _is_placeholder_or_empty(user_agent):
        raise ConfigError("The 'reddit.user_agent' field is required and must not be empty.")

    raw_client_id = reddit_raw.get("client_id")
    raw_client_secret = reddit_raw.get("client_secret")

    # Detect mode: praw requires both client_id and client_secret without placeholder values
    has_keys = not _is_placeholder_or_empty(raw_client_id) and not _is_placeholder_or_empty(raw_client_secret)
    mode = "praw" if has_keys else "keyless_rss"

    reddit_cfg = RedditConfig(
        client_id=None if _is_placeholder_or_empty(raw_client_id) else str(raw_client_id).strip(),
        client_secret=None if _is_placeholder_or_empty(raw_client_secret) else str(raw_client_secret).strip(),
        user_agent=user_agent,
        mode=mode,
    )

    # --- 2. Search Section ---
    search_raw = data.get("search")
    if not isinstance(search_raw, dict):
        raise ConfigError("Missing required 'search' section in configuration.")

    queries_raw = search_raw.get("queries")
    cleaned_queries: list[str] = []
    query_categories: dict[str, list[str]] = {}
    query_to_category: dict[str, str] = {}

    if isinstance(queries_raw, dict):
        for cat_name, q_list in queries_raw.items():
            if isinstance(q_list, list):
                clean_list = [str(q).strip() for q in q_list if str(q).strip()]
                query_categories[cat_name] = clean_list
                for q in clean_list:
                    cleaned_queries.append(q)
                    query_to_category[q] = cat_name
    elif isinstance(queries_raw, list):
        cleaned_queries = [str(q).strip() for q in queries_raw if str(q).strip()]
        query_categories["general"] = cleaned_queries
        for q in cleaned_queries:
            query_to_category[q] = "general"
    else:
        raise ConfigError("The 'search.queries' field must be a non-empty list or dictionary of categories.")

    if not cleaned_queries:
        raise ConfigError("The 'search.queries' field must contain at least one non-empty query string.")

    subreddits_raw = search_raw.get("subreddits", [])
    subreddits: list[str] = []
    subreddit_tiers: dict[str, list[str]] = {}
    subreddit_to_tier: dict[str, str] = {}

    if isinstance(subreddits_raw, dict):
        for tier_name, s_list in subreddits_raw.items():
            if isinstance(s_list, list):
                clean_list = [str(s).strip() for s in s_list if str(s).strip()]
                subreddit_tiers[tier_name] = clean_list
                for s in clean_list:
                    subreddits.append(s)
                    subreddit_to_tier[s] = tier_name
    elif isinstance(subreddits_raw, list):
        subreddits = [str(s).strip() for s in subreddits_raw if str(s).strip()]
        subreddit_tiers["primary"] = subreddits
        for s in subreddits:
            subreddit_to_tier[s] = "primary"

    search_cfg = SearchConfig(
        queries=cleaned_queries,
        subreddits=subreddits,
        sort=str(search_raw.get("sort", "relevance")),
        time_filter=str(search_raw.get("time_filter", "all")),
        limit_per_query=int(search_raw.get("limit_per_query", 25)),
        query_categories=query_categories,
        query_to_category=query_to_category,
        subreddit_tiers=subreddit_tiers,
        subreddit_to_tier=subreddit_to_tier,
    )

    # --- 3. Pipeline Section ---
    pipeline_raw = data.get("pipeline", {})
    if not isinstance(pipeline_raw, dict):
        pipeline_raw = {}

    out_fmt = str(pipeline_raw.get("output_format", "json")).lower()
    if out_fmt not in ("json", "csv", "both"):
        raise ConfigError(f"Invalid 'pipeline.output_format': '{out_fmt}'. Must be 'json', 'csv', or 'both'.")

    pipeline_cfg = PipelineConfig(
        deduplicate_by=str(pipeline_raw.get("deduplicate_by", "id")),
        output_format=out_fmt,
        output_dir=str(pipeline_raw.get("output_dir", "data/output")),
        request_delay_seconds=float(pipeline_raw.get("request_delay_seconds", 2.0)),
        max_comments_per_post=int(pipeline_raw.get("max_comments_per_post", 3)),
    )

    # --- 4. Privacy Section ---
    privacy_raw = data.get("privacy", {})
    if not isinstance(privacy_raw, dict):
        privacy_raw = {}

    privacy_cfg = PrivacyConfig(
        anonymize_authors=bool(privacy_raw.get("anonymize_authors", False)),
    )

    # --- 5. Groq Section ---
    groq_raw = data.get("groq", {})
    if not isinstance(groq_raw, dict):
        groq_raw = {}

    raw_groq_key = groq_raw.get("api_key")
    groq_key = None if _is_placeholder_or_empty(raw_groq_key) else str(raw_groq_key).strip()

    if not groq_key:
        warnings.warn(
            "GROQ_API_KEY is not set or is empty. Groq client will be initialized in stub mode (required for V1).",
            UserWarning,
            stacklevel=2,
        )

    groq_cfg = GroqConfig(
        api_key=groq_key,
        model=str(groq_raw.get("model", "llama-3.3-70b-versatile")),
        enabled=bool(groq_raw.get("enabled", False)),
    )

    # --- 6. Logging Section ---
    logging_raw = data.get("logging", {})
    if not isinstance(logging_raw, dict):
        logging_raw = {}

    logging_cfg = LoggingConfig(
        level=str(logging_raw.get("level", "INFO")),
        log_file=str(logging_raw.get("log_file", "logs/run.log")),
    )

    return AppConfig(
        reddit=reddit_cfg,
        search=search_cfg,
        pipeline=pipeline_cfg,
        groq=groq_cfg,
        logging=logging_cfg,
        privacy=privacy_cfg,
    )


def load_taxonomy(taxonomy_path: str | Path = "config/taxonomy.yaml") -> TaxonomyConfig:
    """Load, validate, and return frozen TaxonomyConfig.

    Args:
        taxonomy_path: Path to taxonomy YAML configuration file.

    Returns:
        TaxonomyConfig instance.

    Raises:
        ConfigError: If configuration is missing, unparseable, or invalid.
    """
    path = Path(taxonomy_path)
    if not path.is_file():
        raise ConfigError(f"Taxonomy configuration file not found: {path.resolve()}")

    try:
        raw_text = path.read_text(encoding="utf-8")
    except OSError as e:
        raise ConfigError(f"Failed to read taxonomy file {path}: {e}") from e

    substituted_text = _substitute_env_vars(raw_text)

    try:
        data = yaml.safe_load(substituted_text)
    except yaml.YAMLError as e:
        raise ConfigError(f"Malformed YAML in taxonomy file {path}: {e}") from e

    if not isinstance(data, dict):
        raise ConfigError(f"Taxonomy configuration in {path} must contain a top-level dictionary/mapping.")

    version = str(data.get("version", "1.0")).strip()
    description = str(data.get("description", "")).strip()

    # 1. Relevance Criteria
    relevance_raw = data.get("relevance_criteria")
    if not isinstance(relevance_raw, list) or not relevance_raw:
        raise ConfigError("Missing or empty 'relevance_criteria' list in taxonomy configuration.")
    relevance_criteria = [str(r).strip() for r in relevance_raw if str(r).strip()]
    if not relevance_criteria:
        raise ConfigError("The 'relevance_criteria' list must contain at least one non-empty string.")

    # Helper for category sections
    def _parse_categories(raw_val: Any, section_name: str) -> list[TaxonomyCategory]:
        if isinstance(raw_val, dict) and "categories" in raw_val:
            raw_list = raw_val["categories"]
        elif isinstance(raw_val, list):
            raw_list = raw_val
        else:
            raise ConfigError(
                f"Missing or invalid '{section_name}' in taxonomy configuration. "
                "Must be a list or a mapping with a 'categories' list."
            )

        if not isinstance(raw_list, list) or not raw_list:
            raise ConfigError(f"The '{section_name}' section must contain at least one category.")

        categories: list[TaxonomyCategory] = []
        seen_ids: set[str] = set()

        for idx, item in enumerate(raw_list):
            if not isinstance(item, dict):
                raise ConfigError(f"Category #{idx + 1} in '{section_name}' must be a dictionary with 'id' and 'description'.")

            cat_id = str(item.get("id", "")).strip()
            desc = str(item.get("description", "")).strip()

            if not cat_id:
                raise ConfigError(f"Category #{idx + 1} in '{section_name}' is missing a valid 'id'.")

            if cat_id in seen_ids:
                raise ConfigError(f"Duplicate category id '{cat_id}' found in '{section_name}'.")

            seen_ids.add(cat_id)
            categories.append(TaxonomyCategory(id=cat_id, description=desc))

        return categories

    # 2. Memory Cues
    memory_cues = _parse_categories(data.get("memory_cues"), "memory_cues")

    # 3. Retrieval Failure Points
    failure_points = _parse_categories(data.get("retrieval_failure_points"), "retrieval_failure_points")

    # 4. Target Media Types
    media_raw = data.get("target_media_types")
    if not isinstance(media_raw, list) or not media_raw:
        raise ConfigError("Missing or empty 'target_media_types' in taxonomy configuration.")
    target_media_types = [str(m).strip() for m in media_raw if str(m).strip()]
    if not target_media_types:
        raise ConfigError("The 'target_media_types' list must contain at least one non-empty string.")

    # 5. Workaround Types
    workarounds = _parse_categories(data.get("workaround_types"), "workaround_types")

    # 6. Friction Types
    friction_raw = data.get("friction_types")
    if not isinstance(friction_raw, list) or not friction_raw:
        raise ConfigError("Missing or empty 'friction_types' in taxonomy configuration.")
    friction_types = [str(f).strip() for f in friction_raw if str(f).strip()]
    if not friction_types:
        raise ConfigError("The 'friction_types' list must contain at least one non-empty string.")

    # 7. Retrieval Failure Stages (Optional with defaults)
    if "retrieval_failure_stages" in data and data["retrieval_failure_stages"]:
        failure_stages = _parse_categories(data.get("retrieval_failure_stages"), "retrieval_failure_stages")
    else:
        failure_stages = list(DEFAULT_FAILURE_STAGES)

    # 8. Relevance Classes (Optional with defaults)
    if "relevance_classes" in data and data["relevance_classes"]:
        relevance_classes = _parse_categories(data.get("relevance_classes"), "relevance_classes")
    else:
        relevance_classes = list(DEFAULT_RELEVANCE_CLASSES)

    # 9. Groq Analysis Section
    groq_raw = data.get("groq_analysis", {})
    if not isinstance(groq_raw, dict):
        groq_raw = {}

    groq_analysis = GroqAnalysisConfig(
        model=str(groq_raw.get("model", "llama-3.3-70b-versatile")),
        temperature=float(groq_raw.get("temperature", 0.1)),
        max_retries=int(groq_raw.get("max_retries", 3)),
        timeout_seconds=int(groq_raw.get("timeout_seconds", 30)),
        batch_size=int(groq_raw.get("batch_size", 1)),
    )

    return TaxonomyConfig(
        version=version,
        description=description,
        relevance_criteria=relevance_criteria,
        memory_cues=memory_cues,
        retrieval_failure_points=failure_points,
        target_media_types=target_media_types,
        workaround_types=workarounds,
        friction_types=friction_types,
        groq_analysis=groq_analysis,
        retrieval_failure_stages=failure_stages,
        relevance_classes=relevance_classes,
    )

