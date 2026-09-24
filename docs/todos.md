# Implementation checklist

Work **backend-first, then a thin frontend, then retrieval, then the LLM, then polish**. The frontend is a thin authenticated chat client. Trust (citations, grounding, “I don’t know”) lives in FastAPI. Building the UI before there is an API, schema, and corpus just means you invent fake contracts.

**Why this order**

1. **Accounts + env** — nothing else boots without Supabase and OpenAI keys.
2. **Backend scaffold + schema** — the product is retrieval + grounded answers; tables and auth on the API are the contract.
3. **Frontend shell** — sign-in and a stub chat against that contract, so you can see the loop early.
4. **Ingestion** — no corpus means nothing to retrieve.
5. **Hybrid retrieval + agent + grounding** — this is the product.
6. **Citation UI + errors** — the brief’s trust bar.
7. **Deploy + analyst-shaped eval** — definition of done.

Tick boxes as you go. Architecture: [architecture.md](architecture.md). Brief: [client-brief.md](client-brief.md).

---

## Phase 0 — Accounts and local env

- [X] Create hosted Supabase project ([guides/supabase-setup.md](guides/supabase-setup.md))
- [X] Collect project URL, anon key, service-role key, direct `DATABASE_URL` (session/direct, not pooler)
- [X] Enable email auth only; for local dev, disable email confirmation if you have no inbox
- [X] Create an OpenAI API key
- [X] Fill `backend/.env` from `backend/.env.example` (never commit secrets)
- [X] Fill `frontend/.env` from `frontend/.env.example`
- [X] Confirm local tools: Python 3.12+, uv, Node 20+, pnpm

---

## Phase 1 — Backend scaffold (do this first)

Goal: FastAPI process that fails fast on missing config and can talk to Postgres.

- [X] `uv sync` / add declared backend deps (FastAPI, uvicorn, pydantic-settings, httpx, structlog, openai, supabase, pydantic-ai, sqlalchemy, alembic, psycopg, pgvector)
- [X] `app/config.py` as the only env source (`SUPABASE_*`, `DATABASE_URL`, `OPENAI_API_KEY`, `ALLOWED_ORIGINS`, embedding model + dimensions)
- [X] `app/main.py` + health route; CORS from `ALLOWED_ORIGINS`
- [ ] `app/database/supabase.py` (user-scoped vs service-role clients)
- [X] `uv run uvicorn app.main:app --reload` boots locally

---

## Phase 2 — Schema (Alembic owns tables)

Goal: product tables exist in Supabase. Do **not** create them in the dashboard.

- [ ] `alembic init`; `env.py` imports SQLAlchemy metadata and uses direct `DATABASE_URL`
- [X] SQLAlchemy models: `users`, `chat_threads`, `chat_messages`, `message_citations`, `source_documents`, `document_chunks`
- [ ] Reviewed migration with explicit ops: `vector` extension, `vector(1536)`, generated `tsvector`, HNSW, GIN, RLS + policies, grants
- [ ] `uv run alembic upgrade head` against hosted Supabase

--- 

## Phase 3 — Auth on the API

Goal: no retrieval or LLM work without a verified Supabase JWT.

- [ ] `app/auth/dependencies.py` — `Authorization: Bearer`, verify via Supabase Auth, `get_current_user`
- [ ] Reject missing/expired/invalid tokens with `401` before any privileged work
- [ ] Persist chats/messages always attached to authenticated `user_id`
- [ ] `403` if a user hits another user’s thread

---

## Phase 4 — Frontend scaffold + sign-in

Goal: analyst can open the SPA and log in with email. Still no real answers.

- [ ] Vite React-TS, Tailwind, shadcn, React Router (`pnpm` only)
- [ ] `src/lib/env.ts` validates `VITE_API_BASE_URL`, `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`
- [ ] `src/lib/supabase.ts` browser client (anon key only)
- [ ] Email sign-in / sign-up pages; session in the shared client
- [ ] Protected chat route; unauthenticated users bounce to login
- [ ] `src/lib/http.ts` + `src/lib/api.ts` — base URL, bearer injection, timeouts, typed errors (`isNetworkError`)

---

## Phase 5 — Chat loop with a stub assistant

Goal: end-to-end request path before ingestion or the real model. Proves streaming + persistence.

- [ ] FastAPI thread CRUD: create thread, list own threads, load message history
- [ ] `POST /chat/stream` accepts AI SDK-shaped `{ threadId, messages }`
- [ ] Stub stream (fixed text) in AI SDK event format
- [ ] Persist user + assistant messages after a successful stub turn
- [ ] Frontend: AI SDK `useChat` + `DefaultChatTransport` pointing at FastAPI (not a Vite route)
- [ ] Thread list + new chat in the UI

---

## Phase 6 — Corpus ingestion

Goal: sample 10-Ks become searchable rows. Download script already exists; ingestion does not.

- [ ] Run `uv run data/download.py` from repo root (set `USER_AGENT`); confirm `data/downloads/` + `manifest.json`
- [ ] `backend/ingest/`: HTML/filing → normalized Markdown on `source_documents`
- [ ] Chunk with page/section metadata (ticker, company, filing type, date, year, accession, page, offsets)
- [ ] Embed chunks (configured OpenAI model); write `document_chunks` including `tsvector`
- [ ] Idempotent re-run (same filing does not duplicate blindly)
- [ ] Unit tests for parse/chunk (no network)

---

## Phase 7 — Hybrid retrieval

Goal: a question returns bounded, ranked passages. Testable without the LLM.

- [ ] Query embed → `pgvector` search on `document_chunks.embedding`
- [ ] Postgres full-text on `document_chunks.search_vector`
- [ ] Reciprocal Rank Fusion in Python
- [ ] Fetch selected chunks + document metadata + optional neighbors
- [ ] Bounded tools for the agent later: `search_filings`, `read_chunk`, `read_surrounding_chunks` (no agent-generated SQL)
- [ ] Unit tests for fusion + ranking policy

---

## Phase 8 — PydanticAI agent (grounded answers)

Goal: typed assistant that answers only from retrieved passages.

- [ ] `assistant/outputs.py` — `GroundedAnswer`, `Citation`, `SourcePassage`
- [ ] `assistant/deps.py` — request-scoped deps (user, thread, retriever, validator)
- [ ] `assistant/instructions.md` — corpus only; cite every claim; refuse if insufficient; no stock picks / investment advice
- [ ] `assistant/agent.py` + `chat/orchestrator.py` for one full turn
- [ ] Stream text deltas + citation/source parts to the browser
- [ ] Persist citations on `message_citations` after a successful run

---

## Phase 9 — Grounding (trust is code, not a prompt)

Matches the brief: never invent facts; always cite; show the passage.

- [ ] Every answer has ≥1 citation **or** an explicit “not enough evidence” refusal
- [ ] Every citation maps to a passage retrieved for **this** request
- [ ] Cited payload includes company, filing, date, page/section, excerpt
- [ ] Validation failure → controlled error, not a polished unsupported answer
- [ ] Unit tests for citation extraction + grounding (required)

---

## Phase 10 — Chat UI that analysts will actually use

- [ ] Render citations as filing + page (click → underlying passage)
- [ ] Passage panel / drawer for one-click verify
- [ ] Empty states, streaming status, auth/network vs HTTP errors
- [ ] Own past conversations only
- [ ] `pnpm tsc --noEmit` and `pnpm lint` clean
- [ ] Manual browser pass: login → new thread → question → citation → passage → history

---

## Phase 11 — Brief quality bar (pilot questions)

Use the sample corpus (AAPL, AMZN, GOOGL, MSFT, NVDA 10-Ks). For each, the bot should cite passages or refuse to infer.

- [ ] Apple revenue mix 2021–2025 (iPhone, Services, Mac, iPad, Wearables)
- [ ] Amazon AWS vs NA vs International operating income/margin
- [ ] NVIDIA Data Center demand, concentration, supply constraints
- [ ] Microsoft Azure / AI infra / capacity language over time
- [ ] Alphabet segment revenue trends
- [ ] Risk-factor language on AI, cloud, export controls, supply chain, regulation
- [ ] Apple + NVIDIA supplier / manufacturing dependence
- [ ] Capex and purchase commitments (MSFT, GOOGL, AMZN, NVDA)
- [ ] Geographic revenue exposures, latest 10-K + YoY
- [ ] “Did generative AI improve margins?” — evidence only; refuse beyond filings

---

## Phase 12 — Deploy (small cloud footprint)

- [ ] Railway backend: Uvicorn, env vars, CORS for the real frontend origin
- [ ] Railway frontend: Vite static build, `VITE_*` for prod Supabase + API URL
- [ ] Production auth: re-enable email confirmation if it was off for local
- [ ] Confirm service-role key never in the frontend
- [ ] Smoke: sign in on prod URL, one grounded question, citations persist

---

## Explicitly out of scope (do not add)

- Trading recommendations / stock picks
- News, social, alternative data
- Multi-tenant / billing / mobile app
- Next.js, SSR, frontend calling OpenAI
- Vector DB other than Supabase `pgvector`
- Frontend unit/e2e test suite (browser + `tsc` + lint only)

---

## Definition of done (from the brief)

Pilot (5 senior analysts), one week: **≥3 hours saved per analyst per week**, answers trusted enough to use as intake, every claim citable to filing + page with the passage visible. If yes, firm-wide rollout.
