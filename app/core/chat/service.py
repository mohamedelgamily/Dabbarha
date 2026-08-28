from __future__ import annotations

from app.core.chat.guardrails import GuardrailPolicy, GuardrailDecision
from app.core.chat.provider import LLMProvider
from app.core.chat.schemas import ChatResponse, UserContext
from app.core.chat.tools import ALL_TOOLS


class ChatService:
    def __init__(
        self,
        provider: LLMProvider,
        guardrails: GuardrailPolicy,
    ) -> None:
        self.provider = provider
        self.guardrails = guardrails
        self.tool_definitions = ALL_TOOLS

    def chat(self, user_context: UserContext, message: str) -> ChatResponse:
        decision = self.guardrails.decide(message)
        if decision.outcome != "allow":
            return decision.response

        return self.provider.generate(
            messages=[],
            tools=self.tool_definitions,
        )
