from fastapi.testclient import TestClient

from app.api.dependencies import get_llm_client
from app.main import app


class FakeLLMClient:
    async def get_chat_completion(self, messages: list[dict[str, str]]) -> str:
        return "Muito bem, jovem treinador! Resposta de teste."


app.dependency_overrides[get_llm_client] = lambda: FakeLLMClient()
client = TestClient(app)


def test_chat_pt_br_returns_response():
    resp = client.post(
        "/chat",
        json={"message": "Qual o melhor time para VGC?", "language": "pt-BR"},
    )
    assert resp.status_code == 200
    assert resp.json() == {"response": "Muito bem, jovem treinador! Resposta de teste."}


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


def test_health_check():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
