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

    session = type("FakeSession", (), {"commit": staticmethod(_noop_commit)})()
    yield session


@pytest.fixture(autouse=True)
def patch_orchestrator(store: FakeChatStore, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(orchestrator_module, "create_message", store.create_message)
    monkeypatch.setattr(orchestrator_module, "AsyncSessionLocal", _fake_session_scope)


def test_stream_422_on_malformed_body(client: TestClient) -> None:
    response = client.post("/chat/stream", json={"messages": "not-a-list"})
    assert response.status_code == 422


def test_stream_404_when_thread_missing(client: TestClient) -> None:
    body: dict[str, Any] = {
        "thread_id": "223e4567-e89b-12d3-a456-426614174099",
        "messages": [],
    }
    response = client.post("/chat/stream", json=body)
    assert response.status_code == 404


def test_stream_403_when_thread_owned_by_other_user(client: TestClient, store: FakeChatStore) -> None:
    thread = store.seed_thread(owner_id=OTHER_USER_ID)
    body: dict[str, Any] = {"thread_id": str(thread.id), "messages": []}
    response = client.post("/chat/stream", json=body)
    assert response.status_code == 403


def test_stream_happy_path(client: TestClient, store: FakeChatStore) -> None:
    thread = store.seed_thread(owner_id=CURRENT_USER_ID)
    body: dict[str, Any] = {
        "thread_id": str(thread.id),
        "messages": [
            {"id": "m1", "role": "user", "parts": [{"type": "text", "text": "hello"}]},
        ],
    }

    response = client.post("/chat/stream", json=body)

    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]
    assert "text-delta" in response.text
    assert "finish" in response.text

    assert len(store.messages) == 2
    assert {m.role for m in store.messages} == {"user", "assistant"}
