"""A costume on a character's approved cast sheet. Its prompt (both face frames, the face line, the
words line, the clothing of the frames ruled out by name, the ignores, within 4000); its refusals, each one line; its
job (face-1, face-2, then the costume pictures; 124 frames, six views); its Approve (its folder and `variants` entry,
every other key of the character's record as it was) and Remove (the record before the folder); the character's own
approve after keeps it; a rename carries it; the Characters listing does not see it."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image

from hub.core.api import Invalid
from hub.modules.casting import costume, prompt, record, routes, state, variants
from tests.engine import test_casting_extra as extra

ctx, no_drafts = extra.ctx, extra.no_drafts                  # the fixtures
approved, call, finish, land = extra.approved, extra.call, extra.finish, extra.land

JACKET = "a worn black leather jacket, white T-shirt, dark jeans, black boots"
FACE1, FACE2 = "chars/Character 8/sheet/face-1.png", "chars/Character 8/sheet/face-2.png"


def jacket(ctx, n: int = 1) -> list[dict]:
    """`n` costume pictures in Temp, each with its lines."""
    out = Path(ctx.files.roots["out"]) / "2026-10-20"
    out.mkdir(parents=True, exist_ok=True)
    for i in range(n):
        Image.new("RGB", (60, 80), (i, 1, 2)).save(out / f"j{i}.jpg")
    return [{"id": f"out/2026-10-20/j{i}.jpg", "keep": f"the jacket {i}", "ignore": f"the figure {i}"}
            for i in range(n)]


def home(ctx, name: str = "Character 8") -> Path:
    return Path(ctx.files.roots["chars"]) / name


async def cast(ctx, variant: str = "Leather jacket", **extra) -> dict:
    return await call(costume.post_cast, ctx, body={"name": "Character 8", "variant": variant, **extra})


async def made(ctx, variant: str = "Leather jacket", n: int = 1) -> dict:
    """A costume of `n` pictures and words, cast, landed and approved."""
    answer = await cast(ctx, variant, pictures=jacket(ctx, n), words=JACKET)
    await finish(ctx, answer["job"], land(ctx, 6, f"c{len(ctx.jobs.jobs)}"))
    return await call(costume.post_approve, ctx, body={"name": "Character 8", "variant": variant})


def test_the_costume_prompt():
    text = prompt.costume([{"keep": "the jacket", "ignore": "the figure wearing it"}, {"keep": "", "ignore": ""}],
                          {"age": "50", "build": "heavy"}, JACKET + ".", "Prompt 1")
    a = text[:-len(prompt.SEPARATOR + "Prompt 1")]
    assert text.endswith(prompt.SEPARATOR + "Prompt 1")
    assert a == "\n".join([
        "subject_definitions: <Subject 1> is the character shown in <Picture 1> and <Picture 2>. heavy",
        "<Picture 3>: the jacket", f"{JACKET}.", "",                                    # no face line
        "retention_analysis: <Picture 3>: the figure wearing it"])
    assert "wears" not in prompt.costume([{"keep": "x", "ignore": ""}], None, "  ")
    assert "x" * 4000 + "." in prompt.costume([], None, "x" * 4000), "the costume's words whole"


async def test_the_costume_job_is_the_characters_faces_then_the_costume_124_frames_six_views(ctx):
    await approved(ctx)
    pictures = jacket(ctx, 2)
    answer = await cast(ctx, pictures=pictures, words=JACKET)
    params = ctx.jobs.jobs[answer["job"]][1]
    assert params["pictures"] == [FACE1, FACE2, *(p["id"] for p in pictures)]
    assert (params["frames"], params["views"], params["variant"]) == (124, [2, 21, 42, 63, 84, 113], "Leather jacket")
    assert params["prompt"] == prompt.costume(pictures, {"age": "30", "build": "slim"}, JACKET)
    assert ctx.jobs.get(answer["job"]).plan.summary["title"] == "Cast · Character 8 · Leather jacket · 4 pictures"
    assert ctx.service("orbit").calls[-1][3:] == (124, [2, 21, 42, 63, 84, 113])
    assert ctx.bus.sent[-1] == ("changed", "changed", {"name": "Character 8", "variant": "Leather jacket"})
    opened = await call(costume.get_costume, ctx, {"name": "Character 8", "variant": "leather JACKET"})
    assert (opened["variant"], opened["state"], opened["faces"], opened["words"]) == (
        "Leather jacket", "rendering", [FACE1, FACE2], JACKET)
    assert opened["from"] == record.read(ctx, "Character 8")["approved"] and all(opened["face_thumbs"])
    chips = (await call(routes.get_draft, ctx, {"name": "Character 8"}))["costumes"]
    assert chips == [{"variant": "Leather jacket", "state": "rendering", "approved": False, "earlier": False,
                      "thumb": None}]


async def test_the_refusals(ctx):
    assert (await cast(ctx, words=JACKET))["problem"] == "Approve Character 8's sheet as cast before a costume"
    assert (await call(costume.get_costume, ctx, {"name": "Character 8", "variant": "X"}))["problem"] == (
        "Approve Character 8's sheet as cast before a costume")
    await approved(ctx, "Character 14", role="audience")
    assert (await call(costume.post_cast, ctx, body={"name": "Character 14", "variant": "Coat", "words": "a coat"}))[
        "problem"] == "Approve Character 14's sheet as cast before a costume"
    await approved(ctx)
    assert (await cast(ctx))["problem"] == "Give the costume a picture or words"
    assert (await cast(ctx, pictures=jacket(ctx, 8)))["problem"] == "A costume takes at most 7 pictures; this has 8"
    assert (await cast(ctx, "Sheet", words=JACKET))["problem"] == "Sheet is a name Casting uses; choose another"
    assert (await cast(ctx, "bits", words=JACKET))["problem"] == "bits is a name Casting uses; choose another"
    assert (await cast(ctx, "a/b", words=JACKET))["problem"] == "Use a plain costume name, without slashes"
    (home(ctx) / "Old").mkdir()
    assert (await cast(ctx, "old", words=JACKET))["problem"] == (
        "A folder called Old is in Character 8's folder and is not a costume of the character")
    (Path(ctx.files.roots["clips"]) / "c.mp4").write_bytes(b"\0")
    assert (await cast(ctx, pictures=[{"id": "clips/c.mp4"}]))["problem"] == "Box 3 holds no picture"
    (home(ctx) / "sheet" / "face-2.png").unlink()
    assert (await cast(ctx, words=JACKET))["problem"] == ("Character 8's approved face frames are gone; "
                                                         "cast the character again")
    assert (await call(costume.post_approve, ctx, body={"name": "Character 8", "variant": "Leather jacket"}))[
        "problem"] == record.NOT_READY
    assert (await call(costume.post_again, ctx, body={"name": "Character 8", "variant": "Nothing"}))[
        "problem"] == "Cast Nothing first"
    assert (await call(costume.post_remove, ctx, body={"name": "Character 8", "variant": "Nothing"}))[
        "problem"] == "Character 8 has no costume called Nothing"
    with pytest.raises(Invalid):
        await cast(ctx, words=JACKET, name="Nobody")


async def test_approve_writes_its_folder_and_entry_and_leaves_the_record_as_it_was(ctx):
    base = await approved(ctx)
    entry = await made(ctx, n=2)
    folder = home(ctx) / "Leather jacket"
    assert sorted(p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_file()) == sorted(
        ["costume/3.jpg", "costume/4.jpg", "orbit.mp4", *(f"sheet/{v}.png" for v in record.SHEET)])
    found = record.read(ctx, "Character 8")
    assert {k: v for k, v in found.items() if k != "variants"} == base
    assert found["variants"] == {"Leather jacket": entry}
    assert entry["from"] == base["approved"] and entry["orbit"] == "Leather jacket/orbit.mp4"
    assert entry["costume"] == {"words": JACKET, "pictures": [
        {"file": "Leather jacket/costume/3.jpg", "keep": "the jacket 0", "ignore": "the figure 0"},
        {"file": "Leather jacket/costume/4.jpg", "keep": "the jacket 1", "ignore": "the figure 1"}]}
    assert entry["sheet"]["face-2"] == {"file": "Leather jacket/sheet/face-2.png", "frame": 113}
    text = json.dumps(found)
    assert "prompt" not in text and "seed" not in text and "j_" not in text
    opened = await call(costume.get_costume, ctx, {"name": "Character 8", "variant": "Leather jacket"})
    assert opened["state"] == "approved" and opened["record"] == entry
    assert opened["files"]["views"]["front"] == "chars/Character 8/Leather jacket/sheet/front.png"
    assert opened["files"]["orbit_url"].startswith("/api/casting/orbit?name=Character%208&variant=Leather%20jacket&v=")
    served = await call(routes.get_orbit, ctx, {"name": "Character 8", "variant": "Leather jacket"})
    assert Path(served.path) == folder / "orbit.mp4"
    listed = {c["name"]: c for c in await call(routes.get_list, ctx)}["Character 8"]
    assert (listed["role"], listed["costumes"]) == ("cast", 1)
    state.clear()                                                   # a restart: the entry is the draft
    again = await call(costume.get_costume, ctx, {"name": "Character 8", "variant": "Leather jacket"})
    assert [p["id"] for p in again["pictures"]] == ["chars/Character 8/Leather jacket/costume/3.jpg",
                                                    "chars/Character 8/Leather jacket/costume/4.jpg"]
    assert "job" in await call(costume.post_again, ctx, body={"name": "Character 8", "variant": "Leather jacket"})


async def test_a_second_costume_approve_drops_a_picture_it_has_not(ctx):
    await approved(ctx)
    await made(ctx, n=2)
    await made(ctx, n=1)
    assert sorted(p.name for p in (home(ctx) / "Leather jacket" / "costume").iterdir()) == ["3.jpg"]


async def test_the_characters_own_approve_keeps_the_costumes_and_a_recast_marks_them_earlier(ctx, monkeypatch):
    stamps = iter(f"2026-10-20T10:00:0{n}+00:00" for n in range(9))
    monkeypatch.setattr(record, "now", lambda: next(stamps))
    await approved(ctx)
    entry = await made(ctx)
    rebase = await approved(ctx)
    assert rebase["variants"] == {"Leather jacket": entry}
    chips = (await call(routes.get_draft, ctx, {"name": "Character 8"}))["costumes"]
    assert [(c["variant"], c["approved"], c["earlier"]) for c in chips] == [("Leather jacket", True, True)]
    assert chips[0]["thumb"].startswith("/thumbs/chars/Character%208/Leather%20jacket/sheet/front.png/")


async def test_remove_writes_the_record_before_the_folder_goes(ctx, monkeypatch):
    await approved(ctx)
    await made(ctx)
    seen = []
    real = variants.shutil.rmtree

    def watch(path, *args, **kwargs):
        seen.append(("variants" in (record.read(ctx, "Character 8") or {}), Path(path).name))
        return real(path, *args, **kwargs)
    monkeypatch.setattr(variants.shutil, "rmtree", watch)
    answer = await call(costume.post_remove, ctx, body={"name": "Character 8", "variant": "leather jacket"})
    assert answer == {"removed": "Leather jacket"} and seen == [(False, "Leather jacket")]
    assert not (home(ctx) / "Leather jacket").exists() and (home(ctx) / "sheet").is_dir()
    assert (await call(routes.get_draft, ctx, {"name": "Character 8"}))["costumes"] == []
    await cast(ctx, "Hat", words="a hat")                             # a costume only in memory: just dropped
    assert await call(costume.post_remove, ctx, body={"name": "Character 8", "variant": "Hat"}) == {"removed": "Hat"}
    assert state.get("Character 8", "Hat") is None


async def test_a_rename_carries_the_costume_and_the_listing_does_not_see_it(ctx):
    await approved(ctx)
    await made(ctx)
    before = ctx.files.characters()
    assert [c["name"] for c in before] == ["Character 14", "Character 8"] and before[1]["views"] == []
    ctx.files.character_rename("chars/Character 8.png", "Character 15")
    found = record.read(ctx, "Character 15")
    entry = found["variants"]["Leather jacket"]
    files = variants.urls(ctx, "Character 15", "Leather jacket", entry)
    assert all(ctx.files.existing_image(i) for i in files["views"].values())
    assert ctx.files.existing_image(files["pictures"][0]) and (home(ctx, "Character 15") / entry["orbit"]).is_file()
    assert [c["name"] for c in ctx.files.characters()] == ["Character 14", "Character 15"]


async def test_a_record_that_cannot_be_written_strands_no_new_costume_folder(ctx, monkeypatch):
    await approved(ctx)
    before = record.read(ctx, "Character 8")

    def full(*args, **kwargs):
        raise OSError(28, "No space left on device")
    with monkeypatch.context() as m:
        m.setattr(variants, "write_json", full)
        answer = await made(ctx)
    assert answer == {"problem": "Could not write Character 8's sheet: No space left on device"}
    assert not (home(ctx) / "Leather jacket").exists() and record.read(ctx, "Character 8") == before
    entry = await call(costume.post_approve, ctx, body={"name": "Character 8", "variant": "Leather jacket"})
    assert entry["orbit"] == "Leather jacket/orbit.mp4", "approved again, not refused as a folder not the character's"
    with monkeypatch.context() as m:                               # an approved costume's folder stays
        m.setattr(variants, "write_json", full)
        assert "problem" in await call(costume.post_approve, ctx, body={"name": "Character 8",
                                                                        "variant": "Leather jacket"})
    assert (home(ctx) / "Leather jacket" / "orbit.mp4").is_file()
    assert record.read(ctx, "Character 8")["variants"]["Leather jacket"] == entry
