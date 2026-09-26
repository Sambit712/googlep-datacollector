"""Query Engine for Reddit Research Evidence-Collection System.

Generates search task tuples from configuration by computing the
Cartesian product of queries × subreddits, tagging each task with
its query category (product_specific vs behavior_specific) and
subreddit tier (primary vs discovery).
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

    def generate_tasks(
        self,
        limit_override: int | None = None,
    ) -> list[tuple[str, str | None, dict[str, Any]]]:
        """Generate Cartesian product of queries × subreddits with categorization metadata.

        If no subreddits specified, yield (query, None, params) for global search.

        Args:
            limit_override: Optional override for max_results_per_query (e.g. from CLI --limit).

        Returns:
            List of (query_string, subreddit_name, search_params) tuples.
        """
        queries = self.config.search.queries
        subreddits = self.config.search.subreddits

        limit = limit_override if limit_override is not None else self.config.search.limit_per_query

        tasks: list[tuple[str, str | None, dict[str, Any]]] = []

        if subreddits:
            for query in queries:
                q_cat = self.config.search.query_to_category.get(query, "general")
                for subreddit in subreddits:
                    sub_tier = self.config.search.subreddit_to_tier.get(subreddit, "primary")
                    params = {
                        "sort": self.config.search.sort,
                        "time_filter": self.config.search.time_filter,
                        "limit": limit,
                        "query_category": q_cat,
                        "subreddit_tier": sub_tier,
                    }
                    tasks.append((query, subreddit, params))
        else:
            for query in queries:
                q_cat = self.config.search.query_to_category.get(query, "general")
                params = {
                    "sort": self.config.search.sort,
                    "time_filter": self.config.search.time_filter,
                    "limit": limit,
                    "query_category": q_cat,
                    "subreddit_tier": "global",
                }
                tasks.append((query, None, params))

        logger.info(
            f"QueryEngine generated {len(tasks)} search tasks "
            f"({len(queries)} queries × {len(subreddits) or 1} subreddits)"
        )
        return tasks
