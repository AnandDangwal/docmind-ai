from __future__ import annotations

from datetime import date
from io import BytesIO, TextIOWrapper
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

pytest.importorskip("docling")
pytest.importorskip("tiktoken")

from ingest import chunk_and_embed
from ingest.chunking import ChunkRecord


class FakeSession:
    def __init__(self, *, fail_commit: bool = False) -> None:
        self.added: list[object] = []
        self.committed = False
        self.rolled_back = False
        self.fail_commit = fail_commit

    def add_all(self, values) -> None:
        self.added.extend(values)

    def commit(self) -> None:
        if self.fail_commit:
            raise RuntimeError("database failure")
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True


def _document():
    return SimpleNamespace(
        id=uuid4(),
        ticker="AAPL",
        company_name="Apple Inc.",
        filing_type="10-K",
        filing_date=date(2023, 11, 3),
        fiscal_year=2023,
        accession_number="0000320193-23-000106",
        source_url="https://example.test/filing",
    )


def _record(index: int = 0) -> ChunkRecord:
    return ChunkRecord(
        chunk_index=index,
        text=f"chunk {index}",
        page=None,
        section="Item 7",
        token_count=2,
        chunk_metadata={"chunker": "hybrid"},
    )


def test_preflight_rejects_schema_dimension_mismatch(monkeypatch) -> None:
    fake_column = SimpleNamespace(type=SimpleNamespace(dim=1_024))
    fake_table = SimpleNamespace(c=SimpleNamespace(embedding=fake_column))
    monkeypatch.setattr(
        chunk_and_embed,
        "DocumentChunk",
        SimpleNamespace(__table__=fake_table),
    )
    monkeypatch.setattr(
        chunk_and_embed,
        "settings",
        SimpleNamespace(gemini_embedding_dimensions=1_536),
    )

    with pytest.raises(ValueError, match="expects 1024, settings request 1536"):
        chunk_and_embed._validate_embedding_schema()


def test_dry_run_never_embeds_or_writes(monkeypatch) -> None:
    session = FakeSession()
    monkeypatch.setattr(chunk_and_embed, "_document_has_chunks", lambda *args: False)
    monkeypatch.setattr(
        chunk_and_embed,
        "chunk_document",
        lambda *args, **kwargs: [_record()],
    )
    monkeypatch.setattr(
        chunk_and_embed,
        "embed_texts",
        lambda texts: pytest.fail("dry run must not call OpenAI"),
    )

    count = chunk_and_embed.ingest_document(
        session,
        _document(),
        Path("filing.md"),
        dry_run=True,
    )

    assert count == 1
    assert session.added == []
    assert session.committed is False


def test_preview_handles_characters_unsupported_by_console(monkeypatch) -> None:
    output = BytesIO()
    console = TextIOWrapper(output, encoding="cp1252")
    monkeypatch.setattr(chunk_and_embed.sys, "stdout", console)
    record = ChunkRecord(
        chunk_index=0,
        text="checked ☒",
        page=None,
        section=None,
        token_count=2,
        chunk_metadata={},
    )

    chunk_and_embed._print_preview([record])
    console.flush()

    assert b"checked \\u2612" in output.getvalue()


def test_smoke_test_embeds_and_writes_exactly_one_chunk(monkeypatch) -> None:
    session = FakeSession()
    embedded: list[list[str]] = []
    monkeypatch.setattr(chunk_and_embed, "_document_has_chunks", lambda *args: False)
    monkeypatch.setattr(
        chunk_and_embed,
        "chunk_document",
        lambda *args, **kwargs: [_record()],
    )
    monkeypatch.setattr(
        chunk_and_embed,
        "embed_texts",
        lambda texts: embedded.append(texts) or [[0.1, 0.2, 0.3]],
    )

    count = chunk_and_embed.ingest_document(
        session,
        _document(),
        Path("filing.md"),
        max_chunks=1,
    )

    assert count == 1
    assert embedded == [["chunk 0"]]
    assert len(session.added) == 1
    assert session.committed is True


def test_existing_document_is_skipped_before_chunking(monkeypatch) -> None:
    session = FakeSession()
    monkeypatch.setattr(chunk_and_embed, "_document_has_chunks", lambda *args: True)
    monkeypatch.setattr(
        chunk_and_embed,
        "chunk_document",
        lambda *args, **kwargs: pytest.fail("existing document should be skipped"),
    )

    count = chunk_and_embed.ingest_document(
        session,
        _document(),
        Path("filing.md"),
    )

    assert count == 0
    assert session.committed is False


def test_force_prepares_embedding_before_deleting(monkeypatch) -> None:
    session = FakeSession()
    events: list[str] = []
    monkeypatch.setattr(
        chunk_and_embed,
        "chunk_document",
        lambda *args, **kwargs: [_record()],
    )
    monkeypatch.setattr(
        chunk_and_embed,
        "embed_texts",
        lambda texts: events.append("embed") or [[0.1]],
    )
    monkeypatch.setattr(
        chunk_and_embed,
        "_delete_chunks",
        lambda *args: events.append("delete"),
    )

    chunk_and_embed.ingest_document(
        session,
        _document(),
        Path("filing.md"),
        force=True,
    )

    assert events == ["embed", "delete"]
    assert session.committed is True


def test_embedding_failure_preserves_existing_chunks(monkeypatch) -> None:
    session = FakeSession()
    deleted = False

    def fail_embedding(texts):
        raise RuntimeError("OpenAI failure")

    def track_delete(*args):
        nonlocal deleted
        deleted = True

    monkeypatch.setattr(
        chunk_and_embed,
        "chunk_document",
        lambda *args, **kwargs: [_record()],
    )
    monkeypatch.setattr(chunk_and_embed, "embed_texts", fail_embedding)
    monkeypatch.setattr(chunk_and_embed, "_delete_chunks", track_delete)

    with pytest.raises(RuntimeError, match="OpenAI failure"):
        chunk_and_embed.ingest_document(
            session,
            _document(),
            Path("filing.md"),
            force=True,
        )

    assert deleted is False
    assert session.committed is False


def test_database_failure_rolls_back_force_replacement(monkeypatch) -> None:
    session = FakeSession(fail_commit=True)
    monkeypatch.setattr(
        chunk_and_embed,
        "chunk_document",
        lambda *args, **kwargs: [_record()],
    )
    monkeypatch.setattr(chunk_and_embed, "embed_texts", lambda texts: [[0.1]])
    monkeypatch.setattr(chunk_and_embed, "_delete_chunks", lambda *args: None)

    with pytest.raises(RuntimeError, match="database failure"):
        chunk_and_embed.ingest_document(
            session,
            _document(),
            Path("filing.md"),
            force=True,
        )

    assert session.rolled_back is True


