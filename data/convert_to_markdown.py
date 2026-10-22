"""Convert the SEC filings in downloads/ from HTML to Markdown with Docling.

Mirrors downloads/ into markdown/ (same year folders, same file names with a
.md extension) and writes a markdown/manifest.json whose `local_path` entries
point at the .md files. Docling lives in the backend environment, so run with
`uv run --project backend data/convert_to_markdown.py`.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from docling.document_converter import DocumentConverter

DATA_DIR = Path(__file__).resolve().parent
DOWNLOADS_DIR = DATA_DIR / "downloads"
MARKDOWN_DIR = DATA_DIR / "markdown"


def convert_all(converter: DocumentConverter) -> list[Path]:
    converted = []
    sources = sorted(DOWNLOADS_DIR.rglob("*.htm"))
    for i, src in enumerate(sources, 1):
        dest = MARKDOWN_DIR / src.relative_to(DOWNLOADS_DIR).with_suffix(".md")
        print(f"[{i}/{len(sources)}] {src.name}", flush=True)
        dest.parent.mkdir(parents=True, exist_ok=True)
        document = converter.convert(src).document
        dest.write_text(document.export_to_markdown(), encoding="utf-8")
        converted.append(dest)
    return converted


def write_manifest() -> None:
    manifest = json.loads((DOWNLOADS_DIR / "manifest.json").read_text(encoding="utf-8"))
    manifest["converted_at_utc"] = datetime.now(UTC).isoformat()
    manifest["converter"] = "docling"
    for filing in manifest["filings"]:
        filing["local_path"] = str(Path(filing["local_path"]).with_suffix(".md"))
    (MARKDOWN_DIR / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )


def main() -> None:
    converted = convert_all(DocumentConverter())
    write_manifest()
    print(f"Converted {len(converted)} filings into {MARKDOWN_DIR}")


if __name__ == "__main__":
    main()
