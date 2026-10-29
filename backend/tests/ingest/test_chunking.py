from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("docling")
pytest.importorskip("tiktoken")

from ingest import chunking


def _markdown_path() -> Path:
    return chunking.MARKDOWN_DIR / "test-fixture.md"


def test_openai_tokenizer_accepts_special_token_text() -> None:
    tokenizer = chunking.build_tokenizer()

    assert tokenizer.count_tokens("ordinary <|endoftext|> filing text") > 0


def test_hybrid_chunker_enables_merging_and_table_headers() -> None:
    hybrid_chunker = chunking.build_hybrid_chunker()

    assert hybrid_chunker.merge_peers is True
    assert hybrid_chunker.repeat_table_header is True
    assert hybrid_chunker.omit_header_on_overflow is True
    assert hybrid_chunker.max_tokens == chunking.CHUNK_MAX_TOKENS


def test_real_markdown_conversion_preserves_structure_and_table_headers(
    tmp_path,
    monkeypatch,
) -> None:
    markdown_path = tmp_path / "filing.md"
    markdown_path.write_text(
        "# Example Corp\n\n"
        "## Item 7\n\n"
        "Revenue discussion.\n\n"
        "| Year | Revenue |\n"
        "| --- | ---: |\n"
        "| 2023 | 100 |\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        chunking,
        "_relative_source_path",
        lambda path: "tests/fixtures/filing.md",
    )

    records = chunking.chunk_document(markdown_path, {})

    combined = "\n".join(record.text for record in records)
    assert "Item 7" in combined
    assert "Year" in combined
    assert "Revenue" in combined
    assert all(record.page is None for record in records)
    assert all(record.token_count <= chunking.CHUNK_MAX_TOKENS for record in records)


def test_real_hybrid_chunker_splits_oversized_markdown(tmp_path, monkeypatch) -> None:
    markdown_path = tmp_path / "large.md"
    paragraphs = [
        f"Paragraph {index}: revenue increased because demand remained strong."
        for index in range(80)
    ]
    markdown_path.write_text(
        "# Example Corp\n\n## Item 7\n\n" + "\n\n".join(paragraphs),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        chunking,
        "_relative_source_path",
        lambda path: "tests/fixtures/large.md",
    )

    records = chunking.chunk_document(markdown_path, {}, max_tokens=64)

    assert len(records) > 1
    assert all(record.token_count <= 64 for record in records)


def test_chunk_document_maps_contextualized_text_and_headings(monkeypatch) -> None:
    class FakeMeta:
        headings = ("Company", "Item 7")

    class FakeChunk:
        text = "raw body"
        meta = FakeMeta()

    class FakeTokenizer:
        @staticmethod
        def count_tokens(text: str) -> int:
            return len(text.split())

    class FakeChunker:
        tokenizer = FakeTokenizer()

        @staticmethod
        def chunk(*, dl_doc):
            assert dl_doc == "doc"
            return iter([FakeChunk()])

        @staticmethod
        def contextualize(*, chunk) -> str:
            assert isinstance(chunk, FakeChunk)
            return "Company\nItem 7\ncontextualized body"

    monkeypatch.setattr(chunking, "convert_markdown_to_document", lambda path: "doc")
    monkeypatch.setattr(
        chunking, "build_hybrid_chunker", lambda **kwargs: FakeChunker()
    )

    records = chunking.chunk_document(
        _markdown_path(),
        {"accession_number": "example"},
    )

    assert len(records) == 1
    record = records[0]
    assert record.chunk_index == 0
    assert record.text == "Company\nItem 7\ncontextualized body"
    assert record.section == "Company > Item 7"
    assert record.page is None
    assert record.chunk_metadata["raw_text"] == "raw body"
    assert record.chunk_metadata["headings"] == ["Company", "Item 7"]
    assert record.chunk_metadata["source_path"] == "data/markdown/test-fixture.md"
    assert record.chunk_metadata["chunker"] == "hybrid"


def test_chunk_document_skips_non_indexable_chunks_and_keeps_indices_contiguous(
    monkeypatch,
) -> None:
    class FakeMeta:
        headings: tuple[str, ...] = ()

    class FakeChunk:
        def __init__(self, text: str) -> None:
            self.text = text
            self.meta = FakeMeta()

    class FakeTokenizer:
        @staticmethod
        def count_tokens(text: str) -> int:
            return len(text.split())

    chunks = [
        FakeChunk(""),
        FakeChunk("|  |  |\n| - | - |\n|  |  |"),
        FakeChunk("one"),
        FakeChunk("two"),
    ]

    class FakeChunker:
        tokenizer = FakeTokenizer()

        @staticmethod
        def chunk(*, dl_doc):
            return iter(chunks)

        @staticmethod
        def contextualize(*, chunk) -> str:
            return chunk.text

    monkeypatch.setattr(chunking, "convert_markdown_to_document", lambda path: object())
    monkeypatch.setattr(
        chunking, "build_hybrid_chunker", lambda **kwargs: FakeChunker()
    )

    records = chunking.chunk_document(_markdown_path(), {})

    assert [record.chunk_index for record in records] == [0, 1]


def test_sec_item_heading_propagates_when_markdown_has_no_heading_markers(
    monkeypatch,
) -> None:
    class FakeMeta:
        headings: tuple[str, ...] = ()

    class FakeChunk:
        def __init__(self, text: str) -> None:
            self.text = text
            self.meta = FakeMeta()

    class FakeTokenizer:
        @staticmethod
        def count_tokens(text: str) -> int:
            return len(text.split())

    chunks = [
        FakeChunk("Item 7. Management's Discussion and Analysis\nOpening text."),
        FakeChunk("Continued management discussion."),
        FakeChunk("Item 7A. Quantitative and Qualitative Disclosures\nRisk text."),
    ]

    class FakeChunker:
        tokenizer = FakeTokenizer()

        @staticmethod
        def chunk(*, dl_doc):
            return iter(chunks)

        @staticmethod
        def contextualize(*, chunk) -> str:
            return chunk.text

    monkeypatch.setattr(chunking, "convert_markdown_to_document", lambda path: object())
    monkeypatch.setattr(
        chunking, "build_hybrid_chunker", lambda **kwargs: FakeChunker()
    )

    records = chunking.chunk_document(_markdown_path(), {})

    assert records[0].section == "Item 7. Management's Discussion and Analysis"
    assert records[1].section == records[0].section
    assert records[2].section == "Item 7A. Quantitative and Qualitative Disclosures"


def test_oversized_context_is_split_with_repeated_heading() -> None:
    tokenizer = chunking.build_tokenizer(max_tokens=16)
    heading = "Item 15 exhibits"
    raw_text = " ".join(f"entry-{index}" for index in range(40))

    parts = chunking._split_oversized_context(
        f"{heading}\n{raw_text}",
        raw_text,
        tokenizer,
        max_tokens=16,
    )

    assert len(parts) > 1
    assert all(part.startswith(heading) for part in parts)
    assert all(tokenizer.count_tokens(part) <= 16 for part in parts)


def test_chunk_document_honors_max_chunks_after_empty_output(monkeypatch) -> None:
    class FakeMeta:
        headings: tuple[str, ...] = ()

    class FakeChunk:
        def __init__(self, text: str) -> None:
            self.text = text
            self.meta = FakeMeta()

    class FakeTokenizer:
        @staticmethod
        def count_tokens(text: str) -> int:
            return 1

    class FakeChunker:
        tokenizer = FakeTokenizer()

        @staticmethod
        def chunk(*, dl_doc):
            return iter([FakeChunk(""), FakeChunk("first"), FakeChunk("second")])

        @staticmethod
        def contextualize(*, chunk) -> str:
            return chunk.text

    monkeypatch.setattr(chunking, "convert_markdown_to_document", lambda path: object())
    monkeypatch.setattr(
        chunking, "build_hybrid_chunker", lambda **kwargs: FakeChunker()
    )

    records = chunking.chunk_document(_markdown_path(), {}, max_chunks=1)

    assert [record.text for record in records] == ["first"]
