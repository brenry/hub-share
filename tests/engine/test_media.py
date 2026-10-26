"""Media: the Temp page (plain files, only size read), paging, delete delegation."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from PIL import Image

from hub.core.api import Invalid
from hub.modules.media import library, routes
from tests.engine.helpers import FakeCtx, FakeEngine, FakeRequest, load_catalog


def save_png(path: Path, size=(64, 48)) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, (10, 20, 30)).save(path, "PNG")
    return path


@pytest.fixture
def media(tmp_path):
    ctx = FakeCtx("media", tmp_path / "data", FakeEngine(load_catalog("catalog_upstream.json")))
    out = tmp_path / "data" / "outputs"
    for day, names in (("2026-10-08", ["090000-001_a.png", "235959-999_b.png"]),
                       ("2026-10-09", ["080000-000_c.png", "080000-500_d.png", "120000-000_e.png"])):
        for name in names:
            save_png(out / day / name)
    (out / "2026-10-09" / ".hidden.png").write_bytes(b"x")
    (out / "2026-10-09" / "notes.txt").write_text("x")
    os.symlink(tmp_path / "elsewhere.png", out / "2026-10-09" / "999999-999_link.png")
    save_png(tmp_path / "elsewhere.png")
    return ctx


async def test_paging_newest_first(media):
    first = await routes.list_media(media, FakeRequest({"limit": "2"}))
    assert [i["id"] for i in first["items"]] == ["out/2026-10-09/120000-000_e.png", "out/2026-10-09/080000-500_d.png"]
    assert first["more"] is True
    item = first["items"][0]
    assert item["url"] == "/files/out/2026-10-09/120000-000_e.png" and item["kind"] == "image"
    assert item["thumb"].startswith("/thumbs/out/2026-10-09/120000-000_e.png/336?v=")
    assert (item["w"], item["h"]) == (64, 48) and item["createdAt"] > 0 and "meta" not in item
    rest = await routes.list_media(media, FakeRequest({"before": first["items"][-1]["id"], "limit": "10"}))
    assert [i["id"] for i in rest["items"]] == ["out/2026-10-09/080000-000_c.png", "out/2026-10-08/235959-999_b.png",
                                                "out/2026-10-08/090000-001_a.png"]
    assert rest["more"] is False, "hidden files, other types and links leaving the library are skipped"
    with pytest.raises(Invalid):
        await routes.list_media(media, FakeRequest({"limit": "0"}))


async def test_list_works_without_the_engine(media):
    media.engine = FakeEngine(None)
    page = await routes.list_media(media, FakeRequest({"limit": "1"}))
    assert len(page["items"]) == 1


async def test_delete_goes_through_core_files(media):
    ids = ["out/2026-10-09/120000-000_e.png"]
    assert await routes.delete(media, FakeRequest(body=json.dumps({"ids": ids}).encode())) == {"ids": ids}
    assert media.files.deleted == [ids]
    for body in (b"{}", b"nope", json.dumps({"ids": ["in/abc.png"]}).encode(),
                 json.dumps({"ids": ["out/../settings.json"]}).encode(), json.dumps({"ids": []}).encode()):
        with pytest.raises(Invalid):
            await routes.delete(media, FakeRequest(body=body))
    many = [f"out/2026-10-09/120000-{k:03d}_e.png" for k in range(501)]              # no most ids
    assert await routes.delete(media, FakeRequest(body=json.dumps({"ids": many}).encode())) == {"ids": many}


def test_ids_are_checked():
    assert library.rel_of("out/2026-10-09/a.png") == "2026-10-09/a.png"
    for bad in ("in/a.png", "out/../a.png", "out//a.png", "out/a.txt", "out/.a.png", "out/a\\b.png", 5, "out/a\0.png"):
        assert library.rel_of(bad) is None


def test_thumb_cache_key_changes_with_the_file(media, tmp_path):
    item = "out/2026-10-08/090000-001_a.png"
    first = library.describe(media, item)
    path = tmp_path / "data" / "outputs" / "2026-10-08" / "090000-001_a.png"
    Image.new("RGB", (8, 8)).save(path, "PNG")
    os.utime(path, ns=(1, 1))
    again = library.describe(media, item)
    assert first["thumb"] != again["thumb"] and (again["w"], again["h"]) == (8, 8)
    assert set(again) == {"id", "kind", "url", "thumb", "w", "h", "createdAt", "group", "fav"}, "the picture is all"
    assert library.describe(media, "out/missing.png") is None


async def test_a_favorite_is_a_file_in_the_favorites_folder(media, tmp_path):
    ids = ["out/2026-10-09/120000-000_e.png", "out/2026-10-08/090000-001_a.png"]
    out = await routes.favorite(media, FakeRequest(body=json.dumps({"ids": ids, "on": True}).encode()))
    assert [m["to"] for m in out["moved"]] == ["out/2026-10-09/Favorites/120000-000_e.png",
                                               "out/2026-10-08/Favorites/090000-001_a.png"]
    assert (tmp_path / "data" / "outputs" / "2026-10-09" / "Favorites" / "120000-000_e.png").is_file()
    assert media.bus.sent[-1] == ("changed", "changed", {"what": "favorites"})
    page = await routes.list_media(media, FakeRequest({"limit": "10"}))
    assert [i["id"] for i in page["items"]] == ["out/2026-10-09/Favorites/120000-000_e.png",
                                                "out/2026-10-09/080000-500_d.png", "out/2026-10-09/080000-000_c.png",
                                                "out/2026-10-08/Favorites/090000-001_a.png",
                                                "out/2026-10-08/235959-999_b.png"], "one stream, every group"
    assert page["groups"] == [{"name": "Favorites", "count": 2}] and page["total"] == 5
    favs = [i for i in page["items"] if i["fav"]]
    assert [i["id"] for i in favs] == [m["to"] for m in out["moved"]] and all(i["group"] == "Favorites" for i in favs)
    back = await routes.favorite(media, FakeRequest(body=json.dumps({"ids": [favs[0]["id"]], "on": False})
                                                  .encode()))
    assert back["moved"] == [{"from": "out/2026-10-09/Favorites/120000-000_e.png",
                              "to": "out/2026-10-09/120000-000_e.png"}]
    assert not list(tmp_path.rglob("favorites.json")), "no list of favorites anywhere: the folder is the list"
    for body in ({"ids": ["drive/x/a.png"]}, {"ids": ids, "on": "yes"}):
        with pytest.raises(Invalid):
            await routes.favorite(media, FakeRequest(body=json.dumps(body).encode()))


async def test_the_sounds_page_lists_wavs_newest_first(media, tmp_path):
    """Sounds: their own root and page, a flat list newest first, each with its length and no
    thumbnail; a sound is no picture for favorites, the Drive or Characters."""
    from hub.core.files import Files
    from tests.fakes.wav import tiny_wav
    media.files = Files(tmp_path / "data")
    for name, seconds in (("2026-10-16/090000-000.wav", 2), ("2026-10-17/120000-000.wav", 4.5)):
        path = media.files.roots["sounds"] / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(tiny_wav(seconds))
    (media.files.roots["sounds"] / "2026-10-17" / "stray.png").write_bytes(b"x")
    page = await routes.list_media(media, FakeRequest({"root": "sounds", "limit": "10"}))
    assert [(i["id"], i["kind"], i["seconds"], i["thumb"]) for i in page["items"]] == [
        ("sounds/2026-10-17/120000-000.wav", "sound", 4.5, None), ("sounds/2026-10-16/090000-000.wav", "sound", 2.0,
                                                                    None)]
    assert page["total"] == 2 and page["items"][0]["url"].startswith("/files/sounds/2026-10-17/120000-000.wav")
    body = json.dumps({"ids": ["sounds/2026-10-17/120000-000.wav"], "on": True}).encode()
    with pytest.raises(Invalid, match="pictures"):
        await routes.favorite(media, FakeRequest(body=body))
