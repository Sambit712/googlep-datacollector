"""Unit tests for src/groq_client.py."""

from unittest.mock import MagicMock, patch
import pytest

from src.groq_client import GroqClient


@patch("src.groq_client.Groq")
def test_init_with_valid_key(mock_groq_cls):
    """Client initialises without error."""
    client = GroqClient(api_key="gsk_test123")
    mock_groq_cls.assert_called_once_with(api_key="gsk_test123")
    assert client.client is not None


@patch("src.groq_client.Groq")
def test_init_sets_model(mock_groq_cls):
    """self.model matches provided model."""
    client = GroqClient(api_key="gsk_test123", model="mixtral-8x7b-32768")
    assert client.model == "mixtral-8x7b-32768"

    client_default = GroqClient(api_key="gsk_test123")
    assert client_default.model == "llama-3.3-70b-versatile"


@patch("src.groq_client.Groq")
def test_v1_stubs_raise_not_implemented(mock_groq_cls):
    """analyze_post, classify_memory_type, extract_search_behavior raise NotImplementedError."""
    client = GroqClient(api_key="gsk_test123")

    with pytest.raises(NotImplementedError, match="V1 feature"):
        client.analyze_post({"title": "test"})

    with pytest.raises(NotImplementedError, match="V1 feature"):
        client.classify_memory_type({"title": "test"})

    with pytest.raises(NotImplementedError, match="V1 feature"):
        client.extract_search_behavior({"title": "test"})


@patch("src.groq_client.Groq")
def test_health_check_with_mock(mock_groq_cls):
    """Health check calls API and returns bool."""
    mock_instance = MagicMock()
    mock_groq_cls.return_value = mock_instance

    # Simulate successful models.list()
    mock_model = MagicMock()
    mock_model.id = "llama-3.3-70b-versatile"
    mock_models_response = MagicMock()
    mock_models_response.data = [mock_model]
    mock_instance.models.list.return_value = mock_models_response

    client = GroqClient(api_key="gsk_test123")
    assert client.health_check() is True
    mock_instance.models.list.assert_called_once()

    # Simulate failed health check
    mock_instance.models.list.side_effect = Exception("Invalid API key")
    assert client.health_check() is False
