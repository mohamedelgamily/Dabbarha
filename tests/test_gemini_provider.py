import sys
from unittest.mock import MagicMock, patch

import pytest

from app.core.chat.provider import GeminiProvider, MockLLMProvider
from app.core.chat.schemas import ChatMessage, ChatResponse, ToolDefinition


def _mock_genai_modules():
    mock_google = MagicMock()
    mock_genai = MagicMock()
    mock_types = MagicMock()

    mock_google.genai = mock_genai
    mock_genai.Client.return_value = MagicMock()
    mock_genai.types = mock_types

    return {
        "google": mock_google,
        "google.genai": mock_genai,
        "google.genai.types": mock_types,
    }


def test_gemini_provider_initializes_from_api_key() -> None:
    mock_modules = _mock_genai_modules()
    with (
        patch.dict(sys.modules, mock_modules),
        patch("app.core.config.GEMINI_API_KEY", "test-api-key"),
        patch("app.core.config.GEMINI_MODEL", "gemini-3.7-flash"),
    ):
        provider = GeminiProvider()
        mock_modules["google.genai"].Client.assert_called_once_with(api_key="test-api-key")


def test_missing_api_key_produces_configuration_error() -> None:
    with patch("app.core.config.GEMINI_API_KEY", None):
        with pytest.raises(ValueError, match="GEMINI_API_KEY is not configured"):
            GeminiProvider(api_key=None, model="gemini-3.7-flash")


def test_gemini_response_maps_to_domain_response() -> None:
    mock_modules = _mock_genai_modules()
    mock_response = MagicMock()
    mock_response.text = "Hello from Gemini"
    mock_response.candidates = []
    mock_modules["google.genai"].Client.return_value.models.generate_content.return_value = mock_response

    with patch.dict(sys.modules, mock_modules):
        provider = GeminiProvider(api_key="test-key", model="gemini-3.7-flash")
        result = provider.generate(messages=[ChatMessage(role="user", content="Hi")])

    assert result.content == "Hello from Gemini"
    assert result.metadata == {"provider": "gemini", "model": "gemini-3.7-flash"}


def test_provider_receives_tool_definitions() -> None:
    mock_modules = _mock_genai_modules()
    mock_response = MagicMock()
    mock_response.text = "Tool result"
    mock_response.candidates = []
    mock_modules["google.genai"].Client.return_value.models.generate_content.return_value = mock_response

    with patch.dict(sys.modules, mock_modules):
        provider = GeminiProvider(api_key="test-key", model="gemini-3.7-flash")
        tools = [ToolDefinition(name="test_tool", description="A test tool", parameters={})]
        provider.generate(
            messages=[ChatMessage(role="user", content="Use the tool")],
            tools=tools,
        )
        mock_modules["google.genai"].Client.return_value.models.generate_content.assert_called_once()
        call_kwargs = mock_modules["google.genai"].Client.return_value.models.generate_content.call_args[1]
        assert "config" in call_kwargs
        assert call_kwargs["config"] is not None


def test_provider_errors_converted_to_provider_error() -> None:
    mock_modules = _mock_genai_modules()
    mock_modules["google.genai"].Client.return_value.models.generate_content.side_effect = Exception("API error")

    with patch.dict(sys.modules, mock_modules):
        provider = GeminiProvider(api_key="test-key", model="gemini-3.7-flash")
        result = provider.generate(messages=[ChatMessage(role="user", content="Hi")])

    assert result.metadata == {"provider": "gemini", "error": "provider_error"}
    assert "trouble connecting" in result.content.lower()


def test_api_key_not_in_response_or_error() -> None:
    mock_modules = _mock_genai_modules()
    mock_response = MagicMock()
    mock_response.text = "Hello"
    mock_response.candidates = []
    mock_modules["google.genai"].Client.return_value.models.generate_content.return_value = mock_response

    with patch.dict(sys.modules, mock_modules):
        provider = GeminiProvider(api_key="secret-key-123", model="gemini-3.7-flash")
        result = provider.generate(messages=[ChatMessage(role="user", content="Hi")])

    assert "secret-key-123" not in result.content
    assert "secret-key-123" not in str(result.metadata)

    mock_modules["google.genai"].Client.return_value.models.generate_content.side_effect = Exception("API error")
    result = provider.generate(messages=[ChatMessage(role="user", content="Hi")])
    assert "secret-key-123" not in result.content
    assert "secret-key-123" not in str(result.metadata)


def test_mock_llm_provider_continues_passing() -> None:
    provider = MockLLMProvider()
    result = provider.generate(messages=[ChatMessage(role="user", content="Hi")])
    assert result.content == "I'm your Dabbarha financial assistant. I can help you with budgeting, forecasting, obligations, and affordability. What would you like to know?"
    assert result.metadata == {"provider": "mock"}


def test_gemini_provider_extracts_text_from_candidate_parts() -> None:
    mock_modules = _mock_genai_modules()
    mock_part = MagicMock()
    mock_part.text = "Text from part"
    mock_content = MagicMock()
    mock_content.parts = [mock_part]
    mock_candidate = MagicMock()
    mock_candidate.content = mock_content
    mock_response = MagicMock()
    mock_response.text = None
    mock_response.candidates = [mock_candidate]
    mock_modules["google.genai"].Client.return_value.models.generate_content.return_value = mock_response

    with patch.dict(sys.modules, mock_modules):
        provider = GeminiProvider(api_key="test-key", model="gemini-3.7-flash")
        result = provider.generate(messages=[ChatMessage(role="user", content="Hi")])

    assert result.content == "Text from part"


def test_gemini_provider_returns_generic_message_when_no_text() -> None:
    mock_modules = _mock_genai_modules()
    mock_response = MagicMock()
    mock_response.text = None
    mock_response.candidates = []
    mock_modules["google.genai"].Client.return_value.models.generate_content.return_value = mock_response

    with patch.dict(sys.modules, mock_modules):
        provider = GeminiProvider(api_key="test-key", model="gemini-3.7-flash")
        result = provider.generate(messages=[ChatMessage(role="user", content="Hi")])

    assert result.content == "I received your request but couldn't generate a text response."
