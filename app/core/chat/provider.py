from __future__ import annotations

from typing import Protocol

from app.core.chat.schemas import ChatMessage, ChatResponse, ToolDefinition


class LLMProvider(Protocol):
    def generate(
        self,
        messages: list[ChatMessage],
        tools: list[ToolDefinition] | None = None,
    ) -> ChatResponse:
        ...


class MockLLMProvider:
    def generate(
        self,
        messages: list[ChatMessage],
        tools: list[ToolDefinition] | None = None,
    ) -> ChatResponse:
        return ChatResponse(
            content="I'm your Dabbarha financial assistant. I can help you with budgeting, forecasting, obligations, and affordability. What would you like to know?",
            metadata={"provider": "mock"},
        )


class GeminiProvider:
    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        from app.core.config import GEMINI_API_KEY, GEMINI_MODEL

        self._api_key = api_key or GEMINI_API_KEY
        self._model = model or GEMINI_MODEL

        if not self._api_key:
            raise ValueError("GEMINI_API_KEY is not configured")

        from google import genai

        self._client = genai.Client(api_key=self._api_key)

    def generate(
        self,
        messages: list[ChatMessage],
        tools: list[ToolDefinition] | None = None,
    ) -> ChatResponse:
        try:
            contents = self._convert_messages(messages)
            gemini_tools = self._convert_tools(tools) if tools else None

            kwargs: dict[str, object] = {
                "model": self._model,
                "contents": contents,
            }
            if gemini_tools is not None:
                kwargs["config"] = self._build_config(gemini_tools)

            response = self._client.models.generate_content(**kwargs)
            text = self._extract_text(response)

            return ChatResponse(
                content=text,
                metadata={"provider": "gemini", "model": self._model},
            )
        except Exception:
            return ChatResponse(
                content="I'm having trouble connecting right now. Please try again later.",
                metadata={"provider": "gemini", "error": "provider_error"},
            )

    def _convert_messages(self, messages: list[ChatMessage]) -> list[object]:
        from google.genai import types

        contents: list[object] = []
        for msg in messages:
            role = "user" if msg.role == "user" else "model"
            contents.append(
                types.Content(
                    role=role,
                    parts=[types.Part.from_text(text=msg.content)],
                )
            )
        return contents

    def _convert_tools(self, tools: list[ToolDefinition]) -> list[object]:
        from google.genai import types

        function_declarations = [
            types.FunctionDeclaration(
                name=tool.name,
                description=tool.description,
                parameters=tool.parameters,
            )
            for tool in tools
        ]
        return [types.Tool(function_declarations=function_declarations)]

    def _build_config(self, tools: list[object]) -> object:
        from google.genai import types

        return types.GenerateContentConfig(tools=tools)

    def _extract_text(self, response: object) -> str:
        if hasattr(response, "text") and response.text:
            return response.text

        candidates = getattr(response, "candidates", None)
        if candidates:
            for candidate in candidates:
                content = getattr(candidate, "content", None)
                if content is None:
                    continue
                parts = getattr(content, "parts", None)
                if parts:
                    for part in parts:
                        text = getattr(part, "text", None)
                        if text:
                            return text

        return "I received your request but couldn't generate a text response."


class GroqProvider:
    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        from app.core.config import GROQ_API_KEY, GROQ_MODEL

        self._api_key = api_key or GROQ_API_KEY
        self._model = model or GROQ_MODEL

        if not self._api_key:
            raise ValueError("GROQ_API_KEY is not configured")

        from groq import Groq

        self._client = Groq(api_key=self._api_key)

    def generate(
        self,
        messages: list[ChatMessage],
        tools: list[ToolDefinition] | None = None,
    ) -> ChatResponse:
        try:
            groq_messages = self._convert_messages(messages)
            groq_tools = self._convert_tools(tools) if tools else None

            kwargs: dict[str, object] = {
                "model": self._model,
                "messages": groq_messages,
            }
            if groq_tools is not None:
                kwargs["tools"] = groq_tools

            response = self._client.chat.completions.create(**kwargs)
            text = self._extract_text(response)

            return ChatResponse(
                content=text,
                metadata={"provider": "groq", "model": self._model},
            )
        except Exception:
            return ChatResponse(
                content="I'm having trouble connecting right now. Please try again later.",
                metadata={"provider": "groq", "error": "provider_error"},
            )

    def _convert_messages(self, messages: list[ChatMessage]) -> list[dict[str, str]]:
        return [
            {"role": msg.role, "content": msg.content}
            for msg in messages
        ]

    def _convert_tools(self, tools: list[ToolDefinition]) -> list[dict[str, object]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                },
            }
            for tool in tools
        ]

    def _extract_text(self, response: object) -> str:
        choices = getattr(response, "choices", None)
        if choices:
            message = getattr(choices[0], "message", None)
            if message is not None:
                content = getattr(message, "content", None)
                if content:
                    return content
        return "I received your request but couldn't generate a text response."


class FallbackLLMProvider:
    def __init__(self, primary: LLMProvider, fallback: LLMProvider) -> None:
        self.primary = primary
        self.fallback = fallback

    def generate(
        self,
        messages: list[ChatMessage],
        tools: list[ToolDefinition] | None = None,
    ) -> ChatResponse:
        primary_response = self.primary.generate(messages, tools)
        if self._is_provider_error(primary_response):
            fallback_response = self.fallback.generate(messages, tools)
            if self._is_provider_error(fallback_response):
                return ChatResponse(
                    content="I'm having trouble connecting right now. Please try again later.",
                    metadata={"provider": "fallback", "error": "provider_error"},
                )
            return fallback_response
        return primary_response

    def _is_provider_error(self, response: ChatResponse) -> bool:
        return bool(response.metadata and response.metadata.get("error") == "provider_error")
