"""What the Hub asks for a chat message (blueprint §21.2), pure: one schema-held ask turns the words
into operations on the script's numbered listing. `listing` (the context, then per scene its shots by number with their
framing and every event in timeline order with its ref's name (`refs`) and its whole words), `schema`
(`{title?, operations}`, each operation one flat object, no `anyOf`: which fields an operation needs is
`saycheck.fields`'), `messages` (the Hub's rules, the listing, then `Script message: <its words>`, not `Script:`, which
the block hands over) and `calls`: each operation as the ordinary tool calls on the trial as it stands, so R48 §2's
event-at-a-time checks stay the Hub's. Anyone may be cast (`name` is text, no picture or voice needed); `PLAIN`, the
rules of plain messages (a removal only when asked; a look or costume rewritten whole; `picture` sets a member's
`picture_use`); the listing shows each member's look, costume and picture use, so a change keeps the words not named.
`HELD`: a shot holds its own `seconds` (add_shot, change_shot): a story with no line is written as held shots that
reach the length the message names; the listing shows each shot's hold and `action`. A new story is `saystory`'s;
a length sent is never rounded nor held to a range (`_whole`, `_hold`)."""
from __future__ import annotations

import copy
import json

from hub.core.api import Invalid

from . import camera, edit, layout, length, panels, refs, scriptshape
from . import context as scene_context
from .layout import lines_of, secs
from .saycheck import OPS

USER = "Script message: {}"
SEND_BACK = ("The Hub refused that list: {}. Send the whole list again as one JSON object, changed only where "
             "needed.")
RULES = (
    "You turn the chat message into operations on the script listed below. Answer with JSON only: "
    '{"title": "<the script\'s title>", "operations": [...]}, one operation per line, cue, pose or shot. Write the '
    'whole message as operations. The message\'s quoted words and the words after "to:" exactly as written, '
    "punctuation and case kept. The message's numbers as written. A change is change_line, change_cue, change_shot, "
    "remove, move, set_length, cast or picture, never an add. A length (seconds) only where the message names one. "
    "Shots are numbered within their scene as they stand after the operations before; add_shot makes the next "
    "number; scene and shot default to the last. ref names one thing: {speaker, nth} the speaker's nth line, {cue, "
    "nth}, {shot: n}, with an optional scene. at {speaker, nth, end} is that line's start, or its end with end: true.")
STORY = (
    " For a story: shots that tell it in order. Every add_shot has its action: what we see happen in that shot (who "
    "does what, the expression, the movement, the beat), in the story's own events, never a camera word alone. "
    "Consecutive shots differ in framing (wide, medium, close-up, over-the-shoulder, insert, reaction) or in who is "
    "on: an opening wide or two-shot, then singles, inserts and reactions cut on the action and the exchange; the "
    "actions build to a turn and an end. A framing of a few words with who is in frame (on); each line the "
    "speaker's own words acting on the other, who answers it, never the narration copied; a cue only where the story "
    "or the stage calls for one; a length reached by more shots with their actions, or by lines, never by repeating "
    "a shot.")
HELD = (
    " A shot holds its own seconds (up to 15 s, whole or tenths) on add_shot or change_shot: yours to choose for that "
    "shot from its action and the pace of the cut, a long hold for a slow or quiet moment, a quick cut for a sudden "
    "beat; never an equal share of the length. A story with no spoken line has no add_line: many shots, each "
    "add_shot with its action, its seconds, a framing and a move that cut on the action, who is on, add_pose where a "
    "pose helps, a cue where a sound is called for. The shots' seconds add up to the length the message names: the "
    "Hub never adds a shot nor changes a shot's seconds.")
PLAIN = (
    " Take out a line, cue, shot or cast member only when the message asks to take it out; never to make room. "
    "A message that names nothing to change gets an empty list of operations. A change to someone's look or costume is "
    "cast with that member's whole new look or costume: the words listed, with the change. Anyone may be cast, "
    "with or without a picture: a person the story names who is not listed is a cast with a look and costume only "
    "where the story's words give them. How a member's picture is used is picture {name, picture_use}: reference, the "
    "picture is who the person is in every shot; frame, the picture is the first frame; none, the picture is not used.")
NEW = " This is a new story: start with add_scene; title is required."


def _text() -> dict:              # not blank, no length cap of the Hub's
    return {"type": "string", "minLength": 1}


def _enum(names: list[str]) -> dict:
    return {"type": "string", "enum": list(names)} if names else _text()


def _no(lo: int = 1) -> dict:
    return {"type": "integer", "minimum": lo}


def schema(cast: list[str], characters: list[str], new: bool = False) -> dict:
    """The schema: the speakers, characters, `on` and `cast` an enum of the context's names; `name` any name
    (`characters`, the names with a picture, are kept in the signature)."""
    names = {"type": "array", "minItems": 1, "items": _enum(cast)}
    at = {"type": "object", "additionalProperties": False, "required": ["speaker", "nth"],
          "properties": {"speaker": _enum(cast), "nth": _no(), "end": {"type": "boolean"}}}
    ref = {"type": "object", "additionalProperties": False,
           "properties": {"speaker": _enum(cast), "cue": {"type": "string", "enum": list(scriptshape.CUES)},
                          "shot": _no(), "nth": _no(), "scene": _no()}}
    op = {"type": "object", "additionalProperties": False, "required": ["op"], "properties": {
        "op": {"type": "string", "enum": list(OPS)}, "scene": _no(), "shot": _no(), "after": _no(0),
        "title": _text(), "cast": names, "on": {**names, "minItems": 0},
        "seconds": {"type": "number", "minimum": 0.1},
        "framing": _text(), "move": _text(), "speaker": _enum(cast),
        "character": _enum(cast), "words": _text(), "emotion": _text(),
        "cue": {"type": "string", "enum": list(scriptshape.CUES)},
        "pose": {"type": "string", "enum": list(scriptshape.POSES)}, "at": at, "ref": ref,
        "name": _text(), "picture_use": {"type": "string", "enum": list(scene_context.PICTURE_USES)},
        "look": _text(), "costume": _text(), "ignore": _text(), "action": _text(),
        "home": {"type": "integer", "minimum": 0, "maximum": 100}, "remove": {"type": "boolean"}}}
    listed = {"type": "array", "minItems": 1 if new else 0, "items": op}   # none, nothing named
    return {"type": "object", "additionalProperties": False, "required": ["title", "operations"] if new else
            ["operations"], "properties": {"title": _text(), "operations": listed}}


def _context(script: dict) -> list[str]:
    held = script.get("context") or {}
    out = [f"cast {m['name']}" + "".join(f" · {k} {m[k]}" if k == "home" else f" · {k}: {m[k]}" for k in
           ("home", "look", "costume", "picture_use") if m.get(k) is not None) for m in held.get("cast", [])]
    stage = held.get("set") or {}
    if stage:
        props = ", ".join(p.get("name", "") for p in stage.get("props", []))
        out.append(f"set {stage.get('name', '')}: {', '.join(stage.get('elements', []))}"
                   + (f" · props {props}" if props else ""))
    if held.get("style"):
        out.append(f"style {held['style']}")
    return out


def _event(ev: dict, k: dict[str, int]) -> str | None:
    at = secs(ev["start_ms"])
    if ev["kind"] == "line":
        tail = f" · {ev['emotion']}" if ev.get("emotion") else ""
        return f'{ev["speaker"]} {k.get(ev["id"], "?")} ({ev["id"]}) {at} s: "{ev["words"]}"{tail}'
    if ev["kind"] == "cue":
        return f'{ev["cue"]} cue {k.get(ev["id"], "?")} ({ev["id"]}) at {at} s: "{ev["words"]}"'
    if ev["kind"] == "pose" and not ev.get("auto"):
        return f"{ev['character']} pose ({ev['id']}) at {at} s: {ev['pose']}"
    return None


def listing(script: dict) -> str:
    """The listing: the context, then every scene, shot and event; whole words, so a change can be written from it."""
    out = ["The script:", *_context(script)]
    for n, scene in enumerate(script.get("scenes", []), 1):
        k = {ev["id"]: j for kind in ("line", "cue") for j, ev in refs._numbered(scene, kind)}
        asked = f" · asked {scene['seconds']} s" if "seconds" in scene else ""
        out.append(f'scene {n} "{scene["title"]}" · cast {", ".join(scene["cast"])} · runs '
                   f'{secs(length.length(scene))} s{asked}{" · done" if scene.get("done") else ""}')
        for j, shot in enumerate(scene["shots"], 1):
            cam = camera.of(shot)
            on = f" on {', '.join(cam['on'])}" if cam.get("on") else ""
            move = f" · {cam['move']}" if cam.get("move") else ""
            hold = f" · holds {shot['seconds']:g} s" if "seconds" in shot else ""
            did = f' · action: "{shot["action"]}"' if "action" in shot else ""
            out.append(f"shot {j} ({shot.get('id', '?')}) · {cam.get('framing', 'no framing')}{on}{move}{hold} · "
                       f"{secs(shot['start_ms'])}–{secs(shot['end_ms'])} s{did}")
            for ev in sorted(shot["events"], key=lambda e: (e["start_ms"], e["id"])):
                said = _event(ev, k)
                if said:
                    out.append(f"  {said}")
    if not script.get("scenes"):
        out.append("no scenes yet")
    return "\n".join(out)


def messages(script: dict, words: str, new: bool) -> list[dict]:
    rules = RULES + PLAIN + HELD + (STORY if new or not script.get("scenes") else "") + (NEW if new else "")
    return [{"role": "system", "content": f"{rules}\n\n{listing(script)}"},
            {"role": "user", "content": USER.format(words)}]


def send_back(reply: str, lines: list[str]) -> list[dict]:
    return [{"role": "assistant", "content": reply}, {"role": "user", "content": SEND_BACK.format("; ".join(lines))}]


# ---------------------------------------------------------------- the ordinary calls
def _no_way(text: str) -> Invalid:
    return Invalid("operation", text)


def scene_of(script: dict, op: dict, ref: dict | None = None) -> int:
    count = len(script.get("scenes", []))
    n = (ref or {}).get("scene") or op.get("scene") or count
    if not 1 <= n <= count:
        raise _no_way(f"there is no scene {n}" if count else "there is no scene yet: add_scene first")
    return n


def _shot(script: dict, n: int, k: int | None) -> dict:
    shots = script["scenes"][n - 1]["shots"]
    if not shots:
        raise _no_way(f"scene {n} has no shot: add_shot first")
    if k is None:
        return shots[-1]
    if not 1 <= k <= len(shots):
        raise _no_way(f"scene {n} has {len(shots)} shots, not {k}")
    return shots[k - 1]


def _resolve(script: dict, op: dict, ref: dict, tool: str) -> str:
    sent = {**ref, **({"scene": op["scene"]} if "scene" in op and "scene" not in ref else {})}
    try:
        return str(refs.resolve(script, {"ref": sent}, tool)[0]["id"])
    except Invalid as e:
        try:
            raise _no_way(str(json.loads(e.text)["problem"])) from None
        except (ValueError, KeyError, TypeError):
            raise _no_way(e.text) from None


def _at(script: dict, op: dict, n: int) -> tuple[dict, dict]:
    """The line `at` names (its shot, the line)."""
    at = op["at"]
    ident = _resolve(script, op, {"speaker": at["speaker"], "nth": at["nth"], "scene": n}, "event_change")
    _, shot, ev = edit.find_event(script, ident)
    return shot, ev


def _placed(script: dict, op: dict, n: int) -> tuple[dict, dict | None]:
    """The shot an add goes into (its number, else the `at` line's, else the scene's last) and its anchor."""
    if "at" in op:
        shot, line = _at(script, op, n)
        if "shot" in op and _shot(script, n, op["shot"]) is not shot:
            raise _no_way(f"{op['at']['speaker']}'s line {op['at']['nth']} is not in shot {op['shot']}")
        return shot, {"line": line["id"], "at": "end" if op["at"].get("end") else "start"}
    return _shot(script, n, op.get("shot")), None


def _kept(op: dict, keys: tuple[str, ...]) -> dict:
    return {k: op[k] for k in keys if k in op}


def _hold(op: dict) -> dict:
    """A shot's held length; the planner's own, never changed by the Hub (else sent back)."""
    if not isinstance(op.get("seconds"), (int, float)) or isinstance(op["seconds"], bool):
        return {}
    if not layout.held_seconds(op["seconds"]):
        raise _no_way(f"a shot holds up to {layout.HOLD_MAX_S:g} s, whole or tenths, not {op['seconds']:g}")
    return {"seconds": op["seconds"]}


def _whole(seconds: float) -> int:
    """A scene's length as sent (never rounded nor held to a range by the Hub); else refused, sent back."""
    if float(seconds).is_integer() and 1 <= seconds:
        return int(seconds)
    raise _no_way(f"a scene's length is a whole number of seconds from 1, not {seconds:g}")


def bare(script: dict) -> dict:
    """A copy without its panels (what the refs count)."""
    out = copy.deepcopy(script)
    panels.strip(out)
    return out


def calls(op: dict, script: dict, counters: dict) -> tuple[list[tuple[str, dict]], int | None]:
    """The operation as the ordinary tool calls on `script` (the trial as it stands, its `counters`) -> (the
    calls, the scene it touches); an operation that names nothing there raises `Invalid` with its line."""
    kind, script = op["op"], bare(script)
    if kind == "cast":
        return [("context_set", {"cast": [_kept(op, ("name", "look", "costume", "ignore", "home", "remove"))]})], None
    if kind == "picture":                                  # a member's picture_use, as the message says
        held = {m["name"].casefold(): m["name"] for m in script["context"]["cast"]}
        if op["name"].casefold() not in held:
            raise _no_way(f"{op['name']} is not in the cast")
        return [("context_set", {"cast": [{"name": held[op["name"].casefold()], "picture_use": op["picture_use"]}]})], \
            None
    if kind == "add_scene":
        cast = op.get("cast") or [m["name"] for m in script["context"]["cast"]]
        sec = {"seconds": _whole(op["seconds"])} if "seconds" in op else {}
        return [("scene_add", {"title": op["title"], "cast": cast, **sec})], len(script["scenes"]) + 1
    ref = op.get("ref") if isinstance(op.get("ref"), dict) else None
    n = scene_of(script, op, ref)
    if kind == "set_length":
        return [("scene_change", {"scene": n, "seconds": _whole(op["seconds"])})], n
    if kind == "add_shot":
        cam = _kept(op, ("framing", "on", "move"))      # a shot without a framing is a shot (no camera word asked)
        if op.get("after") == 0:
            raise _no_way("a shot cannot go before shot 1: leave after out, or name the shot it follows")
        after = {"after": _shot(script, n, op["after"])["id"]} if "after" in op else {}
        return [("shot_add", {"scene": n, "camera": cam, **after, **_hold(op), **_kept(op, ("action",))})], n
    if kind in ("add_line", "add_cue", "add_pose"):
        shot, anchor = _placed(script, op, n)
        if kind == "add_line":
            return [("line_add", {"shot": shot["id"], **_kept(op, ("speaker", "words", "emotion"))})], n
        if kind == "add_pose":
            return [("pose_add", {"shot": shot["id"], **_kept(op, ("character", "pose")),
                                  **({"anchor": anchor} if anchor else {})})], n
        out = [("cue_add", {"shot": shot["id"], **_kept(op, ("cue", "words")), **({"anchor": anchor} if anchor
                                                                                  else {})})]
        if "seconds" in op:
            cue = edit.next_id(copy.deepcopy(script), dict(counters), "c")
            out.append(("event_change", {"id": cue, "fields": {"seconds": op["seconds"]}}))
        return out, n
    if kind == "change_shot":
        k = (ref or {}).get("shot") or op.get("shot")
        cam = _kept(op, ("framing", "on", "move"))
        fields = {**({"camera": cam} if cam else {}), **_hold(op), **_kept(op, ("action",))}
        return [("event_change", {"id": _shot(script, n, k)["id"], "fields": fields})], n
    if ref is None:
        raise _no_way(f"{kind} needs ref")
    if kind == "remove":
        return [("event_remove", {"id": _resolve(script, op, ref, "event_remove")})], n
    ident = _resolve(script, op, ref, "event_change" if kind != "move" else "event_move")
    if kind in ("change_line", "change_cue"):
        keys = ("words", "emotion") if kind == "change_line" else ("words", "seconds")
        return [("event_change", {"id": ident, "fields": _kept(op, keys)})], n
    _, home, ev = edit.find_event(script, ident)            # move
    if "at" in op:
        shot, line = _at(script, op, n)
        start = line["end_ms" if op["at"].get("end") else "start_ms"]
    else:
        shot = _shot(script, n, op["shot"]) if "shot" in op else home
        start = max((e["end_ms"] for e in lines_of(shot) if e is not ev), default=shot["start_ms"])
    return [("event_move", {"id": ident, "shot": shot["id"], "start_ms": start - shot["start_ms"]})], n
