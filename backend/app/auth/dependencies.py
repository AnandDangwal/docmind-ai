from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.database.supabase import verify_jwt

bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class CurrentUser:
    user_id: UUID
    email: str | None = None
    access_token: str | None = None


def _normalize_user_id(user_id: UUID | str) -> UUID:
    if isinstance(user_id, UUID):
        return user_id
    return UUID(str(user_id))


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> CurrentUser:
    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials

    try:
        user_response = await verify_jwt(token)
    except Exception as exc:  # pragma: no cover - exercised by auth layer / backend runtime
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    user = getattr(user_response, "user", None)
    if user is None or getattr(user, "id", None) is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        user_id = UUID(str(user.id))
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    return CurrentUser(
        user_id=user_id,
        email=getattr(user, "email", None),
        access_token=token,
    )


async def require_same_user(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    owning_user_id: UUID | str,
) -> CurrentUser:
    normalized_owner_id = _normalize_user_id(owning_user_id)
    if current_user.user_id != normalized_owner_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User does not have access to this thread",
        )
    return current_user


async def require_thread_access(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    thread_user_id: UUID | str,
) -> CurrentUser:
    return await require_same_user(current_user, thread_user_id)
