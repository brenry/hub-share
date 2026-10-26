"""The voice samples a clip takes as its audio references: the session's shot's voiced speakers
(`shotcheck.frame`, `Frame.voices`), each the speaker's `<Name>.wav` beside its picture, read where it is, sent absolute
in audio-number order. Each is at least `SHORTEST` s (the engine's floor, the clip family's handler `:1055`; read
from the file itself, `sound_exact`); there are at most `MOST` (`:1060`) and no more than the pictures sent
(`:1065`, views counted); none beside a Sound-box sound (a kept soundtrack is no reference, `:978-979`). Each
refusal is one line before any job. Without a shot, or with no voiced speaker, nothing: the model's own voice.
"""
from __future__ import annotations

import os
from pathlib import Path

from hub.core.api import Ctx, Invalid, sound_exact

from . import routes, voiced

SHORTEST = 2.0
MOST = 3
VOICE_SHORT = "{}'s voice sample is under {:g} s"
VOICE_UNREAD = "{}'s voice sample cannot be read"
VOICE_SOUND = "A voiced line and a sound in the Sound box do not mix"
VOICES_OVER = "{} voiced speakers need {} pictures in the boxes; there are {}"
VOICES_MOST = "{} takes at most {} voices in one clip"


def voices(ctx: Ctx, model: dict, ui: dict, heard: bool, pictures: int) -> list[str]:
    """The samples' real paths for the session's shot ([] when it has no voiced speaker), checked."""
    from . import shotcheck  # late: `screen` reads it at import, and `shotcheck` reads `screen` through `chain`

    shot = routes.session_part(ctx).get("shot")
    if not isinstance(shot, dict):
        return []
    where = shotcheck.frame(ctx, model, ui["label"], shot)
    if not where.voices:
        return []
    if heard:
        raise Invalid("sound", VOICE_SOUND)
    if len(where.voices) > MOST:
        raise Invalid("shot", VOICES_MOST.format(ui["label"], MOST))
    if len(where.voices) > pictures:
        raise Invalid("references", VOICES_OVER.format(len(where.voices), len(where.voices), pictures))
    listed = voiced.characters(ctx)
    return [sample(ctx, listed[who]["name"]) for who, _ in sorted(where.voices.items(), key=lambda kv: kv[1])]


def sample(ctx: Ctx, name: str) -> str:
    """The speaker's `<Name>.wav`'s real path, read where it is: readable and at least `SHORTEST` s, else one line."""
    real = Path(os.path.realpath(ctx.files.character_sample(name)))
    try:
        seconds = sound_exact(real)
    except (OSError, ValueError):
        raise Invalid("shot", VOICE_UNREAD.format(name)) from None
    if seconds < SHORTEST:
        raise Invalid("shot", VOICE_SHORT.format(name, SHORTEST))
    return str(real)

