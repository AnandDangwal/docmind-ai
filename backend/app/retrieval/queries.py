from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import EMBEDDING_DIMENSIONS, DocumentChunk, SourceDocument
from app.retrieval.models import Chunk, RetrievalFilters, RetrievalSource, SearchHit

MAX_QUERY_RESULTS = 100


def _validate_limit(limit: int) -> None:
    if not 1 <= limit <= MAX_QUERY_RESULTS:
        raise ValueError(f"limit must be between 1 and {MAX_QUERY_RESULTS}")


def _apply_filters(
    statement: Select,
    filters: RetrievalFilters,
) -> Select:
    if filters.tickers:
        statement = statement.where(SourceDocument.ticker.in_(filters.tickers))
    if filters.fiscal_years:
        statement = statement.where(
            SourceDocument.fiscal_year.in_(filters.fiscal_years)
        )
    if filters.filing_types:
        statement = statement.where(
            SourceDocument.filing_type.in_(filters.filing_types)
        )
    return statement


def build_semantic_query(
    query_embedding: Sequence[float],
    *,
    limit: int,
    filters: RetrievalFilters,
) -> Select:
    _validate_limit(limit)
    if len(query_embedding) != EMBEDDING_DIMENSIONS:
        raise ValueError(
            f"Expected query embedding dimension {EMBEDDING_DIMENSIONS}, "
            f"got {len(query_embedding)}"
        )
    distance = DocumentChunk.embedding.cosine_distance(list(query_embedding))
    statement = (
        select(DocumentChunk, SourceDocument, (1.0 - distance).label("score"))
        .join(SourceDocument, SourceDocument.id == DocumentChunk.document_id)
        .order_by(distance.asc(), DocumentChunk.id.asc())
        .limit(limit)
    )
    return _apply_filters(statement, filters)


def build_full_text_query(
    query: str,
    *,
    limit: int,
    filters: RetrievalFilters,
) -> Select:
    _validate_limit(limit)
    if not query.strip():
        raise ValueError("query must not be blank")
    tsquery = func.websearch_to_tsquery("english", query)
    rank = func.ts_rank_cd(DocumentChunk.search_vector, tsquery)
    statement = (
        select(DocumentChunk, SourceDocument, rank.label("score"))
        .join(SourceDocument, SourceDocument.id == DocumentChunk.document_id)
        .where(DocumentChunk.search_vector.bool_op("@@")(tsquery))
        .order_by(rank.desc(), DocumentChunk.id.asc())
        .limit(limit)
    )
    return _apply_filters(statement, filters)


def _chunk(document_chunk: DocumentChunk, document: SourceDocument) -> Chunk:
    return Chunk(
        id=document_chunk.id,
        document_id=document_chunk.document_id,
        chunk_index=document_chunk.chunk_index,
        content=document_chunk.content,
        page=document_chunk.page,
        section=document_chunk.section,
        token_count=document_chunk.token_count,
        ticker=document.ticker,
        company_name=document.company_name,
        filing_type=document.filing_type,
        filing_date=document.filing_date,
        fiscal_year=document.fiscal_year,
        accession_number=document.accession_number,
        source_url=document.source_url,
    )


async def _search(
    session: AsyncSession,
    statement: Select,
    *,
    source: RetrievalSource,
) -> list[SearchHit]:
    rows = (await session.execute(statement)).all()
    return [
        SearchHit(
            chunk=_chunk(row[0], row[1]),
            source=source,
            rank=rank,
            score=float(row[2]),
        )
        for rank, row in enumerate(rows, start=1)
    ]


async def semantic_search(
    session: AsyncSession,
    query_embedding: Sequence[float],
    *,
    limit: int,
    filters: RetrievalFilters,
) -> list[SearchHit]:
    return await _search(
        session,
        build_semantic_query(query_embedding, limit=limit, filters=filters),
        source="semantic",
    )


async def full_text_search(
    session: AsyncSession,
    query: str,
    *,
    limit: int,
    filters: RetrievalFilters,
) -> list[SearchHit]:
    return await _search(
        session,
        build_full_text_query(query, limit=limit, filters=filters),
        source="lexical",
    )


async def read_chunk(session: AsyncSession, chunk_id: UUID) -> Chunk | None:
    row = (
        await session.execute(
            select(DocumentChunk, SourceDocument)
            .join(SourceDocument, SourceDocument.id == DocumentChunk.document_id)
            .where(DocumentChunk.id == chunk_id)
        )
    ).first()
    if row is None:
        return None
    return _chunk(row[0], row[1])


async def read_neighbor_chunks(
    session: AsyncSession,
    anchors: Sequence[tuple[UUID, int]],
    *,
    before: int,
    after: int,
) -> dict[tuple[UUID, int], tuple[Chunk, ...]]:
    if not anchors:
        return {}
    windows = [
        and_(
            DocumentChunk.document_id == document_id,
            DocumentChunk.chunk_index.between(
                chunk_index - before, chunk_index + after
            ),
        )
        for document_id, chunk_index in anchors
    ]
    rows = (
        await session.execute(
            select(DocumentChunk, SourceDocument)
            .join(SourceDocument, SourceDocument.id == DocumentChunk.document_id)
            .where(or_(*windows))
            .order_by(DocumentChunk.document_id, DocumentChunk.chunk_index)
        )
    ).all()
    available = [_chunk(row[0], row[1]) for row in rows]
    return {
        anchor: tuple(
            chunk
            for chunk in available
            if chunk.document_id == anchor[0]
            and anchor[1] - before <= chunk.chunk_index <= anchor[1] + after
            and chunk.chunk_index != anchor[1]
        )
        for anchor in anchors
    }
