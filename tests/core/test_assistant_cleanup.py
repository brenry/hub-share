"""The hub's Open WebUI chats are deleted, and a deletion Open WebUI refuses is said: after every tool-server turn
the sweep deletes every chat titled "Hub" but the one in use (remote.py), a DELETE answered 200 or 404 means gone,
any other answer shows once per reason as an error line. The fake Open WebUI is tests/fakes/openwebui.py's."""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from hub.modules.assistant import chat
from tests.core.harness import Hub, own_modules, start_hub
from tests.fakes.openwebui import SWEEP, FakeOpenWebUI, settled, tool_hub, until

REFUSAL = "Open WebUI did not delete the Hub's old chat: "
NO_RIGHT = "You do not have permission to access this resource."


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


def deleted(owui: FakeOpenWebUI) -> list[str]:
    return [r["path"].removeprefix("/api/v1/chats/") for r in owui.requests if r["method"] == "DELETE"]


async def test_a_refused_delete_is_said_once_and_the_next_sweep_deletes_the_chat(hub: Hub, owui: FakeOpenWebUI) -> None:
    cookie, w = await tool_hub(hub, owui)
    session = chat.get(hub.core.ctxs["assistant"])
    await hub.http("POST", "/api/assistant/chat", cookie, {"text": "hi"})
    await settled(w, 2)
    await until(lambda: not session.cleanup)
    owui.delete_status = 403              # a key or a user without the delete permission
    assert (await hub.http("DELETE", "/api/assistant/chat", cookie)).json()["messages"] == []
    view = await settled(w, 1)
    assert [(m["role"], m["text"]) for m in view["messages"]] == [("error", REFUSAL + NO_RIGHT)], \
        "Open WebUI's own reason, as an error line"
    assert owui.chats.keys() == {"chat-1"}, "refused: the chat stays"
    # the next turn's sweep is refused for the same reason: no second line
    await hub.http("POST", "/api/assistant/chat", cookie, {"text": "again"})
    await settled(w, 3)
    await until(lambda: not session.cleanup)
    assert deleted(owui) == ["chat-1", "chat-1"]
    view = (await hub.http("GET", "/api/assistant/chat", cookie)).json()
    assert [m["role"] for m in view["messages"]] == ["error", "user", "assistant"]
    assert owui.chats.keys() == {"chat-1", "chat-2"}
    # allowed again: the next turn's sweep deletes the leftover and keeps the chat in use
    owui.delete_status = 200
    await hub.http("POST", "/api/assistant/chat", cookie, {"text": "and again"})
    await settled(w, 5)
    await until(lambda: not session.cleanup)
    assert owui.chats.keys() == {"chat-2"} and session.remote == "chat-2"
    assert deleted(owui) == ["chat-1", "chat-1", "chat-1"]
    view = (await hub.http("GET", "/api/assistant/chat", cookie)).json()
    assert sum(m["role"] == "error" for m in view["messages"]) == 1
    await w.close()


async def test_a_different_reason_is_said_again(hub: Hub, owui: FakeOpenWebUI) -> None:
    cookie, w = await tool_hub(hub, owui)
    session = chat.get(hub.core.ctxs["assistant"])
    owui.chats["old"] = {}
    owui.delete_status, owui.delete_detail = 403, NO_RIGHT
    await hub.http("POST", "/api/assistant/chat", cookie, {"text": "hi"})
    await settled(w, 3)                   # the reply, then the sweep's refusal
    await until(lambda: not session.cleanup)
    owui.delete_status = 500              # no detail: the status is the reason
    owui.delete_detail = ""
    await hub.http("POST", "/api/assistant/chat", cookie, {"text": "again"})
    view = await settled(w, 6)
    errors = [m["text"] for m in view["messages"] if m["role"] == "error"]
    assert errors == [REFUSAL + NO_RIGHT, REFUSAL + "Open WebUI answered HTTP 500"]
    await w.close()


async def test_the_sweep_deletes_leftover_hub_chats_only(hub: Hub, owui: FakeOpenWebUI) -> None:
    owui.chats.update({"old-1": {}, "old-2": {}, "mine": {}})
    owui.titles["mine"] = "Dinner plans"  # a chat not made by the Hub
    cookie, w = await tool_hub(hub, owui)
    session = chat.get(hub.core.ctxs["assistant"])
    await hub.http("POST", "/api/assistant/chat", cookie, {"text": "hi"})
    view = await settled(w, 2)
    await until(lambda: not session.cleanup)
    assert sorted(deleted(owui)) == ["old-1", "old-2"]
    assert owui.chats.keys() == {"chat-1", "mine"} and session.remote == "chat-1"
    assert [m["role"] for m in view["messages"]] == ["user", "assistant"], "no error line"
    assert [r["path"] for r in owui.requests].count(SWEEP) == 1
    await w.close()


async def test_a_delete_answered_404_is_gone(hub: Hub, owui: FakeOpenWebUI) -> None:
    cookie, w = await tool_hub(hub, owui)
    session = chat.get(hub.core.ctxs["assistant"])
    owui.chats["old"] = {}
    owui.delete_status = 404              # already deleted, in Open WebUI or by an earlier try
    await hub.http("POST", "/api/assistant/chat", cookie, {"text": "hi"})
    await settled(w, 2)
    await until(lambda: not session.cleanup)
    assert deleted(owui) == ["old"]
    assert (await hub.http("DELETE", "/api/assistant/chat", cookie)).json()["messages"] == []
    await until(lambda: not session.cleanup)
    assert deleted(owui) == ["old", "chat-1"] and owui.chats == {}
    await asyncio.sleep(0.1)
    assert (await hub.http("GET", "/api/assistant/chat", cookie)).json()["messages"] == [], "no error line"
    await w.close()


async def test_the_sweep_never_deletes_the_chat_a_turn_is_making(hub: Hub, owui: FakeOpenWebUI) -> None:
    """Open WebUI has made the turn's chat (so it is listed, titled "Hub") but its id has not reached the hub yet:
    a sweep then waits for the turn to have it, and keeps it."""
    cookie, w = await tool_hub(hub, owui)
    session = chat.get(hub.core.ctxs["assistant"])
    owui.making = 0.5
    await hub.http("POST", "/api/assistant/chat", cookie, {"text": "hi"})
    await until(lambda: owui.made == 1)
    assert session.remote is None
    sweep = asyncio.get_running_loop().create_task(session.sweep())
    view = await settled(w, 2)
    await sweep
    await until(lambda: not session.cleanup)
    assert [(m["role"], m["text"]) for m in view["messages"]] == [("user", "hi"), ("assistant", "Queued a red fox.")]
    assert deleted(owui) == [] and owui.chats.keys() == {"chat-1"} and session.remote == "chat-1"
    await w.close()


async def test_no_sweep_without_a_tool_server(hub: Hub, owui: FakeOpenWebUI) -> None:
    cookie = hub.pair()
    await hub.http("PATCH", "/api/assistant/openwebui", cookie, {"url": owui.url, "key": "sk-abc", "model": "q"})
    w = await hub.screen(cookie, "workspace", "w")
    session = chat.get(hub.core.ctxs["assistant"])
    owui.chats["old"] = {}
    for n in (2, 4):
        await hub.http("POST", "/api/assistant/chat", cookie, {"text": "hi"})
        await settled(w, n)
    await asyncio.sleep(0.2)
    assert not session.cleanup
    assert [(r["method"], r["path"]) for r in owui.requests] == [("POST", "/api/chat/completions")] * 2
    assert owui.chats.keys() == {"old"}
    await w.close()
