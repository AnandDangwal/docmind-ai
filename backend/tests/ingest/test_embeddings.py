from __future__ import annotations

from types import SimpleNamespace

import pytest

pytest.importorskip("tiktoken")

from ingest import embeddings


class FakeResponse:
    def __init__(self, vectors: list[list[float]]) -> None:
        self.vectors = vectors
        self.status_code = 200
        self.text = ""

    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict:
        return {"embeddings": [{"values": vector} for vector in self.vectors]}


class FakeClient:
    def __init__(self, responses: list[list[list[float]]]) -> None:
        self.responses = iter(responses)
        self.calls: list[dict] = []

    def post(self, url: str, **kwargs) -> FakeResponse:
        self.calls.append({"url": url, **kwargs})
        return FakeResponse(next(self.responses))

    def close(self) -> None:
        pass


def _settings(dimensions: int = 3):
    return SimpleNamespace(
        gemini_api_key=SimpleNamespace(get_secret_value=lambda: "test-key"),
        gemini_embedding_model="gemini-embedding-2",
        gemini_embedding_dimensions=dimensions,
    )


def test_empty_input_makes_no_client(monkeypatch) -> None:
    monkeypatch.setattr(
        embeddings,
        "_client",
        lambda: pytest.fail("client should not be constructed"),
    )

    assert embeddings.embed_texts([]) == []


def test_embeddings_preserve_request_order_and_settings(monkeypatch) -> None:
    client = FakeClient([[[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]]])
    monkeypatch.setattr(embeddings, "settings", _settings())
    monkeypatch.setattr(embeddings, "_count_tokens", lambda text: 1)
    monkeypatch.setattr(
        embeddings,
        "_client",
        lambda: client,
    )

    vectors = embeddings.embed_texts(["first", "second"])

    assert vectors == [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]]
    assert client.calls[0]["url"].endswith(
        "/models/gemini-embedding-2:batchEmbedContents"
    )
    assert [
        request["content"]["parts"][0]["text"]
        for request in client.calls[0]["json"]["requests"]
    ] == ["first", "second"]
    assert all(
        request["output_dimensionality"] == 3
        for request in client.calls[0]["json"]["requests"]
    )


def test_embeddings_respect_batch_size(monkeypatch) -> None:
    client = FakeClient([[[1.0], [2.0]], [[3.0]]])
    monkeypatch.setattr(embeddings, "settings", _settings(dimensions=1))
    monkeypatch.setattr(embeddings, "_count_tokens", lambda text: 1)
    monkeypatch.setattr(
        embeddings,
        "_client",
        lambda: client,
    )

    vectors = embeddings.embed_texts(["a", "b", "c"], batch_size=2)

    assert vectors == [[1.0], [2.0], [3.0]]
    assert [
        [request["content"]["parts"][0]["text"] for request in call["json"]["requests"]]
        for call in client.calls
    ] == [["a", "b"], ["c"]]


@pytest.mark.parametrize("text", ["", "   "])
def test_embeddings_reject_empty_text_before_client(monkeypatch, text: str) -> None:
    monkeypatch.setattr(
        embeddings,
        "_client",
        lambda: pytest.fail("client should not be constructed"),
    )

    with pytest.raises(ValueError, match="is empty"):
        embeddings.embed_texts([text])


def test_embeddings_reject_oversized_text_before_client(monkeypatch) -> None:
    monkeypatch.setattr(
        embeddings,
        "_count_tokens",
        lambda text: embeddings.EMBED_MAX_INPUT_TOKENS + 1,
    )
    monkeypatch.setattr(
        embeddings,
        "_client",
        lambda: pytest.fail("client should not be constructed"),
    )

    with pytest.raises(ValueError, match="limit is 8192"):
        embeddings.embed_texts(["too long"])


def test_embeddings_reject_dimension_mismatch(monkeypatch) -> None:
    client = FakeClient([[[1.0, 2.0]]])
    monkeypatch.setattr(embeddings, "settings", _settings(dimensions=3))
    monkeypatch.setattr(embeddings, "_count_tokens", lambda text: 1)
    monkeypatch.setattr(
        embeddings,
        "_client",
        lambda: client,
    )

    with pytest.raises(ValueError, match="Expected embedding dimension 3, got 2"):
        embeddings.embed_texts(["text"])


def test_rate_limit_retry_uses_gemini_retry_delay(monkeypatch) -> None:
    rate_limited = FakeResponse([])
    rate_limited.status_code = 429
    rate_limited.text = '{"retryInfo": {"retryDelay": "12.5s"}}'

    class RateLimitedClient:
        def __init__(self) -> None:
            self.responses = iter([rate_limited, FakeResponse([[1.0]])])

        def post(self, *args, **kwargs):
            return next(self.responses)

    client = RateLimitedClient()
    delays = []
    monkeypatch.setattr(embeddings, "settings", _settings(dimensions=1))
    monkeypatch.setattr(embeddings.time, "sleep", delays.append)

    assert embeddings._embed_batch(client, ["text"]) == [[1.0]]
    assert delays == [13.5]


def test_daily_quota_failure_does_not_retry(monkeypatch) -> None:
    rate_limited = FakeResponse([])
    rate_limited.status_code = 429
    rate_limited.text = "Embed content requests per day limit exceeded"

    class DailyQuotaClient:
        def post(self, *args, **kwargs):
            return rate_limited

    monkeypatch.setattr(
        embeddings.time,
        "sleep",
        lambda delay: pytest.fail("daily quota failures must not sleep and retry"),
    )

    with pytest.raises(RuntimeError, match="daily embedding quota is exhausted"):
        embeddings._embed_batch(DailyQuotaClient(), ["text"])


