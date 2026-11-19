# Local document ingestion

Run these commands from `backend/`. The ingestion dependencies are optional and
are not needed by the deployed FastAPI service.

The files under `data/markdown/` are the authoritative ingestion corpus. They
were converted from the downloaded SEC HTML with `data/convert_to_markdown.py`.
The converter restores canonical PART/ITEM headings and high-confidence bold
subsections after Docling conversion. Chunk metadata retains the section path,
stable HTML anchor, extraction confidence, and extractor version. Verified page
markers are used when present; otherwise citations fall back to the SEC section
or HTML anchor. Page numbers are never guessed.

```powershell
uv sync --extra ingest
```

Apply migrations before creating a new corpus generation:

```powershell
uv run alembic upgrade head
```

The CLI has no default target. Select either one accession or the entire
Markdown manifest. Production re-indexes are immutable staging generations;
the active generation remains searchable until the staging generation passes
verification and is explicitly activated.

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

Create normalized staging Markdown from the original SEC HTML (run from the
repository root):

```powershell
uv run --project backend data/convert_to_markdown.py --staging
```

From `backend/`, preview the staging corpus without embeddings or writes:

```powershell
uv run python -m ingest.chunk_and_embed `
  --all `
  --manifest ../data/markdown_staging/manifest.json `
  --dry-run
```

Embed all filings into a new staging generation:

```powershell
uv run python -m ingest.chunk_and_embed `
  --all `
  --manifest ../data/markdown_staging/manifest.json `
  --new-generation `
  --no-skip-existing
```

Verify the staging generation. This records a passing verification report but
does not change live retrieval:

```powershell
uv run python -m ingest.verify `
  --staging-generation `
  --manifest ../data/markdown_staging/manifest.json
```

Activate the generation ID printed by the embedding command:

```powershell
uv run python -m ingest.activate_generation <generation-id>
```

The same activation command can reactivate a verified retired generation for
rollback. Old chunks remain available to historical chat citations. A retired
generation must not be deleted while any `message_citations` row references it.
