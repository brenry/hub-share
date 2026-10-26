"""The face judge: a clip is scored, second by second, for how much the face in it is the character's in
the box. Stdlib only; the engine's face models and the libraries that run them are imported at the call, inside the
engine's Python.

The engine's face refiner ships InsightFace: a detector, 106 landmarks and the ArcFace recognition model, found by the
engine's own file locator under one asset folder (the folder and the file names are in the facts file, `faces`, never
here; `insightface` and `onnxruntime` are the engine's requirements). `app.get(bgr)` on a frame gives each face's `bbox`
and `normed_embedding`; the cosine of two normed embeddings is their similarity (R40 §4). Frames are decoded by the
engine's ffmpeg (`soundtail.ffmpeg()`) at `FPS` a second and `WIDTH` wide, raw BGR; a reference picture the same way,
whole. The reference of a character is the mean embedding of its picture and views (the request's identities of one
name; nameless identities are one character). Per frame the face whose similarity is highest is the character's; the
series gives `min` and `median` (over the frames with a face), `first` and `last` (the first and last second's means, a
frame without the face as 0), `drift` (last − first), `lost_at` (the second from which it stays under the bar, or is
absent, for a full second) and `present` (the share of frames with a face). The character's face's box per frame gives
the frame judge's numbers (`framing`: the face's height as a share of the frame's and its path), and the same
app then reads the speaker's mouth (`mouth.score`). The judge runs on the CPU provider unless asked for `cuda`, so it
never takes the GPU's memory beside the model. Anything that cannot be done here gives `{"face": None, "why": …}`, never
an exception.
"""
from __future__ import annotations

import importlib
import os
import subprocess
from pathlib import Path
from typing import Any

from . import mouth, soundtail

READS: dict[str, dict[str, str]] = {c: {} for c in ("wgp", "api", "definition", "settings", "generate_video",
                                                    "suffixes")}
LOCATOR = "shared.utils.files_locator"
FPS = 2                       # frames judged a second
WIDTH = 640                   # every frame this wide: the detector's own size
SECONDS = 600                 # the most a decode may take
PROVIDERS = {"cpu": ["CPUExecutionProvider"], "cuda": ["CUDAExecutionProvider", "CPUExecutionProvider"]}
NO_FFMPEG = "no ffmpeg to decode the clip"
NO_PEOPLE = "no character in a box"
TASKS = ("detection", "recognition", "landmark_2d_106")   # the three files: the mouth judge reads the third


def _decode(program: str, path: str, fps: int | None, one: bool = False, start: float = 0.0) -> bytes | None:
    """Raw BGR24 output of a decode at `fps` (None: every frame), scaled to exactly WIDTH wide; `one`: one frame;
    `start`: from that second on (an input seek, frame-accurate)."""
    scale = f"scale={WIDTH}:-2"
    argv = [program, "-nostdin", "-v", "error", *(["-ss", f"{start:.3f}"] if start > 0 else []), "-i", path,
            "-vf", f"fps={fps},{scale}" if fps else scale,
            *(["-frames:v", "1"] if one else []), "-f", "rawvideo", "-pix_fmt", "bgr24", "-"]
    try:
        done = subprocess.run(argv, capture_output=True, timeout=SECONDS, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return done.stdout if done.returncode == 0 and done.stdout else None


def _frames(program: str, path: str, fps: int | None, start: float = 0.0) -> tuple[list[bytes], int, int] | None:
    """Raw BGR frames of a clip at `fps` (None: a picture, whole) from `start` seconds on, WIDTH wide: (frames, w,
    h). The height is read from a one-frame decode, so it is exactly what ffmpeg made."""
    first = _decode(program, path, fps, one=True)
    if first is None or len(first) % (WIDTH * 3):
        return None
    h = len(first) // (WIDTH * 3)
    frame = WIDTH * h * 3
    data = first if fps is None else _decode(program, path, fps, start=start)
    if not data or len(data) < frame:
        return None
    return [data[i:i + frame] for i in range(0, len(data) - frame + 1, frame)], WIDTH, h


_apps: dict[str, Any] = {}                                    # one loaded app per device, for the worker's life


def app_for(facts: dict[str, Any], device: str) -> Any:
    """`_app`: on the CPU loaded once and kept (the three ONNX sessions take seconds to open, and every clip asks);
    on `cuda` opened per clip and let go, so nothing of the judge's stays on the GPU beside the model."""
    if device != "cpu":
        return _app(facts, device)
    if device not in _apps:
        _apps[device] = _app(facts, device)
    return _apps[device]


def _app(facts: dict[str, Any], device: str) -> Any:
    """InsightFace with the engine's own files (the folder and names from the facts), on the chosen provider."""
    fl = importlib.import_module(LOCATOR)
    first = fl.locate_file(f"{facts['folder']}/{facts['files'][0]}", error_if_none=False)
    if not first or not os.path.isfile(first):
        raise FileNotFoundError(f"{facts['folder']}/{facts['files'][0]} not found")
    folder = os.path.dirname(os.path.abspath(first))
    onnxruntime = importlib.import_module("onnxruntime")
    zoo = importlib.import_module("insightface.model_zoo").model_zoo
    analysis = importlib.import_module("insightface.app").FaceAnalysis
    onnxruntime.set_default_logger_severity(3)                    # as the refiner: warnings and up
    align = facts.get("align") or {}
    if align:                                                     # the refiner's own alignment (facts `align`)
        try:
            fn = getattr(importlib.import_module(str(align["module"])), str(align["function"]))
            importlib.import_module("insightface.utils.face_align").estimate_norm = fn
        except Exception:  # noqa: BLE001  (the refiner moved: InsightFace's own alignment stands)
            pass
    available = set(onnxruntime.get_available_providers())
    providers = [p for p in PROVIDERS.get(device, PROVIDERS["cpu"]) if p in available] or ["CPUExecutionProvider"]
    app = analysis.__new__(analysis)
    app.models, app.model_dir = {}, folder
    for name in facts["files"]:
        path = os.path.join(folder, name)
        if not os.path.isfile(path):
            raise FileNotFoundError(f"{facts['folder']}/{name} not found")
        model = zoo.get_model(path, providers=providers)
        if model is not None and model.taskname in TASKS:
            app.models[model.taskname] = model
    if "detection" not in app.models or "recognition" not in app.models:
        raise RuntimeError("the face files hold no detector and recognizer")
    app.det_model = app.models["detection"]
    app.prepare(ctx_id=0 if providers[0].startswith("CUDA") else -1, det_size=(640, 640))
    return app


def _faces(app: Any, np: Any, raw: bytes, w: int, h: int) -> list[Any]:
    """The faces InsightFace finds in one raw frame (each with `normed_embedding`, `bbox`, `kps`, landmarks)."""
    frame = np.frombuffer(raw, dtype=np.uint8).reshape(h, w, 3)
    return [f for f in app.get(frame) if getattr(f, "normed_embedding", None) is not None]


def _median(values: list[float]) -> float:
    ordered = sorted(values)
    half = len(ordered) // 2
    return ordered[half] if len(ordered) % 2 else (ordered[half - 1] + ordered[half]) / 2


def framing(boxes: list[list[float] | None], w: int, h: int, fps: int) -> dict[str, Any]:
    """The frame judge from one character's face box per frame: `size` (the box's height as a share of
    the frame's, the median), and the path: `size_first`/`size_last`, `x_first`/`x_last`, `y_first`/`y_last` (the
    centre as shares of the width and the height; the first and the last second's means)."""
    seen = [b for b in boxes if b]
    if not seen:
        return {"size": None}
    head = [b for b in boxes[:fps] if b] or seen[:1]
    tail = [b for b in boxes[-fps:] if b] or seen[-1:]
    measures = {"size": lambda b: (b[3] - b[1]) / h, "x": lambda b: (b[0] + b[2]) / 2 / w,
                "y": lambda b: (b[1] + b[3]) / 2 / h}
    out: dict[str, Any] = {"size": round(_median([measures["size"](b) for b in seen]), 3)}
    for key, f in measures.items():
        out[f"{key}_first"] = round(sum(map(f, head)) / len(head), 3)
        out[f"{key}_last"] = round(sum(map(f, tail)) / len(tail), 3)
    return out


def series(scores: list[float | None], fps: int, bar: float, offset: float = 0.0) -> dict[str, Any]:
    """The judge's numbers from one character's similarity per frame (None: no face in that frame); `offset`: the
    second the first frame is at (a continue's judged part), so `lost_at` is a second of the clip."""
    seen = [s for s in scores if s is not None]
    if not scores:
        return {"min": None, "median": None, "first": None, "last": None, "drift": None, "lost_at": None,
                "present": 0.0}
    if not seen:                                                      # never in the judged part: lost from its start
        return {"min": 0.0, "median": 0.0, "first": 0.0, "last": 0.0, "drift": 0.0, "lost_at": round(offset, 2),
                "present": 0.0}
    median = _median(seen)
    head = [0.0 if s is None else s for s in scores[:fps]]           # a frame without the face counts 0 here,
    tail = [0.0 if s is None else s for s in scores[-fps:]]          # so "0.99 → 0.00" says it left the frame
    first, last = sum(head) / len(head), sum(tail) / len(tail)
    lost_at = None
    for i in range(len(scores)):
        window = scores[i:i + fps]
        if len(window) == fps and all(s is None or s < bar for s in window):
            lost_at = round(offset + i / fps, 2)
            break
    return {"min": round(min(seen), 3), "median": round(median, 3), "first": round(first, 3),
            "last": round(last, 3), "drift": round(last - first, 3), "lost_at": lost_at,
            "present": round(len(seen) / len(scores), 3)}


def _start(clip: str, new_frames: int | None, fps_of_clip: float | None) -> float:
    """The second a continue's new part begins, by the Hub's own MP4 reader (its length and rate); 0 for a whole
    clip, or when the file cannot be read (then the whole clip is judged)."""
    if not new_frames:
        return 0.0
    try:
        got = soundtail.reader().facts(Path(clip))
        fps = float(fps_of_clip or got["fps"] or 24.0)
        seconds = float(got["seconds"])
        return max(0.0, min(seconds - new_frames / fps, seconds - 1.0 / FPS))   # at least one judged frame
    except Exception:  # noqa: BLE001
        return 0.0


def _references(program: str, app: Any, np: Any, people: dict[str, list[str]]) -> dict[str, Any]:
    """Each character's reference: the mean embedding of its picture and views, normed; none for a face-less one."""
    refs: dict[str, Any] = {}
    for name, pictures in people.items():
        found = []
        for picture in pictures:
            decoded = _frames(program, picture, None)
            if decoded:
                found.extend(f.normed_embedding for f in _faces(app, np, decoded[0][0], decoded[1], decoded[2]))
        if found:
            mean = np.mean(np.stack(found), axis=0)
            refs[name] = mean / (np.linalg.norm(mean) or 1.0)
    return refs


def score(clip: str, people: dict[str, list[str]], facts: dict[str, Any], device: str = "cpu",
          bar: float = 0.3, new_frames: int | None = None, fps_of_clip: float | None = None,
          speaker: str | None = None) -> dict[str, Any]:
    """`{"face": {name: series…}, "frame": {name: framing…}, "mouth": …}`, or with `"face": None, "why": line` when the
    faces could not be judged (no character in a box, no face in the character's pictures, the files absent). `people`:
    each character's picture paths ({} : the mouth judge alone, on the largest face); `new_frames`: a continued clip's
    new frames (the file holds the source too): only that part is read, from its second on (`_start`); `fps_of_clip`:
    its rate, else the file's own; `speaker`: whose mouth the mouth judge reads."""
    program = soundtail.ffmpeg()
    if program is None:
        return {"face": None, "why": NO_FFMPEG}
    try:
        np = importlib.import_module("numpy")
        app = app_for(facts, device)
    except Exception as exc:  # noqa: BLE001  (the files absent, the libraries absent: one line)
        return {"face": None, "why": (str(exc).strip().splitlines() or [type(exc).__name__])[0][:160]}
    start = _start(clip, new_frames, fps_of_clip)
    refs = _references(program, app, np, people) if people else {}
    out: dict[str, Any] = {"face": None, "why": NO_PEOPLE if not people else "no face in the pictures in the boxes"}
    faceless = [name for name in people if name not in refs]        # a character whose pictures show no face
    if refs:
        decoded = _frames(program, clip, FPS, start)
        if not decoded:
            return {"face": None, "why": "the clip could not be decoded", "mouth": None,
                    "mouth_why": "the clip could not be decoded"}
        frames, w, h = decoded
        per: dict[str, list[float | None]] = {name: [] for name in refs}
        boxes: dict[str, list[list[float] | None]] = {name: [] for name in refs}
        for raw in frames:
            found = _faces(app, np, raw, w, h)
            for name, ref in refs.items():
                best = max(found, key=lambda f: float(np.dot(ref, f.normed_embedding)), default=None)
                per[name].append(float(np.dot(ref, best.normed_embedding)) if best is not None else None)
                boxes[name].append([float(v) for v in best.bbox] if best is not None else None)
        out = {"face": {name: series(scores, FPS, bar, start) for name, scores in per.items()},
               "frame": {name: framing(boxes[name], w, h, FPS) for name in refs}}
        if faceless:
            out["faceless"] = faceless
    try:
        out.update(mouth.score(program, app, np, clip, refs, speaker, start=start))   # the judged part alone
    except Exception as exc:  # noqa: BLE001  (the mouth judge is advice; the face's verdict stands)
        out.update({"mouth": None, "mouth_why": (str(exc).strip().splitlines() or [type(exc).__name__])[0][:160]})
    return out
