"""Application settings, sourced from environment variables / .env file."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Aponta para qualquer endpoint compatível com a API da OpenAI:
    # Ollama local (padrão), vLLM, LM Studio, Groq, Together, Fireworks, etc.
    llm_base_url: str = "http://localhost:11434/v1"
    llm_api_key: str = "ollama"
    llm_model: str = "qwen2.5:7b-instruct"

    llm_temperature: float = 0.8
    llm_max_tokens: int = 1600
    request_timeout_seconds: float = 60.0

    # Total estimated-token budget for ONE request (system prompt + injected
    # competitive stats + conversation history + current message + the
    # reserved llm_max_tokens output) — history is trimmed, oldest turns
    # first, to stay under this. Default leaves a safety margin under the
    # 8000 TPM Groq free-tier ceiling noted in .env.example for
    # qwen/qwen3.6-27b; lower it for stricter tiers, raise it for looser ones.
    llm_context_token_budget: int = 7500

    # Formato de saída para modelos de raciocínio (ex: "hidden" para ocultar o raciocínio).
    llm_reasoning_format: str | None = None

    firebase_credentials_path: str = "./firebase-credentials.json"
    firebase_credentials_json: str | None = None

   
    competitive_formats: str = "gen9ou,gen9vgc2026regi"
   
    cron_secret: str | None = None

    @property
    def competitive_formats_list(self) -> list[str]:
        return [f.strip() for f in self.competitive_formats.split(",") if f.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
