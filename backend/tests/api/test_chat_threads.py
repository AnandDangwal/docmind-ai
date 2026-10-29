from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError

from app.config import settings
from tests.api.conftest import CURRENT_USER_ID, OTHER_USER_ID
from tests.api.fakes import FakeChatStore


def test_database_failure_returns_readable_error_with_cors(client, monkeypatch):
    async def fail(*args, **kwargs):
        raise SQLAlchemyError("private database details")

    monkeypatch.setattr("app.api.chat.create_thread", fail)
    origin = settings.allowed_origins[0]
    response = client.post(
        "/chat/threads", json={"title": None}, headers={"Origin": origin}
    )
    assert response.status_code == 503
    assert response.headers["access-control-allow-origin"] == origin
    assert response.json() == {
        "detail": "The database request failed. Please try again shortly."
    }
    assert "private database details" not in response.text


def test_create_and_list_threads(client: TestClient) -> None:
    create_response = client.post("/chat/threads", json={"title": "New thread"})
    assert create_response.status_code == 201
    created = create_response.json()
    assert created["title"] == "New thread"

    list_response = client.get("/chat/threads")
    assert list_response.status_code == 200
    threads = list_response.json()
    assert len(threads) == 1
    assert threads[0]["id"] == created["id"]


def test_get_messages_404_when_thread_missing(client: TestClient) -> None:
    response = client.get(f"/chat/threads/{uuid4()}/messages")
    assert response.status_code == 404


def test_get_messages_403_when_thread_owned_by_other_user(
    client: TestClient, store: FakeChatStore
) -> None:
    thread = store.seed_thread(owner_id=OTHER_USER_ID)
    response = client.get(f"/chat/threads/{thread.id}/messages")
    assert response.status_code == 403


def test_get_messages_empty_for_owned_thread(client: TestClient, store: FakeChatStore) -> None:
    thread = store.seed_thread(owner_id=CURRENT_USER_ID)
    response = client.get(f"/chat/threads/{thread.id}/messages")
    assert response.status_code == 200
    assert response.json() == []
