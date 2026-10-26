"""Approve copies the six views, the orbit and the bits into `Characters/<Name>/` and writes
`casting.json` (no prompt, seed, chat or job). The sources stay where they were. An earlier sheet is replaced only on
the new one's Approve; a bit it had that the new one has not is erased; a bit that is a file of the sheet it replaces
is read before anything is written."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image

from hub.core.api import Invalid
from hub.core.files import Files
from hub.modules.casting import record, state
from tests.engine.helpers import FakeCtx, FakeEngine

DAY = "2026-10-20"


@pytest.fixture
def ctx(tmp_path: Path) -> FakeCtx:
    held = FakeCtx("casting", tmp_path / "data", FakeEngine(None))
    chars = tmp_path / "Characters"
    chars.mkdir()
    Image.new("RGB", (64, 64), "white").save(chars / "Character 8.png")
    held.files = Files(tmp_path / "data", None, chars)
    return held


def made(ctx, tone: int, n_bits: int = 2) -> dict:
    """A ready draft: six views of one grey, an orbit and `n_bits` bits in Temp."""
    out, clips = Path(ctx.files.roots["out"]) / DAY, Path(ctx.files.roots["clips"]) / DAY
    out.mkdir(parents=True, exist_ok=True)
    clips.mkdir(parents=True, exist_ok=True)
    views = {}
    for i, view in enumerate(record.SHEET):
        Image.new("RGB", (70, 124), (tone, tone, tone)).save(out / f"v{tone}-{i}.png")
        views[view] = f"out/{DAY}/v{tone}-{i}.png"
    (clips / f"o{tone}.mp4").write_bytes(bytes([tone]) * 64)
    bits = []
    for i in range(n_bits):
        Image.new("RGB", (40, 40), (tone, 0, 0)).save(out / f"b{tone}-{i}.jpg")
        bits.append({"id": f"out/{DAY}/b{tone}-{i}.jpg", "keep": f"keep {i}", "ignore": f"ignore {i}"})
    draft = state.fresh("Character 8", "chars/Character 8.png")
    draft.update(state="ready", orbit=f"clips/{DAY}/o{tone}.mp4", views=views, bits=bits, seed=12345, job="j_1",
                 model="MiniMax H3 Ref2VA Pruned 20B", facts={"age": "50", "build": "heavy"})
    return draft


def home(ctx) -> Path:
    return Path(ctx.files.roots["chars"]) / "Character 8"


def tone(path: Path) -> int:
    with Image.open(path) as im:
        return im.convert("RGB").getpixel((0, 0))[0]


def test_approve_writes_the_sheet_the_orbit_the_bits_and_the_record(ctx):
    draft = made(ctx, 10)
    written = record.approve(ctx, draft)
    folder = home(ctx)
    assert sorted(p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_file()) == sorted(
        ["bits/2.jpg", "bits/3.jpg", "casting.json", "orbit.mp4",
         *(f"sheet/{v}.png" for v in ("front", "left", "back", "right", "face-1", "face-2"))])
    assert json.loads((folder / "casting.json").read_text(encoding="utf-8")) == written
    approved = written.pop("approved")
    assert approved[:4].isdigit() and "T" in approved
    assert written == {
        "version": 1, "name": "Character 8", "role": "cast", "facts": {"age": "50", "build": "heavy"},
        "headshot": {"keep": draft["headshot"]["keep"], "ignore": ""},
        "bits": [{"file": "bits/2.jpg", "keep": "keep 0", "ignore": "ignore 0"},
                 {"file": "bits/3.jpg", "keep": "keep 1", "ignore": "ignore 1"}],
        "sheet": {"front": {"file": "sheet/front.png", "frame": 2}, "left": {"file": "sheet/left.png", "frame": 21},
                  "back": {"file": "sheet/back.png", "frame": 42}, "right": {"file": "sheet/right.png", "frame": 63},
                  "face-1": {"file": "sheet/face-1.png", "frame": 84},
                  "face-2": {"file": "sheet/face-2.png", "frame": 113}},
        "orbit": "orbit.mp4", "model": "MiniMax H3 Ref2VA Pruned 20B"}
    text = (folder / "casting.json").read_text(encoding="utf-8")
    assert "12345" not in text and "prompt" not in text and "seed" not in text and "j_1" not in text
    assert (folder / "orbit.mp4").read_bytes() == bytes([10]) * 64 and tone(folder / "sheet" / "back.png") == 10
    assert all(ctx.files.existing_media(v) for v in draft["views"].values()), "copied, never moved"
    assert record.cast(ctx, "Character 8") and not record.cast(ctx, "Nobody")


def test_the_record_and_its_ids(ctx):
    record.approve(ctx, made(ctx, 10))
    found = record.read(ctx, "Character 8")
    assert found is not None and found["name"] == "Character 8"
    files = record.ids("Character 8", found)
    assert files["views"]["face-2"] == "chars/Character 8/sheet/face-2.png" and files["bits"] == [
        "chars/Character 8/bits/2.jpg", "chars/Character 8/bits/3.jpg"]
    assert all(ctx.files.existing_image(i) for i in files["views"].values()), "each view is a picture Media serves"
    assert record.read(ctx, "Nobody") is None


def test_an_earlier_sheet_is_replaced_only_on_approve(ctx):
    record.approve(ctx, made(ctx, 10, n_bits=2))
    later = made(ctx, 200, n_bits=1)
    assert tone(home(ctx) / "sheet" / "front.png") == 10, "a new sheet ready is not approved"
    record.approve(ctx, later)
    assert tone(home(ctx) / "sheet" / "front.png") == 200 and (home(ctx) / "orbit.mp4").read_bytes()[0] == 200
    assert sorted(p.name for p in (home(ctx) / "bits").iterdir()) == ["2.jpg"]


def test_bits_that_are_the_sheets_own_files_are_read_first(ctx):
    record.approve(ctx, made(ctx, 10, n_bits=2))
    again = state.fresh("Character 8", "chars/Character 8.png", record.read(ctx, "Character 8"))
    assert [b["id"] for b in again["bits"]] == ["chars/Character 8/bits/2.jpg", "chars/Character 8/bits/3.jpg"]
    ready = made(ctx, 90, n_bits=0)
    ready["bits"] = list(reversed(again["bits"]))           # box 2 now holds what was bit 3
    record.approve(ctx, ready)
    assert tone(home(ctx) / "bits" / "2.jpg") == 10 and (home(ctx) / "bits" / "3.jpg").is_file()
    assert json.loads((home(ctx) / "casting.json").read_text())["bits"][0]["keep"] == "keep 1"


def test_nothing_to_approve_and_a_lost_file_are_one_line(ctx):
    draft = made(ctx, 10)
    with pytest.raises(Invalid) as err:
        record.approve(ctx, {**draft, "state": "rendering"})
    assert err.value.text == record.NOT_READY
    Path(ctx.files.resolve(draft["views"]["left"])).unlink()
    with pytest.raises(Invalid) as err:
        record.approve(ctx, draft)
    assert err.value.text == record.LOST and not home(ctx).exists(), "nothing written"


def snapshot(folder: Path) -> dict[str, bytes]:
    return {p.relative_to(folder).as_posix(): p.read_bytes() for p in sorted(folder.rglob("*")) if p.is_file()}


def failing(monkeypatch, name: str, at: int) -> None:
    """`record.<shutil|os>.<name>`'s call number `at` (from 1) fails as a full disk."""
    target = record.shutil if name == "copyfile" else record.os
    real, calls = getattr(target, name), []

    def fake(*args, **kwargs):
        calls.append(args)
        if len(calls) == at:
            raise OSError(28, "No space left on device")
        return real(*args, **kwargs)
    monkeypatch.setattr(target, name, fake)


@pytest.mark.parametrize(("name", "at"), [*(("copyfile", k) for k in range(1, 10)), ("replace", 1)])
def test_a_write_failing_at_any_stage_leaves_the_earlier_sheet_whole(ctx, monkeypatch, name, at):
    """6 views, the orbit, 2 bits: a copy failing at each (a full disk), or the first move into place."""
    record.approve(ctx, made(ctx, 10, n_bits=3))
    before = snapshot(home(ctx))
    later = made(ctx, 200, n_bits=2)
    with monkeypatch.context() as m:
        failing(m, name, at)
        with pytest.raises(OSError):
            record.approve(ctx, later)
    assert snapshot(home(ctx)) == before, "the old sheet, bits and record whole; no temporary file left"


def test_a_failure_on_a_first_approve_leaves_no_folder(ctx, monkeypatch):
    failing(monkeypatch, "copyfile", 3)
    with pytest.raises(OSError):
        record.approve(ctx, made(ctx, 10))
    assert not home(ctx).exists()


def test_a_bit_that_is_no_picture_is_refused_and_nothing_is_kept(ctx):
    record.approve(ctx, made(ctx, 10))
    before = snapshot(home(ctx))
    later = made(ctx, 200, n_bits=1)
    Path(ctx.files.resolve(later["bits"][0]["id"])).write_bytes(b"not a picture")
    with pytest.raises((OSError, ValueError)):
        record.approve(ctx, later)
    assert snapshot(home(ctx)) == before


def test_a_bit_is_stripped_of_its_metadata(ctx):
    from PIL import PngImagePlugin
    draft = made(ctx, 10, n_bits=0)
    info = PngImagePlugin.PngInfo()
    info.add_text("Comment", "the secret")
    src = Path(ctx.files.roots["out"]) / DAY / "tagged.png"
    Image.new("RGB", (40, 40), (1, 2, 3)).save(src, pnginfo=info)
    draft["bits"] = [{"id": f"out/{DAY}/tagged.png", "keep": "", "ignore": ""}]
    record.approve(ctx, draft)
    kept = home(ctx) / "bits" / "2.png"
    assert b"the secret" not in kept.read_bytes() and b"the secret" in src.read_bytes(), "the source is untouched"
    assert tone(kept) == 1


def test_the_urls_carry_a_version_that_a_new_approve_changes(ctx):
    import os
    record.approve(ctx, made(ctx, 10))
    first = record.urls(ctx, "Character 8", record.read(ctx, "Character 8"))
    assert first["views"]["front"] == "chars/Character 8/sheet/front.png", "the ids stay bare"
    assert first["view_urls"]["front"].startswith("/files/chars/Character%208/sheet/front.png?v=")
    assert first["view_thumbs"]["front"].startswith("/thumbs/chars/Character%208/sheet/front.png/336?v=")
    assert first["bit_urls"][0].startswith("/files/chars/Character%208/bits/2.jpg?v=")
    assert first["orbit_url"].startswith("/api/casting/orbit?name=Character%208&v=")
    record.approve(ctx, made(ctx, 200))
    for p in home(ctx).rglob("*"):                       # the clock may not tick between the two approves here
        os.utime(p, ns=(p.stat().st_atime_ns, p.stat().st_mtime_ns + 1_000_000))
    second = record.urls(ctx, "Character 8", record.read(ctx, "Character 8"))
    assert second["view_urls"]["front"] != first["view_urls"]["front"] and second["orbit_url"] != first["orbit_url"]


def audience(ctx, tone: int, seat: dict | None = None) -> dict:
    """A ready extra's draft: the extra's four views, from `made`'s six."""
    draft = made(ctx, tone, n_bits=0)
    views = draft["views"]
    draft.update(role="audience", seat=seat or {"side": "left", "row": 3},
                 views={v: views[v] for v in record.AUDIENCE}, expect=list(record.AUDIENCE))
    return draft


def test_an_audience_approve_writes_four_views_the_role_and_seat_and_erases_the_earlier_back(ctx):
    record.approve(ctx, made(ctx, 10, n_bits=0))
    assert (home(ctx) / "sheet" / "back.png").is_file() and (home(ctx) / "sheet" / "face-2.png").is_file()
    written = record.approve(ctx, audience(ctx, 60))
    assert sorted(p.name for p in (home(ctx) / "sheet").iterdir()) == ["face-1.png", "front.png", "left.png",
                                                                       "right.png"]
    assert (written["role"], written["seat"]) == ("audience", {"side": "left", "row": 3})
    assert written["sheet"] == {"front": {"file": "sheet/front.png", "frame": 2},
                                "left": {"file": "sheet/left.png", "frame": 21},
                                "right": {"file": "sheet/right.png", "frame": 63},
                                "face-1": {"file": "sheet/face-1.png", "frame": 84}}
    assert tone(home(ctx) / "sheet" / "front.png") == 60 and "variants" not in written
    assert set(record.ids("Character 8", written)["views"]) == set(record.AUDIENCE), "the extra's views only"
    back = record.approve(ctx, made(ctx, 90, n_bits=0))
    assert "seat" not in back and back["role"] == "cast" and len(list((home(ctx) / "sheet").iterdir())) == 6


def test_an_audience_draft_without_the_four_views_is_not_ready(ctx):
    draft = audience(ctx, 60)
    with pytest.raises(Invalid) as err:
        record.approve(ctx, {**draft, "views": made(ctx, 61)["views"]})
    assert err.value.text == record.NOT_READY


def with_costume(ctx) -> dict:
    """The character's record as approved, with a costume entry beside it (as `variants.approve` writes it)."""
    record.approve(ctx, made(ctx, 10, n_bits=0))
    found = json.loads((home(ctx) / "casting.json").read_text(encoding="utf-8"))
    found["variants"] = {"Leather jacket": {"from": found["approved"], "orbit": "Leather jacket/orbit.mp4"}}
    (home(ctx) / "casting.json").write_text(json.dumps(found), encoding="utf-8")
    return found["variants"]


def test_the_characters_own_approve_after_a_costume_keeps_the_costumes(ctx):
    costumes = with_costume(ctx)
    written = record.approve(ctx, made(ctx, 200, n_bits=1))
    assert written["variants"] == costumes and record.read(ctx, "Character 8")["variants"] == costumes


def test_an_audience_approve_is_refused_while_the_character_has_costumes(ctx):
    with_costume(ctx)
    before = snapshot(home(ctx))
    with pytest.raises(Invalid) as err:
        record.approve(ctx, audience(ctx, 60))
    assert err.value.text == "Character 8 has costumes; remove them before casting as audience"
    assert snapshot(home(ctx)) == before


@pytest.mark.parametrize("seat", [{"side": "left", "row": 0}, {"side": "left", "row": 13}, {"side": "middle",
                                  "row": 1}, {"side": "left", "row": "3"}, {"side": "left", "row": True}, None])
def test_a_seat_out_of_range_is_one_line(seat):
    with pytest.raises(Invalid) as err:
        record.seat_of(seat)
    assert err.value.text == "A seat is a side (left, centre or right) and a row from 1 to 12"
    assert record.seat_of({"side": "right", "row": 12}) == {"side": "right", "row": 12}
