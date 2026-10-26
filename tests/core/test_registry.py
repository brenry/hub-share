"""Module discovery, manifest validation, and every manifest field wired through the running controller."""
from __future__ import annotations

import asyncio
import json
import shutil
import textwrap
from pathlib import Path
from typing import Any

import pytest
from starlette.requests import Request

from hub.core.api import Action, Card, CardState, Ctx, Listing, Module, Route, Screen, Setting, SocketGroup, Tab
from hub.core.registry import RegistryError, discover, validate
from tests.core.harness import Hub, own_modules, start_hub

MANIFEST = textwrap.dedent('''
    from hub.core.api import Module, Tab
    MODULE = Module(id="{id}", title="{title}", tab=Tab("{title}", 20))
''')


def make_package(root: Path, name: str, modules: dict[str, str]) -> None:
    pkg = root / name
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    for folder, body in modules.items():
        (pkg / folder).mkdir()
        if body:
            (pkg / folder / "manifest.py").write_text(body)


def test_discovery_finds_folders_skips_broken_and_disabled(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.syspath_prepend(str(tmp_path))
    make_package(tmp_path, "pkg_a", {"alpha": MANIFEST.format(id="alpha", title="Alpha"),
                                     "beta": MANIFEST.format(id="beta", title="Beta"),
                                     "broken": "raise RuntimeError('half written')",
                                     "nomodule": "X = 1", "empty": "", "_private": MANIFEST.format(id="p", title="P")})
    mods, errors = discover(package="pkg_a")
    assert [m.id for m in mods] == ["alpha", "beta"]
    assert errors == ["hub: module broken was not loaded: RuntimeError: half written",
                      "hub: module nomodule was not loaded: manifest.py has no MODULE"]
    assert [m.id for m in discover(["beta"], package="pkg_a")[0]] == ["alpha"]
    shutil.rmtree(tmp_path / "pkg_a" / "beta")
    assert [m.id for m in discover(package="pkg_a")[0]] == ["alpha"]


def test_the_shipped_modules_load(tmp_path: Path) -> None:
    mods, errors = discover()
    assert {"network", "assistant"} <= {m.id for m in mods} and errors == []


async def noop(*args: Any) -> None:
    return None


@pytest.mark.parametrize("mod, rule", [
    (Module(id="Bad_Id", title="x"), "kebab-case"),
    (Module(id="settings", title="x"), "reserved"),
    (Module(id="a", title="x", sockets=(SocketGroup("s", "S", ("image",), 1),) * 2), "socket group ids"),
    (Module(id="a", title="x", sockets=(SocketGroup("s", "S", ("pdf",), 1),)), "unknown kinds"),  # type: ignore
    (Module(id="a", title="x", routes=(Route("GET", "/x", noop),) * 2), "share a method"),
    (Module(id="a", title="x", routes=(Route("GET", "x", noop),)), "bad method, path or auth"),
    (Module(id="a", title="x", routes=(Route("GET", "/x", noop, auth="bearer"),)), "bad method, path or auth"),
    (Module(id="a", title="x", routes=(Route("PUT", "/x", noop, body_limit=30 << 20),)), "body_limit"),
    (Module(id="a", title="x", handlers={"ping": noop}), "must be named a.<name>"),
    (Module(id="a", title="x", lanes=("Bad Lane",)), "snake_case"),
    (Module(id="a", title="x", jobs={"Bad Kind": noop}), "snake_case"),  # type: ignore[dict-item]
    (Module(id="a", title="x", actions=(Action("Get Job", "d.", {}, noop),)), "unique snake_case"),  # type: ignore
    (Module(id="a", title="x", actions=(Action("twin", "d.", {}, noop),) * 2), "unique snake_case"),  # type: ignore
    (Module(id="a", title="x", listings=(Listing("Models", "d.", {}, noop),)), "unique snake_case"),  # type: ignore
    (Module(id="a", title="x", listings=(Listing("x", "d.", {}, noop),), actions=(Action("list_x", "d.", {}, noop),)),
     "tool list_x must be a unique"),  # type: ignore
    (Module(id="a", title="x", actions=(Action("x", "no period", {}, noop),)), "ending with a period"),  # type: ignore
    (Module(id="a", title="x", actions=(Action("x", "w" * 200 + ".", {}, noop),)), "at most 200"),  # type: ignore
    (Module(id="a", title="x", actions=(Action("x", "d.", "nope", noop),)), "with a schema"),  # type: ignore
    (Module(id="a", title="x", screen=Screen((), noop, noop)), "unique snake_case names"),  # type: ignore
    (Module(id="a", title="x", screen=Screen((Setting("Steps", "integer"),), noop, noop)), "snake_case names"),
    (Module(id="a", title="x", screen=Screen((Setting("s", "integer"),) * 2, noop, noop)), "unique snake_case"),
    (Module(id="a", title="x", screen=Screen((Setting("s", "slider"),), noop, noop)), "unknown kind"),  # type: ignore
    (Module(id="a", title="x", screen=Screen((Setting("s", "seed", choices=("1",)),), noop, noop)), "choices"),
    (Module(id="a", title="x", screen=Screen((Setting("s", "choice", choices=(1, 2)),), noop, noop)), "choices"),
    (Module(id="a", title="x", screen=Screen((Setting("s", "number", choices=("1",)),), noop, noop)), "choices"),
    (Module(id="a", title="x", screen=Screen((Setting("s", "seed"),), noop, noop)), "bounds in lo and hi"),
    (Module(id="a", title="x", screen=Screen((Setting("s", "loras", lo=0),), noop, noop)), "bounds in lo and hi"),
    (Module(id="a", title="x", screen=Screen((Setting("s", "loras", lo=2, hi=0),), noop, noop)), "bounds in lo and hi"),
    (Module(id="a", title="x", screen=Screen((Setting("s", "names"),), noop, noop)), "bounds in lo and hi"),
    (Module(id="a", title="x", screen=Screen((Setting("s", "names", hi=0),), noop, noop)), "bounds in lo and hi"),
    (Module(id="a", title="x", screen=Screen((Setting("s", "text"),), noop, noop),
            actions=(Action("get_a_settings", "d.", {}, noop),)), "tool get_a_settings must be a unique"),
])
def test_manifest_rules(mod: Module, rule: str) -> None:
    with pytest.raises(RegistryError, match=rule):
        validate([mod])


def test_duplicate_ids_fail() -> None:
    with pytest.raises(RegistryError, match="same id"):
        validate([Module(id="a", title="A"), Module(id="a", title="B")])


def test_a_names_setting_with_a_top_passes() -> None:
    validate([Module(id="a", title="A", screen=Screen((Setting("references", "names", hi=1),), noop, noop))])
    validate([Module(id="a", title="A", screen=Screen((Setting("references", "names", hi=6),), noop, noop))])


def test_generated_tool_names_are_unique_across_modules() -> None:
    a = Module(id="a", title="A", listings=(Listing("things", "Things.", {}, noop),))
    b = Module(id="b", title="B", actions=(Action("list_things", "Things.", {}, noop),))
    validate([a])
    validate([b])
    with pytest.raises(RegistryError, match="module b: tool list_things must be a unique"):
        validate([a, b])


EVENTS: list[tuple[str, Any]] = []


async def hello(ctx: Ctx, request: Request) -> dict:
    return {"greeting": ctx.settings["greeting"], "device": request.state.device.name}


async def echo(ctx: Ctx, request: Request) -> dict:
    body = await request.json()
    ctx.doc("notes", {"n": 0}).patch({"last": body})
    ctx.bus.publish("events", "changed", {"last": body})
    return {"saved": body}


async def ping(ctx: Ctx, screen: dict, data: dict) -> dict:
    ctx.emit("demo.pinged", {"from": screen["role"]})
    return {"pong": data.get("n")}


async def heard(ctx: Ctx, data: dict) -> None:
    EVENTS.append(("pinged", data))


async def start(ctx: Ctx) -> None:
    EVENTS.append(("start", str(ctx.data_dir)))


async def stop(ctx: Ctx) -> None:
    EVENTS.append(("stop", ctx.module_id))


DEMO = Module(id="demo", title="Demo", tab=Tab("Demo", 5),
              routes=(Route("GET", "/hello", hello), Route("POST", "/echo", echo)),
              handlers={"demo.ping": ping}, lanes=("events",), listens={"demo.pinged": heard},
              card=Card("Demo", 950, lambda ctx: CardState("All good", "ok")), start=start, stop=stop)


@pytest.fixture
async def hub(tmp_path: Path):  # type: ignore[no-untyped-def]
    EVENTS.clear()
    h = await start_hub(tmp_path / "data", modules=[*own_modules(), DEMO], settings={"modules": {"demo": {
        "greeting": "hi"}}})
    yield h
    await h.close()


async def test_every_manifest_field_is_wired(hub: Hub) -> None:
    assert EVENTS == [("start", str(hub.data / "demo"))]
    cookie = hub.pair()
    assert (await hub.http("GET", "/api/demo/hello", cookie=cookie)).json() == {"greeting": "hi", "device": "Desk"}
    w = await hub.screen(cookie, "workspace", "w")
    assert "demo.events" in w.welcome["you"]["lanes"]
    assert [t["id"] for t in w.welcome["tools"]] == ["demo"]
    assert [c["module"] for c in w.welcome["cards"]] == ["network", "assistant", "demo"]
    r = await hub.http("POST", "/api/demo/echo", cookie=cookie, json_body={"x": 1})
    assert r.json() == {"saved": {"x": 1}}
    assert (await w.recv("demo.changed"))["d"] == {"last": {"x": 1}}
    await w.send("demo.ping", {"n": 7}, id="p1")
    assert (await w.recv("reply"))["d"] == {"pong": 7}
    await asyncio.sleep(0.05)
    assert ("pinged", {"from": "workspace"}) in EVENTS
    await w.send("demo.nothing", {}, id="p2")
    assert (await w.recv("error"))["d"]["code"] == "protocol"
    with pytest.raises(TypeError):
        hub.core.ctxs["demo"].settings["greeting"] = "changed"  # type: ignore[index]
    hub.core.store.flush()
    assert json.loads((hub.data / "demo" / "notes.json").read_text()) == {"n": 0, "last": {"x": 1}}


async def test_stop_hooks_run_at_shutdown(tmp_path: Path) -> None:
    EVENTS.clear()
    hub = await start_hub(tmp_path / "data", modules=[DEMO], settings={"modules": {"demo": {"greeting": "x"}}})
    await hub.close()
    assert EVENTS[-1] == ("stop", "demo")
