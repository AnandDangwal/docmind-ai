# Phase 8 readiness report

Date: 2026-11-19

Phase 7 is complete, so the repository was ready to enter Phase 8. The fast
backend baseline passed (123 tests) before the Phase 8 changes and 124 tests
passed afterward.

## Implemented

- Replaced the root README placeholder with copy-paste backend, frontend,
  migration, initial-corpus, and pilot commands plus the complete environment
  variable split.
- Documented initial seeding and the existing staged corpus update/verification/
  activation workflow.
- Added `backend/pilot_smoke.py` for the exact ten client-brief questions. It
  calls the authenticated API, checks citations and persisted history in a new
  HTTP session, checks Question 10's causal boundary, measures first-event and
  first-text latency, and writes a JSON report.
- Confirmed chat state is Postgres-backed and every thread route checks the
  authenticated owner. No user or thread is stored in process-global state.
- Made the database pool assumptions explicit: 5 persistent connections plus
  10 overflow connections by default. The application and database paths have
  no single-user state, but the live Gemini failures mean ~40-user capacity is
  not yet validated; provider quota and load testing remain prerequisites.
- Configured `structlog` JSON output and added request IDs plus per-turn stage,
  duration, status, and citation-count events. Questions and answers are not
  logged.

## Live acceptance result

The ten-question authenticated run completed against the populated environment:

- Question 10 passed with persisted history and 7 citations.
- Questions 1–9 returned the controlled Gemini busy/quota response after both
  the primary and fallback models were tried. They produced no answer text or
  citations, so the analyst pilot is not ready to start.
- Every first SSE event arrived in 606.9–707.0 ms, comfortably inside the
  three-second stream-start target. The successful answer's first text arrived
  after 32.2 seconds, which remains a user-experience concern for broad research
  turns even though progress is visible immediately.
- The isolated Supabase test user and generated threads were removed afterward.

After the Gemini usage reset, Questions 1 and 2 immediately reproduced the same
primary/fallback busy response. A diagnostic rerun with broad-research map calls
serialized also reproduced it, so the temporary concurrency change was reverted.

The latest reset-usage retry evidence is in `docs/pilot-smoke-report.json`; the
completed ten-question run is summarized above. Phase 8 is not complete:
provision sufficient Gemini capacity/quota, obtain a clean 10/10 rerun, then run
the five-analyst week and confirm the time-savings goal.
