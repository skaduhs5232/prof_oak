"""Pydantic contracts for the /chat endpoint."""

from enum import Enum

from pydantic import BaseModel, Field


class SupportedLanguage(str, Enum):
    """Languages the assistant is allowed to answer in."""

    PT_BR = "pt-BR"
    EN = "en"


class ChatRequest(BaseModel):
    message: str = Field(
        ...,
        min_length=1,
        max_length=4000,
        description="Mensagem do treinador para o Professor Carvalho.",
        examples=["Meu time é Charizard, Rotom-Wash, Garchomp, Ferrothorn, Dragapult e Clefable. O que posso melhorar?"],
    )
    language: SupportedLanguage = Field(
        ...,
        description="Idioma da resposta. Controla exclusivamente o idioma de saída, independente do idioma da mensagem.",
    )


class ChatResponse(BaseModel):
    response: str = Field(..., description="Resposta do Professor Carvalho, no idioma solicitado.")
