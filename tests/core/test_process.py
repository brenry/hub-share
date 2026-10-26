"""The real `python -m hub serve` process: netlock on, two stdout lines, no stderr, going_off on SIGTERM,
and the retired LLM module's data folder deleted at start."""
from __future__ import annotations

import asyncio
import copy
import json
import signal
import socket
import sys
from pathlib import Path

import pytest

from hub.settings import DEFAULTS, save, validate
from tests.fakes.screen import Screen, http

ROOT = Path(__file__).resolve().parents[2]


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


async def cli(*args: str) -> str:
    proc = await asyncio.create_subprocess_exec(sys.executable, "-m", "hub", *args, cwd=ROOT,
                                                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    out, err = await proc.communicate()
    assert proc.returncode == 0, err.decode()
    return out.decode().strip()


async def start(data: Path) -> tuple[asyncio.subprocess.Process, int]:
    port = free_port()
    s = copy.deepcopy(DEFAULTS)
    s["server"]["port"] = port
    save(data, validate(s))
    proc = await asyncio.create_subprocess_exec(sys.executable, "-m", "hub", "serve", "--data", str(data), cwd=ROOT,
                                                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    line = await asyncio.wait_for(proc.stdout.readline(), 20)  # type: ignore[union-attr]
    assert line.decode() == f"hub started on http://127.0.0.1:{port}\n"
    return proc, port


async def paired_cookie(data: Path, port: int) -> str:
    code = (await cli("pair", "--name", "Desk", "--data", str(data))).split("#c=")[1]
    r = await http(port, "POST", "/api/pair", {"Origin": f"http://127.0.0.1:{port}",
                                               "Content-Type": "application/json"}, json.dumps({"code": code}))
    assert r.status == 200
    return r.headers["set-cookie"].split(";")[0].split("=", 1)[1]


@pytest.mark.parametrize("restart, code", [(False, 4000), (True, 4001)])
async def test_serve_is_quiet_and_says_going_off(tmp_path: Path, restart: bool, code: int) -> None:
    data = tmp_path / "data"
    (data / "llm" / "purposes").mkdir(parents=True)
    (data / "llm" / "purposes" / "assistant.md").write_text("an old system prompt")
    proc, port = await start(data)
    try:
        assert not (data / "llm").exists()
        cookie = await paired_cookie(data, port)
        screen = await Screen.open(port, cookie)
        welcome = await screen.hello("media", "scr_1", "Right")
        assert welcome["presence"]["screens"]["media"] == 1
        reader, writer = await asyncio.open_connection("127.0.0.1", port)   # the desktop app's bare TCP probe
        writer.close()
        for raw in (b"GARBAGE\r\n\r\n", b"GET / HTTP/1.1\r\nHost: x\r\nX: " + b"a" * 20_000 + b"\r\n\r\n"):
            reader, writer = await asyncio.open_connection("127.0.0.1", port)   # malformed: nothing is printed
            writer.write(raw)
            await reader.read()
            writer.close()
        assert (await http(port, "GET", "/?screen=media", {"Cookie": f"hub_screen={cookie}"})).status == 200
        if restart:
            (data / "run").mkdir(exist_ok=True)
            (data / "run" / "restart").touch()
        proc.send_signal(signal.SIGTERM)
        assert await screen.closed() == code
        reasons = [m["d"]["reason"] for m in screen.seen if m["t"] == "going_off"]
        assert reasons == ["restart" if restart else "shutdown"]
        out, err = await asyncio.wait_for(proc.communicate(), 20)
        assert out.decode() == "hub stopped\n"
        assert err.decode() == ""
    finally:
        if proc.returncode is None:
            proc.kill()
            await proc.wait()
    files = [p.relative_to(data) for p in data.rglob("*") if p.is_file()]
    assert {"devices.json", "settings.json"} <= {str(f) for f in files}
    assert [f for f in files if f.suffix not in (".json", ".md")] == []  # state documents only: no logs
