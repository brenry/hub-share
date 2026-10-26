"""A fake ffmpeg and ffprobe for the join (stdlib scripts, run by the test's own Python).

`install(folder, **config)` writes the programs `ffmpeg` and `ffprobe` into `folder` (each a shell line that execs
`ffmpeg.py`/`ffprobe.py` here, so its pid is the program's) and returns the environment naming them, as the
adapter's `prepare` would. Each call appends `{"prog", "argv", "pid", "list"?}` to `<folder>/calls.jsonl` (`calls`).
The config (`<folder>/fake.json`, `configure`) steers them:

- ffprobe: `no_hash` (base names whose video has no `extradata_hash`, or true for all), `hash` ({base name: value}).
- ffmpeg: `off` (frames added to what it should make), `exit` (its code, after `stderr` lines), `sleep` (seconds
  between the first progress and the rest), `ignore_term` (SIGTERM ignored).
"""
from __future__ import annotations

import json
import shlex
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent


def configure(folder: Path, **config: Any) -> None:
    (folder / "fake.json").write_text(json.dumps(config))


def install(folder: Path, **config: Any) -> dict[str, str]:
    folder.mkdir(parents=True, exist_ok=True)
    env = {}
    for name, var in (("ffmpeg", "FFMPEG_BINARY"), ("ffprobe", "FFPROBE_BINARY")):
        program = folder / name
        program.write_text(f"#!/bin/sh\nexec {shlex.quote(sys.executable)} -B "
                           f"{shlex.quote(str(HERE / f'{name}.py'))} {shlex.quote(str(folder))} \"$@\"\n")
        program.chmod(0o755)
        env[var] = str(program)
    configure(folder, **config)
    return env


def calls(folder: Path, prog: str | None = None) -> list[dict[str, Any]]:
    path = folder / "calls.jsonl"
    seen = [json.loads(x) for x in path.read_text().splitlines()] if path.exists() else []
    return [c for c in seen if prog is None or c["prog"] == prog]
