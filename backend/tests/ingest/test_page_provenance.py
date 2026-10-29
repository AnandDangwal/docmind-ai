from pathlib import Path

from ingest import page_provenance


def test_apple_footer_assigns_text_to_its_source_page(
    tmp_path: Path, monkeypatch
) -> None:
    markdown_dir = tmp_path / "data" / "markdown"
    download_dir = tmp_path / "data" / "downloads"
    markdown_path = markdown_dir / "2024" / "apple.md"
    html_path = download_dir / "2024" / "apple.htm"
    markdown_path.parent.mkdir(parents=True)
    html_path.parent.mkdir(parents=True)
    markdown_path.write_text("placeholder", encoding="utf-8")
    html_path.write_text(
        "<html><body>First page has one unique revenue sentence here. "
        "Apple Inc. | 2024 Form 10-K | 1 "
        "Second page has another unique margin sentence here. "
        "Apple Inc. | 2024 Form 10-K | 2</body></html>",
        encoding="utf-8",
    )
    monkeypatch.setattr(page_provenance, "_REPOSITORY_DIR", tmp_path)
    monkeypatch.setattr(page_provenance, "_DOWNLOAD_DIR", download_dir)

    resolver = page_provenance.PageResolver.from_markdown(markdown_path)

    assert resolver is not None
    assert (
        resolver.page_for_text("First page has one unique revenue sentence here") == 1
    )
    assert (
        resolver.page_for_text("Second page has another unique margin sentence here")
        == 2
    )


def test_missing_branded_page_markers_returns_none(tmp_path: Path, monkeypatch) -> None:
    markdown_dir = tmp_path / "data" / "markdown"
    download_dir = tmp_path / "data" / "downloads"
    markdown_path = markdown_dir / "2024" / "example.md"
    html_path = download_dir / "2024" / "example.htm"
    markdown_path.parent.mkdir(parents=True)
    html_path.parent.mkdir(parents=True)
    markdown_path.write_text("placeholder", encoding="utf-8")
    html_path.write_text("<html><body>No page footer.</body></html>", encoding="utf-8")
    monkeypatch.setattr(page_provenance, "_REPOSITORY_DIR", tmp_path)
    monkeypatch.setattr(page_provenance, "_DOWNLOAD_DIR", download_dir)

    assert page_provenance.PageResolver.from_markdown(markdown_path) is None
