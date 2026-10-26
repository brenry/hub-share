"""The face judge. `series` from a similarity per frame (held, fading, absent); `score` against faked
ffmpeg, numpy, onnxruntime and insightface (the files named by the facts); missing files → why; `finish` on a clip
request with identities returns `{"face": …}`; a continue judges its new frames alone."""
from __future__ import annotations

import os
import stat
import sys
import types
from pathlib import Path

from hub.worker.adapters import faces, joins, upstream
from hub.worker.engineapi import ClipRequest, Reference

FACTS = upstream.facts_file()["faces"]


def test_series_held_fading_and_absent():
    held = faces.series([0.6, 0.62, 0.58, 0.61, 0.6, 0.63], 2, 0.3)
    assert held["min"] == 0.58 and held["lost_at"] is None and held["present"] == 1.0
    assert abs(held["drift"] - ((0.6 + 0.63) / 2 - (0.6 + 0.62) / 2)) < 1e-6
    fading = faces.series([0.6, 0.62, 0.5, 0.35, 0.2, 0.15, 0.1, 0.12], 2, 0.3)
    assert fading["lost_at"] == 2.0 and fading["drift"] < 0 and fading["first"] == 0.61
    gap = faces.series([0.6, None, None, 0.59], 2, 0.3)
    assert gap["present"] == 0.5 and gap["lost_at"] == 0.5, "no face for a full second counts as lost"
    assert (gap["first"], gap["last"], gap["min"]) == (0.3, 0.295, 0.59), "absent counts 0 at the ends, not in min"
    gone = faces.series([0.99, 0.99, 0.99, 0.99, None, None, None, None], 2, 0.3, offset=10.0)
    assert (gone["first"], gone["last"], gone["lost_at"], gone["present"]) == (0.99, 0.0, 12.0, 0.5)
    absent = faces.series([None, None], 2, 0.3, offset=3.5)
    assert (absent["present"], absent["min"], absent["lost_at"]) == (0.0, 0.0, 3.5), "never there: lost from the start"
    assert faces.series([], 2, 0.3)["min"] is None
    one = faces.series([0.45], 2, 0.3)
    assert one["median"] == 0.45 and one["first"] == one["last"] == 0.45


class Vec(list):
    """The little of a numpy vector the judge uses (the Hub's own Python has no numpy; the engine's does)."""
    def __truediv__(self, k): return Vec(v / k for v in self)


def fake_numpy():
    np = types.SimpleNamespace(uint8="u8", float32="f32")
    np.frombuffer = lambda raw, dtype=None: types.SimpleNamespace(reshape=lambda *s: raw)
    np.asarray = lambda e, dtype=None: Vec(float(v) for v in e)
    np.stack = lambda vs: [Vec(v) for v in vs]
    np.mean = lambda vs, axis=0: Vec(sum(v[i] for v in vs) / len(vs) for i in range(len(vs[0])))
    np.linalg = types.SimpleNamespace(norm=lambda v: sum(x * x for x in v) ** 0.5)
    np.dot = lambda a, b: sum(x * y for x, y in zip(a, b, strict=True))
    return np


def fake_libs(monkeypatch, embeddings_by_frame):
    """numpy, insightface and onnxruntime faked (the Hub's own Python has none of them; the engine's has all)."""
    monkeypatch.setattr(faces, "_apps", {})                   # the worker keeps one app per device; a test starts bare
    np = fake_numpy()
    monkeypatch.setitem(sys.modules, "numpy", np)
    calls = {"frames": 0, "providers": None}

    class Face:
        """An embedding, or {"e", "box", "open"}: the box in a 640-wide frame, the mouth's opening over the eyes'
        distance (60 px between the two eye keypoints: a 0.2 opening is 12 px between landmarks 53 and 62)."""
        def __init__(self, e):
            spec = e if isinstance(e, dict) else {"e": e}
            self.normed_embedding = np.asarray(spec["e"])
            self.bbox = list(spec.get("box") or [100.0, 100.0, 200.0, 200.0])
            self.kps = [[120.0, 130.0], [180.0, 130.0], [150.0, 150.0], [130.0, 180.0], [170.0, 180.0]]
            self.landmark_2d_106 = [[150.0, 150.0]] * 106
            self.landmark_2d_106[faces.mouth.UPPER] = [150.0, 170.0]
            self.landmark_2d_106[faces.mouth.LOWER] = [150.0, 170.0 + 60.0 * float(spec.get("open") or 0.0)]

    class App:
        def prepare(self, ctx_id, det_size): calls["ctx"] = ctx_id
        def get(self, frame):
            i = calls["frames"]
            calls["frames"] += 1
            return [Face(e) for e in embeddings_by_frame[min(i, len(embeddings_by_frame) - 1)]]

    class Model:
        def __init__(self, task): self.taskname = task

    def get_model(path, providers=None):
        calls["providers"] = providers
        name = os.path.basename(path)
        return Model({"det_10g.onnx": "detection", "w600k_r50.onnx": "recognition"}.get(name, "landmark_2d_106"))
    zoo = types.SimpleNamespace(model_zoo=types.SimpleNamespace(get_model=get_model))
    app_mod = types.SimpleNamespace(FaceAnalysis=App)
    ort = types.SimpleNamespace(get_available_providers=lambda: ["CUDAExecutionProvider", "CPUExecutionProvider"],
                                set_default_logger_severity=lambda level: calls.__setitem__("quiet", level))
    aligned = types.SimpleNamespace(estimate_norm="insightface's own")
    monkeypatch.setitem(sys.modules, "insightface.utils.face_align", aligned)
    monkeypatch.setitem(sys.modules, FACTS["align"]["module"],
                        types.SimpleNamespace(**{FACTS["align"]["function"]: "the refiner's"}))
    calls["aligned"] = aligned
    monkeypatch.setitem(sys.modules, "insightface.model_zoo", zoo)
    monkeypatch.setitem(sys.modules, "insightface.app", app_mod)
    monkeypatch.setitem(sys.modules, "onnxruntime", ort)
    return calls


def fake_ffmpeg(tmp_path: Path, monkeypatch, height: int = 360, frames: int = 6):
    """An ffmpeg that writes raw BGR frames WIDTH wide: one for a picture (no fps), `frames` for a clip."""
    script = tmp_path / "ffmpeg"
    script.write_text(f"""#!/usr/bin/env python3
import sys
args = sys.argv
with open({str(tmp_path / "ffmpeg.log")!r}, "a") as log:
    log.write(" ".join(args[1:]) + "\\n")
n = {frames} if any('fps=' in a for a in args) else 1
if '-ss' in args and n > 1:
    fps = int(next(a for a in args if a.startswith('fps=')).split(',')[0][4:])
    n = max(0, n - round(float(args[args.index('-ss') + 1]) * fps))
if '-frames:v' in args:
    n = 1
sys.stdout.buffer.write(bytes({faces.WIDTH * height * 3}) * n)
""")
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("FFMPEG_BINARY", str(script))


def fake_reader(monkeypatch, seconds: float, fps: float = 24.0):
    """The Hub's MP4 reader as `faces._start` asks it: the clip's length and rate."""
    from hub.worker.adapters import soundtail
    monkeypatch.setattr(soundtail, "reader", lambda: types.SimpleNamespace(
        facts=lambda path: {"seconds": seconds, "fps": fps, "frames": round(seconds * fps)}))


def fake_locator(tmp_path: Path, monkeypatch, present=True):
    """The engine's locator: the path of a file in the model folders, None for one that is not
    (`error_if_none=False`)."""
    folder = tmp_path / FACTS["folder"]
    folder.mkdir(exist_ok=True)
    if present:
        for name in FACTS["files"]:
            (folder / name).write_bytes(b"onnx")

    def locate_file(name, error_if_none=True, **k):
        if (tmp_path / name).is_file():
            return str(tmp_path / name)
        if error_if_none:
            raise Exception(f"Unable to locate file '{name}', tried [...]")   # noqa: TRY002  (the engine's own)
        return None
    monkeypatch.setitem(sys.modules, faces.LOCATOR, types.SimpleNamespace(locate_file=locate_file))


def test_score_against_the_boxes_pictures_held_face_and_cpu_by_default(monkeypatch, tmp_path: Path):
    fake_ffmpeg(tmp_path, monkeypatch, frames=6)
    fake_locator(tmp_path, monkeypatch)
    ref = [1.0, 0.0, 0.0]
    frames = [[ref], [[0.9, 0.1, 0.0]], [[0.8, 0.2, 0.0], [0.0, 1.0, 0.0]], [ref], [ref], [ref], [ref]]
    calls = fake_libs(monkeypatch, frames)
    out = faces.score(str(tmp_path / "c.mp4"), {"Character 7": [str(tmp_path / "j.png")]}, FACTS, "cpu", 0.3)
    character_7 = out["face"]["Character 7"]
    assert calls["providers"] == ["CPUExecutionProvider"] and calls["ctx"] == -1
    assert calls["quiet"] == 3 and calls["aligned"].estimate_norm == "the refiner's", "as the refiner sets them"
    assert character_7["present"] == 1.0 and character_7["lost_at"] is None and character_7["min"] > 0.7
    assert calls["frames"] == 7, "the picture, then six frames of the clip at 2 a second"
    frame = out["frame"]["Character 7"]
    assert frame["size"] == round(100 / 360, 3) and frame["x_first"] == round(150 / 640, 3), "the box's share"
    assert out["mouth"] is None and out["mouth_why"] == faces.mouth.NO_SPEECH, "no inspection here: no speech"
    opened = calls["providers"]
    calls["providers"] = None
    faces.score(str(tmp_path / "c.mp4"), {"Character 7": [str(tmp_path / "j.png")]}, FACTS, "cpu", 0.3)
    assert calls["providers"] is None and opened and set(faces._apps) == {"cpu"}, "the second clip reuses the app"


def test_a_continue_judges_its_new_frames_and_a_lost_face_is_named(monkeypatch, tmp_path: Path):
    """A 4 s clip continued by 48 frames at 24 fps: the judge reads from 2.0 s (the Hub's reader gives the length),
    four frames at 2 a second, and names the second of the clip the face was lost at."""
    fake_ffmpeg(tmp_path, monkeypatch, frames=8)
    fake_locator(tmp_path, monkeypatch)
    fake_reader(monkeypatch, seconds=4.0)
    ref = [1.0, 0.0, 0.0]
    lost = [0.0, 1.0, 0.0]
    frames = [[ref], [ref], [lost], [lost], [lost]]        # the picture, then only the frames the judge looks at
    calls = fake_libs(monkeypatch, frames)
    out = faces.score(str(tmp_path / "c.mp4"), {"Character 7": [str(tmp_path / "j.png")]}, FACTS, "cuda", 0.3,
                      new_frames=48)
    character_7 = out["face"]["Character 7"]
    assert calls["frames"] == 5, "the picture, then the last two seconds of eight frames at 2 a second: four"
    assert character_7["lost_at"] == 2.5 and character_7["drift"] <= -0.5, "the four judged: 1, 0, 0, 0, from 2.0 s on"
    lines = (tmp_path / "ffmpeg.log").read_text().splitlines()
    decodes = [line for line in lines if "fps=2," in line and "-frames:v" not in line]
    assert len(decodes) == 1 and "-ss 2.000 -i" in decodes[0], decodes


def test_missing_files_or_no_face_in_the_picture_say_why(monkeypatch, tmp_path: Path):
    fake_ffmpeg(tmp_path, monkeypatch)
    fake_locator(tmp_path, monkeypatch, present=False)
    fake_libs(monkeypatch, [[[1.0, 0.0, 0.0]]])
    out = faces.score(str(tmp_path / "c.mp4"), {"Character 7": [str(tmp_path / "j.png")]}, FACTS)
    assert out["face"] is None and "det_10g.onnx not found" in out["why"]
    fake_locator(tmp_path, monkeypatch)
    calls = fake_libs(monkeypatch, [[]])
    monkeypatch.delitem(sys.modules, FACTS["align"]["module"])          # the refiner's module gone: not a fault
    out = faces.score(str(tmp_path / "c.mp4"), {"Character 7": [str(tmp_path / "j.png")]}, FACTS)
    assert out == {"face": None, "why": "no face in the pictures in the boxes",
                   "mouth": None, "mouth_why": faces.mouth.NO_SPEECH}, "the mouth judge still looked for speech"
    assert calls["aligned"].estimate_norm == "insightface's own"
    out = faces.score(str(tmp_path / "c.mp4"), {}, FACTS)
    assert out == {"face": None, "why": faces.NO_PEOPLE, "mouth": None, "mouth_why": faces.mouth.NO_SPEECH}
    # Character 7's picture, Character 4's blank
    fake_libs(monkeypatch, [[[1.0, 0.0, 0.0]], []] + [[[1.0, 0.0, 0.0]]] * 8)
    out = faces.score(str(tmp_path / "c.mp4"), {"Character 7": [str(tmp_path / "j.png")],
                                                "Character 4": [str(tmp_path / "b.png")]},
                      FACTS)
    assert list(out["face"]) == ["Character 7"] and out["faceless"] == ["Character 4"], \
        "the blank picture is named, not dropped"
    fake_reader(monkeypatch, seconds=4.0)
    assert faces._start(str(tmp_path / "c.mp4"), 2, None) == 3.5, "a new part under one judged frame: the last frame"
    assert faces._start(str(tmp_path / "c.mp4"), 48, None) == 2.0
    monkeypatch.setenv("FFMPEG_BINARY", str(tmp_path / "none"))
    monkeypatch.setattr("shutil.which", lambda name: None)
    assert faces.score("c.mp4", {"J": ["j.png"]}, FACTS) == {"face": None, "why": faces.NO_FFMPEG}


def test_finish_judges_a_clip_with_identities_when_asked(monkeypatch, tmp_path: Path):
    seen = {}

    def score(clip, people, facts, device="cpu", bar=0.3, new_frames=None, fps_of_clip=24.0, speaker=None):
        seen.update(clip=clip, people=people, device=device, bar=bar, new_frames=new_frames, speaker=speaker)
        return {"face": {"Character 7": {"min": 0.5}}}
    monkeypatch.setattr(faces, "score", score)
    refs = [Reference("/c/Character 7.png", "identity", "Character 7"), Reference("/c/Character 7.side.png", "identity",
                                                                                  "Character 7"),
            Reference("/c/Character 4.png", "identity", None)]
    asked = ClipRequest("m", "x", (960, 544), 7, 124, references=refs, judge="cpu", judge_bar=0.25,
                        speaker="Character 7")
    assert joins.finish(asked, {}, ["/out/c.mp4"]) == {"face": {"Character 7": {"min": 0.5}}}
    assert seen == {"clip": "/out/c.mp4", "people": {"Character 7": ["/c/Character 7.png", "/c/Character 7.side.png"],
                                                   "the character": ["/c/Character 4.png"]},
                    "device": "cpu", "bar": 0.25, "new_frames": None, "speaker": "Character 7"}
    cont = ClipRequest("m", "x", (960, 544), 7, 48, references=[Reference("/s.mp4", "source"), refs[0]], judge="cuda")
    joins.finish(cont, {"video_length": 48}, ["/out/c.mp4"])
    assert seen["new_frames"] == 47 and seen["device"] == "cuda", "a continue of n frames grows the clip by n − 1"
    quiet = ClipRequest("m", "x", (960, 544), 7, 124, references=refs, judge=None)
    assert joins.finish(quiet, {}, ["/out/c.mp4"]) is None
    assert joins.finish(ClipRequest("m", "x", (960, 544), 7, 124, judge="cpu"), {}, ["/out/c.mp4"]) is None
