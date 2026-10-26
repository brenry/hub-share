"""Track (blueprint §12.1, §12.2, A.9; every press locks the script
first, `autolock.settle`, whatever its scenes say): every line of the script whose
take is none or stale spoken as its own take, one job on the queue, one task per take, on the speech model Generate
picks (its `speech` service; the pulldown's, else the last or only speech model). Each take is
judged by the words judge and measured in the worker (`SpeechRequest.judge`, `measure`), its verdict `takejudge`'s;
under the bar a line is taken again up to Generate's `speech_takes_max`; one failed take never ends the
job (`TrackJudge.alone`). At the job's end (`trackfinish.Finish`) every landed take is filed in Sounds
as `<script>/<id>-<n>.wav` and the best take of each line recorded in the script's `takes` (the line's hash at the
press, the measured and judged fields), the one write going through `scripts.change`, not the tools' guard.

In memory only: `running` {script: {job, ids}} while its job runs (one job per script), `failed` {(script, id): one
line} for a line with no take landed, cleared by the next press on that script. Nothing of a job is on disk.
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from hub.core.api import Action, Ctx, Invalid, JobPlan, SpeechRequest, request_wire

from . import audioscript, cuetakes, layout, lock, mix, routes, scripts, takejudge
from .teach import SAY
from .trackfinish import Finish

KIND = "track"
NOTHING = "nothing to render: every line has a take"
NO_GENERATE = "Generate Image is not running"
AUDIENCE = "Sounds keeps the audience in audience/: rename the script"
NO_TAKE = "no take landed"
OLD = "{} is a version-1 script; Track takes version 2"
CHANGED = "{} changed as Track started: press Track again"
running: dict[str, dict[str, Any]] = {}
failed: dict[tuple[str, str], str] = {}
FIXES = {"lock": "Call script_track again",
         "model": "Pick a speech model in Generate, then call script_track again",
         "speech": "Put a speech model in your model folders, Rescan, then call script_track again",   # no speech model
         "name": "Rename the script", "script": "Nothing to do",
         "cue": "Put that sound model in your model folders, Rescan, then call script_track again",
         "line": "Change that line with event_change; the Hub takes it again",
         "mix": "Do what the line says, then call script_track again"}


class Refusal(Invalid):
    """A Track refusal: its one line, for a sample the speaker it names; `NOTHING`'s lines left out."""

    def __init__(self, field: str, text: str, who: str | None = None, notes: Sequence[str] = ()) -> None:
        super().__init__(field, text)
        self.who, self.notes = who, list(notes)


def state(name: str) -> dict[str, tuple[str, str | None]]:
    """{line id: ("rendering", None) | ("failed", why)} of the script `name`."""
    out: dict[str, tuple[str, str | None]] = {i: ("failed", why) for (n, i), why in failed.items() if n == name}
    held = running.get(name)
    if held is not None:
        out.update({i: ("rendering", None) for i in held["ids"]})
    return out


def _lines(script: dict) -> list[dict]:
    rows = [ev for shot in layout.shots(script) for ev in shot["events"] if ev["kind"] == "line"]
    return sorted(rows, key=lambda ev: (ev["start_ms"], ev["id"]))


def _sample(ev: dict, voice: routes.Voice | None) -> None:
    """The line's speaker has a sample of at least 2 s that reads as a WAV; else one line."""
    who = ev["speaker"]
    if voice is None:
        raise Refusal("sample", f"{ev['id']}: {who} has no voice sample in Characters", who)
    if voice.seconds is None:
        raise Refusal("sample", f"{ev['id']}: {who}'s voice sample does not read as a WAV", who)
    if voice.seconds < lock.MIN_SAMPLE_S:
        raise Refusal("sample", f"{ev['id']}: {who}'s voice sample is {lock.cut(voice.seconds)} s, under 2 s", who)


def _model(ctx: Ctx) -> dict:
    """Generate's speech pick; its refusal keeps the pick's field (`speech` or `model`)."""
    try:
        pick = ctx.service("speech")
    except Invalid:
        raise Refusal("model", NO_GENERATE) from None
    try:
        return pick()
    except Invalid as e:
        raise Refusal(e.field if e.field in FIXES else "model", e.text) from None


def job(params: dict, ctx: Ctx) -> JobPlan:
    """The `track` job kind: one task per take of each line to render, each line's takes in a row; then the cue
    and room tasks by model, each model once (`cuetakes.plan`, handed the speech model first)."""
    name = scripts.name_of(params.get("script"))
    try:
        script = scripts.readable(routes.folder(ctx), name, routes.characters(ctx))
    except Invalid as e:
        raise Refusal("lock", lock._problem(e)) from None
    if script["version"] != 2:
        raise Refusal("lock", OLD.format(name))
    if not lock.locked(script):                          # a write landed between the press and the plan
        raise Refusal("lock", CHANGED.format(name))
    if name.casefold() == "audience":
        raise Refusal("name", AUDIENCE)
    voices = routes.voices(ctx, script, measure=True)
    takes = script.get("takes") or {}
    there = routes.present(ctx, takes)
    todo = [ev for ev in _lines(script) if audioscript.take(
        name, ev, takes, present=there, voice=_facts(voices.get(ev["speaker"].casefold())))["state"] in
        ("none", "stale")]
    speech = _model(ctx) if todo else None
    more = cuetakes.plan(ctx, name, script, takes, there, None if speech is None else speech["id"])  # cues, room
    if not todo and not more.ids:
        raise Refusal("script", NOTHING, notes=more.notes)               # the lines left out kept
    model = speech or {"id": more.models[0][0], "label": more.models[0][1], "takes_max": 1,
                       "seconds": {"min": 1, "max": 1}}
    lo, hi = int(model["seconds"]["min"]), int(model["seconds"]["max"])
    n = max(1, int(model["takes_max"]))
    tasks, names, hashes = [], [], {}         # no seed, each take the same request run again
    for ev in todo:
        voice = voices.get(ev["speaker"].casefold())
        _sample(ev, voice)
        text, problem = audioscript.block(ev)
        if text is None:
            raise Refusal("line", f"{ev['id']}: {problem}")
        planned = (ev["end_ms"] - ev["start_ms"]) / 1000
        if planned > hi:
            raise Refusal("line", f"{ev['id']}: planned {planned:.2f} s, over the {hi} s {model['label']} speaks at "
                                  "most")
        prompt = text[len(audioscript.SPEAKER) + 1:]           # the worker writes the header (tasks.speech)
        hashes[ev["id"]] = audioscript.sound_hash(ev, _facts(voice))
        for t in range(n):
            tasks.append(request_wire(SpeechRequest(
                model["id"], prompt, None, min(hi, max(lo, audioscript.cap(ev))), sample=str(voice.path.absolute()),
                turn_seconds=None, pace=None, join_seconds=None, judge=True, measure=True)))
            names.append(ev["id"] + ("" if t == 0 else f" · take {t + 1}"))
    takes_of = tuple(tuple((k * n + t + 1,) for t in range(n)) for k in range(len(todo))) + tuple(
        ((len(tasks) + j + 1,),) for j in range(len(more.ids)))         # each cue and the room one take
    judge = takejudge.TrackJudge(takes_of, model, {len(todo) + j + 1: k for j, k in enumerate(more.kinds)})
    summary = {"prompt": f"Track · {name}", "model": model["label"], "model_id": model["id"], "mode": "refs",
               "kind": "sound", "width": None, "height": None, "count": len(todo) + len(more.ids), "steps": None,
               "guidance": None,
               "seeds": more.seeds, "loras": [], "references": sorted({ev["speaker"] for ev in todo}),
               "voice": "sample", "step_names": names + more.ids}
    finish = Finish(ctx, name, [ev["id"] for ev in todo] + more.ids, hashes | more.hashes, judge, takes_of)
    finish.more, finish.lines, finish.n = more, len(todo), n
    return JobPlan("image", model["id"], tuple(tasks + more.tasks), summary, finish=finish, takes=takes_of,
                   judge=judge)


def _facts(voice: routes.Voice | None) -> list[int] | None:
    return None if voice is None else [voice.size, voice.mtime_s]


def _publish(ctx: Ctx, name: str) -> None:
    from . import tools  # late: tools reads the routes this module reads

    tools._publish(ctx, name)


def prune(ctx: Ctx, name: str) -> None:
    """The script's job dropped from `running` when the book holds it no more or it ended without its finish (a queued
    job cancelled), so a press is never refused by a job that is gone."""
    held = running.get(name)
    if held is not None:
        made = ctx.jobs.get(held["job"])
        if made is None or getattr(made, "state", None) in ("done", "failed", "cancelled"):
            running.pop(name, None)


async def on_finished(ctx: Ctx, data: dict) -> None:
    """`job.finished` of a Track job that `running` still holds (its finish never ran: cancelled or
    refused while queued): the entry dropped and `director.changed` published. Nothing is marked failed (no take was
    made); a job whose finish ran is found nowhere and publishes nothing more. The Hub's line said
    and `pending` dropped (a cancel is not undone)."""
    from . import autolock  # late: it reads this module

    if data.get("kind") != f"{ctx.module_id}.{KIND}":
        return
    held = [name for name, entry in running.items() if entry.get("job") == data.get("job")]
    for name in held:
        running.pop(name, None)
        _publish(ctx, name)
        autolock.track_queued(ctx, name, data)


def tail(refused: Invalid) -> str:
    """`; <line>` for each line a `NOTHING` refusal carries (a kind or the room left out)."""
    return "".join(f"; {note}" for note in getattr(refused, "notes", ()))


async def press(ctx: Ctx, name: str) -> dict:
    """The job submitted for the script `name` -> {job, lines, takes}; refused in one line (`Refusal`). Every press
    clears the script's `pending`. The script is locked first (`autolock.settle`); never called while the tools'
    guard is held."""
    from . import autolock  # late: it reads this module

    autolock.pending.discard(name)
    prune(ctx, name)
    held = running.get(name)
    if held is not None:
        raise Refusal("busy", f"{name}'s takes are rendering (job {held['job']})")
    line = await autolock.settle(ctx, name)
    if line is not None:
        raise Refusal("lock", line)
    for key in [k for k in failed if k[0] == name]:
        del failed[key]
    try:
        made = ctx.jobs.submit(KIND, {"script": name})
    except Refusal as e:                                 # nothing to render, the mix may be due
        return mix.when_nothing(ctx, name, e)
    fin = made.plan.finish
    fin.job = made.id
    running[name] = {"job": made.id, "ids": list(fin.ids)}
    _publish(ctx, name)
    return {"job": made.id, "lines": fin.lines, "takes": fin.n if fin.lines else 0, "cues": fin.more.cues,
            "room": fin.more.room, "note": fin.more.note, "notes": list(fin.more.notes)}


async def script_track(ctx: Ctx, args: dict) -> dict:
    """Track on the open script; ≤ 6 lines, or {problem, fix, hints}. The press locks it."""
    from . import tools  # late: tools reads this module's neighbours

    name = tools._current(ctx)
    try:
        got = await press(ctx, name)
    except Refusal as e:
        fix = FIXES.get(e.field, "Call script_track again")
        if e.field == "busy":
            fix = f"Wait for job {running[name]['job']} to end"
        elif e.field == "sample":
            fix = (f"Put {e.who}.wav of at least 2 s beside the speaker's picture in Characters, then call "
                   "script_track again")
        raise layout.refuse(e.text, fix) from None
    return {"script": name, "state": mix.said(got) or cuetakes.answer(name, got)}


ACTION = Action("script_track", SAY["script_track"], {"type": "object", "additionalProperties": False,
                                                      "required": [], "properties": {}}, script_track)
