"""GET endpoints to list a user's chats and load a single chat's history."""

from fastapi import APIRouter, Depends, HTTPException

from app.api.dependencies import get_memory_service
from app.models.history import ChatHistoryResponse, ChatSessionSummary, Message
from app.services.memory_service import MemoryService

router = APIRouter(tags=["history"])


@router.get(
    "/users/{user_id}/chats",
    response_model=list[ChatSessionSummary],
    summary="Lista as conversas (chats) de um usuário",
)
async def list_chats(
    user_id: str,
    memory_service: MemoryService = Depends(get_memory_service),
) -> list[ChatSessionSummary]:
    sessions = await memory_service.list_sessions(user_id)
    return [ChatSessionSummary(**session) for session in sessions]


@router.get(
    "/users/{user_id}/chats/{session_id}",
    response_model=ChatHistoryResponse,
    summary="Carrega o histórico completo de uma conversa",
)
async def get_chat_history(
    user_id: str,
    session_id: str,
    memory_service: MemoryService = Depends(get_memory_service),
) -> ChatHistoryResponse:
    messages = await memory_service.get_full_history(user_id, session_id)
    if messages is None:
        raise HTTPException(status_code=404, detail="Conversa não encontrada.")
    return ChatHistoryResponse(
        user_id=user_id,
        session_id=session_id,
        messages=[Message(**message) for message in messages],
    )
