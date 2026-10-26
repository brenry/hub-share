"""The Casting module. Its manifest; the routes as the tab uses them (list, draft, cast, again,
approve, the approved orbit) over a stand-in orbit service and, once, Generate's real one on the upstream catalog;
the job's end setting the draft; every refusal one line as `{problem}`; `casting.changed` told at each change."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image

from hub.core.api import Invalid, JobPlan, SocketGroup, Tab
from hub.core.files import Files
from hub.modules.casting import manifest, prompt, record, routes, state
from hub.modules.generate_image import orbit
from hub.modules.generate_image import routes as groutes
from tests.engine import test_upstream_rules as rules
from tests.engine.helpers import FakeCtx, FakeEngine, FakeRequest
from tools import release

cat, accepted, ref_ctx = rules.cat, rules.accepted, rules.ref_ctx
DAY = "2026-10-20"
CHANGED = ("changed", "changed", {"name": "Character 11"})


@pytest.fixture(autouse=True)
def no_drafts():
    state.clear()
    yield
    state.clear()


class Orbit:
    """Generate's service, stood in: it records each call; `refuse` is raised instead when set."""

    def __init__(self) -> None:
        self.calls: list[tuple[list[str], str, int]] = []
        self.refuse: Invalid | None = None

    def __call__(self, pictures: list[str], text: str, seed: int | None) -> JobPlan:
        if self.refuse is not None:
            raise self.refuse
        self.calls.append((pictures, text, seed))
        return JobPlan("image", "m", ({"kind": "video"}, {"kind": "frames"}), {"model": "H3 Ref2VA", "kind": "clip"})


@pytest.fixture
def ctx(tmp_path: Path) -> FakeCtx:
    held = FakeCtx("casting", tmp_path / "data", FakeEngine(None), {routes.KIND: routes.job})
    chars = tmp_path / "Characters"
    chars.mkdir()
    for name in ("Character 11", "Character 4"):
        Image.new("RGB", (64, 64)).save(chars / f"{name}.png")
    held.files = Files(tmp_path / "data", None, chars)
    held.offer("orbit", Orbit())
    return held


async def call(fn, ctx, query: dict | None = None, body: dict | None = None):
    return await fn(ctx, FakeRequest(query, json.dumps(body).encode() if body is not None else b""))


def cast_body(**extra) -> dict:
    return {"name": "character 11", "headshot": {"keep": "the face", "ignore": "the hat"},
            "bits": [{"id": "chars/Character 4.png", "keep": "the  coat", "ignore": ""}],
            "facts": {"age": "50", "build": "heavy"}, **extra}


def land(ctx) -> list[str]:
    """What a finished orbit job lands: one clip, then six pictures."""
    out, clips = Path(ctx.files.roots["out"]) / DAY, Path(ctx.files.roots["clips"]) / DAY
    out.mkdir(parents=True, exist_ok=True)
    clips.mkdir(parents=True, exist_ok=True)
    (clips / "o.mp4").write_bytes(b"\0" * 32)
    for i in range(6):
        Image.new("RGB", (70, 124)).save(out / f"v{i}.png")
    return [f"clips/{DAY}/o.mp4", *(f"out/{DAY}/v{i}.png" for i in range(6))]


async def finish(ctx, job_id: str, outputs: list[str], end: str = "done", error: str | None = None) -> None:
    job = ctx.jobs.get(job_id)
    job.state, job.error = end, error
    await state.finished(ctx, {"job": job_id, "tool": "casting", "state": end, "outputs": outputs, "notes": {}})


def test_the_manifest():
    mod = manifest.MODULE
    assert (mod.id, mod.title, mod.tab, mod.lanes) == ("casting", "Casting", Tab("Casting", 40), ("changed",))
    assert mod.sockets == (SocketGroup("pictures", "Pictures", ("image",), 9),)
    assert set(mod.jobs) == {"orbit"} and set(mod.listens) == {"job.finished"}
    assert {(r.method, r.path) for r in mod.routes} == {("GET", "/list"), ("GET", "/draft"), ("POST", "/cast"),
                                                        ("POST", "/again"), ("POST", "/approve"), ("GET", "/orbit"),
                                                        ("POST", "/seat"), ("GET", "/costume"),
                                                        *(("POST", f"/costume/{p}") for p in
                                                          ("cast", "again", "approve", "remove"))}
    text = Path(manifest.__file__).read_text(encoding="utf-8")
    assert release.MODULE_ID.search(text).group(2) == "casting", "the first id= in the manifest (tools/release.py)"


async def test_list_open_cast_land_approve(ctx):
    more = {"role": None, "costumes": 0}                                          # the extra and costume fields
    assert await call(routes.get_list, ctx) == [{"name": "Character 11", "picture": "chars/Character 11.png",
                                                 "cast": False, **more},
                                                {"name": "Character 4", "picture": "chars/Character 4.png",
                                                 "cast": False, **more}]
    opened = await call(routes.get_draft, ctx, {"name": "character 11"})
    assert (opened["name"], opened["picture"], opened["state"], opened["job"], opened["record"]) == (
        "Character 11", "chars/Character 11.png", "none", None, None)
    assert opened["headshot"] == {"id": "chars/Character 11.png", "keep": "", "ignore": ""}
    answer = await call(routes.post_cast, ctx, body=cast_body())
    job = ctx.jobs.get(answer["job"])
    assert job.plan.summary["title"] == "Cast · Character 11 · 2 pictures" and ctx.bus.sent[-1] == CHANGED
    pictures, text, seed = ctx.service("orbit").calls[-1]
    assert pictures == ["chars/Character 11.png",
                        "chars/Character 4.png"] and seed is None, "no seed of the Hub's"
    assert text == prompt.prompt([{"keep": "the face", "ignore": "the hat"}, {"keep": "the coat", "ignore": ""}],
                                 {"age": "50", "build": "heavy"})
    assert (await call(routes.post_cast, ctx, body=cast_body()))["problem"] == "Character 11 is being cast now"
    rendering = await call(routes.get_draft, ctx, {"name": "Character 11"})
    assert (rendering["state"], rendering["job"], rendering["model"]) == ("rendering", answer["job"], "H3 Ref2VA")
    assert rendering["bits"] == [{"id": "chars/Character 4.png", "keep": "the coat", "ignore": ""}]
    outputs = land(ctx)
    await finish(ctx, answer["job"], outputs)
    ready = await call(routes.get_draft, ctx, {"name": "Character 11"})
    assert (ready["state"], ready["orbit"], ready["problem"]) == ("ready", outputs[0], None)
    assert ready["views"] == dict(zip(record.SHEET, outputs[1:], strict=True)) and ctx.bus.sent[-1] == CHANGED
    written = await call(routes.post_approve, ctx, body={"name": "Character 11"})
    assert written["name"] == "Character 11" and written["bits"][0]["file"] == "bits/2.png" \
        and ctx.bus.sent[-1] == CHANGED
    assert (await call(routes.get_list, ctx))[0]["cast"] is True
    done = await call(routes.get_draft, ctx, {"name": "Character 11"})
    assert done["state"] == "approved" and done["record"] == written
    assert done["files"]["views"]["front"] == "chars/Character 11/sheet/front.png"
    served = await call(routes.get_orbit, ctx, {"name": "Character 11"})
    assert Path(served.path) == Path(ctx.files.roots["chars"]) / "Character 11" / "orbit.mp4"


async def test_again_is_the_same_pictures_and_lines_with_no_seed(ctx):
    assert (await call(routes.post_again, ctx, body={"name": "Character 11"}))["problem"] == "Cast Character 11 first"
    first = await call(routes.post_cast, ctx, body=cast_body())
    await finish(ctx, first["job"], land(ctx))
    again = await call(routes.post_again, ctx, body={"name": "Character 11"})
    calls = ctx.service("orbit").calls
    assert again["job"] != first["job"] and calls[0][:2] == calls[1][:2] and calls[0][2] is calls[1][2] is None


async def test_after_a_restart_the_approved_record_is_the_draft(ctx):
    first = await call(routes.post_cast, ctx, body=cast_body())
    await finish(ctx, first["job"], land(ctx))
    await call(routes.post_approve, ctx, body={"name": "Character 11"})
    state.clear()                                                  # a restart: the draft in memory is gone
    opened = await call(routes.get_draft, ctx, {"name": "Character 11"})
    assert (opened["state"], opened["headshot"]["keep"], opened["facts"]) == (
        "approved", "the face", {"age": "50", "build": "heavy"})
    assert opened["bits"] == [{"id": "chars/Character 11/bits/2.png", "keep": "the coat", "ignore": ""}]
    again = await call(routes.post_again, ctx, body={"name": "Character 11"})
    assert "job" in again and ctx.service("orbit").calls[-1][0] == ["chars/Character 11.png",
                                                                    "chars/Character 11/bits/2.png"]


async def test_a_cast_prompt_over_4000_is_sent_whole(ctx):
    long = cast_body(headshot={"keep": "x" * 4000, "ignore": ""}, prompt="y" * 5000)   # no cap of the Hub's
    assert "job" in await call(routes.post_cast, ctx, body=long)
    assert "<Picture 1>: " + "x" * 4000 in ctx.service("orbit").calls[-1][1]
    assert ctx.service("orbit").calls[-1][1].endswith("\n\n" + "y" * 5000)


async def test_the_refusals_are_one_line(ctx):
    nine = [{"id": "chars/Character 4.png", "keep": "", "ignore": ""}] * 9
    assert (await call(routes.post_cast, ctx, body=cast_body(bits=nine)))["problem"] == (
        "Casting takes at most 9 pictures; this has 10")
    (Path(ctx.files.roots["clips"]) / "c.mp4").write_bytes(b"\0")
    clip = [{"id": "clips/c.mp4", "keep": "", "ignore": ""}]
    assert (await call(routes.post_cast, ctx, body=cast_body(bits=clip)))["problem"] == "Box 2 holds no picture"
    ctx.service("orbit").refuse = Invalid("model", orbit.NO_REF2VA)
    assert (await call(routes.post_cast, ctx, body=cast_body()))["problem"] == orbit.NO_REF2VA
    assert (await call(routes.get_draft, ctx, {"name": "Character 11"}))["problem"] == orbit.NO_REF2VA
    ctx.services.clear()
    assert (await call(routes.post_cast, ctx, body=cast_body()))["problem"] == "Generate Image is not running"
    assert (await call(routes.post_approve, ctx, body={"name": "Character 11"}))["problem"] == record.NOT_READY
    with pytest.raises(Invalid) as err:
        await call(routes.get_draft, ctx, {"name": "Nobody"})
    assert err.value.text == "No character is called Nobody"


async def test_a_failed_and_a_cancelled_cast(ctx):
    first = await call(routes.post_cast, ctx, body=cast_body())
    line = "The orbit has 113 frames; the views need 114"
    await finish(ctx, first["job"], land(ctx)[:1], "failed", line)
    failed = await call(routes.get_draft, ctx, {"name": "Character 11"})
    assert (failed["state"], failed["problem"], failed["views"]) == ("failed", line, None)
    second = await call(routes.post_again, ctx, body={"name": "Character 11"})
    del ctx.jobs.jobs[second["job"]]                     # cancelled while queued: the core sends no job.finished
    assert (await call(routes.get_draft, ctx, {"name": "Character 11"}))["problem"] == state.CANCELLED


async def test_with_generates_real_orbit(ref_ctx):
    ctx = FakeCtx("casting", Path(ref_ctx.files.data_dir), FakeEngine(None), {routes.KIND: routes.job})
    ctx.files = ref_ctx.files
    ctx.offer("orbit", lambda pictures, text, seed: orbit.orbit_plan(ref_ctx, pictures, text, seed))
    ref_ctx.doc(groutes.DRAFT, {}).replace({"model": rules.REF2VA})
    answer = await call(routes.post_cast, ctx, body={"name": "Character 12", "headshot": {"keep": "", "ignore": ""},
                                                     "bits": [{"id": "chars/Character 11.png", "keep": "the coat"}],
                                                     "prompt": "Prompt 1"})
    plan = ctx.jobs.get(answer["job"]).plan
    assert plan.summary["title"] == "Cast · Character 12 · 2 pictures" and plan.tasks[1]["frames"] == list(orbit.VIEWS)
    assert [Path(r["path"]).name for r in plan.tasks[0]["references"]] == ["Character 12.png", "Character 11.png"]
    assert plan.tasks[0]["prompt"].endswith("\n\nPrompt 1") and "<Picture 2>: the coat" in plan.tasks[0]["prompt"]
    assert list(record.SHEET.values()) == list(orbit.VIEWS), "the record's frames are the ones taken"


async def test_a_sheet_that_cannot_be_written_is_one_line(ctx, monkeypatch):
    first = await call(routes.post_cast, ctx, body=cast_body())
    await finish(ctx, first["job"], land(ctx))

    def full(*args, **kwargs):
        raise OSError(28, "No space left on device")
    monkeypatch.setattr(record.shutil, "copyfile", full)
    answer = await call(routes.post_approve, ctx, body={"name": "Character 11"})
    assert answer == {"problem": "Could not write Character 11's sheet: No space left on device"}
    assert (await call(routes.get_draft, ctx, {"name": "Character 11"}))["state"] == "ready"
    assert not (Path(ctx.files.roots["chars"]) / "Character 11").exists()


async def test_the_approved_files_carry_versioned_urls(ctx):
    first = await call(routes.post_cast, ctx, body=cast_body())
    await finish(ctx, first["job"], land(ctx))
    await call(routes.post_approve, ctx, body={"name": "Character 11"})
    files = (await call(routes.get_draft, ctx, {"name": "Character 11"}))["files"]
    assert set(files) == {"views", "bits", "view_urls", "view_thumbs", "bit_urls", "orbit_url"}
    assert files["bits"] == ["chars/Character 11/bits/2.png"] and "?v=" in files["bit_urls"][0]
    assert all("?v=" in u for u in [*files["view_urls"].values(), *files["view_thumbs"].values()])
