"""Redo one shot of a scene: the same shot plan rendered again on a new seed, then the cut and the scene's
Edit Video sequence rebuilt with it, as one job.

A scene's plan is kept here, in the controller's memory only (`SCENES`, at most `KEPT` scenes, the oldest dropped),
from its planning (`keep`, called by `scene.ScenePlanner.plan`) until the Hub stops; its job's last step completes it
(`Scene.landed`, called by `audience.Finish`): the sequence's name, each shot's clip, the sounds' ids. Nothing of it
is ever written (`CLAUDE.md`), so a scene made before the Hub last started cannot be redone.

`redo_shot {shot, scene?}` (tools.py) submits `{"redo": {...}}`; `build.image_job` sends those params here (`job`).
Its planning step (`RedoPlanner`) refuses in one line what it cannot do (`check`), else sends shot k's kept tasks (and
every shot never made) on the kept seed + its takes so far, asked of the engine again (`build.preflight`), then the
scene's cut with every kept shot's file and each redone shot's last task as "kept". Its last step
(`RedoFinish`) puts the new take where the old one was in the scene's sequence, its in/out kept. Nothing is
re-planned, re-written or re-pressed: the Generate screen is not touched.
"""
from __future__ import annotations

import copy
from collections import OrderedDict
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from typing import Any

from hub.core.api import Ctx, Invalid, JobPlan, JoinItem, JoinRequest, request_wire

from . import audience, build, director, judgeshot, screen, tools

KEPT = 8                         # scenes held at once: it bounds the memory a run of the Hub keeps
SAY = "Redo · shot {} of {}"
PROMPT = "Redo shot {} of {}"
TAKE = " · take {}"
LAST = "the last scene"
BEFORE = ("{} was made before the Hub last started; a scene's plan is held in memory only. Send the scene again.")
NO_SCENE = "No scene was made since the Hub last started."
RUNNING = "{} is still being made"
SHOTS = "{} has {} shots"
NO_SEQUENCE = "{}'s sequence is no longer on Edit Video"
NOTHING = "No shot of {} was made; send the scene again"
OTHER = "{} was made on {}; pick it in Generate to redo its shot"
CLIP_GONE = "shot {} of {} is no longer in Clips; redo it too"
SOUND_GONE = "Audience: the {} sound of {} is no longer in Sounds; send the scene again"
ARGS = "Name a shot by its number"


def _key(name: Any) -> str:
    return " ".join(str(name or "").split()).casefold()


@dataclass
class Shot:
    """One shot as planned: its tasks (wire requests, `inputs` local to it), its step names, its join item (path
    empty), the shot as checked (its lines and framing, for the judges); once made, its clip and how many
    takes of it ran (a redo's seed is the kept seed + these)."""
    tasks: tuple[dict, ...]
    inputs: tuple[Mapping[str, tuple[int, str]], ...]
    names: list[str]
    item: JoinItem
    clip: str | None = None
    takes: int = 0
    shot: dict = field(default_factory=dict)


@dataclass
class Scene:
    """A scene's plan, kept in memory."""
    title: str
    model: str                   # the model id the scene rendered on
    label: str
    shots: list[Shot]
    cut: JoinRequest             # the scene's join as planned (made sounds' paths empty)
    placed: list[tuple[int, str, int, int]]
    loras: list = field(default_factory=list)
    sounds: dict[str, str] = field(default_factory=dict)
    name: str | None = None      # the sequence's saved name
    ended: bool = False

    @property
    def shown(self) -> str:
        return self.name or self.title

    def landed(self, name: str | None, made: list[str], sounds: Mapping[str, str],
               ran: list[int] | None = None) -> None:
        """The scene's job ended (`audience.Finish`, any end): its sequence, the shots made in order (each its take in
        the cut), the sounds, and the takes that ran per shot (none given: one)."""
        self.name, self.sounds, self.ended = name, dict(sounds), True
        for i, shot in enumerate(self.shots):
            clip, count = made[i] if i < len(made) else None, ran[i] if ran and i < len(ran) else 0
            shot.clip, shot.takes = (clip, max(1, count)) if clip else (None, count)


def heard(ctx: Ctx, tasks: tuple[dict, ...], shot: dict) -> tuple[dict, ...]:
    """A shot's tasks, its clip task given the shot's spoken words (its lines in order, by a space; none: None) for
    the words judge when `clip_judge` is on."""
    said = " ".join(" ".join(str(x.get("words") or "").split()) for x in shot.get("lines") or []).strip() or None
    on = bool(ctx.settings.get("clip_judge", True))
    return tuple({**copy.deepcopy(t), "words": said} if t.get("kind") == "video" and on else copy.deepcopy(t)
                 for t in tasks)


def seeded(tasks: tuple[dict, ...], more: int) -> tuple[dict, ...]:
    """A shot's tasks with its clip's seed + `more`; a spoken line's too. A task
    sent with no seed stays without one: each take is the engine's own run."""
    return tuple({**copy.deepcopy(t), "seed": int(t["seed"]) + more}
                 if t.get("kind") in ("video", "speech") and t.get("seed") is not None
                 else copy.deepcopy(t) for t in tasks)


SCENES: OrderedDict[int, Scene] = OrderedDict()
_count = [0]


def keep(record: Scene) -> Scene:
    """A scene just planned, as the newest; the ninth drops the oldest."""
    _count[0] += 1
    SCENES[_count[0]] = record
    while len(SCENES) > KEPT:
        SCENES.popitem(last=False)
    return record


def find(scene: str | None) -> Scene:
    """The scene named by its sequence's name or its title (any case), the newest first; none named: the newest."""
    if scene is None:
        if not SCENES:
            raise Invalid("redo", NO_SCENE)
        return next(reversed(SCENES.values()))
    key = _key(scene)
    for match in (lambda r: r.name and _key(r.name) == key, lambda r: _key(r.title) == key):
        for record in reversed(SCENES.values()):
            if match(record):
                return record
    raise Invalid("redo", BEFORE.format(" ".join(scene.split())))


def job(p: dict, ctx: Ctx) -> JobPlan:
    """The job of `Redo shot k [of <title>]`: no task yet; its plan is built when it starts (`RedoPlanner`), where
    whatever cannot be redone fails on the card in one line."""
    args = p.get("redo") if isinstance(p.get("redo"), dict) else {}
    k, scene = args.get("shot"), args.get("scene")
    if isinstance(k, bool) or not isinstance(k, int) or k < 1:
        raise Invalid("shot", ARGS)
    if scene is not None and (not isinstance(scene, str) or not scene.strip()):
        scene = None
    try:
        record, line = find(scene), None
    except Invalid as err:
        record, line = None, err.text
    model = record.model if record else str(screen.read(ctx).get("model") or "")
    shown = record.shown if record else " ".join(scene.split()) if scene else LAST
    return JobPlan("image", model, (), {"kind": "clip", "mode": "scene", "model": record.label if record else "",
                                        "model_id": model, "prompt": PROMPT.format(k, shown), "seeds": []},
                   prepare=RedoPlanner(ctx, k, record, line or ""))


def _shift(wants: tuple[Mapping[str, tuple[int, str]], ...], before: int) -> list[dict]:
    return [{name: (j + before, kind) for name, (j, kind) in w.items()} for w in wants]


class RedoPlanner:
    """A redo job's planning step (`JobPlan.prepare`). `job` is the job's id, set by `tools.redo_shot` at once."""

    def __init__(self, ctx: Ctx, k: int, record: Scene | None, line: str) -> None:
        self.ctx, self.k, self.record, self.line = ctx, k, record, line
        self.job: str | None = None

    def check(self, record: Scene) -> list[int]:
        """The refusals that need no engine; -> the shots to render (0-based): shot k and every shot never made."""
        files, title, n = self.ctx.files, record.shown, len(record.shots)
        if not record.ended:
            raise Invalid("redo", RUNNING.format(title))
        if not 1 <= self.k <= n:
            raise Invalid("redo", SHOTS.format(title, n))
        if not any(s.clip for s in record.shots):
            raise Invalid("redo", NOTHING.format(title))
        if record.name not in {s["name"] for s in files.sequences()}:
            raise Invalid("redo", NO_SEQUENCE.format(title))
        redone = [i for i, s in enumerate(record.shots) if i == self.k - 1 or s.clip is None]
        for i, s in enumerate(record.shots):
            if i not in redone and files.clip_facts(s.clip) is None:
                raise Invalid("redo", CLIP_GONE.format(i + 1, title))
        for _, kind, _, _ in record.placed:
            if not record.sounds.get(kind) or files.sound_facts(record.sounds[kind]) is None:
                raise Invalid("redo", SOUND_GONE.format(kind, title))
        return redone

    async def __call__(self, say: Callable[[str], None]) -> JobPlan:
        ctx, record = self.ctx, self.record
        say(SAY.format(self.k, record.shown if record else LAST))
        if record is None:
            raise Invalid("redo", self.line)
        redone = self.check(record)
        cat = await tools._catalog(ctx)
        if screen.pick_model(cat, screen.read(ctx))["id"] != record.model:
            raise Invalid("redo", OTHER.format(record.shown, record.label))
        director.video_model(ctx, cat)                         # a video model with a Generate window: its line
        tasks: list[dict] = []
        inputs: list[dict] = []
        names: list[str] = []
        seeds: list[int] = []
        last: dict[int, int] = {}
        planned, takes = [], []
        for i in redone:
            shot = record.shots[i]
            mine = seeded(shot.tasks, shot.takes)
            notes, line = await build.preflight(ctx, JobPlan("image", record.model, mine, {"kind": "clip"},
                                                             inputs=shot.inputs))
            planned.append(notes)
            if line:
                raise Invalid("plan", f"shot {i + 1}: {line}")
            inputs += _shift(shot.inputs or tuple({} for _ in mine), len(tasks))
            takes.append((tuple(range(len(tasks) + 1, len(tasks) + 1 + len(mine))),))
            tasks += mine
            last[i] = len(tasks)
            names += [shot.names[0] + (TAKE.format(shot.takes + 1) if shot.takes else ""), *shot.names[1:]]
            seeds += [t["seed"] for t in mine if t.get("kind") == "video"]
        if self.job is not None:
            ctx.jobs.note(self.job, plans=planned)
        items = [s.item if i in last else replace(s.item, path=str(ctx.files.resolve(s.clip)))
                 for i, s in enumerate(record.shots)]
        cut = replace(record.cut, items=items, audio=audience.sounds(ctx, record.placed, record.sounds))
        inputs.append({f"items.{i}.path": (j, "kept") for i, j in last.items()})
        canvas, total = record.cut.canvas, sum(i.frames for i in items)
        summary = {"kind": "clip", "mode": "scene", "model": record.label, "model_id": record.model,
                   "prompt": PROMPT.format(self.k, record.shown), "width": canvas.w, "height": canvas.h, "count": 1,
                   "frames": total, "seconds": round(total / canvas.fps, 2), "seeds": seeds, "loras": record.loras,
                   "shots": len(items), "step_names": audience.step_names([], names, len(record.placed))}
        judge = judgeshot.ShotJudge(ctx, [record.shots[i].shot for i in redone], tuple(takes), 0, again_ok=False,
                                    numbers=[(i + 1, record.shots[i].takes + 1) for i in redone])  # shot, take numbers
        return JobPlan("image", record.model, (*tasks, request_wire(cut)), summary, inputs=tuple(inputs),
                       takes=tuple(takes), judge=judge,
                       finish=RedoFinish(ctx, record, last, len(tasks) + 1, judge, self.job))


class RedoFinish:
    """The redo's last step, whatever its end: each redone take that landed counts as a take; when the cut
    landed, the scene's sequence takes the new takes: in track 1 every item of a redone shot's old clip gets the new
    clip, its in/out kept; a shot not in it (never made) goes after the shots before it, whole, and its reaction on
    track 2; every other item as it was; saved as the next revision. A redo that did not cut leaves it as it was."""

    def __init__(self, ctx: Ctx, record: Scene, last: Mapping[int, int], cut: int,
                 judge: judgeshot.ShotJudge | None = None, job: str | None = None) -> None:
        self.ctx, self.record, self.last, self.cut = ctx, record, dict(last), cut
        self.judge, self.job = judge, job

    async def __call__(self, landed: Mapping[int, str]) -> None:
        shots = self.record.shots
        new = {i: landed[t] for i, t in self.last.items() if t in landed}
        if self.judge is not None and self.job is not None:     # each new take's line, whatever it scored
            job = self.ctx.jobs.get(self.job)
            chosen = {n: t for n, t in enumerate(self.last.values(), 1) if t in landed}
            verdict, verdicts = self.judge.lines(landed, chosen, {**self.judge.seen, **(job.takes if job else {})})
            self.ctx.jobs.note(self.job, verdict=verdict, verdicts=verdicts)
        for i in new:
            shots[i].takes += 1
        if self.cut not in landed:
            return
        files, name = self.ctx.files, str(self.record.name)
        seq = files.sequence(name)
        one, two = seq["tracks"]
        old = {shots[i].clip: i for i in new if shots[i].clip}
        one = [{**it, "clip": new[old[it["clip"]]]} if it.get("clip") in old else it for it in one]
        fresh = [i for i in new if new[i] not in {it.get("clip") for it in one}]
        for i in sorted(fresh):
            before = {new.get(j, shots[j].clip) for j in range(i)}
            at = max((p + 1 for p, it in enumerate(one) if it.get("clip") in before), default=0)
            one.insert(at, {"clip": new[i], "in": 0, "out": None})
        unmade = {i + 1 for i in new if shots[i].clip is None}
        two = [*two, *audience.Finish(self.ctx, name, [], [p for p in self.record.placed if p[0] in unmade])
               ._track2(len(shots), self.record.sounds)]
        saved = files.sequence_save(name, [one, two], seq["revision"], max(len(one), len(two)))
        for i, clip in new.items():
            shots[i].clip = clip
        self.ctx.emit(audience.WRITTEN, {"name": saved["name"], "revision": saved["revision"]})

