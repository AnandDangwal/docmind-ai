# Backend

FastAPI service for Document Copilot. Run all commands from this folder.

## Setup

```bash
uv sync
cp .env.example .env   # fill in keys; never commit .env
```

## Run

```bash
uv run uvicorn app.main:app --reload
```

Health check: [http://localhost:8000/health](http://localhost:8000/health)  
API docs: [http://localhost:8000/docs](http://localhost:8000/docs)

Same app via `uv run python app/main.py`.

## Other commands

```bash
uv run pytest -m "not integration"
uv run ruff check .
uv run alembic upgrade head   # once Alembic is initialized
```

## Grounded assistant (Phase 6)

Add these required settings to your local `.env` before starting the backend:

```dotenv
GEMINI_CHAT_MODEL=gemini-3.8-flash
GEMINI_FALLBACK_CHAT_MODEL=gemini-3.5-flash-lite
GEMINI_REASONING_EFFORT=medium
GEMINI_EMBEDDING_MODEL=gemini-embedding-2
GEMINI_EMBEDDING_DIMENSIONS=1536
```

Transient Gemini failures (HTTP 408, 429, and retryable 5xx responses) switch
immediately from the primary model to the fallback model, which gets one bounded
retry. Keep the two model IDs distinct so a capacity spike on one model does not
fail the whole turn.

`POST /chat/stream` accepts `{ "threadId": "uuid", "messages": [...] }` with
AI SDK UI messages and a final nonblank user text message. The server loads prior
history from the owned thread; client-supplied historical messages are ignored.
The user's question is committed before retrieval. The agent receives an initial
hybrid search and can make up to three follow-up searches and eight tool calls,
with at most 40 exposed chunks. Only exposed chunks can be cited.

The complete typed answer is validated before any answer text is sent. The SSE
response includes a server message ID, text deltas, persistent `data-citation`
parts, and the AI SDK finish marker. A citation contains filing identity, page
(nullable), section, source URL, and an exact chunk excerpt. After sending the
answer parts, the backend stores the assistant message and normalized citations
in one transaction before the stream signals success. An interruption before
persistence stores no assistant answer; if delivery stops after the commit, the
saved answer is available when the thread is reloaded.

Validation checks citation membership, marker consistency, and citation coverage
on each prose line. It does not prove semantic entailment: the prompt and live
review of analyst answers remain necessary. Retrieval/model/validation failures
return a controlled 502 before streaming, leaving the user question available.
Persistence failures roll back the assistant transaction, send an AI SDK error
event without a success finish event, and show an error in the chat view.
Earlier validated text may be visible until the thread is reloaded.

Run unit tests with `uv run pytest -m "not integration"`. Run live checks
with `uv run pytest tests/assistant/test_grounding_integration.py -m integration -s`.
These require Gemini access and a populated Supabase corpus. The corpus must use
real embeddings from the configured model to validate semantic relevance.

For Question 10, review the printed answer to confirm it distinguishes disclosed
figures from causal inference and does not claim generative AI proved margin
improvements. Page provenance is nullable; section references are used when a
reliable page is unavailable. Citation rendering belongs to Phase 7.

## Phase 8 pilot smoke test

With the backend running against the populated corpus, exercise the exact ten
questions from the client brief through the authenticated HTTP API:

```powershell
uv run python pilot_smoke.py --email analyst@example.com
```

The runner records status, citation count, persisted history, first SSE event,
first answer text, and total outcome in `../docs/pilot-smoke-report.json`. It
uses a fresh HTTP client to reload each thread, so persistence is verified
across sessions rather than from process memory. Use `--api-url` for a deployed
backend and `--keep-threads` to retain the review threads.

Application logs are JSON. Each HTTP request has a request ID, and chat-turn
events include user, thread, message, stage timing, answer status, and citation
count without logging question or answer text.
