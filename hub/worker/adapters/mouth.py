"""The mouth judge: does the speaker's mouth move with the words. Stdlib only; InsightFace and numpy come
in from the face judge (`faces.score`), which calls this after its own pass, with the same app.

The engine's face refiner measures a mouth's opening as `|landmark[53].y − landmark[62].y| / eye distance`, the eye
distance from the first two of the 5 keypoints (the refiner's `face.py:248-257`, under `postprocessing/`); the Hub takes
the same measure from InsightFace's `landmark_2d_106` and `kps`. The spans of speech come from the engine's own
`shared/deepy/audio_inspection.speech_intervals(path)` (`:146-178`: 200-4000 Hz band energy in 20 ms windows, the clip
read directly; a clip without a sound track raises). Frames at `MOUTH_FPS` a second, `faces.WIDTH` wide; per frame the
speaker's face (the best cosine to the speaker's reference; no reference: the largest face) and its opening; the motion
is the opening's change frame to frame. `talk` is the mean motion inside the spans, `rest` the mean at least `AWAY`
seconds outside every span, `lips = talk / (talk + rest)` (None when the clip never rests: a line that fills it),
`moving` the share of speaking frames whose motion is over `STILL`, `speech` the spans' seconds, `speech_from` and
`speech_to` the first span's start and the last span's end. A continue is judged from `start` on (its new
seconds, as the face judge counts them), decoded from there: the source's part is never read. Anything that cannot be
done gives `{"mouth": None, "mouth_why": …}`, never an exception.
"""
from __future__ import annotations

import importlib
from typing import Any

INSPECTION = "shared.deepy.audio_inspection"
READS: dict[str, dict[str, str]] = {c: {} for c in ("wgp", "api", "definition", "settings", "generate_video",
                                                    "suffixes")}
MOUTH_FPS = 8                  # frames read a second: lips need finer time than the face judge's 2
UPPER, LOWER = 53, 62          # the 106 landmarks the engine's refiner measures between (face.py:257)
AWAY = 0.25                    # a frame this far from every span is at rest
STILL = 0.01                   # motion under this is a still mouth
NO_SPEECH = "no speech in the soundtrack"
NO_FACE = "no face to read the mouth of"


def spans(clip: str) -> list[tuple[float, float]]:
    """The clip's spans of speech, by the engine's own inspection; [] when it has no sound or no speech."""
    try:
        found = importlib.import_module(INSPECTION).speech_intervals(clip)
    except Exception:  # noqa: BLE001  (no sound track, or the module absent: no speech)
        return []
    return [(float(a), float(b)) for a, b in found or []]


def opening(face: Any) -> float | None:
    """The engine's measure of a face's mouth: the lips' distance over the eyes' distance; None without landmarks."""
    marks, kps = getattr(face, "landmark_2d_106", None), getattr(face, "kps", None)
    if marks is None or kps is None:
        return None
    eyes = ((float(kps[0][0]) - float(kps[1][0])) ** 2 + (float(kps[0][1]) - float(kps[1][1])) ** 2) ** 0.5
    if eyes < 1e-6:
        return None
    return abs(float(marks[UPPER][1]) - float(marks[LOWER][1])) / eyes


def _pick(found: list[Any], np: Any, ref: Any) -> Any:
    """The speaker's face among those found: the best match to the speaker's reference, else the largest."""
    if not found:
        return None
    if ref is not None:
        return max(found, key=lambda f: float(np.dot(ref, f.normed_embedding)))
    return max(found, key=lambda f: (float(f.bbox[2]) - float(f.bbox[0])) * (float(f.bbox[3]) - float(f.bbox[1])))


def measure(openings: list[float | None], times: list[float], speech: list[tuple[float, float]]) -> dict[str, Any]:
    """The judge's numbers from the speaker's opening per frame and each frame's second."""
    talk: list[float] = []
    rest: list[float] = []
    for i in range(1, len(openings)):
        a, b = openings[i - 1], openings[i]
        if a is None or b is None:
            continue
        t = times[i]
        if any(s <= t <= e for s, e in speech):
            talk.append(abs(b - a))
        elif all(t < s - AWAY or t > e + AWAY for s, e in speech):
            rest.append(abs(b - a))
    talking = sum(talk) / len(talk) if talk else None
    resting = sum(rest) / len(rest) if rest else None
    lips = None
    if talking is not None and resting is not None and talking + resting > 0:
        lips = round(talking / (talking + resting), 3)
    r4 = lambda v: None if v is None else round(v, 4)  # noqa: E731
    return {"lips": lips, "moving": round(sum(1 for m in talk if m > STILL) / len(talk), 3) if talk else None,
            "talk": r4(talking), "rest": r4(resting), "speech": round(sum(e - s for s, e in speech), 2),
            "speech_from": round(min(s for s, _ in speech), 2) if speech else None,
            "speech_to": round(max(e for _, e in speech), 2) if speech else None,
            "present": round(sum(1 for o in openings if o is not None) / len(openings), 3) if openings else 0.0}


def score(program: str, app: Any, np: Any, clip: str, refs: dict[str, Any], speaker: str | None,
          start: float = 0.0) -> dict[str, Any]:
    """`{"mouth": {"speaker", "lips", "moving", "talk", "rest", "speech", "speech_from", "speech_to",
    "present"}}` or `{"mouth": None,
    "mouth_why": …}`. `refs`: the face judge's reference embeddings by name; `start`: the second the judged part
    begins (a continue's new part), 0 for the whole clip."""
    from . import faces  # late: faces imports this module

    speech = [(max(s, start), e) for s, e in spans(clip) if e > start]
    if not speech:
        return {"mouth": None, "mouth_why": NO_SPEECH}
    decoded = faces._frames(program, clip, MOUTH_FPS, start)
    if not decoded:
        return {"mouth": None, "mouth_why": "the clip could not be decoded"}
    frames, w, h = decoded
    who = next((n for n in refs if speaker and n.casefold() == speaker.casefold()), None)
    if who is None and speaker is None and len(refs) == 1:          # nobody named, one character: its mouth
        who = next(iter(refs))
    ref = refs[who] if who else None                                 # a speaker not in the boxes: the largest face
    openings: list[float | None] = []
    times: list[float] = []
    for i, raw in enumerate(frames):
        face = _pick(faces._faces(app, np, raw, w, h), np, ref)
        openings.append(opening(face) if face is not None else None)
        times.append(start + (i + 0.5) / MOUTH_FPS)
    if all(o is None for o in openings):
        return {"mouth": None, "mouth_why": NO_FACE}
    name = who or speaker or "the speaker"
    return {"mouth": {"speaker": name, **measure(openings, times, speech)}}
