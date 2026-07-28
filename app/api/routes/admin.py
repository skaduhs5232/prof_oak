"""Internal endpoint to trigger the Smogon competitive-stats sync.

Meant to be called by a scheduler (Vercel Cron, GitHub Actions, etc.), not by
end users — protected by a shared secret rather than the app's normal auth.
"""

from fastapi import APIRouter, Depends, Header, HTTPException

from app.core.config import Settings, get_settings
from app.services.smogon_sync import sync_formats

router = APIRouter(tags=["admin"])


def get_smogon_syncer():
    """Indirection point so tests can swap in a fake without hitting Smogon/Firestore."""
    return sync_formats


@router.get("/internal/sync-competitive-stats", summary="Atualiza os dados competitivos a partir da Smogon")
async def sync_competitive_stats(
    authorization: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
    syncer=Depends(get_smogon_syncer),
) -> dict:
    if settings.cron_secret:
        expected = f"Bearer {settings.cron_secret}"
        if authorization != expected:
            raise HTTPException(status_code=401, detail="Não autorizado.")

    results = await syncer(settings.competitive_formats_list)
    return {
        "synced": [
            {
                "format": result.format,
                "month": result.month,
                "rating_cutoff": result.rating_cutoff,
                "pokemon_synced": result.pokemon_synced,
            }
            for result in results
        ]
    }
