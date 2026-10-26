"""A recording as a character's voice: `POST /api/characters/sample?id=` takes the WAV
the browser made, 2 to 15 s, and keeps it as `<Name>.wav` beside the picture, stripped to its sound, replacing
the one there; the temp file in the Temp goes; every Media window hears `media.changed`."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tests.core.harness import Hub, start_hub
from tests.core.test_characters import png
from tests.fakes.wav import SECRET, chunk_ids, tiny_wav

WAV = {"Content-Type": "audio/wav"}


@pytest.fixture
def chars(tmp_path: Path) -> Path:
    folder = tmp_path / "Characters"
    png(folder / "Character 8.png")
    return folder


@pytest.fixture
async def hub(tmp_path: Path, chars: Path):  # type: ignore[no-untyped-def]
    h = await start_hub(tmp_path / "data", settings={"paths": {"characters": str(chars)}})
    yield h
    await h.close()


async def send(hub: Hub, body: bytes, item: str = "chars/Character%208.png",
               headers: dict[str, str] | None = None) -> Any:
    return await hub.http("POST", f"/api/characters/sample?id={item}", cookie=hub.pair(), body=body,
                          headers=headers or WAV)


def left_in_temp(hub: Hub) -> list[str]:
    return [p.name for p in (hub.data / "outputs").rglob("*") if p.is_file()]


async def test_a_recording_becomes_the_characters_voice_stripped_and_replacing(hub: Hub, chars: Path) -> None:
    (chars / "character 8.WAV").write_bytes(tiny_wav(5))
    heard: list[tuple[str, dict]] = []
    publish = hub.core.bus.publish
    hub.core.bus.publish = lambda lane, t, d, *a, **k: (heard.append((t, d)), publish(lane, t, d, *a, **k))  # type: ignore[method-assign]
    r = await send(hub, tiny_wav(3, tagged=True))
    assert r.status == 200 and r.json() == {"id": "chars/Character 8.png", "seconds": 3.0}
    assert sorted(p.name for p in chars.iterdir()) == ["Character 8.png", "Character 8.wav"], \
        "the old sample of any case goes"
    kept = (chars / "Character 8.wav").read_bytes()
    assert chunk_ids(kept) == [b"fmt ", b"data"] and SECRET not in kept
    assert ("media.changed", {"what": "characters"}) in heard
    assert left_in_temp(hub) == []


@pytest.mark.parametrize(("body", "text"), [
    (tiny_wav(1), "A voice sample is at least 2 seconds"),
    (b"\x89PNG\r\n\x1a\n" + b"\x00" * 64, "That sound file could not be read"),
    (b"", "That sound file could not be read"),
])
async def test_what_is_not_a_voice_sample_is_refused(hub: Hub, chars: Path, body: bytes, text: str) -> None:
    r = await send(hub, body)
    assert r.status == 400 and r.json()["text"] == text
    assert sorted(p.name for p in chars.iterdir()) == ["Character 8.png"]
    assert left_in_temp(hub) == []


async def test_a_sample_past_fifteen_seconds_is_taken(hub: Hub, chars: Path) -> None:
    r = await send(hub, tiny_wav(20))                       # over 15 s the engine only splits samples
    assert r.status == 200 and r.json() == {"id": "chars/Character 8.png", "seconds": 20.0}
    assert sorted(p.name for p in chars.iterdir()) == ["Character 8.png", "Character 8.wav"]
    assert left_in_temp(hub) == []


async def test_a_sample_over_four_megabytes_is_taken(hub: Hub, chars: Path) -> None:
    body = tiny_wav(40)                                     # held to the sound upload's byte limit
    assert len(body) > 4 * 1024 * 1024
    r = await send(hub, body)
    assert r.status == 200 and r.json() == {"id": "chars/Character 8.png", "seconds": 40.0}
    assert sorted(p.name for p in chars.iterdir()) == ["Character 8.png", "Character 8.wav"]


async def test_only_a_wav_to_a_character_there(hub: Hub, chars: Path) -> None:
    small = tiny_wav(0.001)                                 # a refused body is not read: keep it small
    assert (await send(hub, small, headers={"Content-Type": "image/png"})).status == 415
    assert (await send(hub, small, headers={"Content-Type": "audio/mpeg"})).status == 415
    r = await send(hub, tiny_wav(3), item="chars/Nobody.png")
    assert r.status == 400 and r.json()["text"] == "That character is not in the Characters folder now"
    assert (await send(hub, tiny_wav(3), item="out/day/a.png")).json()["text"] == "Not a character"
    bare = await hub.http("POST", "/api/characters/sample?id=chars/Character%208.png", body=small, headers=WAV)
    assert bare.status == 401
    assert sorted(p.name for p in chars.iterdir()) == ["Character 8.png"]
    assert left_in_temp(hub) == []


async def test_no_characters_folder(tmp_path: Path) -> None:
    h = await start_hub(tmp_path / "bare")
    try:
        r = await send(h, tiny_wav(3))
        assert r.status == 400 and "Characters" in r.json()["text"]
    finally:
        await h.close()
