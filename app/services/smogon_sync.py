"""Sync Smogon usage-stats dumps into Firestore.

Source: https://www.smogon.com/stats/{month}/chaos/{format}-{rating}.json —
Smogon's official monthly usage stats, published as machine-readable JSON.
There's no API; downloading these static files is the documented, intended
way to consume this data (no scraping/ToS concerns).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import httpx
from firebase_admin import firestore
from starlette.concurrency import run_in_threadpool

from app.services.firestore_client import get_firestore_client

STATS_BASE_URL = "https://www.smogon.com/stats"

# Smogon publishes several rating cutoffs per format (higher = stronger
# ladder). Try the highest first; not every format/month has every cutoff.
RATING_CUTOFFS_TO_TRY = (1825, 1760, 1695, 1630, 1500, 0)
MONTHS_TO_TRY = 3

# How many entries to keep per category — the raw files list every option
# ever used, most with negligible usage.
TOP_N = {"abilities": 5, "items": 8, "moves": 15, "teammates": 8, "spreads": 5, "tera_types": 5}

FIRESTORE_BATCH_LIMIT = 400  # Firestore caps a batch at 500 writes; stay under it.


@dataclass
class FormatSyncResult:
    format: str
    month: str
    rating_cutoff: int
    pokemon_synced: int


def _previous_months(count: int) -> list[str]:
    today = date.today()
    year, month = today.year, today.month
    months = []
    for _ in range(count):
        months.append(f"{year:04d}-{month:02d}")
        month -= 1
        if month == 0:
            month, year = 12, year - 1
    return months


async def _fetch_latest_chaos_json(
    client: httpx.AsyncClient, format_name: str
) -> tuple[dict, str, int] | None:
    for month in _previous_months(MONTHS_TO_TRY):
        for rating in RATING_CUTOFFS_TO_TRY:
            url = f"{STATS_BASE_URL}/{month}/chaos/{format_name}-{rating}.json"
            resp = await client.get(url)
            if resp.status_code == 200:
                return resp.json(), month, rating
    return None


def _top_percentages(raw_counts: dict[str, float], weighted_total: float, top_n: int) -> dict[str, float]:
    if not weighted_total:
        return {}
    # Some Smogon dumps include an empty-string key (e.g. an unset move slot);
    # Firestore map fields reject empty keys, so drop it.
    named_counts = {name: count for name, count in raw_counts.items() if name}
    ranked = sorted(named_counts.items(), key=lambda item: item[1], reverse=True)[:top_n]
    return {name: round(count / weighted_total * 100, 2) for name, count in ranked}


def _weighted_total(stats: dict) -> float:
    # "Raw count" is an unweighted sample size and NOT the right denominator once
    # a rating cutoff is applied — Abilities/Items/Spreads are each exactly one
    # per team, so their (rating-weighted) sums equal this Pokémon's true
    # weighted appearance count, which every other category's percentage
    # should be computed against.
    for category in ("Abilities", "Items", "Spreads"):
        values = stats.get(category, {})
        if values:
            return sum(values.values())
    return 0.0


def _build_pokemon_doc(name: str, stats: dict) -> dict:
    weighted_total = _weighted_total(stats)
    return {
        "name": name,
        "usage_percent": round(stats.get("usage", 0) * 100, 2),
        "raw_count": stats.get("Raw count", 0),
        "abilities": _top_percentages(stats.get("Abilities", {}), weighted_total, TOP_N["abilities"]),
        "items": _top_percentages(stats.get("Items", {}), weighted_total, TOP_N["items"]),
        "moves": _top_percentages(stats.get("Moves", {}), weighted_total, TOP_N["moves"]),
        "teammates": _top_percentages(stats.get("Teammates", {}), weighted_total, TOP_N["teammates"]),
        "spreads": _top_percentages(stats.get("Spreads", {}), weighted_total, TOP_N["spreads"]),
        "tera_types": _top_percentages(stats.get("Tera Types", {}), weighted_total, TOP_N["tera_types"]),
    }


def _safe_doc_id(name: str) -> str:
    return name.replace("/", "_")


async def sync_format(format_name: str) -> FormatSyncResult:
    async with httpx.AsyncClient(timeout=30.0) as client:
        result = await _fetch_latest_chaos_json(client, format_name)
    if result is None:
        raise RuntimeError(
            f"Não encontrei stats da Smogon para o formato '{format_name}' "
            f"nos últimos {MONTHS_TO_TRY} meses."
        )
    payload, month, rating = result
    pokemon_data: dict[str, dict] = payload.get("data", {})

    def _write() -> int:
        db = get_firestore_client()
        format_ref = db.collection("competitive_stats").document(format_name)
        pokemon_collection = format_ref.collection("pokemon")

        entries = [(name, stats) for name, stats in pokemon_data.items() if name != "empty"]
        synced = 0
        for i in range(0, len(entries), FIRESTORE_BATCH_LIMIT):
            batch = db.batch()
            for name, stats in entries[i : i + FIRESTORE_BATCH_LIMIT]:
                batch.set(pokemon_collection.document(_safe_doc_id(name)), _build_pokemon_doc(name, stats))
            batch.commit()
            synced += len(entries[i : i + FIRESTORE_BATCH_LIMIT])

        format_ref.set(
            {
                "month": month,
                "rating_cutoff": rating,
                "pokemon_count": synced,
                "synced_at": firestore.SERVER_TIMESTAMP,
            }
        )
        return synced

    pokemon_synced = await run_in_threadpool(_write)
    return FormatSyncResult(format=format_name, month=month, rating_cutoff=rating, pokemon_synced=pokemon_synced)


async def sync_formats(formats: list[str]) -> list[FormatSyncResult]:
    return [await sync_format(format_name) for format_name in formats]
