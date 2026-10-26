"""Run the real controller (Core + uvicorn) on 127.0.0.1 with fakes, inside the test's event loop."""
from __future__ import annotations

import asyncio
import copy
import json
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from hub.core.api import Module
from hub.core.line import Timing
from hub.core.registry import discover, validate
from hub.core.runtime import Core
from hub.server import HubServer, bind, config
from hub.settings import DEFAULTS, save
from hub.settings import validate as validate_settings
from tests.fakes.fake_probes import FakeProbes
from tests.fakes.screen import Resp, Screen, http

FAST = Timing(hello_s=1.0, beat_s=25.0, deliver_s=0.5, session_grace_s=0.4)


@dataclass
class Hub:
    core: Core
    server: HubServer
    task: asyncio.Task
    port: int
    data: Path
    probes: FakeProbes

    @property
    def origin(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def pair(self, name: str = "Desk", addr: str = "127.0.0.1") -> str:
        """Pair a screen directly; -> `<id>.<secret>` (the cookie value)."""
        code, _ = self.core.devices.mint_code(name)
        result = self.core.devices.redeem(code, addr)
        assert result is not None
        return f"{result[0].id}.{result[1]}"

    async def http(self, method: str, path: str, cookie: str | None = None, json_body: Any = None,
                   headers: dict[str, str] | None = None, body: bytes | str = b"", origin: bool = True) -> Resp:
        hdrs = dict(headers or {})
        if cookie:
            hdrs["Cookie"] = f"hub_screen={cookie}"
        if origin and method != "GET":
            hdrs.setdefault("Origin", self.origin)
        if json_body is not None:
            body = json.dumps(json_body)
            hdrs.setdefault("Content-Type", "application/json")
        return await http(self.port, method, path, hdrs, body)

    async def screen(self, cookie: str, role: str, screen: str, label: str | None = None) -> Screen:
        s = await Screen.open(self.port, cookie)
        await s.hello(role, screen, label)
        return s

    async def close(self) -> None:
        self.server.should_exit = True
        await asyncio.wait_for(self.task, 10)


def own_modules() -> list[Module]:
    from hub.modules.assistant.manifest import MODULE as assistant
    from hub.modules.network.manifest import MODULE as network

    return [network, assistant]


async def start_hub(data: Path, *, lanes: Iterable[Any] = (), modules: list[Module] | str = "own",
                    probes: FakeProbes | None = None, timing: Timing = FAST, settings: dict | None = None,
                    dist: Path | None = None, ping_s: float | None = None) -> Hub:
    s = copy.deepcopy(DEFAULTS)
    s["server"]["bind"] = ["127.0.0.1"]
    for key, value in (settings or {}).items():
        s[key] = {**s[key], **value} if isinstance(value, dict) and isinstance(s.get(key), dict) else value
    s = validate_settings(s)
    data.mkdir(parents=True, exist_ok=True)
    save(data, s)
    probes = probes or FakeProbes()
    socks, bound, missing = bind(["127.0.0.1"], 0)
    port = socks[0].getsockname()[1]
    extra = {} if dist is None else {"dist": dist}
    core = Core(data, s, probes, port=port, bound=bound, missing=missing, timing=timing, **extra)
    for lane in lanes:
        core.add_engine(lane, lane)
    if modules == "discover":
        mods, _ = discover(s["modules_disabled"])
    elif modules == "own":
        mods = own_modules()
    else:
        validate(list(modules))
        mods = list(modules)
    core.load_modules(mods)
    cfg = config(core.app())
    if ping_s is not None:
        cfg.ws_ping_interval = cfg.ws_ping_timeout = ping_s
    server = HubServer(cfg, core)
    await core.start()
    task = asyncio.get_running_loop().create_task(server.serve(sockets=socks))
    for _ in range(200):
        if server.started:
            break
        await asyncio.sleep(0.01)
    return Hub(core, server, task, port, data, probes)
