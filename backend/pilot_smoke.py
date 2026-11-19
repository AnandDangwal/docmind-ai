from __future__ import annotations

import argparse
import asyncio
import getpass
import json
import secrets
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any
from uuid import UUID, uuid4

import httpx
from supabase import create_client

from app.config import settings

QUESTIONS = (
    "Across Apple's 2021-2025 10-Ks, how did the revenue mix between iPhone, Services, Mac, iPad, and Wearables change, and which category appears to have contributed most to any mix shift?",
    "For Amazon, compare AWS operating income and margin against North America and International from 2021-2025. In which years did AWS appear to fund losses or weaker profitability elsewhere?",
    "How did NVIDIA describe demand drivers, customer concentration, and supply constraints for its Data Center business from fiscal 2021 through fiscal 2025?",
    "Across Microsoft's 2021-2025 filings, what changed in the way the company describes Azure, AI infrastructure, and cloud capacity constraints?",
    "For Alphabet, how did Google Search, YouTube ads, Google Network, subscriptions/platforms/devices, and Google Cloud revenue trends differ across the available 10-Ks?",
    "Which of the five companies added, removed, or materially changed risk-factor language related to AI, cloud infrastructure, export controls, supply chain concentration, or regulation between 2021 and 2025?",
    "For Apple and NVIDIA, what do the filings say about supplier concentration or dependence on third-party manufacturing, and did the wording become more or less urgent over time?",
    "Compare capital expenditures and purchase commitments for Microsoft, Alphabet, Amazon, and NVIDIA. What do the filings imply about the scale and timing of AI/cloud infrastructure investment?",
    "For each company, summarize the most important geographic revenue exposures disclosed in the latest 10-K, then identify any year-over-year changes that could matter to an analyst.",
    "If an analyst asks whether the filings prove that generative AI improved margins for any of these companies, what evidence exists in the corpus, and where should the bot refuse to infer beyond the filings?",
)

_CAUSAL_BOUNDARY_PHRASES = (
    "does not prove",
    "do not prove",
    "does not establish",
    "do not establish",
    "does not demonstrate",
    "do not demonstrate",
    "cannot conclude",
    "cannot be established",
    "cannot infer",
    "cannot attribute",
    "not enough evidence",
    "insufficient evidence",
)


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the ten client-brief questions through the real chat API."
    )
    parser.add_argument("--api-url", default="http://127.0.0.1:8000")
    identity = parser.add_mutually_exclusive_group(required=True)
    identity.add_argument("--email", help="Pilot user's Supabase email address")
    identity.add_argument(
        "--access-token",
        help="Existing Supabase access token; prefer --email to keep tokens out of shell history",
    )
    identity.add_argument(
        "--temporary-user",
        action="store_true",
        help="Create and remove an isolated Supabase user for this run",
    )
    parser.add_argument(
        "--max-first-event-seconds",
        type=float,
        default=3.0,
        help="Maximum acceptable time to the first SSE status event",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=Path(__file__).resolve().parent.parent
        / "docs"
        / "pilot-smoke-report.json",
    )
    parser.add_argument(
        "--keep-threads",
        action="store_true",
        help="Keep the ten generated pilot threads instead of cleaning them up",
    )
    return parser.parse_args()


def _access_token(args: argparse.Namespace) -> tuple[str, UUID | None]:
    if args.access_token:
        return args.access_token, None
    if args.temporary_user:
        email = f"phase8-{uuid4().hex}@example.com"
        password = secrets.token_urlsafe(32)
        admin = create_client(
            settings.supabase_url,
            settings.supabase_service_role_key.get_secret_value(),
        )
        created = admin.auth.admin.create_user(
            {"email": email, "password": password, "email_confirm": True}
        )
        if created.user is None:
            raise SystemExit("Supabase did not create the temporary pilot user.")
        try:
            anon = create_client(
                settings.supabase_url, settings.supabase_anon_key.get_secret_value()
            )
            response = anon.auth.sign_in_with_password(
                {"email": email, "password": password}
            )
            if response.session is None:
                raise RuntimeError("Supabase did not return an authenticated session.")
        except Exception:
            admin.auth.admin.delete_user(str(created.user.id))
            raise
        return response.session.access_token, UUID(str(created.user.id))

    password = getpass.getpass(f"Password for {args.email}: ")
    supabase = create_client(
        settings.supabase_url, settings.supabase_anon_key.get_secret_value()
    )
    response = supabase.auth.sign_in_with_password(
        {"email": args.email, "password": password}
    )
    if response.session is None:
        raise SystemExit("Supabase did not return an authenticated session.")
    return response.session.access_token, None


def _delete_temporary_user(user_id: UUID) -> None:
    from sqlalchemy import create_engine, delete, make_url
    from sqlalchemy.orm import Session

    from app.database.models import User

    url = make_url(settings.database_url.get_secret_value())
    if url.drivername == "postgresql":
        url = url.set(drivername="postgresql+psycopg")
    engine = create_engine(url.render_as_string(hide_password=False), pool_pre_ping=True)
    try:
        with Session(engine) as session, session.begin():
            session.execute(delete(User).where(User.id == user_id))
    finally:
        engine.dispose()
    admin = create_client(
        settings.supabase_url,
        settings.supabase_service_role_key.get_secret_value(),
    )
    admin.auth.admin.delete_user(str(user_id))


def _milliseconds(started_at: float) -> float:
    return round((perf_counter() - started_at) * 1_000, 1)


async def _persisted_history(
    *, api_url: str, headers: dict[str, str], thread_id: str
) -> tuple[bool, int]:
    # A new client verifies that history is server-side, not connection-local state.
    async with httpx.AsyncClient(
        base_url=api_url, headers=headers, timeout=60
    ) as reload_client:
        response = await reload_client.get(f"/chat/threads/{thread_id}/messages")
        response.raise_for_status()
        messages = response.json()
    roles = [message.get("role") for message in messages]
    return "user" in roles and "assistant" in roles, len(messages)


async def _run_question(
    client: httpx.AsyncClient,
    *,
    api_url: str,
    headers: dict[str, str],
    number: int,
    question: str,
    max_first_event_seconds: float,
    keep_thread: bool,
) -> dict[str, Any]:
    thread_response = await client.post(
        "/chat/threads", json={"title": f"Phase 8 pilot question {number}"}
    )
    thread_response.raise_for_status()
    thread_id = thread_response.json()["id"]
    started_at = perf_counter()
    first_event_ms: float | None = None
    first_text_ms: float | None = None
    answer_status: str | None = None
    error: str | None = None
    finished = False
    citations = 0
    answer_parts: list[str] = []

    try:
        payload = {
            "threadId": thread_id,
            "messages": [
                {
                    "id": str(uuid4()),
                    "role": "user",
                    "parts": [{"type": "text", "text": question}],
                }
            ],
        }
        async with client.stream("POST", "/chat/stream", json=payload) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line.startswith("data: "):
                    continue
                if first_event_ms is None:
                    first_event_ms = _milliseconds(started_at)
                raw_event = line.removeprefix("data: ")
                if raw_event == "[DONE]":
                    break
                event = json.loads(raw_event)
                event_type = event.get("type")
                if event_type == "text-delta":
                    if first_text_ms is None:
                        first_text_ms = _milliseconds(started_at)
                    answer_parts.append(event.get("delta", ""))
                elif event_type == "data-citation":
                    citations += 1
                elif event_type == "data-answer-status":
                    answer_status = event.get("data", {}).get("status")
                elif event_type == "error":
                    error = event.get("errorText", "Unknown stream error")
                elif event_type == "finish":
                    finished = True

        persisted, persisted_messages = await _persisted_history(
            api_url=api_url, headers=headers, thread_id=thread_id
        )
        answer = "".join(answer_parts)
        causal_boundary = number != 10 or any(
            phrase in answer.casefold() for phrase in _CAUSAL_BOUNDARY_PHRASES
        )
        first_event_within_budget = (
            first_event_ms is not None
            and first_event_ms <= max_first_event_seconds * 1_000
        )
        passed = all(
            (
                finished,
                error is None,
                citations > 0,
                persisted,
                first_event_within_budget,
                causal_boundary,
            )
        )
        return {
            "number": number,
            "question": question,
            "passed": passed,
            "answer_status": answer_status,
            "citation_count": citations,
            "history_persisted": persisted,
            "persisted_message_count": persisted_messages,
            "first_event_ms": first_event_ms,
            "first_text_ms": first_text_ms,
            "total_ms": _milliseconds(started_at),
            "causal_boundary_present": causal_boundary,
            "error": error,
            "answer": answer,
        }
    finally:
        if not keep_thread:
            try:
                cleanup = await client.delete(f"/chat/threads/{thread_id}")
                cleanup.raise_for_status()
            except httpx.HTTPError as exc:
                print(f"  Thread cleanup deferred: {type(exc).__name__}", flush=True)


def _report(
    args: argparse.Namespace,
    results: list[dict[str, Any]],
    *,
    interrupted_by: str | None = None,
) -> dict[str, Any]:
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "api_url": args.api_url.rstrip("/"),
        "max_first_event_seconds": args.max_first_event_seconds,
        "questions_passed": sum(result["passed"] for result in results),
        "questions_completed": len(results),
        "questions_total": len(QUESTIONS),
        "all_passed": len(results) == len(QUESTIONS)
        and all(result["passed"] for result in results),
        "interrupted_by": interrupted_by,
        "results": results,
    }


def _write_report(args: argparse.Namespace, report: dict[str, Any]) -> None:
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


async def _run(args: argparse.Namespace, token: str) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {token}"}
    timeout = httpx.Timeout(900, connect=30)
    results: list[dict[str, Any]] = []
    async with httpx.AsyncClient(
        base_url=args.api_url.rstrip("/"), headers=headers, timeout=timeout
    ) as client:
        health = await client.get("/health")
        health.raise_for_status()
        for number, question in enumerate(QUESTIONS, start=1):
            print(f"[{number}/10] {question}", flush=True)
            try:
                result = await _run_question(
                    client,
                    api_url=args.api_url.rstrip("/"),
                    headers=headers,
                    number=number,
                    question=question,
                    max_first_event_seconds=args.max_first_event_seconds,
                    keep_thread=args.keep_threads,
                )
            except httpx.HTTPError as exc:
                result = {
                    "number": number,
                    "question": question,
                    "passed": False,
                    "error": f"{type(exc).__name__}: {exc}",
                }
                results.append(result)
                report = _report(args, results, interrupted_by=type(exc).__name__)
                _write_report(args, report)
                print(f"  INTERRUPTED | {result['error']}", flush=True)
                return report
            results.append(result)
            _write_report(args, _report(args, results))
            print(
                f"  {'PASS' if result['passed'] else 'FAIL'} | "
                f"first event {result['first_event_ms']} ms | "
                f"first text {result['first_text_ms']} ms | "
                f"{result['citation_count']} citations",
                flush=True,
            )

    return _report(args, results)


def main() -> None:
    args = _arguments()
    token, temporary_user_id = _access_token(args)
    try:
        report = asyncio.run(_run(args, token))
    finally:
        if temporary_user_id is not None:
            _delete_temporary_user(temporary_user_id)
    print(f"Report written to {args.report}")
    if not report["all_passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
