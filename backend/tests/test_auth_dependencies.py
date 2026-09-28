from __future__ import annotations

import asyncio
from uuid import UUID

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from app.auth.dependencies import CurrentUser, get_current_user, require_same_user


def test_get_current_user_accepts_valid_token(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeUser:
        id = "123e4567-e89b-12d3-a456-426614174000"
        email = "analyst@example.com"

    class FakeResponse:
        user = FakeUser()

    async def fake_verify_jwt(_token: str) -> FakeResponse:
        return FakeResponse()

    monkeypatch.setattr("app.auth.dependencies.verify_jwt", fake_verify_jwt)

    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="valid-token")
    current_user = asyncio.run(get_current_user(credentials))

    assert current_user.user_id == UUID("123e4567-e89b-12d3-a456-426614174000")
    assert current_user.email == "analyst@example.com"


def test_get_current_user_rejects_missing_token() -> None:
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(get_current_user(None))

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Missing bearer token"


def test_require_same_user_rejects_other_user() -> None:
    current_user = CurrentUser(user_id=UUID("123e4567-e89b-12d3-a456-426614174000"))
    other_user_id = UUID("223e4567-e89b-12d3-a456-426614174001")

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(require_same_user(current_user, other_user_id))

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "User does not have access to this thread"
