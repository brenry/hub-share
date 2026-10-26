"""An extra (a featured audience member). Its prompt ends in the box whole; the extra's
cast is one 107-frame orbit and four views (front, left, right, face-1); the extra's draft ends ready with four pictures
(a cast member's with four is failed); the extra's Approve writes `role: "audience"` and the extra's seat; `/seat`
refuses a seat out of range and rewrites only the record's seat. Also the stand-in orbit service and the fixtures
`test_casting_costume` uses."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image

from hub.core.api import Invalid, JobPlan
from hub.core.files import Files
from hub.modules.casting import prompt, record, routes, state
from hub.modules.generate_image import orbit
from hub.modules.generate_image import routes as groutes
from tests.engine import test_upstream_rules as rules
from tests.engine.helpers import FakeCtx, FakeEngine, FakeRequest

cat, accepted, ref_ctx = rules.cat, rules.accepted, rules.ref_ctx
DAY = "2026-10-20"
SEAT = {"side": "left", "row": 3}
BOX = "Prompt 1"


@pytest.fixture(autouse=True)
def no_drafts():
    state.clear()
    yield
    state.clear()


class Orbit:
    """Generate's service, stood in, as Casting calls it: three arguments, or five (frames, views)."""

    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def __call__(self, pictures: list[str], text: str, seed: int, *shape) -> JobPlan:
        self.calls.append((pictures, text, seed, *shape))
        return JobPlan("image", "m", ({"kind": "video"}, {"kind": "frames"}), {"model": "H3 Ref2VA", "kind": "clip"})


@pytest.fixture
def ctx(tmp_path: Path) -> FakeCtx:
    held = FakeCtx("casting", tmp_path / "data", FakeEngine(None), {routes.KIND: routes.job})
    chars = tmp_path / "Characters"
    chars.mkdir()
    for name in ("Character 14", "Character 8"):
        Image.new("RGB", (64, 64)).save(chars / f"{name}.png")
    held.files = Files(tmp_path / "data", None, chars)
    held.offer("orbit", Orbit())
    return held


async def call(fn, ctx, query: dict | None = None, body: dict | None = None):
    return await fn(ctx, FakeRequest(query, json.dumps(body).encode() if body is not None else b""))


def land(ctx, n: int, tag: str = "o") -> list[str]:
    """What a finished orbit job lands: one clip, then `n` pictures."""
    out, clips = Path(ctx.files.roots["out"]) / DAY, Path(ctx.files.roots["clips"]) / DAY
    out.mkdir(parents=True, exist_ok=True)
    clips.mkdir(parents=True, exist_ok=True)
    (clips / f"{tag}.mp4").write_bytes(b"\0" * 32)
    for i in range(n):
        Image.new("RGB", (70, 124)).save(out / f"{tag}{i}.png")
    return [f"clips/{DAY}/{tag}.mp4", *(f"out/{DAY}/{tag}{i}.png" for i in range(n))]


async def finish(ctx, job_id: str, outputs: list[str]) -> None:
    ctx.jobs.get(job_id).state = "done"
    await state.finished(ctx, {"job": job_id, "tool": "casting", "state": "done", "outputs": outputs, "notes": {}})


def body(name: str = "Character 14", **extra) -> dict:
    return {"name": name, "headshot": {"keep": "the face", "ignore": ""}, "bits": [],
            "facts": {"age": "30", "build": "slim"}, **extra}


async def approved(ctx, name: str = "Character 8", **extra) -> dict:
    """`name` cast and approved through the routes."""
    answer = await call(routes.post_cast, ctx, body=body(name, **extra))
    n = len(record.AUDIENCE) if extra.get("role") == "audience" else len(record.SHEET)
    await finish(ctx, answer["job"], land(ctx, n, f"{name}{len(ctx.jobs.jobs)}"))
    return await call(routes.post_approve, ctx, body={"name": name})


async def test_an_audience_cast_is_107_frames_four_views_and_its_title(ctx):
    answer = await call(routes.post_cast, ctx, body=body(role="audience", seat=SEAT, prompt=BOX))
    job = ctx.jobs.get(answer["job"])
    params = ctx.jobs.jobs[answer["job"]][1]
    assert (params["frames"], params["views"], params["role"]) == (107, [2, 21, 63, 84], "audience")
    assert job.plan.summary["title"] == "Cast · Character 14 · audience · 1 picture"
    pictures, text, _, frames, views = ctx.service("orbit").calls[-1]
    assert (pictures, frames, views) == (["chars/Character 14.png"], 107, [2, 21, 63, 84])
    assert text.endswith(prompt.SEPARATOR + BOX)                         # the box whole, as typed
    opened = await call(routes.get_draft, ctx, {"name": "Character 14"})
    assert (opened["role"], opened["seat"], opened["state"]) == ("audience", SEAT, "rendering")


async def test_a_cast_members_call_stays_three_arguments(ctx):
    await call(routes.post_cast, ctx, body=body("Character 8"))
    assert len(ctx.service("orbit").calls[-1]) == 3
    assert ctx.jobs.get("j_1").plan.summary["title"] == "Cast · Character 8 · 1 picture"


async def test_four_pictures_end_an_audience_draft_ready_and_a_cast_draft_failed(ctx):
    extra = await call(routes.post_cast, ctx, body=body(role="audience"))
    member = await call(routes.post_cast, ctx, body=body("Character 8"))
    await finish(ctx, extra["job"], outs := land(ctx, 4, "a"))
    await finish(ctx, member["job"], land(ctx, 4, "k"))
    character_14 = await call(routes.get_draft, ctx, {"name": "Character 14"})
    assert character_14["state"] == "ready" and character_14["views"] == dict(zip(record.AUDIENCE, outs[1:],
                                                                                  strict=True))
    assert (await call(routes.get_draft, ctx, {"name": "Character 8"}))["state"] == "failed"


async def test_the_extras_approve_list_tag_and_files(ctx):
    written = await approved(ctx, "Character 14", role="audience", seat=SEAT)
    assert (written["role"], written["seat"], set(written["sheet"])) == ("audience", SEAT, set(record.AUDIENCE))
    listed = {c["name"]: c for c in await call(routes.get_list, ctx)}
    assert (listed["Character 14"]["role"], listed["Character 14"]["costumes"],
            listed["Character 8"]["role"]) == ("audience", 0, None)
    await approved(ctx, "Character 8")
    assert {c["name"]: c["role"] for c in await call(routes.get_list, ctx)} == {"Character 14": "audience",
                                                                                "Character 8": "cast"}
    state.clear()                                                    # a restart: the extra's record is the draft
    opened = await call(routes.get_draft, ctx, {"name": "Character 14"})
    assert (opened["role"], opened["seat"], opened["state"]) == ("audience", SEAT, "approved")
    assert set(opened["files"]["views"]) == set(record.AUDIENCE) and opened["costumes"] == []


async def test_the_seat_is_refused_out_of_range_and_rewrites_only_the_seat(ctx):
    line = "A seat is a side (left, centre or right) and a row from 1 to 12"
    assert await call(routes.post_seat, ctx, body={"name": "Character 14", "seat": {"side": "left", "row": 13}}) == {
        "problem": line}
    assert (await call(routes.post_cast, ctx, body=body(role="audience", seat={"side": "up", "row": 1})))[
        "problem"] == line
    unsaved = await call(routes.post_seat, ctx, body={"name": "Character 14", "seat": {"side": "right", "row": 2}})
    assert unsaved == {"seat": {"side": "right", "row": 2}, "record": None}
    written = await approved(ctx, "Character 14", role="audience", seat=SEAT)
    home = Path(ctx.files.roots["chars"]) / "Character 14"
    before = json.loads((home / "casting.json").read_text(encoding="utf-8"))
    assert before == written
    answer = await call(routes.post_seat, ctx, body={"name": "Character 14", "seat": {"side": "centre", "row": 12}})
    after = json.loads((home / "casting.json").read_text(encoding="utf-8"))
    assert after == {**before, "seat": {"side": "centre", "row": 12}} == answer["record"]
    assert ctx.bus.sent[-1] == ("changed", "changed", {"name": "Character 14"})
    assert (await call(routes.get_draft, ctx, {"name": "Character 14"}))["seat"] == {"side": "centre", "row": 12}
    character_8 = await approved(ctx, "Character 8")
    assert (await call(routes.post_seat, ctx, body={"name": "Character 8", "seat": SEAT}))["record"] is None
    assert record.read(ctx, "Character 8") == character_8, "a cast member's record has no seat"


async def test_a_bad_role_is_a_bad_request(ctx):
    with pytest.raises(Invalid) as err:
        await call(routes.post_cast, ctx, body=body(role="crowd"))
    assert err.value.field == "role"


async def test_casting_as_audience_is_refused_while_the_character_has_costumes(ctx):
    await approved(ctx, "Character 8")
    found = record.read(ctx, "Character 8")
    found["variants"] = {"Leather jacket": {"from": found["approved"]}}
    (Path(ctx.files.roots["chars"]) / "Character 8" / "casting.json").write_text(json.dumps(found), encoding="utf-8")
    answer = await call(routes.post_cast, ctx, body=body("Character 8", role="audience"))
    assert answer == {"problem": "Character 8 has costumes; remove them before casting as audience"}


async def test_with_generates_real_orbit(ref_ctx):
    ctx = FakeCtx("casting", Path(ref_ctx.files.data_dir), FakeEngine(None), {routes.KIND: routes.job})
    ctx.files = ref_ctx.files
    ctx.offer("orbit", lambda *args: orbit.orbit_plan(ref_ctx, *args))
    ref_ctx.doc(groutes.DRAFT, {}).replace({"model": rules.REF2VA})
    answer = await call(routes.post_cast, ctx, body={"name": "Character 12", "role": "audience", "seat": SEAT,
                                                     "headshot": {"keep": "", "ignore": ""}, "bits": [],
                                                     "prompt": BOX})
    clip, views = ctx.jobs.get(answer["job"]).plan.tasks
    assert clip["frames"] == record.EXTRA_FRAMES == 107 and views["frames"] == list(record.AUDIENCE.values())
    assert clip["prompt"].endswith(prompt.SEPARATOR + BOX)


async def test_a_refused_audience_cast_leaves_the_ready_sheet_approvable(ctx):
    await approved(ctx, "Character 8")
    found = record.read(ctx, "Character 8")
    found["variants"] = {"Hat": {"from": found["approved"]}}
    (Path(ctx.files.roots["chars"]) / "Character 8" / "casting.json").write_text(json.dumps(found), encoding="utf-8")
    answer = await call(routes.post_cast, ctx, body=body("Character 8"))
    await finish(ctx, answer["job"], land(ctx, 6, "r"))
    assert "problem" in await call(routes.post_cast, ctx, body=body("Character 8", role="audience"))
    written = await call(routes.post_approve, ctx, body={"name": "Character 8"})
    assert written["role"] == "cast" and written["variants"] == {"Hat": {"from": found["approved"]}}
    opened = await call(routes.get_draft, ctx, {"name": "Character 8"})
    assert (opened["role"], opened["seat"]) == ("cast", record.SEAT), "a refused cast leaves the role and seat"


async def test_a_refused_audience_cast_changes_neither_role_nor_seat(ctx):
    answer = await call(routes.post_cast, ctx, body=body("Character 8"))
    await finish(ctx, answer["job"], land(ctx, 6, "s"))
    ctx.services.clear()                                           # Generate not running: the cast is refused
    refused = await call(routes.post_cast, ctx, body=body("Character 8", role="audience", seat=SEAT))
    assert refused == {"problem": "Generate Image is not running"}
    opened = await call(routes.get_draft, ctx, {"name": "Character 8"})
    assert (opened["role"], opened["seat"], set(opened["views"])) == ("cast", record.SEAT, set(record.SHEET))


class Watched:
    """`record.LOCK` stood in: whether it is held now."""

    def __init__(self) -> None:
        self.held = False

    def __enter__(self):
        self.held = True

    def __exit__(self, *exc):
        self.held = False


async def test_stale_files_are_erased_under_the_lock(ctx, monkeypatch):
    from hub.modules.casting import costume, variants
    await approved(ctx, "Character 8")
    lock, erased = Watched(), []
    monkeypatch.setattr(record, "LOCK", lock)
    real = Path.unlink

    def unlink(self, *args, **kwargs):
        erased.append((self.name, lock.held))
        return real(self, *args, **kwargs)
    monkeypatch.setattr(Path, "unlink", unlink)
    out = Path(ctx.files.roots["out"]) / DAY
    out.mkdir(parents=True, exist_ok=True)
    for i in range(2):
        Image.new("RGB", (40, 40)).save(out / f"bit{i}.png")
    for n in (2, 1):                                              # two bits, then one: bits/3.png goes
        answer = await call(routes.post_cast, ctx, body=body(
            "Character 8", bits=[{"id": f"out/{DAY}/bit{i}.png"} for i in range(n)]))
        await finish(ctx, answer["job"], land(ctx, 6, f"b{n}"))
        await call(routes.post_approve, ctx, body={"name": "Character 8"})
    for n in (2, 1):                                              # a costume of two pictures, then one
        answer = await call(costume.post_cast, ctx, body={"name": "Character 8", "variant": "Coat", "pictures": [
            {"id": f"out/{DAY}/bit{i}.png"} for i in range(n)]})
        await finish(ctx, answer["job"], land(ctx, 6, f"c{n}"))
        assert "costume" in await call(costume.post_approve, ctx, body={"name": "Character 8", "variant": "Coat"})
    stale = [e for e in erased if not e[0].startswith(".")]
    assert ("3.png", True) in stale and ("4.png", True) in stale and all(held for _, held in stale)
    assert variants.entry(record.read(ctx, "Character 8"), "Coat") is not None
