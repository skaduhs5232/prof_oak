from fastapi import APIRouter, Depends, HTTPException

from app.api.dependencies import get_competitive_data_service, get_llm_client, get_memory_service
from app.core.config import Settings, get_settings
from app.models.chat import ChatRequest, ChatResponse
from app.services.chat_service import get_pokemon_response
from app.services.competitive_data import CompetitiveDataService
from app.services.llm_client import LLMClient, LLMUnavailableError
from app.services.memory_service import MemoryService

router = APIRouter(tags=["chat"])


@router.post(
    "/chat",
    response_model=ChatResponse,
    summary="Converse com o Professor Carvalho sobre o universo Pokémon",
)
async def chat(
    request: ChatRequest,
    llm_client: LLMClient = Depends(get_llm_client),
    memory_service: MemoryService = Depends(get_memory_service),
    competitive_data_service: CompetitiveDataService = Depends(get_competitive_data_service),
    settings: Settings = Depends(get_settings),
) -> ChatResponse:
    try:
        return await get_pokemon_response(
            request, llm_client, memory_service, competitive_data_service, settings
        )
    except LLMUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
