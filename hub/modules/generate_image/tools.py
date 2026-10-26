"""What the Generate Image screen can do, declared for the tool server: its settings (read and set, `screen.py`),
the image models that can run, the characters, the one render and the one request the Hub plans itself. The core
turns these into the MCP tools `get_generate_image_settings`, `set_generate_image_settings`, `list_image_models`,
`list_characters`, `generate_image`, `direct_clip` (`director.py`), `direct_scene` (
`scene.py`) and `redo_shot` (`redo.py`).

The assistant writes its draft on the page (the `draft` setting); nothing of the draft ever reaches the
prompt box, which no tool writes. generate_image is a press of the Generate button: it renders the draft with the
screen's reference boxes and settings, exactly as the window sends them (`web/src/modules/generate-image/job.ts`
buildJob with the draft as the text), queues the job and answers at once; the picture lands in Media like any
other. When it is called is set in Open WebUI's system prompt. The model and the reference boxes
are the screen's alone: the tools report them and render on them, never change them.
"""
from __future__ import annotations

from hub.core.api import Action, Ctx, Invalid, JobPlan, Listing, Screen

from . import build, cast, models, routes, screen, shotcheck

JOB_KIND = "image"

NO_ARGS: dict = {"type": "object", "properties": {}, "additionalProperties": False}


async def _catalog(ctx: Ctx) -> dict:
    """The engine catalog, or the engine's own one-line reason as the tool's error (as GET /models answers)."""
    try:
        return await models.catalog(ctx)
    except Exception as exc:
        raise Invalid("engine", models.reason(exc)) from None


async def list_image_models(ctx: Ctx, args: dict) -> dict:
    cat = await _catalog(ctx)
    return {"models": [
        {"id": m["id"], "name": m["name"], "size": "x".join(str(v) for v in m.get("size") or (1024, 1024)),
         "steps": m.get("steps"), "loaded": m["id"] == cat.get("resident")}
        for m in models.present(cat)]}


async def read_settings(ctx: Ctx) -> dict:
    """The screen's settings for the model picked on it; refused in one line when that one cannot run. On a video
    model with a draft, `plan`: what the engine would make of it."""
    cat = await _catalog(ctx)
    model = screen.pick_model(cat, screen.read(ctx))
    out = screen.view(ctx, cat, model)
    planned = await plan_of_draft(ctx, cat, model)
    return {**out, "plan": planned} if planned is not None else out


async def write_settings(ctx: Ctx, changes: dict) -> dict:
    """Set some settings on the screen (saved, open windows redraw); the settings after. A shot with cuts is held
    against the engine's plan of the clip it makes: a cut inside a window is refused in one line and the
    shot and its draft are cleared, as a draft set alone would clear them."""
    cat = await _catalog(ctx)
    out = screen.apply(ctx, cat, changes)
    shot = changes.get("shot")
    if isinstance(shot, dict) and shot.get("cuts") and ctx.settings.get("plan_before_render", True):
        model = screen.pick_model(cat, screen.read(ctx))
        planned = await plan_of_draft(ctx, cat, model)
        try:
            shotcheck.cuts_on_plan(shot, planned)
        except Invalid:
            screen.apply(ctx, cat, {"draft": ""})
            raise
        out = {**out, "plan": planned}
    return out


def press_params(ctx: Ctx, cat: dict, text: str) -> dict:
    """The params a press of Generate sends for the draft `text`, as the window builds them (`buildJob`)."""
    saved = screen.read(ctx)
    model = screen.pick_model(cat, saved)
    ui = models.ui_model(model, models.ref_caps(ctx))
    adv = saved["advanced"].get(model["id"]) or {}
    seed = adv.get("seed") if isinstance(adv.get("seed"), dict) else {}
    guidance = adv.get("guidance")
    refs = shotcheck.used(screen.references(ctx))           # a scene's shot: its own boxes
    width, height = screen.canvas(saved["aspect"], saved["size"], refs, model)
    params: dict = {
        "model": model["id"], "mode": "refs" if refs else "new", "prompt": text,
        "loras": screen.stack(saved, model["id"]), "width": width, "height": height, "images": saved["images"],
        "steps": None if ui["lockSteps"] else adv.get("steps"),
        "guidance": guidance if ui["guidanceKey"] and isinstance(guidance, (int, float)) else None,
        "seed": {"mode": "fixed", "value": seed["value"]} if seed.get("mode") == "fixed" and "value" in seed
        else {"mode": "random"}}
    if refs:
        params["references"] = [r["id"] for r in refs]
    if ui["kind"] == "speech":                       # a line: the box and the seed; no size, count or LoRAs
        params = {k: params[k] for k in ("model", "mode", "prompt", "seed")} | {"references": params.get(
            "references", [])}
    elif refs and models.identities(model) and any(r.get("cutout") is True for r in refs):   # as buildJob
        params["cutout"] = [r.get("cutout") is True for r in refs]
    if ui["video"]:                                  # one clip of the card's length
        params.update(images=1, frames=screen.clip_frames(saved, model))
        held = routes.session_part(ctx)
        heard = held.get("sound") if ui["video"].get("soundtrack") else None
        if isinstance(heard, dict) and isinstance(heard.get("id"), str):   # the Sound box, as buildJob
            params["sound"] = heard["id"]
        shown = held.get("video") if ui["video"].get("reference_video") else None
        if isinstance(shown, dict) and isinstance(shown.get("id"), str):   # the Video box
            params["video"] = shown["id"]
    return params


async def generate_image(ctx: Ctx, args: dict) -> dict:
    """A press of Generate: the draft with the screen's references and settings, as the window sends them.
    -> {state} at once; the picture lands in Media."""
    text = screen.draft(ctx)
    if not text.strip():
        raise Invalid("draft", "The draft is empty")
    return {"state": ctx.jobs.submit(JOB_KIND, press_params(ctx, await _catalog(ctx), text)).state}


async def plan_of_draft(ctx: Ctx, cat: dict, model: dict) -> dict | None:
    """The engine's plan of the draft as it stands, on a video model with a draft: the clip the press
    would make, planned by the engine's preflight; None otherwise. A refusal at the build is the plan's one error."""
    text = screen.draft(ctx)
    if not models.video(model) or not text.strip():
        return None
    try:
        job = build.image_job(press_params(ctx, cat, text), ctx)
    except Invalid as err:
        return {"valid": False, "windows": [], "warnings": [], "errors": [err.text], "notes": []}
    try:
        return await ctx.engine.query("plan", request=job.tasks[0])
    except Exception as exc:  # noqa: BLE001  (the engine's one line, never a failed settings read)
        return {"valid": False, "windows": [], "warnings": [], "errors": [models.reason(exc)], "notes": []}


SCREEN = Screen(settings=screen.SETTINGS, read=read_settings, write=write_settings)


async def list_characters(ctx: Ctx, args: dict) -> dict:
    """Each character's name, with its notes and its voice in words when there are any, and whether it has
    a voice sample."""
    return {"characters": cast.listing(ctx)}


LISTINGS = (Listing("image_models", "Models that can run, with default size and steps.", {}, list_image_models),
            Listing("characters", "Characters by name, with the notes on each, the words for its voice and "
                    "whether it has a voice sample, from the Characters folder.",
                    {}, list_characters))
NO_PICTURE_MODEL = "Pick a picture model in Generate"
SKETCH = (576, 320)             # a sketch's canvas, 16:9 in multiples of 16; Generate's menu unchanged
SKETCH_FALLBACK = (848, 480)   # the size if 576x320 does not read on the model; not used here


def sketch_plan(ctx: Ctx, prompt: str) -> JobPlan:
    """The Director's sketch panel: one 16:9 picture at `SKETCH`, mode new, no
    reference and no LoRA, the model's own steps, on the picture model picked here: the pulldown's when it is one,
    else the picture model picked last (`lastModel`). Never a video or speech model. The draft is only read."""
    cat = models.cached()
    if cat is None:
        raise Invalid("model", NO_PICTURE_MODEL)
    saved = ctx.doc(routes.DRAFT, {}).get()
    last = saved.get("lastModel") if isinstance(saved.get("lastModel"), dict) else {}
    present = models.present(cat)
    model = next((m for m in (models.find(cat, saved.get("model")), models.find(cat, last.get("image")))
                  if m is not None and m in present and routes.kind(m) == "image" and not models.video(m)), None)
    if model is None:
        raise Invalid("model", NO_PICTURE_MODEL)
    ui = models.ui_model(model, models.ref_caps(ctx))
    width, height = models.within(model, *SKETCH, 16 / 9)
    return build.picture_job({"mode": "new", "prompt": prompt, "width": width, "height": height, "images": 1,
                              "steps": None, "guidance": None, "seed": {"mode": "none"}, "loras": []},
                             ctx, model, ui)


NO_SPEECH_MODEL = "Pick a speech model in Generate"
NO_SPEECH_THERE = "no speech model in your model folders"


def speech_pick(ctx: Ctx) -> dict:
    """The Director's takes: a present speech model, in this order: the pulldown's; the
    one picked last (`lastModel.speech`); the only one. With its length range and the settings' bars for a line
    (`speech_takes_max`, `speech_words_bar`, `scene_unscripted_seconds`). None present: `Invalid("speech", …)`;
    several and none picked: `Invalid("model", …)`. Only read: the draft and `lastModel` are as they were."""
    cat = models.cached()
    if cat is None:
        raise Invalid("model", NO_SPEECH_MODEL)
    saved = ctx.doc(routes.DRAFT, {}).get()
    last = saved.get("lastModel") if isinstance(saved.get("lastModel"), dict) else {}
    speech = [m for m in models.present(cat) if routes.kind(m) == "speech"]
    model = next((m for m in (models.find(cat, saved.get("model")), models.find(cat, last.get("speech")))
                  if m is not None and m in speech), speech[0] if len(speech) == 1 else None)
    if model is None:
        raise Invalid("speech", NO_SPEECH_THERE) if not speech else Invalid("model", NO_SPEECH_MODEL)
    seconds = (models.speech_model(model).get("speech") or {}).get("seconds") or {}
    s = ctx.settings
    return {"id": model["id"], "label": model["name"],
            "seconds": {"min": int(seconds.get("min") or 1), "max": int(seconds.get("max") or 0)},
            "takes_max": max(1, int(s.get("speech_takes_max") or 1)),
            "words_bar": float(s.get("speech_words_bar") or 0.9),
            "unscripted_s": float(s.get("scene_unscripted_seconds") or 2.5)}


def cue_pick(ctx: Ctx, kind: str) -> dict:
    """The Director's cue and room takes: the sound model for `kind` the catalog marks best whose files
    are there (`models.cue_maker`), with its length range; else one line naming the model it needs. No selection:
    the pulldown is as it was."""
    cat = models.cached()
    lead = "room tone needs" if kind == "room" else f"{kind} cues need"
    model = models.cue_maker(cat, kind)
    if model is not None:
        seconds = (model.get("speech") or {}).get("seconds") or {}
        return {"id": model["id"], "label": model["name"],
                "seconds": {"min": int(seconds.get("min") or 1), "max": int(seconds.get("max") or 1)}}
    known = models.cue_models(cat, kind)
    if not known:
        raise Invalid("model", f"{lead} a sound model; none is in the engine's list")
    absent = [m for m in known if not models.there(m)]
    held = next((m for m in known if models.there(m) and m.get("why_not")), None)
    if not absent:
        raise Invalid("model", f"{lead} {held['name']}, which {held['why_not']}")
    first = absent[0]
    name = first["name"] + (f" ({first['lacks'][0]})" if first.get("lacks") else "")
    line = f"{lead} {name}, not in your model folders"
    raise Invalid("model", line + (f"; {held['name']} is, but {held['why_not']}" if held is not None else ""))


async def direct_clip(ctx: Ctx, args: dict) -> dict:
    """`request` as written, one job the Hub plans and renders: -> {state, job} at once, so Open
    WebUI's turn is over before the Hub asks the same model to plan."""
    await _catalog(ctx)
    job = ctx.jobs.submit(JOB_KIND, {"direct": args["request"]})
    if job.plan.prepare is not None:
        job.plan.prepare.job = job.id                      # type: ignore[attr-defined]  (`director.Planner`)
    return {"state": job.state, "job": job.id}


async def direct_scene(ctx: Ctx, args: dict) -> dict:
    """`request` for a scene as written, one job the Hub plans, renders and cuts: -> {state, job} at
    once, as `direct_clip`."""
    await _catalog(ctx)
    job = ctx.jobs.submit(JOB_KIND, {"scene": args["request"]})
    if job.plan.prepare is not None:
        job.plan.prepare.job = job.id                      # type: ignore[attr-defined]  (`scene.ScenePlanner`)
    return {"state": job.state, "job": job.id}


async def redo_shot(ctx: Ctx, args: dict) -> dict:
    """One shot of a scene made in this run of the Hub rendered again on a new seed, then the cut and the scene's
    sequence rebuilt: -> {state, job} at once, as `direct_scene`."""
    await _catalog(ctx)
    job = ctx.jobs.submit(JOB_KIND, {"redo": {"shot": args["shot"], "scene": args.get("scene")}})
    if job.plan.prepare is not None:
        job.plan.prepare.job = job.id                      # type: ignore[attr-defined]  (`redo.RedoPlanner`)
    return {"state": job.state, "job": job.id}


REDO = {"type": "object", "additionalProperties": False, "required": ["shot"],
        "properties": {"shot": {"type": "integer", "minimum": 1},
                       "scene": {"type": "string", "minLength": 1}}}
REQUEST = {"type": "object", "additionalProperties": False, "required": ["request"],
           "properties": {"request": {"type": "string", "minLength": 1}}}
NOT_SCRIPT = " Not for a chat started with Script:, which the script tools write."
ACTIONS = (Action("generate_image", "Render the draft with the screen's settings, as the Generate button does."
                  + NOT_SCRIPT, NO_ARGS, generate_image),
           Action("direct_clip", "Plan and render one clip from request, its words as written."
                  + NOT_SCRIPT, REQUEST, direct_clip),
           Action("direct_scene", "Plan, render and cut a scene of several shots from request, its "
                  "words as written." + NOT_SCRIPT, REQUEST, direct_scene),
           Action("redo_shot", "Render one shot of a scene again on a new seed and cut the scene again with it.",
                  REDO, redo_shot))
