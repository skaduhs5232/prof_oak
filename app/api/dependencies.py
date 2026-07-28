"""Shared FastAPI dependencies."""

from functools import lru_cache

from app.core.config import get_settings
from app.services.llm_client import LLMClient


@lru_cache
def get_llm_client() -> LLMClient:
    return LLMClient(get_settings())
