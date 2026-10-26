"""The script tools (`hub/modules/director/tools.py`) on a version-2 script in a temp folder: each
tool's happy path and its answer's lines; `script_start` with a stand-in model (accepted on ask 1; a context naming
someone not in Characters sent back and accepted on ask 2); every refusal with its problem, fix and hints, the
file byte for byte unchanged and nothing published; a version-1 script refused; ids never reused after a remove;
`director.changed` published once per write. The pointer through the MCP server and the routes is
`test_script_tools_mcp.py`."""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from hub.core.api import Invalid
from hub.core.files import Files
from hub.core.store import JsonDoc
from hub.modules.director import start, tools
from tests.engine.test_media_characters import png_bytes
from tests.engine.test_script_shape import FIXTURE

NINE = "Line one opens here, and the rest needs more."
FIRST = "Line one opens here,…"                      # NINE's first 4 words
CONTEXT = {"cast": [{"name": "Character 7", "look": "A tall figure", "costume": "A navy suit",
                     "ignore": "The background", "home": 30},
                  {"name": "Character 6", "look": "A figure in grey", "costume": "A red dress",
                   "ignore": "The chair", "home": 70}],
         "set": {"name": "The stage", "description": "A bare stage", "elements": ["Table"],
                 "props": [{"name": "Mug", "owner": "Character 7", "description": "A white mug"}]},
         "style": "A scripted scene"}


class Model:
    """The assistant's "ask" service, faked: the replies in order; every message list and schema it was sent."""

    def __init__(self, *replies: str) -> None:
        self.replies, self.sent, self.schemas = list(replies), [], []

    async def __call__(self, messages: list[dict], schema: dict | None = None) -> tuple[str, str]:
        if not messages:
            return "qwen3.5:9b", ""
        self.sent.append([dict(m) for m in messages])
        self.schemas.append(schema)
        return "qwen3.5:9b", self.replies.pop(0)


class Bus:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str, dict]] = []

    def publish(self, lane: str, type: str, data: dict, key: str | None = None) -> None:
        self.sent.append((lane, type, data))


class Ctx:
    module_id = "director"

    def __init__(self, tmp: Path) -> None:
        cast = tmp / "Characters"
        cast.mkdir()
        for name in ("Character 7", "Character 6"):
            (cast / f"{name}.png").write_bytes(png_bytes())
        self.data_dir = tmp / "data" / "director"
        self.files = Files(tmp / "data", characters_root=cast)
        self.bus = Bus()
        self.docs: dict[str, JsonDoc] = {}
        self.model = Model()
        self.events: list[tuple[str, dict]] = []      # what `emit` was handed (the Hub's chat lines)

    def emit(self, event: str, data: dict) -> None:
        self.events.append((event, data))

    def doc(self, name: str, default: dict) -> JsonDoc:
        if name not in self.docs:
            self.docs[name] = JsonDoc(self.data_dir / f"{name}.json", default)
        return self.docs[name]

    def service(self, name: str) -> Any:
        """As `hub/core/context.py`: a name nobody offers raises `Invalid` (no `pace` here, 2.6)."""
        if name != "ask":
            raise Invalid("assistant", "The assistant is not running")
        return self.model


@pytest.fixture
def ctx(tmp_path: Path) -> Ctx:
    return Ctx(tmp_path)


def by_name(name: str) -> Any:
    return next(a.fn for a in tools.ACTIONS if a.name == name)


async def call(ctx: Ctx, name: str, args: dict) -> dict:
    return await by_name(name)(ctx, args)


async def refused(ctx: Ctx, name: str, args: dict, script: str = "Script 1") -> dict:
    """The refusal's {problem, fix, hints}; the file byte for byte as it was and nothing published."""
    path = ctx.files.roots["scripts"] / f"{script}.json"
    before, sent = path.read_bytes() if path.exists() else None, len(ctx.bus.sent)
    with pytest.raises(Invalid) as e:
        await call(ctx, name, args)
    assert (path.read_bytes() if path.exists() else None) == before, "the file untouched"
    assert len(ctx.bus.sent) == sent, "nothing published"
    return json.loads(e.value.text)


def on_disk(ctx: Ctx, name: str = "Script 1") -> dict:
    return json.loads((ctx.files.roots["scripts"] / f"{name}.json").read_text())


async def started(ctx: Ctx) -> dict:
    ctx.model = Model(json.dumps(CONTEXT))
    return await call(ctx, "script_start", {"name": "Script 1",
                                            "story": "Character 7 meets Character 6 on the stage"})


async def framed(ctx: Ctx) -> None:
    """Script 1: scene 1 (Character 7, Character 6), shots s1 and s2."""
    await started(ctx)
    await call(ctx, "scene_add", {"title": "The opening", "cast": ["Character 7", "Character 6"]})
    await call(ctx, "shot_add", {"scene": 1, "camera": "Wide shot of the stage"})
    await call(ctx, "shot_add", {"scene": 1, "camera": "Close on Character 6"})


async def test_script_start_asks_for_the_context_with_its_schema_and_sets_the_pointer(ctx: Ctx) -> None:
    answer = await started(ctx)
    assert answer == {"script": "Script 1", "state": ["Script 1 · 0 scenes · 0 shots · 0.00 s",
                                                  "started Script 1 · context written",
                                                  "context cast: Character 7, Character 6",
                                                  "now write the story: scene_add, shot_add, line_add"]}
    assert on_disk(ctx) == {"version": 2, "context": CONTEXT, "scenes": []}
    assert ctx.docs["current"].get() == {"name": "Script 1"}
    assert ctx.bus.sent == [("changed", "changed", {"name": "Script 1", "revision": ctx.bus.sent[0][2]["revision"]})]
    [sent] = ctx.model.sent
    assert sent[0]["role"] == "system" and \
        "only these names from Characters: Character 6, Character 7" in sent[0]["content"]
    assert sent[1] == {"role": "user", "content": "Story: Character 7 meets Character 6 on the stage"}
    held = ctx.model.schemas[0]
    assert held["properties"]["cast"]["items"]["properties"]["name"]["enum"] == ["Character 6", "Character 7"]
    assert held["required"] == ["cast"], "only the cast required"


async def test_a_context_naming_someone_not_in_characters_is_sent_back_and_ask_2_accepted(ctx: Ctx) -> None:
    extra = {**CONTEXT, "cast": [*CONTEXT["cast"],
                                 {"name": "Character 4", "look": "x", "costume": "x", "ignore": "x", "home": 5}]}
    ctx.model = Model("<think>a context</think>```json\n" + json.dumps(extra) + "\n```", json.dumps(CONTEXT))
    await call(ctx, "script_start", {"name": "Script 1", "story": "Character 7 meets Character 6"})
    assert len(ctx.model.sent) == 2 and on_disk(ctx)["context"] == CONTEXT
    assert ctx.model.sent[1][-1] == {"role": "user", "content": start.SEND_BACK.format(
        "Cast and set, cast Character 4: Character 4 has no picture in Characters")}
    ctx.model = Model("no json", "{}", json.dumps(extra))
    got = await refused(ctx, "script_start", {"name": "Other", "story": "x"}, "Other")
    assert got["problem"].startswith("The context was refused 2 times: "), "the second refusal ends it"
    assert len(ctx.model.sent) == 2 and ctx.model.replies == [json.dumps(extra)]
    taken = await refused(ctx, "script_start", {"name": "Script 1", "story": "x"})
    assert taken["problem"] == "A script named Script 1 already exists"


async def test_the_context_ask_requires_no_trait(ctx: Ctx) -> None:
    (ctx.files.roots["chars"] / "Character 1.png").write_bytes(png_bytes())
    held = start.schema(["Character 1"])
    assert held["required"] == ["cast"] and held["properties"]["cast"]["minItems"] == 0
    assert held["properties"]["cast"]["items"]["required"] == ["name"]
    assert held["properties"]["set"]["required"] == ["name"]
    assert held["properties"]["set"]["properties"]["props"]["items"]["required"] == ["name"]
    ctx.model = Model(json.dumps({"cast": [{"name": "Character 1"}]}))
    await call(ctx, "script_start", {"name": "Script 1", "story": "Character 1 speaks"})
    assert len(ctx.model.sent) == 1 and on_disk(ctx, "Script 1")["context"] == {"cast": [{"name": "Character 1"}]}


async def test_the_context_ask_tells_the_model_to_leave_out_what_the_story_does_not_say() -> None:
    rule = "only from what the story says, and leave out every field the story says nothing of"
    for told in (start.SYSTEM, start.ANYONE):
        assert rule in told and "what fits" not in told and told.endswith("Answer with JSON only.")


async def test_every_tool_on_its_happy_path(ctx: Ctx) -> None:
    await framed(ctx)                        # p1–p2 at s1's start, p3–p4 at s2's (Character 7, Character 6)
    line = await call(ctx, "line_add", {"shot": "s1", "speaker": "character 7", "words": NINE, "emotion": "warm"})
    assert line == {"script": "Script 1", "state": [
        "Script 1 · 1 scenes · 2 shots · 4.64 s", "line l1 · Character 7 · shot s1 · 0.00–3.64 s (script 0.00–3.64 s)",
        "shot s1 · script 0.00–3.64 s · 11.44 s left",
        f"scene 1 cast: Character 7, Character 6 · lines: 1 · Character 7 · {FIRST}"]}, "l1 ends s1: no end keyframe"
    await call(ctx, "line_add", {"shot": "s2", "speaker": "Character 6", "words": "Thank you, friend."})
    cue = await call(ctx, "cue_add", {"shot": "s1", "cue": "reaction", "words": "Applause",
                                      "anchor": {"line": "l1", "at": "end"}})
    assert cue["state"][1] == "cue c1 · reaction · shot s1 · 3.64–5.64 s (script 3.64–5.64 s)"
    assert cue["state"][2] == "keys p5 added", "the cue runs after l1: the speaker's keyframe at its end"
    pose = await call(ctx, "pose_add", {"shot": "s1", "character": "Character 7", "pose": "arms_raised",
                                        "anchor": {"line": "l1", "at": "start"}})
    assert pose["state"][1] == \
        "pose p1 · Character 7 · shot s1 · 0.00–3.64 s (script 0.00–3.64 s) · arms_raised (replaced)"
    await call(ctx, "pose_add", {"shot": "s2", "character": "Character 7", "pose": "stand", "start_ms": 200})
    moved = await call(ctx, "event_move", {"id": "c1", "start_ms": 1000})
    assert moved["state"][1] == ("the 1st reaction cue, c1: Applause · "
                                 "moved cue c1 · reaction · shot s1 · 1.00–3.00 s (script 1.00–3.00 s)")
    changed = await call(ctx, "event_change", {"id": "l2", "fields": {"words": "It's good to be back, friend."}})
    assert changed["state"][1].startswith("Character 6's 1st line, l2: Thank you, friend. · changed line l2 · "
                                          "Character 6 · shot s2")
    gone = await call(ctx, "event_remove", {"id": "p6"})
    assert gone["state"][1] == "Character 7's pose p6: stand · removed Character 7's pose p6 · shot s2"
    context = await call(ctx, "context_set", {"cast": [{"name": "Character 6", "home": 80}], "style": "Bright light"})
    assert context["state"][1] == "context · cast Character 7, Character 6 · set The stage · style"
    s = on_disk(ctx)
    assert s["context"]["cast"][1] == {**CONTEXT["cast"][1], "home": 80} and s["context"]["style"] == "Bright light"
    [s1, s2] = s["scenes"][0]["shots"]
    assert (s1["id"], s1["start_ms"], s1["end_ms"], s2["id"], s2["start_ms"]) == ("s1", 0, 3642, "s2", 3642)
    assert [e["id"] for e in s2["events"] if e["kind"] != "pose"] == ["l2"]
    assert s2["events"][2]["words"] == "It's good to be back, friend."
    assert len(ctx.bus.sent) == 13 and {x[:2] for x in ctx.bus.sent} == {("changed", "changed")}, "once per write"
    await tools.fill(ctx)                    # the pass a write's wake runs (a read runs it too)
    sent = len(ctx.bus.sent)
    read = await call(ctx, "script_read", {})
    assert read["script"] == "Script 1" and read["read"][:6] == [
        "Script 1 · 1 scenes · 2 shots · 6.13 s", "3 takes: 3 to take",
        "context cast: Character 7, Character 6", "set: The stage — A bare stage",
        "style: Bright light", "scene 1 · The opening · cast Character 7, Character 6"]
    assert [x for x in read["read"][6:] if " panel " not in x] == [
        "s1 · scene 1 · script 0.00–3.64 s · Wide shot of the stage",
        f'l1 line Character 7 0.00–3.64 (script 0.00–3.64) "{NINE}" · warm · 2.6',
        "p1 pose Character 7 arms_raised 0.00–3.64 (script 0.00–3.64)",
        "p2 pose Character 6 stand 0.00–3.64 (script 0.00–3.64)",
        'c1 cue reaction 1.00–3.00 (script 1.00–3.00) "Applause"',
        "s2 · scene 1 · script 3.64–6.13 s · Close on Character 6",
        'l2 line Character 6 0.00–2.49 (script 3.64–6.13) "It\'s good to be back, friend." · 2.6',
        "p3 pose Character 7 arms_raised 0.00–2.49 (script 3.64–6.13)",          # the pose in effect
        "p4 pose Character 6 stand 0.00–2.49 (script 3.64–6.13)",
        f"scene 1 lines: 1 · Character 7 · {FIRST} | 1 · Character 6 · It's good to be…"], \
        "p5 left with c1's move: l1 ends s1 again"
    assert len(ctx.bus.sent) == sent, "a read publishes nothing"


async def test_every_refusal_says_problem_fix_and_hints_and_changes_nothing(ctx: Ctx) -> None:
    await framed(ctx)
    await call(ctx, "line_add", {"shot": "s1", "speaker": "Character 7", "words": NINE})
    await call(ctx, "line_add", {"shot": "s1", "speaker": "Character 6", "words": "Thank you."})
    await call(ctx, "cue_add", {"shot": "s1", "cue": "reaction", "words": "Applause",
                                "anchor": {"line": "l1", "at": "end"}})
    got = await refused(ctx, "line_add", {"shot": "s1", "speaker": "Character 4", "words": "Hi."})
    assert got == {"problem": "Character 4 is not in scene 1's cast",
                   "fix": "Give the line to one of the scene's cast, or add a scene with this cast",
                   "hints": {"valid_speakers": ["Character 7", "Character 6"]}}
    got = await refused(ctx, "pose_add", {"shot": "s1", "character": "Character 4", "pose": "sit"})
    assert got["hints"] == {"valid_speakers": ["Character 7", "Character 6"]}
    got = await refused(ctx, "scene_add", {"title": "Two", "cast": ["Character 7", "Character 4"]})
    assert got == {"problem": "Character 4 is not in the context's cast",
                   "fix": "Call context_set with Character 4 first",
                   "hints": {"context_cast": ["Character 7", "Character 6"]}}
    got = await refused(ctx, "context_set", {"cast": [{"name": "Character 4"}]})
    assert got == {"problem": "Cast and set, cast Character 4: Character 4 has no picture in Characters",
                   "fix": "Cast only names that have a picture in Characters", "hints": {"characters": ["Character 6",
                                                                                                        "Character 7"]}}
    long = " ".join([NINE] * 4)
    got = await refused(ctx, "line_add", {"shot": "s1", "speaker": "Character 7", "words": long})
    assert got["problem"] == "Line l3 would carry shot s1 past 15.08 s"
    assert got["hints"] == {"shot": "s1", "max_words": 26, "suggested_end_ms": 15_080}
    got = await refused(ctx, "event_move", {"id": "l2", "start_ms": 2000})
    assert got == {"problem": "Line l2 would overlap line l1", "fix": "Move it where no other line of the shot is: "
                   "one speaker at a time", "hints": {"shot": "s1", "suggested_start_ms": 3642}}
    got = await refused(ctx, "event_move", {"id": "c1", "start_ms": 14_000})
    assert got == {"problem": "Cue c1 would fall outside shot s1's 15.08 s",
                   "fix": "Place it inside the shot: start it at latest_start_ms or earlier",
                   "hints": {"shot": "s1", "shot_max_end_ms": 15_080, "latest_start_ms": 5_643}}
    got = await refused(ctx, "pose_add", {"shot": "s1", "character": "Character 7", "pose": "point", "start_ms": 1000})
    assert got == {"problem": "Pose p8 of Character 7 starts inside Character 7's own line l1",
                   "fix": "Anchor it to that line's start, or give it a start_ms after the line's end",
                   "hints": {"shot": "s1", "line": "l1", "start_ms": 0, "end_ms": 3642}}
    got = await refused(ctx, "line_add", {"shot": "s9", "speaker": "Character 7", "words": "Hi."})
    assert got["hints"] == {"shots": ["s1", "s2"]}
    got = await refused(ctx, "shot_add", {"scene": 2, "camera": "Wide"})
    assert got["hints"] == {"scenes": [{"scene": 1, "title": "The opening"}]}
    got = await refused(ctx, "event_change", {"id": "x1", "fields": {"words": "Hi."}})
    assert got["hints"] == {"ids": ["p1", "p2", "l1", "l2", "p5", "p6", "c1", "p7", "p3", "p4"]}
    got = await refused(ctx, "pose_add", {"shot": "s1", "character": "Character 7", "pose": "dance"})
    assert got["hints"] == {"valid_poses": ["stand", "sit", "walk_step", "turn", "point", "arms_raised",
                                            "hand_to_face"]}
    got = await refused(ctx, "event_remove", {"id": "l1"})
    assert got == {"problem": "Line l1 has events anchored to it", "fix": "Remove or move those first",
                   "hints": {"anchored": ["c1"]}}
    got = await refused(ctx, "event_change", {"id": "l1", "fields": {"speaker": "Character 6"}})
    assert got["hints"] == {"fields": ["words", "language", "emotion", "pace"]}
    pushed = await call(ctx, "event_change", {"id": "l1", "fields": {"words": NINE + " " + NINE}})
    assert pushed["state"][2] == "moved l2, c1, p5–p7 +3.46 s; shots s2 +3.46 s", "l2 pushed"
    l2 = next(e for e in on_disk(ctx)["scenes"][0]["shots"][0]["events"] if e["id"] == "l2")
    assert l2["start_ms"] == 7103


async def test_no_script_open_and_a_version_1_script_are_refused(ctx: Ctx) -> None:
    got = await refused(ctx, "scene_add", {"title": "One", "cast": ["Character 7"]})
    assert got == {"problem": "No script is open", "fix": "Call script_start, or script_read with a name",
                   "hints": {}}
    folder = ctx.files.roots["scripts"]
    v2 = json.loads(FIXTURE.read_text())
    v1 = {"version": 1, "scenes": v2["scenes"]}
    (folder / "Old.json").write_text(json.dumps(v1))
    read = await call(ctx, "script_read", {"name": "Old"})
    assert read["read"][0] == "Old · 1 scenes · 3 shots · 24.00 s", "a version 1 script reads"
    got = await refused(ctx, "line_add", {"shot": "s1", "speaker": "Character 7", "words": "Hi."}, "Old")
    assert got == {"problem": "Old is a version 1 script", "fix": "Start a new script with script_start",
                   "hints": {}}


async def test_the_example_gets_shot_ids_on_its_first_write(ctx: Ctx) -> None:
    folder = ctx.files.roots["scripts"]
    shutil.copy(FIXTURE, folder / "Example.json")
    read = await call(ctx, "script_read", {"name": "Example"})
    assert [x.split(" · ")[0] for x in read["read"] if x[:2] in ("s1", "s2", "s3")] == ["s1", "s2", "s3"]
    assert "id" not in on_disk(ctx, "Example")["scenes"][0]["shots"][0], "a read writes nothing"
    await call(ctx, "cue_add", {"shot": "s3", "cue": "reaction", "words": "Laughter"})
    shots = on_disk(ctx, "Example")["scenes"][0]["shots"]
    assert [s["id"] for s in shots] == ["s1", "s2", "s3"]
    assert [e["id"] for e in shots[2]["events"] if e["kind"] == "cue"][-1] == "c5", "after the example's c1 to c4"


async def test_ids_are_never_reused_after_a_remove(ctx: Ctx) -> None:
    await framed(ctx)
    await call(ctx, "line_add", {"shot": "s2", "speaker": "Character 7", "words": "Hi."})
    await call(ctx, "event_remove", {"id": "l1"})
    again = await call(ctx, "line_add", {"shot": "s2", "speaker": "Character 7", "words": "Hello."})
    assert again["state"][1].startswith("line l2 ")
    await call(ctx, "shot_add", {"scene": 1, "camera": "Close on Character 7", "after": "s1"})
    shots = on_disk(ctx)["scenes"][0]["shots"]
    assert [s["id"] for s in shots] == ["s1", "s3", "s2"], "inserted after s1, a new number"
    assert [(s["start_ms"], s["end_ms"]) for s in shots] == [(0, 1000), (1000, 2000), (2000, 3000)], \
        "s2: l2 ends it, no keyframe filled at its end"
