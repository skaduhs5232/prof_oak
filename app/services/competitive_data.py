"""Looks up Pokémon mentioned in a message against the Smogon stats synced
into Firestore by smogon_sync, and formats them for injection into the LLM
prompt.

Performance: the full stats set per format is a few hundred small documents,
refreshed at most once a day by the sync job — there's no reason to hit
Firestore on every chat turn. This service loads everything into an
in-process cache once per TTL window (and once per cold start on Vercel),
so a normal request only does regex matching against already-loaded data.
"""

from __future__ import annotations

import re
import time
from typing import Protocol

from starlette.concurrency import run_in_threadpool

from app.services.firestore_client import get_firestore_client

CACHE_TTL_SECONDS = 3600
MAX_MATCHES_PER_MESSAGE = 6
VARIANTS_PER_BASE_NAME = 2


class CompetitiveDataService(Protocol):
    async def find_relevant_stats(self, message: str) -> list[str]: ...


def _format_block(format_name: str, month: str, stats: dict) -> str:
    name = stats.get("name", "?")
    lines = [f"- {name} ({format_name}, dados de {month}): uso {stats.get('usage_percent', 0)}% dos times"]

    abilities = stats.get("abilities") or {}
    if abilities:
        top_ability = max(abilities.items(), key=lambda kv: kv[1])
        lines.append(f"  Habilidade mais comum: {top_ability[0]} ({top_ability[1]}%)")

    items = sorted((stats.get("items") or {}).items(), key=lambda kv: kv[1], reverse=True)[:3]
    if items:
        lines.append("  Itens mais comuns: " + ", ".join(f"{n} ({p}%)" for n, p in items))

    moves = sorted((stats.get("moves") or {}).items(), key=lambda kv: kv[1], reverse=True)[:4]
    if moves:
        lines.append("  Golpes mais comuns: " + ", ".join(f"{n} ({p}%)" for n, p in moves))

    tera_types = sorted((stats.get("tera_types") or {}).items(), key=lambda kv: kv[1], reverse=True)[:2]
    if tera_types:
        lines.append("  Tera Types mais comuns: " + ", ".join(f"{n} ({p}%)" for n, p in tera_types))

    return "\n".join(lines)


class FirestoreCompetitiveDataService:
    def __init__(self, formats: list[str]) -> None:
        self._formats = formats
        self._full_name_patterns: list[tuple[re.Pattern, str, dict]] = []
        self._base_name_patterns: list[tuple[re.Pattern, str, list[tuple[str, dict]]]] = []
        self._month_by_format: dict[str, str] = {}
        self._loaded_at: float = 0.0

    async def find_relevant_stats(self, message: str) -> list[str]:
        await self._ensure_cache()
        lowered = message.lower()
        matched_names: set[str] = set()
        blocks: list[str] = []

        for pattern, format_name, stats in self._full_name_patterns:
            if len(matched_names) >= MAX_MATCHES_PER_MESSAGE:
                break
            name_key = stats["name"].lower()
            if name_key in matched_names or not pattern.search(lowered):
                continue
            matched_names.add(name_key)
            blocks.append(_format_block(format_name, self._month_by_format.get(format_name, "?"), stats))

        for pattern, base_name, variants in self._base_name_patterns:
            if len(matched_names) >= MAX_MATCHES_PER_MESSAGE:
                break
            if not pattern.search(lowered):
                continue
            for format_name, stats in variants[:VARIANTS_PER_BASE_NAME]:
                name_key = stats["name"].lower()
                if name_key in matched_names:
                    continue
                matched_names.add(name_key)
                blocks.append(_format_block(format_name, self._month_by_format.get(format_name, "?"), stats))

        return blocks[:MAX_MATCHES_PER_MESSAGE]

    async def _ensure_cache(self) -> None:
        if self._loaded_at and (time.monotonic() - self._loaded_at) < CACHE_TTL_SECONDS:
            return
        await run_in_threadpool(self._load_cache_sync)
        self._loaded_at = time.monotonic()

    def _load_cache_sync(self) -> None:
        db = get_firestore_client()
        full_name_patterns: list[tuple[re.Pattern, str, dict]] = []
        base_names: dict[str, list[tuple[str, dict]]] = {}
        months: dict[str, str] = {}

        for format_name in self._formats:
            format_ref = db.collection("competitive_stats").document(format_name)
            format_doc = format_ref.get()
            months[format_name] = format_doc.to_dict().get("month", "?") if format_doc.exists else "?"

            for doc in format_ref.collection("pokemon").stream():
                stats = doc.to_dict()
                name = stats.get("name", doc.id)
                full_name_patterns.append((_word_boundary_pattern(name), format_name, stats))
                base = name.split("-")[0]
                base_names.setdefault(base.lower(), []).append((format_name, stats))

        for variants in base_names.values():
            variants.sort(key=lambda item: item[1].get("usage_percent", 0), reverse=True)

        base_name_patterns = [
            (_word_boundary_pattern(base), base, variants) for base, variants in base_names.items()
        ]

        self._full_name_patterns = full_name_patterns
        self._base_name_patterns = base_name_patterns
        self._month_by_format = months


def _word_boundary_pattern(name: str) -> re.Pattern:
    return re.compile(rf"\b{re.escape(name.lower())}\b")
