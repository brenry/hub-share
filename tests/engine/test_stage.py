"""The Stage module. The sets root; the prompts (the fields as typed, then the pan's box); a change by asking (`parse`,
`apply`); Generate's pan on the upstream catalog (`pan_plan`); the job's titles and end; Approve of a build, a change
and a house (files, `set.json`, revision, the bus, a failed copy); the routes; and a real 175-frame pan through the
worker's frames task."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from PIL import Image

from hub.core import jobgraph
from hub.core.api import Invalid, JobPlan, SocketGroup, Tab
from hub.core.files import Files
from hub.modules.generate_image import cast, models, orbit, pan
from hub.modules.generate_image import routes as groutes
from hub.modules.stage import change, drafts, manifest, prompt, record, routes
from hub.worker import enginewire, frames
from tests.engine import test_upstream_rules as rules
from tests.engine.helpers import FakeCtx, FakeEngine, FakeRequest
from tools import release

cat, accepted, ref_ctx = rules.cat, rules.accepted, rules.ref_ctx
DAY = "2026-10-20"
R51 = Path(__file__).resolve().parents[2] / "docs/video-plan/research/R51-character-sheet-and-stage-pan.md"
STAGE_PLATES = ["wide", "left", "centre", "right", "audience"]
HOUSE_PLATES = ["wide", "left", "right", "row"]


@pytest.fixture(autouse=True)
def no_drafts():
    drafts.clear()
    yield
    drafts.clear()


class Pan:
    """Generate's service, stood in: it records each call; `refuse` is raised instead when set."""

    def __init__(self) -> None:
        self.calls: list[tuple] = []
        self.refuse: Invalid | None = None

    def __call__(self, pictures, text, seed, length, grabs) -> JobPlan:
        if self.refuse is not None:
            raise self.refuse
        self.calls.append((pictures, text, seed, length, grabs))
        return JobPlan("image", "m", ({"kind": "video"}, {"kind": "frames"}),
                       {"model": "H3 Ref2VA", "kind": "clip", "frames": 175, "fps": 24})


@pytest.fixture
def ctx(tmp_path: Path) -> FakeCtx:
    held = FakeCtx("stage", tmp_path / "data", FakeEngine(None), {routes.KIND: routes.job})
    held.files = Files(tmp_path / "data")
    out = Path(held.files.roots["out"]) / DAY
    out.mkdir(parents=True)
    for n in range(1, 4):
        Image.new("RGB", (1200, 700), (n, n, n)).save(out / f"set{n}.png")
    held.offer("pan", Pan())
    return held


async def call(fn, ctx, query: dict | None = None, body: dict | None = None):
    return await fn(ctx, FakeRequest(query, json.dumps(body).encode() if body is not None else b""))


def build_body(**extra) -> dict:
    return {"name": "Set 1", "pictures": [{"id": f"out/{DAY}/set1.png", "keep": ""},
                                           {"id": f"out/{DAY}/set2.png", "keep": "the  table"}],
            "description": "a scripted scene", "pieces": ["long table", "two stools", " "],
            "audience": "seen", **extra}


def land(ctx, n: int, tone: int = 10) -> list[str]:
    """What a finished pan lands: one clip, then `n` plates of 864×480 (tones tone, tone+1, …)."""
    out, clips = Path(ctx.files.roots["out"]) / DAY, Path(ctx.files.roots["clips"]) / DAY
    clips.mkdir(parents=True, exist_ok=True)
    (clips / f"p{tone}.mp4").write_bytes(bytes([tone]) * 32)
    for i in range(n):
        Image.new("RGB", (864, 480), (tone + i, 0, 0)).save(out / f"plate{tone}-{i}.png")
    return [f"clips/{DAY}/p{tone}.mp4", *(f"out/{DAY}/plate{tone}-{i}.png" for i in range(n))]


async def finish(ctx, job_id: str, outputs: list[str], end: str = "done", error: str | None = None) -> None:
    job = ctx.jobs.get(job_id)
    job.state, job.error = end, error
    await drafts.finished(ctx, {"job": job_id, "tool": "stage", "state": end, "outputs": outputs, "notes": {}})


async def approved_set(ctx, tone: int = 10) -> dict:
    answer = await call(routes.post_build, ctx, body=build_body())
    await finish(ctx, answer["job"], land(ctx, 5, tone))
    return (await call(routes.post_approve, ctx, body={"name": "Set 1"}))["record"]


def folder(ctx) -> Path:
    return Path(ctx.files.roots["sets"]) / "Set 1"


def red(path: Path) -> int:
    with Image.open(path) as im:
        return im.convert("RGB").getpixel((0, 0))[0]


def test_the_manifest():
    mod = manifest.MODULE
    assert (mod.id, mod.title, mod.tab, mod.lanes) == ("stage", "Stage", Tab("Stage", 45), ("changed",))
    assert mod.sockets == (SocketGroup("pictures", "Pictures", ("image",), 9),)
    assert set(mod.jobs) == {"pan"} and set(mod.listens) == {"job.finished"}
    assert {(r.method, r.path) for r in mod.routes} == {
        ("GET", "/sets"), ("GET", "/set"), ("GET", "/pan"),
        *(("POST", f"/{p}") for p in ("build", "again", "change", "house", "house-change", "approve", "discard",
                                      "audience", "delete"))}
    assert {r.path: r.body_limit for r in mod.routes if r.method == "POST"}["/build"] == 65_536
    text = Path(manifest.__file__).read_text(encoding="utf-8")
    assert release.MODULE_ID.search(text).group(2) == "stage", "the first id= in the manifest (tools/release.py)"


def test_sets_is_a_hub_root(tmp_path):
    files = Files(tmp_path / "data")
    assert files.roots["sets"] == tmp_path / "data" / "sets" and files.roots["sets"].is_dir()
    plates = files.roots["sets"] / "Set 1" / "plates"
    plates.mkdir(parents=True)
    Image.new("RGB", (8, 8)).save(plates / "wide.png")
    (plates.parent / "pan.mp4").write_bytes(b"\0" * 8)
    assert files.kind("sets/Set 1/plates/wide.png") == "image"
    assert files.url("sets/Set 1/plates/wide.png").startswith("/files/sets/Set%201/plates/wide.png?v=")
    assert files.existing_image("sets/Set 1/plates/wide.png") == plates / "wide.png"
    assert files.kind("sets/Set 1/pan.mp4") is None, "the pan is no media kind"
    (plates / ".wide.png.hub-new").write_bytes(b"x")
    Files(tmp_path / "data")
    assert not (plates / ".wide.png.hub-new").exists(), "a half-written approve is erased at start"


def test_the_build_prompt():
    text = prompt.build([{"keep": ""}, {"keep": "Keep 2"}, {"keep": "the <Picture 9>  table\n"}], "Description 1.",
                        ["Piece 1", " Piece  2 "])
    assert text == "<Picture 2> - Keep 2\n<Picture 3> - the Picture 9 table\nDescription 1.\nPiece 1\nPiece 2"
    assert prompt.build([{"keep": "x"}], "", []) == "<Picture 1> - x"
    assert prompt.build([{"keep": "x"}], "", [], "Prompt 1\n\n[a]  b ") == "<Picture 1> - x\n\nPrompt 1\n\n[a]  b "
    assert prompt.build([{"keep": "x"}], "", [], " \n ") == "<Picture 1> - x", "a box of spaces sends nothing"
    long = prompt.build([{"keep": "x" * 3000}], "", [], "y" * 1000)      # sent whole, any length
    assert long == "<Picture 1> - " + "x" * 3000 + "\n\n" + "y" * 1000


def test_the_change_prompt():
    held = {"description": "Description 1", "elements": ["Element 1"], "props": []}
    words = "add a <bench> stage left."
    op = change.parse(words, held)
    text = prompt.change(words, op, change.apply(held, op), "Prompt 1")
    assert text == "add a bench stage left.\nDescription 1\nElement 1\nbench stage left\n\nPrompt 1"
    plain = prompt.change("make the walls blue", change.parse("make the walls blue", held), held)
    assert plain == "make the walls blue\nDescription 1\nElement 1"


def test_the_house_prompts():
    with pytest.raises(Invalid) as err:
        prompt.house({"era": " ", "dress": "Dress 1"})
    assert err.value.text == "Say the audience's era"
    full = prompt.house({"era": "Era 1", "dress": "Dress 1", "hair": "Hair 1", "size": "Size 1"}, "Prompt 1")
    assert full == "Era 1\nSize 1\nDress 1\nHair 1\n\nPrompt 1"
    assert prompt.house({"era": "Era 1", "hair": "Hair 1"}) == "Era 1\nHair 1"
    assert prompt.house_change("Change 1", {"era": "Era 1"}, "Prompt 1") == "Change 1\nEra 1\n\nPrompt 1"
    assert prompt.house_change("Change 1", {"era": "Era 1"}) == "Change 1\nEra 1"


def test_each_pan_is_its_fields_and_its_box():
    """Each pan's prompt less the fields' text, the `<Picture N> - ` labels and the box holds only
    newlines."""
    held = {"description": "Description 1", "elements": ["Element 1"], "props": [{"name": "Prop 1", "place": {
        "words": "Place 1", "side": None, "depth": None}}]}
    box = "Prompt 1\n[Line 1]"
    house = {"era": "Era 1", "dress": "Dress 1", "hair": "Hair 1", "size": "Size 1"}
    made = [
        (prompt.build([{"keep": "Keep 1"}, {"keep": "Keep 2"}], "Description 1", ["Piece 1"], box),
         ["<Picture 1> - ", "Keep 1", "<Picture 2> - ", "Keep 2", "Description 1", "Piece 1"]),
        (prompt.change("Change 1", {"op": "remove"}, held, box),
         ["Change 1", "Description 1", "Element 1", "Prop 1 Place 1"]),
        (prompt.house(house, box), list(house.values())),
        (prompt.house_change("Change 1", house, box), ["Change 1", *house.values()]),
    ]
    for text, fields in made:
        assert text.endswith("\n\n" + box)
        rest = text.removesuffix(box)
        for field in fields:
            assert field in rest
            rest = rest.replace(field, "", 1)
        assert set(rest) == {"\n"}, (text, rest)


def test_an_empty_keep_sends_no_line():
    assert prompt.build([{"keep": ""}, {"keep": "  "}, {}], "", []) == ""
    assert prompt.build([{"keep": ""}, {"keep": "Keep 2"}], "", []) == "<Picture 2> - Keep 2"
    assert drafts.empty_inputs()["pictures"] == [{"id": "", "keep": ""}]


async def test_the_boxes_are_held_in_memory_and_go_with_their_pans(ctx):
    assert (await call(routes.get_sets, ctx))["prompts"] == {"stage": "", "house": ""}
    await call(routes.post_build, ctx, body={**build_body(), "prompt": "Prompt 1\n\nLine 2 "})
    assert ctx.service("pan").calls[-1][1].endswith("\n\nPrompt 1\n\nLine 2 ")
    assert (await call(routes.get_set, ctx, {"name": "Set 1"}))["prompts"] == {"stage": "Prompt 1\n\nLine 2 ",
                                                                               "house": ""}
    await call(routes.post_change, ctx, body={"name": "Other", "words": "x", "prompt": "y" * 4001})
    assert drafts.box("stage") == "y" * 4001, "a box of any length is set whole"
    assert not [p for p in Path(ctx.data_dir).parent.rglob("*") if p.is_file() and b"Prompt 1" in p.read_bytes()]
    drafts.clear()
    assert drafts.boxes() == {"stage": "", "house": ""}


def test_parse():
    held = {"elements": ["long table"], "props": [{"name": "Bench", "place": {"words": "", "side": None,
                                                                            "depth": None}}]}

    def p(words):
        found = change.parse(words, held)
        place = found["place"] or {}
        return found["op"], found["thing"], place.get("side"), place.get("depth"), place.get("words")
    assert p("add a bench stage left") == ("add", "bench", "stage_left", None, "stage left"), "add stays add"
    assert p("add a lamp stage left") == ("add", "lamp", "stage_left", None, "stage left")
    assert p("Bring some plants at the back") == ("add", "plants", None, "upstage", "at the back")
    assert p("put the bench stage right") == ("move", "bench", "stage_right", None, "stage right")
    assert p("place a vase centre stage") == ("add", "vase", "centre", None, "centre stage")
    assert p("set the bench in the middle")[:3] == ("move", "bench", "centre")
    assert p("move the long table to the left") == ("move", "long table", "stage_right", None, "the left")
    assert p("shift the table camera right") == ("move", "table", "stage_left", None, "camera right")
    assert p("slide the table screen left downstage")[2:4] == ("stage_right", "downstage")
    assert p("move the table upstage")[2:4] == (None, "upstage")
    assert p("move the table at the front")[2:4] == (None, "downstage")
    assert p("put a plant on the table") == ("add", "plant", None, None, "on the table")
    for verb in ("remove", "delete", "take away", "take out", "get rid of"):
        assert p(f"{verb} the bench") == ("remove", "bench", None, None, None)
    found = change.parse("make the walls blue", held)
    assert found == {"op": "other", "thing": None, "place": None, "words": "make the walls blue"}
    assert change.parse("add  a bench   stage left", held)["words"] == "add a bench stage left"


def test_apply():
    held = {"elements": ["long table", "stools"], "props": [], "changes": [], "floor_plan": {"x": 1}}

    def run(record, words):
        return change.apply(record, change.parse(words, record))
    one = run(held, "add a bench stage left")
    assert held["props"] == [] and one["floor_plan"] == {"x": 1}
    assert one["props"] == [{"name": "bench", "place": {"words": "stage left", "side": "stage_left", "depth": None}}]
    again = run(one, "add the bench stage right")
    assert [p["place"]["side"] for p in again["props"]] == ["stage_right"], "added again: its place replaced"
    moved = run(again, "move the bench upstage")
    assert moved["props"][0]["place"] == {"words": "upstage", "side": None, "depth": "upstage"}
    table = run(moved, "move the long table centre stage")
    assert table["elements"] == ["stools"] and table["props"][-1]["name"] == "long table"
    lamp = run(table, "move a lamp stage left")
    assert lamp["props"][-1] == {"name": "lamp", "place": {"words": "stage left", "side": "stage_left",
                                                           "depth": None}}
    gone = run(run(lamp, "remove the lamps"), "take away the stool")
    assert [p["name"] for p in gone["props"]] == ["bench", "long table"] and gone["elements"] == []
    same = run(gone, "remove the piano")
    assert (same["props"], same["elements"]) == (gone["props"], gone["elements"])
    other = run(same, "make the walls blue")
    assert other["changes"] == ["add a bench stage left", "add the bench stage right", "move the bench upstage",
                                "move the long table centre stage", "move a lamp stage left", "remove the lamps",
                                "take away the stool", "remove the piano", "make the walls blue"]


def test_pan_plan(ref_ctx):
    draft = {"model": rules.FL2VA, "lastModel": {"video": rules.REF2VA}}
    ref_ctx.doc(groutes.DRAFT, {}).replace(draft)
    folder = Path(ref_ctx.files._real["chars"])
    for i in range(8):
        Image.new("RGB", (1200, 700)).save(folder / f"S{i}.png")
    boxes = ["chars/Character 11.png", *(f"chars/S{i}.png" for i in range(8))]
    grabs = list(record.STAGE.values())
    plan = pan.pan_plan(ref_ctx, boxes, "<Picture 1> - the stage.", 7, 175, grabs)
    assert ref_ctx.doc(groutes.DRAFT, {}).get() == draft, "the pulldown and lastModel are only read"
    clip, plates = plan.tasks
    assert (plan.lane_kind, plan.model, plan.inputs) == ("image", rules.REF2VA, ({}, {"clip": (1, "kept")}))
    assert len(boxes) == 9 > cast.BOXES
    assert [(Path(r["path"]).name, r["role"], r["name"]) for r in clip["references"]] == [
        (Path(b).name, "identity", None) for b in boxes]
    assert (clip["frames"], clip["size"], clip["seed"]) == (175, [864, 480], 7)
    assert (clip["detail"], clip["judge"], clip["sound"], clip["video"], clip["voices"]) == (None, None, None, None,
                                                                                             [])
    assert plates == {"kind": "frames", "clip": "", "frames": [20, 44, 68, 92, 166]}
    assert plan.summary["step_names"] == ["Pan", "Plates"] and (plan.summary["frames"], plan.summary["fps"]) == (
        175, 24)
    jobgraph.check(plan)
    assert enginewire.request_parse(plates).frames == tuple(grabs)
    label = rules.entry(models.cached(), rules.REF2VA)["name"]
    with pytest.raises(Invalid) as err:
        pan.pan_plan(ref_ctx, [*boxes, "chars/Character 12.png"], "x", 1, 175, grabs)
    assert err.value.text == f"{label} takes 9 pictures; this set has 10"
    facts = {"tiers": [{"name": "480p", "sizes": {"16:9": [864, 480]}}, {"name": "720p", "sizes": {"16:9": [1280,
                                                                                                          704]}}]}
    assert pan.wide({"name": "M"}, facts) == (864, 480)
    with pytest.raises(Invalid) as err:
        pan.wide({"name": "M"}, {"tiers": [{"name": "a", "sizes": {"9:16": [480, 864]}}]})
    assert err.value.text == "M makes no 16:9 clip"
    ref_ctx.doc(groutes.DRAFT, {}).replace({"model": rules.FL2VA, "lastModel": {"video": rules.FL2VA}})
    with pytest.raises(Invalid) as err:
        pan.pan_plan(ref_ctx, boxes, "x", 1, 175, grabs)
    assert err.value.text == orbit.NO_REF2VA


async def test_job_titles_and_finished(ctx):
    params = {"name": "Set 1", "pictures": ["a"], "prompt": "p", "seed": 1, "length": 175, "grabs": [1]}
    titles = [routes.job({**params, "mode": m}, ctx).summary["title"] for m in ("build", "change", "house",
                                                                                 "house-change")]
    assert titles == ["Stage · Set 1 · build", "Stage · Set 1 · change", "House · Set 1 · build",
                      "House · Set 1 · change"]
    answer = await call(routes.post_build, ctx, body=build_body())
    outputs = land(ctx, 5)
    await finish(ctx, answer["job"], outputs)
    draft = drafts.get("set 1")
    assert (draft["state"], draft["pan"]) == ("ready", outputs[0])
    assert draft["plates"] == dict(zip(STAGE_PLATES, outputs[1:], strict=True))
    again = await call(routes.post_again, ctx, body={"name": "Set 1"})
    assert all("seed" not in params for _, params in ctx.jobs.jobs.values()), "a pan sends no seed"
    assert draft["seed"] is None
    line = "The orbit has 100 frames; the views need 167"
    await finish(ctx, again["job"], outputs[:1], "failed", line)
    assert (draft["state"], draft["problem"], draft["plates"]) == ("failed", line, None)
    third = await call(routes.post_again, ctx, body={"name": "Set 1"})
    await finish(ctx, third["job"], [], "cancelled", "Cancelled")
    assert draft["problem"] == "The pan was cancelled"
    fourth = await call(routes.post_again, ctx, body={"name": "Set 1"})
    del ctx.jobs.jobs[fourth["job"]]                     # cancelled while queued: no job.finished
    assert (await call(routes.get_set, ctx, {"name": "Set 1"}))["draft"]["state"] == "failed"
    ctx.services.clear()
    assert (await call(routes.post_again, ctx, body={"name": "Set 1"}))["problem"] == "Generate Image is not running"


async def test_approve_build(ctx):
    written = await approved_set(ctx)
    home = folder(ctx)
    assert sorted(p.relative_to(home).as_posix() for p in home.rglob("*") if p.is_file()) == sorted(
        ["set.json", "pan.mp4", "pictures/1.png", "pictures/2.png", *(f"plates/{p}.png" for p in STAGE_PLATES)])
    assert json.loads((home / "set.json").read_text(encoding="utf-8")) == written
    assert [red(home / "plates" / f"{p}.png") for p in STAGE_PLATES] == [10, 11, 12, 13, 14]
    assert (written["version"], written["name"], written["revision"], written["audience"]) == (1, "Set 1", 1, "seen")
    assert written["elements"] == ["long table", "two stools"] and written["props"] == written["changes"] == []
    assert written["pictures"] == [{"file": "pictures/1.png", "keep": ""}, {"file": "pictures/2.png",
                                                                            "keep": "the table"}]
    assert written["format"] == {"aspect": "16:9", "width": 864, "height": 480, "fps": 24,
                                 "crop_4_3": {"x": 112, "y": 0, "width": 640, "height": 480}}
    assert written["pan"] == {"file": "pan.mp4", "frames": 175} and written["camera_plan"] == "three_camera"
    assert {p: (v["camera"], v["frame"], v["file"]) for p, v in written["plates"].items()} == {
        "wide": ("wide", 20, "plates/wide.png"), "left": ("1", 44, "plates/left.png"),
        "centre": ("2", 68, "plates/centre.png"), "right": ("3", 92, "plates/right.png"),
        "audience": ("rev", 166, "plates/audience.png")}
    assert written["house"] is None and written["lighting"] is None and written["model"] == "H3 Ref2VA"
    text = (home / "set.json").read_text(encoding="utf-8")
    assert not any(k in text for k in ('"seed"', '"prompt"', '"job"', "Keep the set")), "no prompt, seed or job"
    with Image.open(home / "pictures" / "1.png") as im:
        assert not im.info.get("parameters") and not im.getexif()
    assert (Path(ctx.files.roots["out"]) / DAY / "set1.png").is_file(), "copied, never moved"
    assert drafts.get("Set 1") is None and ctx.bus.sent[-1] == ("changed", "changed", {"name": "Set 1",
                                                                                         "revision": 1})
    assert ctx.events == [], "a build tells no set.changed"


async def test_approve_change(ctx, monkeypatch):
    await approved_set(ctx)
    held = json.loads((folder(ctx) / "set.json").read_text(encoding="utf-8"))
    held["floor_plan"] = {"elements": []}
    (folder(ctx) / "set.json").write_text(json.dumps(held), encoding="utf-8")
    answer = await call(routes.post_change, ctx, body={"name": "set 1", "words": "add a bench stage left"})
    pictures, text, _, length, grabs = ctx.service("pan").calls[-1]
    assert pictures == [f"sets/Set 1/plates/{p}.png" for p in STAGE_PLATES] and (length, grabs) == (
        175, [20, 44, 68, 92, 166])
    assert text.startswith("add a bench stage left\n") and ctx.jobs.get(answer["job"]).plan.summary[
        "title"] == "Stage · Set 1 · change"
    await finish(ctx, answer["job"], land(ctx, 5, 50))
    detail = await call(routes.get_set, ctx, {"name": "Set 1"})
    assert detail["draft"]["mode"] == "change" and detail["draft"]["words"] == "add a bench stage left"
    assert set(detail["draft"]["plates"]) == set(STAGE_PLATES) and set(detail["approved"]["plates"]) == set(
        STAGE_PLATES)

    def full(*args, **kwargs):
        raise OSError(28, "No space left on device")
    with monkeypatch.context() as m:
        m.setattr(record.shutil, "copyfile", full)
        answer = await call(routes.post_approve, ctx, body={"name": "Set 1"})
    assert answer == {"problem": "Could not write Set 1: No space left on device"}
    assert red(folder(ctx) / "plates" / "wide.png") == 10 and not list(folder(ctx).rglob(".*")), "the old set whole"
    written = (await call(routes.post_approve, ctx, body={"name": "Set 1"}))["record"]
    assert [red(folder(ctx) / "plates" / f"{p}.png") for p in STAGE_PLATES] == [50, 51, 52, 53, 54]
    assert (folder(ctx) / "pan.mp4").read_bytes() == bytes([50]) * 32
    assert written["revision"] == 2 and written["floor_plan"] == {"elements": []}
    assert written["props"] == [{"name": "bench", "place": {"words": "stage left", "side": "stage_left",
                                                            "depth": None}}]
    assert written["changes"] == ["add a bench stage left"] and written["pictures"] == held["pictures"]
    assert ctx.events == [("set.changed", {"name": "Set 1", "revision": 2})]
    assert ctx.bus.sent[-1] == ("changed", "changed", {"name": "Set 1", "revision": 2})


async def test_house(ctx):
    house = {"name": "Set 1", "era": "present day", "dress": "sweaters", "hair": "", "size": "fifty"}
    assert (await call(routes.post_house, ctx, body=house))["problem"] == "Approve Set 1's plates first"
    await approved_set(ctx)
    assert (await call(routes.post_house, ctx, body={**house, "era": ""}))["problem"] == (
        "Say the audience's era")
    assert (await call(routes.post_house_change, ctx, body={"name": "Set 1", "words": "x"}))["problem"] == (
        "Approve Set 1's house first")
    answer = await call(routes.post_house, ctx, body=house)
    pictures, text, _, _, grabs = ctx.service("pan").calls[-1]
    assert pictures == ["sets/Set 1/plates/audience.png", "sets/Set 1/plates/wide.png"]
    assert grabs == [20, 44, 116, 166] and text == prompt.house({k: house[k] for k in drafts.HOUSE_WORDS})
    await finish(ctx, answer["job"], land(ctx, 4, 70))
    written = (await call(routes.post_approve, ctx, body={"name": "Set 1"}))["record"]
    assert sorted(p.name for p in (folder(ctx) / "house").iterdir()) == ["left.png", "pan.mp4", "right.png",
                                                                         "row.png", "wide.png"]
    assert {p: (v["camera"], v["frame"]) for p, v in written["house"]["plates"].items()} == {
        "wide": ("rev", 20), "left": ("house_left", 44), "right": ("house_right", 116), "row": ("rev", 166)}
    assert written["house"]["plates"]["row"]["framing"] == "medium" and written["revision"] == 2
    assert (written["house"]["era"], written["house"]["pan"]) == ("present day", {"file": "house/pan.mp4",
                                                                                     "frames": 175})
    answer = await call(routes.post_house_change, ctx, body={"name": "Set 1", "words": "make them older"})
    pictures = ctx.service("pan").calls[-1][0]
    assert pictures == [*(f"sets/Set 1/house/{p}.png" for p in HOUSE_PLATES), "sets/Set 1/plates/audience.png"]
    assert ctx.jobs.get(answer["job"]).plan.summary["title"] == "House · Set 1 · change"
    await finish(ctx, answer["job"], land(ctx, 4, 90))
    written = (await call(routes.post_approve, ctx, body={"name": "Set 1"}))["record"]
    assert written["house"]["changes"] == ["make them older"] and written["revision"] == 3
    assert red(folder(ctx) / "house" / "row.png") == 93 and red(folder(ctx) / "plates" / "wide.png") == 10
    switched = (await call(routes.post_audience, ctx, body={"audience": "heard", "name": "Set 1"}))["record"]
    assert switched["audience"] == "heard" and switched["revision"] == 3
    assert (folder(ctx) / "house" / "pan.mp4").is_file(), "switching away keeps the house's files"


async def test_routes(ctx):
    assert await call(routes.get_sets, ctx) == {"sets": [], "prompts": {"stage": "", "house": ""}}
    with pytest.raises(Invalid) as err:
        await call(routes.get_set, ctx, {"name": "Set 1"})
    assert err.value.text == "No set is called Set 1"
    assert (await call(routes.post_build, ctx, body=build_body(name="a/b")))["problem"] == (
        "Use a plain set name, without slashes")
    bad = build_body(pictures=[{"id": "", "keep": ""}])
    assert (await call(routes.post_build, ctx, body=bad))["problem"] == "Put a picture of the set in box 1"
    gap = build_body(pictures=[{"id": f"out/{DAY}/set1.png", "keep": ""}, {"id": "", "keep": ""},
                               {"id": f"out/{DAY}/set3.png", "keep": "x"}])         # the web's empty box between
    assert await call(routes.post_build, ctx, body=gap) == {"problem": "Box 2 holds no picture"}
    first = build_body(pictures=[{"id": "", "keep": "k"}, {"id": f"out/{DAY}/set2.png", "keep": ""}])
    assert await call(routes.post_build, ctx, body=first) == {"problem": "Put a picture of the set in box 1"}
    assert await call(routes.post_build, ctx, body=gap) == {"problem": "Box 2 holds no picture"}
    detail = await call(routes.get_set, ctx, {"name": "set 1"})
    assert detail["draft"]["state"] == "none" and detail["inputs"]["pictures"][1] == {"id": "", "keep": ""}
    with pytest.raises(Invalid):
        await call(routes.post_build, ctx, body=build_body(audience="loud"))
    answer = await call(routes.post_build, ctx, body=build_body())
    pictures, text, _, length, grabs = ctx.service("pan").calls[-1]
    assert pictures == [f"out/{DAY}/set1.png", f"out/{DAY}/set2.png"] and (length, grabs) == (
        175, [20, 44, 68, 92, 166])
    assert text == prompt.build([{"keep": ""}, {"keep": "the table"}], "a scripted scene",
                                ["long table", "two stools"])
    assert (await call(routes.post_build, ctx, body=build_body()))["problem"] == "Set 1 is being rendered now"
    listed = (await call(routes.get_sets, ctx))["sets"]
    assert listed == [{"name": "Set 1", "approved": False, "revision": None, "audience": "seen", "house": False,
                       "thumb": None, "state": "rendering"}]
    await finish(ctx, answer["job"], land(ctx, 5))
    ready = await call(routes.get_set, ctx, {"name": "Set 1"})
    assert ready["inputs"]["pieces"] == ["long table", "two stools"] and ready["approved"] is None
    assert set(ready["draft"]) == {"mode", "state", "job", "problem", "model", "words", "pan", "plates"}
    assert ready["draft"]["plates"]["wide"]["url"].startswith(f"/files/out/{DAY}/") and ready["draft"]["pan"][
        "thumb"].startswith("/thumbs/clips/")
    await call(routes.post_approve, ctx, body={"name": "Set 1"})
    assert (await call(routes.post_build, ctx, body=build_body()))["problem"] == (
        "Set 1 is approved: ask for a change, or build a new set under another name")
    assert (await call(routes.post_change, ctx, body={"name": "Set 1", "words": " "}))["problem"] == (
        "Say the change")
    assert (await call(routes.post_approve, ctx, body={"name": "Set 1"}))["problem"] == (
        "There are no plates to approve")
    drafts.clear()                                                   # a restart: the record is the inputs
    opened = await call(routes.get_set, ctx, {"name": "SET 1"})
    assert opened["name"] == "Set 1" and opened["draft"] is None
    assert opened["inputs"]["pictures"] == [{"id": "sets/Set 1/pictures/1.png", "keep": ""},
                                            {"id": "sets/Set 1/pictures/2.png", "keep": "the table"}]
    assert set(opened["approved"]) == {"record", "plates", "house", "pan_url", "house_pan_url", "pictures"}
    assert opened["approved"]["plates"]["wide"]["id"] == "sets/Set 1/plates/wide.png"
    assert "?v=" in opened["approved"]["plates"]["wide"]["url"] and opened["approved"]["house"] is None
    assert opened["approved"]["pan_url"].startswith("/api/stage/pan?name=Set%201&which=stage&v=")
    served = await call(routes.get_pan, ctx, {"name": "Set 1", "which": "stage"})
    assert Path(served.path) == folder(ctx) / "pan.mp4" and served.headers["cache-control"] == "no-store"
    with pytest.raises(Invalid):
        await call(routes.get_pan, ctx, {"name": "Set 1", "which": "house"})
    listed = (await call(routes.get_sets, ctx))["sets"][0]
    assert listed["approved"] and listed["revision"] == 1 and listed["thumb"].startswith("/thumbs/sets/Set%201/")
    answer = await call(routes.post_change, ctx, body={"name": "Set 1", "words": "remove the long table"})
    assert (await call(routes.post_delete, ctx, body={"name": "Set 1"}))["problem"] == "Set 1 is being rendered now"
    assert await call(routes.post_discard, ctx, body={"name": "Set 1"}) == {"ok": True}
    assert (await call(routes.get_set, ctx, {"name": "Set 1"}))["draft"] is None
    assert json.loads((folder(ctx) / "set.json").read_text(encoding="utf-8"))["revision"] == 1, "as it was"
    with pytest.raises(Invalid):
        await call(routes.post_audience, ctx, body={"audience": "loud", "name": "Set 1"})
    assert (await call(routes.post_audience, ctx, body={"name": "Nope", "audience": "none"}))["problem"] == (
        "Approve Nope's plates first")
    assert (await call(routes.post_audience, ctx, body={"audience": "none", "name": "Set 1"}))["record"][
        "audience"] == "none"
    ctx.service("pan").refuse = Invalid("model", orbit.NO_REF2VA)
    assert (await call(routes.post_change, ctx, body={"name": "Set 1", "words": "x"}))["problem"] == orbit.NO_REF2VA
    assert await call(routes.post_delete, ctx, body={"name": "Set 1"}) == {"ok": True}
    assert not folder(ctx).exists() and (await call(routes.get_sets, ctx))["sets"] == []
    assert ctx.bus.sent[-1] == ("changed", "changed", {"name": "Set 1"})


FFMPEG = shutil.which("ffmpeg") and shutil.which("ffprobe")


@pytest.mark.skipif(not FFMPEG, reason="no ffmpeg")
def test_a_real_pan_gives_its_plates(tmp_path, monkeypatch):
    """A 175-frame 864×480 clip whose frame n draws n in eight 108 px stripes; each plate is its frame, full size."""
    monkeypatch.setenv("FFMPEG_BINARY", shutil.which("ffmpeg"))
    monkeypatch.setenv("FFPROBE_BINARY", shutil.which("ffprobe"))
    w, h, bits = 864, 480, 8
    raw = bytearray()
    for n in range(175):
        raw += bytes(255 if n >> (bits - 1 - x // 108) & 1 else 0 for x in range(w)) * h
    clip = tmp_path / "pan.mp4"
    subprocess.run([shutil.which("ffmpeg"), "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "gray", "-s",
                    f"{w}x{h}", "-r", "24", "-i", "-", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-qp", "0",
                    str(clip)], input=bytes(raw), check=True, capture_output=True, timeout=300)
    for table in (record.STAGE, record.HOUSE):
        grabs = list(table.values())
        made = frames.extract("j1", 2, {"clip": str(clip), "frames": grabs}, str(tmp_path / "state"))
        for png, n in zip(made, grabs, strict=True):
            with Image.open(png) as im:
                gray = im.convert("L")
                assert im.size == (w, h)
                assert sum(1 << (bits - 1 - i) for i in range(bits) if gray.getpixel((i * 108 + 54, h // 2)) > 128
                           ) == n


def test_media_never_deletes_or_moves_a_set_file(tmp_path):
    drive = tmp_path / "Drive"
    drive.mkdir()
    files = Files(tmp_path / "data", drive)
    plates = files.roots["sets"] / "Set 1" / "plates"
    plates.mkdir(parents=True)
    Image.new("RGB", (8, 8)).save(plates / "wide.png")
    for op in (lambda: files.delete(["sets/Set 1/plates/wide.png"]),
               lambda: files.move(["sets/Set 1/plates/wide.png"], "")):
        with pytest.raises(Invalid) as err:
            op()
        assert err.value.text == "A set's plates and pan stay in its set"
    assert (plates / "wide.png").is_file() and not list(drive.iterdir())
    out = files.roots["out"] / DAY
    out.mkdir()
    Image.new("RGB", (8, 8)).save(out / "a.png")
    assert files.move([f"out/{DAY}/a.png"], "") == [(f"out/{DAY}/a.png", "drive/a.png")], "Temp still moves"


async def test_a_sets_name_is_its_folder(ctx):
    await approved_set(ctx)
    held = json.loads((folder(ctx) / "set.json").read_text(encoding="utf-8"))
    (folder(ctx) / "set.json").write_text(json.dumps({**held, "name": "../Other"}), encoding="utf-8")
    assert (await call(routes.get_set, ctx, {"name": "set 1"}))["name"] == "Set 1"
    served = await call(routes.get_pan, ctx, {"name": "set 1", "which": "stage"})
    assert Path(served.path) == folder(ctx) / "pan.mp4"
    answer = await call(routes.post_change, ctx, body={"name": "SET 1", "words": "add a lamp"})
    await finish(ctx, answer["job"], land(ctx, 5, 30))
    written = (await call(routes.post_approve, ctx, body={"name": "set 1"}))["record"]
    assert written["name"] == "Set 1" and ctx.events[-1] == ("set.changed", {"name": "Set 1", "revision": 2})


async def test_build_lists_are_lists(ctx):
    for key in ("pictures", "pieces"):
        with pytest.raises(Invalid) as err:
            await call(routes.post_build, ctx, body=build_body(**{key: "long table"}))
        assert err.value.text == f"{key.capitalize()} must be a list"
    junk = build_body(pictures=["x", {"id": f"out/{DAY}/set1.png", "keep": ""}])
    assert await call(routes.post_build, ctx, body=junk) == {"problem": "Put a picture of the set in box 1"}


async def test_an_again_during_approve_keeps_its_draft(ctx, monkeypatch):
    answer = await call(routes.post_build, ctx, body=build_body(name="Other"))
    await finish(ctx, answer["job"], land(ctx, 5))
    real = record.approve
    newer = {}

    def racing(ctx_, draft):
        written = real(ctx_, draft)
        newer.update(draft, job="j_99", state="rendering")      # Again pressed while the copies ran
        drafts.put(newer)
        return written
    monkeypatch.setattr(record, "approve", racing)
    assert "record" in await call(routes.post_approve, ctx, body={"name": "Other"})
    assert drafts.get("Other") is newer, "the newer draft is not dropped"


def test_a_leading_preposition_is_not_the_thing():
    for words, thing in (("bring in a piano", "piano"), ("put on the piano", "piano"),
                         ("bring into view a piano", "view a piano"), ("bring in some pianos", "pianos")):
        assert change.parse(words, {})["thing"] == thing
    assert change.parse("bring in a piano stage left", {})["place"]["side"] == "stage_left"
