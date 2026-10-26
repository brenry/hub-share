"""Casting: a shot's subject that is in Characters and has no picture in a box goes into the next empty box; filled
boxes are never moved or replaced; a model whose boxes are not identities places nothing. The speaker's voice goes
with the clip (`test_voice_reference`)."""
from __future__ import annotations

from typing import Any

from hub.modules.generate_image import routes, voiced
from tests.engine.test_generate_image import call
from tests.engine.test_shotprompt import CHARACTER_7, CHARACTER_16, ctx, pick  # noqa: F401
from tests.engine.test_upstream_rules import FL2VA, REF2VA, cat  # noqa: F401


def shot(**extra: Any) -> dict:
    return {"subjects": [{"name": "Character 7"}], "where": "a bare stage",
            "camera": {"framing": "medium shot", "move": "slow push in"}, "action": ["Character 7 faces the camera"],
            "lines": [{"speaker": "Character 7", "words": "Line one, everybody!"}], **extra}


def boxes(ctx: Any) -> list[str]:  # noqa: F811
    return [r["id"] for r in routes.session_part(ctx)["references"]]


async def test_a_named_character_goes_into_the_next_empty_box(ctx):  # noqa: F811
    pick(ctx, REF2VA)                                                   # no box filled
    await call(ctx, "set_generate_image_settings", {"shot": shot()})
    assert boxes(ctx) == ["chars/Character 7.png"], "cast by name"
    two = shot(subjects=[{"name": "Character 16"}, {"name": "Character 7"}])
    await call(ctx, "set_generate_image_settings", {"shot": two})
    assert boxes(ctx) == ["chars/Character 7.png",
                          "chars/Character 16.png"], "the filled box stays; Character 16 takes the next"


async def test_the_users_own_boxes_are_never_moved_and_a_frame_model_places_nothing(ctx):  # noqa: F811
    pick(ctx, REF2VA, CHARACTER_16)
    await call(ctx, "set_generate_image_settings", {"shot": shot()})
    assert boxes(ctx) == ["chars/Character 16.png", "chars/Character 7.png"]
    pick(ctx, REF2VA, CHARACTER_7)
    assert voiced.cast_named(ctx, shot(subjects=[{"name": "a waiter"}, {"name": "Character 7"}]),
                             {"video": {"references": {"role": "identity", "max": 9}}}) == []
    pick(ctx, FL2VA)
    await call(ctx, "set_generate_image_settings", {"shot": shot()})
    assert boxes(ctx) == [], "a start-frame model's box is never filled by casting"
    assert not ctx.jobs.jobs, "nothing queued"
