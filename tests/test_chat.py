from fastapi.testclient import TestClient

from app.api.dependencies import get_competitive_data_service, get_llm_client, get_memory_service
from app.core.config import Settings, get_settings
from app.main import app
from app.services.chat_service import _fit_history_to_budget


class FakeLLMClient:
    def __init__(self) -> None:
        self.last_messages: list[dict[str, str]] | None = None

    async def get_chat_completion(self, messages: list[dict[str, str]]) -> str:
        self.last_messages = messages
        return "Muito bem, jovem treinador! Resposta de teste."


class FakeCompetitiveDataService:
    """Stand-in for FirestoreCompetitiveDataService — no real Firebase in tests."""

    def __init__(self) -> None:
        self.blocks: list[str] = []

    async def find_relevant_stats(self, message: str) -> list[str]:
        return self.blocks


class FakeMemoryService:
    """In-memory stand-in for FirestoreMemoryService — no real Firebase in tests."""

    def __init__(self) -> None:
        self.histories: dict[tuple[str, str], list[dict[str, str]]] = {}

    async def get_context(self, user_id: str, session_id: str) -> list[dict[str, str]]:
        return self.histories.get((user_id, session_id), [])

    async def append_turn(
        self, user_id: str, session_id: str, user_message: str, assistant_message: str
    ) -> None:
        history = self.histories.setdefault((user_id, session_id), [])
        history.append({"role": "user", "content": user_message})
        history.append({"role": "assistant", "content": assistant_message})

    async def list_sessions(self, user_id: str) -> list[dict]:
        return [
            {"session_id": sid, "created_at": None, "updated_at": None, "last_message": None}
            for (uid, sid) in self.histories
            if uid == user_id
        ]

    async def get_full_history(self, user_id: str, session_id: str) -> list[dict[str, str]] | None:
        return self.histories.get((user_id, session_id))


_fake_llm_client = FakeLLMClient()
_fake_memory_service = FakeMemoryService()
_fake_competitive_data_service = FakeCompetitiveDataService()
app.dependency_overrides[get_llm_client] = lambda: _fake_llm_client
app.dependency_overrides[get_memory_service] = lambda: _fake_memory_service
app.dependency_overrides[get_competitive_data_service] = lambda: _fake_competitive_data_service
client = TestClient(app)


def test_chat_pt_br_returns_response():
    resp = client.post(
        "/chat",
        json={"message": "Qual o melhor time para VGC?", "language": "pt-BR"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["response"] == "Muito bem, jovem treinador! Resposta de teste."
    assert body["session_id"]


def test_chat_en_returns_response():
    resp = client.post(
        "/chat",
        json={"message": "Can you help me improve my VGC team?", "language": "en"},
    )
    assert resp.status_code == 200
    assert "response" in resp.json()


def test_chat_unsupported_language_returns_422_with_supported_list():
    resp = client.post("/chat", json={"message": "Bonjour", "language": "fr"})
    assert resp.status_code == 422
    body = resp.json()
    assert body["supported_languages"] == ["pt-BR", "en"]


def test_chat_missing_message_returns_422():
    resp = client.post("/chat", json={"language": "en"})
    assert resp.status_code == 422


def test_chat_missing_language_returns_generic_422():
    resp = client.post("/chat", json={"message": "Oi"})
    assert resp.status_code == 422
    # Missing field is a different failure than an unsupported language value —
    # it must not be reported as "unsupported language".
    assert "supported_languages" not in resp.json()


def test_chat_reuses_user_and_session_id_and_keeps_history():
    first = client.post(
        "/chat",
        json={"message": "Meu time tem Garchomp.", "language": "pt-BR"},
    )
    user_id = first.json()["user_id"]
    session_id = first.json()["session_id"]

    second = client.post(
        "/chat",
        json={
            "message": "E o que mais?",
            "language": "pt-BR",
            "user_id": user_id,
            "session_id": session_id,
        },
    )
    assert second.status_code == 200
    assert second.json()["user_id"] == user_id
    assert second.json()["session_id"] == session_id
    assert _fake_memory_service.histories[(user_id, session_id)] == [
        {"role": "user", "content": "Meu time tem Garchomp."},
        {"role": "assistant", "content": "Muito bem, jovem treinador! Resposta de teste."},
        {"role": "user", "content": "E o que mais?"},
        {"role": "assistant", "content": "Muito bem, jovem treinador! Resposta de teste."},
    ]


def test_chat_same_user_different_session_id_starts_a_new_chat():
    first = client.post("/chat", json={"message": "Oi", "language": "pt-BR"})
    user_id = first.json()["user_id"]

    second = client.post("/chat", json={"message": "Outra conversa", "language": "pt-BR", "user_id": user_id})
    assert second.json()["user_id"] == user_id
    assert second.json()["session_id"] != first.json()["session_id"]


def test_list_chats_returns_sessions_for_that_user():
    first = client.post("/chat", json={"message": "Primeira conversa", "language": "pt-BR"})
    user_id = first.json()["user_id"]
    session_id = first.json()["session_id"]

    resp = client.get(f"/users/{user_id}/chats")
    assert resp.status_code == 200
    session_ids = [session["session_id"] for session in resp.json()]
    assert session_id in session_ids


def test_get_chat_history_returns_full_message_list():
    first = client.post("/chat", json={"message": "Meu time tem Garchomp.", "language": "pt-BR"})
    user_id = first.json()["user_id"]
    session_id = first.json()["session_id"]

    resp = client.get(f"/users/{user_id}/chats/{session_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["user_id"] == user_id
    assert body["session_id"] == session_id
    assert body["messages"] == [
        {"role": "user", "content": "Meu time tem Garchomp."},
        {"role": "assistant", "content": "Muito bem, jovem treinador! Resposta de teste."},
    ]


def test_get_chat_history_returns_404_for_unknown_session():
    resp = client.get("/users/no-such-user/chats/no-such-session")
    assert resp.status_code == 404


def test_chat_injects_competitive_stats_when_available():
    _fake_competitive_data_service.blocks = ["- Garchomp (gen9ou, dados de 2026-06): uso 5.1% dos times"]
    try:
        resp = client.post("/chat", json={"message": "Fale do meu Garchomp", "language": "pt-BR"})
        assert resp.status_code == 200
        system_messages = [m["content"] for m in _fake_llm_client.last_messages if m["role"] == "system"]
        assert any("Garchomp" in content for content in system_messages)
    finally:
        _fake_competitive_data_service.blocks = []


def test_chat_skips_stats_message_when_no_matches():
    _fake_competitive_data_service.blocks = []
    resp = client.post("/chat", json={"message": "Oi", "language": "pt-BR"})
    assert resp.status_code == 200
    roles = [m["role"] for m in _fake_llm_client.last_messages]
    assert roles.count("system") == 1


def test_fit_history_to_budget_drops_oldest_turns_first():
    history = [
        {"role": "user", "content": "a" * 400},  # ~100 estimated tokens
        {"role": "assistant", "content": "b" * 400},
        {"role": "user", "content": "c" * 400},
        {"role": "assistant", "content": "d" * 400},
    ]
    trimmed = _fit_history_to_budget(history, other_messages_tokens=0, token_budget=250)
    assert trimmed == history[-2:]


def test_fit_history_to_budget_keeps_everything_when_it_fits():
    history = [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}]
    trimmed = _fit_history_to_budget(history, other_messages_tokens=0, token_budget=1000)
    assert trimmed == history


def test_fit_history_to_budget_drops_everything_when_budget_already_exhausted():
    history = [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}]
    trimmed = _fit_history_to_budget(history, other_messages_tokens=5000, token_budget=100)
    assert trimmed == []


def test_chat_trims_old_history_to_stay_under_the_token_budget():
    user_id, session_id = "budget-test-user", "budget-test-session"
    long_turn_count = 10
    _fake_memory_service.histories[(user_id, session_id)] = [
        message
        for turn in range(long_turn_count)
        for message in (
            {"role": "user", "content": f"Pergunta longa numero {turn}: " + "x" * 300},
            {"role": "assistant", "content": f"Resposta longa numero {turn}: " + "y" * 300},
        )
    ]

    app.dependency_overrides[get_settings] = lambda: Settings(llm_max_tokens=100, llm_context_token_budget=2000)
    try:
        resp = client.post(
            "/chat",
            json={"message": "E agora?", "language": "pt-BR", "user_id": user_id, "session_id": session_id},
        )
        assert resp.status_code == 200
        sent_history = [m for m in _fake_llm_client.last_messages if m["role"] != "system"][:-1]
        assert 0 < len(sent_history) < long_turn_count * 2
        assert sent_history[-1]["content"] == f"Resposta longa numero {long_turn_count - 1}: " + "y" * 300
        assert sent_history[0]["content"] != "Pergunta longa numero 0: " + "x" * 300
    finally:
        app.dependency_overrides.pop(get_settings, None)
        del _fake_memory_service.histories[(user_id, session_id)]


def test_health_check():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
