"""Gemini embedding generation for document chunks."""

from __future__ import annotations

import re
import time
from collections.abc import Iterator

import httpx
import tiktoken

from app.config import settings

EMBED_BATCH_SIZE = 50
EMBED_MAX_INPUT_TOKENS = 8_192
EMBED_MAX_REQUEST_TOKENS = 300_000
GEMINI_API_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
MAX_RATE_LIMIT_ATTEMPTS = 5


def _client() -> httpx.Client:
    return httpx.Client(
        headers={"x-goog-api-key": settings.gemini_api_key.get_secret_value()},
        timeout=90,
    )


def _count_tokens(text: str) -> int:
    encoding = tiktoken.get_encoding("cl100k_base")
    return len(
        encoding.encode(
            text=text,
            allowed_special=set(),
            disallowed_special=(),
        )
    )


def _validated_inputs(texts: list[str]) -> list[tuple[str, int]]:
    validated: list[tuple[str, int]] = []
    for index, text in enumerate(texts):
        if not text.strip():
            raise ValueError(f"Embedding input {index} is empty")
        token_count = _count_tokens(text)
        if token_count > EMBED_MAX_INPUT_TOKENS:
            raise ValueError(
                f"Embedding input {index} has {token_count} tokens; "
                f"limit is {EMBED_MAX_INPUT_TOKENS}"
            )
        validated.append((text, token_count))
    return validated


def _iter_batches(
    inputs: list[tuple[str, int]],
    *,
    batch_size: int,
) -> Iterator[list[str]]:
    batch: list[str] = []
    batch_tokens = 0
    for text, token_count in inputs:
        if batch and (
            len(batch) >= batch_size
            or batch_tokens + token_count > EMBED_MAX_REQUEST_TOKENS
        ):
            yield batch
            batch = []
            batch_tokens = 0
        batch.append(text)
        batch_tokens += token_count

    if batch:
        yield batch


def _embed_batch(client: httpx.Client, texts: list[str]) -> list[list[float]]:
    model = settings.gemini_embedding_model
    dimensions = settings.gemini_embedding_dimensions
    url = f"{GEMINI_API_BASE_URL}/models/{model}:batchEmbedContents"
    body = {
        "requests": [
            {
                "model": f"models/{model}",
                "content": {"parts": [{"text": text}]},
                "output_dimensionality": dimensions,
            }
            for text in texts
        ]
    }
    for attempt in range(MAX_RATE_LIMIT_ATTEMPTS):
        response = client.post(url, json=body)
        if response.status_code != 429:
            response.raise_for_status()
            break
        if "per day limit exceeded" in response.text.lower():
            raise RuntimeError(
                "Gemini daily embedding quota is exhausted; resume ingestion "
                "after the project's daily quota resets"
            )
        if attempt == MAX_RATE_LIMIT_ATTEMPTS - 1:
            response.raise_for_status()
        match = re.search(
            r'(?:retry in |"retryDelay"\s*:\s*")([0-9.]+)s',
            response.text,
            re.IGNORECASE,
        )
        delay = min(float(match.group(1)) + 1 if match else 10, 60)
        time.sleep(delay)

    payload = response.json()
    embeddings = payload.get("embeddings")
    if not isinstance(embeddings, list) or len(embeddings) != len(texts):
        raise ValueError("Gemini embedding count does not match the request")

    vectors: list[list[float]] = []
    for item in embeddings:
        values = item.get("values") if isinstance(item, dict) else None
        if not isinstance(values, list) or not all(
            isinstance(value, int | float) for value in values
        ):
            raise ValueError("Gemini embedding response did not contain float values")
        vector = [float(value) for value in values]
        if len(vector) != dimensions:
            raise ValueError(
                f"Expected embedding dimension {dimensions}, got {len(vector)}"
            )
        vectors.append(vector)
    return vectors


def embed_texts(
    texts: list[str],
    *,
    batch_size: int = EMBED_BATCH_SIZE,
) -> list[list[float]]:
    """Embed texts in stable order and validate the configured vector shape."""
    if not texts:
        return []
    if not 1 <= batch_size <= EMBED_BATCH_SIZE:
        raise ValueError(f"batch_size must be between 1 and {EMBED_BATCH_SIZE}")

    inputs = _validated_inputs(texts)
    client = _client()
    try:
        return [
            vector
            for batch in _iter_batches(inputs, batch_size=batch_size)
            for vector in _embed_batch(client, batch)
        ]
    finally:
        client.close()
