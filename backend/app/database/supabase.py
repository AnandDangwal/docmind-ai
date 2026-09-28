from __future__ import annotations

import asyncio

from supabase import Client, create_client

from app.config import settings

_service_role_client: Client | None = None


def get_service_role_client() -> Client:
    global _service_role_client
    if _service_role_client is None:
        _service_role_client = create_client(
            settings.supabase_url,
            settings.supabase_service_role_key.get_secret_value(),
        )
    return _service_role_client


def create_user_client(access_token: str) -> Client:
    return create_client(settings.supabase_url, access_token)


async def verify_jwt(access_token: str) -> dict:
    client = get_service_role_client()
    return await asyncio.to_thread(client.auth.get_user, access_token)
