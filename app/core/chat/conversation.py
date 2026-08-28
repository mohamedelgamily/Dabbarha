from __future__ import annotations

import json
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.conversation import Conversation, ConversationMessage

if TYPE_CHECKING:
    from app.models.user import User


class ConversationRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_or_create_conversation(
        self,
        user_id: int,
        conversation_id: int | None = None,
    ) -> Conversation:
        if conversation_id is not None:
            conversation = self.db.scalar(
                select(Conversation).where(
                    Conversation.id == conversation_id,
                    Conversation.user_id == user_id,
                )
            )
            if conversation is None:
                raise ValueError("Conversation not found")
            return conversation

        conversation = Conversation(user_id=user_id)
        self.db.add(conversation)
        self.db.commit()
        self.db.refresh(conversation)
        return conversation

    def get_messages(
        self,
        conversation_id: int,
        limit: int = 20,
    ) -> list[ConversationMessage]:
        stmt = (
            select(ConversationMessage)
            .where(ConversationMessage.conversation_id == conversation_id)
            .order_by(ConversationMessage.created_at.desc())
            .limit(limit)
        )
        return list(reversed(self.db.scalars(stmt).all()))

    def add_message(
        self,
        conversation_id: int,
        role: str,
        content: str,
        tool_name: str | None = None,
        tool_arguments: dict[str, object] | None = None,
        tool_result: object | None = None,
    ) -> ConversationMessage:
        message = ConversationMessage(
            conversation_id=conversation_id,
            role=role,
            content=content,
            tool_name=tool_name,
            tool_arguments=json.dumps(tool_arguments) if tool_arguments is not None else None,
            tool_result=json.dumps(tool_result) if tool_result is not None else None,
        )
        self.db.add(message)
        self.db.commit()
        self.db.refresh(message)
        return message