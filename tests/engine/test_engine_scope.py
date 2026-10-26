"""The engine worker in a cgroup of its own (`hub/core/enginescope.py`): asked of systemd's user manager once, the
worker exec'd in the same process so the pid, the socket and the parent-death rule hold, and its environment clean.
A stand-in `systemd-run` on PATH does what the real one does in --scope mode: record, then exec the command."""
from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from hub.core import enginescope
from hub.core.supervisor import EngineFailed, Supervisor
from tests.engine.test_supervisor import Recorder, spawn

STAND_IN = """#!/bin/sh
echo "$@" >> "$(dirname "$0")/calls.log"
[ -e "$(dirname "$0")/refuse" ] && exit 1
while [ "$1" != "--" ]; do shift; done
shift
exec "$@"
"""


@pytest.fixture
def stand_in(tmp_path, monkeypatch) -> Path:
    tools = tmp_path / "tools"
    tools.mkdir()
    run = tools / "systemd-run"
    run.write_text(STAND_IN)
    run.chmod(run.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("PATH", f"{tools}:{os.environ['PATH']}")
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path / "run-user"))
    monkeypatch.setenv("DBUS_SESSION_BUS_ADDRESS", "unix:path=/nowhere")
    enginescope.reset()
    return tools / "calls.log"


def test_asked_once_and_only_with_a_user_manager(stand_in, monkeypatch):
    assert enginescope.available() is True
    first = stand_in.read_text().splitlines()
    assert len(first) == 1 and first[0].startswith("--user --scope --quiet --collect --description=Hub engine")
    assert first[0].endswith(" -u DBUS_SESSION_BUS_ADDRESS -u INVOCATION_ID true"), "the worker's own wrapper"
    assert enginescope.available() is True and len(stand_in.read_text().splitlines()) == 1, "asked once"
    enginescope.reset()
    (stand_in.parent / "refuse").write_text("")
    assert enginescope.available() is False, "a manager that refuses: the worker starts as before"
    enginescope.reset()
    monkeypatch.delenv("XDG_RUNTIME_DIR")
    assert enginescope.available() is False


def test_wrap_hands_systemd_its_variables_and_the_worker_none_of_them(stand_in):
    argv, env = enginescope.wrap(["/py", "main.py"], {"PATH": "/bin", "HOME": "/h"}, "0")
    assert argv[1:7] == ["--user", "--scope", "--quiet", "--collect", "--description=Hub engine (GPU 0)", "--"]
    assert argv[7].endswith("env") and argv[8:14] == ["-u", "XDG_RUNTIME_DIR", "-u", "DBUS_SESSION_BUS_ADDRESS",
                                                      "-u", "INVOCATION_ID"]
    assert argv[14:] == ["/py", "main.py"]
    assert env["XDG_RUNTIME_DIR"] and env["DBUS_SESSION_BUS_ADDRESS"] and env["HOME"] == "/h"


async def test_the_worker_runs_through_the_scope_with_its_own_pid_and_clean_environment(stand_in, tmp_path):
    rec = Recorder()
    sup = Supervisor(spawn(tmp_path), rec)
    await sup.start()
    try:
        assert sup.state == "ready" and sup.pid
        assert "--scope" in stand_in.read_text().splitlines()[-1]
        cmdline = Path(f"/proc/{sup.pid}/cmdline").read_bytes().split(b"\0")
        assert any(part.endswith(b"fake_worker.py") for part in cmdline), "the pid the Hub holds is the worker's"
        raw = Path(f"/proc/{sup.pid}/environ").read_bytes().split(b"\0")
        environ = dict(x.split(b"=", 1) for x in raw if b"=" in x)
        assert b"XDG_RUNTIME_DIR" not in environ and b"DBUS_SESSION_BUS_ADDRESS" not in environ
        assert environ[b"LANG"] == b"C.UTF-8"
    finally:
        await sup.stop()
    assert sup.state == "none"


async def test_a_scope_that_does_not_hold_falls_back_to_a_plain_start(stand_in, tmp_path):
    """The check passed, then the scoped worker ended before saying anything: that start fails with one line, the
    next one runs plain (the worker never stays down for the scope)."""
    stand_in.parent.joinpath("systemd-run").write_text(STAND_IN.replace(
        'while [ "$1" != "--" ]', 'case "$*" in *fake_worker.py*) exit 1 ;; esac\nwhile [ "$1" != "--" ]'))
    rec = Recorder()
    sup = Supervisor(spawn(tmp_path), rec)
    with pytest.raises(EngineFailed, match="while starting"):
        await sup.start()
    assert sup.state == "none" and enginescope.available() is False
    await sup.start()
    try:
        assert sup.state == "ready"
        calls = stand_in.read_text().splitlines()
        assert len(calls) == 2 and "fake_worker.py" in calls[1], "the check, the scoped try; the plain start asks none"
    finally:
        await sup.stop()
