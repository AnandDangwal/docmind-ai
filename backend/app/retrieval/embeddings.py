from __future__ import annotations

import httpx

from app.config import settings

GEMINI_API_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"


class GeminiQueryEmbedder:
    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client

    async def __call__(self, query: str) -> list[float]:
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            response = await client.post(
                f"{GEMINI_API_BASE_URL}/models/"
                f"{settings.gemini_embedding_model}:embedContent",
                headers={"x-goog-api-key": settings.gemini_api_key.get_secret_value()},
                json={
                    "content": {"parts": [{"text": query}]},
                    "output_dimensionality": settings.gemini_embedding_dimensions,
                },
            )
            response.raise_for_status()
            payload = response.json()
        finally:
            if self._client is None:
                await client.aclose()

        values = payload.get("embedding", {}).get("values")
        if not isinstance(values, list) or not all(
            isinstance(value, int | float) for value in values
        ):
            raise ValueError("Gemini embedding response did not contain float values")
        embedding = [float(value) for value in values]
        if len(embedding) != settings.gemini_embedding_dimensions:
            raise ValueError(
                "Expected query embedding dimension "
                f"{settings.gemini_embedding_dimensions}, got {len(embedding)}"
            )
        return embedding
