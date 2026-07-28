from functools import lru_cache

from app.core.config import get_settings
from app.services.competitive_data import CompetitiveDataService, FirestoreCompetitiveDataService
from app.services.llm_client import LLMClient
from app.services.memory_service import FirestoreMemoryService, MemoryService


@lru_cache
def get_llm_client() -> LLMClient:
    return LLMClient(get_settings())


@lru_cache
def get_memory_service() -> MemoryService:
    return FirestoreMemoryService()


@lru_cache
def get_competitive_data_service() -> CompetitiveDataService:
    return FirestoreCompetitiveDataService(get_settings().competitive_formats_list)
