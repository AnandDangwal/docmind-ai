# Document Copilot

An internal AI chatbot that lets analysts query a corpus of documents in plain English and get sourced, citable answers.

## The client

**Driftwood Capital** — fictional independent investment research firm. Their analysts spend half their week reading 10-Ks and 10-Qs before they can produce any original analysis. Document Copilot eats that intake work so they can skip straight to insight.

Full brief: [docs/client-brief.md](docs/client-brief.md)

## Stack

| Layer              | Choice                                               |
| ------------------ | ---------------------------------------------------- |
| Backend            | Python + FastAPI                                     |
| Frontend           | Vite + React SPA + TypeScript                        |
| Database           | Supabase Postgres (users, chats, documents, chunks)  |
| Migrations         | SQLAlchemy models + Alembic                          |
| Retrieval          | Supabase `pgvector` + Postgres full-text search      |
| Auth               | Supabase Auth (email only)                           |
| Hosting            | Railway                                              |
| LLM + embeddings   | Google Gemini                                        |

## Repo layout

```text
document-copilot/
├── AGENTS.md           # agent instructions (read first)
├── README.md           # this file
├── data/               # local corpus + download script (payloads gitignored)
├── docs/
│   └── client-brief.md # the client one-pager
├── backend/            # FastAPI service
└── frontend/           # React SPA (Vite)
```

## Prerequisites

Install these before setting up `backend/` or `frontend/`:

| Tool | Version | Used for | Install |
| ---- | ------- | -------- | ------- |
| [Python](https://www.python.org/downloads/) | 3.12+ | Backend runtime | OS package manager or python.org |
| [uv](https://docs.astral.sh/uv/getting-started/installation/) | latest | Backend deps + `data/download.py` | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| [Node.js](https://nodejs.org/) | 20+ (LTS) | Frontend toolchain | nodejs.org or `nvm install --lts` |
| [pnpm](https://pnpm.io/installation) | latest | Frontend package manager | `corepack enable && corepack prepare pnpm@latest --activate` |

You also need accounts/keys for external services once the app is wired up. Start with [docs/guides/supabase-setup.md](docs/guides/supabase-setup.md) (account + project), then create a Gemini API key in Google AI Studio for the LLM and embedding layer.

## Running locally

The commands below assume PowerShell and start from the repository root. On
macOS/Linux, replace `Copy-Item` with `cp`.

1. Create local environment files:

   ```powershell
   Copy-Item backend/.env.example backend/.env
   Copy-Item frontend/.env.example frontend/.env
   ```

   Fill in every placeholder. The backend needs the Supabase URL, anon and
   service-role keys, the direct/session Postgres URL, a Gemini API key, model
   names, allowed browser origins, and logging/pool settings. The frontend only
   receives browser-safe values: the backend URL, Supabase URL, and anon key.
   Never copy `SUPABASE_SERVICE_ROLE_KEY` or `DATABASE_URL` into `frontend/.env`.

2. Install the backend, migrate the database, and start FastAPI:

   ```powershell
   Set-Location backend
   uv sync --extra ingest
   uv run alembic upgrade head
   uv run uvicorn app.main:app --reload
   ```

   Verify [http://127.0.0.1:8000/health](http://127.0.0.1:8000/health) returns
   `{"status":"ok"}`.

3. In a second terminal, install and start the SPA:

   ```powershell
   Set-Location frontend
   pnpm install --frozen-lockfile
   pnpm dev
   ```

   Open [http://localhost:5173](http://localhost:5173), create a Supabase email
   account, and sign in.

4. If the database does not yet contain the sample corpus, run this once from
   `backend/` (Gemini embedding calls may incur cost):

   ```powershell
   uv run python -m ingest
   uv run python -m ingest.chunk_and_embed --all
   uv run python -m ingest.verify
   ```

   This seeds the active corpus from `data/markdown/manifest.json`. Corpus
   updates use an immutable staging generation, verification, and explicit
   activation; follow [backend/ingest/README.md](backend/ingest/README.md) so a
   partial update never replaces the searchable corpus.

5. With both services running and the corpus loaded, execute the ten-question
   pilot smoke test:

   ```powershell
   Set-Location backend
   uv run python pilot_smoke.py --email analyst@example.com
   ```

   The password prompt is hidden. The runner creates a separate thread per
   question, checks citations and history through a fresh HTTP session, measures
   first-event/first-text latency, cleans up its threads, and writes
   `docs/pilot-smoke-report.json`. Use `--keep-threads` when analysts should
   review the generated conversations in the UI.

Detailed setup references:

- [Supabase](docs/guides/supabase-setup.md) — account, hosted project (dashboard or CLI)
- [Backend](docs/guides/backend-setup.md)
- [Frontend](docs/guides/frontend-setup.md)

## Sample SEC data

Use the standalone downloader to fetch a small local 10-K sample from SEC EDGAR.
Edit the params at the top of `data/download.py`, especially `USER_AGENT`, then run:

```bash
uv run data/download.py
```

By default this downloads the latest 5 10-K filings for AAPL, MSFT, NVDA, AMZN, and GOOGL into year folders under `data/downloads/` and writes a `manifest.json`.
Downloaded files are gitignored; the `data/` folder itself stays in git for the script and notes.
