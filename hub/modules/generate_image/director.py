"""The Director engine: one request in Open WebUI becomes a rendered clip that the Hub plans itself.

`direct_clip {request}` (tools.py) submits `{"direct": request}`; `build.image_job` sends those params here (`job`): a
job with no task yet whose `prepare` is its first step, run by the core before the engine starts (`Planner`). It asks
the model named in Settings -> Assistant (the assistant module's "ask" service) for one shot as JSON, a refused reply
sent back once, each ask carrying `PLAN` for the backend to hold the reply to. A reply
is read leniently (`read`: a <think> block and code fences dropped, the first balanced {...} that parses) and checked
strictly: the shot's schema, then `set_generate_image_settings {shot}` exactly (`tools.write_settings`: casting,
`shotcheck.prepare`, cuts on the engine's plan). A refusal goes back with its line; the model's words are never edited.
Accepted, the press is built as the Generate button sends it (`press_params`, `build.image_job`) and asked of the engine
(`build.preflight`); that plan becomes the job. A refusal of the press or the engine fails the job at once: the model
cannot fix it. The messages live in this module's memory only for the job's planning: nothing of the request, the
replies or the shot is written.
"""
from __future__ import annotations

import copy
import json
import math
import re
from collections.abc import Callable
from typing import Any

from hub.core.api import Ctx, Invalid, JobPlan, schema_check, turns

from . import build, cast, models, pace, presstakes, routes, screen, shotcheck, tools

ASKING = "Planning · ask {} · {}"
FIXING = "Planning · fixing: {} · ask {} · {}"
REFUSED = "Planning: refused {} times; last: {}"
SEND_BACK = "The Hub refused that shot: {}. Send the whole shot again as one JSON object, changed only where needed."
NO_JSON = "The reply holds no JSON object"
REQUEST = "The request is text, not blank"
USER = "Shot plan: {}"           # not "Clip:": the Open WebUI block's hand-over does not fire on it
MESSAGE = (
    "You plan one shot of a video for the Hub. Reply with one JSON object and nothing else: no prose, no code fence.\n"
    "It follows this JSON Schema: {schema}\n"
    "Characters (use these exact names for them): {characters}.\n"
    "subjects: everyone seen. lines: the spoken words only, each with its speaker, a subject's name. If the request "
    "gives no words, write no line. One speaker per shot; put all spoken words in one "
    "line: at most {words} words and {stops} of . ! ? ; : (another line costs {turn} words, another mark {mark}). If "
    "the request gives the words, use them as written, whole sentences in its order, and keep the first ones that "
    "fit. seconds: how long the whole shot runs, the action and the lines, at most {top:.1f}; give the action the "
    "time it takes; if the request names a length, use it.\n"
    "Spoken words go in lines only. The room's sound is the Hub's; you write no sound but music, and music only if "
    "asked. One clear action per beat; the camera as a framing and one move. language: only a language the request "
    "names.")
PLAN = copy.deepcopy({**shotcheck.SCHEMA, "required": [*shotcheck.SCHEMA["required"], "seconds"]})  # a length
PLAN["properties"]["sound"]["properties"].pop("ambience")     # the room's sound is the place's
_THINK = re.compile(r"</think\s*>", re.IGNORECASE)
_FENCE = re.compile(r"^\s*```[\w-]*\s*$", re.MULTILINE)


def job(p: dict, ctx: Ctx) -> JobPlan:
    """The job of one request: on the pulldown's model, a video model, with a Generate window open; its plan is built
    when it starts (`Planner`)."""
    request = p.get("direct")
    if not isinstance(request, str) or not request.strip():
        raise Invalid("request", REQUEST)
    model = video_model(ctx, models.cached())
    label = models.ui_model(model, models.ref_caps(ctx))["label"]
    return JobPlan("image", model["id"], (), {"kind": "clip", "model": label, "model_id": model["id"],
                                              "prompt": request, "seeds": []}, prepare=Planner(ctx, request))


def video_model(ctx: Ctx, cat: Any) -> dict:
    """The pulldown's model when it makes clips and a Generate window is open; else the screen's one line."""
    model = screen.pick_model(cat, screen.read(ctx))
    ui = models.ui_model(model, models.ref_caps(ctx))
    if ui["kind"] != "video":
        raise Invalid("model", shotcheck.NOT_CLIP.format(ui["label"]))
    screen._draft(ctx, "")                                # "No Generate window is open": the panel shows the draft
    return model


def messages(ctx: Ctx, model: dict, request: str) -> list[dict]:
    """The system message (the rules, the schema, the characters, the budget: `shotcheck.budget` on the boxes as they
    are), then `Shot plan: <request>`."""
    named = "; ".join(c["name"] + (", has a voice sample" if c.get("sample") else "") for c in cast.listing(ctx))
    where = shotcheck.frame(ctx, model, models.ui_model(model, models.ref_caps(ctx))["label"])
    words, stops = shotcheck.budget(ctx, model, where)
    rate = pace.current(ctx) or pace.ENGINE
    mark = math.ceil(turns.STOP_SECONDS * rate - 1e-9)
    system = MESSAGE.format(schema=json.dumps(PLAN, separators=(",", ":")), characters=named or "none",
                            words=words, stops=stops, turn=math.ceil(turns.TURN_SECONDS * rate - 1e-9),
                            mark=f"{mark} word" + ("s" if mark > 1 else ""), top=shotcheck.top(ctx, model, where))
    return [{"role": "system", "content": system}, {"role": "user", "content": USER.format(request)}]


def _close(text: str, start: int) -> int | None:
    """The index of the `}` that closes the `{` at `start`, strings skipped; None when it never closes."""
    depth, quoted, escaped = 0, False, False
    for i in range(start, len(text)):
        c = text[i]
        if quoted:
            if escaped:
                escaped = False
            elif c == "\\":
                escaped = True
            elif c == '"':
                quoted = False
            continue
        if c == '"':
            quoted = True
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i
    return None


def read(reply: str) -> dict | None:
    """The shot in a reply: everything up to a closing </think> and every code-fence line dropped, then the first
    balanced {...} that parses as an object; None when there is none."""
    text = _FENCE.sub("", _THINK.split(reply)[-1])
    at = text.find("{")
    while at != -1:
        end = _close(text, at)
        if end is None:
            return None
        try:
            found = json.loads(text[at:end + 1])
        except ValueError:
            found = None
        if isinstance(found, dict):
            return found
        at = text.find("{", end + 1)
    return None


class Planner:
    """A job's planning step (`JobPlan.prepare`). `job` is the job's id, set by whoever submitted it, at once
    (`tools.direct_clip`): the engine's plan and the takes' verdicts go on its notes."""

    def __init__(self, ctx: Ctx, request: str) -> None:
        self.ctx, self.request = ctx, request
        self.job: str | None = None

    async def __call__(self, say: Callable[[str], None]) -> JobPlan:
        ctx = self.ctx
        ask = ctx.service("ask")
        name, _ = await ask([])                            # which model answers; no model set: its one line
        cat = await tools._catalog(ctx)
        sent = messages(ctx, video_model(ctx, cat), self.request)
        line, n = "", 0
        while True:                                        # a one-line refusal is sent back once
            n += 1
            say(ASKING.format(n, name) if n == 1 else FIXING.format(line, n, name))
            _, reply = await ask(sent, PLAN)                # the schema held by the backend too
            video_model(ctx, cat)                       # the pulldown or the window changed: nothing the model fixes
            try:
                await self.accept(reply)
            except Invalid as err:
                line = err.text
                if n > 1:
                    raise Invalid("shot", REFUSED.format(n, line)) from None
                sent = [*sent, {"role": "assistant", "content": reply}, {"role": "user",
                                                                       "content": SEND_BACK.format(line)}]
                continue
            return await self.press(await tools._catalog(ctx))

    async def accept(self, reply: str) -> None:
        """The reply's shot set on the screen as `set_generate_image_settings {shot}` sets it; else the shot check's
        one line sent back. No word of the plan is refused: the prompt is the Hub's text."""
        shot = read(reply)
        if shot is None:
            raise Invalid("shot", NO_JSON)
        await tools.write_settings(self.ctx, {"shot": schema_check(PLAN, shot)})

    async def press(self, cat: dict) -> JobPlan:
        """The press of the accepted shot, as the Generate button sends it, with its takes (
        `presstakes.plan`), asked of the engine as a queued press is (`build.preflight`); its refusals fail the job.
        -> the job's plan."""
        ctx = self.ctx
        params = tools.press_params(ctx, cat, screen.draft(ctx))
        plan = presstakes.plan(ctx, build.image_job(params, ctx))
        if isinstance(plan.finish, presstakes.Finish):
            plan.finish.job = self.job
        planned, line = await build.preflight(ctx, plan)
        if planned is not None and self.job is not None:
            ctx.jobs.note(self.job, plan=planned)
        if line:
            raise Invalid("plan", line)
        seeds: list[Any] = list(plan.summary.get("seeds") or [])
        routes.session_part(ctx)["last_seeds"] = {"model": plan.summary["model_id"], "seeds": seeds}
        return plan
