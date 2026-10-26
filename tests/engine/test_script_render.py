"""The Storyboard's Render and the edits on its timeline (`hub/modules/director/render.py`, `owner.py`,
`generate_image/storyclip.py`). On a version-2 script, locked or not, with no voice sample, no take and no mix: one job
of each shot's clip through the `Clip:` route's compiler then the join; a shot with no line says no one speaks; the
model rule with the pulldown never changed; the cut filed and pointed at; every `/edit` op one write of the tools' own
functions, a refusal one plain line; the chat's word "render"; a length the message does not name dropped. The catalog
is the real worker's answer for upstream's H3 definitions (`test_upstream_rules.cat`). Neutral names only."""
from __future__ import annotations

import copy
import json
import os
import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from PIL import Image

from hub.core import jobgraph
from hub.core.files import Files
from hub.core.store import JsonDoc
from hub.modules.director import drawing, manifest, owner, render, routes, say, saycheck, scripts, teach, tools
from hub.modules.first_cut import pictures
from hub.modules.generate_image import models, storyclip
from hub.modules.generate_image import routes as groutes
from tests.engine import test_upstream_rules as rules
from tests.engine.helpers import FakeCtx, FakeEngine, FakeRequest
from tests.engine.test_upstream_rules import FL2VA, REF2VA

FIRST_REF2VA = "minimax_h3_ref2va"               # the first present model whose pictures are identities

cat = rules.cat                                   # the H3 capture's catalog, shared
NAME = "Script 1"
CONTEXT = {"cast": [{"name": "A", "look": "A tall person", "costume": "A grey coat", "ignore": "The wall", "home": 30},
                  {"name": "B", "look": "A short person", "costume": "A green coat", "ignore": "The chair",
                   "home": 70}],
         "set": {"name": "Room 1", "description": "A plain room", "elements": ["Table"], "props": []},
         "style": "Plain light"}


class Bus:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str, dict]] = []

    def publish(self, lane: str, type: str, data: dict, key: str | None = None) -> None:
        self.sent.append((lane, type, data))


class Jobs:
    def __init__(self, ctx: Any) -> None:
        self.ctx, self.book = ctx, {}

    def submit(self, kind: str, params: dict) -> Any:
        assert kind == render.KIND
        plan = render.job(copy.deepcopy(params), self.ctx)
        job = SimpleNamespace(id=f"j{len(self.book) + 1}", state="queued", plan=plan)
        self.book[job.id] = job
        return job

    def get(self, job_id: str) -> Any:
        return self.book.get(job_id)


class Ctx:
    module_id = "director"

    def __init__(self, tmp: Path, gen: FakeCtx, files: Files) -> None:
        self.data_dir, self.files, self.gen = tmp / "data" / "director", files, gen
        self.bus, self.jobs, self.docs, self.events = Bus(), Jobs(self), {}, []
        self.asked = 0

    def emit(self, event: str, data: dict) -> None:
        self.events.append((event, data))

    def doc(self, name: str, default: dict) -> JsonDoc:
        return self.docs.setdefault(name, JsonDoc(self.data_dir / f"{name}.json", default))

    def service(self, name: str) -> Any:
        if name == "clip_plan":
            return lambda: storyclip.Shots(self.gen)
        if name == "cast_pictures":
            return lambda shot, who, cap, label: pictures.pick(self, shot, who, cap, label)
        if name == "ask":
            self.asked += 1
        raise render.Invalid("assistant", "The assistant is not running")


@pytest.fixture
async def ctx(tmp_path: Path, cat: dict) -> Any:
    await drawing.stop()
    render.running.clear()
    chars = tmp_path / "Characters"
    chars.mkdir()
    for name in ("A", "B"):
        Image.new("RGB", (600, 900), (90, 90, 90)).save(chars / f"{name}.png")
    files = Files(tmp_path / "data", None, chars)
    gen = FakeCtx("generate-image", tmp_path / "data", FakeEngine(copy.deepcopy(cat)))
    gen.files = files
    gen.doc(groutes.DRAFT, {}).replace({"model": REF2VA})
    await models.catalog(gen)
    held = Ctx(tmp_path, gen, files)
    scripts.create(routes.folder(held), NAME, {"version": 2, "context": copy.deepcopy(CONTEXT), "scenes": []},
                   routes.characters(held))
    yield held
    await drawing.stop()


def on_disk(ctx: Ctx) -> dict:
    return json.loads((routes.folder(ctx) / f"{NAME}.json").read_text(encoding="utf-8"))


def event(ctx: Ctx, ident: str) -> dict:
    return next(e for s in on_disk(ctx)["scenes"][0]["shots"] for e in s["events"] if e["id"] == ident)


async def edit(ctx: Ctx, op: str, **args: Any) -> dict:
    return await routes.post_edit(ctx, FakeRequest(body=json.dumps({"name": NAME, "op": op, **args}).encode()))


async def two_shots(ctx: Ctx) -> None:
    """Scene 1 (A, B): s1 a two-shot with A's line and B's line, s2 on B with no line."""
    from hub.modules.director import frame
    await tools._write(ctx, lambda s, c, ch: frame.scene_add(s, {"title": "Scene one", "cast": ["A", "B"]}), None,
                       NAME)
    assert "problem" not in await edit(ctx, "add_shot", scene=1, camera={"framing": "Two-shot", "move": "Slow push"})
    assert "problem" not in await edit(ctx, "add_shot", scene=1, camera={"framing": "Close-up", "on": ["B"]})
    assert "problem" not in await edit(ctx, "add_line", shot="s1", speaker="A", words="Line one is here.")
    assert "problem" not in await edit(ctx, "add_line", shot="s1", speaker="B", words="Line two is here.")


# ---------------------------------------------------------------- the job
async def test_render_is_each_shot_through_the_clip_compiler_then_the_join(ctx: Ctx) -> None:
    await two_shots(ctx)
    got = await routes.post_render(ctx, FakeRequest(body=json.dumps({"name": NAME}).encode()))
    assert got == {"job": "j1", "shots": 2, "skipped": []}
    plan = ctx.jobs.get("j1").plan
    first, second, join = plan.tasks
    assert first["model"] == second["model"] == FIRST_REF2VA, "the catalog's first identity model, not the pulldown's"
    assert "<d>Line one is here.</d>" in first["prompt"] and "Line two is here." in first["prompt"]
    assert "<d>" not in second["prompt"] and "No one speaks" not in second["prompt"], "no line: no <d>, no guard"
    assert "Room 1" in first["prompt"] and "Plain light" in first["prompt"] and "Two-shot" in first["prompt"]
    for task in (first, second):
        assert not task.get("sound") and not task.get("voices"), "no voice sample, no track"
        assert all(r["role"] == "identity" for r in task["references"])
    assert len(first["references"]) > len(second["references"]) >= 1, "the cast in frame: A and B, then B"
    assert [i["path"] for i in join["items"]] == ["", ""]
    assert plan.inputs[-1] == {"items.0.path": (1, "kept"), "items.1.path": (2, "kept")}
    assert jobgraph.between(plan) == set()
    assert plan.summary["step_names"][-1].startswith("Join · ") and plan.summary["shots"] == 2
    assert ctx.gen.doc(groutes.DRAFT, {}).get()["model"] == REF2VA, "the pulldown never changed"


async def test_a_locked_script_renders_and_its_edit_lands(ctx: Ctx) -> None:
    await two_shots(ctx)
    body = on_disk(ctx)
    body["lock"] = {"locked": True, "at": "2026-10-21T00:00:00Z"}
    (routes.folder(ctx) / f"{NAME}.json").write_text(json.dumps(body), encoding="utf-8")
    assert "job" in render.press(ctx, NAME)
    got = await edit(ctx, "change", id="l1", fields={"words": "Line one, changed."})
    assert "problem" not in got and event(ctx, "l1")["words"] == "Line one, changed."


async def test_the_pulldown_and_last_pick_are_never_read_nor_changed(ctx: Ctx) -> None:
    await two_shots(ctx)
    image = next(m["id"] for m in models.present(models.cached()) if groutes.kind(m) == "image")
    draft = {"model": image, "lastModel": {"video": FL2VA}}
    ctx.gen.doc(groutes.DRAFT, {}).replace(copy.deepcopy(draft))
    render.press(ctx, NAME)
    assert {t["model"] for t in ctx.jobs.get("j1").plan.tasks[:2]} == {FIRST_REF2VA}
    assert ctx.gen.doc(groutes.DRAFT, {}).get() == draft


async def test_refusals_are_one_plain_line(ctx: Ctx) -> None:
    assert render.press(ctx, NAME) == {"problem": f"{NAME} has no shot to render"}
    assert render.press(ctx, "Script 2") == {"problem": "There is no script named Script 2"}
    await two_shots(ctx)
    render.press(ctx, NAME)
    assert render.press(ctx, NAME) == {"problem": f"{NAME} is rendering"}


async def test_the_finish_files_the_cut_and_script_points_at_it(ctx: Ctx) -> None:
    await two_shots(ctx)
    render.press(ctx, NAME)
    seen = routes._one(ctx, NAME)
    assert seen["rendering_cut"] == "j1" and seen["cut"] is None and seen["cut_url"] is None
    made = []
    for stem in ("x1", "x2", "x3"):
        path = ctx.files.roots["clips"] / "2026-10-21" / f"{stem}.mp4"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"\x00" * 64)
        made.append(f"clips/2026-10-21/{stem}.mp4")
    job = ctx.jobs.get("j1")
    await job.plan.finish({1: made[0], 2: made[1], 3: made[2]})
    job.state = "done"
    seen = routes._one(ctx, NAME)
    root = ctx.files.roots["clips"]                       # one folder, `<time> - <group> <name>`
    assert seen["rendering_cut"] is None
    assert re.fullmatch(rf"clips/\d{{4}}-\d\d-\d\d \d{{6}} - Storyboard {NAME}\.mp4", seen["cut"])
    assert (root / seen["cut"].split("/", 1)[1]).is_file()
    assert [f for f in os.listdir(root) if f.endswith(f" - Storyboard {NAME} s1.mp4")]
    assert ctx.bus.sent[-1][2]["name"] == NAME


# ---------------------------------------------------------------- the timeline edits
async def test_each_edit_op_is_the_tools_own_write(ctx: Ctx) -> None:
    await two_shots(ctx)
    got = await edit(ctx, "change", id="l2", fields={"speaker": "A", "words": "Line two, now A's."})
    assert got["script"] == NAME and isinstance(got["state"], list)
    ev = event(ctx, "l2")
    assert (ev["speaker"], ev["words"]) == ("A", "Line two, now A's.")
    assert "problem" not in await edit(ctx, "move", id="l2", start_ms=0, shot="s2")
    shots = on_disk(ctx)["scenes"][0]["shots"]
    assert [e["id"] for e in shots[1]["events"] if e["kind"] == "line"] == ["l2"]
    assert "problem" not in await edit(ctx, "add_cue", shot="s2", cue="effect", words="A door closes")
    cue = next(e["id"] for e in on_disk(ctx)["scenes"][0]["shots"][1]["events"] if e["kind"] == "cue")
    assert "problem" not in await edit(ctx, "remove", id=cue)
    assert all(e["kind"] != "cue" for s in on_disk(ctx)["scenes"][0]["shots"] for e in s["events"])
    at = event(ctx, "l2")["end_ms"] - on_disk(ctx)["scenes"][0]["shots"][1]["start_ms"]
    assert "problem" not in await edit(ctx, "add_line", shot="s2", speaker="B", words="Line three.", start_ms=at)
    line = next(e for e in on_disk(ctx)["scenes"][0]["shots"][1]["events"] if e.get("words") == "Line three.")
    assert line["start_ms"] - on_disk(ctx)["scenes"][0]["shots"][1]["start_ms"] == at
    assert "problem" not in await edit(ctx, "move", id="s2", start_ms=0)
    assert [s["id"] for s in on_disk(ctx)["scenes"][0]["shots"]] == ["s2", "s1"], "a shot moves within its scene"
    assert "problem" not in await edit(ctx, "move", id="s2", shot="s1", start_ms=0)
    assert [s["id"] for s in on_disk(ctx)["scenes"][0]["shots"]] == ["s1", "s2"]


async def test_an_edit_refusal_is_one_plain_line(ctx: Ctx) -> None:
    await two_shots(ctx)
    before = on_disk(ctx)
    assert (await edit(ctx, "jump", id="s1")) == {"problem": "op is one of " + ", ".join(owner.OPS)}
    assert (await edit(ctx, "change", id="l1", fields={"speaker": "C"}))["problem"] == "C is not in scene 1's cast"
    assert "\n" not in (await edit(ctx, "move", id="l9", start_ms=0))["problem"]
    assert on_disk(ctx) == before
    got = await edit(ctx, "remove", id="s1")              # a deleted shot goes with what is in it
    assert "problem" not in got
    shots = on_disk(ctx)["scenes"][0]["shots"]
    assert "s1" not in [sh["id"] for sh in shots] and not {"l1", "l2"} & {e["id"] for sh in shots for e in sh["events"]}


# ---------------------------------------------------------------- the chat, the teach line, the length
async def test_the_chat_word_render_presses_render_and_asks_no_model(ctx: Ctx) -> None:
    await two_shots(ctx)
    tools._pointer(ctx).patch({"name": NAME})
    name, line = await say._work(ctx, "Render it.", False, False)
    assert (name, line) == (NAME, "rendering 2 shots into one video (job j1)") and ctx.asked == 0
    got = await next(a.fn for a in manifest.MODULE.actions if a.name == "script_render")(ctx, {})
    assert got == {"script": NAME, "state": [f"not rendered: {NAME} is rendering"]}
    assert manifest.MODULE.actions[-1].name == "script_render" == list(teach.SAY)[-1]


def test_a_length_the_user_did_not_name_is_dropped() -> None:
    op = {"op": "set_length", "scene": 1, "seconds": 20}
    ops, said, bad = saycheck.check({"operations": [op]}, "Make it longer.", {"scenes": []}, False)
    assert said == [] and bad == {1} and "seconds" not in ops[0]
