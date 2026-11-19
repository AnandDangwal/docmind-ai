from ingest.sec_structure import canonical_heading, normalize_markdown_structure


def test_promotes_actual_items_after_compact_table_of_contents() -> None:
    toc = "\n".join(f"Item {number}." for number in range(1, 11))
    markdown = (
        f"{toc}\n\n"
        + "\n".join(f"boilerplate line {index}" for index in range(30))
        + "\nItem 1. Business\nOperating discussion.\n"
        + "Item 1A. Risk Factors\nRisk discussion.\n"
    )

    normalized = normalize_markdown_structure(markdown)

    assert normalized.count("## Item 1. Business") == 1
    assert normalized.count("## Item 1A. Risk Factors") == 1
    assert normalized.startswith("Item 1.\nItem 2.")


def test_promotes_high_confidence_bold_subsection() -> None:
    normalized = normalize_markdown_structure(
        "Item 7. Management's Discussion and Analysis of Financial Condition "
        "and Results of Operations\n\n**Revenue by Segment**\n\nDiscussion.\n"
    )

    assert "## Item 7." in normalized
    assert "### Revenue by Segment" in normalized


def test_preserves_table_rows_when_adding_a_heading() -> None:
    row = "| Item 7. | Management's Discussion and Analysis |"
    table = "|  |  |\n| --- | --- |\n" + row

    assert canonical_heading(row) is not None
    normalized = normalize_markdown_structure(table)
    assert "## Item 7." in normalized
    assert table in normalized
    assert normalized.index("## Item 7.") < normalized.index(table)
