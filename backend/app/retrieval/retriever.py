from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import Awaitable, Callable
from contextlib import AbstractAsyncContextManager
from typing import Protocol
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import EMBEDDING_DIMENSIONS
from app.retrieval.fusion import reciprocal_rank_fusion
from app.retrieval.models import (
    CHUNK_CONTEXT_OVERHEAD_TOKENS,
    Chunk,
    RetrievalFilters,
    RetrievedPassage,
    SearchHit,
)
from app.retrieval.queries import (
    full_text_search,
    list_active_chunks,
    read_chunk,
    read_neighbor_chunks,
    semantic_search,
)

DEFAULT_TOP_K = 10
DEFAULT_CANDIDATE_K = 50
DEFAULT_NEIGHBOR_WINDOW = 1
MAX_TOP_K = 100
MAX_CANDIDATE_K = 500
MAX_NEIGHBOR_WINDOW = 8

QueryEmbedder = Callable[[str], Awaitable[list[float]]]
SemanticSearch = Callable[..., Awaitable[list[SearchHit]]]
FullTextSearch = Callable[..., Awaitable[list[SearchHit]]]


class SessionFactory(Protocol):
    def __call__(self) -> AbstractAsyncContextManager[AsyncSession]: ...


def _validated_query(
    query: str,
    *,
    top_k: int,
    candidate_k: int,
    neighbor_window: int,
) -> str:
    query = query.strip()
    if not query:
        raise ValueError("query must not be blank")
    if not 1 <= top_k <= MAX_TOP_K:
        raise ValueError(f"top_k must be between 1 and {MAX_TOP_K}")
    if not top_k <= candidate_k <= MAX_CANDIDATE_K:
        raise ValueError(f"candidate_k must be between top_k and {MAX_CANDIDATE_K}")
    if not 0 <= neighbor_window <= MAX_NEIGHBOR_WINDOW:
        raise ValueError(f"neighbor_window must be between 0 and {MAX_NEIGHBOR_WINDOW}")
    return query


class DocumentRetriever:
    def __init__(
        self,
        session_factory: SessionFactory,
        embed_query: QueryEmbedder,
        *,
        semantic_search_fn: SemanticSearch = semantic_search,
        full_text_search_fn: FullTextSearch = full_text_search,
    ) -> None:
        self._session_factory = session_factory
        self._embed_query = embed_query
        self._semantic_search = semantic_search_fn
        self._full_text_search = full_text_search_fn

    async def _run_semantic(
        self,
        query_embedding: list[float],
        *,
        filters: RetrievalFilters,
        limit: int,
    ) -> list[SearchHit]:
        async with self._session_factory() as session:
            return await self._semantic_search(
                session,
                query_embedding,
                filters=filters,
                limit=limit,
            )

    async def _run_full_text(
        self,
        query: str,
        *,
        filters: RetrievalFilters,
        limit: int,
    ) -> list[SearchHit]:
        async with self._session_factory() as session:
            return await self._full_text_search(
                session,
                query,
                filters=filters,
                limit=limit,
            )

    async def search_filings(
        self,
        query: str,
        filters: RetrievalFilters | None = None,
        *,
        top_k: int = DEFAULT_TOP_K,
        candidate_k: int = DEFAULT_CANDIDATE_K,
        neighbor_window: int = DEFAULT_NEIGHBOR_WINDOW,
    ) -> list[RetrievedPassage]:
        query = _validated_query(
            query,
            top_k=top_k,
            candidate_k=candidate_k,
            neighbor_window=neighbor_window,
        )
        active_filters = filters or RetrievalFilters()
        query_embedding = await self._embed_query(query)
        if len(query_embedding) != EMBEDDING_DIMENSIONS:
            raise ValueError(
                f"Expected query embedding dimension {EMBEDDING_DIMENSIONS}, "
                f"got {len(query_embedding)}"
            )

        return await self._search_with_embedding(
            query,
            query_embedding,
            active_filters,
            top_k=top_k,
            candidate_k=candidate_k,
            neighbor_window=neighbor_window,
        )

    async def search_filings_balanced(
        self,
        query: str,
        filters: tuple[RetrievalFilters, ...],
        *,
        top_k_per_filter: int = DEFAULT_TOP_K,
        candidate_k: int = DEFAULT_CANDIDATE_K,
        neighbor_window: int = DEFAULT_NEIGHBOR_WINDOW,
    ) -> list[RetrievedPassage]:
        if not filters:
            raise ValueError("filters must not be empty")
        query = _validated_query(
            query,
            top_k=top_k_per_filter,
            candidate_k=candidate_k,
            neighbor_window=neighbor_window,
        )
        query_embedding = await self._embed_query(query)
        if len(query_embedding) != EMBEDDING_DIMENSIONS:
            raise ValueError(
                f"Expected query embedding dimension {EMBEDDING_DIMENSIONS}, "
                f"got {len(query_embedding)}"
            )
        results = await asyncio.gather(
            *(
                self._search_with_embedding(
                    query,
                    query_embedding,
                    active_filters,
                    top_k=top_k_per_filter,
                    candidate_k=candidate_k,
                    neighbor_window=neighbor_window,
                )
                for active_filters in filters
            )
        )
        return [passage for passages in results for passage in passages]

    async def _search_with_embedding(
        self,
        query: str,
        query_embedding: list[float],
        filters: RetrievalFilters,
        *,
        top_k: int,
        candidate_k: int,
        neighbor_window: int,
    ) -> list[RetrievedPassage]:

        semantic_hits, lexical_hits = await asyncio.gather(
            self._run_semantic(
                query_embedding,
                filters=filters,
                limit=candidate_k,
            ),
            self._run_full_text(
                query,
                filters=filters,
                limit=candidate_k,
            ),
        )
        fused = reciprocal_rank_fusion([semantic_hits, lexical_hits])[:top_k]
        anchors = [(hit.chunk.document_id, hit.chunk.chunk_index) for hit in fused]
        async with self._session_factory() as session:
            neighbors = await read_neighbor_chunks(
                session,
                anchors,
                before=neighbor_window,
                after=neighbor_window,
            )

        return [
            RetrievedPassage(
                rank=rank,
                fused_score=hit.score,
                anchor=hit.chunk,
                neighbors=neighbors[(hit.chunk.document_id, hit.chunk.chunk_index)],
                source_hits=hit.source_hits,
            )
            for rank, hit in enumerate(fused, start=1)
        ]

    async def read_chunk(self, chunk_id: UUID) -> Chunk | None:
        async with self._session_factory() as session:
            return await read_chunk(session, chunk_id)

    async def load_relevant_filings(
        self,
        filters: RetrievalFilters,
        *,
        max_chunks: int = 2_000,
        max_tokens: int = 900_000,
    ) -> tuple[list[Chunk], bool]:
        """Load complete selected filings up to the model-safe evidence budget."""
        if not filters.tickers and not filters.fiscal_years and not filters.latest_only:
            raise ValueError("Whole-filing loading requires company or year filters")
        async with self._session_factory() as session:
            available = await list_active_chunks(session, filters)
        selected: list[Chunk] = []
        tokens = 0
        for chunk in available:
            context_tokens = chunk.token_count + CHUNK_CONTEXT_OVERHEAD_TOKENS
            if len(selected) >= max_chunks or tokens + context_tokens > max_tokens:
                return selected, False
            selected.append(chunk)
            tokens += context_tokens
        return selected, True

    async def load_relevant_filing_groups(
        self, filters: RetrievalFilters
    ) -> list[list[Chunk]]:
        """Return active chunks grouped into complete filings in stable order."""
        if not filters.tickers and not filters.fiscal_years and not filters.latest_only:
            raise ValueError("Whole-filing loading requires company or year filters")
        async with self._session_factory() as session:
            available = await list_active_chunks(session, filters)
        grouped: dict[UUID, list[Chunk]] = defaultdict(list)
        for chunk in available:
            grouped[chunk.document_id].append(chunk)
        return list(grouped.values())

    async def read_surrounding_chunks(
        self,
        chunk_id: UUID,
        *,
        before: int = DEFAULT_NEIGHBOR_WINDOW,
        after: int = DEFAULT_NEIGHBOR_WINDOW,
    ) -> tuple[Chunk, ...]:
        if not 0 <= before <= MAX_NEIGHBOR_WINDOW:
            raise ValueError(f"before must be between 0 and {MAX_NEIGHBOR_WINDOW}")
        if not 0 <= after <= MAX_NEIGHBOR_WINDOW:
            raise ValueError(f"after must be between 0 and {MAX_NEIGHBOR_WINDOW}")

        async with self._session_factory() as session:
            anchor = await read_chunk(session, chunk_id)
            if anchor is None:
                return ()
            neighbors = await read_neighbor_chunks(
                session,
                [(anchor.document_id, anchor.chunk_index)],
                before=before,
                after=after,
            )
        return neighbors[(anchor.document_id, anchor.chunk_index)]
