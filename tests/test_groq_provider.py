import sys
from unittest.mock import MagicMock, patch

import pytest

from app.core.chat.provider import GroqProvider, MockLLMProvider
from app.core.chat.schemas import ChatMessage, ChatResponse, ToolDefinition


def _mock_groq_modules():
    mock_groq = MagicMock()
    mock_groq.Groq.return_value = MagicMock()
    return mock_groq


def test_groq_provider_initializes_from_api_key() -> None:
    mock_groq = _mock_groq_modules()
    with (
        patch.dict(sys.modules, {"groq": mock_groq}),
        patch("app.core.config.GROQ_API_KEY", "test-api-key"),
        patch("app.core.config.GROQ_MODEL", "openai/gpt-oss-120b"),
    ):
        provider = GroqProvider()
        mock_groq.Groq.assert_called_once_with(api_key="test-api-key")


def test_missing_groq_api_key_produces_configuration_error() -> None:
    with patch("app.core.config.GROQ_API_KEY", None):
        with pytest.raises(ValueError, match="GROQ_API_KEY is not configured"):
            GroqProvider(api_key=None, model="openai/gpt-oss-120b")


def test_groq_response_maps_to_domain_response() -> None:
    mock_groq = _mock_groq_modules()
    mock_choice = MagicMock()
    mock_choice.message.content = "Hello from Groq"
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_groq.Groq.return_value.chat.completions.create.return_value = mock_response

    with patch.dict(sys.modules, {"groq": mock_groq}):
        provider = GroqProvider(api_key="test-key", model="openai/gpt-oss-120b")
        result = provider.generate(messages=[ChatMessage(role="user", content="Hi")])

    assert result.content == "Hello from Groq"
    assert result.metadata == {"provider": "groq", "model": "openai/gpt-oss-120b"}


def test_provider_receives_tool_definitions() -> None:
    mock_groq = _mock_groq_modules()
    mock_choice = MagicMock()
    mock_choice.message.content = "Tool result"
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_groq.Groq.return_value.chat.completions.create.return_value = mock_response

    with patch.dict(sys.modules, {"groq": mock_groq}):
        provider = GroqProvider(api_key="test-key", model="openai/gpt-oss-120b")
        tools = [ToolDefinition(name="test_tool", description="A test tool", parameters={})]
        provider.generate(
            messages=[ChatMessage(role="user", content="Use the tool")],
            tools=tools,
        )
        mock_groq.Groq.return_value.chat.completions.create.assert_called_once()
        call_kwargs = mock_groq.Groq.return_value.chat.completions.create.call_args[1]
        assert "tools" in call_kwargs
        assert call_kwargs["tools"] is not None
        assert call_kwargs["tools"][0]["function"]["name"] == "test_tool"


def test_openai_gpt_oss_120b_tool_definition_conversion() -> None:
    mock_groq = _mock_groq_modules()
    mock_choice = MagicMock()
    mock_choice.message.content = "Tool result"
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_groq.Groq.return_value.chat.completions.create.return_value = mock_response

    with patch.dict(sys.modules, {"groq": mock_groq}):
        provider = GroqProvider(api_key="test-key", model="openai/gpt-oss-120b")
        tools = [
            ToolDefinition(
                name="update_obligation",
                description="Update an obligation",
                parameters={
                    "type": "object",
                    "properties": {
                        "obligation_id": {"type": "integer"},
                        "amount": {"type": "number"},
                    },
                    "required": ["obligation_id", "amount"],
                },
            )
        ]
        provider.generate(
            messages=[ChatMessage(role="user", content="Use the tool")],
            tools=tools,
        )
        call_kwargs = mock_groq.Groq.return_value.chat.completions.create.call_args[1]
        tool_payload = call_kwargs["tools"][0]
        assert tool_payload["type"] == "function"
        assert tool_payload["function"]["name"] == "update_obligation"
        assert tool_payload["function"]["parameters"]["required"] == ["obligation_id", "amount"]


def test_provider_errors_converted_to_provider_error() -> None:
    mock_groq = _mock_groq_modules()
    mock_groq.Groq.return_value.chat.completions.create.side_effect = Exception("API error")

    with patch.dict(sys.modules, {"groq": mock_groq}):
        provider = GroqProvider(api_key="test-key", model="openai/gpt-oss-120b")
        result = provider.generate(messages=[ChatMessage(role="user", content="Hi")])

    assert result.metadata == {"provider": "groq", "error": "provider_error"}
    assert "trouble connecting" in result.content.lower()


def test_api_key_not_in_response_or_error() -> None:
    mock_groq = _mock_groq_modules()
    mock_choice = MagicMock()
    mock_choice.message.content = "Hello"
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_groq.Groq.return_value.chat.completions.create.return_value = mock_response

    with patch.dict(sys.modules, {"groq": mock_groq}):
        provider = GroqProvider(api_key="secret-key-123", model="openai/gpt-oss-120b")
        result = provider.generate(messages=[ChatMessage(role="user", content="Hi")])

    assert "secret-key-123" not in result.content
    assert "secret-key-123" not in str(result.metadata)

    mock_groq.Groq.return_value.chat.completions.create.side_effect = Exception("API error")
    result = provider.generate(messages=[ChatMessage(role="user", content="Hi")])
    assert "secret-key-123" not in result.content
    assert "secret-key-123" not in str(result.metadata)


def test_mock_llm_provider_continues_passing() -> None:
    provider = MockLLMProvider()
    result = provider.generate(messages=[ChatMessage(role="user", content="Hi")])
    assert result.content == "I'm your Dabbarha financial assistant. I can help you with budgeting, forecasting, obligations, and affordability. What would you like to know?"
    assert result.metadata == {"provider": "mock"}


def test_groq_provider_returns_generic_message_when_no_content() -> None:
    mock_groq = _mock_groq_modules()
    mock_choice = MagicMock()
    mock_choice.message.content = None
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_groq.Groq.return_value.chat.completions.create.return_value = mock_response

    with patch.dict(sys.modules, {"groq": mock_groq}):
        provider = GroqProvider(api_key="test-key", model="openai/gpt-oss-120b")
        result = provider.generate(messages=[ChatMessage(role="user", content="Hi")])

    assert result.content == "I received your request but couldn't generate a text response."
