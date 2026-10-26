"""The assistant chat with a tool server picked: Open WebUI runs the tools in one throwaway chat per conversation,
made at the first message and deleted at New chat, the session's end and the module's stop. The fake Open WebUI is
tests/fakes/openwebui.py's."""
from __future__ import annotations

from pathlib import Path

import pytest

from hub.modules.assistant import chat
from tests.core.harness import Hub, own_modules, start_hub
from tests.fakes.openwebui import SWEEP, TOOL_OUTPUT, FakeOpenWebUI, calls, settled, tool_hub, until


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


async def test_with_a_tool_server_open_webui_runs_the_tools_in_one_chat(hub: Hub, owui: FakeOpenWebUI) -> None:
    """The reply's tool calls (set, generate_image, a failed get) are not in the chat: it holds your message and the
    reply's text, nothing else; the calls show as what they did (the draft, the settings, the picture in Media)."""
    cookie, w = await tool_hub(hub, owui)
    await hub.http("POST", "/api/assistant/chat", cookie, {"text": "make a red fox"})
    view = await settled(w, 2)
    new, turn, read = calls(owui)
    assert (new["method"], new["path"], new["auth"]) == ("POST", "/api/v1/chats/new", "Bearer sk-abc")
    assert new["body"] == {"chat": {"title": "Hub", "models": ["q"], "history": {"messages": {}, "currentId": None},
                                    "messages": []}}
    first = turn["body"]["id"]
    assert turn["path"] == "/api/chat/completions" and turn["body"] == {
        "model": "q", "messages": [{"role": "user", "content": "make a red fox"}], "stream": True,
        "tool_ids": ["server:mcp:hub"], "chat_id": "chat-1", "id": first, "params": {"num_ctx": 8192}}
    assert (read["method"], read["path"]) == ("GET", "/api/v1/chats/chat-1")
    user, reply = view["messages"]
    assert [(m["role"], m["text"]) for m in view["messages"]] == [("user", "make a red fox"),
                                                                  ("assistant", "Queued a red fox.")]
    assert reply["seconds"] is not None and set(reply) == {"id", "role", "text", "at", "seconds"}
    assert not any("red fox in snow" in m["text"] or "no model" in m["text"] for m in view["messages"]), \
        "no tool, no result"
    # the second turn: the same chat, the conversation only; a streamed answer is read to its end
    owui.stream_as, owui.output, owui.content = "sse", [], "Done."
    await hub.http("POST", "/api/assistant/chat", cookie, {"text": "thanks"})
    view = await settled(w, 4)
    assert [r["path"] for r in calls(owui)[3:]] == ["/api/chat/completions", "/api/v1/chats/chat-1"]
    second = calls(owui)[3]["body"]
    assert second["messages"] == [{"role": "user", "content": "make a red fox"},
                                  {"role": "assistant", "content": "Queued a red fox.", "output": TOOL_OUTPUT},
                                  {"role": "user", "content": "thanks"}], \
        "the reply goes back with its tool calls, as Open WebUI's own chat sends it: the model sees what it did"
    assert second["chat_id"] == "chat-1" and second["id"] != first and "parent_id" not in second
    assert view["messages"][-1]["text"] == "Done." and view["messages"][-1]["seconds"] >= 0.4   # the slow stream
    hub.core.store.flush()
    assert sorted(p.name for p in (hub.data / "assistant").iterdir()) == ["openwebui.json"], "nothing else on disk"
    # New chat deletes the Open WebUI chat; the next message starts a new one
    assert (await hub.http("DELETE", "/api/assistant/chat", cookie)).json()["messages"] == []
    await until(lambda: calls(owui)[-1]["method"] == "DELETE")
    assert (calls(owui)[-1]["method"], calls(owui)[-1]["path"]) == ("DELETE", "/api/v1/chats/chat-1")
    assert owui.chats == {}
    await hub.http("POST", "/api/assistant/chat", cookie, {"text": "again"})
    await settled(w, 2)
    assert calls(owui)[-3]["path"] == "/api/v1/chats/new" and calls(owui)[-2]["body"]["chat_id"] == "chat-2"
    await w.close()


async def test_an_error_saved_by_open_webui_shows_as_an_error(hub: Hub, owui: FakeOpenWebUI) -> None:
    cookie, w = await tool_hub(hub, owui)
    owui.output, owui.content, owui.error = [], "", {"content": "Model q is not loaded"}
    await hub.http("POST", "/api/assistant/chat", cookie, {"text": "hi"})
    view = await settled(w, 2)
    assert [(m["role"], m["text"]) for m in view["messages"]] == [("user", "hi"), ("error", "Model q is not loaded")]
    owui.error = None
    await hub.http("POST", "/api/assistant/chat", cookie, {"text": "hi"})
    view = await settled(w, 4)
    last = view["messages"][3]
    assert (last["role"], last["text"]) == ("error", "Open WebUI sent a reply with no text")
    hi = {"role": "user", "content": "hi"}
    assert calls(owui)[-2]["body"]["messages"] == [hi, hi]   # errors are never sent
    await w.close()


async def test_a_turn_that_ran_tools_and_said_nothing_shows_nothing_but_is_kept_for_the_model(
        hub: Hub, owui: FakeOpenWebUI) -> None:
    """The assistant wrote the draft (or rendered it) without a word: the chat shows your message alone, no error;
    the turn is over (not busy) and the next message carries that turn's tool calls, so the model sees it acted."""
    cookie, w = await tool_hub(hub, owui)
    owui.output, owui.content = TOOL_OUTPUT, ""
    await hub.http("POST", "/api/assistant/chat", cookie, {"text": "orchard to volcano"})
    view = await settled(w, 1)
    assert [(m["role"], m["text"]) for m in view["messages"]] == [("user", "orchard to volcano")]
    assert (await hub.http("GET", "/api/assistant/chat", cookie)).json() == view
    owui.output, owui.content = [], "Done."
    await hub.http("POST", "/api/assistant/chat", cookie, {"text": "and a moon"})
    view = await settled(w, 3)
    assert calls(owui)[-2]["body"]["messages"] == [{"role": "user", "content": "orchard to volcano"},
                                                     {"role": "assistant", "content": "", "output": TOOL_OUTPUT},
                                                     {"role": "user", "content": "and a moon"}]
    assert [m["role"] for m in view["messages"]] == ["user", "user", "assistant"], "the tools-only turn is no line"
    await w.close()


async def test_stopping_the_module_deletes_the_open_webui_chat(hub: Hub, owui: FakeOpenWebUI) -> None:
    cookie, w = await tool_hub(hub, owui)
    await hub.http("POST", "/api/assistant/chat", cookie, {"text": "hi"})
    await settled(w, 2)
    await w.close()
    assert owui.chats.keys() == {"chat-1"}
    await chat.stop(hub.core.ctxs["assistant"])
    assert calls(owui)[-1] == {"method": "DELETE", "path": "/api/v1/chats/chat-1", "auth": "Bearer sk-abc",
                               "body": None}
    assert owui.chats == {}


async def test_the_session_ending_forgets_the_chat_here_and_in_open_webui(hub: Hub, owui: FakeOpenWebUI) -> None:
    cookie, w = await tool_hub(hub, owui)
    await hub.http("POST", "/api/assistant/chat", cookie, {"text": "a grey cat under an apple tree"})
    await settled(w, 2)
    before = (await hub.http("GET", "/api/assistant/chat", cookie)).json()
    assert owui.chats.keys() == {"chat-1"} and len(before["messages"]) == 2
    await w.close()                                 # the last window; the harness grace is 0.4 s
    session = chat.get(hub.core.ctxs["assistant"])
    await until(lambda: owui.chats == {} and not session.cleanup, 3.0)
    assert ("DELETE", "/api/v1/chats/chat-1") in [(r["method"], r["path"]) for r in owui.requests]
    assert [r["path"] for r in owui.requests].count(SWEEP) == 2, "a sweep after the turn and one at the session end"
    view = (await hub.http("GET", "/api/assistant/chat", cookie)).json()
    assert view["messages"] == [] and view["busy"] is False
    assert not any("grey cat" in p.read_text(errors="ignore") for p in hub.data.rglob("*") if p.is_file())


async def test_tools_need_assistant_access_on(hub: Hub, owui: FakeOpenWebUI) -> None:
    cookie = hub.pair()
    await hub.http("PATCH", "/api/assistant/openwebui", cookie,
                   {"url": owui.url, "key": "sk-abc", "model": "q", "tools": "hub"})
    w = await hub.screen(cookie, "workspace", "w")
    assert (await hub.http("GET", "/api/assistant", cookie)).json()["on"] is False
    await hub.http("POST", "/api/assistant/chat", cookie, {"text": "make a red fox"})
    view = await settled(w, 2)
    assert [(m["role"], m["text"]) for m in view["messages"]] == [
        ("user", "make a red fox"), ("error", "Assistant access is off, so Open WebUI cannot reach the Hub tools")]
    assert calls(owui) == [], "the turn is skipped: no Open WebUI chat, no completion"
    await hub.http("PATCH", "/api/assistant", cookie, {"on": True})
    await hub.http("POST", "/api/assistant/chat", cookie, {"text": "make a red fox"})
    view = await settled(w, 4)
    assert [m["role"] for m in view["messages"][2:]] == ["user", "assistant"]
    assert [r["path"] for r in calls(owui)] == ["/api/v1/chats/new", "/api/chat/completions", "/api/v1/chats/chat-1"]
    await w.close()


async def test_a_chat_deleted_in_open_webui_starts_a_new_one(hub: Hub, owui: FakeOpenWebUI) -> None:
    cookie, w = await tool_hub(hub, owui)
    await hub.http("POST", "/api/assistant/chat", cookie, {"text": "hi"})
    await settled(w, 2)
    owui.chats.clear()   # deleted in Open WebUI: the next reply is saved into nothing
    await hub.http("POST", "/api/assistant/chat", cookie, {"text": "still there?"})
    view = await settled(w, 4)
    assert (view["messages"][3]["role"], view["messages"][3]["text"]) == (
        "error", "The Open WebUI chat for this conversation is gone; the next message starts a new one")
    assert calls(owui)[-1]["path"] == "/api/v1/chats/chat-1" and chat.get(hub.core.ctxs["assistant"]).remote is None
    await hub.http("POST", "/api/assistant/chat", cookie, {"text": "again"})
    view = await settled(w, 6)
    assert [r["path"] for r in calls(owui)[-3:]] == [
        "/api/v1/chats/new", "/api/chat/completions", "/api/v1/chats/chat-2"]
    assert calls(owui)[-2]["body"]["chat_id"] == "chat-2" and view["messages"][-1]["text"] == "Queued a red fox."
    await w.close()


async def test_new_chat_while_open_webui_makes_the_chat_leaves_none(hub: Hub, owui: FakeOpenWebUI) -> None:
    cookie, w = await tool_hub(hub, owui)
    session = chat.get(hub.core.ctxs["assistant"])
    owui.making = 0.5
    await hub.http("POST", "/api/assistant/chat", cookie, {"text": "hi"})
    await until(lambda: owui.made == 1)   # made in Open WebUI; its id is still on the way
    assert (await hub.http("DELETE", "/api/assistant/chat", cookie)).json() == {
        "busy": False, "messages": [], "model": "q"}
    await until(lambda: owui.chats == {} and not session.cleanup)
    assert [(r["method"], r["path"]) for r in owui.requests] == [
        ("POST", "/api/v1/chats/new"), ("DELETE", "/api/v1/chats/chat-1")], "deleted when its id came; no turn ran"
    assert session.remote is None and session.view()["messages"] == []
    # stopping the module mid-make waits until that chat is deleted too
    await hub.http("POST", "/api/assistant/chat", cookie, {"text": "again"})
    await until(lambda: owui.made == 2)
    await chat.stop(hub.core.ctxs["assistant"])
    assert owui.chats == {} and not session.cleanup
    assert (owui.requests[-1]["method"], owui.requests[-1]["path"]) == ("DELETE", "/api/v1/chats/chat-2")
    await w.close()


def test_a_tool_call_is_read_from_the_output_items() -> None:
    assert chat.ran_tools(TOOL_OUTPUT) is True
    unanswered = [{"type": "function_call", "call_id": "c", "name": "other_tool", "arguments": "not json"}]
    assert chat.ran_tools(unanswered) is True
    for nothing in (None, [], [1, "x"], [{"type": "message"}], "function_call"):
        assert chat.ran_tools(nothing) is False


async def test_every_settings_turn_carries_the_earlier_tool_calls(hub: Hub, owui: FakeOpenWebUI) -> None:
    """Two settings turns in a row (steps to 8, then steps to 20). Each turn goes to Open WebUI with every earlier
    reply's tool calls attached (Open WebUI rebuilds them into the model's history), never as bare text — sent bare,
    the model saw its first change answered in words and answered the second in words, calling nothing."""
    cookie, w = await tool_hub(hub, owui)
    steps8 = [{"type": "function_call", "id": "c8", "call_id": "c8", "name": "hub_set_generate_image_settings",
               "arguments": '{"steps": 8}', "status": "completed"},
              {"type": "function_call_output", "id": "o8", "call_id": "c8",
               "output": [{"type": "input_text", "text": '{"steps": 8}'}], "status": "completed"}]
    owui.output, owui.content = steps8, "Steps set to 8."
    await hub.http("POST", "/api/assistant/chat", cookie, {"text": "set steps to 8"})
    await settled(w, 2)
    owui.output, owui.content = [], "Steps set to 20."
    await hub.http("POST", "/api/assistant/chat", cookie, {"text": "set steps to 20"})
    view = await settled(w, 4)
    sent = calls(owui)[-2]["body"]["messages"]
    assert sent[1] == {"role": "assistant", "content": "Steps set to 8.", "output": steps8}
    assert sent[2] == {"role": "user", "content": "set steps to 20"}
    assert [m["text"] for m in view["messages"]] == ["set steps to 8", "Steps set to 8.", "set steps to 20",
                                                     "Steps set to 20."], "the chat shows words only"
    assert all("output" not in m for m in view["messages"]), "the tool items never reach the screen"
    hub.core.store.flush()
    assert sorted(p.name for p in (hub.data / "assistant").iterdir()) == ["openwebui.json"], "nothing on disk"
    await w.close()
