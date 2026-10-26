"""Media's Characters section over HTTP: the folder's pictures with their names, a picture put in under a name
(replacing the one that had it), a character renamed and deleted from its tree menu, or through the plain delete."""
from __future__ import annotations

import io
from pathlib import Path

from PIL import Image

from hub.modules.media.manifest import MODULE
from hub.settings import load
from tests.core.harness import start_hub


def png_bytes(w: int = 16, h: int = 12, color: tuple[int, int, int] = (200, 10, 10)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), color).save(buf, "PNG")
    return buf.getvalue()


async def test_no_characters_folder_is_unset_and_a_put_is_refused(tmp_path: Path) -> None:
    hub = await start_hub(tmp_path / "data", modules=[MODULE])
    try:
        c = hub.pair()
        (hub.data / "outputs" / "d").mkdir(parents=True)
        (hub.data / "outputs" / "d" / "a.png").write_bytes(png_bytes())
        r = await hub.http("GET", "/api/media/characters", cookie=c)
        assert r.status == 200 and r.json() == {"unset": True, "items": []}
        r = await hub.http("POST", "/api/media/characters", cookie=c, json_body={"name": "Character 17",
                                                                                 "id": "out/d/a.png"})
        assert r.status == 400 and r.json()["text"] == "Choose the Characters folder in Settings → Storage"
    finally:
        await hub.close()


async def test_characters_are_listed_put_replaced_and_deleted(tmp_path: Path) -> None:
    cast = tmp_path / "Characters"
    cast.mkdir()
    (cast / "Character 17.png").write_bytes(png_bytes(30, 20))
    (cast / "notes.txt").write_text("x")
    hub = await start_hub(tmp_path / "data", modules=[MODULE], settings={"paths": {"characters": str(cast)}})
    try:
        c = hub.pair()
        m = await hub.screen(c, "media", "m")
        out = hub.data / "outputs" / "2026-10-12"
        out.mkdir(parents=True)
        (out / "c21.png").write_bytes(png_bytes(40, 10, (1, 2, 3)))
        listed = (await hub.http("GET", "/api/media/characters", cookie=c)).json()
        assert listed["unset"] is False and [(i["name"], i["id"], i["w"], i["h"]) for i in listed["items"]] == [
            ("Character 17", "chars/Character 17.png", 30, 20)]
        assert listed["items"][0]["thumb"].startswith("/thumbs/chars/Character%2017.png/")
        assert (await hub.http("GET", "/files/chars/Character%2017.png", cookie=c)).status == 200

        r = await hub.http("POST", "/api/media/characters", cookie=c,
                           json_body={"name": "Character 21", "id": "out/2026-10-12/c21.png"})
        assert r.status == 200 and r.json() == {"id": "chars/Character 21.png"}
        assert (await m.recv("media.changed", timeout=2))["d"] == {"what": "characters"}
        assert (out / "c21.png").is_file(), "a copy: the Temp picture stays"
        names = [i["name"] for i in (await hub.http("GET", "/api/media/characters", cookie=c)).json()["items"]]
        assert names == ["Character 17", "Character 21"]

        r = await hub.http("POST", "/api/media/characters", cookie=c,
                           json_body={"name": "character 17", "id": "chars/Character 21.png"})
        assert r.status == 200 and r.json() == {"id": "chars/character 17.png"}
        items = (await hub.http("GET", "/api/media/characters", cookie=c)).json()["items"]
        assert [(i["name"], i["w"]) for i in items] == [("character 17", 40), ("Character 21",
                                                                               40)], "Character 17's picture replaced"
        assert sorted(p.name for p in cast.iterdir()) == ["Character 21.png", "character 17.png", "notes.txt"]

        for body in ({"name": "a/b", "id": "out/2026-10-12/c21.png"},
                     {"name": "X", "id": "in/x.png"}, {"name": "X", "id": "out/2026-10-12/gone.png"}):
            assert (await hub.http("POST", "/api/media/characters", cookie=c, json_body=body)).status == 400, body

        r = await hub.http("POST", "/api/media/delete", cookie=c, json_body={"ids": ["chars/character 17.png"]})
        assert r.status == 200 and r.json() == {"ids": ["chars/character 17.png"]}
        assert not (cast / "character 17.png").exists()
        items = (await hub.http("GET", "/api/media/characters", cookie=c)).json()["items"]
        assert [i["name"] for i in items] == ["Character 21"]
    finally:
        await hub.close()


async def test_the_characters_folder_is_chosen_and_cleared_live(tmp_path: Path) -> None:
    """Settings → Storage: the folder set through PATCH /api/settings (Core.update_settings) re-roots `chars` at
    once, is reported, saved, refused inside the Hub's data folder, and "" sets it back to none."""
    cast = tmp_path / "Characters"
    cast.mkdir()
    (cast / "Character 17.png").write_bytes(png_bytes())
    data = tmp_path / "data"
    hub = await start_hub(data, modules=[MODULE])
    try:
        c = hub.pair()
        assert "chars" not in hub.core.files.roots and hub.core.settings_view()["characters"] == ""
        r = await hub.http("PATCH", "/api/settings", c, json_body={"paths": {"characters": str(data / "outputs")}})
        assert r.status == 400 and r.json()["field"] == "paths.characters"
        assert "chars" not in hub.core.files.roots
        r = await hub.http("PATCH", "/api/settings", c, json_body={"paths": {"characters": str(cast)}})
        assert r.status == 200 and r.json()["characters"] == str(cast)
        assert hub.core.files.roots["chars"] == cast and "drive" not in hub.core.files.roots
        assert load(data)["paths"] == {"drive": "", "characters": str(cast)}
        listed = (await hub.http("GET", "/api/media/characters", c)).json()
        assert [i["name"] for i in listed["items"]] == ["Character 17"]
        r = await hub.http("PATCH", "/api/settings", c, json_body={"paths": {"characters": ""}})
        assert r.status == 200 and r.json()["characters"] == ""
        assert "chars" not in hub.core.files.roots and load(data)["paths"]["characters"] == ""
        assert (await hub.http("GET", "/api/media/characters", c)).json() == {"unset": True, "items": []}
        assert (await hub.http("GET", "/files/chars/Character%2017.png", c)).status == 404
        assert (cast / "Character 17.png").is_file(), "nothing is moved or erased"
    finally:
        await hub.close()


def test_characters_ids_are_media_ids() -> None:
    from hub.modules.media import library
    assert library.is_media("chars/Character 17.png") and library.is_media("drive/a/b.png")
    assert not library.is_media("in/x.png") and not library.is_media(None) and not library.is_media(3)


async def test_routes_over_the_fake_ctx_put_a_drive_picture_and_list_it(tmp_path: Path) -> None:
    """The routes alone, over the engine tests' fake ctx with a Characters folder: a Drive picture is put in under a
    name (a copy), the listing names it, `changed` is published once; no folder chosen is `unset`."""
    from hub.modules.media import routes
    from tests.engine.helpers import FakeCtx, FakeEngine, FakeRequest
    cast = tmp_path / "Characters"
    cast.mkdir()
    ctx = FakeCtx("media", tmp_path / "data", FakeEngine(None))
    assert await routes.characters_list(ctx, FakeRequest()) == {"unset": True, "items": []}
    ctx.files = type(ctx.files)(tmp_path / "data", cast)
    (tmp_path / "data" / "Drive").mkdir(parents=True)
    (tmp_path / "data" / "Drive" / "hero.png").write_bytes(png_bytes(20, 10))
    assert await routes.characters_list(ctx, FakeRequest()) == {"unset": False, "items": []}
    body = b'{"name": "Hero", "id": "drive/hero.png"}'
    assert await routes.character_put(ctx, FakeRequest(body=body)) == {"id": "chars/Hero.png"}
    assert (tmp_path / "data" / "Drive" / "hero.png").is_file() and (cast / "Hero.png").is_file()
    assert [x[1:] for x in ctx.bus.sent] == [("changed", {"what": "characters"})]
    items = (await routes.characters_list(ctx, FakeRequest()))["items"]
    assert [(i["name"], i["id"], i["w"], i["h"]) for i in items] == [("Hero", "chars/Hero.png", 20, 10)]


async def test_a_character_is_renamed_and_deleted_over_http(tmp_path: Path) -> None:
    cast = tmp_path / "Characters"
    cast.mkdir()
    (cast / "Character 17.png").write_bytes(png_bytes())
    (cast / "Character 18.png").write_bytes(png_bytes())
    hub = await start_hub(tmp_path / "data", modules=[MODULE], settings={"paths": {"characters": str(cast)}})
    try:
        c = hub.pair()
        m = await hub.screen(c, "media", "m")
        r = await hub.http("POST", "/api/media/characters/rename", cookie=c,
                           json_body={"id": "chars/Character 17.png", "name": "Character 20"})
        assert r.status == 200 and r.json() == {"id": "chars/Character 20.png"}
        assert (await m.recv("media.changed", timeout=2))["d"] == {"what": "characters"}
        assert sorted(p.name for p in cast.iterdir()) == ["Character 18.png", "Character 20.png"]
        r = await hub.http("POST", "/api/media/characters/rename", cookie=c,
                           json_body={"id": "chars/Character 18.png", "name": "character 20"})
        assert r.status == 400 and r.json()["text"] == "A character is already called character 20"
        r = await hub.http("POST", "/api/media/characters/remove", cookie=c, json_body={"id": "chars/Character 20.png"})
        assert r.status == 200 and r.json() == {"name": "Character 20"}
        assert sorted(p.name for p in cast.iterdir()) == ["Character 18.png"]
        for path, body in (("rename", {"id": "out/x.png", "name": "X"}), ("remove", {"id": "chars/Gone.png"}),
                           ("remove", {"id": "chars/../Character 18.png"})):
            assert (await hub.http("POST", f"/api/media/characters/{path}", cookie=c, json_body=body)).status == 400
        assert sorted(p.name for p in cast.iterdir()) == ["Character 18.png"]
    finally:
        await hub.close()


async def test_notes_are_saved_in_the_file_over_http(tmp_path: Path) -> None:
    cast = tmp_path / "Characters"
    cast.mkdir()
    Image.new("RGB", (8, 8)).save(cast / "Character 19.jpg", "JPEG")
    hub = await start_hub(tmp_path / "data", modules=[MODULE], settings={"paths": {"characters": str(cast)}})
    try:
        c = hub.pair()
        m = await hub.screen(c, "media", "m")
        r = await hub.http("POST", "/api/media/characters/notes", cookie=c,
                           json_body={"id": "chars/Character 19.jpg", "notes": "Place 1; a barrel at the neck."})
        assert r.status == 200 and r.json() == {"id": "chars/Character 19.png"}
        assert (await m.recv("media.changed", timeout=2))["d"] == {"what": "characters"}
        assert sorted(p.name for p in cast.iterdir()) == ["Character 19.png"]
        items = (await hub.http("GET", "/api/media/characters", cookie=c)).json()["items"]
        assert [(i["name"], i["notes"]) for i in items] == [("Character 19", "Place 1; a barrel at the neck.")]
        for body in ({"id": "chars/Character 19.png", "notes": 7}, {"id": "out/x.png", "notes": "x"}):
            assert (await hub.http("POST", "/api/media/characters/notes", cookie=c, json_body=body)).status == 400
        long = {"id": "chars/Character 19.png", "notes": "x" * 1001}               # saved whole
        assert (await hub.http("POST", "/api/media/characters/notes", cookie=c, json_body=long)).status == 200
        items = (await hub.http("GET", "/api/media/characters", cookie=c)).json()["items"]
        assert [i["notes"] for i in items] == ["x" * 1001]
    finally:
        await hub.close()
