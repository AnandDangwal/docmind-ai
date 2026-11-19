"""Recover source page numbers from branded filing footers in SEC HTML."""

from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from html.parser import HTMLParser
from itertools import pairwise
from pathlib import Path

_REPOSITORY_DIR = Path(__file__).resolve().parents[2]
_DOWNLOAD_DIR = _REPOSITORY_DIR / "data" / "downloads"
_PAGE_MARKERS = (
    re.compile(
        r"Apple Inc\.\s*\|\s*\d{4} Form 10-K\s*\|\s*(\d+)", re.IGNORECASE
    ),
    re.compile(
        r"(?:Annual Report|Form 10-K)\s*\|\s*(\d{1,4})(?=\s|$)", re.IGNORECASE
    ),
    re.compile(r"\b\d{4}\s+Form 10-K\s+(\d{1,4})(?=\s|$)", re.IGNORECASE),
)
_TOKEN = re.compile(r"[a-z0-9]+")
_VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}


@dataclass(frozen=True, slots=True)
class Provenance:
    page: int | None
    source_anchor: str | None
    kind: str


class _VisibleTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.anchors: dict[str, list[str]] = {}
        self._ignored_depth = 0
        self._anchor_stack: list[str | None] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"head", "script", "style", "ix:hidden"}:
            self._ignored_depth += 1
        attributes = dict(attrs)
        anchor = attributes.get("id") or attributes.get("name")
        inherited = self._anchor_stack[-1] if self._anchor_stack else None
        if tag not in _VOID_TAGS:
            self._anchor_stack.append(anchor or inherited)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"head", "script", "style", "ix:hidden"}:
            self._ignored_depth -= 1
        if self._anchor_stack:
            self._anchor_stack.pop()

    def handle_data(self, data: str) -> None:
        if not self._ignored_depth and data.strip():
            self.parts.append(data)
            anchor = self._anchor_stack[-1] if self._anchor_stack else None
            if anchor:
                self.anchors.setdefault(anchor, []).append(data)


def _normalized_tokens(text: str) -> list[str]:
    normalized = unicodedata.normalize("NFKC", text).lower()
    return _TOKEN.findall(normalized)


def _html_path(markdown_path: Path) -> Path:
    resolved = markdown_path.resolve()
    roots = (
        _REPOSITORY_DIR / "data" / "markdown",
        _REPOSITORY_DIR / "data" / "markdown_staging",
    )
    relative = next(
        (resolved.relative_to(root) for root in roots if resolved.is_relative_to(root)),
        None,
    )
    if relative is None:
        raise ValueError(f"Markdown path is outside a known corpus: {markdown_path}")
    return (_DOWNLOAD_DIR / relative).with_suffix(".htm")


class PageResolver:
    def __init__(
        self, pages: list[tuple[int, str]], anchors: dict[str, str] | None = None
    ) -> None:
        self._pages = [
            (page, " ".join(_normalized_tokens(text))) for page, text in pages
        ]
        self._anchors = [
            (anchor, " ".join(_normalized_tokens(text)))
            for anchor, text in (anchors or {}).items()
        ]
        self._anchor_text = dict(self._anchors)
        token_index: dict[str, set[str]] = defaultdict(set)
        for anchor, content in self._anchors:
            for token in set(content.split()):
                token_index[token].add(anchor)
        self._anchor_token_index = token_index

    @classmethod
    def from_markdown(cls, markdown_path: Path) -> PageResolver | None:
        try:
            html_path = _html_path(markdown_path)
        except ValueError:
            return None
        if not html_path.is_file():
            return None

        parser = _VisibleTextParser()
        parser.feed(html_path.read_text(encoding="utf-8"))
        visible_text = " ".join(parser.parts)
        markers: list[re.Match[str]] = []
        for pattern in _PAGE_MARKERS:
            candidates = list(pattern.finditer(visible_text))
            if len(candidates) >= 2:
                markers = candidates
                break

        pages: list[tuple[int, str]] = []
        numbers = [int(marker.group(1)) for marker in markers]
        if not any(
            next_page <= page or next_page - page > 5
            for page, next_page in pairwise(numbers)
        ):
            start = 0
            for marker, page in zip(markers, numbers, strict=True):
                pages.append((page, visible_text[start : marker.start()]))
                start = marker.end()
        anchors = {key: " ".join(value) for key, value in parser.anchors.items()}
        return cls(pages, anchors) if pages or anchors else None

    @staticmethod
    def _unique_match(
        text: str, candidates: list[tuple[object, str]]
    ) -> object | None:
        tokens = _normalized_tokens(text)
        if len(tokens) < 6:
            return None

        width = min(14, len(tokens))
        for start in range(0, len(tokens) - width + 1, max(1, width // 2)):
            phrase = " ".join(tokens[start : start + width])
            matches = [key for key, content in candidates if phrase in content]
            if len(matches) == 1:
                return matches[0]
        return None

    def page_for_text(self, text: str) -> int | None:
        match = self._unique_match(text, list(self._pages))
        return int(match) if match is not None else None

    def anchor_for_text(self, text: str) -> str | None:
        tokens = _normalized_tokens(text)
        if len(tokens) < 6:
            return None
        width = min(14, len(tokens))
        for start in range(0, len(tokens) - width + 1, max(1, width // 2)):
            phrase_tokens = tokens[start : start + width]
            indexed = [
                self._anchor_token_index.get(token, set()) for token in phrase_tokens
            ]
            candidates = min(indexed, key=len, default=set())
            phrase = " ".join(phrase_tokens)
            matches = [
                anchor
                for anchor in candidates
                if phrase in self._anchor_text[anchor]
            ]
            if len(matches) == 1:
                return matches[0]
        return None

    def provenance_for_text(self, text: str) -> Provenance:
        page = self.page_for_text(text)
        anchor = self.anchor_for_text(text)
        kind = "page" if page is not None else "anchor" if anchor else "section"
        return Provenance(page=page, source_anchor=anchor, kind=kind)
