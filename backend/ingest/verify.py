"""Verify that the complete Markdown corpus was embedded in Postgres."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import bindparam, create_engine, func, make_url, select, text
from sqlalchemy.orm import Session

from app.config import settings
from app.database.models import DocumentChunk, SourceDocument
from ingest.chunking import CHUNK_MAX_TOKENS, iter_all_markdown_paths

APPLE_SPOT_CHECK = "Net sales disaggregated by significant products and services"


@dataclass(frozen=True, slots=True)
class VerificationResult:
    documents: int
    chunks: int
    max_token_count: int
    spot_accession: str
    spot_chunk_index: int
    spot_section: str | None
    spot_page: int | None
    spot_preview: str


def _database_url() -> str:
    url = make_url(settings.database_url.get_secret_value())
    if url.drivername == "postgresql":
        url = url.set(drivername="postgresql+psycopg")
    return url.render_as_string(hide_password=False)


def _chunk_health(session: Session, document_ids: list[Any]) -> Any:
    statement = text(
        """
        SELECT
            count(*) AS chunk_count,
            count(*) FILTER (WHERE embedding IS NULL) AS missing_embeddings,
            count(*) FILTER (
                WHERE vector_dims(embedding) <> :dimensions
            ) AS wrong_dimensions,
            count(*) FILTER (
                WHERE search_vector IS NULL OR search_vector = ''::tsvector
            ) AS missing_search_vectors,
            max(token_count) AS max_token_count
        FROM document_chunks
        WHERE document_id IN :document_ids
        """
    ).bindparams(bindparam("document_ids", expanding=True))
    return session.execute(
        statement,
        {
            "dimensions": settings.gemini_embedding_dimensions,
            "document_ids": document_ids,
        },
    ).one()


def _spot_preview(content: str) -> str:
    normalized = " ".join(content.split())
    match_start = normalized.casefold().find(APPLE_SPOT_CHECK.casefold())
    preview_start = max(0, match_start - 80)
    preview_end = match_start + len(APPLE_SPOT_CHECK) + 160
    prefix = "..." if preview_start else ""
    suffix = "..." if preview_end < len(normalized) else ""
    return f"{prefix}{normalized[preview_start:preview_end]}{suffix}"


def verify_corpus(session: Session) -> VerificationResult:
    accessions = [accession for accession, _ in iter_all_markdown_paths()]
    documents = session.scalars(
        select(SourceDocument).where(SourceDocument.accession_number.in_(accessions))
    ).all()
    documents_by_accession = {
        document.accession_number: document for document in documents
    }
    missing_documents = sorted(set(accessions) - documents_by_accession.keys())
    if missing_documents:
        raise ValueError(
            "Manifest documents missing from source_documents: "
            + ", ".join(missing_documents)
        )

    document_ids = [document.id for document in documents]
    chunk_counts = dict(
        session.execute(
            select(DocumentChunk.document_id, func.count(DocumentChunk.id))
            .where(DocumentChunk.document_id.in_(document_ids))
            .group_by(DocumentChunk.document_id)
        ).tuples().all()
    )
    missing_chunks = [
        accession
        for accession, document in documents_by_accession.items()
        if not chunk_counts.get(document.id)
    ]
    if missing_chunks:
        raise ValueError(
            "Manifest documents without chunks: " + ", ".join(sorted(missing_chunks))
        )

    health = _chunk_health(session, document_ids)
    if health.missing_embeddings:
        raise ValueError(f"{health.missing_embeddings} chunks have no embedding")
    if health.wrong_dimensions:
        raise ValueError(
            f"{health.wrong_dimensions} chunks do not have "
            f"{settings.gemini_embedding_dimensions}-dimension embeddings"
        )
    if health.missing_search_vectors:
        raise ValueError(
            f"{health.missing_search_vectors} chunks have no searchable text vector"
        )
    if health.max_token_count > CHUNK_MAX_TOKENS:
        raise ValueError(
            f"Maximum chunk size is {health.max_token_count}; "
            f"limit is {CHUNK_MAX_TOKENS}"
        )

    spot = session.execute(
        select(DocumentChunk, SourceDocument)
        .join(SourceDocument, SourceDocument.id == DocumentChunk.document_id)
        .where(
            SourceDocument.ticker == "AAPL",
            DocumentChunk.content.ilike(f"%{APPLE_SPOT_CHECK}%"),
        )
        .order_by(SourceDocument.fiscal_year.desc())
        .limit(1)
    ).one_or_none()
    if spot is None:
        raise ValueError(f"Apple spot-check passage not found: {APPLE_SPOT_CHECK!r}")

    chunk, document = spot
    return VerificationResult(
        documents=len(documents),
        chunks=health.chunk_count,
        max_token_count=health.max_token_count,
        spot_accession=document.accession_number,
        spot_chunk_index=chunk.chunk_index,
        spot_section=chunk.section,
        spot_page=chunk.page,
        spot_preview=_spot_preview(chunk.content),
    )


def main() -> None:
    engine = create_engine(_database_url(), pool_pre_ping=True)
    try:
        with Session(engine) as session:
            result = verify_corpus(session)
    finally:
        engine.dispose()

    print("Phase 4 corpus verification passed")
    print(f"  Manifest documents: {result.documents}")
    print(f"  Embedded chunks: {result.chunks}")
    print(f"  Embedding dimensions: {settings.gemini_embedding_dimensions}")
    print("  Populated search vectors: all chunks")
    print(f"  Maximum chunk tokens: {result.max_token_count}/{CHUNK_MAX_TOKENS}")
    print(
        "  Apple spot-check: "
        f"accession={result.spot_accession} "
        f"chunk={result.spot_chunk_index} "
        f"section={result.spot_section!r} page={result.spot_page!r}"
    )
    print(f"  Preview: {result.spot_preview}")


if __name__ == "__main__":
    main()
