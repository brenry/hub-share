"""The takes line, pure: one line saying where a script's takes are, from
what is handed in. With a Track job of the script on the queue, its card as the queue holds it (`JobBook.record`: `id`,
`state`, `position`, `progress` {`index`, `count`}, `summary.step_names`), the job's words as the Storyboard's bar
reads them: `takes: <done> of <all> · <id> being spoken (job <id>)`, or `takes: Track queued (job <id>,
<n> on the queue)`. Else the takes of the script's lines and cues (the room not counted), each state as the audio
script reads it (`audioscript.take`, with the speakers' sample facts, the take files present and Track's live states
handed in as `/script` hands them): `<n> takes: <a> ok, <b> flagged: <id> <why>, <c> failed: <id> <why>, <d> to take`,
each part only when not zero, at most `IDS` ids a state then `+<k>`, each why cut to `WHY_MAX` characters. Nothing
here reads a file, a job or the clock. The room's step is said `· room tone`, not `· room being spoken`.
"""
from __future__ import annotations

from collections.abc import Container, Mapping, Sequence
from typing import Any

from . import audioscript, layout

IDS = 3
WHY_MAX = 60
TO_TAKE = ("none", "stale", "rendering")       # rendering: a job the caller did not hand in still holds it
TAKE_OF = " · take "                           # `track.job`'s step name of a re-take: `<id> · take <t>`
ROOM = "room"                                  # `cuetakes.ROOM_ID`, the room's step name: said `room tone`


def states(script: dict, voices: Mapping[str, Sequence[int]] | None = None, present: Container[str] | None = None,
           live: Mapping[str, tuple[str, str | None]] | None = None) -> list[tuple[str, dict]]:
    """[(event id, its take as `audioscript.take` reads it)] of every line and cue, in order of start, then id."""
    takes = script.get("takes") or {}
    events = sorted((ev for shot in layout.shots(script) for ev in shot["events"] if ev.get("kind") in ("line", "cue")),
                    key=lambda ev: (ev["start_ms"], ev["id"]))
    return [(ev["id"], audioscript.take("", ev, takes, present=present, live=live,
                                        voice=audioscript.voice_of(ev, voices))) for ev in events]


def _named(held: list[tuple[str, dict]]) -> str:
    """`<id> <why>` of the first `IDS`, joined by ` · `, then ` · +<k>` for the rest."""
    said = []
    for ident, got in held[:IDS]:
        why = (got.get("why") or "")[:WHY_MAX].rstrip()
        said.append(f"{ident} {why}" if why else ident)
    if len(held) > IDS:
        said.append(f"+{len(held) - IDS}")
    return " · ".join(said)


def done(script: dict, voices: Mapping[str, Sequence[int]] | None = None, present: Container[str] | None = None,
         live: Mapping[str, tuple[str, str | None]] | None = None, after: str | None = None) -> str:
    """The none-running form; `after` (the caller's line that is not a lock) follows it as `; <after>`."""
    rows = states(script, voices, present, live)
    by: dict[str, list[tuple[str, dict]]] = {"ok": [], "flagged": [], "failed": [], "take": []}
    for ident, got in rows:
        by["take" if got["state"] in TO_TAKE else got["state"]].append((ident, got))
    parts = [f"{len(by['ok'])} ok"] if by["ok"] else []
    parts += [f"{len(by[k])} {k}: {_named(by[k])}" for k in ("flagged", "failed") if by[k]]
    parts += [f"{len(by['take'])} to take"] if by["take"] else []
    # the line shown
    out = f"{len(rows)} take{'' if len(rows) == 1 else 's'}" + (f": {', '.join(parts)}" if parts else "")
    return f"{out}; {after}" if after else out


def job(card: Mapping[str, Any] | None) -> str | None:
    """The running or queued form of a Track job's card; None when no card is handed in, or it runs no more. Running
    before its first task (no `progress` yet): `takes: 0 of <steps> (job <id>)`."""
    if not card:
        return None
    ident, state = card.get("id"), card.get("state")
    if state == "queued":
        place = card.get("position")
        return f"takes: Track queued (job {ident}, {place} on the queue)" if place else \
            f"takes: Track queued (job {ident})"
    if state != "running":
        return None
    names = list((card.get("summary") or {}).get("step_names") or [])
    progress = card.get("progress") or {}
    index = progress.get("index")
    if not isinstance(index, int) or index < 1:
        return f"takes: 0 of {len(names)} (job {ident})"
    count = progress.get("count") or len(names)
    step = names[index - 1].split(TAKE_OF)[0] if index <= len(names) else None
    spoken = " · room tone" if step == ROOM else f" · {step} being spoken" if step else ""   # the room's word
    return f"takes: {index - 1} of {count}{spoken} (job {ident})"


def line(script: dict, running: Mapping[str, Any] | None = None, *,
         voices: Mapping[str, Sequence[int]] | None = None, present: Container[str] | None = None,
         live: Mapping[str, tuple[str, str | None]] | None = None, after: str | None = None) -> str:
    """The takes line: the job's form while `running` (the card of the script's Track job) is queued or
    running, else the none-running form over the script's takes."""
    return job(running) or done(script, voices, present, live, after)
