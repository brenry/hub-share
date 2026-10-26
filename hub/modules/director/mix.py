"""The mix (blueprint §12.3, §12.5): a locked script's takes placed by one map from the rows
(`place.py`) on a lane per speaker, `reaction`, `effect`, `music` and `room`, made one WAV by the worker's lane graph
(`hub/worker/mixcmd.py`): `sounds/<script>.wav` (a file already of that name kept: `<script>-<n>.wav`), stems on
request in `sounds/<script>/stems/`. The script holds the mix (`mix`), the files made (`renders`: names, sizes) and
every row's time in the track (`measured`), written once when the job ends, only if the script is as it was at the press
(`mixfinish.py`). In memory only: `running` {script: job id}, `failed` {script: one line}. Nothing of a
job is on disk.
"""
from __future__ import annotations

import copy
import hashlib
import json
from typing import Any

from hub.core.api import NO_MODEL, Action, Canvas, Ctx, Invalid, JobPlan, JoinRequest, request_wire, sound_exact

from . import audioscript, cuetakes, layout, lock, place, routes, scripts, scriptshape, takejudge
from .mixfinish import Finish
from .teach import SAY

KIND = "mix"
CURRENT = "nothing to render: every take and the mix are current"
NO_ROOM, NOT_LANDED = "no room take", "the mix did not land"
MIXING = "{} is mixing (job {})"                                 # `autolock.start` reads it
TARGET = {"lufs": takejudge.PARAMS["dialogue_lufs"], "true_peak_dbtp": takejudge.PARAMS["true_peak_dbtp"],
          "source": "EBU R 128 (2020)"}
CUES = ("reaction", "effect", "music")
running: dict[str, str] = {}
failed: dict[str, str] = {}


def _takes(ctx: Ctx, name: str, script: dict) -> tuple[dict, set[str], list[str]]:
    """Every line and cue's take `ok` or `flagged` and in Sounds (else the first refused), but a cue of a kind
    with no sound model, left out -> (the takes but theirs, files, the left-out lines)."""
    takes = script.get("takes") or {}
    there, voices = routes.present(ctx, takes), routes.voices(ctx, script)
    lines, out = cuetakes.left(ctx, name, script, takes, there)
    rows = sorted((ev for shot in layout.shots(script) for ev in shot["events"] if ev["kind"] in ("line", "cue")
                   and ev["id"] not in out), key=lambda ev: (ev["start_ms"], ev["id"]))
    for ev in rows:
        v = voices.get(ev["speaker"].casefold()) if ev["kind"] == "line" else None
        facts = None if v is None else [v.size, v.mtime_s]
        if audioscript.take(name, ev, takes, present=there, voice=facts)["state"] not in audioscript.VERDICTS:
            raise Invalid("script", f"{ev['id']} has no current take: call script_track")
    return {k: v for k, v in takes.items() if k not in out}, there, lines


def lanes(script: dict, placed: dict, room: dict | None) -> list[dict]:
    """A dialogue lane per speaker (context order, only speakers with a line), then reaction, effect, music (each
    when it holds a clip), then the room; a lane's gain, and a bed's duck, kept from the last mix's lane of its name."""
    length, clips = placed["length_ms"], list(placed["clips"].values()) + ([room] if room else [])
    before = {lane["name"]: lane for lane in (script.get("mix") or {}).get("lanes", [])}
    said = {c["speaker"].casefold() for c in clips if c["kind"] == "line"}
    order = [(m["name"], "dialogue") for m in script.get("context", {}).get("cast", []) if m["name"].casefold() in said]
    out = []
    for name, kind in order + [(k, k) for k in (*CUES, place.ROOM)]:
        held = [c for c in clips if (c["kind"] == "line" and c["speaker"].casefold() == name.casefold()
                                     if kind == "dialogue" else c["kind"] == kind)]
        if not held:
            continue
        rows = []
        for c in sorted(held, key=lambda c: (c["at_ms"], c["id"])):
            fin, fout = place.fades(c, length)
            rows.append({"take": c["id"], "file": c["file"], "at_ms": c["at_ms"], "in_ms": c["in_ms"],
                         "out_ms": c["out_ms"], "gain_db": c["gain_db"], "fade_in_ms": fin, "fade_out_ms": fout,
                         "loop": kind == place.ROOM})
        last = before.get(name) or {}
        out.append({"name": name, "kind": kind, "gain_db": float(last.get("gain_db", 0.0)),
                    "duck": bool(last.get("duck", True)) if kind in CUES else False, "clips": rows})
    return out


def hashed(held: list[dict], length: int) -> str:
    raw = json.dumps({"lanes": held, "target": TARGET, "length_ms": length}, sort_keys=True, separators=(",", ":"),
                     ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


def build(ctx: Ctx, name: str, script: dict, read_room: bool = True, room_ms: int | None = None) -> dict:
    """The takes, the lanes and each clip's gain in the mix's range -> {placed, lanes, mix (its note the left-out
    lines, or null), takes}; refused in one line. `room_ms`: the room's length as the press measured it, so no WAV is
    read."""
    if script["version"] != 2 or not lock.locked(script):
        raise Invalid("mix", f"{name} changed after its takes: Track it again")
    if not layout.shots(script):
        raise Invalid("mix", f"{name} has no shot")
    takes, there, left = _takes(ctx, name, script)
    room = takes.get(place.ROOM)
    with_room = room is not None and room.get("file") in there and room.get("hash") == cuetakes.room_hash(script)
    lengths: dict[str, int] = {}
    if with_room and (room.get("measured") or {}).get("speech_end_ms") is None and room_ms is not None:
        lengths[place.ROOM] = room_ms
    elif with_room and (room.get("measured") or {}).get("speech_end_ms") is None:
        if not read_room and not isinstance((script.get("mix") or {}).get("room_ms"), int):
            raise Invalid("mix", "the room's length is not recorded")   # the route reads no WAV
        try:
            lengths[place.ROOM] = script["mix"]["room_ms"] if not read_room else round(sound_exact(
                ctx.files.existing_media(f"sounds/{room['file']}")) * 1000)
        except (Invalid, OSError, ValueError):
            lengths[place.ROOM] = 0
    placed = place.place(script, takes, lengths)
    held = lanes(script, placed, place.room(takes, lengths) if with_room else None)
    lo, hi = place.CLIP_GAIN
    for c in (c for lane in held for c in lane["clips"] if not lo <= c["gain_db"] <= hi):
        raise Invalid("mix", f"{c['take']}: its take {c['file']} is levelled by {c['gain_db']:+.1f} dB, past the "
                      f"mix's {f'{hi:+g}' if c['gain_db'] > hi else f'{lo:g}'}: {place.REDO}")
    mix = {"lanes": held, "target": dict(TARGET), "length_ms": placed["length_ms"], "note": "; ".join(left) or None,
           "hash": hashed(held, placed["length_ms"])}
    if read_room and place.ROOM in lengths:
        mix["room_ms"] = lengths[place.ROOM]                    # what the route then uses
    return {"placed": placed, "lanes": held, "mix": mix, "takes": script.get("takes") or {}}   # all, as on disk


def _wire(ctx: Ctx, held: list[dict], length: int, solo: int | None) -> dict:
    out = request_wire(JoinRequest([], Canvas(0, 0, 1000.0), [], 18, "medium", "wav"))
    out.update(lanes=[{"name": ln["name"], "kind": ln["kind"], "gain_db": ln["gain_db"], "duck": ln["duck"],
                       "clips": [{"path": str(ctx.files.existing_media(f"sounds/{c['file']}").resolve()),
                                  "at_ms": c["at_ms"], "in_ms": c["in_ms"], "out_ms": c["out_ms"],
                                  "gain_db": c["gain_db"], "fade_in": c["fade_in_ms"], "fade_out": c["fade_out_ms"],
                                  "loop": c["loop"]} for c in ln["clips"]]} for ln in held],
               target=None if solo is not None else {k: TARGET[k] for k in ("lufs", "true_peak_dbtp")},
               solo=solo, length_ms=length)
    return out


def job(params: dict, ctx: Ctx) -> JobPlan:
    """The `mix` job kind: the master, then one task per lane with `stems`; refused in one `Invalid` line."""
    name = scripts.name_of(params.get("script"))
    try:
        script = scripts.readable(routes.folder(ctx), name, routes.characters(ctx))
    except Invalid as e:
        raise Invalid("mix", lock._problem(e)) from None
    made = build(ctx, name, script)
    if not any(lane["kind"] == place.ROOM for lane in made["lanes"]):         # after the cue lines
        made["mix"]["note"] = "; ".join(filter(None, [made["mix"]["note"], cuetakes.room_note(cuetakes.room_why(
            ctx, NO_ROOM))]))
    trial = copy.deepcopy(script)
    place.apply(trial, made["placed"], made["mix"], script.get("renders") or {"track": None, "size": None, "stems": {}})
    try:
        scriptshape.read(trial, routes.characters(ctx))
    except Invalid as e:
        raise Invalid("mix", e.text) from None
    length, stems, n = made["mix"]["length_ms"], bool(params.get("stems")), len(made["lanes"])
    try:
        tasks = [_wire(ctx, made["lanes"], length, k) for k in [None, *(range(n) if stems else ())]]
    except Invalid:
        raise Invalid("mix", "A take of the mix is gone from Sounds: call script_track") from None
    summary = {"kind": "sound", "mode": "mix", "title": f"Mix · {name} · {n} lane{'' if n == 1 else 's'}",
               "seconds": round(length / 1000, 2)}
    return JobPlan("image", NO_MODEL, tuple(tasks), summary, finish=Finish(ctx, name, made, stems))


def prune(ctx: Ctx, name: str) -> None:
    held = running.get(name)
    made = ctx.jobs.get(held) if held is not None else None
    if held is not None and (made is None or getattr(made, "state", None) in ("done", "failed", "cancelled")):
        running.pop(name, None)


def submit(ctx: Ctx, name: str, stems: bool = False, busy: bool = True) -> Any:
    """The mix job for `name` (refused while one runs when `busy`); a refusal raised as it came."""
    prune(ctx, name)
    if busy and name in running:
        raise Invalid("mix", MIXING.format(name, running[name]))
    failed.pop(name, None)
    made = ctx.jobs.submit(KIND, {"script": name, "stems": stems})
    fin = getattr(made.plan, "finish", None)
    if isinstance(fin, Finish):
        fin.job = made.id
    running[name] = made.id
    return made


def _note(made: Any) -> str | None:
    fin = getattr(made.plan, "finish", None)
    return fin.made["mix"]["note"] if isinstance(fin, Finish) else None


def after_track(ctx: Ctx, name: str) -> str | None:
    """Track's finish submits the mix when every line and cue has a current take; its refusal kept and
    returned (the Hub's line says it), else None."""
    try:
        script = scripts.readable(routes.folder(ctx), name, routes.characters(ctx))
        if script["version"] != 2 or not lock.locked(script):
            return None
        _takes(ctx, name, script)
    except Invalid:
        return None
    try:
        submit(ctx, name, busy=False)
    except Exception as exc:  # noqa: BLE001  (Invalid, or the queue's Refused: its one line, as drawing.py)
        failed[name] = lock._problem(exc) if isinstance(exc, Invalid) else str(getattr(exc, "text", exc))
        return failed[name]
    return None


def remix(ctx: Ctx, name: str) -> Any:
    """The mix submitted with `busy` off, for the mix tools."""
    return submit(ctx, name, busy=False)


def when_nothing(ctx: Ctx, name: str, refused: Invalid) -> dict:
    """Track's "nothing to render": refused when the mix is current, else the mix submitted."""
    from . import tools, track  # late: track reads this module

    if refused.text != track.NOTHING:
        raise refused
    try:
        if routes.current(ctx, name, scripts.readable(routes.folder(ctx), name, routes.characters(ctx))):
            raise track.Refusal("script", CURRENT + track.tail(refused))   # the lines left out
        made = submit(ctx, name)
    except track.Refusal:
        raise
    except Invalid as e:
        raise track.Refusal("mix", lock._problem(e)) from None
    tools._publish(ctx, name)
    return {"job": made.id, "lines": 0, "mixing": True, "answer": f"{name} · Track: nothing to render; mixing "
            f"(job {made.id})", "note": _note(made)}


def said(got: dict) -> list[str] | None:
    """`script_track`'s lines for a mix answer, its note second; None for Track's own."""
    return [got["answer"], *([got["note"]] if got.get("note") else [])] if got.get("answer") else None


async def script_stems(ctx: Ctx, args: dict) -> dict:
    """The open script mixed again with its stems."""
    from . import tools, track  # late

    name = tools._current(ctx)
    try:
        made = submit(ctx, name, stems=True)
    except Invalid as e:
        raise layout.refuse(lock._problem(e), track.FIXES["mix"]) from None
    tools._publish(ctx, name)
    n = len(made.plan.tasks) - 1
    return {"script": name, "state": [f"{name} · Stems: {n} lane{'' if n == 1 else 's'} mixing (job {made.id})",
                                      *filter(None, [_note(made)])]}


ACTION = Action("script_stems", SAY["script_stems"], {"type": "object", "additionalProperties": False,
                                                      "required": [], "properties": {}}, script_stems)
