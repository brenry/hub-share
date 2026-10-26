"""The script tools' input schemas, by tool name in `INPUT`, in the order of
`tools.ACTIONS`. The MCP server checks each call's arguments by its schema (`hub/core/schema.py`: objects, arrays,
strings, no `anyOf`). `shot_add`'s camera is blueprint §2's object, `framing` required.
The three event tools take `ref` or `id`, which the tool checks (`refs.resolve`), as the schema cannot.
"""
from __future__ import annotations

from . import layout, scriptshape


def _s() -> dict:              # typed text, not blank, no length cap of the Hub's
    return {"type": "string", "minLength": 1}


def _obj(props: dict, required: tuple[str, ...] = ()) -> dict:
    return {"type": "object", "additionalProperties": False, "required": list(required), "properties": props}


ID = {"type": "string", "minLength": 1, "maxLength": 24}          # the Hub's ids
POSE = {"type": "string", "minLength": 1, "maxLength": 24}        # a name of `scriptshape.POSES`
MS = {"type": "integer", "minimum": 0}
ANCHOR = _obj({"line": ID, "at": {"type": "string", "enum": ["start", "end"]}}, ("line", "at"))
MEMBER = _obj({"name": _s(), "look": _s(), "costume": _s(), "ignore": _s(),
               "home": {"type": "integer", "minimum": 0, "maximum": 100}, "to": _s(),      # `to` renames
               "remove": {"type": "boolean"}}, ("name",))                                        # `remove` takes it out
PROP = _obj({"name": _s(), "owner": _s(), "description": _s()}, ("name",))
SET = _obj({"name": _s(), "description": _s(), "elements": {"type": "array", "items": _s()},
            "props": {"type": "array", "items": PROP}})
CAMERA = _obj({"framing": _s(), "move": _s(),
               "on": {"type": "array", "items": _s()}}, ())   # no framing needed
SCENE_NO = {"type": "integer", "minimum": 1}
HOLD = {"type": "number", "minimum": 0.1, "maximum": layout.HOLD_MAX_S}   # the least tenth
NONE = _obj({})
NTH = {"type": "integer", "minimum": 1}
REF = _obj({"speaker": _s(), "cue": {"type": "string", "enum": list(scriptshape.CUES)}, "shot": NTH, "nth": NTH,
            "scene": SCENE_NO})                    # one of its forms, checked by `refs.resolve`

INPUT = {
    "script_say": _obj({"words": _s()}, ("words",)),
    "script_start": _obj({"name": _s(), "story": _s()}, ("name", "story")),
    "context_set": _obj({"cast": {"type": "array", "items": MEMBER}, "set": SET, "style": _s()}),
    "scene_add": _obj({"title": _s(), "cast": {"type": "array", "minItems": 1, "items": _s()},
                       "seconds": {"type": "integer", "minimum": 1}}, ("title", "cast")),
    "scene_change": _obj({"scene": SCENE_NO, "seconds": {"type": "integer", "minimum": 0},
                          "done": {"type": "boolean"}}, ("scene",)),
    "shot_add": _obj({"scene": SCENE_NO, "camera": CAMERA, "after": ID, "seconds": HOLD,
                       "action": _s()}, ("scene", "camera")),
    "line_add": _obj({"shot": ID, "speaker": _s(), "words": _s(), "language": _s(), "emotion": _s(),
                      "pace": {"type": "number", "minimum": 0.1}},
                     ("shot", "speaker", "words")),
    "cue_add": _obj({"shot": ID, "cue": {"type": "string", "enum": list(scriptshape.CUES)}, "words": _s(),
                     "anchor": ANCHOR}, ("shot", "cue", "words")),
    "pose_add": _obj({"shot": ID, "character": _s(), "pose": POSE, "anchor": ANCHOR,
                      "start_ms": {"type": "integer", "minimum": 0, "maximum": 15_080}}, ("shot", "character", "pose")),
    "event_move": _obj({"ref": REF, "id": ID, "start_ms": MS, "shot": ID}, ("start_ms",)),     # ref or id
    "event_change": _obj({"ref": REF, "id": ID, "fields": {"type": "object", "maxProperties": 4}}, ("fields",)),
    "event_remove": _obj({"ref": REF, "id": ID}),
    "script_read": _obj({"name": _s()}),
    "script_lock": NONE,                               # on the open script
    "script_unlock": NONE,
}
