"""The join in the worker (`hub/worker/join.py`) against the fake ffmpeg and ffprobe (Stage 11 §5.3, §5.4): progress
and one output, the refusals by their text, a length off by more than a frame per item, a cancel before and during
the run; no list or `.err` file is left behind."""
from __future__ import annotations

import os
import threading
from pathlib import Path

import pytest

from hub.worker import join
from hub.worker.adapters import fork
from tests.engine import fake_ffmpeg
from tests.fakes.mp4 import tiny_mp4

LOADED = "flux2_klein_9b"


@pytest.fixture
def rig(tmp_path, monkeypatch):
    """The fake programs named as `prepare` names them, a state folder and a clips folder."""
    bin_dir = tmp_path / "bin"
    for name, value in fake_ffmpeg.install(bin_dir).items():
        monkeypatch.setenv(name, value)
    (tmp_path / "state" / "outbox").mkdir(parents=True)
    (tmp_path / "clips").mkdir()
    return tmp_path


def clip(rig: Path, name: str, frames: int = 124, **kw) -> dict:
    path = rig / "clips" / name
    path.write_bytes(tiny_mp4(frames=frames, **kw))
    return {"path": str(path), "in": 0, "out": frames, "fps": 24.0, "w": kw.get("w", 960), "h": kw.get("h", 544),
            "frames": frames, "audio": kw.get("audio", False)}


def request(*items: dict) -> dict:
    first = items[0]
    return {"items": list(items), "canvas": {"w": first["w"], "h": first["h"], "fps": first["fps"]}, "audio": [],
            "crf": 18, "preset": "medium"}


def run(rig: Path, req: dict, job: str = "j1") -> tuple[dict, list[dict]]:
    sent: list[dict] = []
    done = join.run(job, 2, req, sent.append, LOADED, str(rig / "state"))
    return done, sent


def left(rig: Path) -> list[str]:
    """What the join left in the state folder (the outbox is the engine's)."""
    return sorted(p.name for p in (rig / "state").iterdir() if p.name != "outbox")


def test_the_refusal_line_is_the_adapters():
    assert join.NO_FFMPEG == fork.NO_FFMPEG == "ffmpeg is not installed on the server"


def test_a_copy_join_reports_progress_and_one_output(rig):
    done, sent = run(rig, request(clip(rig, "a.mp4", audio=True), clip(rig, "it's.mp4", 141, audio=True)))
    assert done["ok"] and done["model"] == LOADED and (done["job"], done["task"]) == ("j1", 2), done
    progress = [m for m in sent if m["ev"] == "progress"]
    assert [(m["step"], m["steps"]) for m in progress] == [(132, 265), (265, 265)], "the N/A line is skipped"
    assert all(m["phase"] == "joining" and m["text"] == "" and m["job"] == "j1" and m["task"] == 2 for m in progress)
    [out] = [m for m in sent if m["ev"] == "output"]
    assert out == {"job": "j1", "task": 2, "ev": "output", "file": str(rig / "state" / "outbox" / "join-j1.mp4")}
    assert join.reader().facts(out["file"])["frames"] == 265
    [ffmpeg] = fake_ffmpeg.calls(rig / "bin", "ffmpeg")
    assert ffmpeg["argv"][ffmpeg["argv"].index("-i") + 1] == str(rig / "state" / "join-j1.txt")
    assert ffmpeg["list"] == f"file '{rig}/clips/a.mp4'\nfile '{rig}/clips/it'\\''s.mp4'\n"
    assert [c["argv"][-1] for c in fake_ffmpeg.calls(rig / "bin", "ffprobe")] == [
        str(rig / "clips" / "a.mp4"), str(rig / "clips" / "it's.mp4")], "each input probed once"
    assert left(rig) == []


def test_a_trim_encodes_and_lands_the_expected_frames(rig):
    a = {**clip(rig, "a.mp4", audio=True), "in": 12, "out": 112}
    done, sent = run(rig, request(a, clip(rig, "b.mp4", 97)))
    assert done["ok"], done
    [ffmpeg] = fake_ffmpeg.calls(rig / "bin", "ffmpeg")
    assert "-filter_complex" in ffmpeg["argv"] and "anullsrc" in ffmpeg["argv"][ffmpeg["argv"].index("-filter_complex")
                                                                                + 1]
    assert [m["steps"] for m in sent if m["ev"] == "progress"] == [197, 197]
    assert join.reader().facts(sent[-1]["file"]) == {"w": 960, "h": 544, "fps": 24.0, "frames": 197,
                                                      "seconds": round(197 / 24, 3), "audio": True}


def test_a_differing_stream_hash_takes_the_encode_path(rig):
    fake_ffmpeg.configure(rig / "bin", hash={"b.mp4": "CRC32:00000000"})
    done, _ = run(rig, request(clip(rig, "a.mp4"), clip(rig, "b.mp4")))
    assert done["ok"] and "-filter_complex" in fake_ffmpeg.calls(rig / "bin", "ffmpeg")[0]["argv"]


def test_no_ffmpeg_is_the_adapters_line(rig, monkeypatch):
    req = request(clip(rig, "a.mp4"), clip(rig, "b.mp4"))
    monkeypatch.setenv("PATH", str(rig / "nowhere"))
    for gone in ("FFMPEG_BINARY", "FFPROBE_BINARY"):
        with monkeypatch.context() as m:
            m.delenv(gone)
            done, sent = run(rig, req)
            assert done["error"] == {"stage": "runtime", "text": fork.NO_FFMPEG} and not done["ok"] and sent == []
    assert fake_ffmpeg.calls(rig / "bin") == []


def test_a_missing_input_is_refused_before_ffmpeg(rig):
    req = request(clip(rig, "a.mp4"), clip(rig, "b.mp4"))
    os.unlink(req["items"][1]["path"])
    done, _ = run(rig, req)
    assert done["error"] == {"stage": "runtime", "text": "A clip of the sequence is gone"}
    assert fake_ffmpeg.calls(rig / "bin") == [] and left(rig) == []


def test_a_failed_ffmpeg_gives_the_last_err_line_cut_to_200(rig):
    fake_ffmpeg.configure(rig / "bin", exit=1, stderr=["first line", "x" * 300, "   "])
    done, sent = run(rig, request(clip(rig, "a.mp4"), clip(rig, "b.mp4")))
    assert done["error"] == {"stage": "runtime", "text": "x" * 200} and not done["ok"]
    assert [m for m in sent if m["ev"] == "output"] == [] and left(rig) == []
    assert not (rig / "state" / "outbox" / "join-j1.mp4").exists()


def test_a_length_off_by_more_than_a_frame_per_item_is_refused_and_the_file_erased(rig):
    req = request(clip(rig, "a.mp4"), clip(rig, "b.mp4"))
    fake_ffmpeg.configure(rig / "bin", off=2)
    done, _ = run(rig, req)
    assert done["ok"], "two frames over two items: within the check"
    fake_ffmpeg.configure(rig / "bin", off=3)
    done, sent = run(rig, req, "j2")
    assert done["error"] == {"stage": "runtime", "text": "The joined clip came out 10.5 s (251 frames) instead of "
                                                         "10.3 s (248 frames)"}
    assert [m for m in sent if m["ev"] == "output"] == [] and left(rig) == []
    assert not (rig / "state" / "outbox" / "join-j2.mp4").exists()


def test_a_cancel_before_the_start_refuses_the_join(rig):
    req = request(clip(rig, "a.mp4"), clip(rig, "b.mp4"))
    join.cancel("j1")
    done, sent = run(rig, req)
    assert done["error"] == {"stage": "cancelled", "text": "Cancelled"} and not done["ok"]
    assert fake_ffmpeg.calls(rig / "bin", "ffmpeg") == [] and left(rig) == [] and sent == []
    join.cancel("another")
    assert run(rig, req, "j3")[0]["ok"], "a cancel for another job does not stop the next join"


@pytest.mark.parametrize("stubborn", [False, True])
def test_a_cancel_during_the_run_stops_ffmpeg(rig, monkeypatch, stubborn):
    monkeypatch.setattr(join, "KILL_AFTER", 0.3)
    fake_ffmpeg.configure(rig / "bin", sleep=60, ignore_term=stubborn)
    req = request(clip(rig, "a.mp4"), clip(rig, "b.mp4"))
    going, result = threading.Event(), {}

    def send(m: dict) -> None:
        if m["ev"] == "progress":
            going.set()

    worker = threading.Thread(target=lambda: result.update(join.run("j1", 1, req, send, None, str(rig / "state"))))
    worker.start()
    assert going.wait(20)
    join.cancel("j1")
    worker.join(20)
    assert not worker.is_alive() and result["error"] == {"stage": "cancelled", "text": "Cancelled"}
    [ffmpeg] = fake_ffmpeg.calls(rig / "bin", "ffmpeg")
    with pytest.raises(ProcessLookupError):
        os.kill(ffmpeg["pid"], 0)
    assert left(rig) == [] and not (rig / "state" / "outbox" / "join-j1.mp4").exists()
