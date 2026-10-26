"""Every Generate press of a clip or a spoken line judged as it lands, and rendered again under the bar inside its
own job: a scene's takes and judge step, for one shot.

The job kind `image` is `job` here: it builds the press as `build.image_job` does and, for a clip or a line (not a
picture, nor a request the Hub plans itself: `direct`, `scene`, `redo`), returns it with takes (`plan`). The
Director's press (`director.Planner.press`) calls `plan` on its own press. Take 1 is the press's own tasks, the clip's
render given the spoken words for the words judge (`words`); take t a copy on the seed + (t − 1), `inputs` shifted; the
judge is `judgeshot.ShotJudge` on the press's one shot (a clip) or `judgeshot.LineJudge` (a line); the last step
(`Finish`) marks the best take on the job's notes: `verdict`, each take's chip (`verdicts`, by item id, when more than
one take ran), `best` (its item) and `best_task` (its first task, whose reading is `notes.judged`). With the judge off
the plan is the press's own, unchanged. Nothing of it is written: the notes live in memory (`CLAUDE.md`).
"""
from __future__ import annotations

import copy
import re
from collections.abc import Mapping
from dataclasses import replace
from typing import Any

from hub.core.api import Ctx, JobPlan, Take, best_take

from . import build, judgeshot, redo, routes

STEPS = {"clip": "Render", "sound": "Line"}
CHIP = "Take {} of {} · {}"
BEST = "Take {} of {} · best · {}"
CHOSEN = "Take {} of {} is best"
UNDER = "Best of {} takes, under the bar: {}"
_SAID = re.compile(r"<d>(.*?)</d>", re.DOTALL)
_TAG = re.compile(r"^\s*\[[^\]]*\]")


def job(params: dict, ctx: Ctx) -> JobPlan:
    """The `image` job kind: the press as `build.image_job` builds it, with takes for a clip or a line."""
    made = build.image_job(params, ctx)
    if isinstance(params, dict) and {"direct", "scene", "redo"} & params.keys():
        return made
    return plan(ctx, made)


def _count(ctx: Ctx, kind: str) -> tuple[bool, int]:
    """(the judge is on, the takes at most) for a clip (`scene_takes_max`, the scene's count) or a line
    (`speech_takes_max`)."""
    s = ctx.settings
    if kind == "clip":
        return bool(s.get("clip_judge", True)), max(1, int(s.get("scene_takes_max") or 1))
    return bool(s.get("speech_judge", True)), max(1, int(s.get("speech_takes_max") or 1))


def _shot(ctx: Ctx) -> dict | None:
    shot = routes.session_part(ctx).get("shot")
    return shot if isinstance(shot, dict) else None


def words(ctx: Ctx, prompt: str) -> str | None:
    """The press's spoken words: the session's shot's lines joined, else the `<d>…</d>` texts of the prompt, the
    `[Language]` tag dropped, joined by a space; none: None."""
    shot = _shot(ctx)
    if shot is not None and shot.get("lines"):
        said = [" ".join(str(x.get("words") or "").split()) for x in shot["lines"] if isinstance(x, dict)]
    else:
        said = [" ".join(_TAG.sub("", text).split()) for text in _SAID.findall(prompt or "")]
    return " ".join(x for x in said if x).strip() or None


def _judged(ctx: Ctx, summary: Mapping[str, Any], said: str | None) -> dict:
    """The one shot the clip's judge reads: the session's shot, else its words and the summary's framing. A clip
    that speaks a kept sound has its words left out: its mouth is judged, its words are not."""
    shot = copy.deepcopy(_shot(ctx)) if _shot(ctx) is not None else {
        "lines": [{"words": said}] if said else [], "camera": {"framing": summary.get("framing")}}
    if summary.get("sound"):
        shot["lines"] = [{**x, "words": ""} for x in shot.get("lines") or [] if isinstance(x, dict)]
    return shot


def plan(ctx: Ctx, made: JobPlan) -> JobPlan:
    """The press with its takes; a picture, a plan already of takes, or a press whose judge is off:
    `made` unchanged."""
    kind = made.summary.get("kind")
    if kind not in STEPS or not made.tasks or made.takes or made.prepare is not None:
        return made
    on, n = _count(ctx, kind)
    if not on:
        return made
    first, said = made.tasks, words(ctx, str(made.summary.get("prompt") or ""))
    if kind == "clip":                                   # take 1 is the press's own plus the judge-only `words`
        heard = None if made.summary.get("sound") else said
        first = tuple({**copy.deepcopy(t), "words": heard} if t.get("kind") == "video" else copy.deepcopy(t)
                      for t in made.tasks)
    size = len(first)
    tasks: list[dict] = []
    inputs: list[dict] = []
    names: list[str] = []
    own = list(made.summary.get("step_names") or [STEPS[kind]] * size)
    for t in range(n):
        tasks += redo.seeded(first, t)
        if made.inputs:
            inputs += redo._shift(made.inputs, t * size)
        names += own if not t else [f"{x}{redo.TAKE.format(t + 1)}" for x in own]
    takes_of = ((*(tuple(range(t * size + 1, (t + 1) * size + 1)) for t in range(n)),),)
    cap = 60 * float(ctx.settings.get("scene_retake_minutes") or 0)
    judge = (judgeshot.ShotJudge(ctx, [_judged(ctx, made.summary, said)], takes_of, cap) if kind == "clip"
             else judgeshot.LineJudge(ctx, takes_of, cap))
    summary = {**made.summary, "step_names": names} if n > 1 or made.summary.get("step_names") else made.summary
    return replace(made, tasks=tuple(tasks), summary=summary, inputs=tuple(inputs), takes=takes_of, judge=judge,
                   finish=Finish(ctx, judge, takes_of))


def _verdict(take: tuple[int, ...], seen: Mapping[int, Take]) -> Take | None:
    """A take's verdict: its failure when a task of it failed, else its first task's judging."""
    return next((seen[j] for j in take if j in seen and not seen[j].rank), seen.get(take[0]))


class Finish:
    """A press's last step, whatever its end: every take kept, the best marked on the job's notes. `job` is the
    job's id, set when it is known (`build.on_submitted`, `director.Planner.press`); unset: nothing is noted."""

    def __init__(self, ctx: Ctx, judge: judgeshot.ShotJudge, takes_of: tuple, job: str | None = None) -> None:
        self.ctx, self.judge, self.takes_of, self.job = ctx, judge, takes_of, job

    async def __call__(self, landed: Mapping[int, str]) -> None:
        job = self.ctx.jobs.get(self.job) if self.job else None
        if job is None:
            return
        notes = self.notes(landed, {**self.judge.seen, **job.takes})
        if notes:
            self.ctx.jobs.note(job.id, **notes)

    def notes(self, landed: Mapping[int, str], seen: Mapping[int, Take]) -> dict[str, Any]:
        """{verdict, verdicts (more than one take ran), best, best_task}; {} when no take landed."""
        pick = best_take(JobPlan("image", "", (), {}, takes=self.takes_of), 1, seen, landed)
        if pick is None:
            return {}
        ran = [take for take in self.takes_of[0] if any(j in seen for j in take)]
        n = len(ran)
        chosen = next(take for take in self.takes_of[0] if take[-1] == pick)
        number = self.takes_of[0].index(chosen) + 1
        top = _verdict(chosen, seen)
        said = top.line if top else judgeshot.NOT_JUDGED.format(judgeshot.NO_JUDGE)
        out: dict[str, Any] = {"best": landed[pick], "best_task": chosen[0]}
        if n <= 1:
            return {"verdict": said, **out}
        others, chips = [], {}
        for t, take in enumerate(ran, 1):
            verdict = _verdict(take, seen)
            line = verdict.line if verdict else judgeshot.NOT_JUDGED.format(judgeshot.NO_JUDGE)
            if take[-1] in landed:
                chips[landed[take[-1]]] = (BEST if take == chosen else CHIP).format(t, n, line)
            if take != chosen and verdict is not None and not verdict.passes:
                others.append(f"take {t}: {self.judge.short.get(take[0]) or line}" if verdict.rank else line)
        if top is not None and not top.passes:
            verdict_line = UNDER.format(n, said)
        else:
            verdict_line = (CHOSEN.format(number, n) + (f" ({'; '.join(others)})" if others else "") + f"; {said}; "
                            + judgeshot.USED.format(self.judge.used() / 60, self.judge.cap / 60))
        return {"verdict": verdict_line, "verdicts": chips, **out}
