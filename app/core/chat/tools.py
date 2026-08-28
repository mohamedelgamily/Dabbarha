from __future__ import annotations

from typing import Protocol

from app.core.chat.schemas import ToolDefinition, ToolResult, UserContext


class Tool(Protocol):
    name: str
    description: str
    parameters: dict[str, object]

    def execute(self, context: UserContext, **kwargs: object) -> ToolResult:
        ...


DASHBOARD_SUMMARY_TOOL = ToolDefinition(
    name="dashboard_summary",
    description="Get the authenticated user's dashboard summary including income, fixed expenses, and current month buffer.",
    parameters={"type": "object", "properties": {}},
)

FORECAST_TOOL = ToolDefinition(
    name="forecast",
    description="Get a monthly cash-flow forecast for the authenticated user.",
    parameters={
        "type": "object",
        "properties": {
            "start_month": {"type": "string", "format": "date"},
            "months": {"type": "integer", "minimum": 1, "maximum": 60},
        },
        "required": ["start_month", "months"],
    },
)

AFFORDABILITY_TOOL = ToolDefinition(
    name="affordability",
    description="Evaluate whether the authenticated user can afford a proposed financial commitment.",
    parameters={
        "type": "object",
        "properties": {
            "amount": {"type": "number", "minimum": 0},
            "start_date": {"type": "string", "format": "date"},
            "term_months": {"type": "integer", "minimum": 1},
        },
        "required": ["amount", "start_date", "term_months"],
    },
)

LIST_OBLIGATIONS_TOOL = ToolDefinition(
    name="list_obligations",
    description="List the authenticated user's obligations.",
    parameters={"type": "object", "properties": {}},
)

CREATE_OBLIGATION_TOOL = ToolDefinition(
    name="create_obligation",
    description="Create a new obligation for the authenticated user.",
    parameters={
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
    },
)

UPDATE_OBLIGATION_TOOL = ToolDefinition(
    name="update_obligation",
    description="Update an existing obligation belonging to the authenticated user.",
    parameters={
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
    },
)

DELETE_OBLIGATION_TOOL = ToolDefinition(
    name="delete_obligation",
    description="Delete an obligation belonging to the authenticated user.",
    parameters={
        "type": "object",
        "properties": {
            "obligation_id": {"type": "integer"},
        },
        "required": ["obligation_id"],
    },
)

ALL_TOOLS: list[ToolDefinition] = [
    DASHBOARD_SUMMARY_TOOL,
    FORECAST_TOOL,
    AFFORDABILITY_TOOL,
    LIST_OBLIGATIONS_TOOL,
    CREATE_OBLIGATION_TOOL,
    UPDATE_OBLIGATION_TOOL,
    DELETE_OBLIGATION_TOOL,
]
