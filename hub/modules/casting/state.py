"""The drafts: per character, in memory, never on disk before Approve. A Hub restart loses an
unapproved draft (no log, CLAUDE.md).

A draft: the character's name, its picture (box 1, the headshot) with its keep and ignore lines, the bits `[{id, keep,
ignore}]`, its facts `{age, build}`, the seed and model of its last cast, the last job, what it made (the orbit clip's
id, the six views' ids by view) and its state, `none | rendering | ready | failed | approved`, with the one line of a
refusal or a failure (`problem`). The job's end (`finished`, on `job.finished`) sets the state from its outputs and
tells the tab (`casting.changed`). A queued job cancelled now sends `job.finished` (cancelled); a draft
rendering whose job is gone without ending reads as failed (`view`), kept as the fallback.

A draft has its `role` (cast | audience) and `seat` and the view names its job makes (`expect`); a
costume's draft (`costume.py`) lives in the same map keyed by (name, costume) (`key`), and its end is found the same
way (`by_job`).

The tab's one Prompt box (`box`, `set_box`), one text for casts, extras and costumes, `""` at start, held
here in memory only: written to no file, record or log; a Hub restart empties it.
"""
from __future__ import annotations

from typing import Any

from hub.core.api import Ctx

from . import record, variants

STATES = ("none", "rendering", "ready", "failed", "approved")
CANCELLED = "The cast was cancelled"
NO_VIEWS = "The orbit made no views"
UNSHOWN = ("seed", "expect", "cast_as")    # kept on a draft, never in an answer
_drafts: dict[Any, dict[str, Any]] = {}
_box = {"text": ""}                        # the Prompt box, never on disk


def box() -> str:
    return _box["text"]


def set_box(text: Any) -> None:
    """The box as typed, byte for byte, when `text` is a string, whatever its length."""
    if not isinstance(text, str):
        return
    _box["text"] = text


def key(name: str, variant: str | None = None) -> Any:
    return name.casefold() if variant is None else (name.casefold(), variant.casefold())


def get(name: str, variant: str | None = None) -> dict[str, Any] | None:
    return _drafts.get(key(name, variant))


def put(draft: dict[str, Any]) -> dict[str, Any]:
    _drafts[key(draft["name"], draft.get("variant"))] = draft
    return draft


def drop(name: str, variant: str | None = None) -> None:
    _drafts.pop(key(name, variant), None)


def costumes_of(name: str) -> list[dict[str, Any]]:
    """The character's costume drafts in memory."""
    return [d for k, d in _drafts.items() if isinstance(k, tuple) and k[0] == name.casefold()]


def clear() -> None:
    _drafts.clear()
    _box["text"] = ""


def by_job(job_id: Any) -> dict[str, Any] | None:
    return next((d for d in _drafts.values() if job_id is not None and d.get("job") == job_id), None)


def fresh(name: str, picture: str, approved: dict[str, Any] | None = None) -> dict[str, Any]:
    """A draft before any cast: empty lines, no bits, no facts; with an approved record, its lines,
    facts and bits (the bits as the record's files, so Cast again sends them as they are)."""
    draft: dict[str, Any] = {
        "name": name, "state": "none", "headshot": {"id": picture, "keep": "", "ignore": ""},
        "bits": [], "facts": {"age": "", "build": ""}, "seed": None, "model": None, "job": None, "orbit": None,
        "views": None, "problem": None, "role": record.role_of(approved),
        "seat": dict((approved or {}).get("seat") or record.SEAT), "expect": None}
    draft["expect"] = list(record.SHEETS[draft["role"]])
    if approved is not None:
        head, facts = approved.get("headshot") or {}, approved.get("facts") or {}
        files = record.ids(name, approved)["bits"]
        bits = [b for b in approved.get("bits") or [] if isinstance(b, dict)]
        draft.update(state="approved", model=approved.get("model"),
                     headshot={"id": picture, "keep": str(head.get("keep") or ""),
                               "ignore": str(head.get("ignore") or "")},
                     facts={"age": str(facts.get("age") or ""), "build": str(facts.get("build") or "")},
                     bits=[{"id": f, "keep": str(b.get("keep") or ""), "ignore": str(b.get("ignore") or "")}
                           for f, b in zip(files, bits, strict=True) if f])
    return draft


def current(ctx: Ctx, name: str, picture: str) -> dict[str, Any]:
    """A character's draft in memory, else a fresh one (from its record when it is cast); its headshot is its picture
    now."""
    draft = get(name)
    if draft is None:
        return fresh(name, picture, record.read(ctx, name))
    draft["headshot"]["id"] = picture
    if draft["state"] == "rendering" and ctx.jobs.get(draft["job"]) is None:
        draft.update(state="failed", problem=CANCELLED)
    return draft


def view(ctx: Ctx, name: str, picture: str) -> dict[str, Any]:
    """The tab's answer (`routes` docstring): the draft, plus the approved record and its files when the character is
    cast, and its costumes."""
    draft = current(ctx, name, picture)
    approved = record.read(ctx, name)
    return {k: value for k, value in draft.items() if k not in UNSHOWN} | {
        "picture": picture, "record": approved, "files": record.urls(ctx, name, approved) if approved else None,
        "costumes": variants.listing(ctx, name, approved, costumes_of(name)), "prompt": box()}


def publish(ctx: Ctx, name: str, variant: str | None = None) -> None:
    ctx.bus.publish("changed", "changed", {"name": name} if variant is None else {"name": name, "variant": variant})


async def finished(ctx: Ctx, data: dict) -> None:
    """`job.finished` of a cast: ready with one clip and the views it expects, else failed with the job's line."""
    draft = by_job(data.get("job")) if data.get("tool") == ctx.module_id else None
    if draft is None:
        return
    outputs = [str(o) for o in data.get("outputs") or []]
    clips = [o for o in outputs if ctx.files.kind(o) == "clip"]
    views = [o for o in outputs if ctx.files.kind(o) == "image"]
    expect = draft.get("expect") or list(record.SHEET)
    if data.get("state") == "done" and len(clips) == 1 and len(views) == len(expect):
        draft.update(state="ready", orbit=clips[0], views=dict(zip(expect, views, strict=True)), problem=None)
    else:
        job = ctx.jobs.get(str(data.get("job")))
        line = getattr(job, "error", None) or (CANCELLED if data.get("state") == "cancelled" else NO_VIEWS)
        draft.update(state="failed", orbit=clips[0] if clips else None, views=None, problem=str(line))
    publish(ctx, draft["name"], draft.get("variant"))
