from fastapi.testclient import TestClient

from app.api.routes.admin import get_smogon_syncer
from app.core.config import Settings, get_settings
from app.main import app
from app.services.smogon_sync import FormatSyncResult


class FakeSyncer:
    def __init__(self, results: list[FormatSyncResult]) -> None:
        self.results = results
        self.called_with: list[str] | None = None

    async def __call__(self, formats: list[str]) -> list[FormatSyncResult]:
        self.called_with = formats
        return self.results


FAKE_RESULTS = [FormatSyncResult(format="gen9ou", month="2026-06", rating_cutoff=1825, pokemon_synced=402)]


def _override_settings(cron_secret: str | None) -> None:
    app.dependency_overrides[get_settings] = lambda: Settings(
        competitive_formats="gen9ou,gen9vgc2026regi", cron_secret=cron_secret
    )


client = TestClient(app)


def test_sync_without_secret_configured_runs_unauthenticated():
    _override_settings(cron_secret=None)
    fake_syncer = FakeSyncer(FAKE_RESULTS)
    app.dependency_overrides[get_smogon_syncer] = lambda: fake_syncer

    resp = client.get("/internal/sync-competitive-stats")

    assert resp.status_code == 200
    assert resp.json() == {
        "synced": [
            {"format": "gen9ou", "month": "2026-06", "rating_cutoff": 1825, "pokemon_synced": 402}
        ]
    }
    assert fake_syncer.called_with == ["gen9ou", "gen9vgc2026regi"]

    app.dependency_overrides.pop(get_settings, None)
    app.dependency_overrides.pop(get_smogon_syncer, None)


def test_sync_with_secret_configured_rejects_missing_or_wrong_header():
    _override_settings(cron_secret="the-real-secret")
    app.dependency_overrides[get_smogon_syncer] = lambda: FakeSyncer(FAKE_RESULTS)

    no_header = client.get("/internal/sync-competitive-stats")
    wrong_header = client.get(
        "/internal/sync-competitive-stats", headers={"Authorization": "Bearer wrong"}
    )

    assert no_header.status_code == 401
    assert wrong_header.status_code == 401

    app.dependency_overrides.pop(get_settings, None)
    app.dependency_overrides.pop(get_smogon_syncer, None)


def test_sync_with_secret_configured_accepts_matching_header():
    _override_settings(cron_secret="the-real-secret")
    fake_syncer = FakeSyncer(FAKE_RESULTS)
    app.dependency_overrides[get_smogon_syncer] = lambda: fake_syncer

    resp = client.get(
        "/internal/sync-competitive-stats", headers={"Authorization": "Bearer the-real-secret"}
    )

    assert resp.status_code == 200
    assert fake_syncer.called_with == ["gen9ou", "gen9vgc2026regi"]

    app.dependency_overrides.pop(get_settings, None)
    app.dependency_overrides.pop(get_smogon_syncer, None)
