"""Voice samples beside a clip's pictures: the engine's audio references. Stdlib only.

The model's catalog entry names the letter under which `audio_guide` is a voice reference (`video.voice_reference`,
the facts file's: Ref2VA `A`, the clip family's handler `:113`); two and three references are `AB` and `ABD`
(the choices, `:769-779`), each letter not yet there appended in order as `refvideo` joins letters; the samples' real
paths are `audio_guide`, `audio_guide2`, `audio_guide3` (`wgp.py:1389-1396`). The engine shows them to the model as
`<Audio 1>`, `<Audio 2>`, `<Audio 3>` in that order (`text_encoder.py:139-140`). A kept soundtrack (`S`) is no
reference (`:978-979`), so a clip never carries both: voices beside a sound are refused, as is a model without the
letter and a fourth voice (`:1060`); the pictures must cover their count (`:1065`; the controller refuses first,
the engine again). Nothing is dropped.
"""
from __future__ import annotations

from typing import Any

try:
    from ..faults import Refused
except ImportError:  # run as a script by the engine's Python
    from faults import Refused

from .refvideo import add_to_sequence

NO_VOICE = "{} takes no voice reference"
VOICE_SOUND = "A voice reference and a kept sound do not mix"
VOICE_CONTINUE = "A continued clip takes no voice reference"
TOO_MANY = "{} takes at most {} voice references"
LETTERS = "ABD"                # the second and third references' letters, in order (`:769-779`)
KEYS = ("audio_guide", "audio_guide2", "audio_guide3")


def merge(task: dict[str, Any], request: Any, entry: dict, by: dict[str, list[Any]]) -> dict[str, Any]:
    """The clip's task with its voice references: the letters in `audio_prompt_type`, the samples under `KEYS`."""
    letters = str((entry.get("video") or {}).get("voice_reference") or "")
    name = entry.get("name") or request.model
    if not letters:
        raise Refused(NO_VOICE.format(name))
    if getattr(request, "sound", None):
        raise Refused(VOICE_SOUND)
    if by["source"]:
        raise Refused(VOICE_CONTINUE)
    voices = list(request.voices)
    if len(voices) > len(KEYS):
        raise Refused(TOO_MANY.format(name, len(KEYS)))
    return {**task, "audio_prompt_type": add_to_sequence(letters, LETTERS[:len(voices)]),
            **dict(zip(KEYS, voices, strict=False))}
