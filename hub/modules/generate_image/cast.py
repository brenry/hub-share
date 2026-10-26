"""The reference boxes by character name, as the tool server reports them (`references`), and the characters.

A character is a picture in the Characters folder, named by its file (`ctx.files.characters`). The boxes
are the session's (`routes.session_part`, as the Generate window fills them: no tool sets
them); each is reported by its character's name, or by its file's name when it is not a character. On a model whose
boxes are identities (`models.identities`) each picture must be within 1:4 and 4:1 (`shape`), said at build time.
A character's views (`<Name>.<view>.*` beside its picture) go with the character: a box holding the character
sends its picture then its views, every one an identity of its name (`with_views`); the total stays within the model's
cap.
"""
from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Any

from PIL import Image

from hub.core.api import Ctx, Invalid, Reference

from . import models, routes

BOXES = 3


def label(ctx: Ctx, ref: dict) -> str:
    """A box as the tool server reports it: its picture's file name without the extension — for a character, its
    name (`chars/Character 1.png` is Character 1)."""
    return PurePosixPath(str(ref.get("id", ""))).stem


def labels(ctx: Ctx) -> list[str]:
    refs = routes.session_part(ctx).get("references")
    return [label(ctx, r) for r in refs if isinstance(r, dict) and isinstance(r.get("id"), str)] \
        if isinstance(refs, list) else []


def character_name(ctx: Ctx, item_id: Any) -> str | None:
    """The name of the character whose listed picture is `item_id`, else None: a plain file (a Temp upload, a Drive
    picture) has none, nor has an older file in the Characters folder that shares a stem with the listed one."""
    return next((c["name"] for c in ctx.files.characters() if c["id"] == item_id), None)


def name_ok(name: str, model_label: str) -> str:
    """A character's name as the manifest carries it; longer than the engine keeps (`models.NAME_MAX`): refused."""
    if len(name) > models.NAME_MAX:
        raise Invalid("references", f"{name} is too long for {model_label}: names are at most {models.NAME_MAX} "
                                    "characters")
    return name


def shape(n: int, w: Any, h: Any, model_label: str) -> None:
    """Identity `n` (from 1) refused in one line when its picture is outside 1:4 to 4:1 (the engine's own rule)."""
    if not models.in_shape(w, h):
        raise Invalid("references", f"Identity {n} is {w}×{h}: {model_label} takes pictures between 1:4 and 4:1")


def image(ctx: Ctx, item: Any, field: str) -> str:
    try:
        path = ctx.files.resolve(str(item)) if isinstance(item, str) and item else None
    except (KeyError, ValueError, OSError):
        path = None
    if path is None or not Path(path).is_file():
        raise Invalid(field, "An image is missing; add it again")
    return str(Path(path).resolve())


def identity(n: int, path: str, cut: bool, name: str | None, model: dict, model_label: str) -> Reference:
    """Identity `n`: its character's name when it is a listed character's (or its view) and the model takes
    names, its cut-out; its picture's shape checked first (the engine refuses it in a vaguer line)."""
    found = size(path)
    if found is not None:
        shape(n, *found, model_label)
    name = name if models.takes_names(model) else None
    return Reference(path, "identity", name_ok(name, model_label) if name is not None else None, cut)


def identities(ctx: Ctx, boxes: list[Box], cap: int, model: dict, model_label: str) -> list[Reference]:
    """The boxes (item id, path, cut-out) as identities, each character followed by its views (`with_views`): a
    fresh clip's boxes, and the boxes beside a continued clip."""
    return [identity(n, path, c, name, model, model_label)
            for n, (_, path, c, name) in enumerate(with_views(ctx, boxes, cap, model_label), 1)]


def size(path: Any) -> tuple[int, int] | None:
    """A picture file's width and height from its header; None when it cannot be read as a picture."""
    try:
        with Image.open(path) as im:
            return im.size
    except (OSError, ValueError):
        return None


def listing(ctx: Ctx) -> list[dict[str, Any]]:
    """The characters by name, each with its notes and the words for its voice when there are any, and
    whether it has a voice sample (`<Name>.wav`)."""
    return [{"name": c["name"], **({"notes": c["notes"]} if c.get("notes") else {}),
             **({"voice": c["voice"]} if c.get("voice") else {}), **({"sample": True} if c.get("sample") else {}),
             **({"views": len(c["views"])} if c.get("views") else {})}
            for c in ctx.files.characters()]


VIEWS_OVER = "{} takes {} identities; {} with its views makes {}"


Box = tuple[str, str, bool]                       # a box: item id, path, cut-out
Identity = tuple[str, str, bool, str | None]      # ... and the character's name, or None


def with_views(ctx: Ctx, boxes: list[Box], cap: int, model_label: str) -> list[Identity]:
    """The boxes (item id, path, cut-out) as (item id, path, cut-out, character name): each listed character followed
    by its views under its name and cut-out. Over `cap` in all: refused in one line naming the character."""
    out: list[tuple[str, str, bool, str | None]] = []
    for item_id, path, cut in boxes:
        name = character_name(ctx, item_id)
        out.append((item_id, path, cut, name))
        if name is not None:
            views = ctx.files.character_views(name)
            out.extend((v, str(ctx.files.existing_media(v)), cut, name) for v in views)
            if len(out) > cap:
                raise Invalid("references", VIEWS_OVER.format(model_label, cap, name, len(views) + 1))
    if len(out) > cap:
        raise Invalid("references", f"Too many references for this model ({len(out)} of {cap})")
    return out
