"""Unit tests for src/config_loader.py."""

import os
import pytest
import warnings
from pathlib import Path

from src.config_loader import (
    ConfigError,
    load_config,
    AppConfig,
    RedditConfig,
    SearchConfig,
)


@pytest.fixture
def sample_yaml_content():
    return """
reddit:
  client_id: "test_id"
  client_secret: "test_secret"
  user_agent: "test-agent/0.1"

search:
  subreddits:
    - "googlephotos"
  queries:
    - "can't find old photo"
  sort: "relevance"
  time_filter: "all"
  limit_per_query: 10

pipeline:
  deduplicate_by: "id"
  output_format: "json"
  output_dir: "data/output"
  request_delay_seconds: 1.5

groq:
  api_key: "gsk_test123"
  model: "llama-3.3-70b-versatile"
  enabled: false

logging:
  level: "DEBUG"
  log_file: "logs/test.log"
"""


def test_load_valid_config_praw(tmp_path: Path, sample_yaml_content: str):
    cfg_file = tmp_path / "queries.yaml"
    cfg_file.write_text(sample_yaml_content, encoding="utf-8")

    config = load_config(cfg_file)
    assert isinstance(config, AppConfig)
    assert config.reddit.mode == "praw"
    assert config.reddit.client_id == "test_id"
    assert config.reddit.client_secret == "test_secret"
    assert config.reddit.user_agent == "test-agent/0.1"
    assert config.search.queries == ["can't find old photo"]
    assert config.search.subreddits == ["googlephotos"]
    assert config.search.limit_per_query == 10
    assert config.pipeline.output_format == "json"
    assert config.groq.api_key == "gsk_test123"
    assert config.groq.model == "llama-3.3-70b-versatile"


def test_load_valid_config_keyless(tmp_path: Path):
    yaml_text = """
reddit:
  client_id: ""
  client_secret: ""
  user_agent: "test-agent/0.1"

search:
  queries:
    - "can't find old photo"
"""
    cfg_file = tmp_path / "queries.yaml"
    cfg_file.write_text(yaml_text, encoding="utf-8")

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        config = load_config(cfg_file)

    assert config.reddit.mode == "keyless_rss"
    assert config.reddit.client_id is None
    assert config.reddit.client_secret is None
    assert config.reddit.user_agent == "test-agent/0.1"


def test_empty_queries_raises(tmp_path: Path):
    yaml_text = """
reddit:
  user_agent: "test-agent/0.1"
search:
  queries: []
"""
    cfg_file = tmp_path / "queries.yaml"
    cfg_file.write_text(yaml_text, encoding="utf-8")

    with pytest.raises(ConfigError, match="search.queries"):
        load_config(cfg_file)


def test_missing_user_agent_raises(tmp_path: Path):
    yaml_text = """
reddit:
  user_agent: ""
search:
  queries:
    - "lost photo"
"""
    cfg_file = tmp_path / "queries.yaml"
    cfg_file.write_text(yaml_text, encoding="utf-8")

    with pytest.raises(ConfigError, match="user_agent"):
        load_config(cfg_file)


def test_env_var_substitution(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("TEST_UA", "my-env-agent/1.0")
    monkeypatch.setenv("TEST_GROQ_KEY", "gsk_env_secret")

    yaml_text = """
reddit:
  user_agent: "${TEST_UA}"
search:
  queries:
    - "find photo"
groq:
  api_key: "${TEST_GROQ_KEY}"
"""
    cfg_file = tmp_path / "queries.yaml"
    cfg_file.write_text(yaml_text, encoding="utf-8")

    config = load_config(cfg_file)
    assert config.reddit.user_agent == "my-env-agent/1.0"
    assert config.groq.api_key == "gsk_env_secret"


def test_default_values(tmp_path: Path):
    yaml_text = """
reddit:
  user_agent: "agent/1.0"
search:
  queries:
    - "test query"
"""
    cfg_file = tmp_path / "queries.yaml"
    cfg_file.write_text(yaml_text, encoding="utf-8")

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        config = load_config(cfg_file)

    assert config.search.subreddits == []
    assert config.search.sort == "relevance"
    assert config.search.time_filter == "all"
    assert config.search.limit_per_query == 25
    assert config.pipeline.output_format == "json"
    assert config.pipeline.output_dir == "data/output"
    assert config.pipeline.request_delay_seconds == 2.0
    assert config.logging.level == "INFO"


def test_malformed_yaml_raises(tmp_path: Path):
    cfg_file = tmp_path / "queries.yaml"
    cfg_file.write_text("reddit: [broken yaml: invalid:", encoding="utf-8")

    with pytest.raises(ConfigError, match="Malformed YAML"):
        load_config(cfg_file)


def test_missing_groq_key_warns(tmp_path: Path):
    yaml_text = """
reddit:
  user_agent: "agent/1.0"
search:
  queries:
    - "query"
groq:
  api_key: ""
"""
    cfg_file = tmp_path / "queries.yaml"
    cfg_file.write_text(yaml_text, encoding="utf-8")

    with pytest.warns(UserWarning, match="GROQ_API_KEY"):
        config = load_config(cfg_file)

    assert config.groq.api_key is None


def test_invalid_output_format_raises(tmp_path: Path):
    yaml_text = """
reddit:
  user_agent: "agent/1.0"
search:
  queries:
    - "query"
pipeline:
  output_format: "xml"
"""
    cfg_file = tmp_path / "queries.yaml"
    cfg_file.write_text(yaml_text, encoding="utf-8")

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        with pytest.raises(ConfigError, match="pipeline.output_format"):
            load_config(cfg_file)


def test_file_not_found_raises():
    with pytest.raises(ConfigError, match="not found"):
        load_config("non_existent_config.yaml")
