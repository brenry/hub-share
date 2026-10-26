"""Media routes over HTTP: Temp groups, Favorites, the Drive's folders, move in, purge delete."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from hub.modules.media.manifest import MODULE
from tests.core.harness import Hub, start_hub
from tests.core.test_files import png_bytes


@pytest.fixture
async def hub(tmp_path: Path):  # type: ignore[no-untyped-def]
    (tmp_path / "Drive").mkdir()
    h = await start_hub(tmp_path / "data", modules=[MODULE], settings={"paths": {"drive": str(tmp_path / "Drive")}})
    out = h.data / "outputs" / "2026-10-09"
    for rel in ("a.png", "b.png", "Group 1/c.png", "Group 1/d.png", "Group 2/e.png"):
        (out / rel).parent.mkdir(parents=True, exist_ok=True)
        (out / rel).write_bytes(png_bytes())
    (tmp_path / "Drive" / "portraits").mkdir()
    (tmp_path / "Drive" / "portraits" / "p.png").write_bytes(png_bytes())
    yield h
    await h.close()


async def test_temp_lists_its_groups(hub: Hub) -> None:
    c = hub.pair()
    r = await hub.http("GET", "/api/media?limit=10", cookie=c)
    assert r.status == 200
    page = r.json()
    assert page["total"] == 5
    assert page["groups"] == [{"name": "Favorites", "count": 0}, {"name": "Group 1", "count": 2},
                              {"name": "Group 2", "count": 1}]
    by_id = {i["id"]: i for i in page["items"]}
    assert by_id["out/2026-10-09/Group 1/c.png"]["group"] == "Group 1" and by_id["out/2026-10-09/a.png"]["group"] == ""
    assert all(i["fav"] is False for i in page["items"])


async def test_favorites_are_a_folder_not_a_list(hub: Hub) -> None:
    c = hub.pair()
    ids = ["out/2026-10-09/a.png", "out/2026-10-09/Group 1/c.png"]
    r = await hub.http("POST", "/api/media/favorite", cookie=c, json_body={"ids": ids, "on": True})
    assert r.status == 200
    assert [m["to"] for m in r.json()["moved"]] == ["out/2026-10-09/Favorites/a.png", "out/2026-10-09/Favorites/c.png"]
    page = (await hub.http("GET", "/api/media?limit=10", cookie=c)).json()
    favs = [i for i in page["items"] if i["fav"]]
    assert sorted(i["id"] for i in favs) == sorted(m["to"] for m in r.json()["moved"])
    assert all(i["group"] == "Favorites" for i in favs)
    assert page["groups"] == [{"name": "Favorites", "count": 2}, {"name": "Group 1", "count": 1},
                              {"name": "Group 2", "count": 1}]
    off = await hub.http("POST", "/api/media/favorite", cookie=c,
                         json_body={"ids": ["out/2026-10-09/Favorites/a.png"], "on": False})
    assert off.status == 200 and off.json()["moved"] == [{"from": "out/2026-10-09/Favorites/a.png",
                                                            "to": "out/2026-10-09/a.png"}]
    page = (await hub.http("GET", "/api/media?limit=10", cookie=c)).json()
    assert [i["id"] for i in page["items"] if i["fav"]] == ["out/2026-10-09/Favorites/c.png"]
    assert not list((hub.data / "modules").rglob("*")), "no list of favorites, no copy: the folder is the record"
    assert (await hub.http("POST", "/api/media/favorite", cookie=c, json_body={"ids": ["in/x.png"]})).status == 400
    drive = {"ids": ["drive/portraits/p.png"], "on": True}
    assert (await hub.http("POST", "/api/media/favorite", cookie=c, json_body=drive)).status == 400
    assert (await hub.http("GET", "/api/media/favorites", cookie=c)).status == 404


async def test_drive_folders_over_http(hub: Hub) -> None:
    c = hub.pair()
    top = (await hub.http("GET", "/api/media/drive", cookie=c)).json()
    assert top == {"path": "", "name": "Drive", "dirs": ["portraits"], "items": [], "unset": False}
    inside = (await hub.http("GET", "/api/media/drive?path=portraits", cookie=c)).json()
    assert inside["dirs"] == [] and [i["id"] for i in inside["items"]] == ["drive/portraits/p.png"]
    assert inside["items"][0]["thumb"].startswith("/thumbs/drive/portraits/p.png/336?v=")
    assert (await hub.http("GET", "/thumbs/drive/portraits/p.png/96", cookie=c)).status == 200
    r = await hub.http("POST", "/api/media/drive/folder", cookie=c, json_body={"path": "", "name": "studies"})
    assert r.status == 200 and r.json() == {"path": "studies"}
    r = await hub.http("POST", "/api/media/drive/rename", cookie=c, json_body={"path": "studies", "name": "sketches"})
    assert r.status == 200 and r.json() == {"path": "sketches"}
    r = await hub.http("POST", "/api/media/drive/move", cookie=c, json_body={"paths": ["sketches"], "to": "portraits"})
    assert r.status == 200 and r.json() == {"paths": ["portraits/sketches"]}
    assert (await hub.http("GET", "/api/media/drive?path=portraits", cookie=c)).json()["dirs"] == ["sketches"]
    assert (await hub.http("GET", "/api/media/drive?path=../", cookie=c)).status == 400
    bad = await hub.http("POST", "/api/media/drive/folder", cookie=c, json_body={"path": "", "name": "a/b"})
    assert bad.status == 400


async def test_move_in_and_purge(hub: Hub) -> None:
    c = hub.pair()
    ids = ["out/2026-10-09/Group 1/c.png", "out/2026-10-09/a.png"]
    r = await hub.http("POST", "/api/media/move", cookie=c, json_body={"ids": ids, "to": "portraits"})
    assert r.status == 200
    assert r.json()["moved"] == [{"from": ids[0], "to": "drive/portraits/c.png"},
                                 {"from": ids[1], "to": "drive/portraits/a.png"}]
    assert not (hub.data / "outputs" / "2026-10-09" / "a.png").exists()
    page = (await hub.http("GET", "/api/media?limit=10", cookie=c)).json()
    assert page["total"] == 3 and page["groups"] == [{"name": "Favorites", "count": 0}, {"name": "Group 1", "count": 1},
                                                     {"name": "Group 2", "count": 1}]
    doomed = ["drive/portraits/c.png", "out/2026-10-09/b.png"]
    r = await hub.http("POST", "/api/media/delete", cookie=c, json_body={"ids": doomed})
    assert r.status == 200 and r.json() == {"ids": ["drive/portraits/c.png", "out/2026-10-09/b.png"]}
    assert not list(hub.data.rglob("c.png")) and not list(hub.data.rglob("b.png")), "gone for good, nowhere else"
    r = await hub.http("POST", "/api/media/drive/remove", cookie=c, json_body={"path": "portraits"})
    assert r.status == 200 and not (hub.data.parent / "Drive" / "portraits").exists()
    assert not list(hub.data.rglob("*.png")) or all("outputs" in str(p) for p in hub.data.rglob("*.png"))


async def test_favorite_folders_are_a_list_of_paths_and_nothing_moves(hub: Hub) -> None:
    """A Drive folder pinned under Favorites: the list is the record (a setting); no file or folder is
    moved, copied or linked; renames and moves through the Hub carry the entry along; an erased folder leaves it."""
    c = hub.pair()
    drive = hub.data.parent / "Drive"
    (drive / "portraits" / "group-1" / "studies").mkdir(parents=True)
    (drive / "portraits" / "group-1" / "m.png").write_bytes(png_bytes())
    assert (await hub.http("GET", "/api/media/favorite-folders", cookie=c)).json() == {"folders": []}
    before = sorted(p.relative_to(drive).as_posix() for p in drive.rglob("*"))

    async def pin(path: str, on: bool = True) -> Any:
        return await hub.http("POST", "/api/media/favorite-folders", cookie=c, json_body={"path": path, "on": on})
    r = await pin("/portraits/group-1/")
    assert r.status == 200 and r.json() == {"folders": [{"path": "portraits/group-1", "name": "group-1", "ok": True}]}
    r = await pin("portraits")
    assert [f["path"] for f in r.json()["folders"]] == ["portraits/group-1", "portraits"], "in the order added"
    again = await pin("portraits/group-1")
    assert [f["path"] for f in again.json()["folders"]] == ["portraits", "portraits/group-1"], "once, moved to the end"
    assert (await hub.http("GET", "/api/media/drive?path=portraits/group-1", cookie=c)).json()["dirs"] == ["studies"]
    assert sorted(p.relative_to(drive).as_posix() for p in drive.rglob("*")) == before, "nothing moved or copied"
    assert not any(p.is_symlink() for p in drive.rglob("*")) and not any(p.is_symlink() for p in hub.data.rglob("*"))
    for bad in ({"path": "", "on": True}, {"path": "nope", "on": True}, {"path": "../", "on": True},
                {"path": "portraits", "on": "yes"}, {"path": 3, "on": True}):
        assert (await hub.http("POST", "/api/media/favorite-folders", cookie=c, json_body=bad)).status == 400
    r = await hub.http("POST", "/api/media/drive/rename", cookie=c, json_body={"path": "portraits", "name": "faces"})
    assert r.status == 200
    listed = (await hub.http("GET", "/api/media/favorite-folders", cookie=c)).json()["folders"]
    assert [(f["path"], f["name"], f["ok"]) for f in listed] == [("faces", "faces", True), ("faces/group-1", "group-1",
                                                                                            True)]
    r = await hub.http("POST", "/api/media/drive/move", cookie=c, json_body={"paths": ["faces/group-1"], "to": ""})
    assert r.status == 200 and r.json() == {"paths": ["group-1"]}
    listed = (await hub.http("GET", "/api/media/favorite-folders", cookie=c)).json()["folders"]
    assert [f["path"] for f in listed] == ["faces", "group-1"]
    (drive / "group-1").rename(drive / "elsewhere")                # gone some other way: listed still, marked
    listed = (await hub.http("GET", "/api/media/favorite-folders", cookie=c)).json()["folders"]
    assert [(f["path"], f["ok"]) for f in listed] == [("faces", True), ("group-1", False)]
    off = await pin("group-1", on=False)
    assert off.status == 200 and [f["path"] for f in off.json()["folders"]] == ["faces"]
    r = await hub.http("POST", "/api/media/drive/remove", cookie=c, json_body={"path": "faces"})
    assert r.status == 200
    assert (await hub.http("GET", "/api/media/favorite-folders", cookie=c)).json() == {"folders": []}
    on_disk = hub.data / "media" / "favorite-folders.json"
    hub.core.store.flush()
    assert on_disk.exists() and "png" not in on_disk.read_text(), "the list holds folder paths, nothing of a picture"
