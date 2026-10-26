"""A `Clip:` plan has no field for the room's sound: a reply carrying
`sound.ambience` fails `director.PLAN`'s schema (the one refusal on it); an accepted plan's `overall_soundscape`
is the Hub's room sentence; `set_generate_image_settings {shot}` takes `sound.ambience`, cleaned, before that
sentence. A camera field that says someone speaks is accepted and reaches the prompt."""
from __future__ import annotations

import json

import pytest

from hub.core.api import Invalid, schema_check
from hub.modules.generate_image import director, screen, shotcheck
from tests.engine.test_director import BARE_STAGE, GOOD, planned
from tests.engine.test_generate_image import call
from tests.engine.test_shotprompt import ctx, pick  # noqa: F401
from tests.engine.test_upstream_rules import REF2VA, cat  # noqa: F401


def test_the_plan_has_no_room_sound_and_the_shot_schema_keeps_it():
    assert set(director.PLAN["properties"]["sound"]["properties"]) == {"music"}
    assert set(shotcheck.SCHEMA["properties"]["sound"]["properties"]) == {"ambience", "music"}, "unchanged"
    with pytest.raises(Invalid):
        schema_check(director.PLAN, {**GOOD, "sound": {"ambience": "a hall with clapping"}})
    schema_check(director.PLAN, {**GOOD, "sound": {"music": "a jazz sting"}})


async def test_a_clip_reply_with_ambience_is_refused_and_the_room_is_the_hubs(ctx):  # noqa: F811
    pick(ctx, REF2VA)
    clapping = {**BARE_STAGE, "sound": {"ambience": "the audience clapping"}}
    job, model, _ = await planned(ctx, json.dumps(clapping), json.dumps(BARE_STAGE))
    assert len(model.sent) == 2 and "ambience" in model.sent[1][-1]["content"], "the schema's line goes back"
    assert job.plan.tasks and "overall_soundscape: N/A\n" in screen.draft(ctx), "no ambience: N/A"
    text = model.sent[0][0]["content"]
    assert "The room's sound is the Hub's; you write no sound but music, and music only if asked." in text
    assert "audience" not in text and "speaks" not in text, "the message does not prime the words"


async def test_set_generate_image_settings_still_takes_ambience(ctx):  # noqa: F811
    pick(ctx, REF2VA)
    await call(ctx, "set_generate_image_settings", {"shot": {**GOOD, "sound": {"ambience": "a murmuring hall"}}})
    assert "overall_soundscape: a murmuring hall.\n" in screen.draft(ctx), "as written"


async def test_a_camera_timed_to_the_speech_is_accepted_on_ask_1(ctx):  # noqa: F811
    pick(ctx, REF2VA)
    timed = {**BARE_STAGE, "camera": {"framing": "medium shot", "move": "slow push in as the speaker talks"}}
    job, model, lines = await planned(ctx, json.dumps(timed))
    assert len(model.sent) == 1 and job.plan.tasks
    assert "slow push in as the speaker talks." in screen.draft(ctx)
    assert "Only this explicitly tagged line" not in screen.draft(ctx), "no guard of the Hub's"
