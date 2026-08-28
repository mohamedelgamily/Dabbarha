from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.deps import get_current_user, get_db
from app.core.chat.conversation import ConversationRepository
from app.core.chat.guardrails import GuardrailPolicy
from app.core.chat.provider import FallbackLLMProvider, GeminiProvider, GroqProvider, MockLLMProvider
from app.core.chat.schemas import UserContext
from app.core.chat.service import ChatService
from app.core.chat.tools import build_tool_dispatcher
from app.core.config import (
    RAG_CHUNK_OVERLAP,
    RAG_CHUNK_SIZE,
    RAG_ENABLED,
    RAG_SCORE_THRESHOLD,
    RAG_TOP_K,
)
from app.core.rag.retriever import KnowledgeRetriever
from app.models.user import User
from app.schemas.chat import ChatRequest, ChatResponse

router = APIRouter()

# Cache the KnowledgeRetriever at module level to avoid rebuilding the index
# on every POST /chat request. The retriever is read-only after initialization.
_KNOWLEDGE_RETRIEVER: KnowledgeRetriever | None = None


def _get_knowledge_retriever() -> KnowledgeRetriever | None:
    global _KNOWLEDGE_RETRIEVER
    if not RAG_ENABLED:
        return None
    if _KNOWLEDGE_RETRIEVER is None:
        _KNOWLEDGE_RETRIEVER = KnowledgeRetriever(
            chunk_size=RAG_CHUNK_SIZE,
            chunk_overlap=RAG_CHUNK_OVERLAP,
            top_k=RAG_TOP_K,
        )
    return _KNOWLEDGE_RETRIEVER


def _get_chat_service(db_session: object) -> ChatService:
    knowledge_retriever = _get_knowledge_retriever()

    try:
        primary = GeminiProvider()
    except Exception:
        primary = MockLLMProvider()

    try:
        fallback = GroqProvider()
    except Exception:
        fallback = MockLLMProvider()

    try:
        return ChatService(
            provider=FallbackLLMProvider(
                primary=primary,
                fallback=fallback,
            ),
            guardrails=GuardrailPolicy(),
            tool_dispatcher=build_tool_dispatcher(db_session),
            conversation_repository=ConversationRepository(db_session),
            knowledge_retriever=knowledge_retriever,
            rag_top_k=RAG_TOP_K,
            rag_score_threshold=RAG_SCORE_THRESHOLD,
        )
    except Exception:
        return ChatService(
            provider=MockLLMProvider(),
            guardrails=GuardrailPolicy(),
            knowledge_retriever=knowledge_retriever,
            rag_top_k=RAG_TOP_K,
            rag_score_threshold=RAG_SCORE_THRESHOLD,
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
