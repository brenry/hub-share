"""`python -m hub ...` in a subprocess (the CLI installs the netlock hook, which must not leak into pytest)."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from hub.core.devices import Devices

ROOT = Path(__file__).resolve().parents[2]


def hub_cli(*args: str, path: Path | None = None, env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    e = {**os.environ, **(env or {})}
    e.pop("HUB_DATA", None) if env is None or "HUB_DATA" not in env else None
    if path is not None:
        e["PATH"] = f"{path}{os.pathsep}{e['PATH']}"
    return subprocess.run([sys.executable, "-m", "hub", *args], cwd=ROOT, capture_output=True, text=True,
                          timeout=60, env=e)


def fake_tool(folder: Path, name: str, script: str) -> None:
    folder.mkdir(exist_ok=True)
    (folder / name).write_text("#!/bin/sh\n" + script)
    (folder / name).chmod(0o755)


@pytest.fixture
def data(tmp_path: Path) -> Path:
    d = tmp_path / "data"
    r = hub_cli("init", "--data", str(d), "--bind", "127.0.0.1", "--engine-root", str(tmp_path / "engine"),
                "--engine-python", "/usr/bin/false", "--lora-folder", str(tmp_path / "l1"), "--lora-folder",
                str(tmp_path / "l2"), "--port", "42011")
    assert r.returncode == 0, r.stderr
    assert r.stdout == f"Settings written to {d / 'settings.json'}\n"
    assert r.stderr == f"Note: {tmp_path / 'engine'} does not exist yet\n"
    return d


def settings(d: Path) -> dict:
    return json.loads((d / "settings.json").read_text())


def test_help_documents_every_command() -> None:
    out = hub_cli("--help").stdout
    for cmd in ("serve", "init --bind IP [--engine-root P --engine-python P] [--lora-folder P]...",
                "pair --name NAME", "network show", "network set [--bind IP[,IP]] [--port N]", "network reset",
                "restart", "engine set --root P --python P", "engine restore --before FILE", "engine clear",
                "HUB_DATA"):
        assert cmd in out


def test_init_writes_and_updates_settings(data: Path, tmp_path: Path) -> None:
    s = settings(data)
    assert s["server"]["bind"] == ["127.0.0.1"] and s["server"]["port"] == 42011
    assert s["engine"]["root"] == str(tmp_path / "engine") and s["engine"]["python"] == "/usr/bin/false"
    assert s["modules"]["loras"]["folders"] == [str(tmp_path / "l1"), str(tmp_path / "l2")]
    assert s["gpus"] == [{"id": "gpu0", "index": 0, "uuid": None, "engine": True}]
    assert os.stat(data / "settings.json").st_mode & 0o777 == 0o600
    s["vram"]["idle_minutes"] = 30
    (data / "settings.json").write_text(json.dumps(s))
    r = hub_cli("init", "--data", str(data), "--bind", "127.0.0.1", "--engine-root", "/srv/e",
                "--engine-python", "/srv/e/python", "--gpu", "1")
    assert r.returncode == 0
    s = settings(data)
    assert s["vram"]["idle_minutes"] == 30 and s["engine"]["root"] == "/srv/e" and s["gpus"][0]["id"] == "gpu1"
    assert s["modules"]["loras"]["folders"] == [str(tmp_path / "l1"), str(tmp_path / "l2")]


def test_init_refuses_every_interface(tmp_path: Path) -> None:
    r = hub_cli("init", "--data", str(tmp_path / "d"), "--bind", "0.0.0.0", "--engine-root", "/e",
                "--engine-python", "/e/p")
    assert r.returncode == 1 and "listens on every network" in r.stderr and not (tmp_path / "d").exists()


def test_pair_prints_a_one_time_link(data: Path) -> None:
    r = hub_cli("pair", "--name", "Desktop", "--data", str(data))
    assert r.returncode == 0 and r.stdout.startswith("http://127.0.0.1:42011/pair#c=")
    code = r.stdout.strip().split("#c=")[1]
    again = hub_cli("pair", "--name", "Laptop", env={"HUB_DATA": str(data)})
    devs = Devices(data)
    assert again.returncode == 0 and {p["name"] for p in devs.pending()} == {"Desktop", "Laptop"}
    device, _ = devs.redeem(code, "127.0.0.1")  # type: ignore[misc]
    assert device.name == "Desktop"
    bad = hub_cli("pair", "--name", "", "--data", str(data))
    assert bad.returncode == 1 and bad.stderr == "hub: Use a name of printable characters, not blank\n"


def test_network_show_set_and_reset(data: Path, tmp_path: Path) -> None:
    devs = Devices(data)
    devs.redeem(devs.mint_code("Desktop")[0], "192.0.2.8")
    show = hub_cli("network", "show", "--data", str(data)).stdout
    assert show == ("Bind: 127.0.0.1\nPort: 42011\nAddresses: http://127.0.0.1:42011\nDevices:\n"
                    "  Desktop 192.0.2.8\n")
    bad = hub_cli("network", "set", "--bind", "192.0.2.99", "--data", str(data))
    assert bad.returncode == 1 and "192.0.2.99 is not an address of this server" in bad.stderr
    assert hub_cli("network", "set", "--bind", "0.0.0.0", "--data", str(data)).returncode == 1
    tools = tmp_path / "bin"
    fake_tool(tools, "systemctl", 'echo "$@" >> "$HUB_LOG"; [ "$2" = "is-active" ] && exit 3; exit 0\n')
    log = tmp_path / "systemctl.log"
    ok = hub_cli("network", "set", "--bind", "127.0.0.1", "--port", "42020", "--data", str(data), path=tools,
                 env={"HUB_LOG": str(log)})
    assert ok.stdout == "Listening on: 127.0.0.1 port 42020\nSaved. Start the hub to use it.\n"
    assert settings(data)["server"]["port"] == 42020
    only_port = hub_cli("network", "set", "--port", "42021", "--data", str(data), path=tools, env={"HUB_LOG": str(log)})
    assert only_port.returncode == 0 and settings(data)["server"]["port"] == 42021
    neither = hub_cli("network", "set", "--data", str(data))
    assert neither.returncode == 1 and neither.stderr == "hub: give --bind, --port or both\n"
    assert hub_cli("network", "set", "--port", "70000", "--data", str(data)).returncode == 1
    fake_tool(tools, "ip", "echo '" + json.dumps([
        {"ifname": "docker0", "operstate": "UP", "addr_info": [{"family": "inet", "local": "10.0.0.1"}]},
        {"ifname": "eth0", "operstate": "UP", "addr_info": [{"family": "inet", "local": "192.0.2.20"}]}]) + "'\n")
    fake_tool(tools, "systemctl", 'echo "$@" >> "$HUB_LOG"; exit 0\n')
    reset = hub_cli("network", "reset", "--data", str(data), path=tools, env={"HUB_LOG": str(log)})
    assert reset.stdout == "Listening on: 192.0.2.20, 127.0.0.1 port 42010\nRestarting the hub.\n"
    assert settings(data)["server"] == {"bind": ["192.0.2.20", "127.0.0.1"], "port": 42010, "extra_hosts": [],
                                        "allow_any_interface": False}
    assert log.read_text().splitlines()[-2:] == ["--user is-active --quiet hub.service", "--user restart hub.service"]
    assert (data / "run" / "restart").exists()


def test_restart_and_missing_data(data: Path, tmp_path: Path) -> None:
    tools = tmp_path / "bin"
    fake_tool(tools, "systemctl", "exit 1\n")
    r = hub_cli("restart", "--data", str(data), path=tools)
    assert r.returncode == 1 and "systemctl --user restart hub" in r.stderr
    assert not (data / "run" / "restart").exists()
    r = hub_cli("network", "show")
    assert r.returncode == 1 and r.stderr == "hub: give --data DIR or set HUB_DATA\n"
    r = hub_cli("network", "show", "--data", str(tmp_path / "nowhere"))
    assert r.returncode == 1 and "run: hub init" in r.stderr
