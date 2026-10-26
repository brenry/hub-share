"""The Hub's line for a chat message, pure: what was done in
plain words from the operations applied (`clause`), then what follows from settle's line (`follows`), then at the limit
`not done: <the first kept problem>` (`plain`: no tool, field or id); at most `CAP` characters. A written
story is one short line: its scenes, shots and length (counted on the script), `rendering N
shots` when Render was pressed, and what is not finished as one plain sentence (`sayhold.sentence`), never a `not
done:` line or a request for words."""
from __future__ import annotations

import json
import re
from typing import Any

from hub.core.api import Invalid

from . import camera, refs, sayask, saycheck, sayhold, sayplain, scriptshape

CAP = 400
FACTS = ("gap_ms", "after_ms", "max_words", "max_seconds", "most_ms", "over_ms", "least_ms", "length_ms",
         "latest_start_ms", "suggested_start_ms", "end_ms")
ADDED = (("add_scene", "scene"), ("add_shot", "shot"), ("add_line", "line"), ("add_cue", "cue"), ("add_pose", "pose"))
Calls = list[tuple[str, dict]]


def refusal(e: Invalid) -> str:
    """A refusal's problem, its gaps and its facts in words; never its fix."""
    try:
        got = json.loads(e.text)
    except ValueError:
        return e.text
    if not isinstance(got, dict):
        return e.text
    hints = got.get("hints") if isinstance(got.get("hints"), dict) else {}
    out = str(got.get("problem", e.text))
    if isinstance(hints.get("gaps"), list) and hints["gaps"]:
        out += ": " + "; ".join(map(str, hints["gaps"][:5]))
    facts = [f"{k} {hints[k]}" for k in FACTS if isinstance(hints.get(k), (int, float))]
    return out + (f" ({', '.join(facts)})" if facts else "")


CAME = ((r"operation \d+ says", "it came back as"), (r"operation \d+ sets one", "one came back"), (r"operation \d+ "
        r"adds it", "it came back as an add"), (r"\boperation \d+\b", "one change"), (r"has a ref that is none of.*$",
        "names nothing it can change"))


def _said_as(ident: str, script: dict | None) -> str:     # an id by what it names, its kind when the script lacks it
    said = _named(script, ident)[0] if script and ident[0] != "f" else "it"
    return said if said != "it" else "a " + {"s": "shot", "l": "line", "c": "cue", "p": "pose", "f": "sketch"}[ident[0]]


def plain(text: str, script: dict | None = None) -> str:
    """No tool, field or id: an `operation k:` / `(tool)` head, `{…}`, a parenthesis naming a call, a
    word with `_` out; a head's tool and fields, an operation number, an id (named in `script`) in plain words."""
    t = re.sub(r"^(operation \d+|scene \d+): ", "", str(text))
    upper, head = t[:1].isupper(), re.match(r"operation \d+ \((\w+)\):? |(\w+) (?=needs |has a ref )", t)
    if head and (head.group(1) or head.group(2) in saycheck.SAID_OP):
        t = saycheck.SAID_OP.get(head.group(1) or head.group(2), "one change") + " " + re.sub(
            r"^needs (.*)$", lambda m: "needs " + re.sub(r"\w+", lambda w: saycheck.SAID_FIELD.get(w[0], w[0]),
                                                         re.sub(r"\{.*?\}", "", m[1])), t[head.end():])
    t = re.sub(r" \(operation \d+ (?:has|says) .*\)$|\s*\([^()]*[_{][^()]*\)|\s*\{[^{}]*\}|\S*_\S*", "", t)
    for was, said in CAME:
        t = re.sub(was, said, t)
    t = re.sub(r"(?:\b(?i:line|shot|cue|pose|sketch)\s+)?\b([sclpf][0-9]+)\b", lambda m: _said_as(m[1], script), t)
    t = re.sub(r"\s+([,;:.])", r"\1", re.sub(r"\s{2,}", " ", t)).strip(" ,;:")
    return t[:1].upper() + t[1:] if upper else t


def cap(text: str) -> str:
    return text if len(text) <= CAP else text[:CAP - 1].rstrip() + "…"


def _named(script: dict, ident: str) -> tuple[str, dict | None]:
    """Plain words for the thing `ident` names in `script`: `<Subject 1>'s 1st line`, `the 2nd reaction cue`,
    `shot 2`."""
    for n, scene in enumerate(script["scenes"], 1):
        at = f" of scene {n}" if len(script["scenes"]) > 1 else ""
        for k, shot in enumerate(scene["shots"], 1):
            if shot.get("id") == ident:
                return f"shot {k}{at}", shot
        for kind in ("line", "cue"):
            for k, ev in refs._numbered(scene, kind):
                if ev["id"] == ident:
                    who = f"{ev['speaker']}'s {refs.ordinal(k)} line" if kind == "line" else \
                        f"the {refs.ordinal(k)} {ev['cue']} cue"
                    return who + at, ev
        for shot in scene["shots"]:
            for ev in shot["events"]:
                if ev["id"] == ident:
                    return f"{ev.get('character')}'s pose", ev
    return "it", None


def clause(op: dict, calls: Calls, before: dict, after: dict) -> str | None:
    """What one applied operation did, in plain words; None for an add (counted in the line)."""
    kind, (_, args), before, after = op["op"], calls[0], sayask.bare(before), sayask.bare(after)
    if kind in saycheck.ADDS:
        return None
    if kind == "set_length":
        return f"set scene {args['scene']} to {args['seconds']} s"
    if kind == "picture":
        return sayplain.USE[op["picture_use"]].format(args["cast"][0]["name"])
    if kind == "cast":
        who = op["name"]
        was = any(m["name"].casefold() == who.casefold() for m in before["context"]["cast"])
        what = "; ".join(f'{k} "{saycheck._cut(op[k], 120)}"' for k in ("look", "costume") if op.get(k))
        return f"took {who} out of the cast" if op.get("remove") else \
            (f"changed {who}: {what}" if what else f"changed {who} in the cast") if was else f"added {who} to the cast"
    what, item = _named(before, args["id"])
    if kind == "change_shot":
        cam = camera.of(_named(after, args["id"])[1] or {})
        parts = [cam[k] for k in ("framing", "move") if cam.get(k)] + ([f"on {', '.join(cam['on'])}"] if
                                                                       cam.get("on") else [])
        parts += ["its action"] if "action" in op else []
        return f"changed {what}: {', '.join(parts)}"
    if kind == "remove":
        words = (item or {}).get("words")
        return f'took out {what}: "{refs.first(words)}"' if words else f"took out {what}"
    if kind == "move":
        return f"moved {what} to {_named(after, args['shot'])[0]}"
    fields = args["fields"]
    if "words" in fields:
        return f'changed {what} to: "{saycheck._cut(fields["words"], 120)}"'
    if "seconds" in fields:
        return f"changed {what} to {fields['seconds']:g} s"
    return f"changed {what}: {fields.get('emotion')}"


def follows(got: dict | None, script: dict | None = None) -> str | None:
    """The press's line (the answer's last) in plain words (`script` names its ids); None when nothing
    follows."""
    last = str((got or {}).get("state", [""])[-1])
    if last.startswith("Track refused: "):
        return "the takes could not start: " + plain(last.removeprefix("Track refused: "), script)
    if last.startswith("Track: "):
        rest = last.removeprefix("Track: ")
        return "the takes follow the job running now" if rest.startswith("again when") else \
            "mixing the track again" if "nothing to render; mixing" in rest else \
            None if "are current" in rest else "the takes are being made"
    return None


def line(tried: Any, got: dict | None, failed: str | None) -> str:
    """What was done · what follows · at the limit what was not done; a new story's is `story`."""
    if tried.new:
        return story(tried, got, failed)
    made = {word: sum(1 for op, _ in tried.applied if op["op"] == kind) for kind, word in ADDED}
    counts = ", ".join(f"{n} {w}{'' if n == 1 else 's'}" for w, n in made.items() if n)
    said = [*tried.said, *(c for _, c in tried.applied if c)]
    lengthened = any(op["op"] == "set_length" for op, _ in tried.applied)
    if tried.new:
        said.insert(0, f"wrote {counts or 'nothing'}")
    elif counts:
        said.append(("wrote " + counts.replace(" line", " more line")) if lengthened else f"added {counts}")
    what = ", ".join(said) if lengthened else "; ".join(said)
    parts = [what] if what else []
    if tried.new or counts or lengthened:
        asked = sum(sc.get("seconds", 0) for sc in tried.script["scenes"])
        parts.append(f"runs {scriptshape.length_ms(tried.script) / 1000:.1f} s" + (f" ({asked} s asked)" if asked and
                                                                                   tried.new else ""))
    parts += [x for x in (follows(got, tried.script), failed) if x]
    if tried.kept and failed is None:
        parts.append(f"not done: {plain(tried.kept[0], tried.script)}")
    return " · ".join(parts) or sayplain.VAGUE                     # nothing named, nothing changed


def _count(script: dict) -> str:
    """What the script holds: scenes, shots, lines, cues and the Director's poses, as written."""
    shots = [shot for sc in script["scenes"] for shot in sc["shots"]]
    evs = [ev for shot in shots for ev in shot["events"] if not ev.get("auto")]
    made = {"scene": len(script["scenes"]), "shot": len(shots), **{w: sum(1 for ev in evs if ev.get("kind") == w)
                                                                   for w in ("line", "cue", "pose")}}
    return ", ".join(f"{n} {w}{'' if n == 1 else 's'}" for w, n in made.items() if n)


def story(tried: Any, got: dict | None, failed: str | None) -> str:
    """A written story's one short line: `wrote <counts> · runs <s> (<s> asked)`, `rendering N shots` when
    Render was pressed, what follows when it is not a gap, and the first thing not finished as one plain sentence."""
    asked = sum(sc.get("seconds", 0) for sc in tried.script["scenes"])
    parts = [f"wrote {_count(tried.script) or 'nothing'}",
             f"runs {scriptshape.length_ms(tried.script) / 1000:.1f} s" + (f" ({asked} s asked)" if asked else "")]
    after = follows(got, tried.script)
    left = [x for x in (failed, *tried.kept[:1], after if after and after.startswith("not done") else None) if x]
    parts += [x for x in (tried.rendered, None if after in left else after) if x]
    rest = sayhold.sentence(plain(left[0], tried.script)) if left else ""
    return " · ".join(parts) + (f". {rest}" if rest else "")
