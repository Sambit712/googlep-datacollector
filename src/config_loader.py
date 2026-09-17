"""Configuration loader for the Reddit Research Data-Retrieval System.

Loads YAML configuration, performs environment-variable substitution,
validates required fields, detects Reddit access mode (keyless_rss vs praw),
and returns an immutable AppConfig dataclass.
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


@dataclass(frozen=True)
class PipelineConfig:
    deduplicate_by: str = "id"
    output_format: str = "json"
    output_dir: str = "data/output"
    request_delay_seconds: float = 2.0


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

    Raises:
        ConfigError: If file not found, YAML is malformed, or required fields missing.
    """
    # Load .env into environment if present
    load_dotenv(override=False)

    path = Path(config_path)
    if not path.is_file():
        raise ConfigError(f"Configuration file not found: {path}")

    try:
        raw_text = path.read_text(encoding="utf-8")
    except Exception as e:
        raise ConfigError(f"Failed to read config file {path}: {e}") from e

    substituted_text = _substitute_env_vars(raw_text)

    try:
        data = yaml.safe_load(substituted_text)
    except yaml.YAMLError as e:
        raise ConfigError(f"Malformed YAML in {path}: {e}") from e

    if not isinstance(data, dict):
        raise ConfigError(f"Invalid configuration root in {path}: expected a YAML mapping/dictionary.")

    # --- 1. Reddit Section ---
    reddit_raw = data.get("reddit")
    if not isinstance(reddit_raw, dict):
        raise ConfigError("Missing required 'reddit' section in configuration.")

    raw_client_id = reddit_raw.get("client_id")
    raw_client_secret = reddit_raw.get("client_secret")
    user_agent = str(reddit_raw.get("user_agent", "")).strip()

    if _is_placeholder_or_empty(user_agent):
        raise ConfigError(
            "Missing or empty 'reddit.user_agent'. Reddit requires a descriptive User-Agent string."
        )

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

    queries = search_raw.get("queries")
    if not isinstance(queries, list) or len(queries) == 0:
        raise ConfigError("The 'search.queries' field must be a non-empty list of query strings.")

    cleaned_queries = [str(q).strip() for q in queries if str(q).strip()]
    if not cleaned_queries:
        raise ConfigError("The 'search.queries' list must contain at least one non-empty query string.")

    subreddits_raw = search_raw.get("subreddits", [])
    subreddits = [str(s).strip() for s in subreddits_raw if str(s).strip()] if isinstance(subreddits_raw, list) else []

    search_cfg = SearchConfig(
        queries=cleaned_queries,
        subreddits=subreddits,
        sort=str(search_raw.get("sort", "relevance")),
        time_filter=str(search_raw.get("time_filter", "all")),
        limit_per_query=int(search_raw.get("limit_per_query", 25)),
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
    )

    # --- 4. Groq Section ---
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

    # --- 5. Logging Section ---
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
    )
