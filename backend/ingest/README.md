# Local document ingestion

Run these commands from `backend/`. The ingestion dependencies are optional and
are not needed by the deployed FastAPI service.

The files under `data/markdown/` are the authoritative ingestion corpus. They
were converted from the downloaded SEC HTML with `data/convert_to_markdown.py`
and use Docling headings for section metadata when available. Otherwise, the
pipeline propagates SEC `Item 1.` through `Item 16.` markers through their
following chunks. The pipeline recovers page provenance when the original HTML
contains a recognized branded page footer (currently Apple's filing format).
Unsupported formats store `page = NULL`; page numbers are never guessed.

```powershell
uv sync --extra ingest
```

The CLI has no default target. Select either one accession or the entire
Markdown manifest. Existing documents are skipped unless `--force` is supplied.

## Required validation sequence

Preview one deterministic chunk without calling Gemini or writing to Postgres:

```powershell
uv run python -m ingest.chunk_and_embed `
  --accession 0000320193-23-000106 `
  --max-chunks 1 `
  --dry-run
```

Validate chunking for all 25 filings without calling Gemini or writing rows:

```powershell
uv run python -m ingest.chunk_and_embed --all --dry-run
```

After reviewing the preview, create one live Gemini embedding and one database row:

```powershell
uv run python -m ingest.chunk_and_embed `
  --accession 0000320193-23-000106 `
  --max-chunks 1
```

Verify that row in Supabase before continuing. It must have a 1,536-dimension
embedding, a token count no greater than 512, the expected document metadata,
and a populated generated `search_vector`.

Replace the one-row smoke result with the complete filing:

```powershell
uv run python -m ingest.chunk_and_embed `
  --accession 0000320193-23-000106 `
  --force
```

Only after that succeeds, process the remaining manifest entries:

```powershell
uv run python -m ingest.chunk_and_embed --all
```

The final command skips the filing promoted in the prior step. Use `--all
--force` when the embedding model changes and every stored vector must be
replaced.

Verify complete manifest coverage, embedding dimensions, generated search
vectors, token limits, and the Apple revenue-mix spot check:

```powershell
uv run python -m ingest.verify
```
