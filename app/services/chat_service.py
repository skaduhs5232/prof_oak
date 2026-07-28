import uuid

from app.core.config import Settings
from app.core.personality import build_system_prompt
from app.core.tokens import estimate_tokens
from app.models.chat import ChatRequest, ChatResponse
from app.services.competitive_data import CompetitiveDataService
from app.services.llm_client import LLMClient
from app.services.memory_service import MemoryService


def _fit_history_to_budget(
    history: list[dict[str, str]], other_messages_tokens: int, token_budget: int
) -> list[dict[str, str]]:
    """Drops the oldest turn (a user+assistant pair) at a time until the
    estimated total fits the budget, so a long conversation degrades to
    "less memory" instead of an oversized/rejected request."""
    remaining = token_budget - other_messages_tokens
    trimmed = history
    while trimmed and sum(estimate_tokens(m["content"]) for m in trimmed) > remaining:
        trimmed = trimmed[2:]
    return trimmed


async def get_pokemon_response(
    request: ChatRequest,
    llm_client: LLMClient,
    memory_service: MemoryService,
    competitive_data_service: CompetitiveDataService,
    settings: Settings,
) -> ChatResponse:
    user_id = request.user_id or str(uuid.uuid4())
    session_id = request.session_id or str(uuid.uuid4())
    system_prompt = build_system_prompt(request.language)
    history = await memory_service.get_context(user_id, session_id)

    stats_blocks = await competitive_data_service.find_relevant_stats(request.message)
    stats_message = None
    if stats_blocks:
        stats_message = {
            "role": "system",
            "content": "Dados de uso competitivo atualizados (Smogon):\n\n" + "\n\n".join(stats_blocks),
        }

    other_messages_tokens = (
        estimate_tokens(system_prompt)
        + (estimate_tokens(stats_message["content"]) if stats_message else 0)
        + estimate_tokens(request.message)
        + settings.llm_max_tokens
    )
    history = _fit_history_to_budget(history, other_messages_tokens, settings.llm_context_token_budget)

    messages = [{"role": "system", "content": system_prompt}]
    if stats_message:
        messages.append(stats_message)
    messages.extend(history)
    messages.append({"role": "user", "content": request.message})

    content = (await llm_client.get_chat_completion(messages)).strip()
    await memory_service.append_turn(user_id, session_id, request.message, content)
    return ChatResponse(response=content, user_id=user_id, session_id=session_id)
