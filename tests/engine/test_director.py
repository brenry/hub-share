"""The Director engine with a fake ask. `direct_clip` queues one job with no task; its planning
step asks the model for a shot, sends a refusal back with its line, and on acceptance the draft panel holds the
compiled prompt and the job's plan is the press's job byte for byte. A reply in <think> and a fence is read; three
refusals fail in one line; a refusal of the press (the speaker's sample under 2 s) is never sent back; the message holds
the schema, the characters and the word budget; nothing of the request, the replies or the shot is on disk; on a picture
model the tool refuses at once. The catalog is the worker's own for upstream's H3 capture (`test_upstream_rules`)."""
from __future__ import annotations

import json
from typing import Any

import pytest

from hub.core.api import Invalid
from hub.modules.generate_image import build, director, models, pace, routes, screen, shotcheck, tools
from tests.engine.test_generate_image import call
from tests.engine.test_shotprompt import ctx, pick, shot  # noqa: F401
from tests.engine.test_upstream_rules import REF2VA, cat  # noqa: F401
from tests.engine.test_voice_reference import sample

REQUEST = "Character 7 stands centre stage in the hall and faces the audience"
GOOD = shot(subjects=[{"name": "Character 7", "look": "in a grey suit"}],
            action=["Character 7 walks to the front of the stage", "the character opens both arms to the room"],
            lines=[{"speaker": "Character 7", "words": "Line one, everybody."}], seconds=6)
QUOTED = {**GOOD, "action": ['Character 7 shouts "line one"', "the character opens both arms to the room"]}


class Model:
    """The assistant's "ask" service, faked: the replies in order, every message list it was sent and the schema
    sent with it."""

    def __init__(self, *replies: str) -> None:
        self.replies, self.sent, self.schemas = list(replies), [], []

    async def __call__(self, messages: list[dict], schema: dict | None = None) -> tuple[str, str]:
        if not messages:
            return "qwen3.5:9b", ""
        self.sent.append([dict(m) for m in messages])
        self.schemas.append(schema)
        return "qwen3.5:9b", self.replies.pop(0)


async def planned(ctx: Any, *replies: str) -> tuple[Any, Model, list[str]]:  # noqa: F811
    """`direct_clip` then the job's planning step, as the dispatcher runs it: -> (the job, the model, the card lines).
    The seed is fixed so a press built again is the same press."""
    await call(ctx, "set_generate_image_settings", {"seed": "41"})
    model, lines = Model(*replies), []
    ctx.offer("ask", model)
    answer = await call(ctx, "direct_clip", {"request": REQUEST})
    [(job, params)] = ctx.jobs.jobs.values()
    assert answer == {"state": "queued", "job": job.id} and params == {"direct": REQUEST}
    assert job.plan.tasks == () and job.plan.summary["prompt"] == REQUEST and job.plan.prepare.job == job.id
    job.plan = await job.plan.prepare(lines.append)
    return job, model, lines


async def test_a_good_reply_on_ask_1_sets_the_draft_and_the_plan_is_the_press(ctx):  # noqa: F811
    pick(ctx, REF2VA)                                                   # every box empty: Character 7 is cast by name
    job, model, lines = await planned(ctx, json.dumps(GOOD))
    assert lines == ["Planning · ask 1 · qwen3.5:9b"] and len(model.sent) == 1
    assert routes.session_part(ctx)["references"][0]["id"] == "chars/Character 7.png", "casting"
    draft = screen.draft(ctx)
    assert draft.startswith("subject_definitions: <Subject 1> is Character 7, from <Picture 1>.")
    assert "(S1) <Subject 1> says <d>Line one, everybody.</d>." in draft
    press = build.image_job(tools.press_params(ctx, await tools._catalog(ctx), draft), ctx)
    said = "Line one, everybody."
    assert job.plan.tasks[0] == {**press.tasks[0], "words": said}, "take 1: the press byte for byte but `words`"
    assert job.plan.tasks[1] == {**press.tasks[0], "words": said, "seed": press.tasks[0]["seed"] + 1}
    assert job.plan.summary == {**press.summary, "step_names": ["Render", "Render · take 2"]}
    assert (job.plan.takes, job.plan.prepare) == ((((1,), (2,)),), None), "the press's takes"
    assert job.plan.finish.job == job.id, "its last step notes this job"
    assert job.plan.summary["kind"] == "clip" and job.notes["plan"]["valid"] is True, "planned by the engine"
    assert ctx.engine.planned == [job.plan.tasks[0]]
    assert routes.session_part(ctx)["last_seeds"] == {"model": REF2VA, "seeds": [41]}
    assert "takes" not in routes.session_part(ctx), "no press is kept to re-take from a listener"


def test_a_reply_in_think_and_a_fence_is_read() -> None:
    reply = f"<think>Plan {{a shot}}.</think>\nHere it is:\n```json\n{json.dumps(GOOD)}\n```\nEnjoy."
    assert director.read(reply) == GOOD
    assert director.read('Sure! {"broken": } then ' + json.dumps(GOOD)) == GOOD, "a balanced {…} that parses"
    assert director.read('{"words": "a } in a string"}') == {"words": "a } in a string"}
    assert director.read("No JSON here.") is None and director.read('{"open": ') is None


async def test_a_quote_in_action_is_accepted_and_sent_as_typed(ctx):  # noqa: F811
    pick(ctx, REF2VA)
    job, model, lines = await planned(ctx, f"```\n{json.dumps(QUOTED)}\n```")
    assert len(model.sent) == 1 and lines == ["Planning · ask 1 · qwen3.5:9b"], "no word is refused"
    draft = screen.draft(ctx)
    shouted = QUOTED["action"][0]
    assert job.plan.tasks and '"' in shouted and shouted in draft, "the quote marks as typed"
    assert "Line one, everybody." in draft


async def test_a_refusal_is_sent_back_with_its_line_and_ask_2_is_accepted(ctx):  # noqa: F811
    pick(ctx, REF2VA)
    stranger = {**GOOD, "lines": [{"speaker": "Character 16", "words": "Line one, everybody."}]}   # not a subject
    job, model, lines = await planned(ctx, f"```\n{json.dumps(stranger)}\n```", json.dumps(GOOD))
    line = "Character 16 speaks but is not a subject"
    assert len(model.sent) == 2 and model.sent[1][:2] == model.sent[0]
    assert model.sent[1][2:] == [
        {"role": "assistant", "content": f"```\n{json.dumps(stranger)}\n```"},
        {"role": "user", "content": f"The Hub refused that shot: {line}. Send the whole shot again as one JSON "
                                    "object, changed only where needed."}]
    assert lines == ["Planning · ask 1 · qwen3.5:9b", f"Planning · fixing: {line} · ask 2 · qwen3.5:9b"]
    assert job.plan.tasks and "Line one, everybody." in screen.draft(ctx)


async def test_three_refusals_fail_in_one_line(ctx):  # noqa: F811
    pick(ctx, REF2VA)
    stranger = {**GOOD, "lines": [{"speaker": "Character 16", "words": "Line one, everybody."}]}
    with pytest.raises(Invalid) as err:
        await planned(ctx, "I cannot do that.", json.dumps({"subjects": []}), json.dumps(stranger))
    assert err.value.text == "Planning: refused 2 times; last: where is required", "the second ends it"


async def test_a_second_refusal_ends_the_planning(ctx):  # noqa: F811
    pick(ctx, REF2VA)
    with pytest.raises(Invalid) as err:
        await planned(ctx, "No JSON 1.", "No JSON 2.", json.dumps(GOOD))
    assert err.value.text == "Planning: refused 2 times; last: The reply holds no JSON object"


async def test_the_message_asks_no_line_and_no_language(ctx):  # noqa: F811
    pick(ctx, REF2VA)
    _, model, _ = await planned(ctx, json.dumps(GOOD))
    text = model.sent[0][0]["content"]
    assert "If the request gives no words, write no line." in text
    assert "language: only a language the request names." in text
    assert "English" not in text and "manner" not in text and "in the character" not in text


async def test_a_refusal_of_the_press_is_not_sent_back(ctx):  # noqa: F811
    ctx.settings["voice_route"] = "reference"                           # the route set
    sample(ctx, "Character 7", seconds=1.5)
    pick(ctx, REF2VA)
    with pytest.raises(Invalid) as err:
        await planned(ctx, json.dumps(GOOD), json.dumps(GOOD))
    assert err.value.text == "Character 7's voice sample is under 2 s"


async def test_the_message_holds_the_schema_the_characters_and_the_word_budget(ctx):  # noqa: F811
    sample(ctx, "Character 7")
    pick(ctx, REF2VA)
    _, model, _ = await planned(ctx, json.dumps(GOOD))
    system, user = model.sent[0]
    assert user == {"role": "user", "content": f"Shot plan: {REQUEST}"}, "not Clip:"
    text = system["content"]
    assert system["role"] == "system" and json.dumps(director.PLAN, separators=(",", ":")) in text
    assert director.PLAN["required"][-1] == "seconds" and "seconds" not in shotcheck.SCHEMA["required"], \
        "the plan asks seconds, the shot check does not"
    assert "Characters (use these exact names for them): Character 16; Character 7, has a voice sample." in text
    assert pace.current(ctx) is None, "the engine's 2.6"
    assert "at most 31 words and 4 of . ! ? ; : (another line costs 4 words, another mark 1 word)" in text
    assert "seconds: how long the whole shot runs, the action and the lines, at most 15.1;" in text
    assert "Spoken words go in lines only." in text and "One speaker per shot; " in text
    assert "audience" not in text and "quote" not in text, "nothing primes audience or quote words"


async def test_a_reply_without_seconds_is_sent_back_with_the_schemas_line(ctx):  # noqa: F811
    pick(ctx, REF2VA)
    bare = {k: v for k, v in GOOD.items() if k != "seconds"}
    _, model, lines = await planned(ctx, json.dumps(bare), json.dumps(GOOD))
    assert lines[1] == "Planning · fixing: seconds is required · ask 2 · qwen3.5:9b"
    assert model.sent[1][-1]["content"].startswith("The Hub refused that shot: seconds is required.")


async def test_over_the_top_says_by_how_much_and_the_fitting_reply_is_accepted(ctx):  # noqa: F811
    pick(ctx, REF2VA)
    long = {**GOOD, "lines": [{"speaker": "Character 7", "words": " ".join(["word"] * 40) + "."}]}
    job, model, _ = await planned(ctx, json.dumps(long), json.dumps(GOOD))
    assert model.sent[1][-1]["content"] == ("The Hub refused that shot: The lines need 18.0 s and one clip holds "
                                            "15.1 s: cut 8 words. Send the whole shot again as one JSON object, "
                                            "changed only where needed.")
    assert job.plan.tasks and "Line one, everybody." in screen.draft(ctx)


async def test_the_users_first_three_sentences_are_one_pass(ctx):  # noqa: F811
    pick(ctx, REF2VA)
    words = ("word word word, word word word word word word, word word word word!. word word word word word word word "
             "word word word! word word word word word word word.")
    spoken = {**GOOD, "lines": [{"speaker": "Character 7", "words": words}], "seconds": 15}
    job, _, _ = await planned(ctx, json.dumps(spoken))
    assert screen.read(ctx)["advanced"][REF2VA]["frames"] == 362 and words in screen.draft(ctx)


async def test_nothing_of_the_request_the_replies_or_the_shot_is_on_disk(ctx, tmp_path):  # noqa: F811
    pick(ctx, REF2VA)
    await planned(ctx, json.dumps(QUOTED), json.dumps(GOOD))
    words = ("centre stage", "Line one", "line one", "grey suit", "Shot plan")
    for path in (p for p in tmp_path.rglob("*") if p.is_file()):
        data = path.read_bytes()
        assert not any(w.encode() in data for w in words), path
    for name, doc in ctx.docs.items():
        assert not any(w in json.dumps(doc.value) for w in words), name


async def test_on_a_picture_model_the_tool_refuses_at_once(ctx):  # noqa: F811
    still = next(m for m in models.present(models.cached()) if m.get("kind") != "video"
                 and models.ui_model(m, models.ref_caps(ctx))["kind"] == "image")
    pick(ctx, still["id"])
    ctx.offer("ask", Model())
    with pytest.raises(Invalid) as err:
        await call(ctx, "direct_clip", {"request": REQUEST})
    label = models.ui_model(still, models.ref_caps(ctx))["label"]
    assert err.value.text == f"{label} makes no clip; a shot is for a video model" and ctx.jobs.jobs == {}


async def test_every_ask_of_a_clip_plan_carries_the_plan_schema(ctx):  # noqa: F811
    pick(ctx, REF2VA)
    bare = {k: v for k, v in GOOD.items() if k != "seconds"}
    _, model, _ = await planned(ctx, json.dumps(bare), json.dumps(GOOD))
    assert len(model.schemas) == 2 and all(s is director.PLAN for s in model.schemas), "the first and the send-back"


ROOM = {**GOOD, "where": "a bare stage with the audience visible in the background",
        "action": ["Slow zoom-in on Character 7 as the speaker begins", "the character opens both arms to the room"]}
BARE_STAGE = {**GOOD, "where": "the bare stage under hot lights"}


async def test_the_audience_and_a_speech_verb_are_accepted_on_ask_1_and_sent_as_written(ctx):  # noqa: F811
    pick(ctx, REF2VA)
    job, model, lines = await planned(ctx, json.dumps(ROOM))
    assert len(model.sent) == 1 and lines == ["Planning · ask 1 · qwen3.5:9b"]
    draft = screen.draft(ctx)
    assert job.plan.tasks and "a bare stage with the audience visible in the background" in draft.lower()
    assert "Slow zoom-in on Character 7 as the speaker begins." in draft, "the plan's words, as written"
    assert "The frame holds on" not in draft and "Only this explicitly tagged line" not in draft, "no guard"
    assert "overall_soundscape: N/A\n" in draft, "no ambience planned: N/A, no sentence of the Hub's"
    assert "audience" not in model.sent[0][0]["content"], "the message does not prime the word"
