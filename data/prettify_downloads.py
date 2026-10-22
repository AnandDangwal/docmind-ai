# /// script
# requires-python = ">=3.12"
# ///
"""Reformat the raw SEC filings in downloads/ onto multiple lines.

SEC EDGAR serves these filings as a single unbroken line of HTML/inline-XBRL,
which makes them unreadable in an editor. This rewrites each file with one
line per tag/text node, indented by nesting depth, while preserving the
original tag casing, attribute text, entities, and script/style content
byte-for-byte. Run with `uv run data/prettify_downloads.py`.
"""
from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path

DOWNLOADS_DIR = Path(__file__).resolve().parent / "downloads"
INDENT = "  "

VOID_ELEMENTS = {
    "area", "base", "br", "col", "embed", "hr", "img", "input",
    "link", "meta", "param", "source", "track", "wbr",
}

TAG_NAME_RE = re.compile(r"^<\s*/?\s*([^\s/>]+)")


class PrettyPrinter(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.out: list[str] = []
        self.depth = 0
        self.tag_stack: list[str] = []
        self.text_buf: list[str] = []

    def _line(self, text: str) -> None:
        self.out.append(f"{INDENT * self.depth}{text}\n")

    def _flush_text(self) -> None:
        if not self.text_buf:
            return
        text = "".join(self.text_buf)
        self.text_buf = []
        if text.strip():
            self._line(text)

    def handle_starttag(self, tag: str, attrs) -> None:
        self._flush_text()
        raw = self.get_starttag_text() or f"<{tag}>"
        self._line(raw)
        if tag not in VOID_ELEMENTS:
            match = TAG_NAME_RE.match(raw)
            self.tag_stack.append(match.group(1) if match else tag)
            self.depth += 1

    def handle_startendtag(self, tag: str, attrs) -> None:
        self._flush_text()
        raw = self.get_starttag_text() or f"<{tag}/>"
        self._line(raw)

    def handle_endtag(self, tag: str) -> None:
        self._flush_text()
        if self.tag_stack:
            self.depth -= 1
            original_name = self.tag_stack.pop()
            self._line(f"</{original_name}>")
        else:
            # Stray end tag with no matching start (shouldn't happen in
            # well-formed input) - keep it as-is rather than dropping it.
            self._line(f"</{tag}>")

    def handle_data(self, data: str) -> None:
        self.text_buf.append(data)

    def handle_entityref(self, name: str) -> None:
        self.text_buf.append(f"&{name};")

    def handle_charref(self, name: str) -> None:
        self.text_buf.append(f"&#{name};")

    def handle_comment(self, data: str) -> None:
        self._flush_text()
        self._line(f"<!--{data}-->")

    def handle_decl(self, decl: str) -> None:
        self._flush_text()
        self._line(f"<!{decl}>")

    def handle_pi(self, data: str) -> None:
        self._flush_text()
        self._line(f"<?{data}>")

    def unknown_decl(self, data: str) -> None:
        self._flush_text()
        self._line(f"<![{data}]>")

    def close(self) -> None:
        super().close()
        self._flush_text()


def prettify(html: str) -> str:
    parser = PrettyPrinter()
    parser.feed(html)
    parser.close()
    return "".join(parser.out)


def main() -> None:
    paths = sorted(DOWNLOADS_DIR.glob("*/*.htm")) + sorted(
        DOWNLOADS_DIR.glob("*/*.html")
    )
    for path in paths:
        original = path.read_text(encoding="utf-8", errors="replace")
        formatted = prettify(original)
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        tmp_path.write_text(formatted, encoding="utf-8")
        tmp_path.replace(path)
        print(f"Reformatted {path.relative_to(DOWNLOADS_DIR)}: "
              f"{len(original):,} chars -> {len(formatted):,} chars, "
              f"{formatted.count(chr(10)):,} lines")


if __name__ == "__main__":
    main()
