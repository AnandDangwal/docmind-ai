from __future__ import annotations

from app.chat.messages import (
    ChatStreamRequest,
    UIMessage,
    UIMessagePart,
    assistant_text_to_parts,
    stored_messages_to_history,
    ui_message_to_parts,
)


def test_ui_message_to_parts_dumps_each_part() -> None:
    msg = UIMessage(
        id="m1",
        role="user",
        parts=[UIMessagePart(type="text", text="hi")],
    )

    assert ui_message_to_parts(msg) == [{"type": "text", "text": "hi"}]


def test_assistant_text_to_parts_wraps_as_single_text_part() -> None:
    assert assistant_text_to_parts("stub reply") == [
        {"type": "text", "text": "stub reply"}
    ]


def test_history_only_converts_stored_text():
    from types import SimpleNamespace

    history = stored_messages_to_history(
        [
            SimpleNamespace(
                role="user",
                parts=[{"type": "text", "text": "question"}, {"type": "unknown"}],
            ),
            SimpleNamespace(
                role="assistant",
                parts=[
                    {"type": "text", "text": "answer"},
                    {"type": "data-citation", "data": {}},
                ],
            ),
        ]
    )
    assert history[0].parts[0].content == "question"
    assert history[1].parts[0].content == "answer"


def test_request_requires_latest_nonblank_user_text():
    import pytest
    from pydantic import ValidationError

    for messages in [
        [],
        [{"id": "a", "role": "assistant", "parts": []}],
        [{"id": "u", "role": "user", "parts": [{"type": "text", "text": " "}]}],
    ]:
        with pytest.raises(ValidationError):
            ChatStreamRequest.model_validate(
                {
                    "threadId": "00000000-0000-0000-0000-000000000001",
                    "messages": messages,
                }
            )
