"""Frames of a clip at full size, in the worker (`hub/worker/frames.py`), on a real ffmpeg clip whose
frames are numbered (each frame draws its number in seven black or white stripes, read back from the PNG). Each
output is its frame, at the clip's size, in the request's order; a clip shorter than the last index needs is refused
in one line and nothing is written. Skipped without ffmpeg."""
from __future__ import annotations

import shutil
import subprocess
import threading
import time
from pathlib import Path

import pytest
from PIL import Image

from hub.worker import enginewire, frames, join
from hub.worker.engineapi import REQUESTS, FramesRequest

W, H, BITS = 112, 64, 7                      # seven 16 px stripes: frame numbers 0-127
VIEWS = (2, 21, 42, 63, 84, 113)

FFMPEG, FFPROBE = shutil.which("ffmpeg"), shutil.which("ffprobe")
needs_ffmpeg = pytest.mark.skipif(not (FFMPEG and FFPROBE), reason="no ffmpeg")


@pytest.fixture(autouse=True)
def real_ffmpeg(monkeypatch):
    """The system's ffmpeg, whatever an earlier test left in the environment."""
    for name, found in (("FFMPEG_BINARY", FFMPEG), ("FFPROBE_BINARY", FFPROBE)):
        if found:
            monkeypatch.setenv(name, found)
        else:
            monkeypatch.delenv(name, raising=False)


def numbered(path: Path, count: int) -> Path:
    """An MP4 of `count` frames, frame n drawing n in binary as white stripes."""
    raw = bytearray()
    for n in range(count):
        row = bytes(255 if n >> (BITS - 1 - x // 16) & 1 else 0 for x in range(W))
        raw += row * H
    subprocess.run([str(FFMPEG), "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "gray", "-s", f"{W}x{H}",
                    "-r", "24", "-i", "-", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-qp", "0", str(path)],
                   input=bytes(raw), check=True, capture_output=True, timeout=120)
    return path


def number(png: str) -> int:
    with Image.open(png) as im:
        gray = im.convert("L")
        return sum(1 << (BITS - 1 - i) for i in range(BITS) if gray.getpixel((i * 16 + 8, H // 2)) > 128)


def run(tmp_path: Path, clip: Path, indices: tuple[int, ...]) -> tuple[dict, list[dict]]:
    sent: list[dict] = []
    request = enginewire.request_parse(enginewire.request_wire(FramesRequest(str(clip), indices)))
    done = frames.run("j1", 2, enginewire.wire(request), sent.append, "h3", str(tmp_path / "state"))
    return done, sent


def test_the_request_crosses_the_wire():
    request = FramesRequest("/x/orbit.mp4", VIEWS)
    wired = enginewire.request_wire(request)
    assert wired == {"kind": "frames", "clip": "/x/orbit.mp4", "frames": list(VIEWS)}
    assert REQUESTS["frames"] is FramesRequest and enginewire.request_parse(wired) == request
    with pytest.raises(ValueError):
        enginewire.request_parse({**wired, "frames": [2, "x"]})


@needs_ffmpeg
def test_each_output_is_its_frame_at_full_size(tmp_path):
    clip = numbered(tmp_path / "orbit.mp4", 124)
    done, sent = run(tmp_path, clip, VIEWS)
    assert done["ok"] and done["ev"] == "task_done" and done["model"] == "h3"
    assert (done["job"], done["task"]) == ("j1", 2)
    assert [s["ev"] for s in sent] == ["output"] * len(VIEWS)
    for s, n in zip(sent, VIEWS, strict=True):
        assert Path(s["file"]).parent == tmp_path / "state" / "outbox" and s["file"].endswith(".png")
        with Image.open(s["file"]) as im:
            assert im.size == (W, H), "full size: never scaled"
        assert number(s["file"]) == n


@needs_ffmpeg
def test_the_outputs_follow_the_requests_order(tmp_path):
    clip = numbered(tmp_path / "orbit.mp4", 124)
    _, sent = run(tmp_path, clip, (113, 2, 63))
    assert [number(s["file"]) for s in sent] == [113, 2, 63]


@needs_ffmpeg
def test_a_clip_too_short_for_the_views_is_refused_in_one_line(tmp_path):
    clip = numbered(tmp_path / "short.mp4", 113)
    done, sent = run(tmp_path, clip, VIEWS)
    assert not done["ok"] and sent == []
    assert done["error"] == {"stage": "runtime", "text": "The orbit has 113 frames; the views need 114"}
    assert not list((tmp_path / "state").glob("outbox/*")), "nothing written"


def test_a_clip_that_is_gone_and_a_frame_asked_twice_are_refused(tmp_path):
    done, _ = run(tmp_path, tmp_path / "gone.mp4", VIEWS)
    assert done["error"]["text"] == frames.GONE
    done, _ = run(tmp_path, tmp_path / "gone.mp4", (2, 2))
    assert done["error"]["text"] == frames.TWICE


def test_the_filter_keeps_exactly_the_frames():
    assert frames.select([21, 2]) == "select='eq(n,2)+eq(n,21)'"
    argv = frames.argv("ffmpeg", "/c.mp4", [2, 21], "/o/f-%d.png")
    assert argv[argv.index("-fps_mode") + 1] == "passthrough" and argv[argv.index("-frames:v") + 1] == "2"
    assert "-vsync" not in argv


@needs_ffmpeg
def test_a_cancel_before_ffmpeg_starts_keeps_it_from_starting(tmp_path):
    clip = numbered(tmp_path / "orbit.mp4", 124)
    join.cancel("j1")                                    # the worker's cancel, before the task's ffmpeg is there
    done, sent = run(tmp_path, clip, VIEWS)
    assert done["error"] == {"stage": "cancelled", "text": "Cancelled"} and sent == []
    assert not list((tmp_path / "state").glob("outbox/*"))


@needs_ffmpeg
def test_a_cancel_stops_a_running_ffmpeg(tmp_path, monkeypatch):
    clip = numbered(tmp_path / "orbit.mp4", 124)
    slow = tmp_path / "ffmpeg"
    slow.write_text("#!/bin/sh\nexec sleep 30\n")
    slow.chmod(0o755)
    monkeypatch.setenv("FFMPEG_BINARY", str(slow))
    out: list = []
    worker = threading.Thread(target=lambda: out.append(run(tmp_path, clip, VIEWS)))
    worker.start()
    deadline = time.monotonic() + 20
    while "j1" not in join._running and time.monotonic() < deadline:
        time.sleep(0.05)
    assert "j1" in join._running, "ffmpeg runs in the join's registry"
    join.cancel("j1")
    worker.join(20)
    assert not worker.is_alive() and out[0][0]["error"] == {"stage": "cancelled", "text": "Cancelled"}
    assert "j1" not in join._running and out[0][1] == []
