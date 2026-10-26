"""The conversation keeps only the last `keep` exchanges: after each turn everything older is deleted, from the
hub's memory (neither shown nor sent again) and, in tool-server mode, from Open WebUI (its chat is deleted and the
next turn makes a new one). The fake Open WebUI is tests/fakes/openwebui.py's."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from hub.core.api import Invalid
from hub.modules.assistant import chat, turns
from tests.core.harness import Hub, own_modules, start_hub
from tests.fakes.openwebui import TOOL_OUTPUT, FakeOpenWebUI, calls, settled, tool_hub, until
from tests.fakes.screen import Screen


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


def m(role: str, text: str = "x") -> dict:
    return {"id": text, "role": role, "text": text, "at": 0.0}


def test_an_exchange_is_your_message_and_everything_after_it() -> None:
    msgs = [m("user", "u1"), m("assistant", "a1"), m("user", "u2"), m("assistant", ""), m("error", "e2"),
            m("user", "u3"), m("error", "e3"), m("user", "u4"), m("assistant", "a4")]
    old = msgs[:5]
    kept, gone = turns.purge(msgs, 2)
    assert [x["text"] for x in kept] == ["u3", "e3", "u4", "a4"] and gone == 5
    assert all(x == {} for x in old), "the deleted messages are emptied, not just dropped"
    kept, gone = turns.purge(kept, 2)
    assert len(kept) == 4 and gone == 0
    msgs = [m("user", "u1"), m("assistant", ""), m("error", "e1"), m("user", "u2")]
    kept, gone = turns.purge(msgs, 1)
    assert [x["text"] for x in kept] == ["u2"] and gone == 3, "a tools-only turn and its error go with their exchange"
    assert turns.purge([], 1) == ([], 0)


def test_keep_bounds() -> None:
    assert (turns.KEEP, turns.LOW, turns.HIGH) == (6, 1, 20)
    for good in (1, 6, 20):
        assert turns.count(good) == good
    for bad in (0, 21, -1, "6", 6.0, True, None, [6]):
        with pytest.raises(Invalid) as e:
            turns.count(bad)
        assert (e.value.field, e.value.text) == ("keep", "Replies kept must be a whole number from 1 to 20")
    assert [turns.saved(v) for v in (None, "9", True, 3.5, 0, 99, 9)] == [6, 6, 6, 6, 1, 20, 9]


async def test_the_setting_defaults_to_six_is_checked_and_saved(hub: Hub, owui: FakeOpenWebUI) -> None:
    cookie = hub.pair()
    assert (await hub.http("GET", "/api/assistant", cookie)).json()["openwebui"]["keep"] == 6
    r = await hub.http("PATCH", "/api/assistant/openwebui", cookie, {"url": owui.url, "keep": 3})
    assert r.status == 200 and r.json()["openwebui"]["keep"] == 3 and r.json()["openwebui"]["url"] == owui.url
    for bad in (0, 21, "4", 2.5, True, None):
        r = await hub.http("PATCH", "/api/assistant/openwebui", cookie, {"keep": bad})
        assert r.status == 400 and r.json()["field"] == "keep", bad
        assert r.json()["text"] == "Replies kept must be a whole number from 1 to 20"
    r = await hub.http("PATCH", "/api/assistant/openwebui", cookie, {"keep": 20, "model": "q"})
    assert r.json()["openwebui"]["keep"] == 20
    hub.core.store.flush()
    saved = json.loads((hub.data / "assistant" / "openwebui.json").read_text())
    assert saved == {"url": owui.url, "key": "", "model": "q", "tools": "", "keep": 20, "context": 8192}
    session = chat.get(hub.core.ctxs["assistant"])
    session.settings.patch({"keep": "lots"})   # a hand-edited file: the default
    assert session.config()["keep"] == 6
    session.settings.patch({"keep": 400})
    assert session.config()["keep"] == 20


async def say(hub: Hub, cookie: str, w: Screen, text: str, count: int) -> dict:
    assert (await hub.http("POST", "/api/assistant/chat", cookie, {"text": text})).status == 202
    return await settled(w, count)


async def test_the_seventh_exchange_deletes_the_first(hub: Hub, owui: FakeOpenWebUI) -> None:
    cookie = hub.pair()
    await hub.http("PATCH", "/api/assistant/openwebui", cookie, {"url": owui.url, "key": "sk-abc", "model": "q"})
    w = await hub.screen(cookie, "workspace", "w")
    for i in range(1, 7):
        owui.reply = {"choices": [{"message": {"role": "assistant", "content": f"reply {i}"}}]}
        view = await say(hub, cookie, w, f"turn {i}", 2 * i)
    assert len(owui.requests[-1]["body"]["messages"]) == 11, "six exchanges are all kept"
    owui.reply = {"choices": [{"message": {"role": "assistant", "content": "reply 7"}}]}
    view = await say(hub, cookie, w, "turn 7", 12)
    assert [x["text"] for x in view["messages"][:2]] == ["turn 2", "reply 2"], "the first exchange is gone"
    assert (await hub.http("GET", "/api/assistant/chat", cookie)).json() == view
    session = chat.get(hub.core.ctxs["assistant"])
    assert not any("turn 1" in x["content"] or "reply 1" in x["content"] for x in session.wire())
    owui.reply = {"choices": [{"message": {"role": "assistant", "content": "reply 8"}}]}
    view = await say(hub, cookie, w, "turn 8", 12)
    sent = owui.requests[-1]["body"]["messages"]
    assert sent[0] == {"role": "user", "content": "turn 2"} and len(sent) == 13
    assert sent[-1] == {"role": "user", "content": "turn 8"}
    assert view["messages"][0]["text"] == "turn 3" and view["messages"][-1]["text"] == "reply 8"
    hub.core.store.flush()
    assert not any("turn 1" in p.read_text(errors="ignore") for p in hub.data.rglob("*") if p.is_file())
    await w.close()


async def test_a_lower_keep_applies_when_the_next_turn_ends(hub: Hub, owui: FakeOpenWebUI) -> None:
    cookie = hub.pair()
    await hub.http("PATCH", "/api/assistant/openwebui", cookie, {"url": owui.url, "key": "sk-abc", "model": "q"})
    w = await hub.screen(cookie, "workspace", "w")
    for i in range(1, 4):
        await say(hub, cookie, w, f"turn {i}", 2 * i)
    await hub.http("PATCH", "/api/assistant/openwebui", cookie, {"keep": 1})
    assert len((await hub.http("GET", "/api/assistant/chat", cookie)).json()["messages"]) == 6, "nothing yet"
    view = await say(hub, cookie, w, "turn 4", 2)
    assert [x["text"] for x in view["messages"]] == ["turn 4", "Hello from Open WebUI."]
    await say(hub, cookie, w, "turn 5", 2)
    assert owui.requests[-1]["body"]["messages"] == [
        {"role": "user", "content": "turn 4"}, {"role": "assistant", "content": "Hello from Open WebUI."},
        {"role": "user", "content": "turn 5"}]
    await w.close()


async def test_tool_mode_deletes_the_open_webui_chat_and_keeps_the_tool_calls(hub: Hub, owui: FakeOpenWebUI) -> None:
    """Seven exchanges with keep 6: a reply with tools, a tools-only turn, an error line. After the seventh the
    first exchange is gone here and the Open WebUI chat that held its reply is deleted; the eighth turn makes a new
    chat and still sends every kept reply with its `output` items (what keeps the model calling tools)."""
    cookie, w = await tool_hub(hub, owui)
    session = chat.get(hub.core.ctxs["assistant"])
    owui.output, owui.content = TOOL_OUTPUT, "Queued a red fox."
    await say(hub, cookie, w, "fox", 2)                         # 1: a reply with tools
    owui.content = ""
    await say(hub, cookie, w, "orchard to volcano", 3)          # 2: tools only, no line
    owui.output, owui.error = [], {"content": "Model q is not loaded"}
    view = await say(hub, cookie, w, "hi", 5)                   # 3: an error line
    assert [x["role"] for x in view["messages"]] == ["user", "assistant", "user", "user", "error"]
    owui.error, owui.content = None, "Fine."
    for i, n in ((4, 7), (5, 9), (6, 11)):
        await say(hub, cookie, w, f"turn {i}", n)
    assert owui.chats.keys() == {"chat-1"} and len(owui.chats["chat-1"]) == 6
    view = await say(hub, cookie, w, "turn 7", 11)            # purge: the fox exchange goes
    assert view["messages"][0]["text"] == "orchard to volcano" and "fox" not in json.dumps(view)
    await until(lambda: owui.chats == {} and not session.cleanup)
    assert ("DELETE", "/api/v1/chats/chat-1") in [(r["method"], r["path"]) for r in owui.requests]
    assert session.remote is None
    assert session.wire()[0] == {"role": "user", "content": "orchard to volcano"} and len(session.wire()) == 11
    before = len(calls(owui))
    view = await say(hub, cookie, w, "turn 8", 12)            # purge: the tools-only exchange goes
    await until(lambda: owui.chats == {} and not session.cleanup)
    made = [(r["method"], r["path"]) for r in calls(owui)[before:]]
    assert made[:3] == [("POST", "/api/v1/chats/new"), ("POST", "/api/chat/completions"),
                        ("GET", "/api/v1/chats/chat-2")]
    # the purge deletes it; the sweep after the turn may see it first and delete it too (gone either way)
    assert made[3:] and set(made[3:]) == {("DELETE", "/api/v1/chats/chat-2")}, \
        "a new chat, then deleted again: it held the purged reply"
    turn = calls(owui)[before + 1]
    assert turn["body"]["chat_id"] == "chat-2" and len(turn["body"]["messages"]) == 12
    assert turn["body"]["messages"][:3] == [
        {"role": "user", "content": "orchard to volcano"}, {"role": "assistant", "content": "", "output": TOOL_OUTPUT},
        {"role": "user", "content": "hi"}], "the kept tools-only reply goes with its tool calls; errors stay here"
    assert view["messages"][0]["text"] == "hi" and view["messages"][1]["role"] == "error"
    assert session.remote is None
    hub.core.store.flush()
    assert sorted(p.name for p in (hub.data / "assistant").iterdir()) == ["openwebui.json"], "nothing on disk"
    await w.close()


async def test_until_a_purge_the_open_webui_chat_stays(hub: Hub, owui: FakeOpenWebUI) -> None:
    cookie, w = await tool_hub(hub, owui)
    session = chat.get(hub.core.ctxs["assistant"])
    owui.output = []
    await hub.http("PATCH", "/api/assistant/openwebui", cookie, {"keep": 2})
    await say(hub, cookie, w, "one", 2)
    await say(hub, cookie, w, "two", 4)
    assert owui.chats.keys() == {"chat-1"} and session.remote == "chat-1"
    assert not any(r["method"] == "DELETE" for r in owui.requests), "nothing purged, nothing deleted"
    view = await say(hub, cookie, w, "three", 4)
    assert [x["text"] for x in view["messages"][::2]] == ["two", "three"]
    await until(lambda: owui.chats == {} and not session.cleanup)
    await w.close()
