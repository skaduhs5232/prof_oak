"""Thin async wrapper around an OpenAI-compatible chat-completions endpoint.

Using the OpenAI SDK against a configurable base_url (instead of a
provider-specific SDK) lets the same code run against a local Ollama server,
a self-hosted vLLM/LM Studio instance, or an OpenAI-compatible cloud provider
(Groq, Together, Fireworks, ...) hosting the chosen open model — the
local-vs-cloud decision becomes a matter of configuration, not code.
"""

from openai import APIConnectionError, APIStatusError, APITimeoutError, AsyncOpenAI

from app.core.config import Settings


class LLMUnavailableError(RuntimeError):
    """Raised when the underlying LLM endpoint cannot be reached or fails."""


class LLMClient:
    def __init__(self, settings: Settings) -> None:
        self._client = AsyncOpenAI(
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key,
            timeout=settings.request_timeout_seconds,
        )
        self._model = settings.llm_model
        self._temperature = settings.llm_temperature
        self._max_tokens = settings.llm_max_tokens

    async def get_chat_completion(self, messages: list[dict[str, str]]) -> str:
        try:
            completion = await self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                temperature=self._temperature,
                max_tokens=self._max_tokens,
            )
        except (APIConnectionError, APITimeoutError, APIStatusError) as exc:
            raise LLMUnavailableError(
                "Não foi possível falar com o modelo de linguagem no momento."
            ) from exc

        content = completion.choices[0].message.content
        if not content:
            raise LLMUnavailableError("O modelo retornou uma resposta vazia.")
        return content
