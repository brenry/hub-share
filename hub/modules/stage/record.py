"""A set's record and files: `<data>/sets/<Name>/` with `set.json`, `plates/*.png`, `pan.mp4`,
`pictures/<n>.<ext>` and, with a house, `house/*.png` and `house/pan.mp4`. Written only on Approve.

`approve(ctx, draft)` copies (never moves: the Temp ids stay in Media) every new file beside its place under
`TEMP`, the input pictures through `api.strip_picture`; a copy that fails erases them all and leaves the set as it was;
then each is put in its place (`os.replace`) and `set.json` written (`api.write_json`). A build writes revision 1; a
change, a house and a house change raise it by one (every plate a panel may stand on is new). A rewrite keeps every key
it does not own (`floor_plan`, `style`, anything a later step adds). No prompt, seed, chat or job is recorded. Its known
low, as the Casting record's: a failure between two `os.replace` can mix plates. `read`, `ids` (media ids
`sets/<Name>/…`), `approved` (the tab's files, each url with its version) and `delete` (the folder).
"""
from __future__ import annotations

import datetime
import json
import os
import shutil
from pathlib import Path
from typing import Any
from urllib.parse import quote

from PIL import Image

from hub.core.api import Ctx, Invalid, strip_picture, write_json

from . import change

ROOT, RECORD, PAN, VERSION = "sets", "set.json", "pan.mp4", 1
STAGE = {"wide": 20, "left": 44, "centre": 68, "right": 92, "audience": 166}    # plate -> its frame (R51)
HOUSE = {"wide": 20, "left": 44, "right": 116, "row": 166}
STAGE_SHOTS = {"wide": ("wide", "wide", "the whole stage"), "left": ("1", "medium-wide", "stage centre"),
               "centre": ("2", "medium-wide", "stage centre"), "right": ("3", "medium-wide", "stage centre"),
               "audience": ("rev", "wide", "the seats")}                         # camera, framing, aim
HOUSE_SHOTS = {"wide": ("rev", "wide", "the whole audience"), "left": ("house_left", "medium-wide", "the audience"),
               "right": ("house_right", "medium-wide", "the audience"), "row": ("rev", "medium", "the rows")}
CAMERA_PLAN = "three_camera"             # R53's preset whose camera names the plates carry
AUDIENCES = ("none", "heard", "seen")
TEMP = ".{}.hub-new"
NOT_READY = "There are no plates to approve"
LOST = "A plate is gone; render it again"
UNWRITTEN = "Could not write {}: {}"


def root(ctx: Ctx) -> Path:
    return Path(ctx.files.roots[ROOT])


def find(ctx: Ctx, name: str) -> str | None:
    """The approved set's name as its folder has it (case-folded match), else None."""
    want = name.casefold()
    try:
        return next((p.name for p in root(ctx).iterdir() if p.name.casefold() == want and (p / RECORD).is_file()),
                    None)
    except OSError:
        return None


def names(ctx: Ctx) -> list[str]:
    try:
        return sorted((p.name for p in root(ctx).iterdir() if (p / RECORD).is_file()), key=str.casefold)
    except OSError:
        return []


def read(ctx: Ctx, name: str) -> dict[str, Any] | None:
    """The approved record, else None."""
    found = find(ctx, name)
    try:
        with open(root(ctx) / str(found) / RECORD, encoding="utf-8") as f:
            record = json.load(f)
    except (OSError, ValueError):
        return None
    return record if found and isinstance(record, dict) else None


def _plates(record: dict[str, Any], key: str) -> dict[str, Any]:
    part = record.get("house") if key == "house" else record
    plates = part.get("plates") if isinstance(part, dict) else None
    return plates if isinstance(plates, dict) else {}


def ids(name: str, record: dict[str, Any]) -> dict[str, Any]:
    """{plates: {plate: id}, house: {plate: id} | None, pictures: [id]}, ids as Media takes them."""
    def at(entry: Any) -> str | None:
        rel = entry.get("file") if isinstance(entry, dict) else None
        return f"{ROOT}/{name}/{rel}" if isinstance(rel, str) and rel else None
    house = _plates(record, "house")
    return {"plates": {p: at(_plates(record, "stage").get(p)) for p in STAGE},
            "house": {p: at(house.get(p)) for p in HOUSE} if house else None,
            "pictures": [i for p in record.get("pictures") or [] if (i := at(p))]}


def file(ctx: Ctx, item: str | None) -> dict[str, Any] | None:
    """A media id as the tab takes it: {id, url, thumb} (each address versioned by its mtime)."""
    return {"id": item, "url": ctx.files.url(item), "thumb": ctx.files.thumb_url(item)} if item else None


def pan_url(ctx: Ctx, name: str, which: str) -> str | None:
    path = root(ctx) / name / ("house/" + PAN if which == "house" else PAN)
    try:
        version = path.stat().st_mtime_ns
    except OSError:
        return None
    return f"/api/stage/pan?name={quote(name)}&which={which}&v={version}"


def approved(ctx: Ctx, name: str, record: dict[str, Any]) -> dict[str, Any]:
    """The tab's `Approved` (routes docstring)."""
    found = ids(name, record)
    house = found["house"]
    return {"record": record, "plates": {p: file(ctx, i) for p, i in found["plates"].items()},
            "house": {p: file(ctx, i) for p, i in house.items()} if house else None,
            "pan_url": pan_url(ctx, name, "stage"), "house_pan_url": pan_url(ctx, name, "house") if house else None,
            "pictures": [file(ctx, i) for i in found["pictures"]]}


def _source(ctx: Ctx, item: Any) -> Path:
    try:
        return ctx.files.existing_media(str(item))
    except Invalid:
        raise Invalid("approve", LOST) from None


def _staged(folder: Path, rel: str) -> Path:
    return folder / Path(rel).parent / TEMP.format(Path(rel).name)


def _copy(folder: Path, files: dict[str, Path], strip: set[str]) -> None:
    """Every file staged beside its place, then each put there; a failure erases what was staged and raises."""
    staged: list[Path] = []
    made = [d for d in {folder, *(folder / Path(rel).parent for rel in files)} if not d.exists()]
    try:
        for rel, src in files.items():
            (folder / rel).parent.mkdir(parents=True, exist_ok=True)
            staged.append(_staged(folder, rel))
            shutil.copyfile(src, staged[-1])
            if rel in strip:
                strip_picture(staged[-1])
        for rel in files:
            os.replace(_staged(folder, rel), folder / rel)
    except (OSError, ValueError):
        for tmp in staged:
            tmp.unlink(missing_ok=True)
            tmp.with_name(f".{tmp.name}.clean").unlink(missing_ok=True)
        for d in sorted(made, key=lambda p: len(p.parts), reverse=True):
            if d.is_dir() and not any(d.iterdir()):
                d.rmdir()
        raise


def _shots(table: dict[str, int], shots: dict[str, tuple[str, str, str]], sub: str) -> dict[str, Any]:
    return {p: {"file": f"{sub}{p}.png", "frame": frame, "camera": shots[p][0], "framing": shots[p][1],
                "aim": shots[p][2]} for p, frame in table.items()}


def _format(path: Path, fps: Any) -> dict[str, Any]:
    with Image.open(path) as im:
        width, height = im.size
    crop = round(height * 4 / 3)
    return {"aspect": "16:9", "width": width, "height": height, "fps": fps,
            "crop_4_3": {"x": (width - crop) // 2, "y": 0, "width": crop, "height": height}}


def approve(ctx: Ctx, draft: dict[str, Any]) -> dict[str, Any]:
    """The draft's plates and pan written to the set's folder (the module docstring); -> the record written."""
    name, mode = draft["name"], draft["mode"]
    house = mode.startswith("house")
    table = HOUSE if house else STAGE
    plates, pan = draft.get("plates") or {}, draft.get("pan")
    if draft.get("state") != "ready" or not pan or set(plates) != set(table):
        raise Invalid("approve", NOT_READY)
    old = read(ctx, name)
    if mode != "build" and old is None:
        raise Invalid("approve", NOT_READY)
    name = find(ctx, name) or name
    folder = root(ctx) / name
    prefix = "house/" if house else ""
    sub = "house/" if house else "plates/"
    files = {f"{sub}{p}.png": _source(ctx, plates[p]) for p in table}
    files[prefix + PAN] = _source(ctx, pan)
    inputs = draft.get("inputs") or {}
    pictures = []
    if mode == "build":
        for n, pic in enumerate(inputs.get("pictures") or [], 1):
            src = _source(ctx, pic["id"])
            pictures.append({"file": f"pictures/{n}{src.suffix.lower()}", "keep": pic.get("keep", "")})
            files[pictures[-1]["file"]] = src
    _copy(folder, files, {p["file"] for p in pictures})
    facts = draft.get("facts") or {}
    record = dict(old or {})
    pan_entry = {"file": prefix + PAN, "frames": facts.get("frames")}
    if mode == "build":
        record.update(version=VERSION, name=name, revision=1, description=inputs.get("description", ""),
                      elements=list(inputs.get("pieces") or []), props=[], changes=[], pictures=pictures,
                      camera_plan=CAMERA_PLAN, audience=inputs.get("audience", "seen"), house=None, lighting=None)
    else:
        record["revision"] = int(record.get("revision") or 1) + 1
    if mode == "change":
        record.update(change.apply(record, draft.get("op") or {"words": draft.get("words")}))
    if not house:
        record.update(format=_format(folder / "plates" / "wide.png", facts.get("fps")), pan=pan_entry,
                      plates=_shots(STAGE, STAGE_SHOTS, sub))
    else:
        was = record.get("house") if isinstance(record.get("house"), dict) else {}
        words = (inputs.get("house") or {}) if mode == "house" else was
        changes = [*(was.get("changes") or [])] if mode == "house-change" else []
        if mode == "house-change":
            changes.append(draft.get("words") or "")
        record["house"] = {**was, **{k: str(words.get(k) or "") for k in ("era", "dress", "hair", "size")},
                           "changes": changes, "pan": pan_entry, "plates": _shots(HOUSE, HOUSE_SHOTS, sub)}
    record.update(name=name, model=draft.get("model") or "",                 # its name is its folder's
                  approved=datetime.datetime.now().astimezone().isoformat(timespec="seconds"))
    write_json(folder / RECORD, record, 0o644)
    return record


def set_audience(ctx: Ctx, name: str, audience: str) -> dict[str, Any]:
    """The record's `audience` written at once (no plate changes: the revision stays)."""
    record = read(ctx, name)
    if record is None:
        raise Invalid("name", f"Approve {name}'s plates first")
    record["audience"] = audience
    write_json(root(ctx) / str(find(ctx, name)) / RECORD, record, 0o644)
    return record


def delete(ctx: Ctx, name: str) -> None:
    found = find(ctx, name)
    if found is not None:
        shutil.rmtree(root(ctx) / found)
