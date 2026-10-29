from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from contextlib import AbstractAsyncContextManager
from typing import Protocol
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import EMBEDDING_DIMENSIONS
from app.retrieval.fusion import reciprocal_rank_fusion
from app.retrieval.models import Chunk, RetrievalFilters, RetrievedPassage, SearchHit
from app.retrieval.queries import (
    full_text_search,
    read_chunk,
    read_neighbor_chunks,
    semantic_search,
)

DEFAULT_TOP_K = 10
DEFAULT_CANDIDATE_K = 50
DEFAULT_NEIGHBOR_WINDOW = 1
MAX_TOP_K = 20
MAX_CANDIDATE_K = 100
MAX_NEIGHBOR_WINDOW = 3

QueryEmbedder = Callable[[str], Awaitable[list[float]]]
SemanticSearch = Callable[..., Awaitable[list[SearchHit]]]
FullTextSearch = Callable[..., Awaitable[list[SearchHit]]]


class SessionFactory(Protocol):
    def __call__(self) -> AbstractAsyncContextManager[AsyncSession]: ...


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
        query = query.strip()
        if not query:
            raise ValueError("query must not be blank")
        if not 1 <= top_k <= MAX_TOP_K:
            raise ValueError(f"top_k must be between 1 and {MAX_TOP_K}")
        if not top_k <= candidate_k <= MAX_CANDIDATE_K:
            raise ValueError(f"candidate_k must be between top_k and {MAX_CANDIDATE_K}")
        if not 0 <= neighbor_window <= MAX_NEIGHBOR_WINDOW:
            raise ValueError(
                f"neighbor_window must be between 0 and {MAX_NEIGHBOR_WINDOW}"
            )

        active_filters = filters or RetrievalFilters()
        query_embedding = await self._embed_query(query)
        if len(query_embedding) != EMBEDDING_DIMENSIONS:
            raise ValueError(
                f"Expected query embedding dimension {EMBEDDING_DIMENSIONS}, "
                f"got {len(query_embedding)}"
            )

        semantic_hits, lexical_hits = await asyncio.gather(
            self._run_semantic(
                query_embedding,
                filters=active_filters,
                limit=candidate_k,
            ),
            self._run_full_text(
                query,
                filters=active_filters,
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
