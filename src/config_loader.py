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
