"""Query Engine for Reddit Research Data-Retrieval System.

Generates search task tuples from configuration by computing the
Cartesian product of queries × subreddits.
"""

from __future__ import annotations

import logging
from typing import Any

from src.config_loader import AppConfig

logger = logging.getLogger(__name__)


class QueryEngine:
    """Generates search task tuples from configuration."""

    def __init__(self, config: AppConfig):
        """Store config for query generation.

        Args:
            config: The validated application configuration.
        """
        self.config = config

    def generate_tasks(self) -> list[tuple[str, str | None, dict[str, Any]]]:
        """Generate Cartesian product of queries × subreddits.

        If no subreddits specified, yield (query, None, params) for global search.

        Returns:
            List of (query_string, subreddit_name, search_params) tuples.
        """
        queries = self.config.search.queries
        subreddits = self.config.search.subreddits
        params = {
            "sort": self.config.search.sort,
            "time_filter": self.config.search.time_filter,
            "limit": self.config.search.limit_per_query,
        }

        tasks: list[tuple[str, str | None, dict[str, Any]]] = []

        if subreddits:
            for query in queries:
                for subreddit in subreddits:
                    tasks.append((query, subreddit, params.copy()))
        else:
            for query in queries:
                tasks.append((query, None, params.copy()))

        logger.info(
            f"QueryEngine generated {len(tasks)} search tasks "
            f"({len(queries)} queries × {len(subreddits) or 1} subreddits)"
        )
        return tasks
