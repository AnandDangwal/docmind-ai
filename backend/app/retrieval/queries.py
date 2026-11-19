from __future__ import annotations

import re
from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.database.models import (
    EMBEDDING_DIMENSIONS,
    DocumentChunk,
    IngestionRun,
    SourceDocument,
)
from app.retrieval.models import Chunk, RetrievalFilters, RetrievalSource, SearchHit

MAX_QUERY_RESULTS = 500
_QUERY_WORD = re.compile(r"[A-Za-z][A-Za-z0-9'-]{2,}")
_QUERY_STOP_WORDS = {
    "about",
    "alphabet",
    "amazon",
    "and",
    "apple",
    "based",
    "can",
    "companies",
    "company",
    "compare",
    "data",
    "filing",
    "filings",
    "financial",
    "generate",
    "google",
    "hundred",
    "hundreds",
    "metrics",
    "microsoft",
    "nvidia",
    "other",
    "performance",
    "please",
    "prompt",
    "question",
    "summary",
    "the",
    "tokens",
    "what",
    "which",
    "with",
    "words",
    "year",
}


def _validate_limit(limit: int) -> None:
    if not 1 <= limit <= MAX_QUERY_RESULTS:
        raise ValueError(f"limit must be between 1 and {MAX_QUERY_RESULTS}")


def lexical_query(query: str) -> str:
    terms = list(
        dict.fromkeys(
            word.casefold()
            for word in _QUERY_WORD.findall(query)
            if word.casefold() not in _QUERY_STOP_WORDS
        )
    )
    return " OR ".join(terms[:12]) or query.strip()


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
    if filters.latest_only:
        latest_document = aliased(SourceDocument)
        latest_chunk = aliased(DocumentChunk)
        latest_run = aliased(IngestionRun)
        latest_date = (
            select(func.max(latest_document.filing_date))
            .select_from(latest_document)
            .join(latest_chunk, latest_chunk.document_id == latest_document.id)
            .join(latest_run, latest_run.id == latest_chunk.ingestion_run_id)
            .where(
                latest_run.status == "active",
                latest_document.ticker == SourceDocument.ticker,
            )
        )
        if filters.fiscal_years:
            latest_date = latest_date.where(
                latest_document.fiscal_year.in_(filters.fiscal_years)
            )
        if filters.filing_types:
            latest_date = latest_date.where(
                latest_document.filing_type.in_(filters.filing_types)
            )
        statement = statement.where(
            SourceDocument.filing_date
            == latest_date.correlate(SourceDocument).scalar_subquery()
        )
    return statement


def _active_chunks(statement: Select) -> Select:
    return statement.join(
        IngestionRun, IngestionRun.id == DocumentChunk.ingestion_run_id
    ).where(IngestionRun.status == "active")


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
    statement = _active_chunks(
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
    tsquery = func.websearch_to_tsquery("english", lexical_query(query))
    rank = func.ts_rank_cd(DocumentChunk.search_vector, tsquery)
    statement = _active_chunks(
        select(DocumentChunk, SourceDocument, rank.label("score"))
        .join(SourceDocument, SourceDocument.id == DocumentChunk.document_id)
        .where(DocumentChunk.search_vector.bool_op("@@")(tsquery))
        .order_by(rank.desc(), DocumentChunk.id.asc())
        .limit(limit)
    )
    return _apply_filters(statement, filters)


def _chunk(document_chunk: DocumentChunk, document: SourceDocument) -> Chunk:
    metadata = document_chunk.chunk_metadata
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
        section_path=(
            metadata.get("section_path")
            if isinstance(metadata.get("section_path"), str)
            else document_chunk.section
        ),
        source_anchor=(
            metadata.get("source_anchor")
            if isinstance(metadata.get("source_anchor"), str)
            else None
        ),
        provenance_kind=(
            metadata.get("provenance_kind")
            if metadata.get("provenance_kind") in {"page", "anchor", "section"}
            else "section"
        ),
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


async def list_active_chunks(
    session: AsyncSession, filters: RetrievalFilters
) -> list[Chunk]:
    statement = _active_chunks(
        select(DocumentChunk, SourceDocument).join(
            SourceDocument, SourceDocument.id == DocumentChunk.document_id
        )
    ).order_by(
        SourceDocument.ticker,
        SourceDocument.fiscal_year,
        DocumentChunk.chunk_index,
    )
    rows = (await session.execute(_apply_filters(statement, filters))).all()
    return [_chunk(row[0], row[1]) for row in rows]


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
            _active_chunks(
                select(DocumentChunk, SourceDocument)
                .join(SourceDocument, SourceDocument.id == DocumentChunk.document_id)
                .where(or_(*windows))
            ).order_by(DocumentChunk.document_id, DocumentChunk.chunk_index)
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
