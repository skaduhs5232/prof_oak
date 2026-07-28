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


@lru_cache
def get_settings() -> Settings:
    return Settings()
