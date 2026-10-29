from __future__ import annotations

import asyncio

import pytest

from app.database.session import AsyncSessionLocal
from app.retrieval.embeddings import GeminiQueryEmbedder
from app.retrieval.models import RetrievalFilters
from app.retrieval.queries import full_text_search, semantic_search
from app.retrieval.retriever import DocumentRetriever

pytestmark = pytest.mark.integration


def test_live_semantic_and_full_text_queries() -> None:
    async def run() -> None:
        filters = RetrievalFilters(tickers=("AAPL",), fiscal_years=(2023,))
        vector = await GeminiQueryEmbedder()("Apple net sales")
        async with AsyncSessionLocal() as session:
            semantic = await semantic_search(
                session,
                vector,
                limit=10,
                filters=filters,
            )
            lexical = await full_text_search(
                session,
                "net sales",
                limit=50,
                filters=filters,
            )

        assert semantic
        assert all(hit.chunk.ticker == "AAPL" for hit in semantic)
        assert all(hit.chunk.fiscal_year == 2023 for hit in semantic)
        assert lexical
        assert all(hit.chunk.ticker == "AAPL" for hit in lexical)
        assert all(hit.chunk.fiscal_year == 2023 for hit in lexical)
        assert any(
            hit.chunk.section and "Item 7" in hit.chunk.section for hit in lexical
        )

    asyncio.run(run())


def test_live_retriever_fuses_results_and_fetches_neighbors() -> None:
    async def run() -> None:
        retriever = DocumentRetriever(AsyncSessionLocal, GeminiQueryEmbedder())

        passages = await retriever.search_filings(
            "net sales",
            RetrievalFilters(tickers=("AAPL",), fiscal_years=(2023,)),
            top_k=5,
            candidate_k=20,
            neighbor_window=1,
        )

        assert len(passages) == 5
        assert [passage.rank for passage in passages] == [1, 2, 3, 4, 5]
        assert all(passage.anchor.ticker == "AAPL" for passage in passages)
        assert all(passage.anchor.fiscal_year == 2023 for passage in passages)
        assert all(passage.source_hits for passage in passages)
        assert all(
            neighbor.document_id == passage.anchor.document_id
            for passage in passages
            for neighbor in passage.neighbors
        )

    asyncio.run(run())


@pytest.mark.parametrize(
    ("query", "ticker"),
    [
        ("net sales", "AAPL"),
        ("AWS operating income", "AMZN"),
        ("Data Center demand", "NVDA"),
        ("Azure cloud capacity", "MSFT"),
        ("Google Cloud revenue", "GOOGL"),
    ],
)
def test_live_hybrid_client_brief_smoke_queries(query: str, ticker: str) -> None:
    """Verify live hybrid retrieval with Gemini query and corpus embeddings."""

    async def run() -> None:
        retriever = DocumentRetriever(AsyncSessionLocal, GeminiQueryEmbedder())

        passages = await retriever.search_filings(
            query,
            RetrievalFilters(tickers=(ticker,)),
            top_k=3,
            candidate_k=10,
            neighbor_window=0,
        )

        assert len(passages) == 3
        assert all(passage.anchor.ticker == ticker for passage in passages)
        assert all(passage.source_hits for passage in passages)
        assert all(
            hit.source in {"semantic", "lexical"}
            for passage in passages
            for hit in passage.source_hits
        )

    asyncio.run(run())
