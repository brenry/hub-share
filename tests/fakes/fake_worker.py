"""A fake engine worker that speaks `hub/worker/protocol.py` (stdlib only).

Same command line as the real worker: --fd N --parent PID --root R --state S [...] -- MODES
Modes (after `--`): fatal, exit-on-start, crash-on-run, ignore-stop, slow, report-env, video, wav.
It takes requests in the Hub's words (`run {request}`, PROTO 2) and writes a small real PNG into <state>/outbox for
every task (`video`: a small MP4; `wav`: a stray sound file), exits on EOF like the real one.
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import socket
import struct
import sys
import threading
import time
import zlib

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "hub", "worker"))
import protocol  # noqa: E402
from mp4 import tiny_mp4  # noqa: E402  (this script's own folder, tests/fakes)
from wav import tiny_wav  # noqa: E402

CATALOG = {"engine": {"api": "upstream", "version": "fake", "settings_version": 1, "root": "", "loras_root": "",
                      "checkpoints": []},
           "models": [{"id": "fake_model", "name": "Fake Model", "family": "Fake", "status": "available",
                       "defaults": {"num_inference_steps": 2}, "steps": 2, "size": None, "guidance": None,
                       "modes": ["new"], "guidance_key": None, "ref_choices": [""],
                       "block": 16, "lock_steps": False, "loras": False, "lora_dirs": [], "lora_recursive": True}]}


def png(path: str, settings: dict) -> None:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 8, 8, 8, 2, 0, 0, 0))
                + chunk(b"iTXt", b"comment\x00\x00\x00\x00\x00" + json.dumps(settings).encode())
                + chunk(b"IDAT", zlib.compress((b"\x00" + b"\x10" * 24) * 8))
                + chunk(b"IEND", b""))


def main() -> None:
    argv = sys.argv[1:]
    modes = set(argv[argv.index("--") + 1:]) if "--" in argv else set()
    argv = argv[:argv.index("--")] if "--" in argv else argv
    p = argparse.ArgumentParser()
    for name in ("--fd", "--parent"):
        p.add_argument(name, type=int)
    for name in ("--root", "--state"):
        p.add_argument(name)
    p.add_argument("--models", action="append", default=[])
    opts = p.parse_args(argv)
    sock = socket.socket(fileno=opts.fd)
    lock = threading.Lock()

    def send(msg: dict) -> None:
        with lock:
            sock.sendall(protocol.encode(msg))

    if "ignore-stop" in modes:
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
    if "fatal" in modes:
        send({"ev": "fatal", "text": "The engine could not start: no GPU"})
        os._exit(1)
    if "exit-on-start" in modes:
        os._exit(3)
    proto = protocol.PROTO - 1 if "old-proto" in modes else protocol.PROTO        # a worker of an older Hub
    send({"ev": "ready", "pid": os.getpid(), "proto": proto, "engine": {"api": "upstream", "version": "fake"}})
    if "report-env" in modes:
        send({"ev": "env", "env": dict(os.environ)})
    loaded: list[str | None] = [None]
    cancelled: set[str] = set()
    outbox = os.path.join(opts.state, "outbox")
    os.makedirs(outbox, exist_ok=True)

    def run(msg: dict) -> None:
        job, task, settings = msg["job"], msg["task"], msg["request"]
        base = {"job": job, "task": task}
        if "crash-on-run" in modes:
            os._exit(139)
        model = settings.get("model", "fake_model")
        if loaded[0] != model:
            send({"ev": "model", "state": "loading", "model": model, "rss_mb": 100})
            loaded[0] = model
            send({"ev": "model", "state": "loaded", "model": model, "rss_mb": 900})
        steps = int(settings.get("steps") or 2)
        for step in range(1, steps + 1):
            if job in cancelled:
                send({**base, "ev": "task_done", "ok": False, "model": model,
                      "error": {"stage": "cancelled", "text": "Cancelled"}})
                return
            time.sleep(0.3 if "slow" in modes else 0.005)
            send({**base, "ev": "progress", "phase": "inference", "step": step, "steps": steps,
                  "pct": int(step / steps * 100), "text": "Denoising"})
        suffix = ".mp4" if "video" in modes else ".wav" if "wav" in modes else ".png"
        path = os.path.join(outbox, f"{job}_{task}{suffix}")
        if suffix == ".png":
            png(path, {**settings, "type": "WanGP vfake by DeepBeepMeep - Fake Model"})
        else:
            with open(path, "wb") as f:
                f.write(tiny_mp4() if suffix == ".mp4" else tiny_wav(tagged=True))
        send({**base, "ev": "output", "file": path})
        send({**base, "ev": "task_done", "ok": True, "seconds": 0.01, "model": model,
              "peak_vram_mb": 1234, "peak_rss_mb": 900})

    buf = protocol.LineBuffer()
    while True:
        chunk = sock.recv(65536)
        if not chunk:
            os._exit(0)
        for line in buf.feed(chunk):
            msg = protocol.decode(line)
            op = msg.get("op")
            if op == "stop" and "ignore-stop" not in modes:
                os._exit(0)
            elif op == "cancel":
                cancelled.add(msg["job"])
            elif op == "run":
                threading.Thread(target=run, args=(msg,), daemon=True).start()
            elif op == "query":
                send({"ev": "reply", "id": msg["id"], "data": CATALOG})


if __name__ == "__main__":
    main()
