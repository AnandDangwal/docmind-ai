from __future__ import annotations

from collections.abc import Iterator
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

import app.api.chat as chat_api_module
from app.auth.dependencies import CurrentUser, get_current_user
from app.database.session import get_db_session
from app.main import app
from tests.api.fakes import FakeChatStore

CURRENT_USER_ID = UUID("123e4567-e89b-12d3-a456-426614174000")
OTHER_USER_ID = UUID("223e4567-e89b-12d3-a456-426614174001")


async def _fake_db_session() -> object:
    yield object()


@pytest.fixture
def store() -> FakeChatStore:
    return FakeChatStore()


@pytest.fixture
def client(store: FakeChatStore, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setattr(chat_api_module, "create_thread", store.create_thread)
    monkeypatch.setattr(chat_api_module, "list_threads_for_user", store.list_threads_for_user)
    monkeypatch.setattr(chat_api_module, "get_thread", store.get_thread)
    monkeypatch.setattr(chat_api_module, "list_messages_for_thread", store.list_messages_for_thread)

    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        user_id=CURRENT_USER_ID, email="analyst@example.com", access_token="fake-token"
    )
    app.dependency_overrides[get_db_session] = _fake_db_session
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_db_session, None)


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
