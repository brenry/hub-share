"""The engine worker in a cgroup of its own, so a memory kill takes the engine and never the Hub.

systemd-oomd kills a whole leaf cgroup ("only leaf cgroups … are eligible candidates", systemd-oomd(8)). With the
worker inside hub.service, that cgroup holds the controller too, so an engine load past the memory limit takes the
whole Hub down with it. Started through `systemd-run --user --scope`, the worker is its own leaf: the
command is exec'd in the same process (systemd v257 `src/run/run.c`, `start_transient_scope`: the scope takes
systemd-run's own pid, then `execvpe`), so the pid, the socket handed over and the parent-death signal stay the same.
`env -u` then takes systemd's own variables out again: the worker keeps its clean environment.

Used only when systemd's user manager answers (a trivial scope runs once per controller); otherwise the worker starts
inside hub.service.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Mapping

SYSTEMD_VARS = ("XDG_RUNTIME_DIR", "DBUS_SESSION_BUS_ADDRESS")   # what systemd-run needs to reach systemd --user
ADDED = (*SYSTEMD_VARS, "INVOCATION_ID")                         # what the worker must not inherit from it
_answer: bool | None = None


def available(env: Mapping[str, str] | None = None) -> bool:
    """Whether systemd's user manager starts a scope (asked once; a failure means: start the worker plain)."""
    global _answer
    if _answer is None:
        src = os.environ if env is None else env
        run, plain = shutil.which("systemd-run"), shutil.which("env")
        if not (run and plain and src.get("XDG_RUNTIME_DIR")):
            _answer = False
        else:
            try:                                             # the very wrapper the worker gets, around `true`
                argv, env2 = wrap(["true"], {k: src[k] for k in ("PATH",) if k in src}, "check", src)
                done = subprocess.run(argv, env=env2, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                      stderr=subprocess.DEVNULL, timeout=15)
                _answer = done.returncode == 0
            except (OSError, subprocess.SubprocessError):
                _answer = False
    return _answer


def wrap(argv: list[str], env: Mapping[str, str], gpu: str, source: Mapping[str, str] | None = None
         ) -> tuple[list[str], dict[str, str]]:
    """`argv` and `env` to start the worker in its own scope: systemd-run gets the variables it needs, the worker
    gets `env` exactly."""
    src = os.environ if source is None else source
    run, plain = shutil.which("systemd-run"), shutil.which("env")
    assert run and plain
    unset = [x for name in ADDED if name not in env for x in ("-u", name)]
    outer = {**env, **{k: src[k] for k in SYSTEMD_VARS if k in src}}
    return [run, "--user", "--scope", "--quiet", "--collect", f"--description=Hub engine (GPU {gpu})", "--",
            plain, *unset, *argv], outer


def give_up() -> bool:
    """A scoped start ended before the worker said anything: start plain from now on (True: worth another start)."""
    global _answer
    was, _answer = _answer, False
    return bool(was)


def reset() -> None:
    """Ask systemd's user manager again at the next start (tests)."""
    global _answer
    _answer = None
