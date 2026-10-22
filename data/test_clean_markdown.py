"""Run with python -m unittest discover -s data -p test_clean_markdown.py."""
import unittest

from clean_markdown import audit_repetitions, clean_markdown


class CleanMarkdownTests(unittest.TestCase):
    def test_exact_columns_and_empty_columns(self):
        source = "before\n\n| Name | Name | | 2024 | 2025 |\n| --- | --- | --- | --- | --- |\n| Sales | Sales | | 10 | 10 |\n\nafter\n"
        result, stats = clean_markdown(source)
        self.assertEqual(result, "before\n\n| Name | 2024 | 2025 |\n| --- | --- | --- |\n| Sales | 10 | 10 |\n\nafter\n")
        self.assertEqual(stats["duplicate_columns_removed"], 1)
        self.assertEqual(stats["empty_columns_removed"], 1)
        self.assertEqual(clean_markdown(result)[0], result)

    def test_same_headers_different_data_retained(self):
        source = "| Value | Value |\n| --- | --- |\n| 10 | 20 |\n"
        self.assertEqual(clean_markdown(source)[0], source)

    def test_partial_duplicate_columns(self):
        source = "| | | |\n| --- | --- | --- |\n| California | California | ID |\n| State | | Employer |\n| Address | Address | Zip |\n"
        result, stats = clean_markdown(source)
        self.assertEqual(result, "|  |  |\n| --- | --- |\n| California | ID |\n| State | Employer |\n| Address | Zip |\n")
        self.assertEqual(stats["duplicate_columns_removed"], 1)

    def test_currency_span_columns(self):
        source = "| | | | | | | |\n| --- | --- | --- | --- | --- | --- | --- |\n| | 2025 | 2025 | 2025 | 2024 | 2024 | 2024 |\n| Sales | $ | 100 | | $ | 90 | |\n| Profit | 20 | 20 | | 20 | 20 | |\n| Loss | ( 10 ) | | | ( 5 ) | | |\n"
        result, stats = clean_markdown(source)
        self.assertEqual(result, "|  |  |  |\n| --- | --- | --- |\n|  | 2025 | 2024 |\n| Sales | $ 100 | $ 90 |\n| Profit | 20 | 20 |\n| Loss | ( 10 ) | ( 5 ) |\n")
        self.assertEqual(stats["duplicate_columns_removed"], 4)
        self.assertEqual(clean_markdown(result)[0], result)

    def test_percentage_and_parenthesis_fragments(self):
        source = "| Item | Rate | Rate |\n| --- | --- | --- |\n| Growth | 10 | % |\n| Loss | ( 5 | ) |\n"
        result, _ = clean_markdown(source)
        self.assertEqual(result, "| Item | Rate |\n| --- | --- |\n| Growth | 10 % |\n| Loss | ( 5 ) |\n")

    def test_adjacent_checkboxes_collapsed(self):
        source = "| | | | |\n| --- | --- | --- | --- |\n| Large filer | ☒ | ☒ | Small filer |\n| Other | ☐ | ☐ | Emerging |\n"
        self.assertEqual(clean_markdown(source)[0], "|  |  |  |\n| --- | --- | --- |\n| Large filer | ☒ | Small filer |\n| Other | ☐ | Emerging |\n")

    def test_distinct_nonadjacent_columns_retained(self):
        source = "| | | | |\n| --- | --- | --- | --- |\n| Large filer | ☐ | Small filer | ☐ |\n"
        self.assertEqual(clean_markdown(source)[0], source)

    def test_disjoint_columns_retained(self):
        source = "| | |\n| --- | --- |\n| Left | |\n| | Right |\n"
        self.assertEqual(clean_markdown(source)[0], source)

    def test_conflicting_numbers_retained(self):
        source = "| 2025 | 2025 |\n| --- | --- |\n| 10 | ( 10 ) |\n| $ | 20 |\n"
        self.assertEqual(clean_markdown(source)[0], source)

    def test_merged_currency_and_repeated_amount(self):
        source = "| Value | Value | Value |\n| --- | --- | --- |\n| $ | 10 | 10 |\n| 20 | 20 | 20 |\n"
        result, _ = clean_markdown(source)
        self.assertEqual(result, "| Value |\n| --- |\n| $ 10 |\n| 20 |\n")
        self.assertEqual(clean_markdown(result)[0], result)

    def test_currency_and_punctuation_stay_with_amounts(self):
        source = "| | | | |\n| --- | --- | --- | --- |\n| $ | 10 | $ | 20 |\n| ( | 30 | ( | 40 |\n"
        self.assertEqual(clean_markdown(source)[0], "|  |  |\n| --- | --- |\n| $ 10 | $ 20 |\n| ( 30 | ( 40 |\n")

    def test_empty_table_removed(self):
        source = "before\n| | |\n| --- | --- |\n| | |\nafter\n"
        result, stats = clean_markdown(source)
        self.assertEqual(result, "before\nafter\n")
        self.assertEqual(stats["empty_tables_removed"], 1)

    def test_escaped_pipe_and_crlf(self):
        source = "| A \\| B | A \\| B |\r\n| :--- | :--- |\r\n| text | text |\r\n"
        self.assertEqual(clean_markdown(source)[0], "| A \\| B |\r\n| :--- |\r\n| text |\r\n")

    def test_ragged_table_preserved_and_reported(self):
        source = "| A | A |\n| --- | --- |\n| text |\n"
        result, stats = clean_markdown(source)
        self.assertEqual(result, source)
        self.assertEqual(stats["skipped_table_lines"], [1])

    def test_code_fences_preserved(self):
        source = "```markdown\n| A | A |\n| --- | --- |\n| X | X |\n```\n"
        self.assertEqual(clean_markdown(source)[0], source)

    def test_repeated_data_audited_not_removed(self):
        paragraph = "A meaningful repeated disclosure containing enough text to be included in the paragraph audit."
        table = "| Label | Value |\n| --- | --- |\n| Sales | 10 |\n| Sales | 10 |\n"
        source = f"{paragraph}\n\n{table}\n{paragraph}\n\n{table}"
        self.assertEqual(clean_markdown(source)[0], source)
        audit, _ = audit_repetitions(source)
        self.assertEqual(len(audit["repeated_paragraphs"]), 1)
        self.assertEqual(len(audit["repeated_tables"]), 1)
        self.assertEqual(len(audit["repeated_data_rows"]), 2)
        self.assertEqual(audit["repeated_data_rows"][0]["occurrences"], [5, 6])


if __name__ == "__main__":
    unittest.main()
