"""`script_say`: the Hub reads the chat message (`hub/modules/director/say.py`, `sayask.py`, `saycheck.py`,
`saytrial.py`, `landing.mended`, `tools.FNS`) on `test_script_track`'s context with stand-in samples, speech model, jobs
and lane (`test_script_mix`'s `mctx`), a scripted `ask` and a fake `said`: a new story in one call (the context ask, the
script ask; the file holds the scenes, shots, lines, cues; every scene done; no lock and no Track job once the sketches
are drawn; the Hub's line a `chat.note`); a paraphrase of the message's quote sent back, then the message's words in the
file; a hole the ask leaves sent back and mended; two cues at one line's end written as sent; the 4th ask still refused:
what landed written and the line's `not done:`; in a Hub-chat turn any writing tool writes the `user` message's words, a
second call writes nothing; with `said` None `line_add` works as before; a slow ask answered "still writing", then the
note; two messages in order; a removal under the message's length written back into it, an add in any other change
refused; no answer or line holds a tool name, `ref`, an id or `fix`; nothing on disk but the script."""
from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Iterator
from typing import Any

import pytest

from hub.modules.director import autolock, mix, say, sayask, saytrial
from tests.engine.test_media_characters import png_bytes
from tests.engine.test_script_mix import mctx  # noqa: F401  (the fixture)
from tests.engine.test_script_stale import draw_all
from tests.engine.test_script_tools import CONTEXT, Model, on_disk
from tests.engine.test_script_track import call
from tests.engine.test_script_track import ctx as track_ctx  # noqa: F401  (the fixture)

STORY = "Script: Character 7 meets Character 6 on the stage, about 15 seconds."
J1 = "Line one opens here, and needs no more."
G1 = "Thank you, friend. It is lovely to be here."
J2 = "Tell me, friend, what brought you back home?"
G2 = "My family, mostly. They still keep the shop."
TOLD = "Friend, good to see you. Tell me everything."
OPS = [{"op": "add_scene", "title": "The opening", "cast": ["Character 7", "Character 6"], "seconds": 15},
       {"op": "add_shot", "framing": "Wide two-shot of the stage", "on": ["Character 7", "Character 6"],
        "action": "action 1"},
       {"op": "add_line", "speaker": "Character 7", "words": J1},
       {"op": "add_line", "speaker": "Character 6", "words": G1},
       {"op": "add_shot", "framing": "Close-up of Character 7 leaning in", "on": ["Character 7"], "action": "action 2"},
       {"op": "add_line", "speaker": "Character 7", "words": J2},
       {"op": "add_shot", "framing": "Close-up of Character 6", "on": ["Character 6"], "action": "action 3"},
       {"op": "add_line", "speaker": "Character 6", "words": G2},
       {"op": "add_cue", "cue": "reaction", "words": "The audience laughs", "at": {"speaker": "Character 6", "nth": 2,
                                                                                   "end": True}}]
TOOLS = re.compile(r"\b(script_\w+|context_set|scene_add|scene_change|shot_add|line_add|cue_add|pose_add|event_\w+|"
                   r"ref|fix|[sclp][0-9]+)\b")


@pytest.fixture(autouse=True)
def clean() -> Iterator[None]:
    for held in (autolock.said, autolock.pending, mix.running, mix.failed, say.handled, say.tasks):
        held.clear()
    yield
    for held in (autolock.said, autolock.pending, mix.running, mix.failed, say.handled, say.tasks):
        held.clear()


def plan(ops: list[dict], title: str | None = "Script 2") -> str:
    return json.dumps({**({"title": title} if title else {}), "operations": ops})


def shot_list(ops: list[dict], title: str | None = None, holds: list[float] | None = None) -> str:
    """The planner's pass-1 answer from a story's operations (`title` else `plan`'s): each add_shot a shot held
    `holds[k]` s (else its own seconds, else 1 s), its add_lines its lines, an add_cue its sound; add_scene's seconds
    the length named."""
    out: dict[str, Any] = {"title": title or json.loads(plan([]))["title"], "shots": []}
    for op in ops:
        if op["op"] == "add_scene" and "seconds" in op:
            out["seconds"] = op["seconds"]
        elif op["op"] == "add_shot":
            k = len(out["shots"])
            held = holds[k] if holds and k < len(holds) else op.get("seconds", 1)
            out["shots"].append({"framing": op["framing"], "on": op.get("on", []), "action": op.get("action", ""),
                                 "seconds": held, "sound": ""})
        elif op["op"] == "add_line":
            out["shots"][-1].setdefault("lines", []).append({"speaker": op["speaker"], "words": op["words"]})
        elif op["op"] == "add_cue":
            out["shots"][-1]["sound"] = op["words"]
    return json.dumps(out)


def hub(ctx: Any, text: str | None, ident: str = "m1", first: bool = True) -> None:
    """The assistant's `said` service, faked: the `user` message while a turn runs (None: no turn)."""
    base = type(ctx).service

    def service(name: str) -> Any:
        if name == "said":
            return lambda: None if text is None else {"id": ident, "text": text, "first": first}
        return base(ctx, name)
    ctx.service = service


def notes(ctx: Any) -> list[str]:
    return [d["text"] for e, d in ctx.events if e == "chat.note"]


def tracks(ctx: Any) -> list[Any]:
    return [j for j in ctx.jobs.made if j.kind == "director.track"]


def lines(script: dict) -> list[tuple[str, str]]:
    return [(ev["speaker"], ev["words"]) for sc in script["scenes"] for shot in sc["shots"] for ev in
            sorted((e for e in shot["events"] if e["kind"] == "line"), key=lambda e: e["start_ms"])]


async def story(ctx: Any) -> dict:
    ctx.model = Model(json.dumps(CONTEXT), shot_list(OPS))
    return await call(ctx, "script_say", {"words": STORY})


async def test_a_new_story_in_one_call(mctx: Any) -> None:  # noqa: F811
    got = await story(mctx)
    [line] = got["state"]
    assert got["next"] == say.REPLY and got["script"] == "Script 2"
    assert line.startswith("Script 2: wrote 1 scene, 3 shots, 4 lines, 1 cue · runs "), line
    assert "(15 s asked)" in line and "the takes start" not in line, line      # no lock, no takes tail
    assert notes(mctx) == [line]
    held = on_disk(mctx, "Script 2")
    assert lines(held) == [("Character 7", J1), ("Character 6", G1), ("Character 7", J2), ("Character 6", G2)]
    assert [s["camera"]["framing"] for s in held["scenes"][0]["shots"]][0] == "Wide two-shot of the stage"
    assert held["scenes"][0]["done"] is True and held["scenes"][0]["seconds"] == 15
    assert len(mctx.model.sent) == 2
    assert mctx.model.sent[1][1] == {"role": "user", "content": "Story: Character 7 meets Character 6 on the "
                                     "stage, about 15 seconds."}                    # pass 1, the story alone
    await draw_all(mctx)
    assert on_disk(mctx, "Script 2").get("lock") is None and not tracks(mctx), "no lock, no Track"
    assert not TOOLS.search(line), line
    root = mctx.data_dir.parents[1]                      # the message is nowhere on disk
    assert not [p for p in root.rglob("*") if p.is_file() and b"the stage, about 15" in p.read_bytes()]


async def test_a_paraphrase_of_the_owners_words_is_sent_back_then_the_owners_words_land(mctx: Any) -> None:  # noqa: F811
    await story(mctx)
    await draw_all(mctx)
    ref = {"speaker": "Character 7", "nth": 1}
    mctx.model = Model(plan([{"op": "change_line", "ref": ref, "words": "Friend, hello! What's new?"}], None),
                       plan([{"op": "change_line", "ref": ref, "words": TOLD}], None))
    hub(mctx, f"Change Character 7's first line to: {TOLD}", "m2", first=False)
    got = await call(mctx, "event_change", {"ref": ref, "fields": {"words": "Friend, hello! What's new?"}})
    assert len(mctx.model.sent) == 2, "the first ask and one mend"
    assert mctx.model.sent[1][-1]["content"].startswith(f'The Hub refused that list: the message writes "{TOLD}"; no '
                                                        "operation holds it as written")
    assert lines(on_disk(mctx, "Script 2"))[0] == ("Character 7", TOLD)
    [line] = got["state"]
    assert line == f'Script 2: changed Character 7\'s 1st line to: "{TOLD}"', line      # no " · " tail
    assert not TOOLS.search(line.replace(TOLD, "")), line
    again = await call(mctx, "line_add", {"shot": "s1", "speaker": "Character 7", "words": "Something else."})
    assert again == {"script": "Script 2", "state": [line], "next": say.DONE}, "the same turn: nothing"
    assert len(mctx.model.sent) == 2 and lines(on_disk(mctx, "Script 2"))[0] == ("Character 7", TOLD)


async def test_a_hole_the_ask_leaves_is_sent_back_and_mended(mctx: Any) -> None:  # noqa: F811
    bare = [{k: v for k, v in op.items() if k != "action"} if op["op"] == "add_shot" else op for op in OPS]
    mctx.model = Model(json.dumps(CONTEXT), shot_list(bare), shot_list(OPS))      # a shot list with no action
    got = await call(mctx, "script_say", {"words": STORY})
    assert len(mctx.model.sent) == 3
    back = mctx.model.sent[2][-1]["content"]
    assert back.startswith("The Hub sent that shot list back: shots 1, 2, 3 have no action"), back
    assert lines(on_disk(mctx, "Script 2"))[-1] == ("Character 6", G2)
    assert "not done" not in got["state"][0]


async def test_two_cues_at_one_lines_end_are_written_as_sent(mctx: Any) -> None:  # noqa: F811
    await story(mctx)
    at = {"speaker": "Character 7", "nth": 1, "end": True}
    two = [{"op": "add_cue", "cue": "reaction", "words": "cue 1", "at": at},
           {"op": "add_cue", "cue": "music", "words": "cue 2", "at": at}]                 # both at one line's end
    mctx.model = Model(plan(two, None))
    got = await call(mctx, "script_say", {"words": "Add a reaction and a sting after Character 7's first line."})
    assert len(mctx.model.sent) == 1 and "2 cues" in got["state"][0], got
    cues = [ev for sh in on_disk(mctx, "Script 2")["scenes"][0]["shots"] for ev in sh["events"]
            if ev["kind"] == "cue" and ev["words"] in ("cue 1", "cue 2")]
    assert [c["cue"] for c in cues] == ["reaction", "music"] and cues[1]["anchor"]["at"] == "end", \
        "past the scene's 15 s asked, written as sent"


async def test_at_the_fourth_ask_what_landed_is_written(mctx: Any) -> None:  # noqa: F811
    await story(mctx)
    wrong = plan([{"op": "change_shot", "ref": {"shot": 2}, "framing": "Close-up of Character 6",
                   "on": ["Character 6"]},
                  {"op": "change_line", "ref": {"speaker": "Character 7", "nth": 1},
                   "words": "Hi friend. What's new?"}],
                 None)
    mctx.model = Model(*[wrong] * 2)
    hub(mctx, f"Make shot 2 a close shot on Character 6, and change Character 7's first line to: {TOLD}", "m3",
        first=False)
    got = await call(mctx, "line_add", {"shot": "s1", "speaker": "Character 7", "words": "Hello."})
    assert len(mctx.model.sent) == 2
    held = on_disk(mctx, "Script 2")
    assert held["scenes"][0]["shots"][1]["camera"]["framing"] == "Close-up of Character 6"
    assert lines(held)[0] == ("Character 7", J1), "no paraphrase of the message reaches the file"
    [line] = got["state"]
    assert line.startswith("Script 2: changed shot 2: Close-up of Character 6, on Character 6 · ") and \
        f'not done: the message writes "{TOLD}"; no operation holds it as written' in line, line
    assert notes(mctx)[-1] == line


async def test_outside_the_hubs_chat_the_tools_work_as_before(mctx: Any) -> None:  # noqa: F811
    await story(mctx)
    hub(mctx, None)
    got = await call(mctx, "line_add", {"shot": "s1", "speaker": "Character 7", "words": "Hello."})
    assert got["state"][0].startswith("Script 2 · 1 scenes · 3 shots") and len(mctx.model.sent) == 2
    assert lines(on_disk(mctx, "Script 2"))[2] == ("Character 7", "Hello.")


async def test_a_slow_ask_answers_still_writing_then_the_line(mctx: Any, monkeypatch: Any) -> None:  # noqa: F811
    monkeypatch.setattr(say, "DEADLINE_S", 0.05)
    slow = Model(json.dumps(CONTEXT), shot_list(OPS))
    first = slow.__call__

    async def ask(messages: list[dict], schema: dict | None = None) -> tuple[str, str]:
        if messages:
            await asyncio.sleep(0.1)
        return await first(messages, schema)
    mctx.model = ask
    got = await call(mctx, "script_say", {"words": STORY})
    assert got == {"script": None, "state": [say.STILL], "next": say.REPLY} and not notes(mctx)
    await asyncio.gather(*say.tasks.values())
    assert notes(mctx)[0].startswith("Script 2: wrote 1 scene, 3 shots, 4 lines, 1 cue")


async def test_two_messages_in_order_and_the_owners_changes_land(mctx: Any) -> None:  # noqa: F811
    change = plan([{"op": "change_shot", "ref": {"shot": 2}, "framing": "Close-up of Character 7",
                    "on": ["Character 7"]}], None)
    gone = plan([{"op": "remove", "ref": {"cue": "effect", "nth": 1}},
                 {"op": "remove", "ref": {"speaker": "Character 6", "nth": 2}}, {"op": "remove", "ref": {"shot": 3}}],
                None)
    free = [{k: v for k, v in op.items() if k != "seconds"} for op in OPS]       # no length asked: none kept
    mctx.model = Model(json.dumps(CONTEXT), shot_list(free), change, gone)
    got = await asyncio.gather(call(mctx, "script_say", {"words": STORY.split(",")[0] + "."}),
                               call(mctx, "script_say", {"words": "Make shot 2 a close shot on Character 7."}),
                               call(mctx, "script_say", {"words": "Take out Character 6's second line, the first "
                                                                  "effect cue and shot 3."}))
    said = [g["state"][0] for g in got]
    assert notes(mctx) == said
    assert said[1].startswith("Script 2: changed shot 2: Close-up of Character 7, on Character 7"), said[1]
    assert said[2].startswith('Script 2: took out the 1st effect cue: "The audience laughs"; took out '
                              'Character 6\'s 2nd line: "My family, mostly. They…"; took out shot 3'), said[2]
    held = on_disk(mctx, "Script 2")
    assert len(held["scenes"][0]["shots"]) == 2 and \
        lines(held) == [("Character 7", J1), ("Character 6", G1), ("Character 7", J2)]
    for line in said:
        assert not TOOLS.search(line), line


async def test_the_owners_length_is_the_owners_number_and_the_hub_writes_on_to_it(mctx: Any) -> None:  # noqa: F811
    await story(mctx)
    more = [{"op": "add_shot", "framing": "Two-shot of the table", "on": ["Character 7", "Character 6"], "seconds": 7},
            {"op": "add_line", "speaker": "Character 7", "words": "And the shop, friend, is it still on Main Street?"},
            {"op": "add_line", "speaker": "Character 6", "words": "It is, and it still smells of fresh bread."},
            {"op": "add_shot", "framing": "Close-up of Character 7", "on": ["Character 7"], "seconds": 8},
            {"op": "add_line", "speaker": "Character 7", "words": "Then we are all coming by tomorrow morning, folks!"},
            {"op": "add_line", "speaker": "Character 6",
             "words": "Bring your appetite, everyone. The first loaf is free."}]
    mctx.model = Model(plan([{"op": "set_length", "seconds": 15}, *more], None),
                       plan([{"op": "set_length", "seconds": 30}, *more], None))
    got = await call(mctx, "script_say", {"words": "Make the scene 30 seconds."})
    assert mctx.model.sent[1][-1]["content"].startswith("The Hub refused that list: the message writes 30 seconds; "
                                                        "operation 1 "
                                                        "says 15")
    [line] = got["state"]
    assert line.startswith("Script 2: set scene 1 to 30 s, wrote 2 shots, 4 more lines · runs "), line
    held = on_disk(mctx, "Script 2")
    assert held["scenes"][0]["seconds"] == 30 and held["scenes"][0]["done"] is True
    assert 27_000 <= held["scenes"][0]["shots"][-1]["end_ms"] <= 33_000


async def test_no_model_is_the_owners_one_sentence(mctx: Any) -> None:  # noqa: F811
    from hub.core.api import Invalid

    async def none(messages: list[dict], schema: dict | None = None) -> tuple[str, str]:
        raise Invalid("model", "Set the Open WebUI model name in Settings -> Assistant")
    mctx.model = none
    got = await call(mctx, "script_say", {"words": STORY})
    assert got["state"] == ["Set the Assistant's model in Settings"] and notes(mctx) == got["state"]


async def test_a_removal_under_a_named_length_writes_the_removal_only(mctx: Any) -> None:  # noqa: F811
    """No range to refill a scene to, so a line added in a change message is sent back as any add."""
    await story(mctx)
    gone = {"op": "remove", "ref": {"speaker": "Character 7", "nth": 2}}
    fill = {"op": "add_line", "shot": 2, "speaker": "Character 7", "words": "So, friend, what is the shop like now?"}
    mctx.model = Model(plan([gone, fill], None), plan([gone], None))
    got = await call(mctx, "script_say", {"words": "Take out Character 7's second line."})
    assert len(mctx.model.sent) == 2 and "never add one (operation 2 is add_line)" in mctx.model.sent[1][-1]["content"]
    [line] = got["state"]
    assert line.startswith('Script 2: took out Character 7\'s 2nd line: "Tell me, friend, what…"'), line
    held = on_disk(mctx, "Script 2")
    assert ("Character 7", J2) not in lines(held) and ("Character 7", fill["words"]) not in lines(held)
    assert held["scenes"][0]["done"] is True and held["scenes"][0]["seconds"] == 15
    await draw_all(mctx)
    assert on_disk(mctx, "Script 2").get("lock") is None and not tracks(mctx), "no lock, no Track"


async def test_an_add_in_a_change_with_no_scene_taken_out_of_its_length_is_refused(mctx: Any) -> None:  # noqa: F811
    await story(mctx)
    shot = {"op": "change_shot", "ref": {"shot": 2}, "framing": "Close-up of Character 7", "on": ["Character 7"]}
    extra = {"op": "add_line", "shot": 2, "speaker": "Character 7", "words": "Hello."}
    mctx.model = Model(plan([shot, extra], None), plan([shot], None))
    await call(mctx, "script_say", {"words": "Make shot 2 a close shot on Character 7."})
    assert len(mctx.model.sent) == 2 and "never add one (operation 2 is add_line)" in mctx.model.sent[1][-1]["content"]
    assert ("Character 7", "Hello.") not in lines(on_disk(mctx, "Script 2"))


async def test_at_the_ask_limit_the_owners_line_names_no_field_and_keeps_its_sentence(mctx: Any) -> None:  # noqa: F811
    """No `operation k`, `(tool)` or `{…}` reaches the chat line; an id is said by what it names."""
    await story(mctx)
    mctx.model = Model(*[plan([{"op": "change_shot", "framing": "Close-up of Character 6"}], None)] * 2)
    got = await call(mctx, "script_say", {"words": "Make shot 2 a close shot on Character 6."})
    assert len(mctx.model.sent) == 2 and "operation 1 (change_shot) needs ref {shot}" in \
        mctx.model.sent[-1][-1]["content"]
    [line] = got["state"]
    assert line == "Script 2: not done: a shot's change needs which one", line
    assert not re.search(r"operation \d|\(\w+_\w+\)|\{", line) and not TOOLS.search(line), line
    held = on_disk(mctx, "Script 2")
    assert saytrial.plain("operation 1: Line l4 starts before l3 ends", held) == \
        "Character 6's 2nd line starts before Character 7's 2nd line ends"
    assert saytrial.plain("operation 1: Line l4 starts before l3 ends") == "A line starts before a line ends"


C1, C2, ONE = "Character 1", "Character 2", "Script 1"


async def _one(ctx: Any) -> None:
    """Script 1: Character 1 and Character 2 with names only, one scene of two shots."""
    (ctx.files.roots["chars"] / f"{C1}.png").write_bytes(png_bytes())
    ops = [{"op": "add_scene", "title": "Scene 1", "cast": [C1, C2]},
           {"op": "add_shot", "framing": "Wide shot", "on": [C1, C2], "action": "action 1"},
           {"op": "add_line", "speaker": C1, "words": "Line 1."},
           {"op": "add_shot", "framing": "Close-up", "on": [C2], "action": "action 2"},
           {"op": "add_line", "speaker": C2, "words": "Line 2."}]
    ctx.model = Model(json.dumps({"cast": [{"name": C1}, {"name": C2}]}), shot_list(ops, ONE))
    await call(ctx, "script_say", {"words": f"Scene 1: {C1} and {C2}, Line 1 and Line 2."})


def _unref(n: int) -> str:
    """A change of `n` operations, each a change_shot with no ref: `n` reasons."""
    return plan([{"op": "change_shot", "framing": f"Framing {k}"} for k in range(1, n + 1)], None)


async def test_a_reply_with_fewer_reasons_is_sent_back_again(mctx: Any) -> None:  # noqa: F811
    await _one(mctx)
    whole = plan([{"op": "change_shot", "ref": {"shot": 2}, "framing": "Medium shot"}], None)
    mctx.model = Model(_unref(3), _unref(2), _unref(1), whole)
    got = await call(mctx, "script_say", {"words": "Make shot 2 a medium shot."})
    assert len(mctx.model.sent) == 4, "each reply had fewer reasons than the one before"
    assert on_disk(mctx, ONE)["scenes"][0]["shots"][1]["camera"]["framing"] == "Medium shot", got


async def test_a_reply_with_as_many_reasons_ends_the_asks(mctx: Any) -> None:  # noqa: F811
    await _one(mctx)
    mctx.model = Model(_unref(2), _unref(2), _unref(1))
    got = await call(mctx, "script_say", {"words": "Make shot 2 a medium shot."})
    assert len(mctx.model.sent) == 2 and mctx.model.replies == [_unref(1)], "the second reply mended nothing"
    assert "not done" in got["state"][0], got
    assert on_disk(mctx, ONE)["scenes"][0]["shots"][1]["camera"]["framing"] == "Close-up"


def test_the_listing_names_no_home_a_member_lacks() -> None:
    held = sayask._context({"context": {"cast": [{"name": C1}, {"name": C2, "home": 70}]}, "scenes": []})
    assert held[:2] == [f"cast {C1}", f"cast {C2} · home 70"], held
