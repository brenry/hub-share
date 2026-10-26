"""Engine worker entry point, run by the engine's own Python (stdlib + engine only).

Serve the controller:   python -B main.py --fd N --parent PID --root ROOT --state DIR [--models DIR]... [--profile N]
                        -- ENGINE ARGS
Dump the catalog:       python -B main.py --root ROOT --dump-catalog OUT.json [--state DIR] -- ENGINE ARGS
Dump the engine:        python -B main.py --root ROOT --dump-engine OUT.json -- ENGINE ARGS   (`enginedump`)
Measure a continue:     python -B main.py --root ROOT --state DIR --probe-continue CLIP [--chain K] [--model ID]
                        [--frames N] -- ENGINE ARGS   (`probe.py`: one JSON line per step on stdout)
Measure a join:         python -B main.py --root ROOT --state DIR --probe-join CLIP CLIP [CLIP]... [--trim]
                        -- ENGINE ARGS   (`probejoin.py`: one JSON line on stdout)
Check the weights:      python -B main.py --root ROOT --check-weights [--models DIR]... [--model ID] -- ENGINE ARGS
                        (one line per file the engine would fetch, on a state folder of its own: reads only)

The controller's end of the socket closing means the controller is gone: exit at once.
"""
from __future__ import annotations

import argparse
import ctypes
import json
import os
import shutil
import signal
import socket
import sys
import tempfile
import threading
from typing import Any

try:
    from . import enginedump, enginewire, faults, frames, join, netguard, probe, probejoin, protocol, wan2gp
    from .adapters import voiceconvert
except ImportError:  # run as a script by the engine's Python
    import enginedump
    import enginewire
    import faults
    import frames
    import join
    import netguard
    import probe
    import probejoin
    import protocol
    import wan2gp
    from adapters import voiceconvert


def one_line(exc: BaseException) -> str:
    if isinstance(exc, SystemExit):
        return "The engine stopped while starting (check its Python packages)"
    if isinstance(exc, (enginedump.Leak, faults.Unready)):
        return str(exc)
    text = (str(exc).strip().splitlines() or [type(exc).__name__])[0][:200]
    return f"The engine could not start: {text}"


class Link:
    """The socket to the controller. Any send failure means the controller is gone."""

    def __init__(self, sock: socket.socket) -> None:
        self.sock = sock
        self._lock = threading.Lock()

    def send(self, message: dict[str, Any]) -> None:
        try:
            data = protocol.encode(message)
            with self._lock:
                self.sock.sendall(data)
        except (OSError, protocol.ProtocolError):
            os._exit(0)


def die_with_parent(parent: int) -> None:
    try:
        ctypes.CDLL(None, use_errno=True).prctl(1, signal.SIGKILL)  # PR_SET_PDEATHSIG
    except (OSError, AttributeError):
        pass
    if os.getppid() != parent:
        os._exit(0)


def serve(link: Link, engine: wan2gp.Engine) -> None:
    busy = threading.Event()
    buf = protocol.LineBuffer()
    while True:
        try:
            chunk = link.sock.recv(65536)
            lines = buf.feed(chunk) if chunk else None
        except (OSError, protocol.ProtocolError):
            lines = None
        if lines is None:
            os._exit(0)
        for line in lines:
            try:
                msg = protocol.decode(line)
            except protocol.ProtocolError:
                os._exit(2)
            op = msg.get("op")
            if op == "stop":
                os._exit(0)
            if op == "cancel":
                join.cancel(str(msg.get("job")))
                engine.cancel(str(msg.get("job")))
            elif op == "run" and busy.is_set():
                link.send({"ev": "task_done", "job": msg.get("job"), "task": msg.get("task"), "ok": False,
                           "error": {"stage": "runtime", "text": "The engine is busy"}})
            elif op == "run":
                busy.set()
                threading.Thread(target=run, args=(link, engine, msg, busy), daemon=True).start()
            elif op == "query":
                threading.Thread(target=answer, args=(link, engine, msg), daemon=True).start()


def run(link: Link, engine: wan2gp.Engine, msg: dict[str, Any], busy: threading.Event) -> None:
    job, task = str(msg.get("job")), int(msg.get("task") or 1)
    try:
        request = enginewire.request_parse(msg.get("request"))
        if request.kind == "join":                        # a join (`join.py`): ffmpeg, no model loaded or freed
            done = join.run(job, task, enginewire.wire(request), link.send, engine.loaded(), engine.state)
        elif request.kind == "frames":                    # frames of a clip at full size: ffmpeg, no model
            done = frames.run(job, task, enginewire.wire(request), link.send, engine.loaded(), engine.state)
        elif request.kind == "voice":                     # a clip's voice made the speaker's: no model
            done = voiceconvert.run(engine, job, task, request, link.send)
        else:
            done = engine.run(job, task, request, link.send)
    except BaseException as exc:  # the engine may call exit(); the controller must still hear back
        done = {"ev": "task_done", "job": job, "task": task, "ok": False,
                "error": {"stage": "runtime", "text": (str(exc).splitlines() or ["failed"])[0][:200]}}
    busy.clear()
    link.send(done)


def answer(link: Link, engine: wan2gp.Engine, msg: dict[str, Any]) -> None:
    try:
        what = msg.get("what")
        if what not in ("catalog", "files", "plan", "voice"):
            raise ValueError(f"unknown query {what!r}")
        if what == "plan":                                # the engine's plan of a request, no GPU work
            data = engine.plan(enginewire.request_parse(msg.get("request")))
        elif what == "voice":                             # SeedVC on, and what it lacks
            data = voiceconvert.state(engine.w, engine.root)
        else:
            data = engine.catalog() if what == "catalog" else {"models": engine.model_files(msg.get("models") or [])}
        link.send({"ev": "reply", "id": msg.get("id"), "data": data})
    except BaseException as exc:
        link.send({"ev": "reply", "id": msg.get("id"), "error": (str(exc).splitlines() or ["failed"])[0][:200]})


def parse(argv: list[str]) -> tuple[argparse.Namespace, list[str]]:
    engine_args: list[str] = []
    if "--" in argv:
        cut = argv.index("--")
        argv, engine_args = argv[:cut], argv[cut + 1:]
    p = argparse.ArgumentParser(prog="worker")
    p.add_argument("--root", required=True)
    p.add_argument("--state")
    p.add_argument("--fd", type=int)
    p.add_argument("--parent", type=int)
    p.add_argument("--models", action="append", default=[])
    p.add_argument("--profile", type=float)
    p.add_argument("--dump-catalog", dest="dump")
    p.add_argument("--dump-engine", dest="dump_engine")
    p.add_argument("--probe-continue", dest="probe")
    p.add_argument("--chain", type=int, default=2)
    p.add_argument("--model")
    p.add_argument("--frames", type=int)
    p.add_argument("--probe-join", dest="join", nargs="+")
    p.add_argument("--trim", action="store_true")
    p.add_argument("--check-weights", dest="check", action="store_true")
    opts = p.parse_args(argv)
    if opts.check and (opts.state is not None or opts.dump or opts.dump_engine or opts.probe or opts.join):
        p.error("--check-weights reads alone, on a state folder of its own: no --state, dump or probe")
    if opts.dump_engine is not None and (opts.models or opts.profile is not None or opts.dump is not None):
        p.error("--dump-engine reads the engine alone: no --models, --profile or --dump-catalog")
    if opts.probe is not None and (opts.state is None or opts.chain < 1):
        p.error("--probe-continue needs --state (its outputs stay there) and a --chain of 1 or more")
    if opts.join is not None and (opts.state is None or len(opts.join) < 2):
        p.error("--probe-join needs --state (its outputs stay there) and two clips or more")
    serving = (opts.dump is None and opts.dump_engine is None and opts.probe is None and opts.join is None
               and not opts.check)
    if serving and (opts.fd is None or opts.parent is None or opts.state is None):
        p.error("--fd, --parent and --state are needed unless --dump-catalog, --dump-engine, --probe-continue, "
                "--probe-join or --check-weights is given")
    return opts, engine_args


def dump(opts: argparse.Namespace, engine_args: list[str]) -> int:
    state = opts.state or tempfile.mkdtemp(prefix="hub-catalog-")
    try:
        engine = wan2gp.Engine(opts.root, state, engine_args, opts.models, opts.profile)
        engine.open()
        data = json.dumps(engine.catalog(), indent=1, ensure_ascii=False)
        out = os.path.abspath(opts.dump)
        with open(out + ".tmp", "w", encoding="utf-8") as f:
            f.write(data)
        os.replace(out + ".tmp", out)
    except BaseException as exc:
        print(one_line(exc), file=sys.stderr)
        return 1
    finally:
        if opts.state is None:
            shutil.rmtree(state, ignore_errors=True)
    return 0


def dump_engine(opts: argparse.Namespace, engine_args: list[str]) -> int:
    """The engine's facts (`enginedump`), opened on an empty state folder of the worker's, never the model folders."""
    out = os.path.abspath(opts.dump_engine)
    state = opts.state or tempfile.mkdtemp(prefix="hub-engine-")
    try:
        engine = wan2gp.Engine(opts.root, state, engine_args, [])
        engine.open()
        enginedump.write(engine, out, state)
    except BaseException as exc:
        print(one_line(exc), file=sys.stderr)
        return 1
    finally:
        if opts.state is None:
            shutil.rmtree(state, ignore_errors=True)
    return 0


def check_weights(opts: argparse.Namespace, engine_args: list[str]) -> int:
    """One line per file the engine would fetch (`Engine.missing_weights`): the files a model folder lacks."""
    state = tempfile.mkdtemp(prefix="hub-weights-")
    try:
        engine = wan2gp.Engine(opts.root, state, engine_args, opts.models, opts.profile)
        engine.open()
        sys.stdout.write("".join(f"{line}\n" for line in engine.missing_weights(opts.model)))
    except BaseException as exc:
        print(one_line(exc), file=sys.stderr)
        return 1
    finally:
        shutil.rmtree(state, ignore_errors=True)
    return 0


def main(argv: list[str]) -> int:
    opts, engine_args = parse(argv)
    os.environ.update(protocol.OFFLINE_ENV)
    sys.dont_write_bytecode = True
    netguard.install()
    if opts.dump_engine is not None:
        return dump_engine(opts, engine_args)
    if opts.dump is not None:
        return dump(opts, engine_args)
    if opts.check:
        return check_weights(opts, engine_args)
    if opts.probe is not None or opts.join is not None:
        try:
            return (probe.run if opts.probe is not None else probejoin.run)(opts, engine_args)
        except BaseException as exc:
            print(one_line(exc).replace("could not start", "probe stopped"), file=sys.stderr)
            return 1
    die_with_parent(opts.parent)
    os.set_inheritable(opts.fd, False)
    link = Link(socket.socket(fileno=opts.fd))
    engine = wan2gp.Engine(opts.root, opts.state, engine_args, opts.models, opts.profile)
    try:
        info = engine.open()
    except BaseException as exc:
        link.send({"ev": "fatal", "text": one_line(exc)})
        os._exit(1)
    link.send({"ev": "ready", "pid": os.getpid(), "proto": protocol.PROTO, "engine": info})
    serve(link, engine)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
