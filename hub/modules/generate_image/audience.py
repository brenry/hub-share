"""The scene's audience as sound: a reaction a shot names, placed under the cut after that shot,
ducked under the speech, as steps inside the scene's one job.

A shot's `reaction` (applause, laughter or gasps) is the scene's, never the shot's: `scene.shots` drops it, and the
room is heard, never written: the compiler sends the shot's own ambience and nothing of the Hub's,
and no word of the plan is refused for naming it.
Each kind's sound is `sounds/audience/<kind>.wav`, the Hub's own file in its sounds root: kept from Sounds
(`Keep as audience…`) or made once by a sound task before the first shot, on the first available model the
catalog marks `sounds`, then filed under the kind when the job ends (`Finish`); neither: the scene fails
before anything renders (`resolve`). The cue is the cut after the shot, from the planned frames the join cuts by; the
last shot's reaction ends with the file (`place`). Each is one level, faded, ducked under track 1 (`level`). Nothing
of a sound's prompt is written: it is sent with its task alone.
"""
from __future__ import annotations

import os
import re
from collections.abc import Callable, Mapping
from typing import Any

from hub.core.api import Ctx, Invalid, JobPlan, JoinSound, SoundRequest, best_take, request_wire

from . import models

KINDS = ("applause", "laughter", "gasps")
FOLDER = "sounds/audience/{}.wav"
SECONDS = 4                      # a made sound's length: the engine's least
STEP = "Audience · {}"
CUT = "Cut · {} reaction{}"
WRITTEN = "sequence.written"     # the core event the sequence module tells Edit Video's windows from
NONE = "Audience: no {} sound: none kept as audience in Sounds, and no sound model in the catalog"
LACKS = "Audience: no {} sound: none kept as audience in Sounds, and {} lacks {}"
DEFAULT = {"level": 1.0, "fade_in": 0, "fade_out": 0, "duck": False}   # a track-2 item's keys left out
REACTION = "shot {}: reaction is applause, laughter or gasps, or left out"
EMPTY = ("", "none")             # a reaction's empty values: no reaction, as if left out
LABELS = ("subject_definitions", "summary", "retention_analysis", "detailed_description", "overall_soundscape",
          "non_diegetic_music")         # the engine's six fields, `N/A` when empty (R22 §A.2-A.3)


def prompt(kind: str) -> str:
    """The sound's own prompt: the engine's six labels, one a line (upstream `dialogue.py:175-202`),
    `overall_soundscape` the kind as the scene names it, every other field `N/A`; nothing of the Hub's."""
    return "\n".join(f"{label}:\n{kind if label == 'overall_soundscape' else 'N/A'}" for label in LABELS)


def reactions(raw: Any) -> list[str]:
    """On the reply before the schema: a shot's empty `reaction` (null, "", "none", any case) removed, as
    if left out; any other value not a kind removed too, with its shot's line (`REACTION`) in place of the schema's."""
    shots = raw.get("shots") if isinstance(raw, dict) else None
    out = []
    for k, shot in enumerate(shots if isinstance(shots, list) else [], 1):
        if not isinstance(shot, dict) or "reaction" not in shot:
            continue
        value = shot["reaction"]
        if value is None or (isinstance(value, str) and value.strip().lower() in EMPTY):
            del shot["reaction"]
        elif value not in KINDS:
            del shot["reaction"]
            out.append(REACTION.format(k))
    return out


def _order(line: str) -> int:
    found = re.match(r"shot (\d+)", line)
    return int(found.group(1)) if found else 0


def refused(lines: list[str]) -> Invalid:
    """One send-back of every fault, the set's first, then by shot, all of them; its `shown` is the
    card's: the first and how many more."""
    sent = sorted(lines, key=_order)
    err = Invalid("scene", "; ".join(sent))
    err.shown = sent[0] + (f" (+{len(sent) - 1} more)" if len(sent) > 1 else "")   # type: ignore[attr-defined]
    err.count = len(sent)                    # type: ignore[attr-defined]  # the reasons, compared
    return err


def kinds(scene: dict) -> list[str]:
    """The kinds the plan names, in shot order, each once."""
    return list(dict.fromkeys(s["reaction"] for s in scene["shots"] if s.get("reaction")))


def kept(ctx: Ctx, kind: str) -> str | None:
    """The id of `sounds/audience/<kind>.wav` when it is there and reads, else None."""
    item = FOLDER.format(kind)
    return item if ctx.files.sound_facts(item) else None


def resolve(ctx: Ctx, cat: dict, wanted: list[str]) -> tuple[dict[str, str | None], dict | None]:
    """Each kind -> its kept id, or None when it is to be made; and the model that makes them (None when none
    is). A kind neither kept nor makeable fails the scene in one line."""
    found = {kind: kept(ctx, kind) for kind in wanted}
    missing = [kind for kind, item in found.items() if item is None]
    if not missing:
        return found, None
    makers = [m for m in models.present(cat) if m.get("sounds")]
    if makers:
        return found, makers[0]
    partial = next((m for m in cat.get("models", []) if m.get("sounds") and m.get("lacks")), None)
    if partial is not None:
        name = partial.get("name") or partial["id"]
        raise Invalid("audience", LACKS.format(missing[0], name, os.path.basename(str(partial["lacks"][0]))))
    raise Invalid("audience", NONE.format(missing[0]))


def makes(model: dict | None, found: Mapping[str, str | None]) -> list[tuple[str, dict]]:
    """The sound tasks of the kinds to make, in plan order: (kind, request), no seed."""
    return [(kind, request_wire(SoundRequest(model["id"], prompt(kind), None, SECONDS)))
            for kind, item in found.items() if item is None and model is not None]


def lengths(ctx: Ctx, found: Mapping[str, str | None]) -> dict[str, int]:
    """Each kind's length in ms: a kept sound's own, a made one's `SECONDS`."""
    out = {}
    for kind, item in found.items():
        facts = ctx.files.sound_facts(item) if item else None
        out[kind] = int(round(float(facts["seconds"]) * 1000)) if facts else SECONDS * 1000
    return out


def place(scene: dict, frames: list[int], fps: float, sizes: Mapping[str, int],
          settings: Mapping[str, Any]) -> list[tuple[int, str, int, int]]:
    """Each reaction as (its shot k, its kind, at ms, length ms): at the cut after shot k; the last shot's ends
    with the file, never before that shot starts; at most `audience_most_ms`, never past the file's end."""
    most, n = int(settings.get("audience_most_ms") or 4000), len(frames)
    cut = [round(1000 * sum(frames[:k]) / fps) for k in range(n + 1)]
    out = []
    for k, shot in enumerate(scene["shots"], 1):
        if not shot.get("reaction"):
            continue
        length = min(sizes[shot["reaction"]], most)
        at = max(cut[n - 1], cut[n] - length) if k == n else cut[k]
        if cut[n] - at > 0:
            out.append((k, shot["reaction"], at, min(length, cut[n] - at)))
    return out


def level(settings: Mapping[str, Any]) -> dict[str, Any]:
    """The keys of one reaction (level, fades, duck), from the module's settings."""
    return {"level": float(settings.get("audience_level", 0.6)),
            "fade_in": int(settings.get("audience_fade_in_ms", 100)),
            "fade_out": int(settings.get("audience_fade_out_ms", 1000)), "duck": True}


def sounds(ctx: Ctx, placed: list[tuple[int, str, int, int]], found: Mapping[str, str | None]) -> list[JoinSound]:
    """The join's track 2: each reaction ducked at its level and fades; a made sound's path sent empty, filled by
    its task."""
    keys = level(ctx.settings)
    return [JoinSound(str(ctx.files.resolve(found[kind])) if found[kind] else "", at, 0, length, 1000.0, **keys)
            for _, kind, at, length in placed]


def step_names(made: list[str], names: list[str], placed: int) -> list[str]:
    """`Audience · <kind>` for each sound made, the shots' names, then `Cut` or `Cut · n reaction(s)`."""
    return [*(STEP.format(kind) for kind in made), *names, CUT.format(placed, "s" if placed > 1 else "")
            if placed else "Cut"]


class Finish:
    """The scene's last step, whatever the job's end: each made sound filed as
    `audience/<kind>` when that name is free; then the shots made, in shot order, on track 1 of a new Edit Video
    sequence named by the title (the next free `<title> 2`, `<title> 3`), and on track 2 every reaction whose shot
    was made, its keys set (those at their default left out); none made, none written. Then `done`, when given.
    With a `judge` a shot's take is its best (`best_take`, the rule the cut read) and the job's notes get
    the scene's `verdict` and each take's chip (`verdicts`, by item id)."""

    def __init__(self, ctx: Ctx, title: str, last: list[int], placed: list[tuple[int, str, int, int]] | None = None,
                 made: Mapping[str, int] | None = None, found: Mapping[str, str | None] | None = None,
                 done: Callable[..., None] | None = None, judge: Any = None, job: str | None = None) -> None:
        self.ctx, self.title, self.last = ctx, " ".join(title.split()), last
        self.placed, self.made, self.found = placed or [], dict(made or {}), dict(found or {})
        self.done = done                 # the scene's kept plan learns its sequence, clips and sounds
        self.judge, self.job = judge, job   # the scene's judge step and its job's id

    def _takes(self, landed: Mapping[int, str]) -> tuple[list[int | None], list[int] | None]:
        """Each shot's take in the cut (its last task; None: none made) and the takes that ran per shot; the job's
        notes written. No judge: each shot's last task."""
        if self.judge is None:
            return list(self.last), None
        job = self.ctx.jobs.get(self.job) if self.job else None
        seen = {**self.judge.seen, **(job.takes if job is not None else {})}
        plan = JobPlan("image", "", (), {}, takes=self.judge.takes_of)
        chosen = {n: best_take(plan, n, seen, landed) for n in range(1, len(plan.takes) + 1)}
        if self.job is not None:
            verdict, verdicts = self.judge.lines(landed, chosen, seen)
            self.ctx.jobs.note(self.job, verdict=verdict, verdicts=verdicts)
        return list(chosen.values()), [sum(take[0] in seen for take in shot) for shot in plan.takes]

    def _track2(self, shots: int, ids: Mapping[str, str]) -> list[dict]:
        keys = {k: v for k, v in level(self.ctx.settings).items() if v != DEFAULT[k]}
        out = []
        for k, kind, at, length in self.placed:
            facts = self.ctx.files.sound_facts(ids[kind]) if k <= shots and kind in ids else None
            if facts:
                ms = int(round(float(facts["seconds"]) * 1000))
                out.append({"sound": ids[kind], "in": 0, "out": min(length, ms), "at": at, **keys})
        return out

    async def __call__(self, landed: Mapping[int, str]) -> None:
        files = self.ctx.files
        ids = {kind: item for kind, item in self.found.items() if item}
        for kind, task in self.made.items():
            if task in landed:
                ids[kind] = files.file_sound(landed[task], kind)
        made, (order, ran) = [], self._takes(landed)
        for task in order:
            if task is None or task not in landed:
                break
            made.append(landed[task])
        if not made:
            if self.done is not None:
                self.done(None, [], ids, ran)
            return
        taken = {s["name"].casefold() for s in files.sequences()}
        name, n = self.title, 2
        while name.casefold() in taken:
            name, n = f"{self.title} {n}", n + 1
        files.sequence_new(name)
        track2 = self._track2(len(made), ids)
        saved = files.sequence_save(name, [[{"clip": i, "in": 0, "out": None} for i in made], track2], 0,
                                    max(len(made), len(track2)))
        self.ctx.emit(WRITTEN, {"name": saved["name"], "revision": saved["revision"]})
        if self.done is not None:
            self.done(saved["name"], made, ids, ran)
