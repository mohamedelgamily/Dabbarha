from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ConversationResponse(BaseModel):
    id: int
    user_id: int
    created_at: datetime
    updated_at: datetime


class ConversationMessageResponse(BaseModel):
    id: int
    conversation_id: int
    role: str
    content: str
    tool_name: str | None
    tool_arguments: dict[str, Any] | None
    tool_result: Any | None
    created_at: datetime