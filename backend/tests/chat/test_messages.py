from __future__ import annotations

from app.chat.messages import (
    UIMessage,
    UIMessagePart,
    assistant_text_to_parts,
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
    assert assistant_text_to_parts("stub reply") == [{"type": "text", "text": "stub reply"}]
