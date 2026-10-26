"""What both fakes share: their folder's config, the call record, the Hub's MP4 reader and the writer of
`tests/fakes/mp4.py` (both loaded by path: the fakes run as scripts)."""
from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
FAKES = HERE.parents[1] / "fakes"
CLIP = HERE.parents[2] / "hub" / "core" / "clip.py"


def _load(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def facts(path: str) -> dict[str, Any]:
    return _load("fake_ffmpeg_clip", CLIP).facts(path)


def tiny_mp4(**kw: Any) -> bytes:
    return _load("fake_ffmpeg_mp4", FAKES / "mp4.py").tiny_mp4(**kw)


def tiny_wav(**kw: Any) -> bytes:
    return _load("fake_ffmpeg_wav", FAKES / "wav.py").tiny_wav(**kw)


def start() -> tuple[Path, list[str], dict[str, Any]]:
    """-> the fake's folder, its own arguments and the folder's config; what to record is the caller's."""
    folder, args = Path(sys.argv[1]), sys.argv[2:]
    config_file = folder / "fake.json"
    config = json.loads(config_file.read_text()) if config_file.exists() else {}
    return folder, args, config


def record(folder: Path, prog: str, args: list[str], **extra: Any) -> None:
    with open(folder / "calls.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps({"prog": prog, "argv": args, "pid": os.getpid(), **extra}) + "\n")
