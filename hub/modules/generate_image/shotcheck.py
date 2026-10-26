"""Director's first cut: the `shot` the assistant fills, its schema, and the checks that refuse it in one
line before any GPU work; then the prompt (`shotprompt`) and the clip's length from its lines.

The schema is the tool argument's (`additionalProperties` false at every level): the assistant's backend may hold
the call to it as a grammar (R21 §4.1); this module refuses anything the schema would have refused regardless (R25).
The boxes are the screen's: a subject is `<Subject N>` when a box holds the listed character of that name, in
box order, a character's views among its pictures; the Hub never adds a box. A subject named as a character
with no box, on a model whose boxes are identities, is refused. The length: the engine's own estimate of each line
(`turns.planned`, at the voice's measured pace) summed, plus 1 s, up to the model's frame lattice; over
the longest one pass makes, refused. A kept sound decides the length itself; with neither, the Seconds
setting stands. the optional `seconds` is how long the whole shot runs, action and lines; the clip is the
longer of it and the lines' need, never shorter than the lines; over the top, refused with the amount (`OVER`, `LONG`),
the words to cut from the check's own arithmetic (`need`, `top`, `budget`). A speaker who is a boxed character with a
voice sample, on a model whose catalog entry has `voice_reference`, with the Sound box empty and no clip continued, is
voiced from the speaker's sample (`Frame.voices`: audio numbers in the order the lines first name them) when
`voice_route` is `reference`; with `convert` (the default) no voice is referenced and the build converts the
speaker's voice after the render (`clipconvert`). No word of the free text is refused: the compiler cleans
it.
"""
from __future__ import annotations

import contextlib
import contextvars
import math
import re
from collections.abc import Iterator
from typing import Any

from hub.core.api import Ctx, Invalid, spoken_line, turns

from . import cast, chain, models, pace, routes, shotprompt

FIELD = "shot"
NOT_CLIP = "{} makes no clip; a shot is for a video model"
NOT_SUBJECT = "{} speaks but is not a subject"
LINE_ONLY = "A line is the spoken words only"
SOUND_WORDS = "The sound carries the words; leave lines empty"
NO_BOX = "{} has no picture in a box"
CUTS = "Cuts go in order, after 0 s and before the clip's end"
OFF_PLAN = "Cut {} at {} s is inside window {} ({} to {} s); move it to {} s or split the shot"
SLACK = 0.06                     # a cut this close to a boundary (one frame and a half at 24 fps) is on it
OVER = "The lines need {need:.1f} s and one clip holds {top:.1f} s: cut {words} words"
LONG = "seconds is {:.1f} and one clip holds {:.1f} s"
LEAD_SECONDS = 1.0               # the lines' seconds plus one


def _text(lo: int = 0) -> dict:            # no length cap of the Hub's on typed text
    return {"type": "string", "minLength": lo}


def _object(required: list[str], **props: dict) -> dict:
    return {"type": "object", "additionalProperties": False, "required": required, "properties": props}


SCHEMA = _object(
    ["subjects", "where", "camera", "action"],
    subjects={"type": "array", "minItems": 1,
              "items": _object(["name"], name=_text(1), look=_text())},
    where=_text(1), light=_text(),
    camera=_object(["framing"], framing=_text(1), move=_text()),
    action={"type": "array", "minItems": 1, "items": _text(1)},
    lines={"type": "array",
           "items": _object(["speaker", "words"], speaker=_text(1), words=_text(1), language=_text())},
    cuts={"type": "array",
          "items": _object(["at", "to"], at={"type": "number", "minimum": 0}, to=_text(1))},
    ending=_text(),
    sound=_object([], ambience=_text(), music=_text()),
    seconds={"type": "number", "minimum": 1},
)
_TAG = re.compile(r"</?d\b", re.IGNORECASE)
_ONLY: contextvars.ContextVar[tuple[str, ...] | None] = contextvars.ContextVar("boxes", default=None)


@contextlib.contextmanager
def only(ids: list[str]) -> Iterator[None]:
    """A scene's shot: inside, the shot's prompt and press use only the boxes holding these ids, in box
    order (`used`); the boxes on screen are not changed. Outside (every other caller): every box, as before."""
    token = _ONLY.set(tuple(ids))
    try:
        yield
    finally:
        _ONLY.reset(token)


def used(refs: list[dict]) -> list[dict]:
    """The boxes a shot uses: every box, or within `only` those it names."""
    ids = _ONLY.get()
    return refs if ids is None else [r for r in refs if r.get("id") in ids]


def _key(name: Any) -> str:
    return " ".join(str(name or "").split()).lower()


def frame(ctx: Ctx, model: dict, label: str, shot: dict | None = None) -> shotprompt.Frame:
    """What the boxes hold for the prompt: each boxed character's subject number (box order) and pictures (its
    picture then its views, after the continued frame when box 1 holds a clip), a start frame, a kept sound, and
    (given the shot) each voiced speaker's audio number."""
    part = routes.session_part(ctx)
    refs = used([r for r in part.get("references") or [] if isinstance(r, dict) and isinstance(r.get("id"), str)])
    continues = bool(refs) and chain.is_clip(ctx, refs[0]["id"])
    boxes = refs[1:] if continues else refs
    role = (models.picture_refs(model) or {}).get("role")
    sound = bool(part.get("sound")) and bool((models.video(model) or {}).get("soundtrack"))
    boxed: dict[str, tuple[int, tuple[int, ...]]] = {}
    if role == "identity" and boxes:
        cap = int((models.picture_refs(model) or {}).get("max") or 0) or len(boxes)
        entries = cast.with_views(ctx, [(r["id"], "", False) for r in boxes], cap, label)
        at, first = 1 + int(continues), 0
        groups: list[tuple[str | None, list[int]]] = []
        for k, (item, _, _, name) in enumerate(entries):
            if first < len(boxes) and item == boxes[first]["id"]:
                groups.append((name, []))
                first += 1
            groups[-1][1].append(at + k)
        for name, pics in groups:
            if name is not None and _key(name) not in boxed:
                boxed[_key(name)] = (len(boxed) + 1, tuple(pics))
    voices: dict[str, int] = {}
    voiced = ((models.video(model) or {}).get("voice_reference") and not part.get("sound") and not continues
              and ctx.settings.get("voice_route", "convert") == "reference")       # else SeedVC after
    if shot is not None and boxed and voiced:
        for line in shot.get("lines") or []:
            who = _key(line.get("speaker") if isinstance(line, dict) else None)
            name = next((c["name"] for c in ctx.files.characters() if _key(c["name"]) == who), None)
            if who in boxed and who not in voices and name and ctx.files.character_sample(name):
                voices[who] = len(voices) + 1
    return shotprompt.Frame(role == "identity", boxed, role == "start" and bool(boxes) and not continues,
                            continues, sound, voices)



def check(ctx: Ctx, shot: dict, where: shotprompt.Frame, seconds: float) -> None:
    """The one-line refusals: a speaker who is not a subject, a line that is not words alone, lines beside a kept
    sound, a named character with no box on an identity model, cuts out of order or past the clip. No word of the
    free text is refused: the compiler sends it as written (`shotprompt.clean`)."""
    names = {_key(s["name"]) for s in shot["subjects"]}
    for line in shot.get("lines") or []:
        if _key(line["speaker"]) not in names:
            raise Invalid(FIELD, NOT_SUBJECT.format(" ".join(str(line["speaker"]).split())))
        if _TAG.search(line["words"]):
            raise Invalid(FIELD, LINE_ONLY)
        try:
            spoken_line(line["words"])
        except Exception:
            raise Invalid(FIELD, LINE_ONLY) from None
    if where.sound and shot.get("lines"):
        raise Invalid(FIELD, SOUND_WORDS)
    if where.identities:
        listed = {_key(c["name"]) for c in ctx.files.characters()}
        for s in shot["subjects"]:
            if _key(s["name"]) in listed and _key(s["name"]) not in where.boxed:
                raise Invalid(FIELD, NO_BOX.format(" ".join(str(s["name"]).split())))
    times = [float(c["at"]) for c in shot.get("cuts") or []]
    if any(t <= 0 or t >= seconds for t in times) or times != sorted(set(times)):
        raise Invalid(FIELD, CUTS)


def need(lines: list[dict], rate: float | None) -> float:
    """The seconds the lines need: the engine's estimate of each (`turns.planned`, at `rate`) summed, plus the lead."""
    return sum(turns.planned(str(line["words"]), rate) for line in lines) + LEAD_SECONDS


def _top(model: dict, where: shotprompt.Frame) -> int:
    """The most frames one clip makes (a continue's step: `window_max` less the overlap), down to the lattice."""
    clip = models.video(model) or {}
    lattice = clip["frames"]
    cap = int(lattice["max"])
    if where.continues:
        over = chain.overlap(model) or 1
        cap = min(cap, int(clip.get("window_max") or lattice["max"]) - over + 1)
    lo, step = int(lattice["min"]), int(lattice["step"])
    return lo + max(0, (cap - lo) // step) * step


def top(ctx: Ctx, model: dict, where: shotprompt.Frame) -> float:
    """The longest one clip in seconds (`_top` over fps)."""
    return _top(model, where) / float((models.video(model) or {})["fps"])


def budget(ctx: Ctx, model: dict, where: shotprompt.Frame) -> tuple[int, int]:
    """(words, stops): the most words one line holds, with one stop per 8 words, whose `need` stays within `top`."""
    rate, most = pace.current(ctx), top(ctx, model, where)
    fits = 0
    while True:
        n = fits + 1
        if need([{"words": " ".join(["word"] * n) + "." * math.ceil(n / 8)}], rate) > most + 1e-9:
            return fits, math.ceil(fits / 8)
        fits = n


def frames(ctx: Ctx, model: dict, shot: dict, where: shotprompt.Frame) -> int | None:
    """The clip's frames (None: a kept sound decides, or neither lines nor `seconds`: the Seconds setting): the
    longer of the lines' `need` and `seconds`, up to the lattice; over the longest one pass makes (a continue's
    step), refused with the amount, the lines first."""
    lines = shot.get("lines") or []
    if where.sound:
        return None
    clip = models.video(model) or {}
    lattice, fps = clip["frames"], int(clip["fps"])
    rate = pace.current(ctx)
    needed = need(lines, rate) if lines else 0.0
    planned = float(shot.get("seconds") or 0)
    want = max(needed, planned)
    if want <= 0:
        return None
    most = _top(model, where)
    if math.ceil(needed * fps - 1e-9) > most:
        words = math.ceil((needed - most / fps) * (rate or turns.WORDS_PER_SECOND) - 1e-9)
        raise Invalid(FIELD, OVER.format(need=needed, top=most / fps, words=words))
    if math.ceil(planned * fps - 1e-9) > most:
        raise Invalid(FIELD, LONG.format(planned, most / fps))
    lo, step = int(lattice["min"]), int(lattice["step"])
    return lo + max(0, math.ceil((math.ceil(want * fps - 1e-9) - lo) / step)) * step


def prepare(ctx: Ctx, model: dict, shot: Any, seconds: float) -> tuple[str, int | None]:
    """The shot checked, its prompt (sent whole) and its frames (`frames`). `seconds`: the clip's
    length without lines (the Seconds setting), for the cuts."""
    ui = models.ui_model(model, models.ref_caps(ctx))
    if ui["kind"] != "video":
        raise Invalid(FIELD, NOT_CLIP.format(ui["label"]))
    if not isinstance(shot, dict):
        raise Invalid(FIELD, "shot must be an object")
    where = frame(ctx, model, ui["label"], shot)
    n = frames(ctx, model, shot, where)
    check(ctx, shot, where, n / int(ui["video"]["fps"]) if n else seconds)
    return shotprompt.compile_shot(shot, where), n


def cuts_on_plan(shot: dict, plan: dict | None) -> None:
    """Each of the shot's `cuts` lands within `SLACK` of a window boundary of the engine's plan, else one line
    naming the window and the boundary to move it to. No plan, or no windows (a continue; the engine not asked): no
    check."""
    windows = (plan or {}).get("windows") or []
    if len(windows) < 2:
        return
    ends, at = [], 0.0
    for w in windows:
        at += float(w.get("new_frames") or 0) / max(1.0, float(w.get("frames") or 1)) * float(w.get("seconds") or 0.0)
        ends.append(at)
    for n, cut in enumerate(shot.get("cuts") or [], 1):
        t = float(cut["at"])
        if any(abs(t - e) <= SLACK for e in ends):
            continue
        k = next((i for i, e in enumerate(ends) if t < e), len(ends) - 1)
        start = ends[k - 1] if k else 0.0
        nearest = min(ends, key=lambda e: abs(e - t))
        raise Invalid(FIELD, OFF_PLAN.format(n, f"{t:g}", k + 1, f"{start:.2f}", f"{ends[k]:.2f}", f"{nearest:.2f}"))
