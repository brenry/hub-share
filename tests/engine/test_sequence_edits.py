"""Edit Video's edges through the hub: a drop is one save (an item without `out` is the whole clip), a rename that
cannot read its file moves nothing and tells nobody, a clip erased in Media drops out of every sequence at once, the
join takes crf and preset from settings, and the last clip is the newest of a job's several."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from hub.modules.sequence import last
from tests.core.harness import Hub
from tests.core.test_mcp import result
from tests.engine.sequence_kit import DAY, clip, seq_path, two, whole
from tests.engine.test_sequence_module import finished, open_hub

PLAIN = "Use a plain sequence name, without slashes"


@pytest.fixture
async def hub(tmp_path: Path):  # type: ignore[no-untyped-def]
    h = await open_hub(tmp_path)
    last._last.clear()
    yield h
    last._last.clear()
    await h.close()


async def quiet(w) -> None:  # type: ignore[no-untyped-def]
    """No `sequence.changed` reaches the window."""
    try:
        got = await w.recv("sequence.changed", timeout=0.3)
    except TimeoutError:
        return
    raise AssertionError(f"told: {got}")


async def test_a_drop_is_one_save_and_the_file_holds_the_frames(hub: Hub) -> None:
    files, cookie = hub.core.files, hub.pair()
    w = await hub.screen(cookie, "workspace", "w")
    a = clip(files, "101500-123")
    await hub.http("POST", "/api/sequence/new", cookie, json_body={"name": "Film"})
    assert (await w.recv("sequence.changed", timeout=2))["d"] == {"name": "Film", "revision": 0}
    put = await hub.http("PUT", "/api/sequence/one", cookie,
                         json_body={"name": "Film", "revision": 0, "tracks": two([{"clip": a, "in": 0}])})
    assert put.status == 200, put.json()
    first = put.json()["tracks"][0][0]
    assert (put.json()["revision"], first["out"], first["kept"], first["kind"], first["id"]) == \
        (1, 124, 5.17, "clip", a)
    assert (await w.recv("sequence.changed", timeout=2))["d"] == {"name": "Film", "revision": 1}
    await quiet(w)
    assert json.loads(seq_path(files, "Film").read_text())["tracks"] == [[whole(a)], []]


async def test_a_rename_refused_moves_nothing_and_tells_nobody(hub: Hub) -> None:
    files, cookie = hub.core.files, hub.pair()
    files.sequence_new("Film")
    w = await hub.screen(cookie, "workspace", "w")
    for to in ("a/b", "", ".x", "x" * 256, "😀" * 60):
        bad = await hub.http("POST", "/api/sequence/rename", cookie, json_body={"name": "Film", "to": to})
        assert (bad.status, bad.json()["text"]) in ((400, PLAIN), (400, "Name the sequence")), to
    seq_path(files, "Torn").write_text("{half")
    torn = await hub.http("POST", "/api/sequence/rename", cookie, json_body={"name": "Torn", "to": "Whole"})
    assert (torn.status, torn.json()["text"]) == (400, "The sequence Torn cannot be read")
    await quiet(w)
    assert sorted(p.name for p in seq_path(files, "Film").parent.iterdir()) == ["Film.json", "Torn.json"]


async def test_a_clip_erased_in_media_drops_out_of_every_sequence(hub: Hub) -> None:
    files, cookie = hub.core.files, hub.pair()
    a, b = clip(files, "101500-123"), clip(files, "101600-456")
    for name in ("Film", "Other", "Spare"):
        files.sequence_new(name)
    files.sequence_save("Film", two([whole(a), whole(b)]), 0, 200)
    files.sequence_save("Other", two([], [{**whole(a), "at": 0}]), 0, 200)
    files.sequence_save("Spare", two([whole(b)]), 0, 200)
    w = await hub.screen(cookie, "workspace", "w")
    gone = await hub.http("POST", "/api/media/delete", cookie, json_body={"ids": [a]})
    assert gone.json() == {"ids": [a]}
    told = [(await w.recv("sequence.changed", timeout=2))["d"] for _ in range(2)]
    assert sorted(told, key=lambda d: d["name"]) == [{"name": "Film", "revision": 2}, {"name": "Other", "revision": 2}]
    await quiet(w)
    assert json.loads(seq_path(files, "Film").read_text())["tracks"] == [[whole(b)], []], "dropped from the file"
    assert files.sequence("Other")["tracks"] == [[], []], "from track 2 too"
    assert files.sequence("Spare")["revision"] == 1, "a sequence without it is not written"
    stale = await hub.http("PUT", "/api/sequence/one", cookie,
                           json_body={"name": "Film", "revision": 1, "tracks": two([whole(a), whole(b)])})
    assert stale.json()["text"] == "The sequence changed in another window", "a window's older save reloads"
    picture = f"out/{DAY}/101700-000.png"
    files.roots["out"].joinpath(DAY).mkdir(parents=True, exist_ok=True)
    files.resolve(picture).write_bytes(b"\x89PNG\r\n\x1a\n")
    erased = await hub.http("POST", "/api/media/delete", cookie, json_body={"ids": [picture]})
    assert erased.json() == {"ids": [picture]}
    await quiet(w)


async def test_the_join_takes_crf_and_preset_from_settings(tmp_path: Path) -> None:
    hub = await open_hub(tmp_path, {"modules": {"sequence": {"join_crf": 23, "join_preset": "veryfast"}}})
    try:
        files, cookie = hub.core.files, hub.pair()
        a = clip(files, "101500-123")
        files.sequence_new("Film")
        files.sequence_save("Film", two([{"clip": a, "in": 12, "out": 60}]), 0, 200)
        joined = await hub.http("POST", "/api/sequence/join", cookie, json_body={"name": "Film"})
        [task] = hub.core.book.get(joined.json()["job"]).plan.tasks
        assert (task["crf"], task["preset"]) == (23, "veryfast"), "not the defaults 18, medium"
    finally:
        await hub.close()


async def test_the_last_clip_is_the_newest_of_several(hub: Hub) -> None:
    files = hub.core.files
    a, b, c = (clip(files, stem) for stem in ("101500-123", "101600-456", "101700-789"))
    await finished(hub, outputs=[a, b, f"out/{DAY}/101800-000.png", c])
    assert (await result(hub, "add_last_clip", {"sequence": "Film"}))["clip"] == c
    await finished(hub, outputs=[b, a])
    assert (await result(hub, "add_last_clip", {"sequence": "Film"}))["clip"] == a, "a later job's newest replaces it"
    assert files.sequence("Film")["tracks"] == [[whole(c), whole(a)], []]
