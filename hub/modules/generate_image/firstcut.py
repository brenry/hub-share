"""The First cut's clips: Generate lends its model pick, its card, its prompt cleaning and
its judges to the First cut tab as the service `first_cut` (`Cut(ctx)`, Generate's ctx), so that module imports
nothing of this one.

`facts()`: the model by `pick`'s rule, read only (the pulldown's when it is a present video model whose pictures
are identities and whose catalog entry has `soundtrack`, else `lastModel.video` when it is one, else the only present
one, else one line); its 16:9 canvas, of every tier within its budget the one nearest 832×480 by pixels; its lattice,
the largest length on it within the model's `frames.max` (one window: 362 on H3 Ref2VA, ~15 s), and the card's steps
and LoRAs; computed once per `Cut`. `clip(part)`: the part's `ClipRequest` (its pictures as identities in box
order, its slice as the kept sound, `F` frames) and its key, the hash of what the request would make (the wire without
the seed, the judges' fields and the slice's path; each picture's size and mtime; the slice's samples,
`part["sound_digest"]`), so an unchanged part is never rendered twice. `prompt(part, facts)` is pure: Ref2VA's
six fields, the words without `<d>` (the kept track is the speech), a line in frame in the engine's lip wording, a
line off frame nothing (the worker adds the engine's lip phrase to a part with none). `judge` is a
scene's `ShotJudge` that never re-takes.
"""
from __future__ import annotations

import hashlib
import json
import os
import posixpath
from typing import Any

from hub.core.api import ClipRequest, Ctx, Invalid, clip_facts, request_wire

from . import build, cast, judgeshot, models, routes, screen, shotprompt

TARGET = (832, 480)                       # the 480p size; the canvas nearest it by pixels
WIDE = "16:9"                             # the storyboard's own aspect (`tools.SKETCH`)
TAGS = "[reference generation + audio reuse]"
NONE_THERE = "No Ref2VA video model that follows a sound in your model folders"
PICK = "Pick a Ref2VA video model in Generate (one that takes reference pictures and follows a sound)"
NO_WIDE = "{} makes no 16:9 clip"
PRESERVED = "{} (appears in [Shot 1]): fully_preserved"      # the engine's retention line and mode (R22 §A.3 :290)
SPEAKS = "From {} to {} seconds, {} speaks with natural lip movements synchronized: {}"
UNKEYED = ("seed", "sound", "judge", "judge_bar")    # a part's key: what it makes, not how it is judged or named


def follows(model: dict) -> bool:
    """A video model whose pictures are identities and that follows a sound (the catalog's `soundtrack`)."""
    return routes.kind(model) == "video" and models.identities(model) and bool((model.get("video") or {}).get(
        "soundtrack"))


def pick(cat: dict | None, draft: dict, fit: Any = follows, none: str = NONE_THERE, choose: str = PICK) -> dict:
    """The pulldown's model, else `lastModel`'s video model, else the only one; else one line. `fit`:
    which present models count (the First cut's: one that follows a sound; the Storyboard's Render, `storyclip`:
    any that makes clips)."""
    there = [m for m in models.present(cat or {"models": []}) if fit(m)]
    last = draft.get("lastModel") if isinstance(draft.get("lastModel"), dict) else {}
    for wanted in (draft.get("model"), last.get("video")):
        found = models.find(cat, wanted) if wanted else None
        if found is not None and found in there:
            return found
    if len(there) == 1:
        return there[0]
    raise Invalid("model", none if not there else choose)


def canvas(model: dict, label: str) -> tuple[int, int]:
    """The 16:9 size of every tier within the model's budget nearest `TARGET` by pixels."""
    top = models.budget(model)
    sizes = [tuple(t["sizes"][WIDE]) for t in (clip_facts(model) or {}).get("tiers") or [] if WIDE in t["sizes"]]
    sizes = [s for s in sizes if top is None or s[0] * s[1] <= top]
    if not sizes:
        raise Invalid("model", NO_WIDE.format(label))
    w, h = min(sizes, key=lambda s: (abs(s[0] * s[1] - TARGET[0] * TARGET[1]), s[0] * s[1]))
    return int(w), int(h)


def _secs(x: float) -> str:
    return f"{float(x):.2f}"


def prompt(part: dict, facts: dict) -> str:
    """The six fields, one per line (a retention line per person), no blank line; every field as written: the
    engine's labels, the person's name when the model takes names, `N/A` for the soundscape."""
    people = list(dict.fromkeys(p["person"] for p in part["pictures"]))
    names = {p["person"]: p["name"] for p in part["pictures"]}
    boxes: dict[int, list[int]] = {}
    for n, p in enumerate(part["pictures"], 1):
        boxes.setdefault(p["person"], []).append(n)
    label = {k: f"<Subject {i}>" for i, k in enumerate(people, 1)}
    defs = []
    for k in people:
        pics = ", ".join(f"<Picture {n}>" for n in boxes[k])
        defs.append(f"{label[k]} is {shotprompt.clean(names[k])}, from {pics}." if facts["names"]
                    else f"{label[k]} is from {pics}.")
    room = part.get("set") or {}
    place = shotprompt.sentence(room.get("name"))
    cam = part.get("camera") or {}
    framing = shotprompt.sentence(cam.get("framing"))
    summary = " ".join(x for x in (TAGS, framing, place) if x)
    told = [shotprompt.sentence(part.get("style")), place,
            *(shotprompt.sentence(x) for x in room.get("elements") or []),
            "[Shot 1]", framing, shotprompt.sentence(cam.get("move"))]
    who = {str(n).casefold(): k for k, n in enumerate(part["who"])}
    for line in part["lines"]:
        k = who.get(str(line["speaker"]).casefold())
        if line["in_frame"] and k in label:
            said = SPEAKS.format(_secs(line["from_s"]), _secs(line["to_s"]), label[k], shotprompt.clean(line["words"]))
            told.append(said if said[-1] in ".!?…" else said + ".")      # the label kept: not through `sentence`
    # a line off frame sends nothing; the name is the `names` field as typed
    kept = "\n".join(PRESERVED.format(label[k]) + (f" - {shotprompt.clean(names[k])}." if facts["names"] else "")
                     for k in people)
    return (f"subject_definitions: {' '.join(defs)}\nsummary: {summary}\nretention_analysis: {kept}\n"
            f"detailed_description: {' '.join(t for t in told if t)}\n"
            f"overall_soundscape: {shotprompt.NONE}\nnon_diegetic_music: {shotprompt.NONE}")


class Cut:
    """The service (`ctx.offer("first_cut", …)`): one per First cut press or view."""

    RULE: tuple = (follows, NONE_THERE, PICK)   # `pick`'s test and its two lines; `storyclip` has its own

    def __init__(self, ctx: Ctx) -> None:
        self.ctx = ctx
        self._facts: dict[str, Any] | None = None
        self._own: dict[str, Any] = {}

    def facts(self) -> dict[str, Any]:
        """The facts (once): {model, label, names, cap, fps, min, step, window, size, steps, loras}."""
        if self._facts is not None:
            return self._facts
        ctx = self.ctx
        model = pick(models.cached(), ctx.doc(routes.DRAFT, {}).get(), *self.RULE)
        label = models.ui_model(model, models.ref_caps(ctx))["label"]
        size = canvas(model, label)
        video = model["video"]
        lattice = video["frames"]
        lo, step = int(lattice["min"]), max(1, int(lattice["step"]))
        top = int(lattice["max"])                     # the longest pass the model makes (not the window_max)
        card = screen.read(ctx)
        adv = card["advanced"].get(model["id"]) or {}
        locked = models.locked_steps(model)
        s_lo, s_hi = model.get("steps_range") or screen.STEPS
        raw = adv.get("steps")
        ok = isinstance(raw, int) and not isinstance(raw, bool) and s_lo <= raw <= s_hi
        steps = locked if locked is not None else raw if ok else int(video["steps"])
        loras = build._loras(model, screen.stack(card, model["id"]))
        self._own = {"model": model, "pairs": [(name, s) for _, name, s in loras],
                     "encoder": screen.clip_encoder(card, model), "detail": screen.clip_detail(card, model)}
        self._facts = {
            "model": model["id"], "label": label, "names": models.takes_names(model),
            "cap": int((models.picture_refs(model) or {}).get("max") or 0), "fps": float(video["fps"]),
            "min": lo, "step": step, "window": lo + max(0, top - lo) // step * step, "size": list(size),
            "steps": steps, "loras": [{"id": i, "name": os.path.splitext(posixpath.basename(n))[0], "strength": s}
                                      for i, n, s in loras]}
        return self._facts

    def clip(self, part: dict) -> dict[str, Any]:
        """{key, task, seconds} of the part (its `pictures`, `sound`, `set`, `style` added by the First cut)."""
        facts, ctx = self.facts(), self.ctx
        model, label = self._own["model"], facts["label"]
        text = prompt(part, facts)
        paths = [cast.image(ctx, p["id"], "pictures") for p in part["pictures"]]
        refs = [cast.identity(n, path, False, p["name"] if facts["names"] else None, model, label)
                for n, (p, path) in enumerate(zip(part["pictures"], paths, strict=True), 1)]
        on = bool(ctx.settings.get("clip_judge", True))
        speaker = next((ln["speaker"] for ln in part["lines"] if ln["in_frame"]), None)
        frames, fps = int(part["render"]), facts["fps"]
        request = ClipRequest(
            facts["model"], text, (facts["size"][0], facts["size"][1]), None, frames,   # no seed
            steps=facts["steps"], loras=list(self._own["pairs"]), references=refs, encoder=self._own["encoder"],
            detail=self._own["detail"], sound=str(part["sound"]), sound_seconds=frames / fps,
            judge=str(ctx.settings.get("judge_device") or "cpu") if on else None,
            judge_bar=float(ctx.settings.get("clip_face_bar") or 0.3), speaker=speaker)
        task = request_wire(request)
        return {"key": key(task, paths, str(part.get("sound_digest") or "")), "task": task,
                "seconds": round(frames / fps, 2)}

    def judge(self, shots: list[dict], takes_of: tuple) -> judgeshot.ShotJudge:
        """The parts judged as a scene's shots (mouth, face, framing), never rendered again by themselves."""
        return judgeshot.ShotJudge(self.ctx, shots, takes_of, 0.0, again_ok=False)


def key(task: dict, paths: list[str], sound: str) -> str:
    """The first 16 hex of sha256 over the wire request without `UNKEYED`, each picture's size and mtime_ns, and the
    slice's digest (`sound`: its samples, so a re-mix re-renders only the parts whose sound changed)."""
    stats = []
    for p in paths:
        try:
            st = os.stat(p)
            stats.append([p, st.st_size, st.st_mtime_ns])
        except OSError:
            stats.append([p, None, None])
    kept = {k: v for k, v in task.items() if k not in UNKEYED}
    body = json.dumps([kept, stats, sound], sort_keys=True, default=str)
    return hashlib.sha256(body.encode()).hexdigest()[:16]
