"""Convert the SEC filings in downloads/ from HTML to Markdown with Docling.

Mirrors downloads/ into markdown/ (same year folders, same file names with a
.md extension) and writes a markdown/manifest.json whose `local_path` entries
point at the .md files. Docling lives in the backend environment, so run with
`uv run --project backend data/convert_to_markdown.py`.
"""
from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from docling.document_converter import DocumentConverter

from clean_markdown import clean_markdown
from ingest.sec_structure import EXTRACTOR_VERSION, normalize_markdown_structure

DATA_DIR = Path(__file__).resolve().parent
DOWNLOADS_DIR = DATA_DIR / "downloads"
MARKDOWN_DIR = DATA_DIR / "markdown"


def convert_all(converter: DocumentConverter, output_dir: Path) -> list[Path]:
    converted = []
    sources = sorted(DOWNLOADS_DIR.rglob("*.htm"))
    for i, src in enumerate(sources, 1):
        dest = output_dir / src.relative_to(DOWNLOADS_DIR).with_suffix(".md")
        print(f"[{i}/{len(sources)}] {src.name}", flush=True)
        dest.parent.mkdir(parents=True, exist_ok=True)
        document = converter.convert(src).document
        cleaned, _ = clean_markdown(document.export_to_markdown())
        normalized = normalize_markdown_structure(cleaned)
        dest.write_text(normalized, encoding="utf-8")
        converted.append(dest)
    return converted


def write_manifest(output_dir: Path) -> None:
    manifest = json.loads((DOWNLOADS_DIR / "manifest.json").read_text(encoding="utf-8"))
    manifest["converted_at_utc"] = datetime.now(UTC).isoformat()
    manifest["converter"] = "docling"
    manifest["extractor_version"] = EXTRACTOR_VERSION
    for filing in manifest["filings"]:
        filing["local_path"] = str(Path(filing["local_path"]).with_suffix(".md"))
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--staging",
        action="store_true",
        help="Write to data/markdown_staging instead of replacing normalized files",
    )
    args = parser.parse_args()
    output_dir = DATA_DIR / ("markdown_staging" if args.staging else "markdown")
    converted = convert_all(DocumentConverter(), output_dir)
    write_manifest(output_dir)
    print(f"Converted {len(converted)} filings into {output_dir}")


if __name__ == "__main__":
    main()
