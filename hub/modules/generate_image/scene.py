"""The 30 s scene: one request in Open WebUI becomes several shots, rendered in order and cut together, as
one job the Hub plans itself.

`direct_scene {request}` (tools.py) submits `{"scene": request}`; `build.image_job` sends those params here (`job`): a
job with no task yet whose `prepare` is its first step (`ScenePlanner`). It asks the model in Settings -> Assistant for
the whole scene as one JSON object (`SCHEMA`: a title, the cast, the set, the shots), while the model mends (a
refusal with fewer faults than the one before is sent back), each carrying `SCHEMA` for the backend to hold
the reply to, read as the Director reads a shot (`director.read`). Checked: the schema, the scene's own rules
(`rules`), then each shot merged with the cast's looks and the set (`shots`) exactly as one shot is checked
(`tools.write_settings {shot}`), in shot order, within its own boxes (`shotcheck.only`: the boxes of its subjects plus
the ones filled before the scene). A refusal goes back whole with its shot named; the model's words are never
edited. Accepted, each shot is written again and pressed as the Generate button sends it, then asked of the engine
(`build.preflight`); the job is every shot's tasks in order, then one join task reading each shot's last file as "kept"
(it lands in Clips as it is made). Its last step (`finish`, any end) writes the shots made, in order, to an Edit Video
sequence named by the title. A shot may name the room's `reaction` (`audience`): its sound goes under the cut,
made first when Sounds holds none of its kind. Nothing of the request, the replies or the plan is written; the plan is
kept in memory for a redo of one shot (`redo`).
"""
from __future__ import annotations

import copy
import json
import math
from collections.abc import Callable
from typing import Any

from hub.core.api import Canvas, Ctx, Duck, Invalid, JobPlan, JoinItem, JoinRequest, request_wire, schema_check, turns

from . import audience, build, cast, director, judgeshot, models, pace, redo, screen, shotcheck, tools, voiced

JOIN = (18, "medium")            # the join's crf and preset: the sequence module's defaults (`settings.py`)
ASKING = "Planning scene · ask {} · {}"
FIXING = "Planning scene · fixing: {} · ask {} · {}"
SEND_BACK = ("The Hub refused that scene: {}. Send the whole scene again as one JSON object, changed only where "
             "needed.")
USER = "Scene plan: {}"          # not "Scene:": the Open WebUI block's hand-over does not fire on it
NOT_LISTED = "{} is not in Characters"
NONE_OF_CAST = "shot {} shows none of the cast"
NOT_CAST = "shot {}: {} is not in the cast"
TWO = "shot {} has two speakers; one speaker per shot"
PLAIN = "title is the sequence's name: plain words, without slashes"
MESSAGE = (
    "You plan a scene of shots of a video for the Hub, cut together in order. Reply with one JSON object and "
    "nothing else: no prose, no code fence.\n"
    "It follows this JSON Schema: {schema}\n"
    "Characters (use these exact names for them): {characters}.\n"
    "cast: everyone seen in the scene, at most {boxes}, with how each looks where the request says; set: the place, "
    "the light and the room's sound as the request describes them, the same for every shot. Each shot: subjects "
    "from the cast only, at least one; one speaker at most, all the speaker's spoken words in one line: at most "
    "{words} words and {stops} of . ! ? ; : (another mark {mark}). The other person's answer is the next shot, "
    "framed on them. If the request gives the words, use them as written, whole sentences in its order, split "
    "across shots at sentence ends. seconds: how long the shot runs, the action and the line, at most {top:.1f}; "
    "the shots together run as long as the request asks. Each shot begins where the one before ended.\n"
    "Spoken words go in lines only. ambience names the room only. reaction: what the audience does at the end of "
    "that shot (applause, laughter or gasps), on the shots where the room reacts; leave it out elsewhere. One clear "
    "action per beat; the camera as a framing and one move. language: only a language the request names.")


def _shot_schema() -> dict:
    """The Director's shot (`director.PLAN`, `seconds` required) without the set's fields and the cuts; a subject is a
    name from the cast, its look the cast's."""
    shot = copy.deepcopy(director.PLAN)
    for name in ("where", "light", "sound", "cuts"):
        shot["properties"].pop(name)
    shot["required"] = [r for r in shot["required"] if r in shot["properties"]]
    shot["properties"]["subjects"]["items"]["properties"].pop("look")
    shot["properties"]["reaction"] = {"enum": list(audience.KINDS)}    # the scene's, not the shot's
    return shot


_text, _object = shotcheck._text, shotcheck._object
SCHEMA = _object(
    ["title", "cast", "set", "shots"], title=_text(1),
    cast={"type": "array", "minItems": 1, "maxItems": cast.BOXES,
          "items": _object(["name"], name=_text(1), look=_text())},
    set=_object(["where"], where=_text(1), light=_text(), ambience=_text()),
    shots={"type": "array", "minItems": 1, "items": _shot_schema()})


def _key(name: Any) -> str:
    return " ".join(str(name or "").split()).lower()


def job(p: dict, ctx: Ctx) -> JobPlan:
    """The job of one scene request: on the pulldown's model, a video model, with a Generate window open (the same
    refusals as `director.job`); its plan is built when it starts (`ScenePlanner`)."""
    request = p.get("scene")
    if not isinstance(request, str) or not request.strip():
        raise Invalid("request", director.REQUEST)
    model = director.video_model(ctx, models.cached())
    label = models.ui_model(model, models.ref_caps(ctx))["label"]
    return JobPlan("image", model["id"], (), {"kind": "clip", "mode": "scene", "model": label,
                                              "model_id": model["id"], "prompt": request, "seeds": []},
                   prepare=ScenePlanner(ctx, request))


def messages(ctx: Ctx, model: dict, request: str) -> list[dict]:
    """The system message (the rules, the schema, the characters, one shot's budget on the boxes as they are), then
    `Scene plan: <request>`."""
    named = "; ".join(c["name"] + (", has a voice sample" if c.get("sample") else "") for c in cast.listing(ctx))
    where = shotcheck.frame(ctx, model, models.ui_model(model, models.ref_caps(ctx))["label"])
    words, stops = shotcheck.budget(ctx, model, where)
    mark = math.ceil(turns.STOP_SECONDS * (pace.current(ctx) or pace.ENGINE) - 1e-9)
    system = MESSAGE.format(schema=json.dumps(SCHEMA, separators=(",", ":")),
                            characters=named or "none", boxes=cast.BOXES, words=words, stops=stops,
                            mark=f"{mark} word" + ("s" if mark > 1 else ""), top=shotcheck.top(ctx, model, where))
    return [{"role": "system", "content": system}, {"role": "user", "content": USER.format(request)}]


def rules(ctx: Ctx, scene: dict) -> None:
    """The scene's rules: a title Edit Video can name a sequence by; every cast member a listed character; every shot
    shows the cast only, at least one, and has one speaker at most."""
    title = scene["title"].strip()
    if not title or title.startswith(".") or "/" in title or "\\" in title:
        raise Invalid("scene", PLAIN)
    listed = voiced.characters(ctx)
    for c in scene["cast"]:
        if _key(c["name"]) not in listed:
            raise Invalid("scene", NOT_LISTED.format(" ".join(c["name"].split())))
    names = {_key(c["name"]) for c in scene["cast"]}
    for k, shot in enumerate(scene["shots"], 1):
        if not any(_key(s["name"]) in names for s in shot["subjects"]):
            raise Invalid("scene", NONE_OF_CAST.format(k))
        for s in shot["subjects"]:
            if _key(s["name"]) not in names:
                raise Invalid("scene", NOT_CAST.format(k, " ".join(s["name"].split())))
        if len({_key(line["speaker"]) for line in shot.get("lines") or []}) > 1:
            raise Invalid("scene", TWO.format(k))


def shots(scene: dict) -> list[dict]:
    """Each shot as one shot is checked: each subject's look from the cast by name, the set's `where`, `light` and
    `ambience` (as `sound.ambience`), word for word; a shot's `reaction` left out."""
    looks = {_key(c["name"]): c.get("look") for c in scene["cast"]}
    room = scene["set"]
    out = []
    for shot in scene["shots"]:
        merged = {**{k: v for k, v in shot.items() if k != "reaction"},
                  "subjects": [{**s, **({"look": looks[_key(s["name"])]} if looks.get(_key(s["name"])) else {})}
                               for s in shot["subjects"]], "where": room["where"]}
        if room.get("light"):
            merged["light"] = room["light"]
        if room.get("ambience"):
            merged["sound"] = {"ambience": room["ambience"]}
        out.append(merged)
    return out


def step_name(k: int, shot: dict, seconds: float) -> str:
    """`Shot 1 · Speaker 1 · 6.2 s`: the speaker, else the first subject."""
    lines = shot.get("lines") or []
    who = lines[0]["speaker"] if lines else shot["subjects"][0]["name"]
    return f"Shot {k} · {' '.join(who.split())} · {seconds:.1f} s"


class ScenePlanner:
    """A scene job's planning step (`JobPlan.prepare`). `job` is the job's id, set by `tools.direct_scene` at once."""

    def __init__(self, ctx: Ctx, request: str) -> None:
        self.ctx, self.request = ctx, request
        self.job: str | None = None
        self.own: list[str] = []             # the boxes filled before the scene: they go with every shot

    async def __call__(self, say: Callable[[str], None]) -> JobPlan:
        ctx = self.ctx
        ask = ctx.service("ask")
        name, _ = await ask([])                            # which model answers; no model set: its one line
        cat = await tools._catalog(ctx)
        model = director.video_model(ctx, cat)
        self.own = [r["id"] for r in screen.references(ctx)]
        sent = messages(ctx, model, self.request)
        line = shown = ""
        n, before = 0, None
        while True:                                        # sent back while the faults fall
            n += 1
            say(ASKING.format(n, name) if n == 1 else FIXING.format(shown, n, name))
            _, reply = await ask(sent, SCHEMA)              # the schema held by the backend too
            director.video_model(ctx, cat)              # the pulldown or the window changed: nothing the model fixes
            try:
                scene = await self.accept(reply, model)
            except Invalid as err:
                line, shown, count = err.text, getattr(err, "shown", err.text), getattr(err, "count", 1)
                if before is not None and count >= before:
                    raise Invalid("scene", director.REFUSED.format(n, line)) from None
                before = count
                sent = [*sent, {"role": "assistant", "content": reply}, {"role": "user",
                                                                       "content": SEND_BACK.format(line)}]
                continue
            return await self.plan(scene, model)

    def boxes(self, shot: dict) -> list[str]:
        """The ids of the boxes a shot sends: those filled before, then each of its subjects' pictures (box order is the
        session's, `shotcheck.used`)."""
        listed = voiced.characters(self.ctx)
        return [*self.own, *(listed[_key(s["name"])]["id"] for s in shot["subjects"] if _key(s["name"]) in listed)]

    async def write(self, k: int, shot: dict, model: dict) -> int:
        """Shot k set on the screen within its own boxes, as `set_generate_image_settings {shot}` sets it; -> its
        planned frames. A refusal: `shot k: <line>`."""
        try:
            with shotcheck.only(self.boxes(shot)):
                await tools.write_settings(self.ctx, {"shot": shot})
        except Invalid as err:
            raise Invalid("scene", f"shot {k}: {err.text}") from None
        return int(screen.clip_frames(screen.read(self.ctx), model) or 0)

    async def accept(self, reply: str, model: dict) -> dict:
        """The reply's scene, checked: each shot's reaction, the schema, the rules, the whole cast cast
        into empty boxes at once (no word check), every merged shot in order, then the scene's
        length; else one send-back of every fault found (`audience.refused`)."""
        scene = director.read(reply)
        if scene is None:
            raise Invalid("scene", director.NO_JSON)
        lines = audience.reactions(scene)
        try:
            scene = schema_check(SCHEMA, scene)
            rules(self.ctx, scene)
            voiced.cast_named(self.ctx, {"subjects": [{"name": c["name"]} for c in scene["cast"]]}, model)
        except Invalid as err:
            raise audience.refused([*lines, err.text]) if lines else err from None
        merged = shots(scene)
        for k, shot in enumerate(merged, 1):
            try:
                await self.write(k, shot, model)
            except Invalid as err:
                lines.append(err.text)
        if lines:
            raise audience.refused(lines)
        return scene

    async def plan(self, scene: dict, model: dict) -> JobPlan:
        """Per shot, its write, its press within its boxes (`press_params`, `build.image_job`) and the engine's
        plan of it (`build.preflight`, its refusal: `shot k: <line>`); then the cut. The sounds to make go
        first, the reactions under the cut; each shot's tasks once per take, the cut its best. -> the job."""
        ctx, clip = self.ctx, models.video(model) or {}
        found, maker = audience.resolve(ctx, await tools._catalog(ctx), audience.kinds(scene))   # fails here
        makes = audience.makes(maker, found)
        tasks, inputs = [task for _, task in makes], [{} for _ in makes]
        names, items, planned, seeds, kept, takes_of = [], [], [], [], [], []
        n = max(1, int(ctx.settings.get("scene_takes_max") or 1))
        for k, shot in enumerate(shots(scene), 1):
            frames = await self.write(k, shot, model)
            try:
                with shotcheck.only(self.boxes(shot)):
                    params = tools.press_params(ctx, await tools._catalog(ctx), screen.draft(ctx))
                    plan = build.image_job(params, ctx)
                    notes, line = await build.preflight(ctx, plan)
            except Invalid as err:
                raise Invalid("plan", f"shot {k}: {err.text}") from None
            planned.append(notes)
            if line:
                raise Invalid("plan", f"shot {k}: {line}")
            own = [step_name(k, shot, frames / float(clip["fps"]))] + [f"Shot {k} · voice"] * (len(plan.tasks) - 1)
            mine = redo.heard(ctx, plan.tasks, shot)                     # the shot's words, for the words judge
            takes_of.append(tuple(tuple(range(len(tasks) + 1 + t * len(mine), len(tasks) + 1 + (t + 1) * len(mine)))
                                  for t in range(n)))
            for t in range(n):                                          # take t + 1 on the seed + t
                inputs += redo._shift(plan.inputs or tuple({} for _ in plan.tasks), len(tasks))
                tasks += redo.seeded(mine, t)
                names += own if not t else [f"{x}{redo.TAKE.format(t + 1)}" for x in own]
                seeds += [int(x) + t for x in plan.summary.get("seeds") or []]
            items.append(JoinItem("", 0, frames, float(clip["fps"]), int(plan.summary["width"]),
                                  int(plan.summary["height"]), frames, bool(clip.get("soundtrack"))))
            kept.append(redo.Shot(copy.deepcopy(mine), plan.inputs or tuple({} for _ in plan.tasks), own, items[-1],
                                  shot=shot))
        if self.job is not None:
            ctx.jobs.note(self.job, plans=planned)
        first, made, last = items[0], {kind: j for j, (kind, _) in enumerate(makes, 1)}, [t[0][-1] for t in takes_of]
        placed = audience.place(scene, [i.frames for i in items], first.fps, audience.lengths(ctx, found),
                                ctx.settings)
        cut = JoinRequest(items, Canvas(first.w, first.h, first.fps), audience.sounds(ctx, placed, found), JOIN[0],
                          JOIN[1], "mp4", Duck())
        inputs.append({**{f"items.{i}.path": (j, "best" if n > 1 else "kept") for i, j in enumerate(last)},
                       **{f"audio.{i}.path": (made[kind], "kept") for i, (_, kind, _, _) in enumerate(placed)
                          if kind in made}})
        total = sum(i.frames for i in items)
        summary = {"kind": "clip", "mode": "scene", "model": plan.summary["model"], "model_id": model["id"],
                   "prompt": self.request, "width": first.w, "height": first.h, "count": 1,
                   "frames": total, "seconds": round(total / first.fps, 2),
                   "seeds": seeds, "loras": plan.summary.get("loras") or [], "shots": len(items),
                   "step_names": audience.step_names(list(made), names, len(placed))}
        record = redo.keep(redo.Scene(" ".join(scene["title"].split()), model["id"], plan.summary["model"], kept, cut,
                                      placed, list(summary["loras"])))           # memory only
        judge = judgeshot.ShotJudge(ctx, [s.shot for s in kept], tuple(takes_of),
                                    60 * float(ctx.settings.get("scene_retake_minutes") or 0))
        return JobPlan("image", model["id"], (*tasks, request_wire(cut)), summary, inputs=tuple(inputs),
                       takes=tuple(takes_of), judge=judge,
                       finish=audience.Finish(ctx, scene["title"], last, placed, made, found, record.landed,
                                              judge=judge, job=self.job))
