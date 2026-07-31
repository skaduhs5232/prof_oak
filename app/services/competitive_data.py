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

# Trigger words that identify a *format/game* mention (as opposed to a specific
# Pokémon species) — used to answer "what's used in <format>" without the
# trainer naming any Pokémon. Kept generic instead of hardcoded to today's
# COMPETITIVE_FORMATS values, so it still works if that env var changes.
_CHAMPIONS_WORDS = ("champions",)
_VGC_WORDS = ("vgc",)
_YEAR_PATTERN = re.compile(r"20\d{2}")
TOP_N_FORMAT_OVERVIEW = 8
MAX_FORMAT_OVERVIEWS_PER_MESSAGE = 2


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


def _format_overview_block(format_name: str, month: str, top_stats: list[dict]) -> str:
    ranked = ", ".join(f"{s['name']} ({s.get('usage_percent', 0)}%)" for s in top_stats)
    return f"- Mais usados em {format_name} ({month}): {ranked}"


def _detect_triggered_formats(lowered_message: str, known_formats: list[str]) -> list[str]:
    """Matches a mention of a *format/game* (not a Pokémon species) against the
    configured formats, e.g. "o que é usado no Pokémon Champions" or "meta do
    vgc 2026" — disambiguating the Champions ladder from the mainline VGC
    ladder by the presence/absence of "champions", and narrowing by year when
    the message mentions one.
    """
    has_champions = any(word in lowered_message for word in _CHAMPIONS_WORDS)
    has_vgc = any(word in lowered_message for word in _VGC_WORDS)
    if not has_champions and not has_vgc:
        return []

    if has_champions:
        candidates = [f for f in known_formats if "champions" in f]
    else:
        non_champions_vgc = [f for f in known_formats if "vgc" in f and "champions" not in f]
        candidates = non_champions_vgc or [f for f in known_formats if "vgc" in f]

    year_match = _YEAR_PATTERN.search(lowered_message)
    if year_match:
        by_year = [f for f in candidates if year_match.group() in f]
        if by_year:
            candidates = by_year

    return candidates


class FirestoreCompetitiveDataService:
    def __init__(self, formats: list[str]) -> None:
        self._formats = formats
        self._full_name_patterns: list[tuple[re.Pattern, str, dict]] = []
        self._base_name_patterns: list[tuple[re.Pattern, str, list[tuple[str, dict]]]] = []
        self._month_by_format: dict[str, str] = {}
        self._top_by_format: dict[str, list[dict]] = {}
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

        triggered_formats = _detect_triggered_formats(lowered, self._formats)
        for format_name in triggered_formats[:MAX_FORMAT_OVERVIEWS_PER_MESSAGE]:
            top_stats = [s for s in self._top_by_format.get(format_name, []) if s["name"].lower() not in matched_names]
            if top_stats:
                blocks.append(_format_overview_block(format_name, self._month_by_format.get(format_name, "?"), top_stats))

        return blocks[: MAX_MATCHES_PER_MESSAGE + MAX_FORMAT_OVERVIEWS_PER_MESSAGE]

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
        top_by_format: dict[str, list[dict]] = {}

        for format_name in self._formats:
            format_ref = db.collection("competitive_stats").document(format_name)
            format_doc = format_ref.get()
            months[format_name] = format_doc.to_dict().get("month", "?") if format_doc.exists else "?"

            format_pokemon: list[dict] = []
            for doc in format_ref.collection("pokemon").stream():
                stats = doc.to_dict()
                name = stats.get("name", doc.id)
                full_name_patterns.append((_word_boundary_pattern(name), format_name, stats))
                base = name.split("-")[0]
                base_names.setdefault(base.lower(), []).append((format_name, stats))
                format_pokemon.append(stats)

            format_pokemon.sort(key=lambda s: s.get("usage_percent", 0), reverse=True)
            top_by_format[format_name] = format_pokemon[:TOP_N_FORMAT_OVERVIEW]

        for variants in base_names.values():
            variants.sort(key=lambda item: item[1].get("usage_percent", 0), reverse=True)

        base_name_patterns = [
            (_word_boundary_pattern(base), base, variants) for base, variants in base_names.items()
        ]

        self._full_name_patterns = full_name_patterns
        self._base_name_patterns = base_name_patterns
        self._month_by_format = months
        self._top_by_format = top_by_format


def _word_boundary_pattern(name: str) -> re.Pattern:
    return re.compile(rf"\b{re.escape(name.lower())}\b")
