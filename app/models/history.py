"""Pydantic contracts for the chat-history endpoints."""

from datetime import datetime

from pydantic import BaseModel, Field


class Message(BaseModel):
    role: str
    content: str


class ChatSessionSummary(BaseModel):
    session_id: str
    created_at: datetime | None = None
    updated_at: datetime | None = None
    last_message: str | None = Field(
        default=None, description="Prévia da última mensagem do usuário nesta conversa."
    )


class ChatHistoryResponse(BaseModel):
    user_id: str
    session_id: str
    messages: list[Message]
