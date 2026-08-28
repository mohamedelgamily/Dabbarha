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
