"""The one PNG text field (`Description`): read, written pixel for pixel, a non-PNG converted, empty text leaving
no field, every other chunk cut."""
from __future__ import annotations

import struct
from pathlib import Path

import pytest
from PIL import Image, PngImagePlugin

from hub.core import pngtext

TEXT = "Note 1; note 2.\nUnicode too: é 山"


def chunks(path: Path) -> list[bytes]:
    data = path.read_bytes()
    pos, found = 8, []
    while pos < len(data):
        (length,) = struct.unpack(">I", data[pos:pos + 4])
        found.append(data[pos + 4:pos + 8])
        pos += 12 + length
    return found


def pixels(path: Path) -> bytes:
    with Image.open(path) as im:
        return im.convert("RGBA").tobytes()


def busy_png(path: Path) -> Path:
    info = PngImagePlugin.PngInfo()
    info.add_text("prompt", "a secret prompt")
    info.add_itxt("Comment", "more")
    info.add_text("Software", "some tool")
    ex = Image.Exif()
    ex[0x010F] = "A camera maker"
    Image.new("RGB", (16, 12), (200, 10, 10)).save(path, "PNG", pnginfo=info, exif=ex.tobytes(), dpi=(72, 72))
    return path


def test_round_trip_pixel_for_pixel(tmp_path: Path) -> None:
    src = busy_png(tmp_path / "a.png")
    before = pixels(src)
    assert pngtext.write(src, TEXT) == src
    assert pngtext.read(src) == TEXT
    assert pixels(src) == before
    assert [p.name for p in tmp_path.iterdir()] == ["a.png"], "no temp file left"


def test_every_other_chunk_is_stripped(tmp_path: Path) -> None:
    src = busy_png(tmp_path / "a.png")
    assert {b"tEXt", b"eXIf", b"pHYs"} <= set(chunks(src)), "the fixture really carries them"
    pngtext.write(src, TEXT)
    assert set(chunks(src)) == {b"IHDR", b"iTXt", b"IDAT", b"IEND"}
    with Image.open(src) as im:
        assert {k for k in im.info if isinstance(im.info[k], str)} == {pngtext.KEY}


def test_empty_text_removes_the_field(tmp_path: Path) -> None:
    src = busy_png(tmp_path / "a.png")
    pngtext.write(src, TEXT)
    pngtext.write(src, "")
    assert pngtext.read(src) == ""
    assert b"iTXt" not in chunks(src) and b"tEXt" not in chunks(src)


@pytest.mark.parametrize(("suffix", "fmt"), [(".jpg", "JPEG"), (".webp", "WEBP")])
def test_a_non_png_is_converted(tmp_path: Path, suffix: str, fmt: str) -> None:
    src = tmp_path / f"a{suffix}"
    opts = {"lossless": True} if fmt == "WEBP" else {"quality": 95}
    Image.new("RGB", (20, 10), (10, 120, 30)).save(src, fmt, **opts)
    before = pixels(src)
    dest = pngtext.write(src, TEXT)
    assert dest == tmp_path / "a.png" and not src.exists()
    assert sorted(p.name for p in tmp_path.iterdir()) == ["a.png"]
    assert pngtext.read(dest) == TEXT and pixels(dest) == before


def test_transparency_stays(tmp_path: Path) -> None:
    src = tmp_path / "a.png"
    Image.new("P", (4, 4), 1).save(src, "PNG", transparency=0)
    pngtext.write(src, TEXT)
    assert b"tRNS" in chunks(src)
    with Image.open(src) as im:
        assert im.info.get("transparency") == 0


def test_read_is_quiet_for_what_carries_nothing(tmp_path: Path) -> None:
    jpg = tmp_path / "a.jpg"
    Image.new("RGB", (4, 4)).save(jpg, "JPEG")
    broken = tmp_path / "b.png"
    broken.write_bytes(b"not a picture")
    assert pngtext.read(jpg) == "" and pngtext.read(broken) == "" and pngtext.read(tmp_path / "none.png") == ""
    assert pngtext.read(busy_png(tmp_path / "c.png")) == "", "other text fields are not the field"


def test_unreadable_file_raises_and_leaves_nothing(tmp_path: Path) -> None:
    broken = tmp_path / "b.png"
    broken.write_bytes(b"not a picture")
    with pytest.raises((OSError, ValueError)):
        pngtext.write(broken, TEXT)
    assert [p.name for p in tmp_path.iterdir()] == ["b.png"] and broken.read_bytes() == b"not a picture"
