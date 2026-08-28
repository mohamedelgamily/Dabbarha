from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.deps import get_current_user, get_db
from app.core.chat.conversation import ConversationRepository
from app.core.chat.guardrails import GuardrailPolicy
from app.core.chat.provider import FallbackLLMProvider, GeminiProvider, GroqProvider, MockLLMProvider
from app.core.chat.schemas import UserContext
from app.core.chat.service import ChatService
from app.core.chat.tools import build_tool_dispatcher
from app.models.user import User
from app.schemas.chat import ChatRequest, ChatResponse

router = APIRouter()


def _get_chat_service(db_session: object) -> ChatService:
    try:
        return ChatService(
            provider=FallbackLLMProvider(
                primary=GeminiProvider(),
                fallback=GroqProvider(),
            ),
            guardrails=GuardrailPolicy(),
            tool_dispatcher=build_tool_dispatcher(db_session),
            conversation_repository=ConversationRepository(db_session),
        )
    except Exception:
        return ChatService(
            provider=MockLLMProvider(),
            guardrails=GuardrailPolicy(),
        )


@router.post(
    "",
    response_model=ChatResponse,
    status_code=status.HTTP_200_OK,
    summary="Chat with Dabbarha financial assistant",
)
def chat(
    request: Request,
    body: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: object = Depends(get_db),
) -> ChatResponse:
    if request.query_params:
        raise HTTPException(
            status_code=422,
            detail="Chat does not accept query parameters",
        )

    chat_service = _get_chat_service(db)
    user_context = UserContext(user_id=current_user.id)
    confirmed_tool_key = request.headers.get("X-Confirmed-Tool-Key")
    result = chat_service.chat(
        user_context=user_context,
        message=body.message,
        conversation_id=body.conversation_id,
        confirmed_tool_key=confirmed_tool_key,
    )
    return ChatResponse(
        response=result.content,
        metadata=result.metadata,
        conversation_id=result.conversation_id or 0,
    )
