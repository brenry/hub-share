"""Save in the worker (`hub/worker/join.py`) against the fake ffmpeg: a WAV of track 1's sounds lands with
its length checked by the Hub's own sound reader; a WAV of track 2 alone; a length off by more than its slack is
refused and the file erased; an MP4 with a sound on track 2 asks ffmpeg once whether `amix` has `normalize` and
writes the mix it gets; a gone track-2 input is refused before ffmpeg."""
from __future__ import annotations

import pytest

from hub.worker import join
from tests.engine import fake_ffmpeg
from tests.engine.test_join import LOADED, clip, request, rig  # noqa: F401  (`rig` is a fixture)
from tests.fakes.wav import tiny_wav


@pytest.fixture(autouse=True)
def fresh(monkeypatch):
    monkeypatch.setattr(join, "_normalize", None)
    monkeypatch.setattr(join, "_duck", None)


def sound(rig, name: str, seconds: float, lo: int = 0, hi: int | None = None) -> dict:  # noqa: F811
    path = rig / "clips" / name
    path.write_bytes(tiny_wav(seconds=seconds))
    ms = round(seconds * 1000)
    return {"path": str(path), "in": lo, "out": ms if hi is None else hi, "fps": 1000.0, "w": 0, "h": 0,
            "frames": ms, "audio": True, "sound": True}


def placed(item: dict, at_ms: int) -> dict:
    return {"path": item["path"], "at_ms": at_ms, "in": item["in"], "out": item["out"], "fps": item["fps"]}


def wav(*items: dict, audio: list | None = None) -> dict:
    return {"items": list(items), "canvas": {"w": 0, "h": 0, "fps": 1000.0}, "audio": audio or [], "crf": 18,
            "preset": "medium", "out_kind": "wav"}


def go(rig, req: dict) -> tuple[dict, list[dict]]:  # noqa: F811
    sent: list[dict] = []
    return join.run("j1", 1, req, sent.append, LOADED, str(rig / "state")), sent


def test_a_wav_of_a_sound_trimmed_to_15_seconds_lands_checked(rig):  # noqa: F811
    done, sent = go(rig, wav(sound(rig, "long.wav", 40.0, 4000, 19000)))
    assert done["ok"], done
    [out] = [m for m in sent if m["ev"] == "output"]
    assert out["file"] == str(rig / "state" / "outbox" / "join-j1.wav")
    assert join.sound_reader().facts(join.Path(out["file"]))["seconds"] == 15.0
    assert [(m["step"], m["steps"]) for m in sent if m["ev"] == "progress"] == [(1500, 1500)]
    assert [c["argv"][:3] for c in fake_ffmpeg.calls(rig / "bin", "ffmpeg")] == [["-hide_banner", "-nostdin",
                                                                                 "-loglevel"]], "nothing to mix"
    assert fake_ffmpeg.calls(rig / "bin", "ffprobe") == [], "a WAV probes no clip"


def test_a_wav_of_track_2_alone(rig):  # noqa: F811
    fx = sound(rig, "fx.wav", 2.0, 0, 1500)
    done, sent = go(rig, wav(audio=[placed(fx, 3000)]))
    assert done["ok"], done
    [out] = [m for m in sent if m["ev"] == "output"]
    assert join.sound_reader().facts(join.Path(out["file"]))["seconds"] == 4.5


def test_a_wav_off_its_length_is_refused_and_erased(rig):  # noqa: F811
    fake_ffmpeg.configure(rig / "bin", off_seconds=0.5)
    done, sent = go(rig, wav(sound(rig, "a.wav", 3.0)))
    assert not done["ok"] and done["error"] == {"stage": "runtime",
                                                "text": "The saved sound came out 3.5 s instead of 3.0 s"}
    assert not (rig / "state" / "outbox" / "join-j1.wav").exists() and not any(m["ev"] == "output" for m in sent)


@pytest.mark.parametrize(("config", "tail"), [
    ({}, "amix=inputs=2:duration=first:dropout_transition=0:normalize=0[a]"),
    ({"no_normalize": True}, "amix=inputs=2:duration=first:dropout_transition=0,volume=2[a]"),
])
def test_an_mp4_with_a_sound_on_track_2_asks_amix_once(rig, config, tail):  # noqa: F811
    fake_ffmpeg.configure(rig / "bin", **config)
    fx = sound(rig, "fx.wav", 1.0)
    req = {**request(clip(rig, "a.mp4", audio=True)), "audio": [placed(fx, 1000)], "out_kind": "mp4"}
    for job in ("j1", "j2"):
        done = join.run(job, 1, req, lambda m: None, LOADED, str(rig / "state"))
        assert done["ok"], done
    calls = fake_ffmpeg.calls(rig / "bin", "ffmpeg")
    assert [c["argv"] for c in calls if "-h" in c["argv"]] == [["-hide_banner", "-h", "filter=amix"]], "asked once"
    joins = [c["argv"] for c in calls if "-filter_complex" in c["argv"]]
    assert len(joins) == 2 and all(a[a.index("-filter_complex") + 1].endswith(tail) for a in joins)


@pytest.mark.parametrize("config", [{}, {"no_duck": True}])
def test_a_ducked_bed_asks_for_the_compressor_once_and_is_refused_without_it(rig, config):  # noqa: F811
    """`-h filter=sidechaincompress` once per worker; with it, the ducked mix; without, one line."""
    fake_ffmpeg.configure(rig / "bin", **config)
    fx = sound(rig, "fx.wav", 1.0)
    req = {**request(clip(rig, "a.mp4", audio=True)), "audio": [{**placed(fx, 1000), "duck": True}], "out_kind": "mp4"}
    results = [join.run(job, 1, req, lambda m: None, LOADED, str(rig / "state")) for job in ("j1", "j2")]
    calls = fake_ffmpeg.calls(rig / "bin", "ffmpeg")
    asked = [c["argv"] for c in calls if c["argv"][:2] == ["-hide_banner", "-h"]]
    if config:
        assert all(not d["ok"] and d["error"]["text"] == join.NO_DUCK for d in results), results
        assert asked == [["-hide_banner", "-h", "filter=amix"], ["-hide_banner", "-h", "filter=sidechaincompress"]]
        assert not any("-filter_complex" in c["argv"] for c in calls), "refused before ffmpeg ran"
        return
    assert all(d["ok"] for d in results), results
    assert asked.count(["-hide_banner", "-h", "filter=sidechaincompress"]) == 1, "asked once"
    joins = [c["argv"] for c in calls if "-filter_complex" in c["argv"]]
    assert len(joins) == 2 and all("[s0][sc0]sidechaincompress=" in a[a.index("-filter_complex") + 1] for a in joins)


def test_a_gone_track_2_input_is_refused_before_ffmpeg(rig):  # noqa: F811
    req = {**request(clip(rig, "a.mp4")), "audio": [{"path": str(rig / "clips" / "none.wav"), "at_ms": 0, "in": 0,
                                                       "out": 5, "fps": 1000.0}]}
    done, _ = go(rig, req)
    assert done["error"] == {"stage": "runtime", "text": "A clip of the sequence is gone"}
    assert fake_ffmpeg.calls(rig / "bin", "ffmpeg") == []
