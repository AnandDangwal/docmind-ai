"""Verify that the complete Markdown corpus was embedded in Postgres."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import bindparam, create_engine, func, make_url, select, text
from sqlalchemy.orm import Session

from app.config import settings
from app.database.models import DocumentChunk, IngestionRun, SourceDocument
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


def _chunk_health(
    session: Session, document_ids: list[Any], ingestion_run_id: UUID
) -> Any:
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
            , count(*) FILTER (WHERE section IS NULL OR btrim(section) = '') AS missing_sections
            , count(*) FILTER (
                WHERE metadata->>'provenance_kind' NOT IN ('page', 'anchor', 'section')
            ) AS missing_provenance
        FROM document_chunks
        WHERE document_id IN :document_ids
          AND ingestion_run_id = :ingestion_run_id
        """
    ).bindparams(bindparam("document_ids", expanding=True))
    return session.execute(
        statement,
        {
            "dimensions": settings.gemini_embedding_dimensions,
            "document_ids": document_ids,
            "ingestion_run_id": ingestion_run_id,
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


def verify_corpus(
    session: Session,
    *,
    ingestion_run_id: UUID | None = None,
    manifest_path=None,
) -> VerificationResult:
    run = (
        session.get(IngestionRun, ingestion_run_id)
        if ingestion_run_id
        else session.scalar(select(IngestionRun).where(IngestionRun.status == "active"))
    )
    if run is None:
        raise ValueError("Corpus generation does not exist")
    paths = iter_all_markdown_paths(manifest_path) if manifest_path else iter_all_markdown_paths()
    accessions = [accession for accession, _ in paths]
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
            .where(
                DocumentChunk.document_id.in_(document_ids),
                DocumentChunk.ingestion_run_id == run.id,
            )
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

    health = _chunk_health(session, document_ids, run.id)
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
    if run.extractor_version != "legacy-v1":
        if health.missing_sections:
            raise ValueError(f"{health.missing_sections} chunks have no section path")
        if health.missing_provenance:
            raise ValueError(
                f"{health.missing_provenance} chunks have no valid provenance fallback"
            )
        missing_headings = [
            document.accession_number
            for document in documents
            if "## Item " not in document.markdown_content
        ]
        if missing_headings:
            raise ValueError(
                "Normalized filings without canonical Item headings: "
                + ", ".join(sorted(missing_headings))
            )

    spot = session.execute(
        select(DocumentChunk, SourceDocument)
        .join(SourceDocument, SourceDocument.id == DocumentChunk.document_id)
        .where(
            SourceDocument.ticker == "AAPL",
            DocumentChunk.ingestion_run_id == run.id,
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
    parser = argparse.ArgumentParser(description=__doc__)
    target = parser.add_mutually_exclusive_group()
    target.add_argument("--generation", type=UUID)
    target.add_argument("--staging-generation", action="store_true")
    parser.add_argument("--manifest", type=str)
    args = parser.parse_args()
    engine = create_engine(_database_url(), pool_pre_ping=True)
    try:
        with Session(engine) as session:
            generation_id = args.generation
            if args.staging_generation:
                generation_id = session.scalar(
                    select(IngestionRun.id).where(IngestionRun.status == "staging")
                )
                if generation_id is None:
                    raise ValueError("No staging corpus generation exists")
            result = verify_corpus(
                session,
                ingestion_run_id=generation_id,
                manifest_path=(Path(args.manifest) if args.manifest else None),
            )
            if generation_id:
                run = session.get(IngestionRun, generation_id)
                run.verification_report = {
                    "passed": True,
                    "documents": result.documents,
                    "chunks": result.chunks,
                    "max_token_count": result.max_token_count,
                }
                session.commit()
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
