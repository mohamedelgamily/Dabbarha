from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ChatMessage:
    role: str
    content: str
    tool_call_id: str | None = None
    tool_name: str | None = None
    arguments: dict[str, object] | None = None


@dataclass(frozen=True)
class ToolCall:
    tool_name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class ChatResponse:
    content: str
    metadata: dict[str, str] | None = None
    tool_calls: list[ToolCall] | None = None
    conversation_id: int | None = None


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    parameters: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ToolResult:
    tool_name: str
    success: bool
    result: Any = None
    error: str | None = None
    requires_confirmation: bool = False


@dataclass(frozen=True)
class UserContext:
    user_id: int
