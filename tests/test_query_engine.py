"""Unit tests for src/query_engine.py."""

import pytest
from src.config_loader import AppConfig, SearchConfig, RedditConfig, PipelineConfig, GroqConfig, LoggingConfig
from src.query_engine import QueryEngine


def _make_config(queries: list[str], subreddits: list[str]) -> AppConfig:
    return AppConfig(
        reddit=RedditConfig(
            client_id="test_id",
            client_secret="test_secret",
            user_agent="test_agent",
            mode="keyless",
        ),
        search=SearchConfig(
            queries=queries,
            subreddits=subreddits,
            sort="relevance",
            time_filter="all",
            limit_per_query=10,
        ),
        pipeline=PipelineConfig(),
        groq=GroqConfig(),
        logging=LoggingConfig(),
    )


def test_query_engine_cartesian_product():
    """Generates queries × subreddits task tuples."""
    config = _make_config(
        queries=["query 1", "query 2"],
        subreddits=["subA", "subB", "subC"],
    )
    engine = QueryEngine(config)
    tasks = engine.generate_tasks()

    assert len(tasks) == 6
    assert tasks[0][0] == "query 1"
    assert tasks[0][1] == "subA"
    assert tasks[0][2]["limit"] == 10
    assert tasks[0][2]["sort"] == "relevance"
    assert tasks[0][2]["time_filter"] == "all"
    assert tasks[5][0] == "query 2"
    assert tasks[5][1] == "subC"


def test_query_engine_global_search_when_no_subreddits():
    """When subreddits list is empty, generates tasks with None subreddit."""
    config = _make_config(
        queries=["global query 1", "global query 2"],
        subreddits=[],
    )
    engine = QueryEngine(config)
    tasks = engine.generate_tasks()

    assert len(tasks) == 2
    assert tasks[0] == ("global query 1", None, {"sort": "relevance", "time_filter": "all", "limit": 10})
    assert tasks[1] == ("global query 2", None, {"sort": "relevance", "time_filter": "all", "limit": 10})
