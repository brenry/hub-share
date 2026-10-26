"""The assistant chat carried by Open WebUI: the words go as they are, the reply shows, nothing on disk. The
tool-server mode (one throwaway Open WebUI chat per conversation) is in test_assistant_tools.py.

The fake Open WebUI (tests/fakes/openwebui.py) records every request it gets (the raw-socket cases are in
test_assistant_link.py).
"""
from __future__ import annotations

import asyncio
import json
import stat
from pathlib import Path

import pytest

from hub.modules.assistant import chat
from hub.modules.generate_image.manifest import MODULE as GENERATE
from tests.core.harness import Hub, own_modules, start_hub
from tests.fakes.openwebui import SERVERS, FakeOpenWebUI, settled


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


async def test_settings_are_saved_and_the_key_is_never_shown(hub: Hub, owui: FakeOpenWebUI) -> None:
    cookie = hub.pair()
    before = (await hub.http("GET", "/api/assistant", cookie)).json()["openwebui"]
    assert before == {"url": "http://127.0.0.1:3000", "model": "", "key": False, "tools": "", "keep": 6,
                      "context": 8192}
    r = await hub.http("PATCH", "/api/assistant/openwebui", cookie, {"url": owui.url, "key": "sk-abc", "model": "q"})
    assert r.status == 200 and r.json()["openwebui"] == {"url": owui.url, "model": "q", "key": True, "tools": "",
                                                         "keep": 6, "context": 8192}
    r = await hub.http("PATCH", "/api/assistant/openwebui", cookie, {"model": "qwen3.5:9b"})
    assert r.json()["openwebui"] == {"url": owui.url, "model": "qwen3.5:9b", "key": True, "tools": "",
                                     "keep": 6, "context": 8192}  # partial
    r = await hub.http("PATCH", "/api/assistant/openwebui", cookie, {"tools": " hub "})
    assert r.json()["openwebui"]["tools"] == "hub"
    for bad, field in (({"url": "http://192.168.0.10:3000"}, "url"), ({"url": "http://localhost:3000"}, "url"),
                       ({"url": "https://127.0.0.1:3000"}, "url"), ({"port": 3000}, "settings"), ({}, "settings"),
                       ({"key": 7}, "key"), ({"key": "sk\r\nX-Evil: 1"}, "key"),
                       ({"model": "q\x00"}, "model"),
                       ({"tools": "h\nub"}, "tools"), ({"tools": 1}, "tools"), ({"model": "mod\u00e8le"}, "model"),
                       ({"url": "http://127.0.0.1:30\n00"}, "url"), ({"url": "http://127.0.0.1:3000/api"}, "url")):
        r = await hub.http("PATCH", "/api/assistant/openwebui", cookie, bad)
        assert r.status == 400 and r.json()["field"] == field, bad
    hub.core.store.flush()
    saved = json.loads((hub.data / "assistant" / "openwebui.json").read_text())
    assert saved == {"url": owui.url, "key": "sk-abc", "model": "qwen3.5:9b", "tools": "hub", "keep": 6,
                     "context": 8192}
    assert sorted(p.name for p in (hub.data / "assistant").iterdir()) == ["openwebui.json"], "settings only"
    assert stat.S_IMODE((hub.data / "assistant" / "openwebui.json").stat().st_mode) == 0o600
    r = await hub.http("PATCH", "/api/assistant/openwebui", cookie, {"model": "x" * 501})   # any length
    assert r.status == 200 and r.json()["openwebui"]["model"] == "x" * 501


async def test_a_message_goes_to_open_webui_as_is_and_the_reply_shows(hub: Hub, owui: FakeOpenWebUI) -> None:
    cookie = hub.pair()
    await hub.http("PATCH", "/api/assistant/openwebui", cookie, {"url": owui.url, "key": "sk-abc", "model": "q"})
    w = await hub.screen(cookie, "workspace", "w")
    r = await hub.http("POST", "/api/assistant/chat", cookie, {"text": "  hello there  "})
    assert r.status == 202
    turn = r.json()["turn"]
    assert (await hub.http("POST", "/api/assistant/chat", cookie, {"text": " "})).status == 400
    view = await settled(w, 2)
    assert [(m["role"], m["text"]) for m in view["messages"]] == [("user", "hello there"),
                                                                  ("assistant", "Hello from Open WebUI.")]
    assert view["messages"][0]["id"] == turn and view["model"] == "q" and view["busy"] is False
    assert set(view["messages"][0]) == {"id", "role", "text", "at", "seconds"}
    assert view["messages"][0]["seconds"] is None
    assert isinstance(view["messages"][1]["seconds"], float)
    [req] = owui.requests
    assert req["path"] == "/api/chat/completions" and req["auth"] == "Bearer sk-abc"
    assert req["body"] == {"model": "q", "messages": [{"role": "user", "content": "hello there"}], "stream": False,
                           "params": {"num_ctx": 8192}}, "the words as they are, and the context length"
    # the second turn carries the whole conversation, nothing more
    await hub.http("POST", "/api/assistant/chat", cookie, {"text": "and again"})
    view = await settled(w, 4)
    assert owui.requests[1]["body"]["messages"] == [
        {"role": "user", "content": "hello there"}, {"role": "assistant", "content": "Hello from Open WebUI."},
        {"role": "user", "content": "and again"}]
    assert (await hub.http("GET", "/api/assistant/chat", cookie)).json() == view
    hub.core.store.flush()
    assert sorted(p.name for p in (hub.data / "assistant").iterdir()) == ["openwebui.json"], "no chat on disk"
    cleared = (await hub.http("DELETE", "/api/assistant/chat", cookie)).json()
    assert cleared == {"busy": False, "messages": [], "model": "q"}
    await w.close()


async def test_busy_and_what_open_webui_refuses(hub: Hub, owui: FakeOpenWebUI) -> None:
    cookie = hub.pair()
    w = await hub.screen(cookie, "workspace", "w")
    r = await hub.http("POST", "/api/assistant/chat", cookie, {"text": "no model yet"})
    assert r.status == 202
    view = await settled(w, 2)
    assert view["messages"][1]["text"] == "Set the Open WebUI model name in Settings -> Assistant"
    assert view["messages"][1]["role"] == "error" and view["messages"][1]["seconds"] is None
    assert owui.requests == []
    await hub.http("DELETE", "/api/assistant/chat", cookie)
    await hub.http("PATCH", "/api/assistant/openwebui", cookie, {"url": owui.url, "key": "bad", "model": "q"})
    owui.status = 401
    owui.reply = {"detail": "Not authenticated"}
    await hub.http("POST", "/api/assistant/chat", cookie, {"text": "hi"})
    view = await settled(w, 2)
    assert view["messages"][1]["text"].startswith("Open WebUI refused the key")
    owui.status = 400
    owui.reply = {"detail": "Model not found"}
    await hub.http("POST", "/api/assistant/chat", cookie, {"text": "hi"})
    view = await settled(w, 4)
    assert view["messages"][3]["text"] == "Model not found"
    owui.status, owui.reply, owui.raw = 200, None, b"<html>"
    await hub.http("POST", "/api/assistant/chat", cookie, {"text": "hi"})
    view = await settled(w, 6)
    assert view["messages"][5]["text"].startswith("Open WebUI sent something the hub cannot read")
    owui.raw = None
    await hub.http("PATCH", "/api/assistant/openwebui", cookie, {"url": "http://127.0.0.1:1"})
    await hub.http("POST", "/api/assistant/chat", cookie, {"text": "hi"})
    view = await settled(w, 8)
    assert view["messages"][7]["text"] == "Open WebUI is not answering on that address"
    assert [m["role"] for m in view["messages"]] == ["user", "error"] * 4
    await w.close()


async def test_errors_are_never_sent_to_open_webui(hub: Hub, owui: FakeOpenWebUI) -> None:
    cookie = hub.pair()
    await hub.http("PATCH", "/api/assistant/openwebui", cookie, {"url": owui.url, "key": "k", "model": "q"})
    w = await hub.screen(cookie, "workspace", "w")
    owui.status, owui.reply = 401, {"detail": "Not authenticated"}
    await hub.http("POST", "/api/assistant/chat", cookie, {"text": "first"})
    await settled(w, 2)
    owui.status, owui.reply = 200, {"choices": [{"message": {"content": "Hello from Open WebUI."}}]}
    for n, text in ((4, "second"), (6, "third")):
        await hub.http("POST", "/api/assistant/chat", cookie, {"text": text})
        view = await settled(w, n)
    assert [m["role"] for m in view["messages"]] == ["user", "error", "user", "assistant", "user", "assistant"]
    assert owui.requests[-1]["body"]["messages"] == [
        {"role": "user", "content": "first"}, {"role": "user", "content": "second"},
        {"role": "assistant", "content": "Hello from Open WebUI."}, {"role": "user", "content": "third"}]
    await w.close()


async def test_a_second_message_while_busy_is_refused(hub: Hub, owui: FakeOpenWebUI) -> None:
    cookie = hub.pair()
    await hub.http("PATCH", "/api/assistant/openwebui", cookie, {"url": owui.url, "key": "k", "model": "q"})
    session = chat.get(hub.core.ctxs["assistant"])
    gate = asyncio.Event()

    async def slow() -> None:
        await gate.wait()
        session.add("assistant", "late")
        session.busy, session.task = False, None
        session.changed()

    session.busy = True
    session.task = asyncio.get_running_loop().create_task(slow())
    r = await hub.http("POST", "/api/assistant/chat", cookie, {"text": "again"})
    assert r.status == 409 and r.json()["code"] == "busy"
    gate.set()
    await asyncio.sleep(0.05)
    assert session.busy is False and owui.requests == []


async def test_said_is_the_users_newest_message_while_a_turn_runs(hub: Hub, owui: FakeOpenWebUI) -> None:
    """The "said" service gives the Director the `user` message of the running turn; None when no turn runs."""
    said = hub.core.services["said"]
    session = chat.get(hub.core.ctxs["assistant"])
    assert said() is None
    first = session.add("user", "Prompt 1.")
    assert said() is None, "idle"
    session.busy = True
    assert said() == {"id": first["id"], "text": "Prompt 1.", "first": True}
    session.add("assistant", "Done.")
    session.add("hub", "Script 1: the takes are being made")
    second = session.add("user", "Make shot 2 a close shot on Character 6.")
    assert said() == {"id": second["id"], "text": "Make shot 2 a close shot on Character 6.", "first": False}
    session.busy = False
    assert said() is None


async def test_the_model_list_comes_from_open_webui_with_the_saved_key(hub: Hub, owui: FakeOpenWebUI) -> None:
    cookie = hub.pair()
    models = lambda: hub.http("GET", "/api/assistant/openwebui/models", cookie)  # noqa: E731
    await hub.http("PATCH", "/api/assistant/openwebui", cookie, {"url": owui.url, "key": "sk-abc"})
    r = await models()
    assert r.status == 200 and r.json() == {"ok": True, "text": "Connected · 2 models", "models": ["q", "gemma3:12b"]}
    [req] = owui.requests
    assert req == {"method": "GET", "path": "/api/models", "auth": "Bearer sk-abc", "body": None}
    owui.status, owui.reply = 401, {"detail": "Not authenticated"}
    assert (await models()).json() == {"ok": False, "models": [],
                                       "text": "Open WebUI refused the key (Settings -> Account -> API keys)"}
    owui.status, owui.models = 200, {"data": []}
    assert (await models()).json()["text"] == "Connected, key accepted, but Open WebUI lists no models"
    owui.models = {"data": [{"id": "only"}]}
    assert (await models()).json() == {"ok": True, "text": "Connected · 1 model", "models": ["only"]}
    await hub.http("PATCH", "/api/assistant/openwebui", cookie, {"url": "http://127.0.0.1:1"})
    assert (await models()).json() == {"ok": False, "models": [], "text": "Open WebUI is not answering on that address"}


async def test_the_tool_server_list_comes_from_open_webui(hub: Hub, owui: FakeOpenWebUI) -> None:
    cookie = hub.pair()
    servers = lambda: hub.http("GET", "/api/assistant/openwebui/tool-servers", cookie)  # noqa: E731
    await hub.http("PATCH", "/api/assistant/openwebui", cookie, {"url": owui.url, "key": "sk-abc"})
    r = await servers()
    assert r.status == 200 and r.json() == {"ok": True, "text": "2 tool servers", "servers": [
        {"id": "hub", "name": "Hub"}, {"id": "notes", "name": "notes"}]}   # MCP only; no keys passed on
    [req] = owui.requests
    assert req == {"method": "GET", "path": "/api/v1/configs/tool_servers", "auth": "Bearer sk-abc", "body": None}
    owui.servers_status = 401   # get_admin_user's refusal for a key whose user is not an admin
    owui.servers = {"detail": "You do not have permission to access this resource. Please contact your "
                              "administrator for assistance."}
    assert (await servers()).json() == {"ok": False, "servers": [],
                                        "text": "Open WebUI shows its tool servers only to an admin's key"}
    owui.servers = {"detail": "Your session has expired or the token is invalid. Please sign in again."}
    assert (await servers()).json()["text"] == "Open WebUI refused the key (Settings -> Account -> API keys)"
    owui.servers_status, owui.servers = 200, {"TOOL_SERVER_CONNECTIONS": []}
    assert (await servers()).json() == {"ok": True, "text": "Open WebUI has no MCP tool servers", "servers": []}
    junk = ["hub", 1, None, [], {"type": "mcp"}, {"type": "mcp", "info": "hub"}, {"type": "mcp", "info": {"id": 7}}]
    owui.servers = {"TOOL_SERVER_CONNECTIONS": [*junk, *SERVERS]}
    assert (await servers()).json()["servers"] == [{"id": "hub", "name": "Hub"}, {"id": "notes", "name": "notes"}]


async def test_new_chat_empties_the_prompt_box_and_the_assistants_draft(tmp_path: Path, owui: FakeOpenWebUI) -> None:
    """New chat (DELETE /api/assistant/chat) ends the conversation and, through the core's `chat.cleared`, empties
    the Generate session's prompt box and draft: GET /draft has both "", the references stay, and every connected
    Generate window hears `generate-image.draft`. The modules never import each other."""
    hub = await start_hub(tmp_path / "data", modules=[*own_modules(), GENERATE])
    try:
        cookie = hub.pair()
        await hub.http("PATCH", "/api/assistant/openwebui", cookie, {"url": owui.url, "key": "sk-abc", "model": "q"})
        w = await hub.screen(cookie, "workspace", "w")
        ref = {"id": "out/2026-10-09/r.png", "w": 8, "h": 8}
        body = {"model": "flux", "prompt": "a grey cat, my words", "draft": "a grey cat, the assistant's take",
                "references": [ref], "selected": "x"}
        assert (await hub.http("PUT", "/api/generate-image/draft", cookie, json_body=body)).status == 200
        await w.recv("generate-image.draft", timeout=2)
        await hub.http("POST", "/api/assistant/chat", cookie, {"text": "hello"})
        assert len((await settled(w, 2))["messages"]) == 2
        cleared = (await hub.http("DELETE", "/api/assistant/chat", cookie)).json()
        assert cleared == {"busy": False, "messages": [], "model": "q"}
        assert (await w.recv("generate-image.draft", timeout=2))["d"] == {}, "the window redraws the box and the panel"
        draft = (await hub.http("GET", "/api/generate-image/draft", cookie)).json()
        assert (draft["prompt"], draft["draft"], draft["references"], draft["selected"]) == ("", "", [ref], "x")
        assert draft["model"] == "flux", "the saved settings stay"
        hub.core.store.flush()
        assert "grey cat" not in (hub.data / "generate-image" / "draft.json").read_text()
        assert (await hub.http("GET", "/api/assistant/chat", cookie)).json()["messages"] == []
        await w.close()
    finally:
        await hub.close()
