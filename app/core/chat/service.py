from __future__ import annotations

from dataclasses import dataclass

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
    ) -> None:
        self.provider = provider
        self.guardrails = guardrails
        self.tool_definitions = ALL_TOOLS
        self.tool_dispatcher = tool_dispatcher
        self.max_tool_iterations = max_tool_iterations

    def chat(
        self,
        user_context: UserContext,
        message: str,
        confirmed_tool_key: str | None = None,
    ) -> ChatResponse:
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
            if result.success:
                return ChatResponse(
                    content=f"Done. {pending.prompt}",
                    metadata={"tool": pending.tool_name, "status": "executed"},
                )
            return ChatResponse(
                content=f"I couldn't complete that action: {result.error}",
                metadata={"tool": pending.tool_name, "status": "error"},
            )

        decision = self.guardrails.decide(message)
        if decision.outcome != "allow":
            return decision.response

        messages = [ChatMessage(role="user", content=message)]

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
                    return ChatResponse(
                        content=(
                            f"You're asking me to {pending.prompt}. "
                            "Should I proceed? Please confirm with 'yes' or 'confirm'."
                        ),
                        metadata={"pending_confirmation": pending.key},
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

            return response

        return ChatResponse(
            content="I'm having trouble processing that. Please try again.",
            metadata={"error": "tool_loop_limit_exceeded"},
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
