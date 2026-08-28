from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.core.chat.conversation import ConversationRepository
from app.core.chat.guardrails import GuardrailPolicy, GuardrailDecision
from app.core.chat.provider import LLMProvider
from app.core.chat.schemas import ChatMessage, ChatResponse, ToolResult, UserContext
from app.core.chat.tools import (
    ALL_TOOLS,
    CONFIRMATION_KEYWORDS,
    WRITE_TOOL_NAMES,
    confirmation_key,
    tool_requires_confirmation,
)

if TYPE_CHECKING:
    from app.models.conversation import ConversationMessage


@dataclass(frozen=True)
class PendingConfirmation:
    key: str
    user_id: int
    tool_name: str
    arguments: dict[str, object]
    prompt: str


# Module-level pending confirmations so state survives across requests.
# Limitation: this is in-memory and will be lost on process restart.
_PENDING_CONFIRMATIONS: dict[str, PendingConfirmation] = {}


class ChatService:
    def __init__(
        self,
        provider: LLMProvider,
        guardrails: GuardrailPolicy,
        tool_dispatcher: object | None = None,
        max_tool_iterations: int = 5,
        conversation_repository: ConversationRepository | None = None,
        history_limit: int = 20,
    ) -> None:
        self.provider = provider
        self.guardrails = guardrails
        self.tool_definitions = ALL_TOOLS
        self.tool_dispatcher = tool_dispatcher
        self.max_tool_iterations = max_tool_iterations
        self.conversation_repository = conversation_repository
        self.history_limit = history_limit

    def chat(
        self,
        user_context: UserContext,
        message: str,
        conversation_id: int | None = None,
        confirmed_tool_key: str | None = None,
    ) -> ChatResponse:
        conversation: Conversation | None = None
        try:
            if self.conversation_repository is not None:
                conversation = self.conversation_repository.get_or_create_conversation(
                    user_id=user_context.user_id,
                    conversation_id=conversation_id,
                )
                conversation_id = conversation.id
                history = self.conversation_repository.get_messages(
                    conversation_id=conversation.id,
                    limit=self.history_limit,
                )
                messages = self._history_to_messages(history)
            else:
                messages = []
        except ValueError as exc:
            return ChatResponse(
                content=str(exc),
                metadata={"error": "conversation_not_found"},
                conversation_id=conversation_id,
            )

        if confirmed_tool_key:
            if confirmed_tool_key not in _PENDING_CONFIRMATIONS:
                return ChatResponse(
                    content="That confirmation key is invalid or has expired.",
                    metadata={"error": "invalid_confirmation_key"},
                )
            pending = _PENDING_CONFIRMATIONS.pop(confirmed_tool_key)
            if pending.user_id != user_context.user_id:
                return ChatResponse(
                    content="I can't confirm that action for you.",
                    metadata={"error": "confirmation_user_mismatch"},
                )
            result = self._execute_tool(user_context, pending.tool_name, pending.arguments)
            if self.conversation_repository is not None and conversation is not None:
                self.conversation_repository.add_message(
                    conversation_id=conversation.id,
                    role="user",
                    content=message,
                )
                self.conversation_repository.add_message(
                    conversation_id=conversation.id,
                    role="assistant",
                    content="",
                    tool_name=pending.tool_name,
                    tool_arguments=pending.arguments,
                    tool_result=result.result if result.success else result.error,
                )
            if result.success:
                return ChatResponse(
                    content=f"Done. {pending.prompt}",
                    metadata={"tool": pending.tool_name, "status": "executed"},
                    conversation_id=conversation_id,
                )
            return ChatResponse(
                content=f"I couldn't complete that action: {result.error}",
                metadata={"tool": pending.tool_name, "status": "error"},
                conversation_id=conversation_id,
            )

        decision = self.guardrails.decide(message)
        if decision.outcome != "allow":
            if self.conversation_repository is not None and conversation is not None:
                self.conversation_repository.add_message(
                    conversation_id=conversation.id,
                    role="user",
                    content=message,
                )
                self.conversation_repository.add_message(
                    conversation_id=conversation.id,
                    role="assistant",
                    content=decision.response.content,
                )
            return ChatResponse(
                content=decision.response.content,
                metadata=decision.response.metadata,
                conversation_id=conversation_id,
            )

        messages.append(ChatMessage(role="user", content=message))

        for _ in range(self.max_tool_iterations):
            response = self.provider.generate(messages, tools=self.tool_definitions)

            if response.tool_calls:
                tool_results = []
                needs_confirmation = False

                for tool_call in response.tool_calls:
                    if tool_requires_confirmation(tool_call.tool_name):
                        needs_confirmation = True
                        key = confirmation_key(user_context.user_id, tool_call.tool_name, tool_call.arguments)
                        _PENDING_CONFIRMATIONS[key] = PendingConfirmation(
                            key=key,
                            user_id=user_context.user_id,
                            tool_name=tool_call.tool_name,
                            arguments=tool_call.arguments,
                            prompt=self._format_confirmation_prompt(tool_call),
                        )

                if needs_confirmation:
                    pending = next(
                        p for p in _PENDING_CONFIRMATIONS.values()
                        if p.user_id == user_context.user_id
                    )
                    if self.conversation_repository is not None and conversation is not None:
                        self.conversation_repository.add_message(
                            conversation_id=conversation.id,
                            role="user",
                            content=message,
                        )
                        self.conversation_repository.add_message(
                            conversation_id=conversation.id,
                            role="assistant",
                            content="",
                            tool_name=pending.tool_name,
                            tool_arguments=pending.arguments,
                        )
                    return ChatResponse(
                        content=(
                            f"You're asking me to {pending.prompt}. "
                            "Should I proceed? Please confirm with 'yes' or 'confirm'."
                        ),
                        metadata={"pending_confirmation": pending.key},
                        conversation_id=conversation_id,
                    )

                for tool_call in response.tool_calls:
                    result = self._execute_tool(user_context, tool_call.tool_name, tool_call.arguments)
                    tool_results.append(result)

                for result in tool_results:
                    messages.append(
                        ChatMessage(
                            role="tool",
                            content=result.result if result.success else result.error or "",
                            tool_name=result.tool_name,
                        )
                    )

                continue

            if self.conversation_repository is not None and conversation is not None:
                self.conversation_repository.add_message(
                    conversation_id=conversation.id,
                    role="user",
                    content=message,
                )
                self.conversation_repository.add_message(
                    conversation_id=conversation.id,
                    role="assistant",
                    content=response.content,
                )
            return ChatResponse(
                content=response.content,
                metadata=response.metadata,
                conversation_id=conversation_id,
            )

        if self.conversation_repository is not None and conversation is not None:
            self.conversation_repository.add_message(
                conversation_id=conversation.id,
                role="user",
                content=message,
            )
            self.conversation_repository.add_message(
                conversation_id=conversation.id,
                role="assistant",
                content="I'm having trouble processing that. Please try again.",
            )
        return ChatResponse(
            content="I'm having trouble processing that. Please try again.",
            metadata={"error": "tool_loop_limit_exceeded"},
            conversation_id=conversation_id,
        )

    def _execute_tool(self, context: UserContext, tool_name: str, arguments: dict[str, object]) -> ToolResult:
        if self.tool_dispatcher is None:
            return ToolResult(
                tool_name=tool_name,
                success=False,
                error="Tool execution is not available.",
            )
        return self.tool_dispatcher.execute(context, tool_name, arguments)

    def _format_confirmation_prompt(self, tool_call: object) -> str:
        tool_name = getattr(tool_call, "tool_name", "")
        arguments = getattr(tool_call, "arguments", {})

        if tool_name == "create_obligation":
            amount = arguments.get("total_amount", "unknown")
            item = arguments.get("item_name", "unknown item")
            return f"create a {amount} EGP obligation for {item}"
        if tool_name == "update_obligation":
            obligation_id = arguments.get("obligation_id", "unknown")
            return f"update obligation {obligation_id}"
        if tool_name == "delete_obligation":
            obligation_id = arguments.get("obligation_id", "unknown")
            return f"delete obligation {obligation_id}"

        return f"execute {tool_name}"

    def _history_to_messages(self, history: list[ConversationMessage]) -> list[ChatMessage]:
        messages: list[ChatMessage] = []
        for item in history:
            if item.role == "tool":
                messages.append(
                    ChatMessage(
                        role="tool",
                        content=item.content,
                        tool_name=item.tool_name,
                    )
                )
            elif item.role == "assistant" and item.tool_name:
                messages.append(
                    ChatMessage(
                        role="assistant",
                        content=item.content,
                        tool_name=item.tool_name,
                        arguments=json.loads(item.tool_arguments) if item.tool_arguments else None,
                    )
                )
            else:
                messages.append(
                    ChatMessage(
                        role=item.role,
                        content=item.content,
                    )
                )
        return messages
