"""A picture is only its pixels: metadata is cut out of PNG, JPEG and WebP files without touching the image."""
from __future__ import annotations

import io
import struct
from pathlib import Path

import pytest
from PIL import Image, PngImagePlugin

from hub.core import clean


def exif_bytes() -> bytes:
    ex = Image.Exif()
    ex[0x010F] = "A camera maker"
    ex[0x9003] = "2026:10:12 09:00:00"
    ex[0x0131] = "Some phone software 1.2"
    return ex.tobytes()


def picture() -> Image.Image:
    im = Image.new("RGBA", (9, 7), (10, 20, 30, 200))
    im.putpixel((3, 3), (250, 1, 2, 255))
    return im


@pytest.mark.parametrize("fmt", ["PNG", "JPEG", "WEBP"])
def test_metadata_goes_and_the_pixels_stay(tmp_path: Path, fmt: str) -> None:
    im = picture() if fmt != "JPEG" else picture().convert("RGB")
    path = tmp_path / f"p.{fmt.lower()}"
    if fmt == "PNG":
        info = PngImagePlugin.PngInfo()
        info.add_text("prompt", "a grey cat asleep under an apple tree")
        info.add_text("parameters", "steps: 4, seed: 1234", zip=True)
        info.add_itxt("Comment", "made somewhere", "en", "comment")
        im.save(path, "PNG", pnginfo=info, exif=exif_bytes())
    elif fmt == "JPEG":
        im.save(path, "JPEG", quality=95, exif=exif_bytes(), comment=b"prompt: a grey cat", icc_profile=b"\0" * 64)
    else:
        im.save(path, "WEBP", lossless=True, exif=exif_bytes(), xmp="<x:xmpmeta>prompt</x:xmpmeta>")
    with Image.open(path) as before:
        before.load()
        pixels_before = before.tobytes()
        assert before.getexif() or before.info, "the test file does carry metadata"
    assert clean.strip(path) is True
    with Image.open(path) as after:
        after.load()
        assert after.tobytes() == pixels_before and after.format == fmt
        assert dict(after.getexif()) == {}
        shape = ("dpi", "icc_profile", "transparency", "mode", "loop", "background", "duration", "timestamp")
        told = {k for k in after.info if not k.startswith("jfif") and k not in shape}
        assert told == set(), f"{fmt} still says {told}"
    raw = path.read_bytes()
    for word in (b"prompt", b"camera", b"xmpmeta", b"2026:10", b"parameters"):
        assert word not in raw
    assert clean.strip(path) is False, "nothing left to cut"


def test_another_format_is_written_again_as_png_and_a_broken_file_is_refused(tmp_path: Path) -> None:
    gif = tmp_path / "a.gif"
    Image.new("RGB", (2, 2), (5, 6, 7)).save(gif, "GIF", comment=b"made somewhere")
    assert clean.strip(gif) is True
    with Image.open(gif) as im:
        assert im.format == "PNG" and im.convert("RGB").getpixel((0, 0)) == (5, 6, 7) and "comment" not in im.info
    broken = tmp_path / "b.png"
    broken.write_bytes(clean.PNG_SIG + b"\0\0\0\x10tEXt")
    with pytest.raises((OSError, ValueError)):
        clean.strip(broken)
    out = io.BytesIO()
    Image.new("RGB", (2, 2)).save(out, "JPEG")
    cut = tmp_path / "c.jpg"
    cut.write_bytes(out.getvalue()[:40])
    with pytest.raises((OSError, ValueError)):
        clean.strip(cut)


def test_jpeg_scans_comments_between_them_and_trailers_after_the_end(tmp_path: Path) -> None:
    """A progressive JPEG has several scans; a phone can put a comment between them and a second picture (with
    its own EXIF) or a video after the end marker. Everything but the picture goes."""
    path = tmp_path / "p.jpg"
    picture().convert("RGB").save(path, "JPEG", quality=90, progressive=True, exif=exif_bytes())
    raw = path.read_bytes()
    first_sos = raw.index(b"\xff\xda")
    second_sos = raw.index(b"\xff\xda", first_sos + 2)
    comment = b"\xff\xfe" + struct.pack(">H", 2 + 12) + b"prompt: cats"
    stuffed = raw[:second_sos] + comment + raw[second_sos:]
    trailer = b"\xff\xd8\xff\xe1" + struct.pack(">H", 2 + 6 + len(exif_bytes())) + b"Exif\0\0" + exif_bytes()
    path.write_bytes(stuffed + trailer + b"ftypmp4 a motion photo")
    with Image.open(path) as before:
        before.load()
        pixels = before.tobytes()
    assert clean.strip(path) is True
    out = path.read_bytes()
    assert out.endswith(b"\xff\xd9") and b"prompt" not in out and b"camera" not in out and b"motion" not in out
    assert out.count(b"\xff\xda") == stuffed.count(b"\xff\xda"), "every scan is still there"
    with Image.open(path) as after:
        after.load()
        assert after.tobytes() == pixels and dict(after.getexif()) == {}


def test_a_leaning_photo_is_turned_upright_and_its_tag_goes(tmp_path: Path) -> None:
    path = tmp_path / "phone.jpg"
    im = Image.new("RGB", (16, 8), (0, 0, 0))
    im.paste((255, 0, 0), (0, 0, 8, 4))       # the left half of the top row is red
    ex = Image.Exif()
    ex[0x0112] = 6                      # rotate 90° clockwise to show
    ex[0x010F] = "A camera maker"
    im.save(path, "JPEG", quality=100, exif=ex.tobytes())
    assert clean.strip(path) is True
    with Image.open(path) as after:
        assert after.size == (8, 16) and dict(after.getexif()) == {}
        assert after.getpixel((6, 2))[0] > 200 and after.getpixel((1, 2))[0] < 60, "the red turned with the picture"
    assert b"camera" not in path.read_bytes()


def test_a_file_that_does_not_parse_is_written_again_from_its_pixels(tmp_path: Path) -> None:
    path = tmp_path / "odd.png"
    info = PngImagePlugin.PngInfo()
    info.add_text("prompt", "secret")
    picture().save(path, "PNG", pnginfo=info)
    path.write_bytes(path.read_bytes()[:-12])            # no IEND: the chunk walk gives up
    with Image.open(path) as before:
        before.load()
        pixels = before.tobytes()
    assert clean.strip(path) is True
    assert b"secret" not in path.read_bytes() and b"tEXt" not in path.read_bytes()
    with Image.open(path) as after:
        after.load()
        assert after.tobytes() == pixels
    junk = tmp_path / "junk.png"
    junk.write_bytes(b"not a picture at all")
    with pytest.raises((OSError, ValueError)):
        clean.strip(junk)
