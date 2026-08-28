from __future__ import annotations

from dataclasses import dataclass

from app.core.chat.schemas import ChatResponse


@dataclass(frozen=True)
class GuardrailDecision:
    outcome: str
    response: ChatResponse


class GuardrailPolicy:
    def __init__(self) -> None:
        self.financial_keywords = {
            "income",
            "expense",
            "budget",
            "loan",
            "afford",
            "forecast",
            "obligation",
            "payment",
            "debt",
            "savings",
            "investment",
            "finance",
            "financial",
            "money",
            "cash",
            "buffer",
            "commitment",
            "installment",
            "term",
            "dashboard",
            "affordability",
        }
        self.unrelated_keywords = {
            "weather",
            "sports",
            "movie",
            "recipe",
            "travel",
            "game",
            "joke",
            "story",
            "poem",
            "song",
        }
        self.injection_patterns = [
            "ignore previous instructions",
            "ignore all previous",
            "system prompt",
            "you are now",
            "act as",
            "pretend to be",
            "disregard",
            "override",
            "new instructions",
        ]

    def decide(self, message: str) -> GuardrailDecision:
        stripped = message.strip()
        if not stripped:
            return GuardrailDecision(
                outcome="injection",
                response=ChatResponse(
                    content="Please provide a message so I can help you.",
                    metadata={"guardrail": "empty_message"},
                ),
            )
        if len(stripped) > 2000:
            return GuardrailDecision(
                outcome="injection",
                response=ChatResponse(
                    content="Your message is too long. Please keep it under 2000 characters.",
                    metadata={"guardrail": "message_too_long"},
                ),
            )

        if self._check_injection(message):
            return GuardrailDecision(
                outcome="injection",
                response=ChatResponse(
                    content="I can't process that request. Please ask me about your finances.",
                    metadata={"guardrail": "injection_attempt"},
                ),
            )

        if self._is_unrelated(message):
            return GuardrailDecision(
                outcome="out_of_scope",
                response=ChatResponse(
                    content="I'm here to help with your finances. I can assist with budgeting, forecasting, obligations, and affordability questions.",
                    metadata={"guardrail": "out_of_scope"},
                ),
            )

        return GuardrailDecision(
            outcome="allow",
            response=ChatResponse(content=stripped, metadata={"guardrail": "allow"}),
        )

    def _is_unrelated(self, message: str) -> bool:
        lower = message.lower()
        for keyword in self.unrelated_keywords:
            if keyword in lower:
                return True
        return False

    def _check_injection(self, message: str) -> bool:
        lower = message.lower()
        for pattern in self.injection_patterns:
            if pattern in lower:
                return True
        return False
