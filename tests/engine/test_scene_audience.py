"""The scene's audience as sound, with a fake ask and the worker's own catalog for upstream's
H3 capture. A shot's `reaction` is the scene's: the shot check never sees it and no shot prompt names it. A kind kept
in `sounds/audience/` is used as it is; one missing is made by a sound task before the first shot, on the catalog's
sound model, and filed under its kind when the job ends. The join's track 2 holds every reaction ducked, at the cut
after its shot (the last one ending with the file). A plan without a reaction is the golden one, byte for byte. The room
is heard, never written: an audience word in any field but `lines` is sent back naming the shot. No sound and no
sound model: the job fails at planning in one line, nothing asked of the engine."""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from hub.core.api import Invalid
from hub.modules.generate_image import audience, director, models, scene, tools
from hub.worker import engineapi, enginewire
from tests.engine.test_scene import GOOD, beat, cast3, clips, plan, planned  # noqa: F401
from tests.engine.test_shotprompt import ctx, pick  # noqa: F401
from tests.engine.test_upstream_rules import REF2VA, SPEECH, cat  # noqa: F401
from tests.fakes.wav import tiny_wav

FPS = 24.0
REACTING = plan({**GOOD["shots"][0], "reaction": "applause"}, GOOD["shots"][1],
                {**GOOD["shots"][2], "reaction": "laughter"})
KIND_WORDS = ("applause", "laughter", "gasps", "audience", "crowd", "cheer", "clap")


def test_the_reaction_sound_is_its_kind_alone() -> None:
    """Each kind's prompt is the engine's six labels, the kind under `overall_soundscape`, `N/A` in
    every other field; no other word."""
    labels = ("subject_definitions", "summary", "retention_analysis", "detailed_description", "overall_soundscape",
              "non_diegetic_music")
    for kind in audience.KINDS:
        rows = audience.prompt(kind).split("\n")
        assert rows[0::2] == [f"{label}:" for label in labels]
        assert rows[1::2] == ["N/A"] * 4 + [kind, "N/A"]


def keep(c: Any, kind: str, seconds: float = 6.0) -> str:
    """A sound already kept as the audience's `kind`."""
    folder = c.files.roots["sounds"] / "audience"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{kind}.wav").write_bytes(tiny_wav(seconds, rate=8000))
    return f"sounds/audience/{kind}.wav"


async def test_a_kept_applause_and_a_made_laughter_go_under_the_cut(cast3, monkeypatch):  # noqa: F811
    pick(cast3, REF2VA)
    keep(cast3, "applause")
    seen: list[dict] = []
    real = tools.write_settings

    async def watched(c: Any, args: dict) -> Any:
        seen.append(copy.deepcopy(args.get("shot") or {}))
        return await real(c, args)
    monkeypatch.setattr(tools, "write_settings", watched)
    job, _, _ = await planned(cast3, json.dumps(REACTING))
    p = job.plan
    assert [t["kind"] for t in p.tasks] == ["sound", "video", "video", "video", "join"]
    made = p.tasks[0]
    assert (made["model"], made["seconds"]) == (SPEECH, 4) and made["prompt"] == audience.prompt("laughter")
    assert all("reaction" not in s for s in seen), "the shot check never sees the reaction"
    names = p.summary["step_names"]
    assert names[0] == "Audience · laughter" and names[1].startswith("Shot 1 · Character 7 · ")
    assert names[-1] == "Cut · 2 reactions" and len(names) == 5
    frames = [t["frames"] for t in p.tasks[1:4]]
    end = round(1000 * sum(frames) / FPS)
    cut = p.tasks[4]
    applause, laughter = cut["audio"]
    assert applause == {"path": str(cast3.files.resolve("sounds/audience/applause.wav")),
                        "at_ms": round(1000 * frames[0] / FPS), "in": 0, "out": 4000, "fps": 1000.0,
                        "level": 0.6, "fade_in": 100, "fade_out": 1000, "duck": True}
    assert laughter == {"path": "", "at_ms": end - 4000, "in": 0, "out": 4000, "fps": 1000.0, "level": 0.6,
                        "fade_in": 100, "fade_out": 1000, "duck": True}, "the last shot's reaction ends with the file"
    assert cut["duck"] == {"threshold": 0.05, "ratio": 6.0, "attack": 50.0, "release": 400.0}
    assert p.inputs == ({}, {}, {}, {}, {"items.0.path": (2, "kept"), "items.1.path": (3, "kept"),
                                         "items.2.path": (4, "kept"), "audio.1.path": (1, "kept")})
    for t in p.tasks[1:4]:
        assert not any(w in t["prompt"].lower() for w in KIND_WORDS), t["prompt"]   # the reaction is not asked for
    enginewire.request_parse(made)
    assert isinstance(enginewire.request_parse(made), engineapi.SoundRequest)


async def test_a_plan_without_a_reaction_is_the_golden_plan_byte_for_byte(cast3, tmp_path):  # noqa: F811
    """`scene-plan.json`, the golden plan of a scene without a reaction: each clip task with its `words` and its
    `prompt` (no sentence of the Hub's, no capitals, no `[English]`), the plan with its `takes`."""
    pick(cast3, REF2VA)
    job, _, _ = await planned(cast3, json.dumps(GOOD))
    p = job.plan
    text = json.dumps({"tasks": p.tasks, "inputs": [{k: list(v) for k, v in i.items()} for i in p.inputs],
                       "summary": p.summary, "takes": p.takes}, sort_keys=True, indent=1).replace(str(tmp_path), "TMP")
    assert text + "\n" == (Path(__file__).parents[1] / "fixtures" / "scene-plan.json").read_text(encoding="utf-8")
    assert p.summary["step_names"][-1] == "Cut" and p.tasks[3]["audio"] == []


async def test_every_kept_sound_makes_nothing(cast3):  # noqa: F811
    pick(cast3, REF2VA)
    keep(cast3, "applause")
    keep(cast3, "laughter", 2.5)
    job, _, _ = await planned(cast3, json.dumps(REACTING))
    p = job.plan
    assert [t["kind"] for t in p.tasks] == ["video", "video", "video", "join"]
    _, laughter = p.tasks[3]["audio"]
    end = round(1000 * sum(t["frames"] for t in p.tasks[:3]) / FPS)
    assert (laughter["out"], laughter["at_ms"]) == (2500, end - 2500), "a kept sound's own length"
    assert "audio.1.path" not in p.inputs[3] and p.summary["step_names"][-1] == "Cut · 2 reactions"


@pytest.mark.parametrize("field, value", [
    ("action", ["Character 7 turns to the crowd"]),
    ("camera", {"framing": "wide shot over the crowd"}),
])
async def test_an_audience_word_in_a_shot_is_accepted_and_sent_as_written(cast3, field, value):  # noqa
    pick(cast3, REF2VA)
    written = plan(GOOD["shots"][0], {**GOOD["shots"][1], field: value}, GOOD["shots"][2])
    job, model, _ = await planned(cast3, json.dumps(written))
    assert len(model.sent) == 1, "no word is refused"
    prompt = job.plan.tasks[1]["prompt"]
    assert "the crowd" in prompt and "Only this explicitly tagged line" not in prompt, "no guard"
    assert "overall_soundscape: a large hall.\n" in prompt, "the set's ambience as written"


async def test_a_quiet_ambience_is_sent_as_written(cast3):  # noqa: F811
    pick(cast3, REF2VA)
    quiet = plan(*GOOD["shots"], set={"where": "a hall", "ambience": "a humming air vent"})
    job, _, _ = await planned(cast3, json.dumps(quiet))
    assert "overall_soundscape: a humming air vent.\n" in job.plan.tasks[0]["prompt"]


async def test_an_ambience_that_is_the_audiences_sound_is_sent_as_written(cast3):  # noqa: F811
    pick(cast3, REF2VA)
    cheering = plan(*GOOD["shots"], set={"where": "a hall", "ambience": "a cheering audience"})
    job, model, _ = await planned(cast3, json.dumps(cheering))
    assert len(model.sent) == 1
    assert all("overall_soundscape: a cheering audience.\n" in t["prompt"] for t in job.plan.tasks[:3]), \
        "the ambience as written, nothing dropped"


async def test_character_6_laughs_and_applause_in_lines_are_accepted(cast3):  # noqa: F811
    pick(cast3, REF2VA)
    keep(cast3, "laughter")
    fine = plan({**GOOD["shots"][0], "lines": [{"speaker": "Character 7", "words": "Give them a round of applause!"}]},
                {**GOOD["shots"][1], "action": ["Character 6 laughs"], "reaction": "laughter"}, GOOD["shots"][2])
    job, model, _ = await planned(cast3, json.dumps(fine))
    assert len(model.sent) == 1 and job.plan.tasks[-1]["audio"][0]["at_ms"] == round(
        1000 * sum(t["frames"] for t in job.plan.tasks[:2]) / FPS), "at the cut after shot 2"


async def test_no_sound_and_no_sound_model_fails_at_planning(cast3, cat, monkeypatch):  # noqa: F811
    pick(cast3, REF2VA)
    bare = copy.deepcopy(cat)
    for m in bare["models"]:
        m.pop("sounds", None)
    cast3.engine.catalog = bare
    monkeypatch.setattr(models, "_last", bare)
    with pytest.raises(Invalid) as err:
        await planned(cast3, json.dumps(REACTING))
    assert err.value.text == ("Audience: no applause sound: none kept as audience in Sounds, and no sound model in "
                              "the catalog")
    assert cast3.engine.planned == [], "nothing asked of the engine"


def sound_landed(c: Any) -> str:
    folder = c.files.roots["sounds"] / "2026-10-18"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "120000-000.wav").write_bytes(tiny_wav(4.0, rate=8000))
    return "sounds/2026-10-18/120000-000.wav"


async def test_finish_files_the_made_sound_and_writes_both_reactions(cast3):  # noqa: F811
    pick(cast3, REF2VA)
    keep(cast3, "applause")
    job, _, _ = await planned(cast3, json.dumps(REACTING))
    made, made_sound = clips(cast3, 4), sound_landed(cast3)
    await job.plan.finish({1: made_sound, 2: made[0], 3: made[1], 4: made[2], 5: made[3]})
    assert cast3.files.sound_facts("sounds/audience/laughter.wav") == {"seconds": 4.0}
    assert not (cast3.files.roots["sounds"] / "2026-10-18" / "120000-000.wav").exists()
    seq = cast3.files.sequence("Script 1")
    at = [a["at_ms"] for a in job.plan.tasks[4]["audio"]]
    keys = {"level": 0.6, "fade_in": 100, "fade_out": 1000, "duck": True}
    assert seq["tracks"][1] == [{"sound": "sounds/audience/applause.wav", "in": 0, "out": 4000, "at": at[0], **keys},
                                {"sound": "sounds/audience/laughter.wav", "in": 0, "out": 4000, "at": at[1], **keys}]
    assert [i["clip"] for i in seq["tracks"][0]] == made[:3]


async def test_a_failure_after_shot_1_keeps_shot_1s_reaction_and_files_the_sound(cast3):  # noqa: F811
    pick(cast3, REF2VA)
    keep(cast3, "applause")
    job, _, _ = await planned(cast3, json.dumps(REACTING))
    made, made_sound = clips(cast3, 1), sound_landed(cast3)
    await job.plan.finish({1: made_sound, 2: made[0]})
    seq = cast3.files.sequence("Script 1")
    assert [i["sound"] for i in seq["tracks"][1]] == ["sounds/audience/applause.wav"]
    assert cast3.files.sound_facts("sounds/audience/laughter.wav") is not None, "paid for: filed"


async def test_a_made_sound_whose_name_is_taken_stays_where_it_landed(cast3):  # noqa: F811
    pick(cast3, REF2VA)
    keep(cast3, "applause")
    job, _, _ = await planned(cast3, json.dumps(REACTING))
    keep(cast3, "laughter", 3.0)                                         # one kept while the job ran
    made, made_sound = clips(cast3, 3), sound_landed(cast3)
    await job.plan.finish({1: made_sound, 2: made[0], 3: made[1], 4: made[2]})
    assert cast3.files.sound_facts("sounds/audience/laughter.wav") == {"seconds": 3.0}
    assert cast3.files.sequence("Script 1")["tracks"][1][1]["sound"] == made_sound


def test_the_schema_offers_the_three_kinds_and_the_message_says_so():
    shot = scene.SCHEMA["properties"]["shots"]["items"]
    assert shot["properties"]["reaction"] == {"enum": ["applause", "laughter", "gasps"]}
    assert "reaction" not in shot["required"] and "reaction" not in director.PLAN["properties"]
    assert "reaction: what the audience does at the end of that shot" in scene.MESSAGE
    assert "never written" not in scene.MESSAGE and "no audience" not in scene.MESSAGE, "no word rule"


# refusals the model can fix. An empty reaction is no reaction; each refusal says what to write
# instead; one send-back carries every fault found in one pass.
def golden(p: Any, tmp_path: Path) -> str:
    return json.dumps({"tasks": p.tasks, "inputs": [{k: list(v) for k, v in i.items()} for i in p.inputs],
                       "summary": p.summary, "takes": p.takes}, sort_keys=True, indent=1).replace(str(tmp_path), "TMP")


async def test_an_empty_reaction_is_no_reaction(cast3, tmp_path):  # noqa: F811
    pick(cast3, REF2VA)
    empty = plan(*[{**s, "reaction": v} for s, v in zip(GOOD["shots"], (None, "", " None "), strict=True)])
    job, model, _ = await planned(cast3, json.dumps(empty))
    assert len(model.sent) == 1, "accepted on ask 1"
    assert golden(job.plan, tmp_path) + "\n" == (Path(__file__).parents[1] / "fixtures" /
                                                 "scene-plan.json").read_text(encoding="utf-8")
    assert job.plan.tasks[-1]["audio"] == [] and job.plan.summary["step_names"][-1] == "Cut", "no reaction placed"


async def test_a_reaction_not_a_kind_is_sent_back_naming_its_shot(cast3):  # noqa: F811
    pick(cast3, REF2VA)
    bad = plan(GOOD["shots"][0], {**GOOD["shots"][1], "reaction": "cheers"}, GOOD["shots"][2])
    _, model, lines = await planned(cast3, json.dumps(bad), json.dumps(GOOD))
    assert model.sent[1][-1]["content"].startswith(
        "The Hub refused that scene: shot 2: reaction is applause, laughter or gasps, or left out. Send the whole")
    assert lines[1].startswith("Planning scene · fixing: shot 2: reaction is applause, laughter or gasps, or left out "
                               "· ask 2")


async def test_the_audience_in_the_set_is_accepted_as_written(cast3):  # noqa: F811
    pick(cast3, REF2VA)
    seats = plan(*GOOD["shots"], set={**GOOD["set"], "where": "Audience seats around a bare stage"})
    job, model, _ = await planned(cast3, json.dumps(seats))
    assert len(model.sent) == 1 and job.plan.tasks[-1]["kind"] == "join", "accepted on ask 1"
    assert "Audience seats around a bare stage." in job.plan.tasks[0]["prompt"]


def test_the_message_names_the_sets_limit_with_no_example_decor():
    assert "stage only" not in scene.MESSAGE and "seats" not in scene.MESSAGE, "the place is the request's"
    assert "set: the place, the light and the room's sound as the request describes them" in scene.MESSAGE
    for decor in ("desk", "couch", "sofa", "curtain", "chair", "e.g.", "for example", "such as"):
        assert decor not in scene.MESSAGE.lower(), decor


async def test_every_fault_goes_back_in_one_send_back(cast3):  # noqa: F811
    pick(cast3, REF2VA)
    bad = plan(GOOD["shots"][0], {**GOOD["shots"][1], "action": ["Character 6 waves to the crowd"], "reaction": "boos"},
               {**GOOD["shots"][2], "reaction": "cheers"},
               set={**GOOD["set"], "where": "Audience seats around a bare stage"})
    job, model, lines = await planned(cast3, json.dumps(bad), json.dumps(GOOD))
    two = "shot 2: reaction is applause, laughter or gasps, or left out"
    three = "shot 3: reaction is applause, laughter or gasps, or left out"
    assert model.sent[1][-1]["content"] == scene.SEND_BACK.format(f"{two}; {three}"), "the words are not faults"
    assert lines[1] == f"Planning scene · fixing: {two} (+1 more) · ask 2 · qwen3.5:9b"
    assert len(model.sent) == 2 and job.plan.tasks[-1]["kind"] == "join", "both fixed: accepted on ask 2"


def test_a_send_back_holds_every_fault():
    err = audience.refused([audience.REACTION.format(k) for k in range(10, 0, -1)])
    assert err.text.count("; ") == 9 and err.text.startswith("shot 1: ") and err.shown.endswith(" (+9 more)")
    assert err.count == 10, "every reason, none cut"
