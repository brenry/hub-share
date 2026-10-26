"""HTTP routes: the model list, the draft and the model defaults.

The draft is in two parts. Settings (model, LoRAs and strengths, size, count, steps, guidance, seed mode, and the
last-picked model of each kind, `lastModel`) are saved to `draft.json`. The
prompt text (the prompt box: typed on the screen, never written by a tool), the assistant's draft prompt (`draft`,
the tool server's setting; a window writes it only to clear it), the reference boxes and the selection are the
session's: held in memory, handed back on reload, forgotten when the session ends. They are never on disk.
New chat (`chat.cleared`, from the assistant module) empties the prompt and the draft; the references stay.
Saved model ids follow an engine line that renames models (`rename.adopt`): the draft remembers the line they were
brought over to (`engine`).
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from PIL import Image
from starlette.requests import Request
from starlette.responses import JSONResponse

from hub.core.api import CardState, Ctx, Invalid

from . import models

DRAFT, DEFAULTS = "draft", "defaults"
NO_DEFAULTS: dict[str, str | None] = {"text": None, "refs": None, "video": None}
SESSION_FIELDS = ("prompt", "draft", "references", "sound", "video", "selected")   # the Sound and Video boxes
SAVED_FIELDS = ("model", "lorasByModel", "aspect", "size", "images", "advancedByModel", "lastModel", "engine")
SERVER_FIELDS = ("model", "lastModel", "engine")   # saved fields a window never writes as they are
KINDS = ("image", "video")                 # `lastModel`: the last-picked model of each kind, the server's alone
_session: dict[Path, dict[str, Any]] = {}


def settle(ctx: Ctx) -> None:
    """The draft on disk holds the saved fields and nothing else: whatever an older hub wrote there (a prompt, the
    references, an edit image) is dropped, now."""
    doc = ctx.doc(DRAFT, {})
    saved = doc.get()
    kept = {k: v for k, v in saved.items() if k in SAVED_FIELDS}
    if kept != saved:
        doc.replace(kept)


def session_part(ctx: Ctx) -> dict[str, Any]:
    return _session.setdefault(ctx.data_dir, {})


async def on_session_ended(ctx: Ctx, data: dict) -> None:
    """The session ended: the prompt, the assistant's draft, the reference boxes and the selection are gone."""
    _session.pop(ctx.data_dir, None)


async def on_chat_cleared(ctx: Ctx, data: dict) -> None:
    """New chat: the prompt box and the assistant's draft empty with the conversation (the reference boxes and the
    selection stay); every open Generate window redraws. With neither held, nothing changes and nothing is told."""
    held = _session.get(ctx.data_dir) or {}
    if not (held.get("prompt") or held.get("draft")):
        return
    held.update({"prompt": "", "draft": ""})
    held.pop("shot", None)
    ctx.bus.publish("changed", "draft", {})


async def get_models(ctx: Ctx, request: Request) -> Any:
    """The usable models. `?rescan=1` (the screen on a page refresh) makes the engine look at the folders again."""
    try:
        cat = await models.catalog(ctx, rescan=request.query_params.get("rescan") == "1")
    except Exception as exc:
        return unavailable(exc)
    caps = models.ref_caps(ctx)
    return [models.ui_model(m, caps) for m in models.present(cat)]


def unavailable(exc: BaseException) -> JSONResponse:
    """The engine could not answer: 503 with its own one plain line."""
    return JSONResponse({"code": "unavailable", "text": models.reason(exc)}, status_code=503)


async def _panel(ctx: Ctx, choose: tuple[str, str] | None = None, rescan: bool = False) -> Any:
    try:
        panel = await ctx.engine.query("weights", choose=choose, rescan=rescan)
        await models.catalog(ctx)                  # the job builder's copy follows the rescan
    except Exception as exc:
        return unavailable(exc)
    return panel


async def get_weights(ctx: Ctx, request: Request) -> Any:
    """The Image models panel: the models a file can be set up like and one record per weight file
    ({path, name, folder, size_mb, status: known|pointer|unknown, model, base, suggested, candidates, chosen})."""
    return await _panel(ctx)


async def rescan(ctx: Ctx, request: Request) -> Any:
    """Look at the model folders again (new files, removed files), then the panel."""
    return await _panel(ctx, rescan=True)


async def choose_base(ctx: Ctx, request: Request) -> Any:
    """The chosen base for a weight file: {"path", "base"}; base "" = not a model. Then the panel."""
    body: Any = await request.json()
    path = body.get("path") if isinstance(body, dict) else None
    base = body.get("base") if isinstance(body, dict) else None
    if not isinstance(path, str) or not path or not isinstance(base, str):
        raise Invalid("path", "Send the file's path and the model to set it up like")
    panel = await _panel(ctx)
    if isinstance(panel, JSONResponse):
        return panel
    if path not in {f["path"] for f in panel["files"]}:
        raise Invalid("path", "That file is not in the model folders")
    if base in {f["model"] for f in panel["files"] if f["status"] == "pointer"}:
        raise Invalid("base", "That model is itself a file the Hub set up; pick the model it is set up like")
    if base and base not in {b["id"] for b in panel["bases"]}:
        raise Invalid("base", "Pick one of the models listed")
    return await _panel(ctx, (path, base))


def card(ctx: Ctx) -> CardState:
    """Settings card: the current model's seed (guidance has no summary; it is per model and rarely set)."""
    d = ctx.doc(DRAFT, {}).get()
    adv = (d.get("advancedByModel") or {}).get(d.get("model")) or {}
    seed = adv.get("seed") if isinstance(adv.get("seed"), dict) else {}
    fixed = seed.get("mode") == "fixed" and "value" in seed
    return CardState(f"Seed {seed['value']}" if fixed else "Random seed", "ok")


def _body(raw: bytes, field: str) -> dict:
    try:
        body = json.loads(raw)
    except ValueError:
        raise Invalid(field, f"The {field} is not valid JSON") from None
    if not isinstance(body, dict):
        raise Invalid(field, f"The {field} must be a JSON object")
    return body


async def get_draft(ctx: Ctx, request: Request) -> dict:
    saved = {k: v for k, v in ctx.doc(DRAFT, {}).get().items() if k in SAVED_FIELDS}
    return {**saved, **session_part(ctx)}


async def put_draft(ctx: Ctx, request: Request) -> dict:
    """A window sends the fields it changed; they merge into what is held (so a window and the tool server never
    write over each other); a card's detail the model does not announce is refused first. A `model` sent becomes the
    last-picked of its kind (`lastModel`, which a window never writes). Returns the whole draft after."""
    draft = _body(await request.body(), "draft")
    doc = ctx.doc(DRAFT, {})
    await _check_detail(ctx, draft, {k: v for k, v in doc.get().items() if k in SAVED_FIELDS})   # nothing held yet
    cat = None
    if "model" in draft:
        try:
            cat = await models.catalog(ctx)
        except Exception:
            cat = models.cached()                       # the engine did not answer: what it last listed
    saved = {k: v for k, v in doc.get().items() if k in SAVED_FIELDS}   # read after the awaits (`rename.adopt`)
    from . import rename  # late: it reads this module

    draft = rename.window(draft, saved, cat or models.cached())        # a window that loaded before a move
    session_part(ctx).update({k: v for k, v in draft.items() if k in SESSION_FIELDS})
    if "draft" in draft:                                  # the panel's Clear (or an edit): a plain draft again
        session_part(ctx).pop("shot", None)
    saved.update({k: v for k, v in draft.items() if k in SAVED_FIELDS and k not in SERVER_FIELDS})
    if "model" in draft:
        pick(saved, cat, draft["model"])
    doc.replace(saved)
    ctx.bus.publish("changed", "draft", {})                 # other Generate windows take it
    if "model" in draft:
        ctx.emit(models.READY, {})                          # a model picked: the Director's sketches
    return {**saved, **session_part(ctx)}


async def _check_detail(ctx: Ctx, draft: dict, saved: dict) -> None:
    """A card's `detail` the window sends (advancedByModel[model].detail, new or changed) must be one the model
    announces (`models.detail`); a value already saved is left to the job builder, which ignores a stale one."""
    sent, before = draft.get("advancedByModel"), saved.get("advancedByModel")
    before = before if isinstance(before, dict) else {}
    for model_id, adv in (sent.items() if isinstance(sent, dict) else ()):
        old = before.get(model_id) if isinstance(before.get(model_id), dict) else {}
        value = adv.get("detail") if isinstance(adv, dict) else None
        if value is None or value == old.get("detail"):
            continue
        try:
            model = models.find(models.cached() or await models.catalog(ctx), model_id)
        except Exception as exc:
            raise Invalid("engine", models.reason(exc)) from None
        facts = models.detail_facts(model) if model else None
        label = model["name"] if model else str(model_id)
        if facts is None:
            raise Invalid("detail", f"{label} has no detail setting")
        if models.detail(model, value) is None:
            values = [str(c["value"]) for c in facts["choices"]]
            words = " or ".join([", ".join(values[:-1]), values[-1]] if len(values) > 1 else values)
            raise Invalid("detail", f"Detail must be {words} for {label}")


async def random_seed(ctx: Ctx, request: Request) -> dict:
    """Media's reset-seed: the current model's seed goes back to random; open Generate windows reload the draft."""
    doc = ctx.doc(DRAFT, {})
    draft = doc.get()
    adv = draft.get("advancedByModel") if isinstance(draft.get("advancedByModel"), dict) else None
    model = draft.get("model")
    if adv is not None and isinstance(model, str) and isinstance(adv.get(model), dict):
        adv[model] = {**adv[model], "seed": {"mode": "random"}}
        doc.replace(draft)
    ctx.bus.publish("changed", "draft", {})
    return {"ok": True}


def defaults(ctx: Ctx) -> dict:
    """The default model for text to image ("text"), for reference to image ("refs") and for a clip ("video");
    null = not set."""
    return {**NO_DEFAULTS, **ctx.doc(DEFAULTS, NO_DEFAULTS).get()}


def kind(model: dict) -> str:
    return str(model["kind"]) if model.get("kind") in ("video", "speech") else "image"   # a voice is no picture


def pick(saved: dict, cat: dict | None, model_id: Any) -> None:
    """The saved draft takes `model_id`: the model it leaves and the one it takes each become the last-picked of
    their kind (`lastModel`; the other kind's is kept). A model the catalog does not list is not remembered. A
    held `speech` entry is kept (the speech model picked last, read by `tools.speech_pick`), none added before a
    speech pick."""
    held = saved.get("lastModel") if isinstance(saved.get("lastModel"), dict) else {}
    last = {k: v if isinstance(v := held.get(k), str) else "" for k in KINDS}
    last |= {"speech": held["speech"]} if isinstance(held.get("speech"), str) else {}
    for model in (models.find(cat, saved.get("model")), models.find(cat, model_id)):
        if model is not None:
            last[kind(model)] = model["id"]
    saved.update(model=model_id, lastModel=last)


async def get_defaults(ctx: Ctx, request: Request) -> dict:
    return defaults(ctx)


async def put_defaults(ctx: Ctx, request: Request) -> dict:
    body = _body(await request.body(), "defaults")
    if not set(body) <= set(NO_DEFAULTS):
        raise Invalid("defaults", "The defaults are text, refs and video")
    present: dict[str, dict] = {}
    if any(v is not None for v in body.values()):
        try:
            present = {m["id"]: m for m in models.present(await models.catalog(ctx))}
        except Exception as exc:
            raise Invalid("engine", models.reason(exc)) from None
    for key, value in ((k, v) for k, v in body.items() if v is not None):
        if value not in present:
            raise Invalid(key, f'No model "{value}" in the model folders')
        clip, name = present[value].get("kind") == "video", present[value]["name"]
        if clip != (key == "video"):                          # text and refs: picture models; video: a clip model
            raise Invalid(key, f"{name} makes clips, not pictures" if clip else f"{name} makes pictures, not clips")
    ctx.doc(DEFAULTS, NO_DEFAULTS).patch(body)
    return defaults(ctx)


async def get_characters(ctx: Ctx, request: Request) -> dict:
    """The characters by name, for the prompt box's Tab completion: each its picture's id and size (Tab puts the
    picture in a reference box) and its thumbnail (the tiles). Never the notes."""
    def build() -> list[dict]:
        out = []
        for c in ctx.files.characters():
            try:
                with Image.open(ctx.files.existing_image(c["id"])) as im:
                    w, h = im.size
            except (OSError, ValueError, Invalid):
                continue
            out.append({"name": c["name"], "id": c["id"], "w": w, "h": h, "thumb": ctx.files.thumb_url(c["id"])})
        return out
    return {"items": await asyncio.to_thread(build)}
