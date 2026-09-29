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
    # `create_client`'s key becomes the `apiKey` header, which the Supabase
    # gateway validates against the project's actual anon/service key — a
    # user JWT there is rejected. Use the anon key for `apiKey` and layer the
    # user's JWT onto postgrest's Authorization header so RLS still sees it.
    client = create_client(settings.supabase_url, settings.supabase_anon_key.get_secret_value())
    client.postgrest.auth(access_token)
    return client


async def verify_jwt(access_token: str) -> dict:
    client = get_service_role_client()
    return await asyncio.to_thread(client.auth.get_user, access_token)
