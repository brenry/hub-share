"""Start the controller: settings, sockets (LAN IP + 127.0.0.1, never 0.0.0.0), engines, modules, uvicorn.

stdout gets exactly two lines per run, `hub started on ...` and `hub stopped`, plus real errors.
"""
from __future__ import annotations

import asyncio
import shutil
import socket
import sys
from pathlib import Path
from typing import Any

import uvicorn

from hub.core.line import Timing
from hub.core.probes import Probes
from hub.core.registry import RegistryError, discover
from hub.core.runtime import Core
from hub.settings import SettingsError, host_entry, load

RESTART_MARKER = ("run", "restart")
RETIRED_DATA = ("llm",)  # data folders of removed modules (LLM Models, 2026-10-10): the hub's own, deleted at start


class HubServer(uvicorn.Server):
    """Says `going_off` and closes every line (4000/4001) before uvicorn closes them with 1012."""

    def __init__(self, config: uvicorn.Config, core: Core) -> None:
        super().__init__(config)
        self.core = core

    async def shutdown(self, sockets: list[socket.socket] | None = None) -> None:
        marker = self.core.data_dir.joinpath(*RESTART_MARKER)
        restart = marker.exists()
        marker.unlink(missing_ok=True)
        await self.core.stop(restart)
        await super().shutdown(sockets)
        print("hub stopped", flush=True)


def config(app: Any) -> uvicorn.Config:
    return uvicorn.Config(app, ws="websockets-sansio", http="h11", loop="asyncio", lifespan="off",
                          ws_ping_interval=15.0, ws_ping_timeout=15.0, ws_max_size=1 << 20, ws_max_queue=32,
                          ws_per_message_deflate=False, access_log=False, log_config=None, log_level="error",
                          server_header=False, date_header=False, proxy_headers=False, timeout_graceful_shutdown=3,
                          limit_concurrency=64, h11_max_incomplete_event_size=16_384)


def bind(addrs: list[str], port: int) -> tuple[list[socket.socket], list[str], list[str]]:
    """Bind each address (all on one port). -> (sockets, bound addresses, addresses that failed)."""
    socks, bound, missing = [], [], []
    for addr in addrs:
        family = socket.AF_INET6 if ":" in addr else socket.AF_INET
        sock = socket.socket(family, socket.SOCK_STREAM)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            if family == socket.AF_INET6:
                sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
            sock.bind((addr, port))
        except OSError as e:
            sock.close()
            missing.append(addr)
            print(f"hub: cannot listen on {host_entry(addr, port)} ({e.strerror}); fix with: hub network reset",
                  file=sys.stderr)
            continue
        port = port or sock.getsockname()[1]
        socks.append(sock)
        bound.append(addr)
    return socks, bound, missing


def wire_engines(core: Core, settings: dict, data_dir: Path, probes: Any) -> None:
    gpus = [g for g in settings["gpus"] if g["engine"]]
    if not gpus:
        return
    try:
        from hub.core import engine
    except ImportError as e:
        raise SystemExit(f"hub: the image engine is not installed ({e})") from None
    for gpu in gpus:
        try:
            lane, eng = engine.create({**settings, "gpus": [gpu, *(g for g in settings["gpus"] if g is not gpu)]},
                                      data_dir, probes)
        except Exception as e:
            raise SystemExit(f"hub: the image engine for {gpu['id']} could not be set up: {e}") from None
        core.add_engine(lane, eng)


def build(data_dir: Path, settings: dict, socks: list[socket.socket], bound: list[str], missing: list[str],
          probes: Any, timing: Timing | None = None, engines: bool = True) -> tuple[Core, HubServer]:
    port = socks[0].getsockname()[1]
    core = Core(data_dir, settings, probes, port=port, bound=bound, missing=missing, timing=timing)
    if engines:
        wire_engines(core, settings, data_dir, probes)
    mods, errors = discover(settings["modules_disabled"])
    for line in errors:
        print(line, file=sys.stderr)
    core.load_modules(mods)
    return core, HubServer(config(core.app()), core)


async def serve(data_dir: Path) -> int:
    try:
        settings = load(data_dir)
    except SettingsError as e:
        print(f"hub: {e}", file=sys.stderr)
        return 1
    data_dir.joinpath(*RESTART_MARKER).unlink(missing_ok=True)
    for name in RETIRED_DATA:
        shutil.rmtree(data_dir / name, ignore_errors=True)
    socks, bound, missing = bind(settings["server"]["bind"], settings["server"]["port"])
    if not socks:
        print("hub: could not listen on any address; fix with: hub network reset", file=sys.stderr)
        return 1
    try:
        core, server = build(data_dir, settings, socks, bound, missing, Probes())
    except (RegistryError, ValueError) as e:
        print(f"hub: {e}" if not str(e).startswith("hub:") else e, file=sys.stderr)
        return 1
    await core.start()
    port = socks[0].getsockname()[1]
    print("hub started on " + " ".join(f"http://{host_entry(a, port)}" for a in bound), flush=True)
    await server.serve(sockets=socks)
    return 0


def run(data_dir: Path) -> int:
    return asyncio.run(serve(data_dir))
