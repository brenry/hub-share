"""A Generate press on the speech model: one character's picture in the box, a typed line -> one
`SpeechRequest`, from the window's press and from the assistant's path (the window picks the model and the character;
the assistant writes the draft, `generate_image`); its refusals, one line each; what `list_characters` tells the
assistant of a voice. The catalog is the worker's own, dumped from the fake root that stands in for upstream 18.05."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from hub.core.api import Invalid
from hub.core.files import Files
from hub.modules.generate_image import build, models, routes, tools
from hub.worker import enginewire
from hub.worker.engineapi import SpeechRequest
from tests.engine.helpers import FakeCtx, FakeEngine
from tests.engine.test_generate_image import Bus, call
from tests.engine.test_upstream_rules import SPEECH, cat  # noqa: F401  (the dumped catalog fixture)
from tests.fakes.wav import tiny_wav

CHARACTER_8 = "low, deep gravelly voice, slow"


@pytest.fixture
def ctx(cat, tmp_path, monkeypatch):  # noqa: F811
    monkeypatch.setattr(models, "_last", cat)
    c = FakeCtx("generate-image", tmp_path / "data", FakeEngine(cat), {"image": build.image_job})
    folder = tmp_path / "Characters"
    folder.mkdir()
    for name in ("Character 8.png", "Character 17.png"):
        Image.new("RGB", (40, 30)).save(folder / name)
    c.files = Files(tmp_path / "data", None, folder)
    c.bus = Bus()
    return c


def press(**extra: Any) -> dict[str, Any]:
    return {"model": SPEECH, "mode": "refs", "prompt": "Stay right there!", "references": ["chars/Character 8.png"],
            "seed": {"mode": "fixed", "value": 7}, "loras": [], **extra}


def request_of(plan) -> SpeechRequest:
    [task] = plan.tasks
    return enginewire.request_parse(task)


def test_the_speech_model_is_offered_as_one_box_and_a_line(cat):  # noqa: F811
    ui = models.ui_model(next(m for m in cat["models"] if m["id"] == SPEECH), {})
    assert (ui["kind"], ui["refCap"], ui["modes"], ui["video"], ui["guidanceKey"]) == (
        "speech", 1, ["refs"], None, None)
    assert ui["speech"]["seconds"]["max"] == 300 and SPEECH in [m["id"] for m in models.present(cat)]


def test_a_press_speaks_in_the_words_for_the_voice_until_the_character_has_a_sample(ctx, tmp_path):
    ctx.files.character_voice("chars/Character 8.png", CHARACTER_8)
    plan = build.image_job(press(), ctx)
    assert request_of(plan) == SpeechRequest(SPEECH, "Stay right there!", 7, 300, sample=None, direction=CHARACTER_8,
                                             turn_seconds=5.0, join_seconds=0.1, judge=True)
    assert (plan.summary["kind"], plan.summary["seeds"], plan.summary["references"]) == ("sound", [7], ["Character 8"])
    sound = "sounds/2026-10-17/120000-000.wav"
    ctx.files.resolve(sound).parent.mkdir(parents=True)
    ctx.files.resolve(sound).write_bytes(tiny_wav(4))
    ctx.files.keep_voice(sound, "Character 8")
    again = request_of(build.image_job(press(), ctx))
    assert (again.sample, again.direction) == (str(tmp_path / "Characters" / "Character 8.wav"),
                                               None), "line 2: the character's voice"


@pytest.mark.parametrize(("change", "text"), [
    ({"references": []}, "Drop one character's picture"),
    ({"references": ["out/2026-10-17/a.png"]}, "Drop one character's picture"),
    ({"references": ["chars/Nobody.png"]}, "Drop one character's picture"),
    ({"references": ["chars/Character 8.png", "chars/Character 17.png"]}, "One character speaks at a time"),
    ({"loras": [{"id": "x/y.safetensors", "strength": 0.5}]}, "takes no LoRAs"),
])
def test_the_refusals_are_one_line_each(ctx, change, text):
    with pytest.raises(Invalid) as err:
        build.image_job(press(**change), ctx)
    assert text in err.value.text


def test_size_count_steps_and_guidance_are_not_sent(ctx):
    plan = build.image_job(press(width=4096, height=4096, images=4, steps=99, guidance=30), ctx)
    assert set(plan.tasks[0]) == {"kind", "model", "prompt", "seed", "seconds", "sample", "direction",
                                 "turn_seconds", "pace", "join_seconds", "judge", "measure"}


def pulldown_and_box_pick(ctx: Any) -> dict:
    """The speech model picked and Character 8 placed in the box, as the window does."""
    ctx.doc(routes.DRAFT, {}).replace({"model": SPEECH})
    character_8 = {"id": "chars/Character 8.png", "w": 40, "h": 30}
    routes.session_part(ctx)["references"] = [character_8]
    return character_8


async def test_the_assistant_cannot_change_the_speaker(ctx):
    """With the speech model and one character in the box, no tool sets the model or the box: the line is
    the boxed character's, in that voice."""
    ctx.files.character_voice("chars/Character 8.png", CHARACTER_8)
    character_8 = pulldown_and_box_pick(ctx)
    for change in ({"references": ["Character 17"]}, {"model": "image"}, {"references": ["Character 17"],
                                                                          "model": "image"}):
        with pytest.raises(Invalid, match="unknown argument"):
            await call(ctx, "set_generate_image_settings", {**change, "draft": "Who's there?"})
    seen = await call(ctx, "set_generate_image_settings", {"draft": "Who's there?"})
    assert (seen["model"], seen["references"]) == (SPEECH, ["Character 8"])
    state = await call(ctx, "generate_image", {})
    assert state == {"state": "queued"}
    [(job, params)] = ctx.jobs.jobs.values()
    assert set(params) == {"model", "mode", "prompt", "seed", "references"}, "no size, count or LoRAs"
    assert request_of(job.plan) == SpeechRequest(SPEECH, "Who's there?", request_of(job.plan).seed, 300,
                                                 direction=CHARACTER_8, turn_seconds=5.0, join_seconds=0.1, judge=True)
    assert routes.kind(models.find(models.cached(), SPEECH)) == "speech"
    assert routes.session_part(ctx)["references"] == [character_8], "the box still holds the placed character"
    assert ctx.doc(routes.DRAFT, {}).get()["model"] == SPEECH, "the pulldown still on its pick"


async def test_list_characters_says_the_voice_and_whether_the_character_has_a_sample(ctx, tmp_path: Path):
    ctx.files.character_voice("chars/Character 8.png", CHARACTER_8)
    (tmp_path / "Characters" / "Character 17.wav").write_bytes(tiny_wav(4))
    assert await tools.list_characters(ctx, {}) == {"characters": [{"name": "Character 17", "sample": True},
                                                                   {"name": "Character 8", "voice": CHARACTER_8}]}


@pytest.mark.parametrize("line", ["The light is ours tonight.", "\"The light is ours tonight.\"",
                                  "(S1) <d>[English] The light is ours tonight.</d>"])
def test_plain_line_sent_as_today(ctx, line):
    assert request_of(build.image_job(press(prompt=line), ctx)) == SpeechRequest(SPEECH, line, 7, 300, turn_seconds=5.0,
                                                                                  join_seconds=0.1, judge=True)


async def test_a_drafted_header_is_refused_in_one_line_before_the_job(ctx):
    pulldown_and_box_pick(ctx)
    await call(ctx, "set_generate_image_settings", {"draft": "Speaker 1: The light is ours tonight."})
    with pytest.raises(Invalid, match="no Speaker header") as err:
        await call(ctx, "generate_image", {})
    assert err.value.field == "prompt" and not ctx.jobs.jobs, "no job made"
