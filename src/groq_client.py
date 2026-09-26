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

    def __init__(
        self,
        api_key: str,
        model: str = "llama-3.3-70b-versatile",
        temperature: float = 0.1,
        max_retries: int = 3,
        timeout: float = 30.0,
    ):
        """
        Args:
            api_key: Groq API key (from GROQ_API_KEY env var).
            model: Model identifier (e.g. llama-3.3-70b-versatile,
                   mixtral-8x7b-32768, gemma2-9b-it).
            temperature: Default sampling temperature.
            max_retries: Default retry limit on 429/5xx errors.
            timeout: Default request timeout in seconds.
        """
        self.model = model
        self.temperature = temperature
        self.max_retries = max_retries
        self.timeout = timeout
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

    def complete_chat(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float = 0.1,
        json_mode: bool = True,
        max_retries: int = 3,
        timeout: float = 30.0,
    ) -> str:
        """Send chat completion request to Groq with retry and exponential backoff.

        Args:
            messages: List of message dictionaries with 'role' and 'content'.
            model: Model identifier override (defaults to self.model).
            temperature: Sampling temperature (default: 0.1).
            json_mode: If True, requests JSON object response format.
            max_retries: Maximum number of retry attempts for 429 / 5xx errors.
            timeout: Request timeout in seconds.

        Returns:
            Raw response text from the model.

        Raises:
            Exception: If max retries are exceeded or fatal error occurs.
        """
        import time
        from groq import (
            RateLimitError,
            APITimeoutError,
            APIConnectionError,
            InternalServerError,
            APIStatusError,
        )

        effective_model = model or self.model
        kwargs: dict[str, Any] = {
            "model": effective_model,
            "messages": messages,
            "temperature": temperature,
            "timeout": timeout,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        last_error: Exception | None = None

        for attempt in range(max_retries + 1):
            try:
                response = self.client.chat.completions.create(**kwargs)
                content = response.choices[0].message.content or ""
                return content
            except (RateLimitError, APITimeoutError, APIConnectionError, InternalServerError) as e:
                last_error = e
                if attempt >= max_retries:
                    logger.error(f"Groq API call failed after {max_retries} retries: {e}")
                    raise
                backoff = 2 ** attempt
                logger.warning(f"Groq transient error ({type(e).__name__}). Retrying in {backoff}s... (attempt {attempt + 1}/{max_retries})")
                time.sleep(backoff)
            except APIStatusError as e:
                last_error = e
                # Check status code for rate limits or server errors
                if hasattr(e, "status_code") and e.status_code in (429, 500, 502, 503, 504):
                    if attempt >= max_retries:
                        logger.error(f"Groq API status error {e.status_code} after {max_retries} retries: {e}")
                        raise
                    backoff = 2 ** attempt
                    logger.warning(f"Groq status {e.status_code} error. Retrying in {backoff}s... (attempt {attempt + 1}/{max_retries})")
                    time.sleep(backoff)
                elif hasattr(e, "status_code") and e.status_code == 404:
                    # Model not found or account lacks access — attempt fallback to available chat model
                    try:
                        avail = [m.id for m in self.client.models.list().data]
                        candidates = [
                            m for m in avail
                            if not any(x in m.lower() for x in ("whisper", "guard", "orpheus", "safeguard"))
                        ]
                        if candidates and candidates[0] != kwargs["model"]:
                            fallback = candidates[0]
                            logger.warning(
                                f"Groq model '{kwargs['model']}' not found on account. "
                                f"Auto-falling back to available model '{fallback}'."
                            )
                            self.model = fallback
                            kwargs["model"] = fallback
                            continue
                    except Exception as fallback_err:
                        logger.warning(f"Model fallback discovery failed: {fallback_err}")
                    logger.error(f"Groq non-retryable API status error: {e}")
                    raise
                else:
                    logger.error(f"Groq non-retryable API status error: {e}")
                    raise
            except Exception as e:
                last_error = e
                err_str = str(e).lower()
                if ("429" in err_str or "rate limit" in err_str or "timeout" in err_str) and attempt < max_retries:
                    backoff = 2 ** attempt
                    logger.warning(f"Groq rate limit/timeout caught. Retrying in {backoff}s... (attempt {attempt + 1}/{max_retries})")
                    time.sleep(backoff)
                else:
                    logger.error(f"Groq fatal/unhandled error: {e}")
                    raise

        if last_error:
            raise last_error
        raise RuntimeError("Groq completion failed with unknown state.")

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

