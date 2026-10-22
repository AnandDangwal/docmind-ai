# Data

Local data artifacts for development live here.

- `downloads/` holds raw source files fetched from SEC EDGAR, grouped by year.
- Downloaded payloads are gitignored because the corpus can get large.
- Fetch a sample corpus with `uv run data/download.py` 

## Markdown cleanup

`clean_markdown.py` scans every filing in `markdown/`, combines adjacent duplicate
and partially duplicated span columns, and drops empty layout columns and tables.
Every header and data row must agree before columns can be combined; separate
currency, number, percentage, and parenthesis fragments are joined into one cell.
Repeated checkboxes are collapsed within their adjacent group. Different periods,
conflicting values, and nonadjacent columns are preserved. Repeated prose, data
rows, and nonempty tables are audited, not deleted.

- Preview: `python data/clean_markdown.py`
- Apply: `python data/clean_markdown.py --write`
- Tests: `python -m unittest discover -s data -p test_clean_markdown.py`

Each run writes `markdown_cleanup_report.json`, including within-file and
cross-file duplicates. Applying changes backs up originals under
`markdown_backups/<UTC timestamp>/`. Change locations reference original lines;
repetition locations reference cleaned lines. Paragraph auditing compares
whitespace-normalized blocks of at least 80 characters; it does not detect
near-duplicates or repetition embedded inside a larger paragraph.

Re-running `convert_to_markdown.py` regenerates the uncleaned Markdown, so run
the cleanup again afterward. `markdown/manifest.json` is left unchanged.
