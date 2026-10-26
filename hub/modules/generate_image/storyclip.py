"""The Storyboard's Render: Generate lends the Director the `Clip:` route's own clip
of one shot as the service `clip_plan` (`Shots(ctx)`, Generate's ctx), so that module imports nothing of this one.

The model is the Director's, per shot, from the catalog's facts alone (`way`); the pulldown and `lastModel` are never
read for it and never changed. Who is in frame and how each one's picture is used (the Director's `render.uses`: a
cast member's `picture_use`, "reference" by default with a picture, "none" without one) decide it: anyone
`reference` → a present model whose pictures are identities (`models.identities`: Ref2VA), the members' pictures;
else anyone `frame` → a present first-frame model (the catalog's role `start`: FL2VA), the member's picture its start
frame; else (nobody pictured, an empty shot) → a present model that renders from words alone (`models.clip_modes`
"new"); else a still drawn from the shot's words on a present picture model (`still`, one more task the Render
chains before the clip by `inputs`) as the start frame of a first-frame model. A `reference` with no identity model
present falls to the first-frame model with the member's picture as the start, a `frame` with no first-frame model
to the identity model; of several present models of one kind, the catalog's first (`models.present`'s order). The
engine's first-frame and identity models both run with no picture (its definitions offer a text-only
run): the catalog says it as `min` 0 (`catalogvideo.picture_refs`, `upstream.identities`).

Each model's facts are the First cut's `Cut` (its canvas, lattice, steps, LoRAs, text encoder and detail
from the card), one per model. `clip(part)` is one shot's `ClipRequest`: its prompt the `Clip:` route's compiler
(`shotprompt.compile_shot`: the shot's fields as written; with lines each `<d>` line the video model speaks, no
voice sample), its pictures by the shot's way, its length the shot's seconds on the model's
lattice within one pass. No session state is read or written: the screen's draft, shot and boxes stay as they are.
"""
from __future__ import annotations

import math
from typing import Any

from hub.core.api import ClipRequest, Invalid, Reference, request_wire

from . import build, cast, firstcut, models, routes, shotprompt

NONE_THERE = "No video model that makes clips in your model folders"
NO_WAY = "shot {} needs a first frame, and no model in your model folders can make one from words"
PASTED = "subject_definitions:"                 # a pasted H3 prompt's first field
USES = ("reference", "frame", "none")          # a cast member's `picture_use`
WAYS = ("identity", "start", "words", "still")  # how a shot's clip is made: its pictures' role, or none, or a still


def makes_clips(model: dict) -> bool:
    """A video model: it makes clips (`routes.kind`)."""
    return routes.kind(model) == "video"


def starts_from(model: dict) -> bool:
    """A first-frame model: the catalog's role for its pictures is `start`."""
    return (models.picture_refs(model) or {}).get("role") == "start"


def from_words(model: dict) -> bool:
    """A model that renders with no picture (the catalog's `min` 0, or no pictures at all)."""
    return "new" in models.clip_modes(model)


def draws(model: dict) -> bool:
    """A picture model that draws from words alone."""
    return routes.kind(model) == "image" and not models.video(model) and "new" in models.modes(model)


def way(videos: list[dict], refer: bool, start: bool, painter: bool) -> tuple[dict, str] | None:
    """The model and way of a shot (the module docstring): `refer` anyone in frame `reference`, `start` anyone
    `frame`, `painter` a picture model present; None when no present model can make it."""
    ids = [m for m in videos if models.identities(m)]
    firsts = [m for m in videos if starts_from(m)]
    words = sorted((m for m in videos if from_words(m)), key=lambda m: (not models.identities(m), not starts_from(m)))
    for wanted, pool, how in ((refer, ids, "identity"), (start, firsts, "start"), (refer, firsts, "start"),
                              (start, ids, "identity"), (True, words, "words"), (painter, firsts, "still")):
        if wanted and pool:
            return pool[0], how
    return None


def _key(name: Any) -> str:
    return " ".join(str(name or "").split()).lower()


def frames(facts: dict, seconds: float) -> int:
    """The shot's seconds as frames on the lattice (`min + k * step`, never under `min`), within one pass."""
    n = math.ceil(max(0.0, float(seconds)) * float(facts["fps"]) - 1e-9)
    lo, step = int(facts["min"]), int(facts["step"])
    return min(int(facts["window"]), lo if n <= lo else lo + -(-(n - lo) // step) * step)


def frame(identities: bool, pictures: list[dict], start: bool = False) -> shotprompt.Frame:
    """What the compiler needs: each pictured person's subject number and picture numbers, by folded name."""
    boxed: dict[str, tuple[int, tuple[int, ...]]] = {}
    if identities:
        for n, p in enumerate(pictures, 1):
            who = _key(p["name"])
            k, held = boxed.get(who, (len(boxed) + 1, ()))
            boxed[who] = (k, (*held, n))
    return shotprompt.Frame(identities, boxed, start)


def still_words(shot: dict) -> str:
    """The still's prompt: the shot's framing, place, light, each subject's look and its first action."""
    cam = shot.get("camera") or {}
    people = [f"{s['name']}, {s['look']}" if s.get("look") else str(s["name"]) for s in shot.get("subjects") or []]
    told = [cam.get("framing"), shot.get("where"), shot.get("light"), *people, *(shot.get("action") or [])[:1]]
    return " ".join(s for s in (shotprompt.sentence(t) for t in told if isinstance(t, str)) if s)


class One(firstcut.Cut):
    """One model's facts (the First cut's): `firstcut.pick`'s test admits that model alone, so the draft decides
    nothing."""

    def __init__(self, ctx: Any, model: dict) -> None:
        super().__init__(ctx)
        self.RULE = (lambda m: m["id"] == model["id"], NONE_THERE, NONE_THERE)


class Shots:
    """The service (`ctx.offer("clip_plan", …)`): one per Render press."""

    def __init__(self, ctx: Any) -> None:
        self.ctx = ctx
        self._cuts: dict[str, One] = {}

    def _present(self) -> list[dict]:
        """Present models, `lastModel`'s (each kind) first: the Hub picks among the models last used, never
        changing the pulldown, so a larger present model not last used is not loaded instead."""
        there = models.present(models.cached() or {"models": []})
        last = (self.ctx.doc(routes.DRAFT, {}).get() or {}).get("lastModel") or {}
        used = {str(v) for v in last.values() if v}
        return sorted(there, key=lambda m: 0 if str(m.get("id")) in used else 1)

    def ready(self) -> None:
        """One line when no present model makes clips."""
        if not any(makes_clips(m) for m in self._present()):
            raise Invalid("model", NONE_THERE)

    def pick(self, sid: str, refer: bool, start: bool) -> dict[str, Any]:
        """The shot's model's facts (`firstcut.Cut.facts`) and its `way`; one line when none can make it."""
        there = self._present()
        found = way([m for m in there if makes_clips(m)], refer, start, any(draws(m) for m in there))
        if found is None:
            raise Invalid("model", NO_WAY.format(sid))
        model, how = found
        cut = self._cuts.setdefault(model["id"], One(self.ctx, model))
        return {**cut.facts(), "way": how}

    def still(self, shot: dict, size: list[int]) -> dict:
        """The still a first-frame clip starts from: one picture of the shot's words at the clip's canvas, mode new,
        no reference and no LoRA, the model's own steps, on the catalog's first present picture model."""
        painter = next(m for m in self._present() if draws(m))
        ui = models.ui_model(painter, models.ref_caps(self.ctx))
        w, h = models.within(painter, int(size[0]), int(size[1]), int(size[0]) / int(size[1]))
        return build.picture_job({"mode": "new", "prompt": still_words(shot), "width": w, "height": h, "images": 1,
                                  "steps": None, "guidance": None, "seed": {"mode": "none"}, "loras": []},
                                 self.ctx, painter, ui).tasks[0]

    def references(self, cut: One, how: str, pictures: list[dict]) -> tuple[list[Reference], shotprompt.Frame]:
        """The shot's pictures by its way, and the compiler's frame of them."""
        ctx, facts, model = self.ctx, cut.facts(), cut._own["model"]
        if how == "identity" and pictures:
            paths = [cast.image(ctx, p["id"], "pictures") for p in pictures]
            refs = [cast.identity(n, path, False, p["name"] if facts["names"] else None, model, facts["label"])
                    for n, (p, path) in enumerate(zip(pictures, paths, strict=True), 1)]
            return refs, frame(True, pictures)
        if how == "start" and pictures:
            return [Reference(cast.image(ctx, pictures[0]["id"], "pictures"), "start")], frame(False, [], True)
        if how == "still":
            return [Reference("", "start")], frame(False, [], True)       # its path: the still's, filled at run
        return [], frame(models.identities(model), [])

    def own(self, cut: One, how: str, pictures: list[dict]) -> tuple[list[Reference], shotprompt.Frame]:
        """A shot's own pictures (`director/shotpics.py`): <Picture 1>, <Picture 2>, ... in the shot's order, tied to no
        subject; on a first-frame model the first one is the start frame."""
        ctx, facts, model = self.ctx, cut.facts(), cut._own["model"]
        paths = [cast.image(ctx, p["id"], "pictures") for p in pictures]
        if how == "identity":
            refs = [cast.identity(n, path, False, None, model, facts["label"]) for n, path in enumerate(paths, 1)]
            return refs, frame(True, [])
        return [Reference(paths[0], "start")], frame(False, [], True)

    def clip(self, part: dict) -> dict[str, Any]:
        """{task, still, frames, seconds, audio, fps, size, label, steps, loras} of the part {id, shot (the `Clip:`
        route's shot), pictures, seconds, model, way} (`still`: the picture task its start frame is, else None)."""
        cut = self._cuts[part["model"]]
        facts, own = cut.facts(), cut._own
        refs, where = (self.own(cut, part["way"], part["pictures"]) if part.get("own")
                       else self.references(cut, part["way"], part["pictures"]))
        said = " ".join((part["shot"].get("action") or [""])[:1]).strip()
        # a shot whose action is a whole H3 prompt (it starts with `subject_definitions:`) goes to the model as pasted
        text = said if said.startswith(PASTED) else shotprompt.compile_shot(part["shot"], where)
        n = frames(facts, part["seconds"])
        request = ClipRequest(
            facts["model"], text, (facts["size"][0], facts["size"][1]), None, n,   # no seed
            steps=facts["steps"], loras=[*own["pairs"], *(tuple(x) for x in part.get("loras") or []
                                                         if own["model"].get("loras"))],
            references=refs, encoder=own["encoder"],
            detail=own["detail"])
        return {"task": request_wire(request), "frames": n, "seconds": round(n / float(facts["fps"]), 2),
                "still": self.still(part["shot"], facts["size"]) if part["way"] == "still" else None,
                "audio": bool((models.video(own["model"]) or {}).get("soundtrack")), "fps": float(facts["fps"]),
                "size": list(facts["size"]), "label": facts["label"], "steps": facts["steps"],
                "loras": facts["loras"]}
