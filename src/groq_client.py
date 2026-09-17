"""Groq API client wrapper for Reddit Research Data-Retrieval System.

V0: Initialises the client and validates the API key.
V1: Will expose methods for post analysis, classification, and
    pattern extraction.
"""

from __future__ import annotations

import logging
from typing import Any

from groq import Groq

logger = logging.getLogger(__name__)


class GroqClient:
    """Wrapper around the Groq inference API using the official SDK.

    V0: Initialises the client and validates the API key.
    V1: Will expose methods for post analysis, classification, and
        pattern extraction.
    """

    def __init__(self, api_key: str, model: str = "llama-3.3-70b-versatile"):
        """
        Args:
            api_key: Groq API key (from GROQ_API_KEY env var).
            model: Model identifier (e.g. llama-3.3-70b-versatile,
                   mixtral-8x7b-32768, gemma2-9b-it).
        """
        self.model = model
        self.client = Groq(api_key=api_key)
        logger.info(f"GroqClient initialised (model={model})")

    def health_check(self) -> bool:
        """Verify the API key is valid by listing available models.

        Returns:
            True if the key is valid, False otherwise.
        """
        try:
            models = self.client.models.list()
            model_ids = [m.id for m in models.data] if hasattr(models, "data") else []
            logger.info(f"Groq health check passed. {len(model_ids)} models available.")
            return True
        except Exception as e:
            logger.warning(f"Groq health check failed: {e}")
            return False

    # --- V1 methods (stubs) ---

    def analyze_post(self, post: dict[str, Any]) -> dict[str, Any]:
        """V1: Analyze a single post for memory patterns. Not implemented in V0."""
        raise NotImplementedError("Groq analysis is a V1 feature.")

    def classify_memory_type(self, post: dict[str, Any]) -> str:
        """V1: Classify what type of memory the user is searching for. Not implemented in V0."""
        raise NotImplementedError("Groq classification is a V1 feature.")

    def extract_search_behavior(self, post: dict[str, Any]) -> dict[str, Any]:
        """V1: Extract search-behavior signals from a post. Not implemented in V0."""
        raise NotImplementedError("Groq behavior extraction is a V1 feature.")
