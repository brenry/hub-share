"""A length named for a scene is the Director's target, through the tools as
`test_script_tools.py`: the length stored and shown (the file, the did line, the shot line, `script_read`'s scene
line), the length asked and the length run, never a range; a write past it lands; `scene_add` is never refused for
what an earlier scene runs; `scene_change` sets, changes and clears; a shot's `max_words` correction is the shot's one
pass; a scene runs past an hour; the format's reading of `seconds`."""
from __future__ import annotations

from pathlib import Path

import pytest

from hub.core.api import Invalid
from hub.modules.director import layout, scriptshape
from tests.engine.test_script_tools import CONTEXT, Ctx, call, on_disk, refused, started

TEN = "one two three four five six seven eight nine ten"


@pytest.fixture
def ctx(tmp_path: Path) -> Ctx:
    return Ctx(tmp_path)


def words(n: int) -> str:
    return " ".join(f"w{k}" for k in range(n))


def ms(n: int) -> int:
    return layout.line_ms(words(n))


async def scene(ctx: Ctx, seconds: int | None = 5) -> dict:
    """Script 1: scene 1 (Character 7, Character 6) with `seconds`, shot s1."""
    await started(ctx)
    extra = {} if seconds is None else {"seconds": seconds}
    added = await call(ctx, "scene_add", {"title": "The opening", "cast": ["Character 7", "Character 6"], **extra})
    await call(ctx, "shot_add", {"scene": 1, "camera": "Wide shot of the stage as Character 6 sits"})
    return added


async def test_the_length_stored_and_shown(ctx: Ctx) -> None:
    added = await scene(ctx)
    assert added["state"][1] == "scene 1 · The opening · 5 s asked"
    assert on_disk(ctx)["scenes"][0]["seconds"] == 5
    said = await call(ctx, "line_add", {"shot": "s1", "speaker": "Character 7", "words": TEN})
    length = layout.line_ms(TEN)
    shot = next(line for line in said["state"] if line.startswith("shot s1"))
    assert shot.endswith(f" s left · scene 1 {layout.secs(length)} s of 5 s"), "the short last scene shown"
    read = (await call(ctx, "script_read", {}))["read"]
    assert "scene 1 · The opening · cast Character 7, Character 6 · 5 s asked" in read, "no range after it"
    assert len(said["state"]) <= 6


async def test_a_write_past_a_named_length_lands_and_says_both_lengths(ctx: Ctx) -> None:
    await scene(ctx)
    await call(ctx, "line_add", {"shot": "s1", "speaker": "Character 7", "words": TEN})
    said = await call(ctx, "line_add", {"shot": "s1", "speaker": "Character 6", "words": words(4)})
    now = layout.line_ms(TEN) + ms(4)
    shot = next(line for line in said["state"] if line.startswith("shot s1"))
    assert shot.endswith(f" s left · scene 1 {layout.secs(now)} s of 5 s"), "past 5 s: written, both lengths said"
    lines = [ev["words"] for ev in on_disk(ctx)["scenes"][0]["shots"][0]["events"] if ev["kind"] == "line"]
    assert lines == [TEN, words(4)]


async def test_a_change_past_a_named_length_is_accepted(ctx: Ctx) -> None:
    await scene(ctx, None)
    await call(ctx, "line_add", {"shot": "s1", "speaker": "Character 7", "words": words(20)})
    changed = await call(ctx, "scene_change", {"scene": 1, "seconds": 5})
    assert changed["state"][1] == (f"scene 1 · 5 s asked · runs {layout.secs(ms(20))} s · "
                                   f"{layout.secs(ms(20) - 5000)} s over · no dead air")
    assert "cut about" not in changed["state"][-1], "no fix line: a named length is reported, never a refusal"
    await call(ctx, "event_change", {"id": "l1", "fields": {"words": words(16)}})
    await call(ctx, "event_change", {"id": "l1", "fields": {"words": words(17)}})    # longer, past it: accepted
    line = next(ev for ev in on_disk(ctx)["scenes"][0]["shots"][0]["events"] if ev["id"] == "l1")
    assert line["words"] == words(17)
    await call(ctx, "event_remove", {"id": "l1"})                                    # a removal: accepted


async def test_a_next_scene_is_added_whatever_the_last_one_runs(ctx: Ctx) -> None:
    await scene(ctx)
    await call(ctx, "line_add", {"shot": "s1", "speaker": "Character 7", "words": TEN})    # short of its 5 s
    assert (await call(ctx, "scene_add", {"title": "Next", "cast": ["Character 7"]}))["state"][1] == "scene 2 · Next"
    await call(ctx, "event_change", {"id": "l1", "fields": {"words": words(20)}})     # over its 5 s
    assert (await call(ctx, "scene_add", {"title": "Third", "cast": ["Character 7"]}))["state"][1] == "scene 3 · Third"


async def test_scene_change_sets_changes_clears(ctx: Ctx) -> None:
    await scene(ctx, None)
    set_ = await call(ctx, "scene_change", {"scene": 1, "seconds": 15})
    assert set_["state"][1] == "scene 1 · 15 s asked · runs 1.00 s · 14.00 s under · no dead air"
    assert "write about" not in set_["state"][-1]
    assert on_disk(ctx)["scenes"][0]["seconds"] == 15
    assert (await call(ctx, "scene_change", {"scene": 1, "seconds": 8}))["state"][1].startswith("scene 1 · 8 s asked")
    cleared = await call(ctx, "scene_change", {"scene": 1, "seconds": 0})
    assert cleared["state"][1] == "scene 1 · no length asked"
    assert "seconds" not in on_disk(ctx)["scenes"][0]
    got = await refused(ctx, "scene_change", {"scene": 2, "seconds": 5})
    assert got["problem"] == "There is no scene 2"


async def test_a_max_words_correction_lands_inside_the_shot(ctx: Ctx) -> None:
    await scene(ctx, 15)
    await call(ctx, "line_add", {"shot": "s1", "speaker": "Character 7", "words": words(26)})
    await call(ctx, "shot_add", {"scene": 1, "camera": "Close-up of Character 6 as the question lands"})
    await call(ctx, "line_add", {"shot": "s2", "speaker": "Character 6", "words": TEN})
    sent = {"shot": "s2", "speaker": "Character 6", "words": words(40)}
    got = await refused(ctx, "line_add", sent)
    n = got["hints"]["max_words"]
    room = layout.SHOT_MAX_MS - layout.line_ms(TEN)
    assert n == max(k for k in range(1, 40) if ms(k) <= room), "the shot's one pass bounds it, not the named length"
    await call(ctx, "line_add", {**sent, "words": " ".join(sent["words"].split()[:n])})      # the hint lands
    sc = on_disk(ctx)["scenes"][0]
    assert sc["shots"][-1]["end_ms"] - sc["shots"][-1]["start_ms"] <= layout.SHOT_MAX_MS


async def test_a_scene_runs_past_an_hour(ctx: Ctx) -> None:
    added = await scene(ctx, None)
    assert added["state"][1] == "scene 1 · The opening"
    said = await call(ctx, "line_add", {"shot": "s1", "speaker": "Character 7", "words": TEN})
    assert next(line for line in said["state"] if line.startswith("shot s1")).endswith(" s left")
    await call(ctx, "scene_change", {"scene": 1, "seconds": 3601})                   # no most
    for k in range(250):                                                              # 250 shots of 15 s held
        await call(ctx, "shot_add", {"scene": 1, "camera": f"Medium on Character 7 {k}", "seconds": 15})
    sc = on_disk(ctx)["scenes"][0]
    assert sc["seconds"] == 3601 and sc["shots"][-1]["end_ms"] - sc["shots"][0]["start_ms"] > 3_600_000


def _v2(scene: dict) -> dict:
    return {"version": 2, "context": CONTEXT, "scenes": [{"title": "A", "cast": ["Character 7"], "shots": [], **scene}]}


@pytest.mark.parametrize("seconds", [1, 60, 3601])
def test_the_format_reads_seconds(seconds: int) -> None:
    read = scriptshape.read(_v2({"seconds": seconds}), {"character 7", "character 6"})
    assert read["scenes"][0]["seconds"] == seconds


@pytest.mark.parametrize("seconds", [0, 1.5, "15", True])
def test_the_format_refuses_bad_seconds(seconds: object) -> None:
    with pytest.raises(Invalid) as e:
        scriptshape.read(_v2({"seconds": seconds}), {"character 7", "character 6"})
    assert e.value.text == "Scene 1: seconds is a whole number from 1"


def test_version_1_knows_no_seconds() -> None:
    v1 = {"version": 1, "scenes": [{"title": "A", "cast": ["Character 7"], "seconds": 5,
                                    "shots": [{"start_ms": 0, "end_ms": 1000, "events": []}]}]}
    with pytest.raises(Invalid) as e:
        scriptshape.read(v1, {"character 7"})
    assert e.value.text == "Scene 1: the scene has a key the format does not know: seconds"
