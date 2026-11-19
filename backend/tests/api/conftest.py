from __future__ import annotations

from collections.abc import Iterator
from types import SimpleNamespace
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

import app.api.chat as chat_api_module
from app.assistant.outputs import GroundedAnswer
from app.auth.dependencies import CurrentUser, get_current_user
from app.database.session import get_db_session
from app.main import app
from tests.api.fakes import FakeChatStore

CURRENT_USER_ID = UUID("123e4567-e89b-12d3-a456-426614174000")
OTHER_USER_ID = UUID("223e4567-e89b-12d3-a456-426614174001")


async def _fake_db_session() -> object:
    async def commit():
        pass

    yield SimpleNamespace(commit=commit)


@pytest.fixture
def store() -> FakeChatStore:
    return FakeChatStore()


@pytest.fixture
def client(
    store: FakeChatStore, monkeypatch: pytest.MonkeyPatch
) -> Iterator[TestClient]:
    async def search(*args, **kwargs):
        return []

    async def run(*args, **kwargs):
        return SimpleNamespace(
            response=SimpleNamespace(model_name="test-model"),
            output=GroundedAnswer(
                status="insufficient_evidence",
                answer="Not enough evidence.",
                citations=[],
            )
        )

    monkeypatch.setattr(
        app.state, "document_agent", SimpleNamespace(run=run), raising=False
    )
    monkeypatch.setattr(
        app.state,
        "document_retriever",
        SimpleNamespace(search_filings=search),
        raising=False,
    )
    monkeypatch.setattr(chat_api_module, "create_thread", store.create_thread)
    monkeypatch.setattr(
        chat_api_module, "list_threads_for_user", store.list_threads_for_user
    )
    monkeypatch.setattr(chat_api_module, "get_thread", store.get_thread)
    monkeypatch.setattr(chat_api_module, "delete_thread", store.delete_thread)
    monkeypatch.setattr(chat_api_module, "get_message", store.get_message)
    monkeypatch.setattr(
        chat_api_module, "list_messages_for_thread", store.list_messages_for_thread
    )

    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        user_id=CURRENT_USER_ID, email="analyst@example.com", access_token="fake-token"
    )
    app.dependency_overrides[get_db_session] = _fake_db_session
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_db_session, None)
