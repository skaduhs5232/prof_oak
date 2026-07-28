"""POST /chat — talk to Professor Carvalho."""

from fastapi import APIRouter, Depends, HTTPException

from app.api.dependencies import get_llm_client
from app.models.chat import ChatRequest, ChatResponse
from app.services.chat_service import get_pokemon_response
from app.services.llm_client import LLMClient, LLMUnavailableError

router = APIRouter(tags=["chat"])


@router.post(
    "/chat",
    response_model=ChatResponse,
    summary="Converse com o Professor Carvalho sobre o universo Pokémon",
)
async def chat(
    request: ChatRequest,
    llm_client: LLMClient = Depends(get_llm_client),
) -> ChatResponse:
    try:
        return await get_pokemon_response(request, llm_client)
    except LLMUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
