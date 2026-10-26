"""`jobgraph`: the inputs of a job of steps, checked at submit and filled as each task starts."""
from __future__ import annotations

import pytest

from hub.core import jobgraph
from hub.core.api import Invalid, JobPlan
from hub.core.supervisor import EngineFailed
from hub.worker import engineapi, enginewire

CLIP = enginewire.request_wire(engineapi.ClipRequest("m", "a shot", (960, 544), 7, 124))
VOICE = enginewire.request_wire(engineapi.VoiceRequest("", "/chars/Character 7.wav", 7))


def plan(*inputs: dict, tasks: tuple = (CLIP, VOICE)) -> JobPlan:
    return JobPlan("image", "m", tasks, {}, inputs=inputs)


def test_a_voice_step_reading_the_render_passes():
    jobgraph.check(plan({}, {"clip": (1, "file")}))
    assert jobgraph.between(plan({}, {"clip": (1, "file")})) == {1}


def test_no_inputs_is_no_graph():
    jobgraph.check(plan())
    assert jobgraph.between(plan()) == set()


@pytest.mark.parametrize("inputs, words", [
    (({"clip": (2, "file")}, {}), "not before it"),                      # a later source
    (({}, {"clip": (2, "file")}), "not before it"),                      # itself
    (({}, {"clip": (0, "file")}), "not before it"),
    (({}, {"film": (1, "file")}), "no text field film"),                 # an unknown field
    (({}, {"seed": (1, "file")}), "no text field seed"),                 # not a text field
    (({}, {"clip": (1, "verdict")}), "names no earlier step's file"),    # not something a step makes yet
])
def test_check_refuses(inputs, words):
    with pytest.raises(Invalid) as err:
        jobgraph.check(plan(*inputs))
    assert words in err.value.text and err.value.field == "params"


def test_check_refuses_a_field_sent_filled():
    filled = enginewire.request_wire(engineapi.VoiceRequest("/clips/x.mp4", "/chars/Character 7.wav", 7))
    with pytest.raises(Invalid, match="sent empty"):
        jobgraph.check(plan({}, {"clip": (1, "file")}, tasks=(CLIP, filled)))


def test_check_refuses_a_length_mismatch():
    with pytest.raises(Invalid, match="Inputs name 1 steps; the job has 2"):
        jobgraph.check(plan({"clip": (1, "file")}))


def test_fill_sets_the_path_and_leaves_the_rest():
    got = jobgraph.fill(VOICE, {"clip": (1, "file")}, {1: "/data/clips/2026-10-18/a.mp4"}, 2)
    assert got == {**VOICE, "clip": "/data/clips/2026-10-18/a.mp4"} and VOICE["clip"] == ""


def test_fill_without_inputs_is_the_task_as_sent():
    assert jobgraph.fill(CLIP, {}, {}, 1) is CLIP


def test_fill_from_a_step_that_made_nothing_fails():
    with pytest.raises(EngineFailed, match="Step 2 has nothing from step 1"):
        jobgraph.fill(VOICE, {"clip": (1, "file")}, {1: None}, 2)


# a shot's file is kept ("kept"); a join's item path is a field an earlier step fills.
JOIN = enginewire.request_wire(engineapi.JoinRequest(
    [engineapi.JoinItem("", 0, 124, 24.0, 960, 544, 124, True),
     engineapi.JoinItem("", 0, 98, 24.0, 960, 544, 98, True)],
    engineapi.Canvas(960, 544, 24.0), [], 18, "medium"))


def scene(*inputs: dict, join: dict = JOIN) -> JobPlan:
    return JobPlan("image", "m", (CLIP, CLIP, join), {}, inputs=inputs)


def test_kept_is_checked_and_filled_like_file_and_is_not_between():
    p = scene({}, {}, {"items.0.path": (1, "kept"), "items.1.path": (2, "kept")})
    jobgraph.check(p)
    assert jobgraph.between(p) == set(), "the kept shots land as they are made"
    got = jobgraph.fill(JOIN, p.inputs[2], {1: "/data/clips/a.mp4", 2: "/data/clips/b.mp4"}, 3)
    assert [i["path"] for i in got["items"]] == ["/data/clips/a.mp4", "/data/clips/b.mp4"]
    assert [i["path"] for i in JOIN["items"]] == ["", ""], "the plan's request is not touched"
    assert jobgraph.named(p.inputs[2]) == {0, 1} and jobgraph.named({"clip": (1, "file")}) == set()


def test_a_voice_render_stays_between_beside_a_kept_shot():
    p = JobPlan("image", "m", (CLIP, VOICE, JOIN), {}, inputs=(
        {}, {"clip": (1, "file")}, {"items.0.path": (2, "kept"), "items.1.path": (2, "kept")}))
    jobgraph.check(p)
    assert jobgraph.between(p) == {1}


@pytest.mark.parametrize("inputs, words", [
    ({"items.2.path": (1, "kept")}, "Step 3 has no item 2"),             # a bad index
    ({"items.x.path": (1, "kept")}, "Step 3 has no text field items.x.path"),
    ({"items.0.path": (3, "kept")}, "not before it"),
])
def test_an_item_field_is_refused_in_one_line(inputs, words):
    with pytest.raises(Invalid) as err:
        jobgraph.check(scene({}, {}, inputs))
    assert words in err.value.text and "\n" not in err.value.text


def test_an_item_field_on_a_request_without_items_is_refused():
    with pytest.raises(Invalid, match="Step 2 has no item 0"):
        jobgraph.check(plan({}, {"items.0.path": (1, "kept")}))


def test_an_item_sent_filled_is_refused():
    filled = {**JOIN, "items": [{**JOIN["items"][0], "path": "/x.mp4"}, JOIN["items"][1]]}
    with pytest.raises(Invalid, match="sent empty"):
        jobgraph.check(scene({}, {}, {"items.0.path": (1, "kept")}, join=filled))


def test_the_workers_parse_accepts_an_empty_path_only_where_named():
    from hub.core import enginelane
    from hub.core.api import Job

    named = scene({}, {}, {"items.0.path": (1, "kept"), "items.1.path": (2, "kept")})
    enginelane.checked(Job("j", "gen.image", "gen", "queued", named))
    half = scene({}, {}, {"items.0.path": (1, "kept")})
    with pytest.raises(EngineFailed, match=r"Task 3 is not a request the engine takes: request.items\[1\].path: empty"):
        enginelane.checked(Job("j", "gen.image", "gen", "queued", half))
    with pytest.raises(EngineFailed, match=r"request.items\[0\].path: empty"):
        enginelane.checked(Job("j", "gen.image", "gen", "queued", JobPlan("image", "m", (JOIN,), {})))


# a join's track-2 sound made by an earlier step: `audio.<i>.path`, checked and filled like an item.
SOUND = enginewire.request_wire(engineapi.SoundRequest("speech", "a crowd laughs", 7, 4))
CUT = {**JOIN, "audio": [enginewire.wire(engineapi.JoinSound("/kept/applause.wav", 0, 0, 4000, 1000.0, duck=True)),
                         enginewire.wire(engineapi.JoinSound("", 3000, 0, 4000, 1000.0, duck=True))]}


def test_an_audio_path_is_checked_and_filled_like_an_item_path():
    p = JobPlan("image", "m", (SOUND, CLIP, CLIP, CUT), {}, inputs=(
        {}, {}, {}, {"items.0.path": (2, "kept"), "items.1.path": (3, "kept"), "audio.1.path": (1, "kept")}))
    jobgraph.check(p)
    assert jobgraph.between(p) == set(), "the made sound lands in Sounds as it is made"
    got = jobgraph.fill(CUT, p.inputs[3], {1: "/data/sounds/s.wav", 2: "/c/a.mp4", 3: "/c/b.mp4"}, 4)
    assert [a["path"] for a in got["audio"]] == ["/kept/applause.wav", "/data/sounds/s.wav"]
    assert [i["path"] for i in got["items"]] == ["/c/a.mp4", "/c/b.mp4"]
    assert CUT["audio"][1]["path"] == "", "the plan's request is not touched"
    assert jobgraph.named(p.inputs[3], "audio") == {1} and jobgraph.named(p.inputs[3]) == {0, 1}


@pytest.mark.parametrize("inputs, words", [
    ({"audio.2.path": (1, "kept")}, "Step 4 has no item 2"),
    ({"audio.0.path": (1, "kept")}, "Step 4's audio.0.path is filled by step 1; it is sent empty"),
])
def test_an_audio_field_is_refused_in_one_line(inputs, words):
    p = JobPlan("image", "m", (SOUND, CLIP, CLIP, CUT), {}, inputs=(
        {}, {}, {}, {"items.0.path": (2, "kept"), "items.1.path": (3, "kept"), **inputs}))
    with pytest.raises(Invalid) as err:
        jobgraph.check(p)
    assert words in err.value.text


def test_the_workers_parse_accepts_an_empty_sound_path_only_where_named():
    from hub.core import enginelane
    from hub.core.api import Job

    items = {"items.0.path": (2, "kept"), "items.1.path": (3, "kept")}
    sound = {**items, "audio.1.path": (1, "kept")}
    named = JobPlan("image", "m", (SOUND, CLIP, CLIP, CUT), {}, inputs=({}, {}, {}, sound))
    enginelane.checked(Job("j", "gen.image", "gen", "queued", named))
    unnamed = JobPlan("image", "m", (SOUND, CLIP, CLIP, CUT), {}, inputs=({}, {}, {}, items))
    with pytest.raises(EngineFailed, match=r"request.audio\[1\].path: empty"):
        enginelane.checked(Job("j", "gen.image", "gen", "queued", unnamed))
