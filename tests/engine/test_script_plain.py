"""Plain talk (`say.py`, `sayplain.py`, `saycheck.py`, `sayask.py`, `saytrial.py`,
`context.py`, `start.py`, `frame.context_set`) on stub planner answers: a story with no length, told with no `Script:`
word, naming a member with no picture and no voice, is written; a message naming nothing to change writes nothing, a
removal it was not asked for is sent back and never written; a done message says every scene done with no model asked;
render is Render with no model asked; a wardrobe change through the context's cast; a member's picture used as the
reference, as the first frame, or not at all. Only the Hub's own terms as placeholders (CLAUDE.md)."""
from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import pytest

from hub.core.api import Invalid
from hub.modules.director import autolock, context, mix, say, sayask, saycheck, sayplain
from tests.engine.test_media_characters import png_bytes
from tests.engine.test_script_mix import mctx  # noqa: F401  (the fixture)
from tests.engine.test_script_say import TOOLS, hub, lines, shot_list
from tests.engine.test_script_tools import Model, on_disk
from tests.engine.test_script_track import call
from tests.engine.test_script_track import ctx as track_ctx  # noqa: F401  (the fixture)

P1, P2, P3, NAME = "Subject 1", "Subject 2", "Subject 3", "Script 1"
STORY = f"Scene 1: {P1} and {P2}, lines l1 to l4."
CONTEXT = {"cast": [{"name": P1, "look": "subject_definitions 1", "costume": "wardrobe 1",
                     "ignore": "retention_analysis", "home": 30},
                    {"name": P2, "look": "subject_definitions 2", "costume": "wardrobe 2",
                     "ignore": "retention_analysis", "home": 70}],
         "set": {"name": "set 1", "description": "set 1 of Scene 1", "elements": ["prop 1"], "props": []},
         "style": "style 1"}
W = [f"<d>line l{k} of Scene 1, said by {who} in shot s{k} of Script 1</d>" for k, who in ((1, P1), (2, P2), (3, P1),
                                                                                          (4, P2))]
OPS = [{"op": "add_scene", "title": "Scene 1", "cast": [P1, P2]},
       {"op": "add_shot", "framing": f"Wide shot of {P1} and {P2}", "on": [P1, P2], "action": "action 1"},
       {"op": "add_line", "speaker": P1, "words": W[0]}, {"op": "add_line", "speaker": P2, "words": W[1]},
       {"op": "add_shot", "framing": f"Close-up of {P1}", "on": [P1], "action": "action 2"},
       {"op": "add_line", "speaker": P1, "words": W[2]},
       {"op": "add_shot", "framing": f"Close-up of {P2}", "on": [P2], "action": "action 3"},
       {"op": "add_line", "speaker": P2, "words": W[3]}]


@pytest.fixture(autouse=True)
def clean() -> Iterator[None]:
    for held in (autolock.said, autolock.pending, mix.running, mix.failed, say.handled, say.tasks):
        held.clear()
    yield
    for held in (autolock.said, autolock.pending, mix.running, mix.failed, say.handled, say.tasks):
        held.clear()


def plan(ops: list[dict], title: str | None = None) -> str:
    return json.dumps({**({"title": title} if title else {}), "operations": ops})


async def told(ctx: Any) -> str:
    """The story as the first message of a chat, no `Script:`: Subject 1 has a picture, Subject 2 none; no voice."""
    (ctx.files.roots["chars"] / f"{P1}.png").write_bytes(png_bytes())
    ctx.model = Model(json.dumps(CONTEXT), shot_list(OPS, NAME))
    hub(ctx, STORY, "m1", first=True)
    got = await call(ctx, "script_say", {"words": STORY})
    hub(ctx, None)
    return got["state"][0]


async def say_(ctx: Any, words: str) -> str:
    return (await call(ctx, "script_say", {"words": words}))["state"][0]


async def test_a_story_with_no_length_and_no_picture_or_voice_is_written(mctx: Any) -> None:  # noqa: F811
    line = await told(mctx)
    assert line.startswith(f"{NAME}: wrote 1 scene, 3 shots, 4 lines · runs ") and "asked" not in line, line
    assert "not done" not in line and "voice" not in line and "picture" not in line and not TOOLS.search(line), line
    held = on_disk(mctx, NAME)
    assert [m["name"] for m in held["context"]["cast"]] == [P1, P2] and "seconds" not in held["scenes"][0]
    assert lines(held) == [(P1, W[0]), (P2, W[1]), (P1, W[2]), (P2, W[3])] and held["scenes"][0]["done"] is True
    system = mctx.model.sent[0][0]["content"]
    assert system.startswith("You write the scene context of a story. The story's cast are the people it names")
    assert system.count("picture in Characters: ") == 1 and f"Characters: {P1}." in system, "only the names it names"
    assert mctx.model.schemas[0]["properties"]["cast"]["items"]["properties"]["name"].get("enum") is None
    assert context.picture_use(held["context"]["cast"][0], {P1.casefold()}) == "reference"
    assert context.picture_use(held["context"]["cast"][1], {P1.casefold()}) == "none"


async def test_a_story_with_characters_empty_is_written(mctx: Any) -> None:  # noqa: F811
    for path in mctx.files.roots["chars"].iterdir():
        path.unlink()
    mctx.model = Model(json.dumps(CONTEXT), shot_list(OPS, NAME))
    line = await say_(mctx, STORY)
    assert line.startswith(f"{NAME}: wrote 1 scene") and "not done" not in line, line
    assert "picture in Characters" not in mctx.model.sent[0][0]["content"]


async def test_a_message_naming_nothing_writes_nothing(mctx: Any) -> None:  # noqa: F811
    await told(mctx)
    before = on_disk(mctx, NAME)
    mctx.model = Model(plan([{"op": "remove", "ref": {"speaker": P1, "nth": 1}}]), plan([]))
    line = await say_(mctx, "Script 1.")
    back = mctx.model.sent[1][-1]["content"]
    assert "takes out what the message does not ask to take out" in back, back
    assert line == f"{NAME}: {sayplain.VAGUE}" and on_disk(mctx, NAME) == before


async def test_a_removal_never_asked_is_never_written_at_the_limit(mctx: Any) -> None:  # noqa: F811
    await told(mctx)
    gone = plan([{"op": "remove", "ref": {"speaker": P1, "nth": 1}},
                 {"op": "change_line", "ref": {"speaker": P2, "nth": 1}, "words": "<d>line l5 of Scene 1</d>"}])
    mctx.model = Model(*[gone] * 2)
    line = await say_(mctx, "Scene 1 of Script 1.")
    held = lines(on_disk(mctx, NAME))
    assert (P1, W[0]) in held and len(held) == 4, "no line lost"
    assert "not done: a removal takes out what the message does not ask to take out" in line, line
    assert not TOOLS.search(line.replace("<d>line l5 of Scene 1</d>", "")), line


def test_lines_lost_unasked_are_never_written() -> None:
    two = {"scenes": [{"shots": [{"events": [{"kind": "line"}, {"kind": "line"}]}]}]}
    one = {"scenes": [{"shots": [{"events": [{"kind": "line"}]}]}]}
    assert sayplain.lost(two, one, "Scene 1.") == 1 and sayplain.lost(two, one, "Delete line l1.") == 0
    tried = say.saytrial.Tried(one)
    tried.calls = [("event_remove", {"id": "l1"})]
    assert say._lost(two, tried, "Scene 1.") == [sayplain.lost_line(1)] and tried.calls == []


async def test_a_removal_the_user_asks_for_is_written(mctx: Any) -> None:  # noqa: F811
    await told(mctx)
    mctx.model = Model(plan([{"op": "remove", "ref": {"speaker": P1, "nth": 1}}]))
    line = await say_(mctx, f"Take out {P1}'s first line.")
    assert len(mctx.model.sent) == 1 and line.startswith(f"{NAME}: took out {P1}'s 1st line"), line
    assert (P1, W[0]) not in lines(on_disk(mctx, NAME))


async def test_done_says_every_scene_done_with_no_model_asked(mctx: Any) -> None:  # noqa: F811
    await told(mctx)
    path = mctx.files.roots["scripts"] / f"{NAME}.json"
    held = json.loads(path.read_text())
    held["scenes"][0].pop("done")
    path.write_text(json.dumps(held))
    mctx.model = Model()
    line = await say_(mctx, "Done.")
    assert mctx.model.sent == [] and line.startswith(f"{NAME}: {sayplain.EVERY}"), line
    assert on_disk(mctx, NAME)["scenes"][0]["done"] is True
    assert (await say_(mctx, "The script is finished.")).startswith(f"{NAME}: {sayplain.ALREADY}")


async def test_render_asks_no_model(mctx: Any, monkeypatch: Any) -> None:  # noqa: F811
    from hub.modules.director import render

    await told(mctx)
    pressed: list[str] = []
    monkeypatch.setattr(render, "press", lambda ctx, name: pressed.append(name) or {"job": "j1"})
    monkeypatch.setattr(render, "line", lambda name, got: f"job {got['job']}")
    mctx.model = Model()
    line = await say_(mctx, "render")
    assert pressed == [NAME] and mctx.model.sent == [] and line == f"{NAME}: job j1"


async def test_a_wardrobe_change_goes_through_the_context(mctx: Any) -> None:  # noqa: F811
    await told(mctx)
    worn = f"<{P1}> wardrobe changed"
    mctx.model = Model(plan([{"op": "cast", "name": P1, "costume": worn}]))
    line = await say_(mctx, f"{P1} wardrobe 2.")
    assert "costume: wardrobe 1" in mctx.model.sent[0][0]["content"], "the listing shows the wardrobe to keep"
    assert line == f'{NAME}: changed {P1}: costume "{worn}"', line
    assert on_disk(mctx, NAME)["context"]["cast"][0]["costume"] == worn and len(lines(on_disk(mctx, NAME))) == 4


@pytest.mark.parametrize(("use", "said"), [("reference", f"{P1}'s picture is the reference in every shot"),
                                           ("frame", f"{P1}'s picture is the first frame"),
                                           ("none", f"{P1} is made from the words, not the picture")])
async def test_how_a_picture_is_used_from_plain_words(mctx: Any, use: str, said: str) -> None:  # noqa: F811
    await told(mctx)
    mctx.model = Model(plan([{"op": "picture", "name": P1.lower(), "picture_use": use}]))
    line = await say_(mctx, f"<Picture 1> of {P1}.")
    schema = mctx.model.schemas[0]["properties"]["operations"]["items"]["properties"]
    assert schema["picture_use"]["enum"] == ["reference", "frame", "none"]
    assert line == f"{NAME}: {said}", line
    member = on_disk(mctx, NAME)["context"]["cast"][0]
    assert member["picture_use"] == use and context.picture_use(member, {P1.casefold()}) == use


async def test_a_picture_use_for_no_member_is_sent_back(mctx: Any) -> None:  # noqa: F811
    await told(mctx)
    mctx.model = Model(*[plan([{"op": "picture", "name": P3, "picture_use": "frame"}])] * 2)
    line = await say_(mctx, f"<Picture 1> of {P3}.")
    assert f"{P3} is not in the cast" in mctx.model.sent[1][-1]["content"]
    assert "not done" in line and all("picture_use" not in m for m in on_disk(mctx, NAME)["context"]["cast"])


def test_the_shape_and_the_checks() -> None:
    member = {"name": P1, "picture_use": "frame"}
    assert context.read({"cast": [member]}, ()) == {P1.casefold(): P1}
    with pytest.raises(Invalid) as e:
        context.read({"cast": [{**member, "picture_use": "<Picture 1>"}]}, ())
    assert e.value.text == f"Cast and set, cast {P1}: picture_use is one of reference, frame, none"
    assert context.picture_use(member, ()) == "none" and \
        context.picture_use({"name": P1}, {P1.casefold()}) == "reference"
    assert saycheck.check({"operations": [{"op": "picture", "name": P1}]}, "Script 1.", {"scenes": []}, False)[1] == [
        "operation 1 (picture) needs picture_use"]
    ops = [{"op": "remove", "ref": {"speaker": P1, "nth": 1}}, {"op": "cast", "name": P2, "remove": True}]
    assert saycheck.check({"operations": ops}, "Scene 1.", {"scenes": []}, False)[2] == {1, 2}
    assert saycheck.check({"operations": ops}, f"Remove {P1}'s first line and {P2}.", {"scenes": []}, False)[2] == set()
    assert sayplain.done("Done.") and sayplain.done("ok, the script is finished!") and not sayplain.done("Done in "
                                                                                                         "Scene 1")
    assert sayask.schema([P1], [], False)["properties"]["operations"]["minItems"] == 0
    assert sayask.schema([P1], [], True)["properties"]["operations"]["minItems"] == 1


async def test_a_first_message_telling_a_story_starts_a_script_with_one_open(mctx: Any) -> None:  # noqa: F811
    await told(mctx)
    mctx.model = Model(json.dumps(CONTEXT), shot_list(OPS, NAME))
    hub(mctx, STORY, "m9", first=True)
    line = (await call(mctx, "script_say", {"words": STORY}))["state"][0]
    assert line.startswith(f"{NAME} 2: wrote 1 scene, 3 shots, 4 lines"), line
    assert len(lines(on_disk(mctx, NAME))) == 4 and len(lines(on_disk(mctx, f"{NAME} 2"))) == 4
