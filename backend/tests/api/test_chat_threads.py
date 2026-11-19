from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError

from app.config import settings
from app.database.models import MessageRole
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


def test_get_messages_empty_for_owned_thread(
    client: TestClient, store: FakeChatStore
) -> None:
    thread = store.seed_thread(owner_id=CURRENT_USER_ID)
    response = client.get(f"/chat/threads/{thread.id}/messages")
    assert response.status_code == 200
    assert response.json() == []


def test_delete_owned_thread_and_messages(
    client: TestClient, store: FakeChatStore
) -> None:
    thread = store.seed_thread(owner_id=CURRENT_USER_ID)
    store.seed_message(thread_id=thread.id, role=MessageRole.user, text="Delete this")

    response = client.delete(f"/chat/threads/{thread.id}")

    assert response.status_code == 204
    assert thread.id not in store.threads
    assert not [message for message in store.messages if message.thread_id == thread.id]


def test_delete_thread_404_when_missing(client: TestClient) -> None:
    response = client.delete(f"/chat/threads/{uuid4()}")

    assert response.status_code == 404


def test_delete_thread_403_when_owned_by_other_user(
    client: TestClient, store: FakeChatStore
) -> None:
    thread = store.seed_thread(owner_id=OTHER_USER_ID)

    response = client.delete(f"/chat/threads/{thread.id}")

    assert response.status_code == 403
    assert thread.id in store.threads


def _replacement_body(thread_id, message_id, *, role="user"):
    return {
        "threadId": str(thread_id),
        "replaceMessageId": str(message_id),
        "messages": [
            {
                "id": str(message_id),
                "role": role,
                "parts": [{"type": "text", "text": "Edited question"}],
            }
        ],
    }


def test_replace_message_404_when_target_missing(
    client: TestClient, store: FakeChatStore
) -> None:
    thread = store.seed_thread(owner_id=CURRENT_USER_ID)
    response = client.post("/chat/stream", json=_replacement_body(thread.id, uuid4()))
    assert response.status_code == 404


def test_replace_message_404_when_target_belongs_to_another_thread(
    client: TestClient, store: FakeChatStore
) -> None:
    thread = store.seed_thread(owner_id=CURRENT_USER_ID)
    other_thread = store.seed_thread(owner_id=CURRENT_USER_ID)
    target = store.seed_message(
        thread_id=other_thread.id, role=MessageRole.user, text="Original"
    )
    response = client.post("/chat/stream", json=_replacement_body(thread.id, target.id))
    assert response.status_code == 404


def test_replace_message_409_when_target_is_assistant(
    client: TestClient, store: FakeChatStore
) -> None:
    thread = store.seed_thread(owner_id=CURRENT_USER_ID)
    target = store.seed_message(
        thread_id=thread.id, role=MessageRole.assistant, text="Answer"
    )
    response = client.post(
        "/chat/stream", json=_replacement_body(thread.id, target.id, role="user")
    )
    assert response.status_code == 409


def test_replace_message_id_must_match_final_user_message(
    client: TestClient, store: FakeChatStore
) -> None:
    thread = store.seed_thread(owner_id=CURRENT_USER_ID)
    target = store.seed_message(
        thread_id=thread.id, role=MessageRole.user, text="Original"
    )
    body = _replacement_body(thread.id, target.id)
    body["messages"][0]["id"] = str(uuid4())
    response = client.post("/chat/stream", json=body)
    assert response.status_code == 422
