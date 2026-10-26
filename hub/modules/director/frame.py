"""The context and the frame of a script being written (blueprint A.3), pure, as `edit.py`: `context_set`
adds a cast member, replaces that member's given fields or renames it everywhere, and replaces the set's
and the style's given fields (`context.read` held), or takes a member out (`remove`, in one call, refused
only while the member has lines); `scene_add` appends a scene cast from the context, with the length named for it
(never refused for what an earlier scene runs); `scene_change` sets or clears that length, and
marks a scene done; `shot_add` inserts an empty shot (`layout.new_shot`), its camera the object; `change` is
`event_change`: a shot's camera, or a line's, cue's or pose's fields (`edit.event_change`). `shot_add` and a shot's
`change` take `seconds`, the shot's held length (`layout.held_seconds`; 0 takes it off), and `action`, what happens
in the shot (`layout.action_ok`)."""
from __future__ import annotations

import copy
from collections.abc import Mapping

from hub.core.api import Invalid

from . import air, camera, edit, layout, length, timing
from . import context as scene_context
from .edit import _scene, next_id, refuse


def _rename(script: dict, old: str, to: str) -> None:
    """`old` is `to` in the context's cast, a prop's owner, each scene's cast, each line's speaker and
    each pose's character; and in each shot's camera words; in its framing, move and on
    (`camera.renamed`)."""
    folded = old.casefold()
    cameras = camera.renamed(script, old, to)

    def same(value: object) -> bool:
        return isinstance(value, str) and value.casefold() == folded
    for shot, cam in cameras:
        shot["camera"] = cam
    for member in script["context"]["cast"]:
        if same(member["name"]):
            member["name"] = to
    for prop in script["context"].get("set", {}).get("props", []):
        if same(prop.get("owner")):
            prop["owner"] = to
    for scene in script["scenes"]:
        scene["cast"] = [to if same(n) else n for n in scene["cast"]]
        for shot in scene["shots"]:
            for ev in shot["events"]:
                key = {"line": "speaker", "pose": "character"}.get(ev.get("kind"))
                if key is not None and same(ev.get(key)):
                    ev[key] = to


def _to(script: dict, found: dict | None, member: dict, characters: Mapping[str, str], names: list[str],
        anyone: bool = False) -> str:
    """The checks on a member's `to` (not in the cast yet; a picture in Characters unless `anyone`); -> the
    did-line's `old → to`."""
    cast = [m["name"] for m in script["context"]["cast"]]
    if found is None:
        raise refuse(f"{member['name']} is not in the context's cast", "Name a member of the context's cast to rename",
                     context_cast=cast)
    to = member["to"]
    if to.casefold() != found["name"].casefold() and to.casefold() in {n.casefold() for n in cast}:
        raise refuse(f"{to} is in the context's cast already", "Rename to a name not in the cast", context_cast=cast)
    if not anyone and to.casefold() not in characters:
        raise refuse(f"Cast and set, cast {to}: {to} has no picture in Characters",
                     "Cast only names that have a picture in Characters", characters=names)
    old = found["name"]
    _rename(script, old, to)
    return f"{old} → {to}"


def _uses(script: dict, folded: str) -> dict[str, list]:
    """Where the script still names a member: line and pose ids, scene numbers, prop names."""
    def same(value: object) -> bool:
        return isinstance(value, str) and value.casefold() == folded
    uses: dict[str, list] = {"lines": [], "poses": [], "scenes": [], "props": []}
    for n, scene in enumerate(script["scenes"], 1):
        if any(same(name) for name in scene["cast"]):
            uses["scenes"].append(n)
        for shot in scene["shots"]:
            for ev in shot["events"]:
                key = {"line": ("speaker", "lines"), "pose": ("character", "poses")}.get(ev.get("kind"))
                if key is not None and same(ev.get(key[0])):
                    uses[key[1]].append(ev.get("id"))
    uses["props"] = [p.get("name") for p in script["context"].get("set", {}).get("props", []) if same(p.get("owner"))]
    return uses


def _remove(script: dict, found: dict | None, member: dict, pace: float | None) -> tuple[str, dict | None]:
    """The member out of the context's cast, every scene's cast and every
    pose, the member's props kept with no owner, in one call, refused only while the member has lines; the script timed
    again when a pose went. -> (the did-line, the timing's moves)."""
    cast = script["context"]["cast"]
    if "to" in member:
        raise refuse("remove or to, not both", "Send remove or to for a member, not both",
                     context_cast=[m["name"] for m in cast])
    if found is None:
        raise refuse(f"{member['name']} is not in the context's cast", "Name a member of the context's cast to remove",
                     context_cast=[m["name"] for m in cast])
    folded = found["name"].casefold()
    uses = _uses(script, folded)
    if uses["lines"]:
        raise refuse(f"{found['name']} still has lines", "Remove those lines with event_remove, then send this again",
                     lines=uses["lines"])
    before = copy.deepcopy(script)
    for scene in script["scenes"]:
        scene["cast"] = [n for n in scene["cast"] if n.casefold() != folded]
        camera.remove({"scenes": [scene]}, folded)       # out of each shot's on too
        for shot in scene["shots"]:
            shot["events"] = [ev for ev in shot["events"] if not (ev.get("kind") == "pose" and isinstance(
                ev.get("character"), str) and ev["character"].casefold() == folded)]
    for prop in script["context"].get("set", {}).get("props", []):
        if isinstance(prop.get("owner"), str) and prop["owner"].casefold() == folded:
            prop["owner"] = None
    cast.remove(found)
    moves = timing.retime(before, script, None, "remove", pace)[1] if uses["poses"] else None
    parts = [f"removed {found['name']}"]
    for key, what in (("poses", "poses"), ("scenes", "scenes"), ("props", "props")):
        if uses[key]:
            parts.append(f"{what} {', '.join(str(v) for v in uses[key])}")
    return " · ".join(parts), moves


def _add(moves: dict | None, more: dict | None) -> dict | None:
    """Two calls' moves as one (`edit.settle`'s sum)."""
    if more is None:
        return moves
    moves = moves or {"events": {}, "shots": {}}
    for part, by_id in more.items():
        for k, by in by_id.items():
            moves[part][k] = moves[part].get(k, 0) + by
    return moves


def context_set(script: dict, args: dict, characters: Mapping[str, str], names: list[str],
              pace: float | None = None, anyone: bool = False) -> dict:
    """A member by name added, or that member's given fields replaced, or renamed everywhere by `to`, or taken out
    by `remove` (timed again at `pace`); the set's and the style's given fields replaced. A new member must have a
    picture in Characters; an existing one without a picture may still be changed.
    `anyone` (the chat message through `script_say`): no picture needed, new or renamed."""
    held = script["context"]
    added: list[dict] = []
    renamed: list[str] = []
    moves: dict | None = None
    for member in args.get("cast", []):
        found = next((m for m in held["cast"] if m["name"].casefold() == member["name"].casefold()), None)
        fields = {k: v for k, v in member.items() if k not in ("name", "to", "remove")}
        if member.get("remove"):
            did, more = _remove(script, found, member, pace)
            renamed.append(did)
            moves = _add(moves, more)
            continue
        if "to" in member:
            renamed.append(_to(script, found, member, characters, names, anyone))
            found = next(m for m in held["cast"] if m["name"] == member["to"])
        if found is None:
            held["cast"].append({k: v for k, v in member.items() if k not in ("to", "remove")})
            added.append(held["cast"][-1])
        else:
            found.update(fields)
    if "set" in args:
        held["set"] = {**held.get("set", {}), **args["set"]}
    if "style" in args:
        held["style"] = args["style"]
    try:
        scene_context.read(held, characters)
    except Invalid as e:
        raise refuse(e.text, "Send that field again as the line says") from None
    try:
        if not anyone:
            scene_context.pictured({"cast": added}, characters)
    except Invalid as e:
        raise refuse(e.text, "Cast only names that have a picture in Characters", characters=names) from None
    parts = [*renamed, f"cast {', '.join(m['name'] for m in held['cast'])}" if held["cast"] else "no cast"]
    if "set" in held:
        parts.append(f"set {held['set'].get('name', '')}")
    if "style" in held:
        parts.append("style")
    return {"did": "context · " + " · ".join(parts), "shot": None, "moved": moves}


def scene_add(script: dict, args: dict, pace: float | None = None) -> dict:
    context_cast = [m["name"] for m in script["context"]["cast"]]
    folded = {n.casefold(): n for n in context_cast}
    cast: list[str] = []
    for name in args["cast"]:
        if name.casefold() not in folded:
            raise refuse(f"{name} is not in the context's cast", f"Call context_set with {name} first",
                         context_cast=context_cast)
        if folded[name.casefold()] in cast:
            raise refuse(f"{name} is in the cast twice", "Name each member once", context_cast=context_cast)
        cast.append(folded[name.casefold()])
    scene = {"title": args["title"], "cast": cast, "shots": [], **({"seconds": args["seconds"]} if "seconds" in args
                                                                     else {})}
    script["scenes"].append(scene)
    n = len(script["scenes"])
    return {"did": f"scene {n} · {args['title']}{length.asked(scene)}", "shot": None, "scene": n}


def scene_change(script: dict, args: dict, pace: float | None = None) -> dict:
    """The length named for scene `scene`, in whole seconds; 0 takes it off. Answered with the length asked, the
    length run and the dead air (`air.told`). `done: true` is
    recorded on the scene with no check; it is the Director's mark that the scene is written and gates nothing."""
    n, done = args["scene"], args.get("done") is True
    if "seconds" not in args and not done:
        raise refuse("Send seconds, done or both", "scene_change {scene, seconds} sets the length named for the scene; "
                     "scene_change {scene, done: true} when the scene is written")
    scene = _scene(script, n)
    if args.get("seconds"):
        scene["seconds"] = args["seconds"]
    elif "seconds" in args:
        scene.pop("seconds", None)
        if not done:
            return {"did": f"scene {n} · no length asked", "shot": None, "scene": n}
    if done:
        scene["done"] = True                              # recorded
    return {"did": air.told(scene, n, done)[0], "shot": None, "scene": n}


def shot_add(script: dict, counters: dict, args: dict) -> dict:
    scene = _scene(script, args["scene"])
    after = None
    if "after" in args:
        after = next((s for s in scene["shots"] if s.get("id") == args["after"]), None)
        if after is None:
            raise refuse(f"Scene {args['scene']} has no shot {args['after']}", "Name a shot of that scene, or leave "
                         "after out", shots=[s.get("id") for s in scene["shots"]])
    cam = camera.merged({}, args["camera"], scene["cast"], args["scene"])     # text is its framing
    hold = _hold(args.get("seconds"), False)
    action = layout.action(args.get("action"))
    shot = layout.new_shot(script, scene, after, next_id(script, counters, "s"), cam, hold)
    if action:
        shot["action"] = action
    held = f" · holds {hold:g} s" if hold else ""
    return {"did": f"shot {shot['id']} · scene {args['scene']} · {camera.said(shot)}{held}", "shot": shot,
            "scene": args["scene"]}


def _hold(value: object, off: bool) -> float | int | None:
    """A held length sent, checked; None when none is sent (`off`: 0 takes it off, answered 0)."""
    if value is None or off and value == 0 and not isinstance(value, bool):
        return None if value is None else 0
    if not layout.held_seconds(value):
        raise refuse(f"A shot holds up to {layout.HOLD_MAX_S:g} s, whole or tenths", "Send seconds in that range"
                     + (", or 0 to take it off" if off else ""), most_seconds=layout.HOLD_MAX_S)
    return round(float(value), 1) if isinstance(value, float) and not float(value).is_integer() else int(value)


def change(script: dict, args: dict, pace: float | None = None) -> dict:
    """`event_change` of a shot id changes that shot's camera; the keys given merged into
    its object (`camera.merged`; text is its framing); any other id goes to `edit.event_change`."""
    found = next(((n, shot) for n, sc in enumerate(script["scenes"], 1) for shot in sc["shots"]
                  if shot.get("id") == args["id"]), None)
    if found is None:
        return edit.event_change(script, args, pace=pace)
    n, shot = found
    fields = args["fields"]
    wrong = [k for k in fields if k not in ("camera", "seconds", "action")]
    if wrong or not fields:
        raise refuse(f"A shot has no field {wrong[0]}" if wrong else "No field to change",
                     "Change a shot's camera, its seconds or its action", fields=["camera", "seconds", "action"])
    parts = []
    if "camera" in fields:
        shot["camera"] = camera.merged(shot, fields["camera"], script["scenes"][n - 1]["cast"], n)
        parts.append(f"camera {camera.said(shot)}")
    if "action" in fields:                                # what happens in it, as written
        if isinstance(fields["action"], str) and not fields["action"].strip():
            shot.pop("action", None)                      # sent empty: taken off
        else:
            shot["action"] = layout.action(fields["action"])
        parts.append("its action")
    if "seconds" not in fields:
        return {"did": f"changed shot {shot['id']} · {' · '.join(parts)}", "shot": shot, "scene": n}
    hold = _hold(fields["seconds"], True)                 # the held length, timed again
    before = copy.deepcopy(script)
    if hold:
        shot["seconds"] = hold
    else:
        shot.pop("seconds", None)
    moved = timing.retime(before, script, None, "change", pace)[1]
    parts.append(f"holds {hold:g} s" if hold else "holds no length")
    return {"did": f"changed shot {shot['id']} · {' · '.join(parts)}", "shot": shot, "scene": n, "moved": moved}
