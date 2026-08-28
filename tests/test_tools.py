from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_db
from app.core.chat.schemas import ChatMessage, ChatResponse, ToolCall, ToolResult, UserContext
from app.core.chat.service import ChatService, PendingConfirmation, _PENDING_CONFIRMATIONS
from app.core.chat.tools import (
    CONFIRMATION_KEYWORDS,
    ALL_TOOLS,
    ToolDispatcher,
    build_tool_dispatcher,
    confirmation_key,
    tool_requires_confirmation,
)
from app.core.chat.provider import MockLLMProvider
from app.core.chat.guardrails import GuardrailPolicy
from app.core.security import create_access_token
from app.db.database import Base
from app.main import app
from app.models.obligation import Obligation
from app.models.user import User


@pytest.fixture
def db_session() -> Session:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(autocommit=False, autoflush=False, bind=engine)()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(db_session: Session) -> TestClient:
    def override_get_db() -> Session:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def _create_user(db: Session, email: str = "user@example.com") -> User:
    user = User(
        name="Test User",
        email=email,
        password_hash="hashed",
        monthly_income=Decimal("10000.00"),
        fixed_expenses=Decimal("3000.00"),
        currency="EGP",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _auth_headers(user: User) -> dict[str, str]:
    token = create_access_token(subject=str(user.id))
    return {"Authorization": f"Bearer {token}"}


class TestToolRegistry:
    def test_all_seven_tools_registered(self) -> None:
        assert len(ALL_TOOLS) == 7
        names = {tool.name for tool in ALL_TOOLS}
        assert names == {
            "dashboard_summary",
            "forecast",
            "affordability",
            "list_obligations",
            "create_obligation",
            "update_obligation",
            "delete_obligation",
        }

    def test_unknown_tool_rejected(self, db_session: Session) -> None:
        dispatcher = build_tool_dispatcher(db_session)
        result = dispatcher.execute(UserContext(user_id=1), "nonexistent_tool", {})
        assert result.success is False
        assert "Unknown tool" in result.error


class TestToolSecurity:
    def test_tool_execution_uses_authenticated_user_context(self, db_session: Session) -> None:
        user = _create_user(db_session, email="alice@example.com")
        dispatcher = build_tool_dispatcher(db_session)
        result = dispatcher.execute(UserContext(user_id=user.id), "list_obligations", {})
        assert result.success is True

    def test_cross_user_read_rejected(self, db_session: Session) -> None:
        alice = _create_user(db_session, email="alice@example.com")
        bob = _create_user(db_session, email="bob@example.com")

        obligation = Obligation(
            user_id=alice.id,
            provider="Test",
            item_name="Laptop",
            category="Electronics",
            total_amount=Decimal("10000.00"),
            monthly_installment_amount=Decimal("1000.00"),
            start_date=date.today(),
            term_months=10,
            due_day_of_month=1,
        )
        db_session.add(obligation)
        db_session.commit()

        dispatcher = build_tool_dispatcher(db_session)
        result = dispatcher.execute(UserContext(user_id=bob.id), "list_obligations", {})
        assert result.success is True
        assert result.result == []

    def test_cross_user_update_rejected(self, db_session: Session) -> None:
        alice = _create_user(db_session, email="alice@example.com")
        bob = _create_user(db_session, email="bob@example.com")

        obligation = Obligation(
            user_id=alice.id,
            provider="Test",
            item_name="Laptop",
            category="Electronics",
            total_amount=Decimal("10000.00"),
            monthly_installment_amount=Decimal("1000.00"),
            start_date=date.today(),
            term_months=10,
            due_day_of_month=1,
        )
        db_session.add(obligation)
        db_session.commit()

        dispatcher = build_tool_dispatcher(db_session)
        result = dispatcher.execute(
            UserContext(user_id=bob.id),
            "update_obligation",
            {"obligation_id": obligation.id, "item_name": "Hacked"},
        )
        assert result.success is False
        assert "not found" in result.error.lower()

    def test_cross_user_delete_rejected(self, db_session: Session) -> None:
        alice = _create_user(db_session, email="alice@example.com")
        bob = _create_user(db_session, email="bob@example.com")

        obligation = Obligation(
            user_id=alice.id,
            provider="Test",
            item_name="Laptop",
            category="Electronics",
            total_amount=Decimal("10000.00"),
            monthly_installment_amount=Decimal("1000.00"),
            start_date=date.today(),
            term_months=10,
            due_day_of_month=1,
        )
        db_session.add(obligation)
        db_session.commit()

        dispatcher = build_tool_dispatcher(db_session)
        result = dispatcher.execute(
            UserContext(user_id=bob.id),
            "delete_obligation",
            {"obligation_id": obligation.id},
        )
        assert result.success is False
        assert "not found" in result.error.lower()


class TestReadTools:
    def test_dashboard_summary(self, db_session: Session) -> None:
        user = _create_user(db_session)
        dispatcher = build_tool_dispatcher(db_session)
        result = dispatcher.execute(UserContext(user_id=user.id), "dashboard_summary", {})
        assert result.success is True
        assert result.result["monthly_income"] == "10000.00"
        assert result.result["fixed_expenses"] == "3000.00"

    def test_forecast(self, db_session: Session) -> None:
        user = _create_user(db_session)
        dispatcher = build_tool_dispatcher(db_session)
        result = dispatcher.execute(
            UserContext(user_id=user.id),
            "forecast",
            {"start_month": date.today().isoformat(), "months": 3},
        )
        assert result.success is True
        assert len(result.result) == 3

    def test_affordability(self, db_session: Session) -> None:
        user = _create_user(db_session)
        dispatcher = build_tool_dispatcher(db_session)
        result = dispatcher.execute(
            UserContext(user_id=user.id),
            "affordability",
            {"amount": 5000, "start_date": date.today().isoformat(), "term_months": 6},
        )
        assert result.success is True
        assert "classification" in result.result

    def test_list_obligations(self, db_session: Session) -> None:
        user = _create_user(db_session)
        dispatcher = build_tool_dispatcher(db_session)
        result = dispatcher.execute(UserContext(user_id=user.id), "list_obligations", {})
        assert result.success is True
        assert result.result == []


class TestWriteTools:
    def test_create_obligation_requires_confirmation(self, db_session: Session) -> None:
        assert tool_requires_confirmation("create_obligation") is True

    def test_update_obligation_requires_confirmation(self, db_session: Session) -> None:
        assert tool_requires_confirmation("update_obligation") is True

    def test_delete_obligation_requires_confirmation(self, db_session: Session) -> None:
        assert tool_requires_confirmation("delete_obligation") is True

    def test_read_tools_do_not_require_confirmation(self, db_session: Session) -> None:
        assert tool_requires_confirmation("dashboard_summary") is False
        assert tool_requires_confirmation("forecast") is False
        assert tool_requires_confirmation("affordability") is False
        assert tool_requires_confirmation("list_obligations") is False

    def test_create_obligation_executes_after_confirmation(self, db_session: Session) -> None:
        user = _create_user(db_session)
        dispatcher = build_tool_dispatcher(db_session)
        result = dispatcher.execute(
            UserContext(user_id=user.id),
            "create_obligation",
            {
                "provider": "Test",
                "item_name": "Laptop",
                "category": "Electronics",
                "total_amount": 10000,
                "monthly_installment_amount": 1000,
                "start_date": date.today().isoformat(),
                "term_months": 10,
                "due_day_of_month": 1,
            },
        )
        assert result.success is True
        assert result.result["id"] is not None

    def test_update_obligation_executes_after_confirmation(self, db_session: Session) -> None:
        user = _create_user(db_session)
        obligation = Obligation(
            user_id=user.id,
            provider="Test",
            item_name="Laptop",
            category="Electronics",
            total_amount=Decimal("10000.00"),
            monthly_installment_amount=Decimal("1000.00"),
            start_date=date.today(),
            term_months=10,
            due_day_of_month=1,
        )
        db_session.add(obligation)
        db_session.commit()

        dispatcher = build_tool_dispatcher(db_session)
        result = dispatcher.execute(
            UserContext(user_id=user.id),
            "update_obligation",
            {"obligation_id": obligation.id, "item_name": "Gaming Laptop"},
        )
        assert result.success is True
        assert result.result["item_name"] == "Gaming Laptop"

    def test_delete_obligation_executes_after_confirmation(self, db_session: Session) -> None:
        user = _create_user(db_session)
        obligation = Obligation(
            user_id=user.id,
            provider="Test",
            item_name="Laptop",
            category="Electronics",
            total_amount=Decimal("10000.00"),
            monthly_installment_amount=Decimal("1000.00"),
            start_date=date.today(),
            term_months=10,
            due_day_of_month=1,
        )
        db_session.add(obligation)
        db_session.commit()

        dispatcher = build_tool_dispatcher(db_session)
        result = dispatcher.execute(
            UserContext(user_id=user.id),
            "delete_obligation",
            {"obligation_id": obligation.id},
        )
        assert result.success is True
        assert result.result["deleted_id"] == obligation.id


class TestConfirmation:
    def test_confirmation_key_is_deterministic(self) -> None:
        key1 = confirmation_key(1, "create_obligation", {"amount": 1000})
        key2 = confirmation_key(1, "create_obligation", {"amount": 1000})
        assert key1 == key2

    def test_confirmation_key_differs_for_different_arguments(self) -> None:
        key1 = confirmation_key(1, "create_obligation", {"amount": 1000})
        key2 = confirmation_key(1, "create_obligation", {"amount": 2000})
        assert key1 != key2

    def test_confirmation_keywords_contains_common_affirmatives(self) -> None:
        assert "yes" in CONFIRMATION_KEYWORDS
        assert "confirm" in CONFIRMATION_KEYWORDS
        assert "proceed" in CONFIRMATION_KEYWORDS


class TestToolLoop:
    def test_normal_text_response(self) -> None:
        provider = MockLLMProvider()
        service = ChatService(provider=provider, guardrails=GuardrailPolicy())
        result = service.chat(UserContext(user_id=1), "What is my budget?")
        assert "financial assistant" in result.content.lower()

    def test_tool_call_then_final_response(self) -> None:
        provider = MagicMock()
        provider.generate.side_effect = [
            ChatResponse(
                content="",
                tool_calls=[ToolCall(tool_name="list_obligations", arguments={})],
            ),
            ChatResponse(content="You have no obligations."),
        ]

        service = ChatService(
            provider=provider,
            guardrails=GuardrailPolicy(),
            tool_dispatcher=ToolDispatcher(db=MagicMock()),
        )
        result = service.chat(UserContext(user_id=1), "List my obligations")
        assert result.content == "You have no obligations."
        assert provider.generate.call_count == 2

    def test_multiple_tool_calls(self) -> None:
        provider = MagicMock()
        provider.generate.side_effect = [
            ChatResponse(
                content="",
                tool_calls=[
                    ToolCall(tool_name="list_obligations", arguments={}),
                    ToolCall(tool_name="dashboard_summary", arguments={}),
                ],
            ),
            ChatResponse(content="Here is your summary."),
        ]

        mock_dispatcher = MagicMock()
        mock_dispatcher.execute.side_effect = [
            ToolResult(tool_name="list_obligations", success=True, result=[]),
            ToolResult(tool_name="dashboard_summary", success=True, result={"monthly_income": "10000"}),
        ]

        service = ChatService(
            provider=provider,
            guardrails=GuardrailPolicy(),
            tool_dispatcher=mock_dispatcher,
        )
        result = service.chat(UserContext(user_id=1), "Give me a full overview")
        assert result.content == "Here is your summary."
        assert mock_dispatcher.execute.call_count == 2

    def test_unknown_tool_returns_safe_error(self) -> None:
        provider = MagicMock()
        provider.generate.return_value = ChatResponse(
            content="",
            tool_calls=[ToolCall(tool_name="unknown_tool", arguments={})],
        )

        mock_dispatcher = MagicMock()
        mock_dispatcher.execute.return_value = ToolResult(
            tool_name="unknown_tool", success=False, error="Unknown tool: unknown_tool"
        )

        service = ChatService(
            provider=provider,
            guardrails=GuardrailPolicy(),
            tool_dispatcher=mock_dispatcher,
        )
        result = service.chat(UserContext(user_id=1), "Do something")
        assert "error" in result.metadata or "unknown" in result.content.lower()

    def test_tool_loop_limit_exceeded(self) -> None:
        provider = MagicMock()
        tool_call = ChatResponse(
            content="",
            tool_calls=[ToolCall(tool_name="list_obligations", arguments={})],
        )
        provider.generate.return_value = tool_call

        mock_dispatcher = MagicMock()
        mock_dispatcher.execute.return_value = ToolResult(
            tool_name="list_obligations", success=True, result=[]
        )

        service = ChatService(
            provider=provider,
            guardrails=GuardrailPolicy(),
            tool_dispatcher=mock_dispatcher,
            max_tool_iterations=2,
        )
        result = service.chat(UserContext(user_id=1), "Loop forever")
        assert "trouble processing" in result.content.lower()
        assert provider.generate.call_count == 2

    def test_write_tool_requires_confirmation(self) -> None:
        provider = MagicMock()
        provider.generate.return_value = ChatResponse(
            content="",
            tool_calls=[ToolCall(tool_name="create_obligation", arguments={"amount": 1000})],
        )

        service = ChatService(
            provider=provider,
            guardrails=GuardrailPolicy(),
            tool_dispatcher=ToolDispatcher(db=MagicMock()),
        )
        result = service.chat(UserContext(user_id=1), "Create an obligation")
        assert "Should I proceed" in result.content
        assert result.metadata.get("pending_confirmation") is not None

    def test_write_request_creates_pending_confirmation(self) -> None:
        provider = MagicMock()
        provider.generate.return_value = ChatResponse(
            content="",
            tool_calls=[ToolCall(tool_name="create_obligation", arguments={"amount": 1000})],
        )

        service = ChatService(
            provider=provider,
            guardrails=GuardrailPolicy(),
            tool_dispatcher=MagicMock(),
        )
        _PENDING_CONFIRMATIONS.clear()

        result = service.chat(UserContext(user_id=1), "Create an obligation")
        assert "Should I proceed" in result.content
        assert result.metadata.get("pending_confirmation") is not None
        assert result.metadata["pending_confirmation"] in _PENDING_CONFIRMATIONS

    def test_second_request_with_correct_key_executes(self) -> None:
        provider = MagicMock()
        provider.generate.return_value = ChatResponse(
            content="",
            tool_calls=[ToolCall(tool_name="create_obligation", arguments={"amount": 1000})],
        )

        mock_dispatcher = MagicMock()
        mock_dispatcher.execute.return_value = ToolResult(
            tool_name="create_obligation", success=True, result={"id": 1}
        )

        service = ChatService(
            provider=provider,
            guardrails=GuardrailPolicy(),
            tool_dispatcher=mock_dispatcher,
        )
        _PENDING_CONFIRMATIONS.clear()

        # Request 1: create pending confirmation
        result1 = service.chat(UserContext(user_id=1), "Create an obligation")
        pending_key = result1.metadata["pending_confirmation"]

        # Request 2: confirm with key
        provider.generate.return_value = ChatResponse(content="Confirmed.")
        result2 = service.chat(UserContext(user_id=1), "yes", confirmed_tool_key=pending_key)
        assert "Done" in result2.content
        mock_dispatcher.execute.assert_called_once()
        assert pending_key not in _PENDING_CONFIRMATIONS

    def test_correct_key_cannot_be_reused(self) -> None:
        provider = MagicMock()
        provider.generate.return_value = ChatResponse(
            content="",
            tool_calls=[ToolCall(tool_name="create_obligation", arguments={"amount": 1000})],
        )

        mock_dispatcher = MagicMock()
        mock_dispatcher.execute.return_value = ToolResult(
            tool_name="create_obligation", success=True, result={"id": 1}
        )

        service = ChatService(
            provider=provider,
            guardrails=GuardrailPolicy(),
            tool_dispatcher=mock_dispatcher,
        )
        _PENDING_CONFIRMATIONS.clear()

        result1 = service.chat(UserContext(user_id=1), "Create an obligation")
        pending_key = result1.metadata["pending_confirmation"]

        provider.generate.return_value = ChatResponse(content="Confirmed.")
        service.chat(UserContext(user_id=1), "yes", confirmed_tool_key=pending_key)

        # Try to reuse the same key
        result2 = service.chat(UserContext(user_id=1), "yes again", confirmed_tool_key=pending_key)
        assert pending_key not in _PENDING_CONFIRMATIONS
        assert "invalid or has expired" in result2.content.lower()

    def test_wrong_user_cannot_use_key(self) -> None:
        provider = MagicMock()
        provider.generate.return_value = ChatResponse(
            content="",
            tool_calls=[ToolCall(tool_name="create_obligation", arguments={"amount": 1000})],
        )

        service = ChatService(
            provider=provider,
            guardrails=GuardrailPolicy(),
            tool_dispatcher=MagicMock(),
        )
        _PENDING_CONFIRMATIONS.clear()

        result1 = service.chat(UserContext(user_id=1), "Create an obligation")
        pending_key = result1.metadata["pending_confirmation"]

        provider.generate.return_value = ChatResponse(content="Confirmed.")
        result2 = service.chat(UserContext(user_id=2), "yes", confirmed_tool_key=pending_key)
        assert "can't confirm" in result2.content.lower()

    def test_wrong_tool_arguments_cannot_use_key(self) -> None:
        provider = MagicMock()
        provider.generate.return_value = ChatResponse(
            content="",
            tool_calls=[ToolCall(tool_name="create_obligation", arguments={"amount": 1000})],
        )

        service = ChatService(
            provider=provider,
            guardrails=GuardrailPolicy(),
            tool_dispatcher=MagicMock(),
        )
        _PENDING_CONFIRMATIONS.clear()

        result1 = service.chat(UserContext(user_id=1), "Create an obligation")
        pending_key = result1.metadata["pending_confirmation"]

        # Create a different pending confirmation with different arguments
        different_key = confirmation_key(1, "create_obligation", {"amount": 2000})
        _PENDING_CONFIRMATIONS[different_key] = PendingConfirmation(
            key=different_key,
            user_id=1,
            tool_name="create_obligation",
            arguments={"amount": 2000},
            prompt="create a 2000 EGP obligation",
        )

        provider.generate.return_value = ChatResponse(content="Confirmed.")
        result2 = service.chat(UserContext(user_id=1), "yes", confirmed_tool_key=pending_key)
        # The original key should still work because it wasn't consumed
        assert "Done" in result2.content

    def test_invalid_unknown_key_does_not_execute(self) -> None:
        provider = MagicMock()
        provider.generate.return_value = ChatResponse(content="Confirmed.")

        service = ChatService(
            provider=provider,
            guardrails=GuardrailPolicy(),
            tool_dispatcher=MagicMock(),
        )
        _PENDING_CONFIRMATIONS.clear()

        result = service.chat(UserContext(user_id=1), "hello", confirmed_tool_key="invalid-key")
        assert "invalid-key" not in _PENDING_CONFIRMATIONS
        assert "invalid or has expired" in result.content.lower()

    def test_read_tools_do_not_require_confirmation(self) -> None:
        provider = MagicMock()
        provider.generate.side_effect = [
            ChatResponse(
                content="",
                tool_calls=[ToolCall(tool_name="list_obligations", arguments={})],
            ),
            ChatResponse(content="You have no obligations."),
        ]

        mock_dispatcher = MagicMock()
        mock_dispatcher.execute.return_value = ToolResult(
            tool_name="list_obligations", success=True, result=[]
        )

        service = ChatService(
            provider=provider,
            guardrails=GuardrailPolicy(),
            tool_dispatcher=mock_dispatcher,
        )
        _PENDING_CONFIRMATIONS.clear()

        result = service.chat(UserContext(user_id=1), "List my obligations")
        assert "Should I proceed" not in result.content
        mock_dispatcher.execute.assert_called_once()


class TestProviderCompatibility:
    def test_mock_provider_remains_usable(self) -> None:
        provider = MockLLMProvider()
        result = provider.generate(messages=[ChatMessage(role="user", content="Hi")])
        assert result.content is not None
        assert result.tool_calls is None

    def test_gemini_tool_calls_extracted(self) -> None:
        mock_part = MagicMock()
        mock_part.text = None
        mock_part.function_call.name = "list_obligations"
        mock_part.function_call.args = {}

        mock_content = MagicMock()
        mock_content.parts = [mock_part]

        mock_candidate = MagicMock()
        mock_candidate.content = mock_content

        mock_response = MagicMock()
        mock_response.text = None
        mock_response.candidates = [mock_candidate]

        provider = MagicMock()
        provider.generate.return_value = ChatResponse(
            content="",
            tool_calls=[ToolCall(tool_name="list_obligations", arguments={})],
        )

        result = provider.generate(messages=[], tools=[])
        assert result.tool_calls == [ToolCall(tool_name="list_obligations", arguments={})]

    def test_groq_tool_calls_extracted(self) -> None:
        mock_tool_call = MagicMock()
        mock_tool_call.function.name = "list_obligations"
        mock_tool_call.function.arguments = "{}"

        mock_message = MagicMock()
        mock_message.content = None
        mock_message.tool_calls = [mock_tool_call]

        mock_choice = MagicMock()
        mock_choice.message = mock_message

        mock_response = MagicMock()
        mock_response.choices = [mock_choice]

        provider = MagicMock()
        provider.generate.return_value = ChatResponse(
            content="",
            tool_calls=[ToolCall(tool_name="list_obligations", arguments={})],
        )

        result = provider.generate(messages=[], tools=[])
        assert result.tool_calls == [ToolCall(tool_name="list_obligations", arguments={})]


class TestFinancialCorrectness:
    def test_forecast_tool_uses_build_forecast(self, db_session: Session) -> None:
        user = _create_user(db_session)
        dispatcher = build_tool_dispatcher(db_session)
        result = dispatcher.execute(
            UserContext(user_id=user.id),
            "forecast",
            {"start_month": date.today().isoformat(), "months": 1},
        )
        assert result.success is True
        assert result.result[0]["income"] == "10000.00"
        assert result.result[0]["fixed_expenses"] == "3000.00"

    def test_affordability_tool_uses_evaluate_affordability(self, db_session: Session) -> None:
        user = _create_user(db_session)
        dispatcher = build_tool_dispatcher(db_session)
        result = dispatcher.execute(
            UserContext(user_id=user.id),
            "affordability",
            {"amount": 5000, "start_date": date.today().isoformat(), "term_months": 6},
        )
        assert result.success is True
        assert result.result["classification"] in {
            "Comfortable", "Manageable", "Risky", "Not Affordable"
        }