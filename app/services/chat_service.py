"""Business logic for a single chat turn with Professor Carvalho."""

from app.core.personality import build_system_prompt
from app.models.chat import ChatRequest, ChatResponse
from app.services.llm_client import LLMClient


async def get_pokemon_response(request: ChatRequest, llm_client: LLMClient) -> ChatResponse:
    system_prompt = build_system_prompt(request.language)
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": request.message},
    ]
    content = await llm_client.get_chat_completion(messages)
    return ChatResponse(response=content.strip())
