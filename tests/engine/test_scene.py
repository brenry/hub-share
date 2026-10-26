"""The 30 s scene with a fake ask. `direct_scene` queues one job with no task; its planning step
asks for the whole scene once, checks it (schema, the scene's rules, every merged shot as one shot is checked), sends
a refusal back with its shot named, and builds every shot's press in order then the cut: one model, the step names,
the join reading each shot's last task as "kept" with the shots' planned frames. The whole cast is cast at
once; a shot sends only its own subjects' boxes; the set is in every prompt word for word. `finish` writes the
shots made, in order, to a sequence named by the title. Nothing of the request, the replies or the plan is on disk.
The catalog is the worker's own for upstream's H3 capture (`test_upstream_rules`)."""
from __future__ import annotations

import json
import re
from typing import Any

import pytest
from PIL import Image

from hub.core.api import Invalid
from hub.modules.generate_image import build, director, routes, scene, takes
from tests.engine.test_director import Model
from tests.engine.test_generate_image import call
from tests.engine.test_shotprompt import ctx, pick  # noqa: F401
from tests.engine.test_upstream_rules import REF2VA, cat  # noqa: F401
from tests.engine.test_voice_reference import sample
from tests.fakes.mp4 import tiny_mp4

REQUEST = ("Character 7 faces the audience. Character 7 brings out Character 6. Character 6 answers. "
           "Character 7 closes. About 30 seconds.")
WHERE = "A brightly lit hall, a blue curtain behind the stage"


def beat(*names: str, speaker: str | None = None, words: str = "", seconds: float = 6) -> dict:
    out: dict = {"subjects": [{"name": n} for n in names], "camera": {"framing": "medium shot"},
                 "action": [f"{names[0]} turns to the room"], "seconds": seconds}
    if speaker:
        out["lines"] = [{"speaker": speaker, "words": words}]
    return out


def plan(*shots: dict, **extra: Any) -> dict:
    return {"title": "Script 1", "cast": [{"name": "Character 7", "look": "in a grey suit"},
                                               {"name": "Character 6", "look": "in a red dress"}],
            "set": {"where": WHERE, "light": "hot stage lights", "ambience": "a large hall"},
            "shots": list(shots), **extra}


GOOD = plan(beat("Character 7", speaker="Character 7", words="Line one, everybody."),
            beat("Character 6", speaker="Character 6", words="Thank you, friend. It is good to be here."),
            beat("Character 7", "Character 6", speaker="Character 7", words="That is our scene."))


@pytest.fixture
def cast3(ctx):  # noqa: F811
    """Character 6 beside Character 7 and Character 16 in Characters; one take a shot."""
    Image.new("RGB", (600, 900)).save(ctx.files.existing_media("chars/Character 7.png").with_name("Character 6.png"))
    ctx.settings["scene_takes_max"] = 1
    return ctx


async def planned(ctx: Any, *replies: str) -> tuple[Any, Model, list[str]]:  # noqa: F811
    """`direct_scene` then the job's planning step, as the dispatcher runs it: -> (the job, the model, the lines)."""
    await call(ctx, "set_generate_image_settings", {"seed": "41"})
    model, lines = Model(*replies), []
    ctx.offer("ask", model)
    answer = await call(ctx, "direct_scene", {"request": REQUEST})
    [(job, params)] = ctx.jobs.jobs.values()
    assert answer == {"state": "queued", "job": job.id} and params == {"scene": REQUEST}
    assert job.plan.tasks == () and job.plan.summary["mode"] == "scene" and job.plan.prepare.job == job.id
    job.plan = await job.plan.prepare(lines.append)
    return job, model, lines


def refused(model: Model, n: int) -> str:
    return model.sent[n][-1]["content"]


async def test_a_three_shot_scene_on_ask_1_is_three_clips_then_the_cut(cast3):
    pick(cast3, REF2VA)                                                 # every box empty: the cast is cast by name
    job, model, lines = await planned(cast3, json.dumps(GOOD))
    p = job.plan
    assert lines == ["Planning scene · ask 1 · qwen3.5:9b"] and len(model.sent) == 1
    assert [t["kind"] for t in p.tasks] == ["video", "video", "video", "join"] and p.model == REF2VA
    assert all(t["model"] == REF2VA for t in p.tasks[:3]), "one model: the lane loads it once"
    fps = 24.0
    names = [f"Shot {k} · {who} · {t['frames'] / fps:.1f} s"
             for k, who, t in zip((1, 2, 3), ("Character 7", "Character 6", "Character 7"), p.tasks[:3], strict=True)]
    assert p.summary["step_names"] == [*names, "Cut"] and p.summary["shots"] == 3
    assert p.inputs == ({}, {}, {}, {"items.0.path": (1, "kept"), "items.1.path": (2, "kept"),
                                     "items.2.path": (3, "kept")})
    cut = p.tasks[3]
    assert [i["frames"] for i in cut["items"]] == [t["frames"] for t in p.tasks[:3]], "the shots' planned frames"
    assert [(i["path"], i["in"], i["out"], i["audio"], i["sound"]) for i in cut["items"]] == [
        ("", 0, t["frames"], True, False) for t in p.tasks[:3]]
    assert cut["canvas"] == {"w": p.tasks[0]["size"][0], "h": p.tasks[0]["size"][1], "fps": fps}
    assert (cut["out_kind"], cut["audio"], cut["crf"], cut["preset"]) == ("mp4", [], 18, "medium")
    assert p.finish is not None and p.prepare is None


async def test_the_cast_is_boxed_first_and_each_shot_sends_its_own_boxes(cast3):
    pick(cast3, REF2VA)
    job, _, _ = await planned(cast3, json.dumps(GOOD))
    boxed = [r["id"] for r in routes.session_part(cast3)["references"]]
    assert boxed == ["chars/Character 7.png", "chars/Character 6.png"], "the whole cast, in cast order, before shot 1"
    one, two, three = job.plan.tasks[:3]
    pictures = [[r["path"].rsplit("/", 1)[-1] for r in t["references"]] for t in (one, two, three)]
    assert pictures == [["Character 7.png"], ["Character 6.png"], ["Character 7.png", "Character 6.png"]]
    assert two["prompt"].startswith("subject_definitions: <Subject 1> is Character 6, from <Picture 1>.")
    assert "<Subject 2>" not in two["prompt"] and "<Subject 2> is Character 6" in three["prompt"]
    for t in (one, two, three):
        assert WHERE in t["prompt"] and "in a red dress" not in one["prompt"], "the set word for word"
    assert "in a red dress" in two["prompt"] and "in a grey suit" in three["prompt"], "the cast's looks"


async def test_the_users_own_box_goes_with_every_shot(cast3):
    pick(cast3, REF2VA, {"id": "chars/Character 16.png", "w": 600, "h": 900})  # box 1 filled
    good = plan(*[{**s, "subjects": [*s["subjects"], {"name": "Character 16"}]} for s in GOOD["shots"]],
                cast=[*GOOD["cast"], {"name": "Character 16"}])
    job, _, _ = await planned(cast3, json.dumps(good))
    two = job.plan.tasks[1]
    assert [r["path"].rsplit("/", 1)[-1] for r in two["references"]] == ["Character 16.png", "Character 6.png"]


async def test_a_shot_with_two_speakers_is_sent_back_and_ask_2_is_accepted(cast3):
    pick(cast3, REF2VA)
    two = plan(GOOD["shots"][0], {**beat("Character 7", "Character 6"), "lines": [
        {"speaker": "Character 7", "words": "Character 6!"}, {"speaker": "Character 6", "words": "Character 7!"}]},
        GOOD["shots"][2])
    job, model, lines = await planned(cast3, json.dumps(two), json.dumps(GOOD))
    assert refused(model, 1) == ("The Hub refused that scene: shot 2 has two speakers; one speaker per shot. Send "
                                 "the whole scene again as one JSON object, changed only where needed.")
    assert model.sent[1][2] == {"role": "assistant", "content": json.dumps(two)}
    assert lines[1] == ("Planning scene · fixing: shot 2 has two speakers; one speaker per shot · ask 2 · "
                        "qwen3.5:9b")
    assert len(job.plan.tasks) == 4


async def test_a_shot_over_one_pass_is_sent_back_naming_the_shot(cast3):
    pick(cast3, REF2VA)
    long = plan(*GOOD["shots"][:2], beat("Character 7", speaker="Character 7", words=" ".join(["word"] * 40) + "."))
    _, model, _ = await planned(cast3, json.dumps(long), json.dumps(GOOD))
    assert refused(model, 1).startswith("The Hub refused that scene: shot 3: The lines need 18.0 s and one clip holds "
                                        "15.1 s: cut 8 words.")


@pytest.mark.parametrize("bad, line", [
    (plan(GOOD["shots"][0], beat("The audience")), "shot 2 shows none of the cast"),
    (plan(GOOD["shots"][0], beat("Character 7", "The audience")), "shot 2: The audience is not in the cast"),
    (plan(*GOOD["shots"], cast=[{"name": "Character 4"}]), "Character 4 is not in Characters"),
    (plan(), "shots has the wrong number of items"),                     # one at least, no most
    (plan(*GOOD["shots"], title="a/b"), scene.PLAIN),
])
async def test_the_scenes_own_rules_refuse(cast3, bad, line):
    pick(cast3, REF2VA)
    _, model, lines = await planned(cast3, json.dumps(bad), json.dumps(GOOD))
    assert refused(model, 1).startswith(f"The Hub refused that scene: {line}"), refused(model, 1)


async def test_a_scene_past_sixty_seconds_is_planned(cast3):
    pick(cast3, REF2VA)
    long = plan(*[beat("Character 7", seconds=13)] * 5)                        # 65 s: no most seconds
    job, model, lines = await planned(cast3, json.dumps(long))
    assert len(model.sent) == 1, lines
    assert [t["kind"] for t in job.plan.tasks] == ["video"] * 5 + ["join"]


async def test_three_refusals_fail_in_one_line_and_nothing_is_planned(cast3):
    pick(cast3, REF2VA)
    bad = json.dumps(plan(GOOD["shots"][0], beat("The audience")))
    with pytest.raises(Invalid) as err:
        await planned(cast3, "No.", bad, bad)
    assert err.value.text == "Planning: refused 2 times; last: shot 2 shows none of the cast", "the last refusal named"
    assert cast3.engine.planned == [], "nothing asked of the engine"


async def test_on_convert_a_voiced_shot_brings_its_voice_and_the_join_reads_it(cast3):
    sample(cast3, "Character 6")                                         # the default route: convert
    pick(cast3, REF2VA)
    job, _, _ = await planned(cast3, json.dumps(GOOD))
    p = job.plan
    assert [t["kind"] for t in p.tasks] == ["video", "video", "voice", "video", "join"]
    assert p.inputs[2] == {"clip": (2, "file")} and p.tasks[2]["clip"] == ""
    assert p.inputs[4] == {"items.0.path": (1, "kept"), "items.1.path": (3, "kept"), "items.2.path": (4, "kept")}
    assert p.summary["step_names"][1:3] == [p.summary["step_names"][1], "Shot 2 · voice"]
    assert p.summary["step_names"][1].startswith("Shot 2 · Character 6 · ")


async def test_a_preflight_refusal_on_shot_2_fails_at_once_naming_it(cast3, monkeypatch):
    pick(cast3, REF2VA)
    real, asked = build.preflight, []

    async def refusing(c: Any, plan: Any) -> tuple[Any, Any]:
        asked.append(plan)
        planned_, line = await real(c, plan)
        return planned_, "Window 2 is past the model's end" if len(asked) == 2 else line
    monkeypatch.setattr(build, "preflight", refusing)
    with pytest.raises(Invalid) as err:
        await planned(cast3, json.dumps(GOOD))
    assert err.value.text == "shot 2: Window 2 is past the model's end" and len(asked) == 2


def clips(c: Any, n: int) -> list[str]:
    folder = c.files.roots["clips"] / "2026-10-18"
    folder.mkdir(parents=True, exist_ok=True)
    for k in range(1, n + 1):
        (folder / f"shot-{k}.mp4").write_bytes(tiny_mp4(audio=True))
    return [f"clips/2026-10-18/shot-{k}.mp4" for k in range(1, n + 1)]


async def test_finish_writes_the_title_then_the_next_free_name_with_the_shots_in_order(cast3):
    pick(cast3, REF2VA)
    job, _, _ = await planned(cast3, json.dumps(GOOD))
    made = clips(cast3, 4)
    await job.plan.finish({1: made[0], 2: made[1], 3: made[2], 4: made[3]})
    seq = cast3.files.sequence("Script 1")
    assert seq["tracks"] == [[{"clip": c, "in": 0, "out": 124} for c in made[:3]], []], "the cut is not a shot"
    await job.plan.finish({1: made[0], 2: made[1]})                    # a failure after shot 2: the two made
    assert [i["clip"] for i in cast3.files.sequence("Script 1 2")["tracks"][0]] == made[:2]
    assert [e for e in cast3.events if e[0] != "sketch.ready"] == [          # Generate's own event
        ("sequence.written", {"name": "Script 1", "revision": 1}),
        ("sequence.written", {"name": "Script 1 2", "revision": 1})]
    await job.plan.finish({})
    assert len(cast3.files.sequences()) == 2, "none made: none written"


async def test_takes_leave_a_scene_alone(cast3):
    pick(cast3, REF2VA)
    job, _, _ = await planned(cast3, json.dumps(GOOD))
    assert job.id not in (routes.session_part(cast3).get("takes") or {}), "remember is not called"
    await takes.on_clip_finished(cast3, job, {"outputs": clips(cast3, 1), "notes": {}})
    assert "last_take" not in routes.session_part(cast3)


async def test_the_message_holds_the_scene_schema_and_one_shots_budget(cast3):
    pick(cast3, REF2VA)
    _, model, _ = await planned(cast3, json.dumps(GOOD))
    system, user = model.sent[0]
    assert user == {"role": "user", "content": f"Scene plan: {REQUEST}"}, "not Scene:"
    text = system["content"]
    assert text.startswith("You plan a scene of shots of a video for the Hub, cut together in order.")
    assert json.dumps(scene.SCHEMA, separators=(",", ":")) in text
    assert "Characters (use these exact names for them): Character 16; Character 6; Character 7." in text
    assert "at most 31 words and 4 of . ! ? ; : (another mark 1 word)" in text
    assert "at most 15.1; the shots together run as long as the request asks. Each shot" in text
    assert "seconds in all" not in text, "no most seconds for a Scene: request"
    assert "about 30" not in text
    assert "look" not in json.dumps(scene.SCHEMA["properties"]["shots"]["items"]["properties"]["subjects"])
    assert director.PLAN["properties"]["subjects"]["items"]["properties"]["look"], "director.PLAN is untouched"


async def test_nothing_of_the_request_the_replies_or_the_plan_is_on_disk(cast3, tmp_path):
    pick(cast3, REF2VA)
    bad = json.dumps(plan(GOOD["shots"][0], beat("The audience")))
    job, _, _ = await planned(cast3, bad, json.dumps(GOOD))
    await job.plan.finish(dict(enumerate(clips(cast3, 3), 1)))
    words = ("Line one", "good to be here", "grey suit", "red dress", "blue curtain", "Scene plan", "audience")
    for path in (p for p in tmp_path.rglob("*") if p.is_file()):
        data = path.read_bytes()
        assert not any(w.encode() in data for w in words), path
    for name, doc in cast3.docs.items():
        assert not any(w in json.dumps(doc.value) for w in words), name
    written = [p for p in tmp_path.rglob("*.json") if "sequences" in p.parts]
    assert [p.name for p in written] == ["Script 1.json"], "the only file the scene writes"
    assert re.search(r"shot-1\.mp4", written[0].read_text())


async def test_every_ask_of_a_scene_plan_carries_the_scene_schema(cast3):
    pick(cast3, REF2VA)
    two = plan(GOOD["shots"][0], {**beat("Character 7", "Character 6"), "lines": [
        {"speaker": "Character 7", "words": "Character 6!"}, {"speaker": "Character 6", "words": "Character 7!"}]},
        GOOD["shots"][2])
    _, model, _ = await planned(cast3, json.dumps(two), json.dumps(GOOD))
    assert len(model.schemas) == 2 and all(s is scene.SCHEMA for s in model.schemas), "the first and the send-back"


def _one(c: Any) -> dict:
    """Character 1 in Characters, and a scene of Character 1 alone with only a name and a place."""
    Image.new("RGB", (600, 900)).save(c.files.roots["chars"] / "Character 1.png")
    return {"title": "Script 1", "cast": [{"name": "Character 1"}], "set": {"where": "Place 1"}}


@pytest.mark.parametrize("count", [1, 9])
async def test_a_one_shot_scene_and_a_nine_shot_scene_are_planned(cast3, count):  # noqa: F811
    pick(cast3, REF2VA)
    planned_scene = {**_one(cast3), "shots": [beat("Character 1", seconds=6)] * count}
    job, model, lines = await planned(cast3, json.dumps(planned_scene))
    assert len(model.sent) == 1 and lines == ["Planning scene · ask 1 · qwen3.5:9b"]
    assert [t["kind"] for t in job.plan.tasks].count("video") == count, "no shot range of the Hub's"


async def test_the_message_names_no_shot_range_no_length_and_no_language(cast3):  # noqa: F811
    pick(cast3, REF2VA)
    _, model, _ = await planned(cast3, json.dumps(GOOD))
    text = model.sent[0][0]["content"]
    assert "2 to 8" not in text and "about 30" not in text and "English" not in text and "stage only" not in text
    assert "language: only a language the request names." in text
    assert "with how each looks where the request says" in text
    shots = scene.SCHEMA["properties"]["shots"]
    assert "maxItems" not in shots and shots["minItems"] == 1
