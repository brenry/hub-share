"""Media roots: path confinement, /files and /thumbs, uploads (magic, size, pixel bomb), regroup, delete."""
from __future__ import annotations

import io
import os
import struct
import zlib
from pathlib import Path

import pytest
from PIL import Image, PngImagePlugin

from hub.core import thumbs as thumbs_mod
from hub.core.api import Invalid
from hub.core.files import Files
from tests.core.harness import Hub, start_hub


def png_bytes(w: int = 16, h: int = 12) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (200, 10, 10)).save(buf, "PNG")
    return buf.getvalue()


def bomb_png(w: int, h: int) -> bytes:
    """A tiny PNG whose header claims w x h pixels."""
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(b"\0")) + chunk(b"IEND", b"")


@pytest.fixture
def media(tmp_path: Path) -> Files:
    f = Files(tmp_path / "data")
    (f.roots["out"] / "day").mkdir()
    (f.roots["out"] / "day" / "a.png").write_bytes(png_bytes())
    (f.roots["out"] / "day" / "page.html").write_text("<script>")
    (f.roots["out"] / "day" / "logo.svg").write_text("<svg/>")
    (tmp_path / "outside.png").write_bytes(png_bytes())
    os.symlink(tmp_path / "outside.png", f.roots["out"] / "day" / "link.png")
    return f


@pytest.mark.parametrize("item", ["", "out", "out/", "/etc/passwd", "out/../../x.png", "out/day/../../x",
                                  "out/./day/a.png", "out//a.png", "in\\x.png", "out/day/a.png\0", "drive/x.png",
                                  "out/day/link.png", "x" * 600])
def test_resolver_refuses_escapes(media: Files, item: str) -> None:
    with pytest.raises(Invalid):
        media.existing_image(item)


def test_resolver_accepts_items_and_only_images(media: Files) -> None:
    assert media.existing_image("out/day/a.png") == media.roots["out"].resolve() / "day" / "a.png"
    for item in ("out/day/page.html", "out/day/logo.svg", "out/day/missing.png"):
        with pytest.raises(Invalid):
            media.existing_image(item)
    assert media.item_for(media.roots["out"] / "day" / "a.png") == "out/day/a.png"
    assert media.item_for(Path("/etc/passwd")) is None
    assert media.url("out/day/a.png").startswith("/files/out/day/a.png?v=")
    assert media.url("out/day/a b#.png") == "/files/out/day/a%20b%23.png"


def test_delete_erases_the_file_and_its_thumbnail_for_good(media: Files) -> None:
    """DEL means gone: no trash folder, no undo; the in-memory thumbnail goes with it."""
    media.thumbnail("out/day/a.png", 96)
    assert any(k.endswith("|96") for k in media.thumbs._items)
    assert media.delete(["out/day/a.png", "out/day/missing.png"]) == ["out/day/a.png"]
    assert not (media.roots["out"] / "day" / "a.png").exists()
    assert not media.thumbs._items, "the thumbnail goes with it"
    assert not list(media.data_dir.rglob("a.png")), "nothing kept anywhere under the data folder"
    own = ["clips", "outputs", "scripts", "sets", "sounds"]
    assert sorted(p.name for p in media.data_dir.iterdir()) == own, "the own roots"


def test_thumbnails_are_webp_in_memory_only(media: Files) -> None:
    data = media.thumbnail("out/day/a.png", 96)
    with Image.open(io.BytesIO(data)) as im:
        assert im.format == "WEBP" and im.size == (16, 12)
    assert media.thumbnail("out/day/a.png", 96) is data, "served from memory the second time"
    with pytest.raises(Invalid):
        media.thumbnail("out/day/a.png", 100)
    assert not list(media.data_dir.rglob("*.webp")), "never written"
    store = thumbs_mod.ThumbStore(cap_mb=0)
    store.put("x|1|96", b"abc")
    assert store.get("x|1|96") is None, "a full store forgets the oldest"


def test_take_in_names_by_time_inside_temp_and_cuts_metadata(media: Files, tmp_path: Path) -> None:
    tmp = tmp_path / "up.png"
    info = PngImagePlugin.PngInfo()
    info.add_text("parameters", "a grey cat, seed 1234")
    Image.new("RGB", (4, 4), (1, 2, 3)).save(tmp, "PNG", pnginfo=info)
    item = media.take_in(tmp, ".png")
    assert item.startswith("out/") and media.existing_image(item).is_file() and not tmp.exists()
    name = item.rsplit("/", 1)[-1]
    assert len(name) == len("HHMMSS-mmm.png") and name[:6].isdigit(), "the time, nothing else"
    with Image.open(media.existing_image(item)) as im:
        assert "parameters" not in im.info and im.getpixel((0, 0)) == (1, 2, 3)
    assert b"grey cat" not in media.existing_image(item).read_bytes()


def test_regroup_moves_within_the_day(media: Files) -> None:
    moved = media.regroup(["out/day/a.png"], "Favorites")
    assert moved == [("out/day/a.png", "out/day/Favorites/a.png")]
    assert media.existing_image("out/day/Favorites/a.png").is_file()
    assert media.regroup(["out/day/Favorites/a.png"], "Favorites") == [], "already there"
    back = media.regroup(["out/day/Favorites/a.png"], "")
    assert back == [("out/day/Favorites/a.png", "out/day/a.png")]
    assert not (media.roots["out"] / "day" / "Favorites").exists(), "an emptied group folder goes"


@pytest.fixture
async def hub(tmp_path: Path):  # type: ignore[no-untyped-def]
    h = await start_hub(tmp_path / "data")
    (h.data / "outputs" / "day").mkdir(parents=True, exist_ok=True)
    (h.data / "outputs" / "day" / "a.png").write_bytes(png_bytes())
    (h.data / "outputs" / "day" / "x.svg").write_text("<svg/>")
    yield h
    await h.close()


async def test_files_and_thumbs_over_http(hub: Hub) -> None:
    c = hub.pair()
    r = await hub.http("GET", "/files/out/day/a.png?v=1", cookie=c)
    assert r.status == 200 and r.headers["content-type"] == "image/png" and r.body == png_bytes()
    assert r.headers["cache-control"] == "no-store", "a browser keeps no copy of a picture"
    assert (await hub.http("GET", "/files/out/day/a.png", cookie=c)).headers["cache-control"] == "no-store"
    assert (await hub.http("GET", "/files/out/day/a.png")).status == 401
    for bad in ("/files/out/day/x.svg", "/files/out/%2e%2e/%2e%2e/settings.json", "/files/out/day/a.png%00",
                "/files//etc/passwd", "/files/in/../out/day/a.png"):
        assert (await hub.http("GET", bad, cookie=c)).status == 404, bad
    t = await hub.http("GET", "/thumbs/out/day/a.png/336?v=2", cookie=c)
    assert t.status == 200 and t.headers["content-type"] == "image/webp" and t.body[8:12] == b"WEBP"
    assert (await hub.http("GET", "/thumbs/out/day/a.png/337", cookie=c)).status == 404


async def test_uploads_are_checked(hub: Hub) -> None:
    c = hub.pair()
    ok = await hub.http("POST", "/api/upload", cookie=c, body=png_bytes(), headers={"Content-Type": "image/png"})
    assert ok.status == 200 and ok.json()["id"].startswith("out/")
    again = await hub.http("POST", "/api/upload", cookie=c, body=png_bytes(), headers={"Content-Type": "image/png"})
    assert again.json()["id"] != ok.json()["id"], "every picture taken in is a Temp file of its own"
    cases = [(png_bytes(), "image/jpeg", 400), (b"GIF89a....", "image/png", 400), (b"", "image/png", 400),
             (bomb_png(20_000, 20_000), "image/png", 400), (bomb_png(9_000, 9_000), "image/png", 400),
             (png_bytes(), "text/plain", 415), (png_bytes(), "image/gif", 415)]
    for body, ctype, status in cases:
        r = await hub.http("POST", "/api/upload", cookie=c, body=body, headers={"Content-Type": ctype})
        assert r.status == status, (ctype, r.text)
    big = await hub.http("POST", "/api/upload", cookie=c, body=b"\x89PNG",
                         headers={"Content-Type": "image/png", "Content-Length": str(25 * 1024 * 1024 + 1)})
    assert big.status == 413
    leftovers = [p.name for p in (hub.data / "outputs").rglob(".*")]
    assert leftovers == [] and not (hub.data / "inputs").exists()
    r = await hub.http("POST", "/api/upload", cookie=c, body=bomb_png(9_000, 9_000),
                       headers={"Content-Type": "image/png"})
    assert r.json()["text"] == "That image is too large (over 64 megapixels)"


async def test_check_confirms_pictures_without_copying(hub: Hub) -> None:
    c = hub.pair()
    r = await hub.http("POST", "/api/media/check", cookie=c, json_body={"items": ["out/day/a.png"]})
    assert r.status == 200 and r.json()["placed"] == [{"item": "out/day/a.png", "id": "out/day/a.png"}]
    many = await hub.http("POST", "/api/media/check", cookie=c, json_body={"items": ["out/day/a.png"] * 51})
    assert many.status == 200 and len(many.json()["placed"]) == 51, "no count of the Hub's"
    for body in ({"items": ["out/day/x.svg"]}, {"items": []}, {"items": "out/day/a.png"}, ["x"]):
        assert (await hub.http("POST", "/api/media/check", cookie=c, json_body=body)).status == 400
    assert sorted(p.name for p in hub.data.iterdir() if p.is_dir()) == sorted(
        n for n in os.listdir(hub.data) if (hub.data / n).is_dir()), "no copies folder appeared"


def test_what_an_older_hub_kept_is_erased_at_start(tmp_path: Path) -> None:
    data = tmp_path / "data"
    for rel in ("inputs/abc.png", "cache/thumbs/x.webp", "media/favorites.json", "loras/covers/c.webp",
                "loras/thumbs/t.webp", "core/learned.json", "generate-image/prompts.json"):
        (data / rel).parent.mkdir(parents=True, exist_ok=True)
        (data / rel).write_bytes(b"old")
    (data / "loras" / "loras.json").write_text('{"version": 1, "loras": {}}')
    (data / "outputs" / "2026-10-09").mkdir(parents=True)
    (data / "outputs" / "2026-10-09" / "a.png").write_bytes(png_bytes())
    Files(data)
    left = sorted(str(p.relative_to(data)) for p in data.rglob("*") if p.is_file())
    assert left == ["loras/loras.json", "outputs/2026-10-09/a.png"], "the pictures and the strengths stay"
