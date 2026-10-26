"""A service one module offers others by name (`ctx.offer`, `ctx.service`), so the Director asks the
model without importing the assistant module; an unknown name is one line. The assistant offers "ask": the model in
Settings -> Assistant asked once, no tools, nothing kept."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from hub.core.api import Invalid, Module
from tests.core.harness import Hub, own_modules, start_hub
from tests.fakes.openwebui import FakeOpenWebUI, calls

OTHER = Module(id="other", title="Other")


@pytest.fixture
def owui():  # type: ignore[no-untyped-def]
    fake = FakeOpenWebUI()
    yield fake
    fake.close()


@pytest.fixture
async def hub(tmp_path: Path):  # type: ignore[no-untyped-def]
    h = await start_hub(tmp_path / "data", modules=[*own_modules(), OTHER])
    yield h
    await h.close()


async def test_a_service_offered_is_used_by_name_and_an_unknown_one_is_one_line(hub: Hub) -> None:
    async def double(n: int) -> int:
        return 2 * n

    hub.core.ctxs["network"].offer("double", double)
    assert await hub.core.ctxs["other"].service("double")(4) == 8
    with pytest.raises(Invalid) as err:
        hub.core.ctxs["other"].service("nothing")
    assert (err.value.field, err.value.text) == ("assistant", "The assistant is not running")


async def test_without_the_assistant_the_ask_is_the_one_line(tmp_path: Path) -> None:
    h = await start_hub(tmp_path / "data", modules=[OTHER])
    try:
        with pytest.raises(Invalid) as err:
            h.core.ctxs["other"].service("ask")
        assert err.value.text == "The assistant is not running"
    finally:
        await h.close()


async def test_the_assistant_offers_ask_with_its_link_settings(hub: Hub, owui: FakeOpenWebUI) -> None:
    ask = hub.core.ctxs["other"].service("ask")
    with pytest.raises(Invalid) as err:
        await ask([{"role": "user", "content": "Shot plan: x"}])
    assert err.value.text == "Set the Open WebUI model name in Settings -> Assistant"
    cookie = hub.pair()
    await hub.http("PATCH", "/api/assistant/openwebui", cookie, {"url": owui.url, "key": "sk-abc", "model": "q"})
    assert await ask([]) == ("q", ""), "no messages: the model's name, nothing asked"
    assert calls(owui) == []
    sent = [{"role": "system", "content": "rules"}, {"role": "user", "content": "Shot plan: x"}]
    assert await ask(sent) == ("q", "Hello from Open WebUI.")
    [req] = calls(owui)
    assert req["path"] == "/api/chat/completions" and req["body"] == {
        "model": "q", "messages": sent, "stream": False, "params": {"num_ctx": 8192}}, "no tools, no chat kept"
    hub.core.store.flush()
    assert sorted(p.name for p in (hub.data / "assistant").iterdir()) == ["openwebui.json"]
    assert "Shot plan" not in json.dumps(json.loads((hub.data / "assistant" / "openwebui.json").read_text()))


async def test_the_ask_holds_the_reply_to_a_schema_when_given(hub: Hub, owui: FakeOpenWebUI) -> None:
    """A schema goes as OpenAI's `response_format` json_schema beside the other fields; none, no field."""
    ask = hub.core.ctxs["other"].service("ask")
    await hub.http("PATCH", "/api/assistant/openwebui", hub.pair(), {"url": owui.url, "key": "sk-abc", "model": "q"})
    sent, schema = [{"role": "user", "content": "Shot plan: x"}], {"type": "object", "required": ["a"]}
    assert await ask(sent, schema) == ("q", "Hello from Open WebUI.")
    assert await ask(sent) == ("q", "Hello from Open WebUI.")
    held, plain = (r["body"] for r in calls(owui))
    assert held == {"model": "q", "messages": sent, "stream": False, "params": {"num_ctx": 8192}, "response_format": {
        "type": "json_schema", "json_schema": {"name": "hub_plan", "schema": schema}}}
    assert plain == {"model": "q", "messages": sent, "stream": False, "params": {"num_ctx": 8192}}
    assert json.dumps(plain) == json.dumps({k: v for k, v in held.items() if k != "response_format"})
