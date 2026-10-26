"""Clips over HTTP: `/files/clips/...` with Range, the `/clips` page, and Media on the clips root."""
from __future__ import annotations

import io
import os
from pathlib import Path

import pytest
from PIL import Image

from hub.modules.media.manifest import MODULE
from tests.core.harness import Hub, start_hub
from tests.fakes.mp4 import tiny_mp4

CLIP = "clips/2026-10-09/120000-000.mp4"


def aged(hub: Hub, *rels: str) -> None:
    """c1573bb: clips are listed newest first by mtime; each one's mtime set to the order given, newest first."""
    for n, rel in enumerate(reversed(rels)):
        os.utime(hub.data / rel, (1_790_000_000 + n, 1_790_000_000 + n))


def png_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (16, 12), (200, 10, 10)).save(buf, "PNG")
    return buf.getvalue()


@pytest.fixture
async def hub(tmp_path: Path):  # type: ignore[no-untyped-def]
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<!doctype html><title>Hub</title>")
    for folder in ("Drive", "Chars"):
        (tmp_path / folder).mkdir()
    h = await start_hub(tmp_path / "data", modules=[MODULE], dist=dist,
                        settings={"paths": {"drive": str(tmp_path / "Drive"), "characters": str(tmp_path / "Chars")}})
    for rel, data in ((CLIP, tiny_mp4()), ("clips/2026-10-08/090000-000.mp4", tiny_mp4(1000)),
                      ("outputs/2026-10-09/a.png", png_bytes())):
        (h.data / rel).parent.mkdir(parents=True, exist_ok=True)
        (h.data / rel).write_bytes(data)
    yield h
    await h.close()


async def test_a_clip_is_served_as_mp4_with_ranges(hub: Hub) -> None:
    c, body = hub.pair(), tiny_mp4()
    r = await hub.http("GET", f"/files/{CLIP}?v=1", cookie=c)
    assert r.status == 200 and r.headers["content-type"] == "video/mp4" and r.body == body
    assert r.headers["accept-ranges"] == "bytes" and r.headers["cache-control"] == "no-store"
    assert r.headers["x-content-type-options"] == "nosniff", "the guard's headers still ride along"
    part = await hub.http("GET", f"/files/{CLIP}", cookie=c, headers={"Range": "bytes=0-99"})
    assert part.status == 206 and part.body == body[:100] and part.headers["content-range"] == "bytes 0-99/5000"
    tail = await hub.http("GET", f"/files/{CLIP}", cookie=c, headers={"Range": "bytes=4990-"})
    assert tail.status == 206 and tail.body == body[4990:] and tail.headers["content-range"] == "bytes 4990-4999/5000"
    bad = await hub.http("GET", f"/files/{CLIP}", cookie=c, headers={"Range": "bytes=9000-"})
    assert bad.status == 416 and bad.headers["content-range"] == "bytes */5000"
    assert (await hub.http("GET", f"/files/{CLIP}")).status == 401
    assert (await hub.http("GET", f"/thumbs/{CLIP}/336", cookie=c)).status == 404, "no thumbnail for a clip"
    pic = await hub.http("GET", "/files/out/2026-10-09/a.png", cookie=c, headers={"Range": "bytes=0-7"})
    assert pic.status == 206 and pic.body == png_bytes()[:8] and pic.headers["content-type"] == "image/png"


async def test_the_clips_page_is_the_shell(hub: Hub) -> None:
    c = hub.pair()
    clips, media = await hub.http("GET", "/clips", cookie=c), await hub.http("GET", "/media", cookie=c)
    assert clips.status == 200 and clips.body == media.body and clips.headers["content-type"].startswith("text/html")


async def test_media_lists_the_clips_root_apart_from_temp(hub: Hub) -> None:
    c = hub.pair()
    aged(hub, CLIP, "clips/2026-10-08/090000-000.mp4")
    r = (await hub.http("GET", "/api/media?root=clips", cookie=c)).json()
    assert [i["id"] for i in r["items"]] == [CLIP, "clips/2026-10-08/090000-000.mp4"] and r["total"] == 2
    item = r["items"][0]
    assert item["kind"] == "clip" and item["thumb"].startswith("/thumbs/clips/")    # 1be310f: its first frame
    assert (item["w"], item["h"]) == (960, 544)
    assert item["seconds"] == pytest.approx(124 / 24, abs=1e-3), "its length, from its boxes"
    assert item["url"].startswith(f"/files/{CLIP}?v=") and item["group"] == "" and item["fav"] is False
    assert set(item) == {"id", "kind", "url", "thumb", "w", "h", "seconds", "createdAt", "group", "fav"}
    assert r["groups"] == [], "no Favorites place among clips"
    out = (await hub.http("GET", "/api/media", cookie=c)).json()
    assert [i["id"] for i in out["items"]] == ["out/2026-10-09/a.png"] and out["items"][0]["kind"] == "image"
    assert (await hub.http("GET", "/api/media?root=out", cookie=c)).json()["items"] == out["items"]
    bad = await hub.http("GET", "/api/media?root=drive", cookie=c)
    assert bad.status == 400 and bad.json()["text"] == "List out, clips or sounds"
    later = (await hub.http("GET", f"/api/media?root=clips&before={CLIP}", cookie=c)).json()
    assert [i["id"] for i in later["items"]] == ["clips/2026-10-08/090000-000.mp4"]


async def test_clips_list_newest_first_like_temp(hub: Hub) -> None:
    c = hub.pair()
    for rel in ("clips/2026-10-09/235959-999.mp4", "clips/2026-10-09/080000-000.mp4",
                "outputs/2026-10-09/235959-999.png", "outputs/2026-10-09/080000-000.png"):
        (hub.data / rel).write_bytes(png_bytes() if rel.endswith(".png") else tiny_mp4())
    aged(hub, "clips/2026-10-09/235959-999.mp4", CLIP, "clips/2026-10-09/080000-000.mp4",
         "clips/2026-10-08/090000-000.mp4")
    clips = (await hub.http("GET", "/api/media?root=clips", cookie=c)).json()["items"]
    assert [i["id"].split("/", 1)[1] for i in clips] == [
        "2026-10-09/235959-999.mp4", "2026-10-09/120000-000.mp4", "2026-10-09/080000-000.mp4",
        "2026-10-08/090000-000.mp4"], "the newest generation at the top, every one loose"
    temp = (await hub.http("GET", "/api/media", cookie=c)).json()["items"]
    assert [i["id"].split("/", 1)[1] for i in temp] == [
        "2026-10-09/a.png", "2026-10-09/235959-999.png", "2026-10-09/080000-000.png"], "the same order as Temp"


async def test_a_clip_whose_boxes_do_not_read_is_listed_without_size(hub: Hub) -> None:
    bad = "clips/2026-10-10/070000-000.mp4"
    (hub.data / bad).parent.mkdir(parents=True, exist_ok=True)
    (hub.data / bad).write_bytes(b"not an mp4 at all")
    r = (await hub.http("GET", "/api/media?root=clips", cookie=hub.pair())).json()
    item = r["items"][0]
    assert item["id"] == bad and r["total"] == 3, "listed all the same"
    assert (item["w"], item["h"], item["seconds"]) == (None, None, None) and item["kind"] == "clip"


async def test_a_clip_can_be_deleted_but_not_favorited_moved_or_cast(hub: Hub) -> None:
    c = hub.pair()
    for path, body, text in (("/api/media/favorite", {"ids": [CLIP], "on": True}, "Only pictures can be favorites"),
                             ("/api/media/move", {"ids": [CLIP], "to": ""}, "Only pictures can go to the Drive"),
                             ("/api/media/characters", {"id": CLIP, "name": "Character 17"},
                              "Only pictures can be characters")):
        r = await hub.http("POST", path, cookie=c, json_body=body)
        assert r.status == 400 and r.json()["text"] == text, path
    assert (hub.data / CLIP).is_file(), "nothing moved"
    assert not any((hub.data.parent / "Chars").iterdir()) and not any((hub.data.parent / "Drive").iterdir())
    r = await hub.http("POST", "/api/media/delete", cookie=c, json_body={"ids": [CLIP]})
    assert r.status == 200 and r.json() == {"ids": [CLIP]} and not (hub.data / CLIP).exists()
    left = (await hub.http("GET", "/api/media?root=clips", cookie=c)).json()["items"]
    assert [i["id"] for i in left] == ["clips/2026-10-08/090000-000.mp4"]
    r = await hub.http("POST", "/api/media/delete", cookie=c, json_body={"ids": ["clips/2026-10-09/../x.mp4"]})
    assert r.status == 400
