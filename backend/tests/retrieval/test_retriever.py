from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import date
from uuid import UUID

import pytest

from app.database.models import EMBEDDING_DIMENSIONS
from app.retrieval.models import Chunk, RetrievalFilters, SearchHit
from app.retrieval.retriever import DocumentRetriever


def _chunk(value: int, *, chunk_index: int | None = None) -> Chunk:
    return Chunk(
        id=UUID(int=value),
        document_id=UUID(int=100),
        chunk_index=value if chunk_index is None else chunk_index,
        content=f"chunk {value}",
        page=None,
        section="Item 7",
        token_count=2,
        ticker="AAPL",
        company_name="Apple Inc.",
        filing_type="10-K",
        filing_date=date(2023, 11, 3),
        fiscal_year=2023,
        accession_number="0000320193-23-000106",
        source_url="https://example.test/filing",
    )


def _hit(value: int, source: str, rank: int) -> SearchHit:
    return SearchHit(
        chunk=_chunk(value),
        source=source,  # type: ignore[arg-type]
        rank=rank,
        score=1.0,
    )


@asynccontextmanager
async def _session_factory():
    yield object()


def test_search_runs_both_branches_with_one_embedding_and_propagates_options(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, object]] = []
    active = 0
    concurrent = False

    async def embed(query: str) -> list[float]:
        calls.append(("embed", query))
        return [0.0] * EMBEDDING_DIMENSIONS

    async def search_semantic(session, vector, **kwargs):
        nonlocal active, concurrent
        calls.append(("semantic", kwargs))
        active += 1
        await asyncio.sleep(0)
        concurrent = concurrent or active > 1
        active -= 1
        return [_hit(1, "semantic", 1)]

    async def search_lexical(session, query, **kwargs):
        nonlocal active, concurrent
        calls.append(("lexical", kwargs))
        active += 1
        await asyncio.sleep(0)
        concurrent = concurrent or active > 1
        active -= 1
        return [_hit(1, "lexical", 1)]

    async def neighbors(session, anchors, **kwargs):
        calls.append(("neighbors", kwargs))
        return {anchor: (_chunk(2),) for anchor in anchors}

    monkeypatch.setattr("app.retrieval.retriever.read_neighbor_chunks", neighbors)
    retriever = DocumentRetriever(
        _session_factory,
        embed,
        semantic_search_fn=search_semantic,
        full_text_search_fn=search_lexical,
    )
    filters = RetrievalFilters(tickers=("AAPL",), fiscal_years=(2023,))

    passages = asyncio.run(
        retriever.search_filings(
            "net sales",
            filters,
            top_k=1,
            candidate_k=7,
            neighbor_window=1,
        )
    )

    assert concurrent is True
    assert [call[0] for call in calls].count("embed") == 1
    assert calls[1][1] == {"filters": filters, "limit": 7}
    assert calls[2][1] == {"filters": filters, "limit": 7}
    assert passages[0].anchor.id == UUID(int=1)
    assert passages[0].neighbors == (_chunk(2),)
    assert [hit.source for hit in passages[0].source_hits] == [
        "semantic",
        "lexical",
    ]


def test_search_degrades_to_one_branch(monkeypatch: pytest.MonkeyPatch) -> None:
    async def embed(query: str) -> list[float]:
        return [0.0] * EMBEDDING_DIMENSIONS

    async def no_semantic(session, vector, **kwargs):
        return []

    async def lexical(session, query, **kwargs):
        return [_hit(2, "lexical", 1)]

    async def neighbors(session, anchors, **kwargs):
        return {anchor: () for anchor in anchors}

    monkeypatch.setattr("app.retrieval.retriever.read_neighbor_chunks", neighbors)
    retriever = DocumentRetriever(
        _session_factory,
        embed,
        semantic_search_fn=no_semantic,
        full_text_search_fn=lexical,
    )

    passages = asyncio.run(retriever.search_filings("AWS margin", top_k=1))

    assert passages[0].anchor.id == UUID(int=2)
    assert [hit.source for hit in passages[0].source_hits] == ["lexical"]


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"top_k": 0}, "top_k"),
        ({"top_k": 10, "candidate_k": 5}, "candidate_k"),
        ({"neighbor_window": 4}, "neighbor_window"),
    ],
)
def test_search_validates_bounds(kwargs: dict[str, int], message: str) -> None:
    async def embed(query: str) -> list[float]:
        return [0.0] * EMBEDDING_DIMENSIONS

    retriever = DocumentRetriever(_session_factory, embed)

    with pytest.raises(ValueError, match=message):
        asyncio.run(retriever.search_filings("query", **kwargs))


def test_search_rejects_wrong_embedding_dimension() -> None:
    async def embed(query: str) -> list[float]:
        return [0.0]

    retriever = DocumentRetriever(_session_factory, embed)

    with pytest.raises(ValueError, match="Expected query embedding dimension"):
        asyncio.run(retriever.search_filings("query"))


def test_read_methods_delegate_to_bounded_queries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def embed(query: str) -> list[float]:
        return [0.0] * EMBEDDING_DIMENSIONS

    async def get_chunk(session, chunk_id):
        return _chunk(5, chunk_index=5) if chunk_id == UUID(int=5) else None

    async def get_neighbors(session, anchors, **kwargs):
        assert anchors == [(UUID(int=100), 5)]
        assert kwargs == {"before": 1, "after": 2}
        return {anchors[0]: (_chunk(4, chunk_index=4), _chunk(6, chunk_index=6))}

    monkeypatch.setattr("app.retrieval.retriever.read_chunk", get_chunk)
    monkeypatch.setattr("app.retrieval.retriever.read_neighbor_chunks", get_neighbors)
    retriever = DocumentRetriever(_session_factory, embed)

    chunk = asyncio.run(retriever.read_chunk(UUID(int=5)))
    neighbors = asyncio.run(
        retriever.read_surrounding_chunks(UUID(int=5), before=1, after=2)
    )
    missing = asyncio.run(retriever.read_surrounding_chunks(UUID(int=6)))

    assert chunk == _chunk(5, chunk_index=5)
    assert [neighbor.chunk_index for neighbor in neighbors] == [4, 6]
    assert missing == ()
