"""The pictures a part sends, per person in frame, as media ids in box order.

Per person, in the order `who` names them: with an approved sheet (Casting's `<Characters>/<Name>/casting.json`, read
raw, never through Casting's code) its `face-1`, `front` and `face-2` views whose files are there; else the picture then
its views (`<Name>.<view>.*` beside it); each at most `EACH`. Then taken round-robin (everyone's first, then everyone's
second …) up to the model's cap, and kept grouped by person in box order. Refused in one line: nobody in frame, more
people than the cap, a person with no picture in Characters.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from hub.core.api import Ctx, Invalid

EACH = 3
SHEET = ("face-1", "front", "face-2")
RECORD = "casting.json"
NOBODY = "shot {} shows nobody; {} needs a person's picture"
CROWD = "shot {} shows {} people; {} takes {} pictures"
NO_PICTURE = "{} has no picture in Characters"


def sheet(ctx: Ctx, name: str) -> list[str]:
    """The character's approved sheet's views (`SHEET` order) whose files are there, as media ids; [] with none."""
    root = ctx.files.roots.get("chars")
    if root is None:
        return []
    home = Path(root) / name
    try:
        record = json.loads((home / RECORD).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    views = record.get("sheet") if isinstance(record, dict) and isinstance(record.get("sheet"), dict) else {}
    out = []
    for view in SHEET:
        rel = (views.get(view) or {}).get("file") if isinstance(views.get(view), dict) else None
        if isinstance(rel, str) and rel and not rel.startswith(("/", "\\")) and "\\" not in rel \
                and ".." not in rel.split("/") and (home / rel).is_file():
            out.append(f"chars/{name}/{rel}")
    return out


def own(ctx: Ctx, person: dict) -> list[str]:
    """A listed character's pictures, at most `EACH`: its sheet's, else its picture and its views."""
    found = sheet(ctx, person["name"]) or [person["id"], *ctx.files.character_views(person["name"])]
    return found[:EACH]


def pick(ctx: Ctx, shot: str, who: list[str], cap: int, label: str) -> list[dict[str, Any]]:
    """[{person (0-based in `who`), name (as listed), id}] in box order."""
    people = list(dict.fromkeys(str(n) for n in who if str(n).strip()))
    if not people:
        raise Invalid("pictures", NOBODY.format(shot, label))
    if len(people) > cap:
        raise Invalid("pictures", CROWD.format(shot, len(people), label, cap))
    listed = {c["name"].casefold(): c for c in ctx.files.characters()}
    each = []
    for name in people:
        person = listed.get(name.casefold())
        if person is None:
            raise Invalid("pictures", NO_PICTURE.format(name))
        each.append((person["name"], own(ctx, person)))
    taken = [0] * len(each)
    left = cap
    for depth in range(EACH):
        for k, (_, ids) in enumerate(each):
            if left and depth < len(ids):
                taken[k], left = taken[k] + 1, left - 1
    return [{"person": k, "name": name, "id": i} for k, (name, ids) in enumerate(each) for i in ids[:taken[k]]]
