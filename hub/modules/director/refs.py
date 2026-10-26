"""What a ref names, resolved by the Hub , pure: the three event tools take a `ref` or an `id`
: `{speaker, nth}`, `{cue, nth}`, `{shot: n}` (not `event_move`), counted in one scene (`scene`, else
the last) in timeline order (its shots in order, each one's events by `(start_ms, id)`). `named` hands `edit`/`frame`
the id and starts the did-line with what it named; `listing`: every write answer's `nth · speaker · first
words`.
"""
from __future__ import annotations

from collections.abc import Callable

from hub.core.api import Invalid

from . import camera, edit, frame, remove, scriptshape
from .edit import refuse

FIX = "Send ref as the message names it: {speaker, nth}, {cue, nth} or {shot: n}"
SHOT_FIX = ("Name a line {speaker, nth} or a cue {cue, nth}; event_change {ref: {shot: n}, fields: {camera}} changes "
            "a shot")


def ordinal(k: int) -> str:                       # 1st, 2nd, 3rd, 4th, … 11th, 12th, 13th, 21st
    return f"{k}{'th' if 10 <= k % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(k % 10, 'th')}"


def first(words: object) -> str:                  # the first 4 words as written, then `…` when there are more
    cut = str(words).split()
    return " ".join(cut[:4]) + ("…" if len(cut) > 4 else "")


def _numbered(scene: dict, kind: str) -> list[tuple[int, dict]]:
    """The scene's lines (cues) in timeline order, each numbered among its speaker's lines (its kind's)."""
    key, seen, out = ("speaker" if kind == "line" else "cue"), {}, []
    for shot in scene["shots"]:
        for ev in sorted(shot["events"], key=lambda e: (e["start_ms"], e["id"])):
            if ev.get("kind") == kind:
                who = str(ev.get(key, "")).casefold()
                seen[who] = seen.get(who, 0) + 1
                out.append((seen[who], ev))
    return out


def entries(scene: dict, kind: str = "line") -> list[str]:
    """`1 · Speaker 1 · Line 1…` (a cue's `1 · reaction · Laughter and…`), in timeline order."""
    key = "speaker" if kind == "line" else "cue"
    return [f"{k} · {ev.get(key)} · {first(ev.get('words', ''))}" for k, ev in _numbered(scene, kind)]


def listing(script: dict, n: int | None) -> str:
    """The entries of scene n joined by ` | `; "" with no lines (or no such scene)."""
    ok = n is not None and 1 <= n <= len(script.get("scenes", []))
    return " | ".join(entries(script["scenes"][n - 1])) if ok else ""


def _nth(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 1


def _form(ref: object) -> str | None:
    """Which of the ref forms `ref` is exactly (each with an optional `scene`); None when it is none of them."""
    if not isinstance(ref, dict) or ("scene" in ref and not _nth(ref["scene"])):
        return None
    keys = set(ref) - {"scene"}
    if keys == {"speaker", "nth"} and isinstance(ref["speaker"], str) and ref["speaker"].strip() and _nth(ref["nth"]):
        return "speaker"
    if keys == {"cue", "nth"} and ref["cue"] in scriptshape.CUES and _nth(ref["nth"]):
        return "cue"
    return "shot" if keys == {"shot"} and _nth(ref["shot"]) else None


def _echo(script: dict, n: int, item: dict, is_shot: bool) -> str:
    """The words for what was named, before the change: a shot, a line, a cue, a pose."""
    scene, at = script["scenes"][n - 1], f" (scene {n})" if len(script["scenes"]) > 1 else ""
    if is_shot:
        k = next(i for i, s in enumerate(scene["shots"], 1) if s is item)
        return f"shot {k}{at}, {item.get('id')}: {camera.said(item) or 'no camera'}"
    if (kind := item.get("kind")) not in ("line", "cue"):
        return f"{item.get('character')}'s pose{at} {item['id']}: {item.get('pose')}"
    k = ordinal(next(i for i, ev in _numbered(scene, kind) if ev is item))
    what = f"{item.get('speaker')}'s {k} line" if kind == "line" else f"the {k} {item['cue']} cue"
    return f"{what}{at}, {item['id']}: {first(item.get('words', ''))}"


def _by_id(script: dict, ident: object) -> str | None:
    """The echo of what an id names; None when the script holds no such id (left for the tool to refuse)."""
    for n, sc in enumerate(script["scenes"], 1):
        for shot in sc["shots"]:
            for item in (shot, *shot["events"]):
                if item.get("id") == ident and item.get("kind") != "panel":
                    return _echo(script, n, item, item is shot)
    return None


def _found(script: dict, n: int, scene: dict, ref: dict, form: str) -> tuple[dict, bool]:
    """The thing a ref names in scene n, or the refusal of an `nth` past the count with the scene's list in its
    hints."""
    if form == "shot":
        found, said, what = scene["shots"], f"Scene {n} has", "shot"
        hints = {"shots": [f"{k} · {s.get('id')} · {camera.said(s) or 'no camera'}" for k, s in enumerate(found, 1)]}
    elif form == "speaker":
        who = edit._member(script, n, ref["speaker"], "line")
        found = [ev for _, ev in _numbered(scene, "line") if str(ev.get("speaker")).casefold() == who.casefold()]
        said, what, hints = f"{who} has", "line", {"lines": entries(scene)}
    else:
        found = [ev for _, ev in _numbered(scene, "cue") if ev.get("cue") == ref["cue"]]
        said, what, hints = f"Scene {n} has", f"{ref['cue']} cue", {"cues": entries(scene, "cue")}
    k = ref["shot"] if form == "shot" else ref["nth"]
    if k > len(found):
        where = f" in scene {n}" if form == "speaker" else ""
        plural = "" if len(found) == 1 else "s"
        raise refuse(f"{said} {len(found)} {what}{plural}{where}, not {k}", "Name one the hints list", **hints)
    return found[k - 1], form == "shot"


def resolve(script: dict, args: dict, tool: str) -> tuple[dict, str | None]:
    """The ref's checks, then what it names: -> (args with `id` for `ref`, the echo; None for an id the script
    lacks)."""
    if ("ref" in args) == ("id" in args):
        raise refuse("ref and id, not both" if "ref" in args else "Name what to change", FIX)
    if "id" in args:
        return args, _by_id(script, args["id"])
    ref, form = args["ref"], _form(args["ref"])
    if form is None:
        raise refuse("A ref names one thing", FIX)
    if form == "shot" and tool == "event_move":           # event_remove takes an empty shot
        raise refuse(f"{tool} takes a line, cue or pose, not a shot", SHOT_FIX)
    n = ref.get("scene", max(1, len(script["scenes"])))
    item, is_shot = _found(script, n, edit._scene(script, n), ref, form)
    return {**{k: v for k, v in args.items() if k != "ref"}, "id": item.get("id")}, _echo(script, n, item, is_shot)


def named(fn: Callable[..., dict], tool: str) -> Callable[..., dict]:
    """`fn(script, args, pace=)` resolving first, its did-line started with the echo."""
    def run(script: dict, args: dict, pace: float | None = None) -> dict:
        sent, echo = resolve(script, args, tool)
        done = fn(script, sent, pace=pace)
        if echo:
            done["did"] = f"{echo} · {done['did']}"
        return done
    return run


TOOLS = {"event_move": named(edit.event_move, "event_move"), "event_change": named(frame.change, "event_change"),
         "event_remove": named(remove.event_remove, "event_remove")}


def call(script: dict, sent: tuple[str, dict]) -> tuple[str, dict] | None:
    """The call with `ref` resolved to `id` on `script` (the file as read); None when it does not resolve."""
    if sent[0] not in TOOLS or "ref" not in sent[1]:
        return sent
    try:
        return sent[0], resolve(script, sent[1], sent[0])[0]
    except Invalid:
        return None
