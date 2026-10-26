"""A continue whose source's sound ends too early for the model's sound join keeps fewer source frames.
H3 makes only the last overlap frame's sound again and refuses a source whose sound ends earlier than that frame
less its `audio_overlap_repair_ms` (`models/minimax_h3/pipeline.py:824`, after wgp.py:7922-7923); the facts file
says which models join so (`sound_join`). The frames come from the MP4's boxes, the sound from ffmpeg's decode."""
from __future__ import annotations

import math
import shutil
import subprocess
from pathlib import Path

import pytest

from hub.worker.adapters import soundtail, upstream
from hub.worker.engineapi import ClipRequest, Reference
from tests.fakes.mp4 import tiny_mp4

TASK = {"model_type": "minimax_h3_fl2va", "video_source": "", "keep_frames_video_source": "",
        "sliding_window_overlap": 9}
H3 = {"fps": 24, "sound_join": {"frames": 1, "repair_ms": 25.0}}


def refused(frames: int, sound: float, fps: float = 24, repair_ms: float = 25.0) -> bool:
    """The engine's test for a source of `frames` kept frames: its sound under the overlap is short by the
    shortfall, which joins the repair; more than the one frame H3 makes again is refused."""
    return max(0.0, frames / fps - sound) + repair_ms / 1000 > 1 / fps


def clip(tmp_path: Path, frames: int = 240, audio: bool = True) -> str:
    path = tmp_path / "source.mp4"
    path.write_bytes(tiny_mp4(frames=frames, audio=audio))
    return str(path)


def kept(task: dict, frames: int = 240) -> int:
    return frames + int(task["keep_frames_video_source"] or 0)


def test_only_a_source_the_engine_would_refuse_loses_frames_and_only_the_fewest(tmp_path):
    task = {**TASK, "video_source": clip(tmp_path)}                       # 240 frames at 24 fps: 10 s
    assert soundtail.cover(task, H3, lambda _: 9.95)["keep_frames_video_source"] == "-1"
    for sound in (10.0, 10.2, 9.99, 9.985):                              # short by 0 to 15 ms: taken as it is
        assert soundtail.cover(task, H3, lambda _, s=sound: s) == task, sound
    for i in range(0, 380):                                               # 9.62 s to 10 s, by the millisecond
        sound = 10 - i / 1000
        out = soundtail.cover(task, H3, lambda _, s=sound: s)
        if out is task:
            assert not refused(240, sound) or 240 - math.floor((sound + 1 / 24 - 0.026) * 24) > 9, sound
            continue
        assert not refused(kept(out), sound) and refused(kept(out) + 1, sound - 0.001), sound   # fits; the fewest


def test_a_model_without_a_sound_join_or_a_long_shortfall_is_left_to_the_engine(tmp_path):
    task = {**TASK, "video_source": clip(tmp_path)}
    asked: list[str] = []
    assert soundtail.cover(task, {"fps": 24}, lambda p: asked.append(p) or 9.0) == task and not asked
    assert soundtail.cover(task, H3, lambda _: 9.0) == task, "a second short: more than the overlap"
    assert soundtail.cover(task, H3, lambda _: None) == task
    assert soundtail.cover({**task, "keep_frames_video_source": "100"}, H3, lambda _: 9.95)[
        "keep_frames_video_source"] == "100", "a frame choice already made stands"
    silent = {**TASK, "video_source": clip(tmp_path, audio=False)}
    assert soundtail.cover(silent, H3, lambda p: asked.append(p) or 1.0) == silent and not asked
    torn = tmp_path / "torn.mp4"
    torn.write_bytes(b"not an mp4")
    assert soundtail.cover({**TASK, "video_source": str(torn)}, H3, lambda _: 1.0)["keep_frames_video_source"] == ""
    bare = {k: v for k, v in TASK.items() if k != "video_source"}
    assert soundtail.cover(bare, H3, lambda _: 1.0) == bare
    assert soundtail.cover(task, {"fps": 24, "sound_join": {"frames": 1, "repair_ms": 80}}, lambda _: 9.95) == task, \
        "a repair longer than the frame: no trim makes it fit"


def test_the_drop_counts_frames_at_the_models_rate(tmp_path):
    task = {**TASK, "video_source": clip(tmp_path)}                       # a 24 fps source, a 16 fps model
    out = soundtail.cover(task, {"fps": 16, "sound_join": {"frames": 1, "repair_ms": 25.0}}, lambda _: 9.95)
    assert out["keep_frames_video_source"] == "-1" and not refused(159, 9.95, fps=16)    # 160 frames; 159 fit


def test_the_upstream_line_measures_a_continue_and_says_what_it_dropped(tmp_path, monkeypatch):
    seen: list[str] = []
    monkeypatch.setattr(soundtail, "sound_seconds", lambda p: seen.append(p) or 9.95)
    source = clip(tmp_path)
    entry = {"id": "h3", "kind": "video", "video": {**H3, "overlap": 9, "continues": True, "window_min": 0}}
    request = ClipRequest(model="h3", prompt="on", frames=121, size=(960, 544), steps=4, seed=1,
                          references=[Reference(source, "source")])
    task = upstream.Upstream().task(request, entry)
    assert (task["video_source"], task["keep_frames_video_source"], seen) == (source, "-1", [source])
    assert upstream.Upstream.dropped(task) == 1 and upstream.Upstream.dropped({"keep_frames_video_source": ""}) == 0
    fresh = ClipRequest(model="h3", prompt="on", frames=121, size=(960, 544), steps=4, seed=1, references=[])
    assert "keep_frames_video_source" not in upstream.Upstream().task(fresh, entry) and seen == [source]


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="no ffmpeg here")
def test_ffmpeg_measures_the_sound_as_the_engine_decodes_it(tmp_path, monkeypatch):
    """A real clip: 48 frames at 24 fps, sound for 1.9 s: the engine would refuse it; the frames kept fit."""
    monkeypatch.delenv("FFMPEG_BINARY", raising=False)
    path = tmp_path / "real.mp4"
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=64x64:r=24:d=2",
                    "-f", "lavfi", "-i", "sine=f=440:d=1.9", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-shortest", "-t", "2", str(path)], check=True)
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=s=64x64:r=24:d=2",
                    "-i", str(path), "-map", "0:v", "-map", "1:a", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    "-c:a", "copy", str(tmp_path / "long.mp4")], check=True)
    sound = soundtail.sound_seconds(str(tmp_path / "long.mp4"))
    assert sound is not None and abs(sound - 1.9) < 0.03
    task = soundtail.cover({**TASK, "video_source": str(tmp_path / "long.mp4")}, H3)
    left = kept(task, 48)
    assert left == math.floor((sound + 1 / 24 - 0.026) * 24) and not refused(left, sound) and refused(48, sound)
    assert soundtail.sound_seconds(str(tmp_path / "nothing.mp4")) is None
