"""What the hub sends of the conversation stays small enough for a small model: tool results of every exchange but the
newest go as one short line (turns.lean; the kept messages stay whole), and every completion carries the "Context
length" setting as `params.num_ctx` (settings.py; 0 sends none). The fake Open WebUI is tests/fakes/openwebui.py's."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from hub.core.api import Invalid
from hub.modules.assistant import chat, settings, turns
from tests.core.harness import Hub, own_modules, start_hub
from tests.fakes.openwebui import FakeOpenWebUI, calls, settled, tool_hub
from tests.fakes.screen import Screen

DRAFT = "A red fox in deep snow. " * 30
SET = json.dumps({"draft": DRAFT, "model": "z_image", "steps": 8}, separators=(",", ":"))
LONG = [
    {"type": "function_call", "id": "call_0", "call_id": "call_0", "name": "hub_set_generate_image_settings",
     "arguments": json.dumps({"draft": DRAFT}), "status": "completed"},
    {"type": "function_call_output", "id": "fco_0", "call_id": "call_0", "status": "completed",
     "output": [{"type": "input_text", "text": SET}, {"type": "input_image", "image_url": "data:image/png;base64,AA"}]},
    {"type": "function_call", "id": "call_1", "call_id": "call_1", "name": "hub_generate_image", "arguments": "{}",
     "status": "failed"},
    {"type": "function_call_output", "id": "fco_1", "call_id": "call_1", "status": "failed",
     "output": [{"type": "input_text", "text": "Error: no model\nTraceback line two"}]},
    {"type": "message", "id": "msg_1", "status": "completed", "role": "assistant",
     "content": [{"type": "output_text", "text": "Set the draft."}]},
]
SHORT = [{**LONG[0]},
         {**LONG[1], "output": [{"type": "input_text", "text": SET[:120] + "…"}]},
         {**LONG[2]},
         {**LONG[3], "output": [{"type": "input_text", "text": "Error: no model…"}]},
         {**LONG[4]}]


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


def test_brief_is_the_first_line_cut_to_120() -> None:
    assert turns.brief('{"state":"queued"}') == '{"state":"queued"}'
    assert turns.brief("x" * 120) == "x" * 120
    assert turns.brief("x" * 121) == "x" * 120 + "…"
    assert turns.brief("Error: no model\nmore") == "Error: no model…"
    assert turns.brief("") == ""


def test_lean_cuts_older_tool_results_on_a_copy() -> None:
    sent = [{"role": "user", "content": "fox"}, {"role": "assistant", "content": "Set.", "output": LONG},
            {"role": "user", "content": "now"}, {"role": "assistant", "content": "", "output": LONG}]
    before = copy.deepcopy(sent)
    out = turns.lean(sent)
    assert sent == before, "the messages given are not changed"
    assert out[1] == {"role": "assistant", "content": "Set.", "output": SHORT}
    assert out[3] is sent[3], "the newest exchange goes as it is"
    calls_ = {i["call_id"] for i in out[1]["output"] if i["type"] == "function_call"}
    results = {i["call_id"] for i in out[1]["output"] if i["type"] == "function_call_output"}
    assert calls_ == results == {"call_0", "call_1"}, "every call still has its result"
    assert turns.lean([]) == [] and turns.lean(sent[:2]) == sent[:2]
    odd = [{"role": "assistant", "content": "", "output": [{"type": "function_call_output", "call_id": "c",
                                                             "output": "plain\ntext"}, "junk"]},
           {"role": "user", "content": "hi"}]
    assert turns.lean(odd)[0]["output"] == [{"type": "function_call_output", "call_id": "c",
                                            "output": [{"type": "input_text", "text": "plain…"}]}, "junk"]


def test_context_bounds() -> None:
    assert (settings.CONTEXT, settings.CONTEXT_LOW, settings.CONTEXT_HIGH) == (8192, 2048, 131072)
    for good in (0, 2048, 8192, 131072):
        assert settings.context(good) == good
    for bad in (1, 2047, 131073, -1, "8192", 8192.0, True, None):
        with pytest.raises(Invalid) as e:
            settings.context(bad)
        assert (e.value.field, e.value.text) == ("context",
                                                 "Context length must be 0 or a whole number from 2048 to 131072")
    assert [settings.saved_context(v) for v in (None, "9", True, 0, -5, 100, 10**7, 16384)] == \
        [8192, 8192, 8192, 0, 0, 2048, 131072, 16384]
    assert settings.params({"context": 0}) == {} and settings.params({"context": 4096}) == {"params": {"num_ctx": 4096}}


async def test_the_setting_defaults_to_8192_is_checked_and_saved(hub: Hub, owui: FakeOpenWebUI) -> None:
    cookie = hub.pair()
    assert (await hub.http("GET", "/api/assistant", cookie)).json()["openwebui"]["context"] == 8192
    for bad in (1000, 200000, "8192", 2.5, True, None):
        r = await hub.http("PATCH", "/api/assistant/openwebui", cookie, {"context": bad})
        assert (r.status, r.json()["field"]) == (400, "context"), bad
    r = await hub.http("PATCH", "/api/assistant/openwebui", cookie, {"context": 16384, "keep": 3})
    assert r.status == 200 and (r.json()["openwebui"]["context"], r.json()["openwebui"]["keep"]) == (16384, 3)
    hub.core.store.flush()
    assert json.loads((hub.data / "assistant" / "openwebui.json").read_text())["context"] == 16384
    session = chat.get(hub.core.ctxs["assistant"])
    session.settings.patch({"context": "big"})   # a hand-edited file: the default
    assert session.config()["context"] == 8192
    assert (await hub.http("PATCH", "/api/assistant/openwebui", cookie, {"context": 0})).json()["openwebui"][
        "context"] == 0


async def say(hub: Hub, cookie: str, w: Screen, text: str, count: int) -> dict:
    assert (await hub.http("POST", "/api/assistant/chat", cookie, {"text": text})).status == 202
    return await settled(w, count)


async def test_plain_mode_sends_num_ctx_unless_it_is_0(hub: Hub, owui: FakeOpenWebUI) -> None:
    cookie = hub.pair()
    await hub.http("PATCH", "/api/assistant/openwebui", cookie,
                   {"url": owui.url, "key": "sk-abc", "model": "q", "context": 32768})
    w = await hub.screen(cookie, "workspace", "w")
    await say(hub, cookie, w, "hi", 2)
    assert owui.requests[-1]["body"]["params"] == {"num_ctx": 32768}
    await hub.http("PATCH", "/api/assistant/openwebui", cookie, {"context": 0})
    await say(hub, cookie, w, "again", 4)
    assert "params" not in owui.requests[-1]["body"], "0 leaves it to Open WebUI"
    await w.close()


async def test_tool_mode_sends_older_tool_results_short_and_num_ctx(hub: Hub, owui: FakeOpenWebUI) -> None:
    """Three turns with a long settings result each. The turn being answered carries every earlier reply with its
    calls whole and its results cut; the replies kept here are whole; error lines are never sent."""
    cookie, w = await tool_hub(hub, owui)
    session = chat.get(hub.core.ctxs["assistant"])
    owui.output, owui.content = LONG, "Set the draft."
    await say(hub, cookie, w, "fox", 2)
    owui.output, owui.content, owui.error = [], "", {"content": "Model q is not loaded"}
    await say(hub, cookie, w, "hi", 4)
    owui.output, owui.error = LONG, None
    await say(hub, cookie, w, "snowier", 5)
    owui.output, owui.content = [], "Done."
    await say(hub, cookie, w, "thanks", 7)
    turns_ = [r["body"] for r in calls(owui) if r["path"] == "/api/chat/completions"]
    assert all(b["params"] == {"num_ctx": 8192} for b in turns_)
    assert turns_[2]["messages"] == [{"role": "user", "content": "fox"},
                                     {"role": "assistant", "content": "Set the draft.", "output": SHORT},
                                     {"role": "user", "content": "hi"}, {"role": "user", "content": "snowier"}]
    assert turns_[3]["messages"] == [{"role": "user", "content": "fox"},
                                     {"role": "assistant", "content": "Set the draft.", "output": SHORT},
                                     {"role": "user", "content": "hi"}, {"role": "user", "content": "snowier"},
                                     {"role": "assistant", "content": "", "output": SHORT},
                                     {"role": "user", "content": "thanks"}]
    assert "Model q is not loaded" not in json.dumps(turns_), "error lines are never sent"
    kept = [m["output"] for m in session.messages if m.get("output")]
    assert kept == [LONG, LONG], "the kept replies stay whole"
    assert DRAFT in json.dumps(turns_[3]), "the draft the model wrote still goes, in its call"
    await hub.http("PATCH", "/api/assistant/openwebui", cookie, {"context": 0})
    await say(hub, cookie, w, "bye", 9)
    assert "params" not in [r["body"] for r in calls(owui) if r["path"] == "/api/chat/completions"][-1]
    await w.close()


async def test_a_chat_turn_carries_no_response_format(hub: Hub, owui: FakeOpenWebUI) -> None:
    """Only the planning asks hold the reply to a schema; the chat turns, plain or with tools, do
    not."""
    cookie = hub.pair()
    await hub.http("PATCH", "/api/assistant/openwebui", cookie, {"url": owui.url, "key": "sk-abc", "model": "q"})
    w = await hub.screen(cookie, "workspace", "w")
    await say(hub, cookie, w, "hi", 2)
    await w.close()
    cookie, w = await tool_hub(hub, owui)
    owui.output, owui.content = LONG, "Set the draft."
    await say(hub, cookie, w, "fox", 4)                 # the same conversation: "hi", its reply, "fox", its reply
    bodies = [r["body"] for r in calls(owui) if r["path"] == "/api/chat/completions"]
    assert len(bodies) == 2 and all("response_format" not in b for b in bodies)
    assert settings.held(None) == {}
    await w.close()
