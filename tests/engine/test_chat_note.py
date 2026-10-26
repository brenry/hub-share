"""The Hub's own line in its chat: a module's `chat.note` {"text"} adds one
`hub` message, shown at once; on the next `user` message it goes to the model as a `user` message "Hub note: <text>"
right before it; a note with no `user` message after it is not sent; New chat and the purge remove it as any message. A
conversation with no note wires byte for byte as `old_wire` does."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from hub.modules.assistant import chat, turns
from tests.core.harness import Hub, own_modules, start_hub
from tests.fakes.openwebui import FakeOpenWebUI, settled


@pytest.fixture
def owui():  # type: ignore[no-untyped-def]
    fake = FakeOpenWebUI()
    yield fake
    fake.close()


@pytest.fixture
async def hub(tmp_path: Path):  # type: ignore[no-untyped-def]
    h = await start_hub(tmp_path / "data", modules=own_modules())
    yield h
    await h.close()


def w(role: str, content: str, **extra: object) -> dict:
    return {"role": role, "content": content, **extra}


def m(role: str, text: str, **extra: object) -> dict:
    return {"id": text, "role": role, "text": text, "at": 0.0, "seconds": None, **extra}


def note(text: str) -> dict:
    return w("user", f"Hub note: {text}")


def old_wire(messages: list[dict]) -> list[dict]:
    """chat.wire without the `hub` role: a conversation with no note must wire byte-identical to it."""
    out = []
    for x in messages:
        if x["role"] in ("user", "assistant"):
            item = {"role": x["role"], "content": x["text"]}
            if x.get("output"):
                item["output"] = x["output"]
            out.append(item)
    return turns.lean(out)


TOOLS = [{"type": "function_call", "call_id": "c1", "name": "set", "arguments": "{}"},
         {"type": "function_call_output", "call_id": "c1", "output": "line one\n" + "x" * 300}]


def test_notes_go_before_the_users_next_message_in_their_order() -> None:
    sent = [w("hub", "n0"), w("user", "u1"), w("hub", "n1"), w("assistant", "a1"), w("hub", "n2"),
            w("user", "u2"), w("assistant", "a2"), w("hub", "n3"), w("hub", "n4"), w("user", "u3"), w("hub", "late")]
    assert turns.notes(sent) == [
        note("n0"), w("user", "u1"), w("assistant", "a1"), note("n1"), note("n2"), w("user", "u2"),
        w("assistant", "a2"), note("n3"), note("n4"), w("user", "u3")], "each reply stays after what it answers"
    assert turns.notes([w("user", "u1"), w("hub", "n")]) == [w("user", "u1")], "a trailing note is not sent"
    assert turns.notes([w("hub", "n")]) == []
    plain = [w("user", "u1"), w("assistant", "a1", output=TOOLS)]
    assert turns.notes(plain) is plain, "no note: the list given, as it is"
    assert sent[0] == w("hub", "n0"), "pure: the messages given are not changed"


async def test_a_note_is_added_shown_and_sent_before_the_users_next_message(hub: Hub, owui: FakeOpenWebUI) -> None:
    cookie = hub.pair()
    await hub.http("PATCH", "/api/assistant/openwebui", cookie, {"url": owui.url, "key": "k", "model": "q"})
    scr = await hub.screen(cookie, "workspace", "w")
    await hub.http("POST", "/api/assistant/chat", cookie, {"text": "first"})
    await settled(scr, 2)
    hub.core.events.emit("chat.note",
                         {"text": "Character 7 Meets Character 8: 4 takes: 3 ok, 1 flagged: l2 heard 62 %"})
    view = await settled(scr, 3)
    assert view["messages"][2] | {"id": "", "at": 0} == {
        "id": "", "role": "hub", "text": "Character 7 Meets Character 8: 4 takes: 3 ok, 1 flagged: l2 heard 62 %",
        "at": 0,
        "seconds": None}, "shown at once, without seconds"
    assert len(owui.requests) == 1, "a note alone asks nothing"
    for bad in ({}, {"text": ""}, {"text": "  "}, {"text": 7}):
        hub.core.events.emit("chat.note", bad)
    hub.core.events.emit("chat.note", {"text": "second note"})
    view = await settled(scr, 4)
    assert [x["role"] for x in view["messages"]] == ["user", "assistant", "hub", "hub"], "an empty note adds nothing"
    await hub.http("POST", "/api/assistant/chat", cookie, {"text": "what now?"})
    await settled(scr, 6)
    assert owui.requests[1]["body"]["messages"] == [
        w("user", "first"), w("assistant", "Hello from Open WebUI."),
        note("Character 7 Meets Character 8: 4 takes: 3 ok, 1 flagged: l2 heard 62 %"), note("second note"),
        w("user", "what now?")]
    hub.core.store.flush()
    assert sorted(p.name for p in (hub.data / "assistant").iterdir()) == ["openwebui.json"], "nothing on disk"
    hub.core.events.emit("chat.note", {"text": "after the reply"})
    await settled(scr, 7)
    cleared = (await hub.http("DELETE", "/api/assistant/chat", cookie)).json()
    assert cleared["messages"] == [], "New chat removes the notes as any message"
    await scr.close()


async def test_a_note_without_a_message_after_it_is_not_sent(hub: Hub) -> None:
    session = chat.get(hub.core.ctxs["assistant"])
    session.messages = [m("user", "u1"), m("hub", "landed during the turn")]
    assert session.wire() == [w("user", "u1")], "it goes on the next turn"
    session.messages.append(m("assistant", "a1"))
    session.messages.append(m("user", "u2"))
    assert session.wire() == [w("user", "u1"), w("assistant", "a1"), note("landed during the turn"), w("user", "u2")]


async def test_a_conversation_with_no_note_wires_byte_identical(hub: Hub) -> None:
    session = chat.get(hub.core.ctxs["assistant"])
    cases = [
        [],
        [m("user", "u1")],
        [m("user", "u1"), m("assistant", "a1"), m("user", "u2")],
        [m("user", "u1"), m("error", "e1"), m("user", "u2"), m("assistant", "", output=TOOLS), m("user", "u3")],
        [m("user", "u1"), m("assistant", "a1", output=TOOLS), m("user", "u2"), m("assistant", "a2", output=TOOLS),
         m("error", "e2")],
        [m("assistant", "a0"), m("user", "u1"), m("assistant", "a1", output=[])],
    ]
    for case in cases:
        session.messages = case
        assert json.dumps(session.wire()).encode() == json.dumps(old_wire(case)).encode(), case


def test_a_note_starts_no_exchange_and_goes_with_its_own() -> None:
    msgs = [m("hub", "h0"), m("user", "u1"), m("assistant", "a1"), m("hub", "h1"), m("user", "u2"),
            m("hub", "h2"), m("assistant", "a2")]
    old = msgs[:4]
    kept, gone = turns.purge(msgs, 1)
    assert [x["text"] for x in kept] == ["u2", "h2", "a2"] and gone == 4
    assert all(x == {} for x in old), "the purged notes are emptied, as any message"
    kept, gone = turns.purge([m("hub", "h0"), m("user", "u1"), m("hub", "h1")], 1)
    assert gone == 0 and len(kept) == 3, "two notes and one exchange: one exchange, nothing purged"
