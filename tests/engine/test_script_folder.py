"""The scripts folder (`hub/modules/director/scripts.py`) and the Scripts tab's routes: no file given at start, the
listing by name, a file that does not read listed with its problem and still renamed and deleted, nothing under
`scripts/` a media item, and every route a paired screen's only. A version-1 file already there is left as it is; `one`
answers each member's picture; a script naming someone not in Characters reads and `one` names them in `unpictured`."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from hub.core.api import Invalid
from hub.core.files import Files
from hub.core.registry import discover, validate
from hub.modules.director import drawing, manifest, mix, render, routes, scripts, tools, track
from hub.modules.media import manifest as media
from tests.core.harness import own_modules, start_hub
from tests.engine.helpers import FakeCtx, FakeEngine
from tests.engine.test_media_characters import png_bytes
from tests.engine.test_script_shape import FIXTURE

SHIPPED = json.loads(FIXTURE.read_text(encoding="utf-8"))
CHARS = {"character 1": "chars/Character 1.png", "character 2": "chars/Character 2.png"}  # {folded name -> picture}
PICTURES = {"Character 1": "chars/Character 1.png", "Character 2": "chars/Character 2.png"}


@pytest.fixture
def folder(tmp_path: Path) -> Path:
    return Files(tmp_path / "data").roots["scripts"]


def refused(fn, *args) -> str:  # type: ignore[no-untyped-def]
    with pytest.raises(Invalid) as e:
        fn(*args)
    return e.value.text


def no_times(listing: list[dict]) -> list[dict]:
    return [{k: v for k, v in x.items() if k != "changed"} for x in listing]


def test_the_folder_is_the_hubs_own_and_holds_no_media(tmp_path: Path, folder: Path) -> None:
    files = Files(tmp_path / "data")
    assert folder == tmp_path / "data" / "scripts" and folder.is_dir()
    for ident in ("scripts/Example.json", "scripts/a.png", "scripts/a.mp4", "scripts/a.wav"):
        assert files.kind(ident) is None
    (folder / ".Example.json.abcd1234.tmp").write_text("{")
    Files(tmp_path / "data")
    assert not (folder / ".Example.json.abcd1234.tmp").exists(), "a torn temp file is erased at start"


async def test_the_hub_gives_no_file_at_start(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The director's start writes nothing into the scripts folder; an old file there is never rewritten."""
    async def no_loop(_ctx: object) -> None:
        return None

    monkeypatch.setattr(drawing, "start", no_loop)
    ctx = FakeCtx("director", tmp_path / "data", FakeEngine(None))
    ctx.files = Files(tmp_path / "data")
    await routes.start(ctx)
    assert list(routes.folder(ctx).iterdir()) == [], "nothing given"
    old = json.dumps({"version": 1, "scenes": SHIPPED["scenes"]}, indent=1).encode()
    (routes.folder(ctx) / "Example.json").write_bytes(old)
    await routes.start(ctx)
    assert scripts.one(routes.folder(ctx), "Example", {})["pictures"] == {}, "version 1: no context, no picture needed"
    assert scripts.listing(routes.folder(ctx), {})[0]["problem"] is None
    assert (routes.folder(ctx) / "Example.json").read_bytes() == old, "never rewritten"


def test_listing_one_rename_delete(tmp_path: Path, folder: Path) -> None:
    (folder / "Example.json").write_text(json.dumps(SHIPPED))
    (folder / "b-roll.json").write_text("{\n  \"version\": 1,\n")
    (folder / "Big.json").write_bytes(b" " * (scripts.MAX_BYTES + 1))
    (folder / "notes.txt").write_text("x")
    empty = {"seconds": 0, "scenes": 0, "shots": 0, "lines": 0}
    assert no_times(scripts.listing(folder, CHARS)) == [
        {"name": "b-roll", **empty, "problem": "The file is not JSON (line 3)"},
        {"name": "Big", **empty, "problem": "The file is over 1 MB"},
        {"name": "Example", "seconds": 24.0, "scenes": 1, "shots": 3, "lines": 3, "problem": None}]
    assert scripts.one(folder, " Example ", CHARS) == {"name": "Example", "seconds": 24.0, "problem": None,
                                                       "script": SHIPPED, "pictures": PICTURES, "unpictured": []}
    assert scripts.one(folder, "b-roll", CHARS) == {"name": "b-roll", "seconds": 0, "problem": "The file is not "
                                                    "JSON (line 3)", "script": None, "pictures": {},
                                                    "unpictured": []}
    assert refused(scripts.one, folder, "Nope", CHARS) == "There is no script named Nope"
    assert refused(scripts.one, folder, None, CHARS) == "Name the script"
    assert refused(scripts.one, folder, "a/b", CHARS) == "Use a plain script name, without slashes"
    assert scripts.rename(folder, "b-roll", "Broken") == {"name": "Broken"}, "a file that does not read is renamed"
    assert refused(scripts.rename, folder, "Broken", "Example") == "A script named Example already exists"
    assert scripts.rename(folder, "Example", "Script 2") == {"name": "Script 2"}
    assert json.loads((folder / "Script 2.json").read_text()) == SHIPPED
    scripts.delete(folder, "Broken")
    scripts.delete(folder, "Big")
    assert refused(scripts.delete, folder, "Broken") == "There is no script named Broken"
    assert [x["name"] for x in scripts.listing(folder, CHARS)] == ["Script 2"]


def test_a_file_that_reads_but_breaks_the_format_says_where(folder: Path) -> None:
    bad = json.loads(json.dumps(SHIPPED))
    bad["scenes"][0]["shots"][1]["events"][0]["speaker"] = "Character 3"
    (folder / "Bad.json").write_text(json.dumps(bad))
    assert scripts.listing(folder, CHARS)[0]["problem"] == \
        "Scene 1, shot 2, event l2: the speaker Character 3 is not in the scene's cast"


def test_a_name_not_in_characters_reads_and_is_named_and_renamed_and_deleted(folder: Path) -> None:
    """The script reads; `one` answers the members without a picture in `unpictured`."""
    (folder / "Script 1.json").write_text(json.dumps(SHIPPED))
    first_only = {"character 1": "chars/Character 1.png"}
    assert scripts.listing(folder, first_only)[0]["problem"] is None
    assert scripts.one(folder, "Script 1", first_only) == {"name": "Script 1", "seconds": 24.0, "problem": None,
                                                       "script": SHIPPED,
                                                     "pictures": {"Character 1": PICTURES["Character 1"]},
                                                       "unpictured": ["Character 2"]}
    assert scripts.listing(folder, {})[0]["problem"] is None
    assert scripts.one(folder, "Script 1", {})["unpictured"] == ["Character 1", "Character 2"]
    assert scripts.rename(folder, "Script 1", "Old script") == {"name": "Old script"}
    scripts.delete(folder, "Old script")
    assert scripts.listing(folder, first_only) == []


def test_the_declarations() -> None:
    validate([manifest.MODULE])
    mods, errors = discover()
    assert "director" in {m.id for m in mods} and errors == [], "on by default"
    m = manifest.MODULE
    assert (m.id, m.title, m.tab.label, m.tab.order) == ("director", "Storyboard", "Storyboard", 30)
    assert (m.screen, m.sockets, m.card, m.listings) == (None, (), None, ())
    assert dict(m.jobs) == {"panel": drawing.job, "track": track.job, "mix": mix.job, "render": render.job}, \
        "Track's job; the mix's; Render's"
    assert dict(m.listens) == {"job.finished": manifest.on_finished, "sketch.ready": drawing.on_ready}, \
        "the sketch panels' job kind and its finish; Generate's ready; Track's"
    assert m.actions == (*tools.ACTIONS, track.ACTION, mix.ACTION, render.ACTION) and m.lanes == ("changed",), \
        "the script tools, then Track's, the mix's and Render's actions"
    assert m.start is routes.start
    assert [(r.method, r.path, r.auth) for r in m.routes] == [
        ("GET", "/scripts", "screen"), ("GET", "/script", "screen"), ("POST", "/rename", "screen"),
        ("POST", "/delete", "screen"), ("POST", "/track", "screen"),
        ("POST", "/render", "screen"), ("GET", "/video-loras", "screen"), ("GET", "/shot-pictures", "screen"),
        ("POST", "/shot-pictures", "screen"), ("POST", "/video-loras", "screen"),
        ("POST", "/edit", "screen")]                                                   # Render, Video LoRA, the edits


async def test_the_routes(tmp_path: Path) -> None:
    cast = tmp_path / "Characters"
    cast.mkdir()
    for name in ("Character 1", "Character 2"):
        (cast / f"{name}.png").write_bytes(png_bytes())
    (Files(tmp_path / "data").roots["scripts"] / "Example.json").write_text(json.dumps(SHIPPED))
    hub = await start_hub(tmp_path / "data", modules=[*own_modules(), media.MODULE, manifest.MODULE],
                          settings={"paths": {"characters": str(cast)}})
    try:
        cookie = hub.pair()
        assert (await hub.http("GET", "/api/director/scripts")).status in (401, 403), "a paired screen only"
        assert (await hub.http("POST", "/api/director/delete", json_body={"name": "Example"})).status in (401, 403)
        listed = (await hub.http("GET", "/api/director/scripts", cookie)).json()
        assert no_times(listed["scripts"]) == [{"name": "Example", "seconds": 24.0, "scenes": 1, "shots": 3,
                                                "lines": 3, "problem": None}]
        one = (await hub.http("GET", "/api/director/script?name=Example", cookie)).json()
        assert [r["kind"] for r in one.pop("audio")].count("line") == 3, "a written script's rows"
        assert one == {"name": "Example", "seconds": 24.0, "problem": None, "script": SHIPPED, "pictures": PICTURES,
                       "unpictured": [], "track": None, "rendering": None,
                       "rendering_cut": None, "cut": None, "cut_url": None}       # Render and the cut
        (cast / "Character 2.png").unlink()
        listed = (await hub.http("GET", "/api/director/scripts", cookie)).json()
        assert listed["scripts"][0]["problem"] is None, "it reads"
        one = (await hub.http("GET", "/api/director/script?name=Example", cookie)).json()
        assert (one["pictures"], one["unpictured"]) == ({"Character 1": PICTURES["Character 1"]}, ["Character 2"])
        (cast / "Character 2.png").write_bytes(png_bytes())
        assert (await hub.http("GET", "/files/scripts/Example.json", cookie)).status == 404, "not served"
        assert (await hub.http("GET", "/thumbs/scripts/Example.json/96", cookie)).status == 404, "not served"
        for root in ("out", "clips", "sounds"):
            items = (await hub.http("GET", f"/api/media?root={root}", cookie)).json()["items"]
            assert not any(i["id"].startswith("scripts/") for i in items), "not in Media"
        renamed = await hub.http("POST", "/api/director/rename", cookie,
                                 json_body={"name": "Example", "to": "Script 1"})
        assert renamed.json() == {"name": "Script 1"}
        taken = await hub.http("POST", "/api/director/rename", cookie, json_body={"name": "Script 1", "to": ""})
        assert (taken.status, taken.json()["text"]) == (400, "Name the script")
        gone = await hub.http("POST", "/api/director/delete", cookie, json_body={"name": "Script 1"})
        assert gone.status == 204
        assert (await hub.http("GET", "/api/director/scripts", cookie)).json() == {"scripts": []}
    finally:
        await hub.close()
    hub = await start_hub(tmp_path / "data", modules=[*own_modules(), media.MODULE, manifest.MODULE])
    try:
        listed = (await hub.http("GET", "/api/director/scripts", hub.pair())).json()
        assert listed == {"scripts": []}, "after a delete, Example does not come back on the next start"
    finally:
        await hub.close()
