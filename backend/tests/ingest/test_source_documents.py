from __future__ import annotations

import json
from pathlib import Path

import pytest

from ingest.source_documents import load_source_documents


def _write_manifest(tmp_path: Path, filing: dict[str, str]) -> Path:
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps({"filings": [filing]}),
        encoding="utf-8",
    )
    return manifest_path


def _filing(local_path: str = "2025\\aapl.md") -> dict[str, str]:
    return {
        "ticker": "AAPL",
        "form": "10-K",
        "filing_date": "2025-10-31",
        "report_date": "2025-09-27",
        "accession_number": "0000320193-25-000079",
        "source_url": "https://www.sec.gov/example",
        "local_path": local_path,
    }


def test_load_source_documents_extracts_database_fields(tmp_path: Path) -> None:
    markdown_path = tmp_path / "2025" / "aapl.md"
    markdown_path.parent.mkdir()
    markdown_path.write_text("# Apple filing\n", encoding="utf-8")

    documents = load_source_documents(_write_manifest(tmp_path, _filing()))

    assert len(documents) == 1
    document = documents[0]
    assert document.ticker == "AAPL"
    assert document.company_name == "Apple Inc."
    assert document.filing_type == "10-K"
    assert document.fiscal_year == 2025
    assert document.markdown_content == "# Apple filing\n"


def test_load_source_documents_rejects_path_outside_corpus(tmp_path: Path) -> None:
    outside_path = tmp_path.parent / "outside.md"
    outside_path.write_text("not in corpus", encoding="utf-8")

    with pytest.raises(ValueError, match="escapes corpus directory"):
        load_source_documents(_write_manifest(tmp_path, _filing("..\\outside.md")))


def test_load_source_documents_rejects_duplicate_accessions(tmp_path: Path) -> None:
    markdown_path = tmp_path / "2025" / "aapl.md"
    markdown_path.parent.mkdir()
    markdown_path.write_text("# Apple filing\n", encoding="utf-8")
    filing = _filing()
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps({"filings": [filing, filing]}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Duplicate accession number"):
        load_source_documents(manifest_path)
