from __future__ import annotations

import asyncio

from app.config import settings
from app.retrieval.embeddings import GeminiQueryEmbedder


def test_gemini_query_embedder_uses_configured_model_and_dimensions() -> None:
    calls = []

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {
                "embedding": {"values": [0.0] * settings.gemini_embedding_dimensions}
            }

    class FakeClient:
        async def post(self, url, **kwargs):
            calls.append({"url": url, **kwargs})
            return FakeResponse()

    embedder = GeminiQueryEmbedder(FakeClient())  # type: ignore[arg-type]

    vector = asyncio.run(embedder("net sales"))

    assert len(vector) == settings.gemini_embedding_dimensions
    assert calls[0]["url"].endswith(
        f"/models/{settings.gemini_embedding_model}:embedContent"
    )
    assert calls[0]["json"] == {
        "content": {"parts": [{"text": "net sales"}]},
        "output_dimensionality": settings.gemini_embedding_dimensions,
    }
    assert calls[0]["headers"]["x-goog-api-key"]
