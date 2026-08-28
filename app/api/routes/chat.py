from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.deps import get_current_user
from app.core.chat.guardrails import GuardrailPolicy
from app.core.chat.provider import MockLLMProvider
from app.core.chat.schemas import UserContext
from app.core.chat.service import ChatService
from app.models.user import User
from app.schemas.chat import ChatRequest, ChatResponse

router = APIRouter()

_chat_service = ChatService(
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
) -> ChatResponse:
    if request.query_params:
        raise HTTPException(
            status_code=422,
            detail="Chat does not accept query parameters",
        )

    user_context = UserContext(user_id=current_user.id)
    result = _chat_service.chat(user_context=user_context, message=body.message)
    return ChatResponse(response=result.content, metadata=result.metadata)
