from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

import pytest
from fastapi.testclient import TestClient

import app.chat.orchestrator as orchestrator_module
from tests.api.conftest import CURRENT_USER_ID, OTHER_USER_ID
from tests.api.fakes import FakeChatStore


@asynccontextmanager
async def _fake_session_scope():
    async def _noop_commit() -> None:
        return None

    @asynccontextmanager
    async def begin():
        yield

    session = type(
        "FakeSession",
        (),
        {"commit": staticmethod(_noop_commit), "begin": staticmethod(begin)},
    )()
    yield session


@pytest.fixture(autouse=True)
def patch_orchestrator(store: FakeChatStore, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(orchestrator_module, "create_message", store.create_message)
    monkeypatch.setattr(
        orchestrator_module, "list_messages_for_thread", store.list_messages_for_thread
    )

    async def no_citations(*args, **kwargs):
        pass

    monkeypatch.setattr(orchestrator_module, "create_citations", no_citations)
    monkeypatch.setattr(orchestrator_module, "AsyncSessionLocal", _fake_session_scope)


def test_stream_422_on_malformed_body(client: TestClient) -> None:
    response = client.post("/chat/stream", json={"messages": "not-a-list"})
    assert response.status_code == 422


def test_stream_404_when_thread_missing(client: TestClient) -> None:
    body: dict[str, Any] = {
        "threadId": "223e4567-e89b-12d3-a456-426614174099",
        "messages": [
            {"id": "m1", "role": "user", "parts": [{"type": "text", "text": "hello"}]}
        ],
    }
    response = client.post("/chat/stream", json=body)
    assert response.status_code == 404


def test_stream_403_when_thread_owned_by_other_user(
    client: TestClient, store: FakeChatStore
) -> None:
    thread = store.seed_thread(owner_id=OTHER_USER_ID)
    body: dict[str, Any] = {
        "threadId": str(thread.id),
        "messages": [
            {"id": "m1", "role": "user", "parts": [{"type": "text", "text": "hello"}]}
        ],
    }
    response = client.post("/chat/stream", json=body)
    assert response.status_code == 403


def test_stream_happy_path(client: TestClient, store: FakeChatStore) -> None:
    thread = store.seed_thread(owner_id=CURRENT_USER_ID)
    body: dict[str, Any] = {
        "threadId": str(thread.id),
        "messages": [
            {"id": "m1", "role": "user", "parts": [{"type": "text", "text": "hello"}]},
        ],
    }

    response = client.post("/chat/stream", json=body)

    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]
    assert '"type": "data-status"' in response.text
    assert '"type": "data-answer-status"' in response.text
    assert "text-delta" in response.text
    assert "finish" in response.text

    assert len(store.messages) == 2
    assert {m.role for m in store.messages} == {"user", "assistant"}


def test_stream_returns_controlled_failure_without_answer(
    client: TestClient, store: FakeChatStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.grounding.validator import GroundingError
    from app.main import app

    async def invalid(*args, **kwargs):
        raise GroundingError("untrusted citation")

    monkeypatch.setattr(app.state.document_agent, "run", invalid)
    thread = store.seed_thread(owner_id=CURRENT_USER_ID)
    response = client.post(
        "/chat/stream",
        json={
            "threadId": str(thread.id),
            "messages": [
                {
                    "id": "u",
                    "role": "user",
                    "parts": [{"type": "text", "text": "Sales?"}],
                }
            ],
        },
    )
    assert response.status_code == 200
    assert '"type": "error"' in response.text
    assert "could not be verified" in response.text
    assert "text-delta" not in response.text
    assert len(store.messages) == 1
    assert store.messages[0].role == "user"
