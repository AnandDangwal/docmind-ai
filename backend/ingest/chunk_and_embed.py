"""Chunk Markdown filings, embed chunks, and store them in Supabase Postgres."""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, delete, func, make_url, select
from sqlalchemy.orm import Session

from app.config import settings
from app.database.models import DocumentChunk, SourceDocument
from ingest.chunking import (
    CHUNK_MAX_TOKENS,
    ChunkRecord,
    chunk_document,
    iter_all_markdown_paths,
    load_manifest_markdown_paths,
)
from ingest.embeddings import EMBED_BATCH_SIZE, embed_texts


@dataclass(frozen=True, slots=True)
class IngestCounts:
    processed: int = 0
    skipped: int = 0
    chunks_written: int = 0


def _filing_metadata(document: SourceDocument) -> dict[str, Any]:
    return {
        "ticker": document.ticker,
        "company_name": document.company_name,
        "filing_type": document.filing_type,
        "filing_date": document.filing_date.isoformat(),
        "fiscal_year": document.fiscal_year,
        "accession_number": document.accession_number,
        "source_url": document.source_url,
    }


def _validate_embedding_schema() -> None:
    schema_dimensions = getattr(
        DocumentChunk.__table__.c.embedding.type,
        "dim",
        None,
    )
    configured_dimensions = settings.gemini_embedding_dimensions
    if schema_dimensions != configured_dimensions:
        raise ValueError(
            "Embedding dimension mismatch: "
            f"document_chunks expects {schema_dimensions}, "
            f"settings request {configured_dimensions}"
        )


def _document_has_chunks(session: Session, document_id: Any) -> bool:
    count = session.scalar(
        select(func.count())
        .select_from(DocumentChunk)
        .where(DocumentChunk.document_id == document_id)
    )
    return bool(count)


def _delete_chunks(session: Session, document_id: Any) -> None:
    session.execute(
        delete(DocumentChunk).where(DocumentChunk.document_id == document_id)
    )


def _database_url() -> str:
    url = make_url(settings.database_url.get_secret_value())
    if url.drivername == "postgresql":
        url = url.set(drivername="postgresql+psycopg")
    return url.render_as_string(hide_password=False)


def _print_preview(records: list[ChunkRecord]) -> None:
    max_tokens = max(record.token_count for record in records)
    print(
        f"  {len(records)} chunk(s), max_tokens={max_tokens}, limit={CHUNK_MAX_TOKENS}"
    )
    sample = records[0]
    print(f"  sample section={sample.section!r} page={sample.page!r}")
    preview = repr(sample.text[:160])
    encoding = sys.stdout.encoding or "utf-8"
    safe_preview = preview.encode(encoding, errors="backslashreplace").decode(encoding)
    print(f"  sample preview={safe_preview}")


def ingest_document(
    session: Session,
    document: SourceDocument,
    markdown_path: Path,
    *,
    max_chunks: int | None = None,
    dry_run: bool = False,
    skip_existing: bool = True,
    force: bool = False,
) -> int:
    """Prepare first, then atomically replace or insert one document's chunks."""
    if not force and skip_existing and _document_has_chunks(session, document.id):
        print(f"Skipping existing chunks for {document.accession_number}")
        return 0

    print(f"Chunking {document.accession_number} from {markdown_path.name}...")
    records = chunk_document(
        markdown_path,
        _filing_metadata(document),
        max_chunks=max_chunks,
    )
    if not records:
        raise ValueError(f"No chunks produced for {document.accession_number}")
    _print_preview(records)

    if dry_run:
        return len(records)

    texts = [record.text for record in records]
    print(f"  Embedding {len(texts)} chunk(s) (batch_size={EMBED_BATCH_SIZE})...")
    vectors = embed_texts(texts)
    if len(vectors) != len(records):
        raise ValueError(f"Expected {len(records)} embeddings, received {len(vectors)}")

    try:
        if force:
            _delete_chunks(session, document.id)

        session.add_all(
            [
                DocumentChunk(
                    document_id=document.id,
                    chunk_index=record.chunk_index,
                    page=record.page,
                    section=record.section,
                    content=record.text,
                    embedding=embedding,
                    token_count=record.token_count,
                    chunk_metadata=record.chunk_metadata,
                )
                for record, embedding in zip(records, vectors, strict=True)
            ]
        )
        session.commit()
    except Exception:
        session.rollback()
        raise

    print(f"  Wrote {len(records)} chunk(s) for {document.accession_number}")
    return len(records)


def ingest_accessions(
    accessions: list[str],
    *,
    max_chunks: int | None = None,
    dry_run: bool = False,
    skip_existing: bool = True,
    force: bool = False,
) -> IngestCounts:
    """Preflight all targets, then process and commit one document at a time."""
    if not accessions:
        return IngestCounts()

    _validate_embedding_schema()
    paths = load_manifest_markdown_paths()
    missing_paths = [accession for accession in accessions if accession not in paths]
    if missing_paths:
        raise ValueError(
            "Accessions missing from the Markdown manifest: " + ", ".join(missing_paths)
        )

    engine = create_engine(_database_url(), pool_pre_ping=True)
    counts = IngestCounts()
    with Session(engine) as session:
        documents = session.scalars(
            select(SourceDocument).where(
                SourceDocument.accession_number.in_(accessions)
            )
        ).all()
        documents_by_accession = {
            document.accession_number: document for document in documents
        }
        missing_documents = [
            accession
            for accession in accessions
            if accession not in documents_by_accession
        ]
        if missing_documents:
            raise ValueError(
                "No source_documents rows for: "
                + ", ".join(missing_documents)
                + ". Run `uv run python -m ingest` first."
            )

        for accession in accessions:
            document = documents_by_accession[accession]
            if (
                not force
                and skip_existing
                and _document_has_chunks(session, document.id)
            ):
                print(f"Skipping existing chunks for {accession}")
                counts = IngestCounts(
                    processed=counts.processed,
                    skipped=counts.skipped + 1,
                    chunks_written=counts.chunks_written,
                )
                continue

            written = ingest_document(
                session,
                document,
                paths[accession],
                max_chunks=max_chunks,
                dry_run=dry_run,
                skip_existing=False,
                force=force,
            )
            counts = IngestCounts(
                processed=counts.processed + 1,
                skipped=counts.skipped,
                chunks_written=counts.chunks_written + written,
            )

    return counts


def ingest_all(
    *,
    max_chunks: int | None = None,
    dry_run: bool = False,
    skip_existing: bool = True,
    force: bool = False,
) -> IngestCounts:
    accessions = [accession for accession, _ in iter_all_markdown_paths()]
    return ingest_accessions(
        accessions,
        max_chunks=max_chunks,
        dry_run=dry_run,
        skip_existing=skip_existing,
        force=force,
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--accession", help="Process one filing by accession number")
    target.add_argument(
        "--all", action="store_true", help="Process all manifest filings"
    )
    parser.add_argument(
        "--max-chunks",
        type=int,
        default=None,
        help="Cap chunks per document (use 1 for the paid smoke test)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Chunk and preview only; no embeddings or database writes",
    )
    parser.add_argument(
        "--skip-existing",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Skip documents that already have chunks (default: true)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Atomically replace existing chunks for selected documents",
    )
    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    if args.max_chunks is not None and args.max_chunks <= 0:
        parser.error("--max-chunks must be positive")

    if args.all:
        result = ingest_all(
            max_chunks=args.max_chunks,
            dry_run=args.dry_run,
            skip_existing=args.skip_existing,
            force=args.force,
        )
    else:
        result = ingest_accessions(
            [args.accession],
            max_chunks=args.max_chunks,
            dry_run=args.dry_run,
            skip_existing=args.skip_existing,
            force=args.force,
        )

    chunk_result = "prepared" if args.dry_run else "written"
    print(
        "Done: "
        f"{result.processed} document(s) processed, "
        f"{result.skipped} skipped, "
        f"{result.chunks_written} chunk(s) {chunk_result}"
    )


if __name__ == "__main__":
    main()
