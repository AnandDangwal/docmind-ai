"""Docling-based chunking for the normalized Markdown corpus."""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import tiktoken
from docling.chunking import HybridChunker
from docling.datamodel.base_models import InputFormat
from docling.document_converter import DocumentConverter
from docling_core.transforms.chunker.hierarchical_chunker import (
    ChunkingDocSerializer,
    ChunkingSerializerProvider,
)
from docling_core.transforms.chunker.tokenizer.openai import OpenAITokenizer
from docling_core.transforms.serializer.markdown import (
    MarkdownParams,
    MarkdownTableSerializer,
)

from ingest.page_provenance import PageResolver

CHUNK_MAX_TOKENS = 512
_REPOSITORY_DIR = Path(__file__).resolve().parents[2]
MARKDOWN_DIR = _REPOSITORY_DIR / "data" / "markdown"
MANIFEST_PATH = MARKDOWN_DIR / "manifest.json"
_SEC_ITEM_HEADING = re.compile(
    r"^(item\s+(?:[1-9]|1[0-6])(?:[a-z])?\.\s*[^\n]+)$",
    flags=re.IGNORECASE | re.MULTILINE,
)
_INDEXABLE_TEXT = re.compile(r"[A-Za-z0-9]")


class PatchedOpenAITokenizer(OpenAITokenizer):
    """Treat special-token-like strings in SEC text as ordinary text."""

    def count_tokens(self, text: str) -> int:
        return len(
            self.tokenizer.encode(
                text=text,
                allowed_special=set(),
                disallowed_special=(),
            )
        )


class MarkdownTableSerializerProvider(ChunkingSerializerProvider):
    """Serialize tables as compact Markdown inside contextualized chunks."""

    def get_serializer(self, doc: Any) -> ChunkingDocSerializer:
        return ChunkingDocSerializer(
            doc=doc,
            table_serializer=MarkdownTableSerializer(),
            params=MarkdownParams(compact_tables=True),
        )


@dataclass(frozen=True, slots=True)
class ChunkRecord:
    chunk_index: int
    text: str
    page: int | None
    section: str | None
    token_count: int
    chunk_metadata: dict[str, Any]


def load_manifest_markdown_paths() -> dict[str, Path]:
    """Return accession-to-Markdown mappings from the normalized manifest."""
    if not MANIFEST_PATH.is_file():
        raise FileNotFoundError(f"Missing Markdown manifest: {MANIFEST_PATH}")

    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    filings = manifest.get("filings", [])
    if not filings:
        raise ValueError(f"No filings listed in {MANIFEST_PATH}")

    paths: dict[str, Path] = {}
    for filing in filings:
        accession = filing["accession_number"]
        if accession in paths:
            raise ValueError(f"Duplicate accession in {MANIFEST_PATH}: {accession}")

        markdown_path = MARKDOWN_DIR / filing["local_path"]
        if not markdown_path.is_file():
            raise FileNotFoundError(f"Missing Markdown file: {markdown_path}")
        paths[accession] = markdown_path

    return paths


def markdown_path_for_accession(accession_number: str) -> Path:
    paths = load_manifest_markdown_paths()
    try:
        return paths[accession_number]
    except KeyError as exc:
        raise KeyError(
            f"Accession {accession_number} not found in {MANIFEST_PATH}"
        ) from exc


def iter_all_markdown_paths() -> Iterator[tuple[str, Path]]:
    yield from load_manifest_markdown_paths().items()


def build_tokenizer(max_tokens: int = CHUNK_MAX_TOKENS) -> PatchedOpenAITokenizer:
    if max_tokens <= 0:
        raise ValueError("max_tokens must be positive")
    return PatchedOpenAITokenizer(
        tokenizer=tiktoken.get_encoding("cl100k_base"),
        max_tokens=max_tokens,
    )


def build_hybrid_chunker(max_tokens: int = CHUNK_MAX_TOKENS) -> HybridChunker:
    """Build the token-aware chunker layered on Docling's hierarchy pass."""
    return HybridChunker(
        tokenizer=build_tokenizer(max_tokens=max_tokens),
        merge_peers=True,
        repeat_table_header=True,
        omit_header_on_overflow=True,
        serializer_provider=MarkdownTableSerializerProvider(),
    )


def convert_markdown_to_document(markdown_path: Path) -> Any:
    converter = DocumentConverter(allowed_formats=[InputFormat.MD])
    return converter.convert(markdown_path).document


def _relative_source_path(markdown_path: Path) -> str:
    return markdown_path.resolve().relative_to(_REPOSITORY_DIR).as_posix()


def _section_from_headings(headings: list[str]) -> str | None:
    cleaned = [heading.strip() for heading in headings if heading.strip()]
    section = " > ".join(cleaned)
    if len(section) > 255:
        return f"{section[:252]}..."
    return section or None


def _section_from_sec_item(text: str) -> str | None:
    matches = _SEC_ITEM_HEADING.findall(text)
    if not matches:
        return None
    return " ".join(matches[-1].split())[:255]


def _has_indexable_text(text: str) -> bool:
    """Reject extraction artifacts made only of Markdown table punctuation."""
    return bool(_INDEXABLE_TEXT.search(text))


def _split_oversized_context(
    contextualized: str,
    raw_text: str,
    tokenizer: PatchedOpenAITokenizer,
    max_tokens: int,
) -> list[str]:
    """Enforce the hard ceiling when Docling metadata pushes a chunk over it."""
    raw_text = raw_text.strip()
    if raw_text and contextualized.endswith(raw_text):
        prefix = contextualized[: -len(raw_text)].rstrip()
        prefix = f"{prefix}\n" if prefix else ""
    else:
        prefix = ""
        raw_text = contextualized

    prefix_tokens = tokenizer.count_tokens(prefix)
    if prefix_tokens >= max_tokens:
        prefix = ""
        prefix_tokens = 0
        raw_text = contextualized

    available_tokens = max_tokens - prefix_tokens
    token_ids = tokenizer.tokenizer.encode(
        raw_text,
        allowed_special=set(),
        disallowed_special=(),
    )
    return [
        f"{prefix}{tokenizer.tokenizer.decode(token_ids[start : start + available_tokens])}".strip()
        for start in range(0, len(token_ids), available_tokens)
    ]


def chunk_document(
    markdown_path: Path,
    filing_metadata: dict[str, Any],
    *,
    max_chunks: int | None = None,
    max_tokens: int = CHUNK_MAX_TOKENS,
) -> list[ChunkRecord]:
    """Convert one Markdown file and return deterministic retrieval chunks."""
    if max_chunks is not None and max_chunks <= 0:
        raise ValueError("max_chunks must be positive")

    document = convert_markdown_to_document(markdown_path)
    chunker = build_hybrid_chunker(max_tokens=max_tokens)
    records: list[ChunkRecord] = []
    current_section: str | None = None
    page_resolver = PageResolver.from_markdown(markdown_path)

    for chunk in chunker.chunk(dl_doc=document):
        if max_chunks is not None and len(records) >= max_chunks:
            break

        if not _has_indexable_text(chunk.text):
            continue

        contextualized = chunker.contextualize(chunk=chunk).strip()
        if not contextualized:
            continue

        headings = list(getattr(chunk.meta, "headings", None) or [])
        current_section = (
            _section_from_headings(headings)
            or _section_from_sec_item(chunk.text)
            or current_section
        )
        token_count = chunker.tokenizer.count_tokens(contextualized)
        texts = (
            [contextualized]
            if token_count <= max_tokens
            else _split_oversized_context(
                contextualized,
                chunk.text,
                chunker.tokenizer,
                max_tokens,
            )
        )

        for text in texts:
            if max_chunks is not None and len(records) >= max_chunks:
                break

            token_count = chunker.tokenizer.count_tokens(text)
            if token_count > max_tokens:
                raise ValueError(
                    f"Fallback emitted a {token_count}-token chunk; limit is {max_tokens}"
                )
            records.append(
                ChunkRecord(
                    chunk_index=len(records),
                    text=text,
                    page=(
                        page_resolver.page_for_text(chunk.text)
                        if page_resolver
                        else None
                    ),
                    section=current_section,
                    token_count=token_count,
                    chunk_metadata={
                        **filing_metadata,
                        "source_path": _relative_source_path(markdown_path),
                        "headings": headings,
                        "raw_text": chunk.text,
                        "chunker": "hybrid",
                        "fallback_split": len(texts) > 1,
                        "chunk_max_tokens": max_tokens,
                    },
                )
            )

    return records
