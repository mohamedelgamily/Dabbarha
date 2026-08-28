from __future__ import annotations

import hashlib
import json
from datetime import date
from decimal import Decimal
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.affordability import AffordabilityResult, ProposedCommitment, evaluate_affordability
from app.core.chat.schemas import ToolDefinition, ToolResult, UserContext
from app.core.forecast import build_forecast, month_start
from app.models.obligation import Obligation
from app.models.user import User


class Tool(Protocol):
    name: str
    description: str
    parameters: dict[str, object]
    requires_confirmation: bool = False

    def execute(self, context: UserContext, db: Session, **kwargs: object) -> ToolResult:
        ...


WRITE_TOOL_NAMES = {"create_obligation", "update_obligation", "delete_obligation"}


class ToolDispatcher:
    def __init__(self, db: Session) -> None:
        self._db = db
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def execute(self, context: UserContext, tool_name: str, arguments: dict[str, Any]) -> ToolResult:
        if tool_name not in self._tools:
            return ToolResult(
                tool_name=tool_name,
                success=False,
                error=f"Unknown tool: {tool_name}",
            )

        tool = self._tools[tool_name]
        validation_error = self._validate_arguments(tool, arguments)
        if validation_error:
            return ToolResult(
                tool_name=tool_name,
                success=False,
                error=validation_error,
            )

        try:
            return tool.execute(context, db=self._db, **arguments)
        except Exception as exc:  # noqa: BLE001
            return ToolResult(
                tool_name=tool_name,
                success=False,
                error="A server error occurred while executing the tool.",
            )

    def _validate_arguments(self, tool: Tool, arguments: dict[str, Any]) -> str | None:
        required = tool.parameters.get("required", [])
        for field in required:
            if field not in arguments or arguments[field] is None:
                return f"Missing required argument: {field}"

        properties = tool.parameters.get("properties", {})
        for field, value in arguments.items():
            if field not in properties:
                return f"Unexpected argument: {field}"
            expected_type = properties[field].get("type")
            if expected_type == "integer" and not isinstance(value, int):
                return f"Argument {field} must be an integer"
            if expected_type == "number" and not isinstance(value, (int, float)):
                return f"Argument {field} must be a number"
            if expected_type == "string" and not isinstance(value, str):
                return f"Argument {field} must be a string"

        return None


class DashboardSummaryTool:
    name = "dashboard_summary"
    description = "Get the authenticated user's dashboard summary including income, fixed expenses, and current month buffer."
    parameters = {"type": "object", "properties": {}}
    requires_confirmation = False

    def execute(self, context: UserContext, db: Session, **kwargs: object) -> ToolResult:  # noqa: ARG002
        user = db.get(User, context.user_id)
        if user is None:
            return ToolResult(tool_name=self.name, success=False, error="User not found.")

        current_month = month_start(date.today())
        obligations = self._load_obligations(db, context.user_id)

        forecast = build_forecast(
            monthly_income=user.monthly_income,
            fixed_expenses=user.fixed_expenses,
            obligations=obligations,
            start_month=current_month,
            months=1,
        )
        current_month_forecast = forecast[0]

        result = {
            "monthly_income": str(user.monthly_income),
            "fixed_expenses": str(user.fixed_expenses),
            "current_month_obligation_payments": str(current_month_forecast.obligation_payments),
            "current_month_projected_buffer": str(current_month_forecast.projected_buffer),
            "has_current_month_negative_buffer": current_month_forecast.has_negative_buffer,
            "active_obligations_count": sum(
                1 for o in obligations if o.status in {"active", "late"}
            ),
        }

        return ToolResult(tool_name=self.name, success=True, result=result)

    def _load_obligations(self, db: Session, user_id: int) -> list[Obligation]:
        stmt = select(Obligation).where(Obligation.user_id == user_id)
        return list(db.scalars(stmt).all())


class ForecastTool:
    name = "forecast"
    description = "Get a monthly cash-flow forecast for the authenticated user."
    parameters = {
        "type": "object",
        "properties": {
            "start_month": {"type": "string", "format": "date"},
            "months": {"type": "integer", "minimum": 1, "maximum": 60},
        },
        "required": ["start_month", "months"],
    }
    requires_confirmation = False

    def execute(self, context: UserContext, db: Session, **kwargs: object) -> ToolResult:
        user = db.get(User, context.user_id)
        if user is None:
            return ToolResult(tool_name=self.name, success=False, error="User not found.")

        start_month = kwargs.get("start_month")
        months = kwargs.get("months")

        if not isinstance(start_month, str) or not isinstance(months, int):
            return ToolResult(tool_name=self.name, success=False, error="Invalid argument types.")

        try:
            start_date = date.fromisoformat(start_month)
        except ValueError:
            return ToolResult(tool_name=self.name, success=False, error="Invalid start_month format. Use YYYY-MM-DD.")

        if months < 1 or months > 60:
            return ToolResult(tool_name=self.name, success=False, error="months must be between 1 and 60.")

        obligations = self._load_obligations(db, context.user_id)
        rows = build_forecast(
            monthly_income=user.monthly_income,
            fixed_expenses=user.fixed_expenses,
            obligations=obligations,
            start_month=start_date,
            months=months,
        )

        result = [
            {
                "month": row.month.isoformat(),
                "income": str(row.income),
                "fixed_expenses": str(row.fixed_expenses),
                "obligation_payments": str(row.obligation_payments),
                "projected_buffer": str(row.projected_buffer),
                "has_negative_buffer": row.has_negative_buffer,
            }
            for row in rows
        ]

        return ToolResult(tool_name=self.name, success=True, result=result)

    def _load_obligations(self, db: Session, user_id: int) -> list[Obligation]:
        stmt = select(Obligation).where(Obligation.user_id == user_id)
        return list(db.scalars(stmt).all())


class AffordabilityTool:
    name = "affordability"
    description = "Evaluate whether the authenticated user can afford a proposed financial commitment."
    parameters = {
        "type": "object",
        "properties": {
            "amount": {"type": "number", "minimum": 0},
            "start_date": {"type": "string", "format": "date"},
            "term_months": {"type": "integer", "minimum": 1},
        },
        "required": ["amount", "start_date", "term_months"],
    }
    requires_confirmation = False

    def execute(self, context: UserContext, db: Session, **kwargs: object) -> ToolResult:
        user = db.get(User, context.user_id)
        if user is None:
            return ToolResult(tool_name=self.name, success=False, error="User not found.")

        amount = kwargs.get("amount")
        start_date = kwargs.get("start_date")
        term_months = kwargs.get("term_months")

        if not isinstance(amount, (int, float)) or not isinstance(start_date, str) or not isinstance(term_months, int):
            return ToolResult(tool_name=self.name, success=False, error="Invalid argument types.")

        try:
            parsed_start = date.fromisoformat(start_date)
        except ValueError:
            return ToolResult(tool_name=self.name, success=False, error="Invalid start_date format. Use YYYY-MM-DD.")

        if amount < 0:
            return ToolResult(tool_name=self.name, success=False, error="amount must be greater than or equal to 0.")
        if term_months < 1:
            return ToolResult(tool_name=self.name, success=False, error="term_months must be greater than 0.")

        obligations = self._load_obligations(db, context.user_id)
        proposed = ProposedCommitment(
            amount=Decimal(str(amount)),
            start_date=parsed_start,
            term_months=term_months,
        )

        result: AffordabilityResult = evaluate_affordability(
            monthly_income=user.monthly_income,
            fixed_expenses=user.fixed_expenses,
            existing_obligations=obligations,
            proposed_commitment=proposed,
            start_month=month_start(proposed.start_date),
            months=proposed.term_months,
        )

        return ToolResult(
            tool_name=self.name,
            success=True,
            result={
                "classification": result.classification,
                "worst_projected_buffer": str(result.worst_projected_buffer),
                "worst_buffer_percentage": str(result.worst_buffer_percentage),
                "worst_month": result.worst_month.isoformat(),
                "explanation": result.explanation,
                "monthly_results": [
                    {
                        "month": row.month.isoformat(),
                        "income": str(row.income),
                        "fixed_expenses": str(row.fixed_expenses),
                        "existing_obligation_payments": str(row.existing_obligation_payments),
                        "proposed_commitment_amount": str(row.proposed_commitment_amount),
                        "projected_buffer": str(row.projected_buffer),
                    }
                    for row in result.monthly_results
                ],
            },
        )

    def _load_obligations(self, db: Session, user_id: int) -> list[Obligation]:
        stmt = select(Obligation).where(Obligation.user_id == user_id)
        return list(db.scalars(stmt).all())


class ListObligationsTool:
    name = "list_obligations"
    description = "List the authenticated user's obligations."
    parameters = {"type": "object", "properties": {}}
    requires_confirmation = False

    def execute(self, context: UserContext, db: Session, **kwargs: object) -> ToolResult:  # noqa: ARG002
        obligations = self._load_obligations(db, context.user_id)
        result = [
            {
                "id": o.id,
                "provider": o.provider,
                "item_name": o.item_name,
                "category": o.category,
                "total_amount": str(o.total_amount),
                "monthly_installment_amount": str(o.monthly_installment_amount),
                "start_date": o.start_date.isoformat(),
                "term_months": o.term_months,
                "due_day_of_month": o.due_day_of_month,
                "status": o.status,
            }
            for o in obligations
        ]
        return ToolResult(tool_name=self.name, success=True, result=result)

    def _load_obligations(self, db: Session, user_id: int) -> list[Obligation]:
        stmt = select(Obligation).where(Obligation.user_id == user_id)
        return list(db.scalars(stmt).all())


class CreateObligationTool:
    name = "create_obligation"
    description = "Create a new obligation for the authenticated user."
    parameters = {
        "type": "object",
        "properties": {
            "provider": {"type": "string"},
            "item_name": {"type": "string"},
            "category": {"type": "string"},
            "total_amount": {"type": "number", "minimum": 0},
            "monthly_installment_amount": {"type": "number", "minimum": 0},
            "start_date": {"type": "string", "format": "date"},
            "term_months": {"type": "integer", "minimum": 1},
            "due_day_of_month": {"type": "integer", "minimum": 1, "maximum": 31},
        },
        "required": [
            "provider",
            "item_name",
            "category",
            "total_amount",
            "monthly_installment_amount",
            "start_date",
            "term_months",
            "due_day_of_month",
        ],
    }
    requires_confirmation = True

    def execute(self, context: UserContext, db: Session, **kwargs: object) -> ToolResult:
        user = db.get(User, context.user_id)
        if user is None:
            return ToolResult(tool_name=self.name, success=False, error="User not found.")

        try:
            obligation = Obligation(
                user_id=context.user_id,
                provider=str(kwargs["provider"]).strip(),
                item_name=str(kwargs["item_name"]).strip(),
                category=str(kwargs["category"]).strip(),
                total_amount=Decimal(str(kwargs["total_amount"])),
                monthly_installment_amount=Decimal(str(kwargs["monthly_installment_amount"])),
                start_date=date.fromisoformat(str(kwargs["start_date"])),
                term_months=int(kwargs["term_months"]),
                due_day_of_month=int(kwargs["due_day_of_month"]),
            )
        except (KeyError, ValueError, TypeError) as exc:
            return ToolResult(tool_name=self.name, success=False, error=f"Invalid arguments: {exc}")

        db.add(obligation)
        db.commit()
        db.refresh(obligation)

        return ToolResult(
            tool_name=self.name,
            success=True,
            result={
                "id": obligation.id,
                "provider": obligation.provider,
                "item_name": obligation.item_name,
                "category": obligation.category,
                "total_amount": str(obligation.total_amount),
                "monthly_installment_amount": str(obligation.monthly_installment_amount),
                "start_date": obligation.start_date.isoformat(),
                "term_months": obligation.term_months,
                "due_day_of_month": obligation.due_day_of_month,
                "status": obligation.status,
            },
        )


class UpdateObligationTool:
    name = "update_obligation"
    description = "Update an existing obligation belonging to the authenticated user."
    parameters = {
        "type": "object",
        "properties": {
            "obligation_id": {"type": "integer"},
            "provider": {"type": "string"},
            "item_name": {"type": "string"},
            "category": {"type": "string"},
            "total_amount": {"type": "number", "minimum": 0},
            "monthly_installment_amount": {"type": "number", "minimum": 0},
            "start_date": {"type": "string", "format": "date"},
            "term_months": {"type": "integer", "minimum": 1},
            "due_day_of_month": {"type": "integer", "minimum": 1, "maximum": 31},
            "status": {"type": "string", "enum": ["active", "completed", "late", "defaulted"]},
        },
        "required": ["obligation_id"],
    }
    requires_confirmation = True

    def execute(self, context: UserContext, db: Session, **kwargs: object) -> ToolResult:
        obligation_id = kwargs.get("obligation_id")
        if obligation_id is None:
            return ToolResult(tool_name=self.name, success=False, error="obligation_id is required.")

        stmt = select(Obligation).where(
            Obligation.id == int(obligation_id),
            Obligation.user_id == context.user_id,
        )
        obligation = db.scalar(stmt)
        if obligation is None:
            return ToolResult(tool_name=self.name, success=False, error="Obligation not found.")

        allowed_fields = {
            "provider", "item_name", "category", "total_amount",
            "monthly_installment_amount", "start_date", "term_months",
            "due_day_of_month", "status",
        }

        for field, value in kwargs.items():
            if field not in allowed_fields or field == "obligation_id":
                continue
            if value is None:
                continue
            if isinstance(value, str):
                value = value.strip()
            setattr(obligation, field, value)

        try:
            db.commit()
            db.refresh(obligation)
        except Exception:  # noqa: BLE001
            db.rollback()
            return ToolResult(tool_name=self.name, success=False, error="Failed to update obligation.")

        return ToolResult(
            tool_name=self.name,
            success=True,
            result={
                "id": obligation.id,
                "provider": obligation.provider,
                "item_name": obligation.item_name,
                "category": obligation.category,
                "total_amount": str(obligation.total_amount),
                "monthly_installment_amount": str(obligation.monthly_installment_amount),
                "start_date": obligation.start_date.isoformat(),
                "term_months": obligation.term_months,
                "due_day_of_month": obligation.due_day_of_month,
                "status": obligation.status,
            },
        )


class DeleteObligationTool:
    name = "delete_obligation"
    description = "Delete an obligation belonging to the authenticated user."
    parameters = {
        "type": "object",
        "properties": {
            "obligation_id": {"type": "integer"},
        },
        "required": ["obligation_id"],
    }
    requires_confirmation = True

    def execute(self, context: UserContext, db: Session, **kwargs: object) -> ToolResult:
        obligation_id = kwargs.get("obligation_id")
        if obligation_id is None:
            return ToolResult(tool_name=self.name, success=False, error="obligation_id is required.")

        stmt = select(Obligation).where(
            Obligation.id == int(obligation_id),
            Obligation.user_id == context.user_id,
        )
        obligation = db.scalar(stmt)
        if obligation is None:
            return ToolResult(tool_name=self.name, success=False, error="Obligation not found.")

        try:
            db.delete(obligation)
            db.commit()
        except Exception:  # noqa: BLE001
            db.rollback()
            return ToolResult(tool_name=self.name, success=False, error="Failed to delete obligation.")

        return ToolResult(tool_name=self.name, success=True, result={"deleted_id": int(obligation_id)})


def build_tool_dispatcher(db: Session) -> ToolDispatcher:
    dispatcher = ToolDispatcher(db=db)
    dispatcher.register(DashboardSummaryTool())
    dispatcher.register(ForecastTool())
    dispatcher.register(AffordabilityTool())
    dispatcher.register(ListObligationsTool())
    dispatcher.register(CreateObligationTool())
    dispatcher.register(UpdateObligationTool())
    dispatcher.register(DeleteObligationTool())
    return dispatcher


def tool_requires_confirmation(tool_name: str) -> bool:
    return tool_name in WRITE_TOOL_NAMES


def confirmation_key(user_id: int, tool_name: str, arguments: dict[str, Any]) -> str:
    raw = f"{user_id}:{tool_name}:{json.dumps(arguments, sort_keys=True)}"
    return hashlib.sha256(raw.encode()).hexdigest()


CONFIRMATION_KEYWORDS = {"yes", "confirm", "do it", "proceed", "go ahead", "sure", "ok", "okay"}


ALL_TOOLS: list[ToolDefinition] = [
    DashboardSummaryTool(),
    ForecastTool(),
    AffordabilityTool(),
    ListObligationsTool(),
    CreateObligationTool(),
    UpdateObligationTool(),
    DeleteObligationTool(),
]

DASHBOARD_SUMMARY_TOOL = DashboardSummaryTool()
FORECAST_TOOL = ForecastTool()
AFFORDABILITY_TOOL = AffordabilityTool()
LIST_OBLIGATIONS_TOOL = ListObligationsTool()
CREATE_OBLIGATION_TOOL = CreateObligationTool()
UPDATE_OBLIGATION_TOOL = UpdateObligationTool()
DELETE_OBLIGATION_TOOL = DeleteObligationTool()
