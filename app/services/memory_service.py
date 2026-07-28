"""Conversation memory, persisted in Firestore under users/{user_id}/chats/{session_id}.

Each user can have many chat sessions (each with its own uuid). A session
document holds the full message history; get_context() only returns the last
MAX_CONTEXT_MESSAGES to keep what's sent to the LLM within token/TPM limits,
while get_full_history() returns everything, for the history endpoint.
"""

from __future__ import annotations

from typing import Any, Protocol

from firebase_admin import firestore
from starlette.concurrency import run_in_threadpool

from app.services.firestore_client import get_firestore_client

CHATS_SUBCOLLECTION = "chats"
MAX_CONTEXT_MESSAGES = 20


class MemoryService(Protocol):
    async def get_context(self, user_id: str, session_id: str) -> list[dict[str, str]]: ...

    async def append_turn(
        self, user_id: str, session_id: str, user_message: str, assistant_message: str
    ) -> None: ...

    async def list_sessions(self, user_id: str) -> list[dict[str, Any]]: ...

    async def get_full_history(self, user_id: str, session_id: str) -> list[dict[str, str]] | None: ...


class FirestoreMemoryService:
    def _chats(self, user_id: str):
        return get_firestore_client().collection("users").document(user_id).collection(CHATS_SUBCOLLECTION)

    async def get_context(self, user_id: str, session_id: str) -> list[dict[str, str]]:
        doc_ref = self._chats(user_id).document(session_id)

        def _read() -> list[dict[str, str]]:
            doc = doc_ref.get()
            if not doc.exists:
                return []
            return doc.to_dict().get("messages", [])[-MAX_CONTEXT_MESSAGES:]

        return await run_in_threadpool(_read)

    async def append_turn(
        self, user_id: str, session_id: str, user_message: str, assistant_message: str
    ) -> None:
        doc_ref = self._chats(user_id).document(session_id)

        def _write() -> None:
            doc = doc_ref.get()
            messages = doc.to_dict().get("messages", []) if doc.exists else []
            messages.append({"role": "user", "content": user_message})
            messages.append({"role": "assistant", "content": assistant_message})
            payload: dict[str, Any] = {"messages": messages, "updated_at": firestore.SERVER_TIMESTAMP}
            if not doc.exists:
                payload["created_at"] = firestore.SERVER_TIMESTAMP
            doc_ref.set(payload, merge=True)

        await run_in_threadpool(_write)

    async def list_sessions(self, user_id: str) -> list[dict[str, Any]]:
        query = self._chats(user_id).order_by("updated_at", direction=firestore.Query.DESCENDING)

        def _read() -> list[dict[str, Any]]:
            summaries = []
            for doc in query.stream():
                data = doc.to_dict()
                messages = data.get("messages", [])
                last_message = next(
                    (m["content"] for m in reversed(messages) if m.get("role") == "user"), None
                )
                summaries.append(
                    {
                        "session_id": doc.id,
                        "created_at": data.get("created_at"),
                        "updated_at": data.get("updated_at"),
                        "last_message": last_message,
                    }
                )
            return summaries

        return await run_in_threadpool(_read)

    async def get_full_history(self, user_id: str, session_id: str) -> list[dict[str, str]] | None:
        doc_ref = self._chats(user_id).document(session_id)

        def _read() -> list[dict[str, str]] | None:
            doc = doc_ref.get()
            return doc.to_dict().get("messages", []) if doc.exists else None

        return await run_in_threadpool(_read)
