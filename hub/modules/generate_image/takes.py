"""What the judges' readings say, and what a finished press leaves in the session's memory.

The sentences (`HELD` … `FRAME`, `face_line`, `mouth_line`, `frame_line`) are the lines shown on a take: the
face judge's (a character's similarity held, lost, late, never or low against `clip_face_bar`), the mouth judge's
(still, moving with the words, or off against `clip_lips_bar`), the frame judge's (the face's size against the band the
shot's `camera.framing` named, `frame_close`, `frame_wide`) and the words judge's (`HEARD`, `VERDICT`, `UNHEARD`).
`judging` and `asked` give a clip request and its summary the judges' fields. Every press is judged inside its
own job (`presstakes`, `judgeshot`); nothing here re-takes. The `job.finished` listeners (`on_clip_finished`,
`on_finished`, from `chain.on_job_finished`) only read the job's notes: the session's `last_take` (memory only) is
the take the job marked best (`notes.best`), else the newest; a line's words span teaches the voice's pace
(`pace.learn_rate`), else the file's own span (`pace.learn`).
"""
from __future__ import annotations

from typing import Any

from hub.core.api import Ctx

from . import pace, routes

UNHEARD = "The words judge did not run"
VERDICT = "Best take heard {}% of the words; the first miss at {} s"
HEARD = "Heard {}% of the words"
HELD = "{}'s face held ({})"
LOST = "{}'s face was lost after {} s ({} → {}); try a closer picture, the character's views, or a shorter clip"
LATE = "{}'s face matched poorly at the start ({}) and held by the end ({})"
NEVER = "{}'s face never matched the picture well ({} → {}); try a closer, front-on picture or its views"
LOW = "{}'s face scored {} ({} is the bar); try a closer picture, the character's views, or a shorter clip"
UNSEEN = "The face judge did not run: {}"
MOUTH_NONE = "The mouth judge did not run: {}"
MOUTH_STILL = "{}'s mouth is still while speaking ({}% of the speaking frames move), another take or a shorter line"
MOUTH_WHOLE = "{} speaks the whole clip; the mouth moves in {}% of it"
UNSCRIPTED = "{} makes {} s of speech that is not the line"
MOUTH_WITH = "{}'s mouth moves with the words ({})"
MOUTH_OFF = "{}'s mouth does not follow the words ({}, {} is the bar); try another take or a shorter line"
FRAME = "{}'s face is {} of the frame's height; the shot asked for {}"
FACELESS = "{}'s picture shows no face to judge by"
STILL_SHARE = 0.2              # under this share of moving frames the mouth is still
BANDS = (("medium", ("medium", "mid", "waist"), "a medium shot"),
         ("close", ("close", "closeup", "tight"), "a close-up"),
         ("wide", ("wide", "full", "long", "establishing", "master"), "a wide shot"))


def judging(ctx: Ctx, identities: list[Any] = ()) -> dict[str, Any]:
    """The judges' fields for a clip request: the face judge's device when it is on and its bar; the
    speaker whose mouth is read: the session's shot's first line's, else the first named identity's."""
    device = str(ctx.settings.get("judge_device") or "cpu")
    on = bool(ctx.settings.get("clip_judge", True))
    shot = routes.session_part(ctx).get("shot") or {}
    lines = shot.get("lines") if isinstance(shot, dict) else None
    speaker = lines[0].get("speaker") if lines and isinstance(lines[0], dict) else None
    speaker = speaker or next((r.name for r in identities if getattr(r, "name", None)), None)
    return {"judge": device if on else None, "judge_bar": float(ctx.settings.get("clip_face_bar") or 0.3),
            "speaker": str(speaker) if speaker else None}


def asked(ctx: Ctx) -> dict[str, str]:
    """`{"framing": …}` for a clip's summary when the session's shot names the camera's framing, else {}."""
    shot = routes.session_part(ctx).get("shot") or {}
    framing = (shot.get("camera") or {}).get("framing") if isinstance(shot, dict) else None
    return {"framing": str(framing)} if framing else {}


def mouth_line(verdict: dict, bar: float) -> tuple[str, bool]:
    """The mouth judge's line and whether it calls for a re-take (a still mouth, or lips under the bar)."""
    read = verdict.get("mouth")
    if not isinstance(read, dict):
        return MOUTH_NONE.format(verdict.get("mouth_why") or "no reading"), False
    who, moving, lips = read.get("speaker") or "the speaker", read.get("moving"), read.get("lips")
    if moving is not None and moving < STILL_SHARE:
        return MOUTH_STILL.format(who, round(moving * 100)), True
    if lips is None:
        return MOUTH_WHOLE.format(who, round(moving * 100) if moving is not None else "?"), False
    if lips >= bar:
        return MOUTH_WITH.format(who, f"{lips:.2f}"), False
    return MOUTH_OFF.format(who, f"{lips:.2f}", f"{bar:.2f}"), True


def frame_subject(verdict: dict, framing: str | None, speaker: str | None, lowest: str) -> str:
    """Whose size the frame line is about: the character the framing names, else the speaker, else the lowest."""
    names = list((verdict.get("frame") or {}).keys())
    words = str(framing or "").casefold()
    named = next((n for n in names if n.casefold() in words), None)
    return named or (speaker if speaker in names else lowest)


def frame_line(verdict: dict, name: str, framing: str | None, close: float, wide: float) -> str | None:
    """The frame judge's line when the shot asked for a band the face's size is outside; None otherwise. A framing
    that names two bands ("medium close-up") fits when either does."""
    size = ((verdict.get("frame") or {}).get(name) or {}).get("size")
    words = set(str(framing or "").casefold().replace("-", " ").split())
    bands = [(b, said) for b, keys, said in BANDS if words & set(keys)]
    if size is None or not bands:
        return None
    fits = {"close": size >= close, "wide": size < wide, "medium": wide <= size < close}
    if any(fits[b] for b, _ in bands):
        return None
    return FRAME.format(name, f"{size:.2f}", " or ".join(said for _, said in bands))


def face_line(verdict: dict, name: str, low: float, bar: float) -> str:
    """The face judge's sentence for `name`, scored `low` against `bar`: held, late, never, lost or low."""
    who = verdict["face"][name]
    if low >= bar:
        return HELD.format(name, f"{low:.2f}")
    if who.get("lost_at") is not None and float(who.get("first") or 0) < bar:   # low from the first second on
        late = float(who.get("last") or 0) >= bar
        return (LATE if late else NEVER).format(name, f"{who['first']:.2f}", f"{who['last']:.2f}")
    if who.get("lost_at") is not None:
        return LOST.format(name, who["lost_at"], f"{who['first']:.2f}", f"{who['last']:.2f}")
    return LOW.format(name, f"{low:.2f}", f"{bar:.2f}")


def verdicts(notes: dict | None) -> dict[int, dict[str, Any]]:
    """{task (1-based) → the words verdict} of a finished job's notes."""
    judged = (notes or {}).get("judged") or {}
    out = {}
    for task, judge in judged.items():
        words = judge.get("words") if isinstance(judge, dict) else None
        if isinstance(words, dict) and isinstance(words.get("heard"), (int, float)):
            out[int(task)] = words
    return out


def best_of(scored: dict[int, dict[str, Any]]) -> int | None:
    """The task with the most words heard; among equals, the one whose first miss is latest (None latest of all)."""
    if not scored:
        return None
    return max(scored, key=lambda t: (scored[t]["heard"], scored[t].get("first_miss") is None,
                                      scored[t].get("first_miss") or 0.0, -t))


async def on_clip_finished(ctx: Ctx, job: Any, data: dict) -> None:
    """A finished clip press: `last_take` is its best take (`notes.best`, its readings and verdict), else
    its newest clip with no verdict. A scene's job is left alone."""
    if job.plan.summary.get("mode") == "scene":
        return
    outputs = [o for o in data.get("outputs") or [] if ctx.files.kind(o) == "clip"]
    if not outputs:
        return
    notes = data.get("notes") or {}
    if notes.get("best") not in outputs:                             # no judge asked: the newest take, no verdict
        routes.session_part(ctx)["last_take"] = {"id": outputs[-1], "verdict": None}
        return
    read = (notes.get("judged") or {}).get(str(notes.get("best_task"))) or {}
    kept = {k: read.get(k) for k in ("face", "mouth", "frame")}
    routes.session_part(ctx)["last_take"] = {"id": notes["best"], **kept, "verdict": notes.get("verdict")}


async def on_finished(ctx: Ctx, job: Any, data: dict) -> None:
    """A finished line press: `last_take` is its best take (`notes.best`), else its newest; the pace is
    learned from the best take's words span, else from the file's own span; with no reading the card
    says the judge did not run."""
    outputs = [o for o in data.get("outputs") or [] if ctx.files.kind(o) == "sound"]
    notes = data.get("notes") or {}
    item = notes.get("best") if notes.get("best") in outputs else outputs[-1] if outputs else None
    words = verdicts(notes).get(int(notes["best_task"])) if isinstance(notes.get("best_task"), int) else None
    if words is None:
        if item is not None:                                   # unheard: the pace from the file's own span
            pace.learn(ctx, ctx.files.existing_media(item), str(job.plan.summary.get("prompt") or ""))
            said = notes.get("verdict") or UNHEARD
            routes.session_part(ctx)["last_take"] = {"id": item, "verdict": said}
            if not notes.get("verdict"):
                ctx.jobs.note(job.id, verdict=UNHEARD)
        return
    if words.get("span") and words.get("words"):
        pace.learn_rate(ctx, float(words["words"]) / float(words["span"]))
    routes.session_part(ctx)["last_take"] = {"id": item, **words, "verdict": notes.get("verdict")}  # for the assistant
