"""The audience's sounds, `sounds/audience/<kind>.wav`, the Hub's own files in its sounds
root. `keep_audience` copies a Sounds item in under its kind, stripped, replacing; `file_sound` moves a made sound
there when the name is free and leaves it where it is when taken; Media lists them under Sounds, above the days."""
from __future__ import annotations

import pytest

from hub.core.api import Invalid
from hub.core.files import Files
from hub.modules.media import library
from tests.core.harness import Hub, start_hub
from tests.fakes.wav import SECRET, chunk_ids, tiny_wav


def landed(f: Files, name: str = "120000-000", seconds: float = 1.0, tagged: bool = False) -> str:
    day = f.roots["sounds"] / "2026-10-18"
    day.mkdir(parents=True, exist_ok=True)
    (day / f"{name}.wav").write_bytes(tiny_wav(seconds, tagged=tagged))
    return f"sounds/2026-10-18/{name}.wav"


def test_keep_audience_copies_in_stripped_and_replaces(tmp_path):
    f = Files(tmp_path / "data")
    first, second = landed(f, "120000-000", 1.0, tagged=True), landed(f, "120001-000", 2.0)
    assert f.keep_audience(first, "applause") == "sounds/audience/applause.wav"
    kept = f.roots["sounds"] / "audience" / "applause.wav"
    assert chunk_ids(kept.read_bytes()) == [b"fmt ", b"data"] and SECRET not in kept.read_bytes(), "stripped"
    assert f.existing_media(first), "a copy: the sound stays in Sounds"
    assert f.keep_audience(second, "applause") == "sounds/audience/applause.wav"
    assert f.sound_facts("sounds/audience/applause.wav") == {"seconds": 2.0}, "replacing the one there"
    assert [p.name for p in kept.parent.iterdir()] == ["applause.wav"], "no temp file left"


@pytest.mark.parametrize("item, kind, field", [
    ("sounds/2026-10-18/120000-000.wav", "boos", "kind"),
    ("out/2026-10-18/a.png", "applause", "id"),
    ("sounds/2026-10-18/none.wav", "applause", "item"),
])
def test_keep_audience_refuses(tmp_path, item, kind, field):
    f = Files(tmp_path / "data")
    landed(f)
    with pytest.raises(Invalid) as err:
        f.keep_audience(item, kind)
    assert err.value.field == field


def test_file_sound_files_when_free_and_leaves_the_item_when_taken(tmp_path):
    f = Files(tmp_path / "data")
    made = landed(f, "120000-000", 4.0)
    assert f.file_sound(made, "laughter") == "sounds/audience/laughter.wav"
    assert not (f.roots["sounds"] / "2026-10-18" / "120000-000.wav").exists(), "moved, not copied"
    again = landed(f, "130000-000", 3.0)
    assert f.file_sound(again, "laughter") == again, "the name is taken: it stays where it landed"
    assert f.sound_facts("sounds/audience/laughter.wav") == {"seconds": 4.0}


def test_ids_list_under_sounds_above_the_days(tmp_path):
    f = Files(tmp_path / "data")
    f.keep_audience(landed(f), "gasps")
    assert library.ids(f.roots["sounds"], "sounds") == ["sounds/audience/gasps.wav",
                                                        "sounds/2026-10-18/120000-000.wav"]


async def test_the_route_keeps_a_sound_as_the_audience(tmp_path):
    hub: Hub = await start_hub(tmp_path / "data")
    try:
        item = landed(hub.core.files)
        heard: list[tuple[str, dict]] = []
        publish = hub.core.bus.publish
        hub.core.bus.publish = lambda lane, t, d, *a, **k: (heard.append((t, d)), publish(lane, t, d, *a, **k))  # type: ignore[method-assign]
        cookie = hub.pair()
        r = await hub.http("POST", "/api/sounds/audience", cookie=cookie, json_body={"id": item, "kind": "laughter"})
        assert r.status == 200 and r.json() == {"id": "sounds/audience/laughter.wav"}
        assert ("media.changed", {"what": "sounds"}) in heard
        r = await hub.http("POST", "/api/sounds/audience", cookie=cookie, json_body={"id": item, "kind": "boos"})
        assert r.status == 400 and r.json()["text"] == "Keep it as applause, laughter or gasps"
        bare = await hub.http("POST", "/api/sounds/audience", json_body={"id": item, "kind": "laughter"})
        assert bare.status == 401
    finally:
        await hub.close()
