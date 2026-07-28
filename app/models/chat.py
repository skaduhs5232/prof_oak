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
    user_id: str | None = Field(
        default=None,
        description=(
            "Identificador do usuário. Omita na primeiríssima chamada — a resposta "
            "devolve um novo user_id, que deve ser reenviado em toda chamada futura "
            "(mesmo em conversas/session_id diferentes) para identificar o mesmo usuário."
        ),
    )
    session_id: str | None = Field(
        default=None,
        description=(
            "Identificador da conversa (chat) atual, para manter memória entre chamadas. "
            "Omita para iniciar uma nova conversa para esse usuário — um usuário pode ter "
            "várias conversas. Reenvie o mesmo session_id para continuar a mesma conversa."
        ),
    )


class ChatResponse(BaseModel):
    response: str = Field(..., description="Resposta do Professor Carvalho, no idioma solicitado.")
    user_id: str = Field(..., description="Reenvie em toda chamada futura para continuar como o mesmo usuário.")
    session_id: str = Field(
        ...,
        description="Identificador desta conversa — reenvie para continuar nela, ou omita para começar outra.",
    )
