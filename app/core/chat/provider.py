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
