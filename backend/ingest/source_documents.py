from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import SourceDocument
from app.database.session import AsyncSessionLocal, engine

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST_PATH = REPO_ROOT / "data" / "markdown" / "manifest.json"

COMPANY_NAMES = {
    "AAPL": "Apple Inc.",
    "AMZN": "Amazon.com, Inc.",
    "GOOGL": "Alphabet Inc.",
    "MSFT": "Microsoft Corporation",
    "NVDA": "NVIDIA Corporation",
}


@dataclass(frozen=True)
class SourceDocumentInput:
    ticker: str
    company_name: str
    filing_type: str
    filing_date: date
    fiscal_year: int
    accession_number: str
    source_url: str
    markdown_content: str
    content_hash: str
    extractor_version: str


def _required_string(filing: dict[str, object], field: str) -> str:
    value = filing.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Filing field {field!r} must be a non-empty string")
    return value.strip()


def _markdown_path(markdown_dir: Path, local_path: str) -> Path:
    relative_path = Path(local_path.replace("\\", "/"))
    path = (markdown_dir / relative_path).resolve()
    try:
        path.relative_to(markdown_dir.resolve())
    except ValueError as exc:
        raise ValueError(
            f"Markdown path escapes corpus directory: {local_path}"
        ) from exc
    if not path.is_file():
        raise ValueError(f"Markdown file does not exist: {path}")
    return path


def load_source_documents(manifest_path: Path) -> list[SourceDocumentInput]:
    manifest_path = manifest_path.resolve()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    filings = manifest.get("filings")
    if not isinstance(filings, list):
        raise TypeError("Manifest field 'filings' must be a list")

    markdown_dir = manifest_path.parent
    extractor_version = manifest.get("extractor_version", "legacy-v1")
    if not isinstance(extractor_version, str) or not extractor_version.strip():
        raise ValueError("Manifest extractor_version must be a non-empty string")
    documents = []
    accessions = set()
    for raw_filing in filings:
        if not isinstance(raw_filing, dict):
            raise TypeError("Every manifest filing must be an object")

        ticker = _required_string(raw_filing, "ticker").upper()
        try:
            company_name = COMPANY_NAMES[ticker]
        except KeyError as exc:
            raise ValueError(
                f"No company name configured for ticker {ticker!r}"
            ) from exc

        accession_number = _required_string(raw_filing, "accession_number")
        if accession_number in accessions:
            raise ValueError(
                f"Duplicate accession number in manifest: {accession_number}"
            )
        accessions.add(accession_number)

        filing_date = date.fromisoformat(_required_string(raw_filing, "filing_date"))
        report_date = date.fromisoformat(_required_string(raw_filing, "report_date"))
        path = _markdown_path(
            markdown_dir,
            _required_string(raw_filing, "local_path"),
        )
        markdown_content = path.read_text(encoding="utf-8")
        if not markdown_content.strip():
            raise ValueError(f"Markdown file is empty: {path}")

        documents.append(
            SourceDocumentInput(
                ticker=ticker,
                company_name=company_name,
                filing_type=_required_string(raw_filing, "form"),
                filing_date=filing_date,
                fiscal_year=report_date.year,
                accession_number=accession_number,
                source_url=_required_string(raw_filing, "source_url"),
                markdown_content=markdown_content,
                content_hash=hashlib.sha256(markdown_content.encode()).hexdigest(),
                extractor_version=extractor_version,
            )
        )
    return documents


async def ingest_source_documents(
    db_session: AsyncSession,
    documents: list[SourceDocumentInput],
) -> tuple[int, int]:
    accessions = [document.accession_number for document in documents]
    existing_documents = list(
        await db_session.scalars(
            select(SourceDocument).where(
                SourceDocument.accession_number.in_(accessions)
            )
        )
    )
    existing = {document.accession_number: document for document in existing_documents}

    new_documents = [
        SourceDocument(
            ticker=document.ticker,
            company_name=document.company_name,
            filing_type=document.filing_type,
            filing_date=document.filing_date,
            fiscal_year=document.fiscal_year,
            accession_number=document.accession_number,
            source_url=document.source_url,
            markdown_content=document.markdown_content,
            content_hash=document.content_hash,
            extractor_version=document.extractor_version,
        )
        for document in documents
        if document.accession_number not in existing
    ]
    updated = 0
    for document in documents:
        stored = existing.get(document.accession_number)
        if stored is None or stored.content_hash == document.content_hash:
            continue
        stored.ticker = document.ticker
        stored.company_name = document.company_name
        stored.filing_type = document.filing_type
        stored.filing_date = document.filing_date
        stored.fiscal_year = document.fiscal_year
        stored.source_url = document.source_url
        stored.markdown_content = document.markdown_content
        stored.content_hash = document.content_hash
        stored.extractor_version = document.extractor_version
        updated += 1
    db_session.add_all(new_documents)
    await db_session.commit()
    return len(new_documents), updated


async def run(manifest_path: Path) -> tuple[int, int]:
    documents = load_source_documents(manifest_path)
    async with AsyncSessionLocal() as db_session:
        return await ingest_source_documents(db_session, documents)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Load normalized Markdown filings into source_documents."
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=DEFAULT_MANIFEST_PATH,
        help=f"Markdown manifest path (default: {DEFAULT_MANIFEST_PATH})",
    )
    args = parser.parse_args()

    try:
        inserted, updated = asyncio.run(run(args.manifest))
        print(f"Source documents inserted: {inserted}")
        print(f"Source documents updated: {updated}")
    finally:
        asyncio.run(engine.dispose())


if __name__ == "__main__":
    main()
