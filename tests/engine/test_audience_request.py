"""An honest plan for a request about the audience: the model writes what was asked (the audience in the set, the
action and the ending, a speech verb in the camera move, "cheerful"), three times. The planner must accept it and the
compiled prompt, the Hub's own text, must carry the engine's guard: nonverbal room tone, no crowd voices, only the
tagged line spoken, the frame on the speaker."""
from __future__ import annotations

import json

from hub.modules.generate_image import screen, shotprompt
from tests.engine.test_director import planned
from tests.engine.test_shotprompt import ctx, pick, shot  # noqa: F401
from tests.engine.test_upstream_rules import REF2VA, cat  # noqa: F401

HONEST = shot(subjects=[{"name": "Character 7", "look": "in a grey suit"}],
              where="a brightly lit stage with a live audience in the seats",
              camera={"framing": "medium shot, centre framing on Character 7",
                      "move": "slow push-in as the speaker begins"},
              action=["Character 7 walks to centre stage and spreads both arms to the audience",
                      "the character gives a cheerful wave as the crowd applauds"],
              lines=[{"speaker": "Character 7",
                      "words": "Line one opens! It's so good to say all of this here."}],
              ending="Character 7 smiles at the audience", seconds=8)


async def test_an_honest_plan_about_the_audience_is_accepted_and_the_prompt_guards_the_sound(ctx):  # noqa: F811
    pick(ctx, REF2VA)
    reply = json.dumps(HONEST)
    job, model, lines = await planned(ctx, reply, reply, reply)
    assert len(model.sent) == 1, f"refused: {lines[-1]}"
    draft = screen.draft(ctx)
    print("\n" + draft)
    body = draft.split("overall_soundscape:")[0]
    sound = draft.split("overall_soundscape:")[1].split("\n")[0]
    assert "<d>Line one opens! It's so good to say all of this here.</d>" in body
    assert "Only this explicitly tagged line" not in body and "mouth closed" not in body, "no guard"
    assert sound.strip() == shotprompt.NONE, "no ambience in the plan: N/A, no sentence of the Hub's"
    assert "The frame holds on" not in body, "no sentence of the Hub's"
