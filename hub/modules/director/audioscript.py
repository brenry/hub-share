"""The audio script (blueprint A.8, A.9, §12.1), pure: for a locked script, each line's exact
`Speaker 1:` block (`block`, as the worker writes one take, `hub/worker/adapters/tasks.py` `speech`), each cue's
request by its kind (no model is named), the cap each would be sent with (`cap`), the hash of the fields that make
its sound (`sound_hash`) and the take it would make (`take`). `check_takes` is the file's `takes` record as
`scriptshape` reads it. Nothing here writes, renders or starts a job; the panel is computed on each read.
A line's hash covers its speaker's sample (its size and modified second); a take is also `rendering`
or `failed` while `Track` holds it, and `none` when its file is gone from Sounds; `check_takes` checks what
`Track` writes and refuses a number that is not finite anywhere in `takes`.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Container, Mapping, Sequence
from typing import Any

from hub.core.api import Invalid, spoken_line

SPEAKER = "Speaker 1:"            # one speaker per generation (blueprint A.8); a test pins it to the worker's
NO_BRACKETS = "language and emotion hold no [ ] or line break"
VERDICTS = ("ok", "flagged")
TAKE = (("file", "hash"), ("tries", "measured", "judge"))
MEASURED = ("speech_start_ms", "speech_end_ms", "length_ms", "lufs", "true_peak_dbtp", "gain_db")
DECAY = "decay_ms"                # beside them for a reaction cue
JUDGED = ("heard", "first_miss_ms", "extra_speech", "verdict", "why")
_BAD = re.compile(r"[\[\]\n\r]")


def prompt(ev: dict) -> str:
    """`[<language>, <emotion>, <pace> words per second] <words>`, each part present, in that order; none: the
    words alone."""
    parts = [ev[k] for k in ("language", "emotion") if ev.get(k)]
    if ev.get("pace") is not None:
        parts.append(f"{float(ev['pace']):g} words per second")
    return f"[{', '.join(parts)}] {ev['words']}" if parts else ev["words"]


def block(ev: dict) -> tuple[str | None, str | None]:
    """A line's block as the Hub will send it, and None; or None and the one line saying why it cannot be sent."""
    if any(_BAD.search(ev.get(k) or "") for k in ("language", "emotion")):
        return None, NO_BRACKETS
    text = prompt(ev)
    try:
        spoken_line(ev["words"])          # the event's `words`, then the prompt as the worker checks it
        spoken_line(text)
    except ValueError as err:
        return None, str(err)
    return f"{SPEAKER}\n{text}", None


def cap(ev: dict) -> int:
    """A line twice its planned length, a cue its length; whole seconds rounded up, at least 1."""
    ms = (ev["end_ms"] - ev["start_ms"]) * (2 if ev["kind"] == "line" else 1)
    return max(1, -(-ms // 1000))


def sound_hash(ev: dict, voice: Sequence[int] | None = None) -> str:
    """The first 16 hex digits of SHA-256 over the fields that make the event's sound, and nothing of time.
    A line whose speaker has a sample (`voice`: its size and modified time in whole seconds) has those
    two numbers as its last field; without one the line's own fields alone. A cue's hash holds its length
    (`cap`, the seconds it is rendered at), so a lengthened cue is stale."""
    if ev["kind"] == "line":
        pace = ev.get("pace")
        fields: list[Any] = ["line", ev["speaker"].casefold(), ev["words"], ev.get("language") or "",
                             ev.get("emotion") or "", float(pace) if pace is not None else None]
        if voice is not None:
            fields.append([int(voice[0]), int(voice[1])])
    else:
        fields = ["cue", ev["cue"], ev["words"], cap(ev)]       # its length, in whole seconds
    raw = json.dumps(fields, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


def take(name: str, ev: dict, takes: Mapping[str, Any], present: Container[str] | None = None,
         live: Mapping[str, tuple[str, str | None]] | None = None, voice: Sequence[int] | None = None) -> dict:
    """None (the file §12.1 names, `<script>/<id>-1.wav`), stale, flagged (and why) or ok. First
    `live` (`track.state`: rendering, or failed and why), then an entry whose file is not in `present` (the take
    files in Sounds; None: not asked) is none; `voice` the speaker's sample facts for the hash. A
    failed take has a `file` only when the record's take is still in Sounds."""
    entry = takes.get(ev["id"])
    made = f"{name}/{ev['id']}-1.wav"
    held = (live or {}).get(ev["id"])
    if held is not None and held[0] == "failed":                  # only a file that landed is named
        landed = entry is not None and (present is None or entry["file"] in present)
        return {"state": "failed", **({"file": entry["file"]} if landed else {}), "why": held[1]}
    if held is not None:
        return {"state": held[0], "file": entry["file"] if entry is not None else made}
    if entry is None or (present is not None and entry["file"] not in present):
        return {"state": "none", "file": made}
    if entry["hash"] != sound_hash(ev, voice):
        return {"state": "stale", "file": entry["file"]}
    judge = entry.get("judge") or {}
    if judge.get("verdict") == "flagged":
        return {"state": "flagged", "file": entry["file"], "why": judge.get("why")}
    return {"state": "ok", "file": entry["file"]}


def _no(text: str) -> Invalid:
    return Invalid("script", text)


def _text(value: Any, hi: int) -> bool:
    return isinstance(value, str) and bool(value.strip()) and len(value) <= hi


def _finite(value: Any, at: str, where: str) -> None:
    """No float that is not finite anywhere in a take, at any depth; the key path named."""
    if isinstance(value, float) and not math.isfinite(value):
        raise _no(f"{where}: {at} is not a finite number")
    items = value.items() if isinstance(value, dict) else enumerate(value) if isinstance(value, list) else ()
    for key, inner in items:
        _finite(inner, f"{at}.{key}" if at else str(key), where)


def _number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _fields(value: dict, where: str) -> None:
    """`measured` of `MEASURED`'s keys, each a number or null; `judge` of `JUDGED`'s, each in its range or null."""
    measured, judge = value.get("measured"), value.get("judge") or {}
    for key, inner in (measured or {}).items():
        if key == DECAY:                  # a reaction cue's decay
            if inner is not None and not (isinstance(inner, int) and not isinstance(inner, bool) and inner >= 0):
                raise _no(f"{where}: measured.{key} is a whole number of 0 or more or null")
            continue
        if key not in MEASURED:
            raise _no(f"{where}: measured has a key the format does not know: {key}")
        if inner is not None and not _number(inner):
            raise _no(f"{where}: measured.{key} is a number or null")
    extra = sorted(set(judge) - set(JUDGED))
    if extra:
        raise _no(f"{where}: judge has a key the format does not know: {extra[0]}")
    if (heard := judge.get("heard")) is not None and not (_number(heard) and 0 <= heard <= 1):
        raise _no(f"{where}: judge.heard is a number from 0 to 1 or null")
    miss = judge.get("first_miss_ms")
    if miss is not None and not (isinstance(miss, int) and not isinstance(miss, bool) and miss >= 0):
        raise _no(f"{where}: judge.first_miss_ms is a whole number of 0 or more or null")
    if (extra_s := judge.get("extra_speech")) is not None and not (_number(extra_s) and extra_s >= 0):
        raise _no(f"{where}: judge.extra_speech is a number of 0 or more or null")
    if judge.get("why") is not None and len(judge["why"]) > 300:
        raise _no(f"{where}: a judge's why is at most 300 characters")


def _entry(value: Any, where: str) -> None:
    if not isinstance(value, dict):
        raise _no(f"{where}: a take is an object")
    _finite(value, "", where)
    need, may = TAKE
    missing = [k for k in need if k not in value]
    if missing:
        raise _no(f"{where}: a take has no {missing[0]}")
    extra = sorted(set(value) - set(need) - set(may))
    if extra:
        raise _no(f"{where}: a take has a key the format does not know: {extra[0]}")
    if not _text(value["file"], 300):
        raise _no(f"{where}: file is text of 1 to 300 characters")
    if not _text(value["hash"], 64):
        raise _no(f"{where}: hash is text of 1 to 64 characters")
    tries = value.get("tries", 1)
    if isinstance(tries, bool) or not isinstance(tries, int) or tries < 1:
        raise _no(f"{where}: tries is a whole number of 1 or more")
    for key in ("measured", "judge"):
        if value.get(key) is not None and not isinstance(value[key], dict):
            raise _no(f"{where}: {key} is an object or null")
    judge = value.get("judge") or {}
    if "verdict" in judge and judge["verdict"] not in VERDICTS:
        raise _no(f"{where}: a judge's verdict is ok or flagged")
    if judge.get("why") is not None and not isinstance(judge["why"], str):
        raise _no(f"{where}: a judge's why is text or null")
    _fields(value, where)


def check_takes(value: Any, ident: re.Pattern[str]) -> None:
    """`takes` is an object of event id -> take; a key naming no event of the script is read and shown nowhere."""
    if not isinstance(value, dict):
        raise _no("takes is an object")
    for key, entry in value.items():
        if not ident.fullmatch(key):
            raise _no("takes: an event's id is 1 to 24 letters, digits, - or _")
        _entry(entry, f"takes, {key}")


def voice_of(ev: dict, voices: Mapping[str, Sequence[int]] | None) -> Sequence[int] | None:
    """A line's speaker's sample facts `[size, mtime_s]`, None for a cue or a speaker with none."""
    return (voices or {}).get(ev["speaker"].casefold()) if ev["kind"] == "line" else None


def _row(name: str, ev: dict, shot: str, samples: Mapping[str, str], takes: Mapping[str, Any],
         seen: dict[str, Any]) -> dict:
    if ev["kind"] == "line":
        text, problem = block(ev)
        who, sample = ev["speaker"], samples.get(ev["speaker"].casefold())
    else:
        text, problem, who, sample = ev["words"], None, ev["cue"], None
    voice = voice_of(ev, seen["voices"])
    return {"id": ev["id"], "kind": ev["kind"], "shot": shot, "start_ms": ev["start_ms"], "end_ms": ev["end_ms"],
            "who": who, "text": text, "problem": problem, "sample": sample, "seconds": cap(ev),
            "hash": sound_hash(ev, voice),
            "take": take(name, ev, takes, present=seen["present"], live=seen["live"], voice=voice)}


def plan(name: str, script: dict, samples: Mapping[str, str], voices: Mapping[str, Sequence[int]] | None = None,
         present: Container[str] | None = None, live: Mapping[str, tuple[str, str | None]] | None = None) -> list[dict]:
    """Every line and cue in order of start, then id (no pose, no panel). `samples`: folded speaker name -> the
    file name of the speaker's sample; `voices` folded name -> `[size, mtime_s]`, `present` and `live` as `take`
    reads them."""
    takes = script.get("takes") or {}
    seen = {"voices": voices, "present": present, "live": live}
    rows = [_row(name, ev, f"{i}.{k}", samples, takes, seen)
            for i, scene in enumerate(script["scenes"], 1) for k, shot in enumerate(scene["shots"], 1)
            for ev in shot["events"] if ev.get("kind") in ("line", "cue")]
    return sorted(rows, key=lambda r: (r["start_ms"], r["id"]))
