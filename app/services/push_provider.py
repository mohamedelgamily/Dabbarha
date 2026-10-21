"""Replaceable push transport. Expo ticket acceptance is not device delivery."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import httpx


@dataclass(frozen=True)
class SendResult:
    accepted: bool
    ticket_id: str | None = None
    retryable: bool = False
    error_code: str | None = None


class PushProvider(Protocol):
    def send(self, token: str, title: str, body: str, data: dict) -> SendResult: ...
    def receipts(self, ticket_ids: list[str]) -> dict[str, dict]: ...


class ExpoPushAdapter:
    SEND_URL = "https://exp.host/--/api/v2/push/send"
    RECEIPTS_URL = "https://exp.host/--/api/v2/push/getReceipts"

    def __init__(self, access_token: str = "", timeout: float = 5.0, client=None):
        self.access_token = access_token
        self.client = client or httpx.Client(timeout=httpx.Timeout(timeout), follow_redirects=False)

    def _headers(self):
        result = {"accept": "application/json", "content-type": "application/json"}
        if self.access_token:
            result["authorization"] = f"Bearer {self.access_token}"
        return result

    def send(self, token: str, title: str, body: str, data: dict) -> SendResult:
        payload = {"to": token, "title": title, "body": body, "data": data,
                   "sound": "default", "priority": "default"}
        try:
            response = self.client.post(self.SEND_URL, json=payload, headers=self._headers())
        except httpx.TimeoutException:
            # The provider may have accepted the request before the timeout. Retrying
            # could produce a duplicate, so this ambiguous result is terminal.
            return SendResult(False, retryable=False, error_code="delivery_outcome_unknown")
        except httpx.TransportError:
            return SendResult(False, retryable=False, error_code="transport_outcome_unknown")
        if response.status_code == 429 or response.status_code >= 500:
            return SendResult(False, retryable=True, error_code=f"http_{response.status_code}")
        if not response.is_success:
            return SendResult(False, error_code=f"http_{response.status_code}")
        try:
            ticket = response.json().get("data")
            if isinstance(ticket, list):
                ticket = ticket[0] if ticket else None
            if not isinstance(ticket, dict):
                return SendResult(False, error_code="invalid_provider_response")
            if ticket.get("status") == "ok" and isinstance(ticket.get("id"), str):
                return SendResult(True, ticket_id=ticket["id"])
            details = ticket.get("details")
            code = details.get("error") if isinstance(details, dict) else None
            return SendResult(False, retryable=code in {"MessageRateExceeded"},
                              error_code=code if isinstance(code, str) else "provider_rejected")
        except (ValueError, TypeError, AttributeError):
            return SendResult(False, error_code="invalid_provider_response")

    def receipts(self, ticket_ids: list[str]) -> dict[str, dict]:
        if not ticket_ids:
            return {}
        response = self.client.post(self.RECEIPTS_URL, json={"ids": ticket_ids}, headers=self._headers())
        response.raise_for_status()
        payload = response.json()
        data = payload.get("data", {}) if isinstance(payload, dict) else {}
        return data if isinstance(data, dict) else {}

    def close(self):
        self.client.close()


class MockPushAdapter:
    """Deterministic worker-test transport; it never contacts a network."""
    def __init__(self, send_result: SendResult | None = None, receipts: dict[str, dict] | None = None):
        self.send_result = send_result or SendResult(True, ticket_id="mock-ticket")
        self.receipt_results = receipts or {"mock-ticket": {"status": "ok"}}
        self.sent: list[dict] = []
        self.receipt_calls: list[list[str]] = []

    def send(self, token: str, title: str, body: str, data: dict) -> SendResult:
        self.sent.append({"token": token, "title": title, "body": body, "data": data})
        return self.send_result

    def receipts(self, ticket_ids: list[str]) -> dict[str, dict]:
        self.receipt_calls.append(list(ticket_ids))
        return {ticket: self.receipt_results[ticket] for ticket in ticket_ids if ticket in self.receipt_results}

    def close(self):
        pass
