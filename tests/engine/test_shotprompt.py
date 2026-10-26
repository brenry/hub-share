"""The Director's first cut: the assistant fills a `shot`, the Hub writes the prompt. Goldens for Ref2VA (six
fields: two boxed subjects and a line; a described subject) and FL2VA (three fields: a start frame; a kept sound);
each one-line refusal; the length from the lines on the lattice; `shot` and `draft` clearing each other; a plain
draft. The catalog is the worker's own for upstream's H3 capture (`test_upstream_rules`)."""
from __future__ import annotations

import re
from typing import Any

import pytest
from PIL import Image

from hub.core.api import Invalid
from hub.core.files import Files
from hub.modules.generate_image import build, chain, models, routes, screen, shotcheck, shotprompt
from tests.engine.helpers import FakeCtx, FakeEngine
from tests.engine.test_generate_image import Bus, call
from tests.engine.test_upstream_rules import FL2VA, REF2VA, cat  # noqa: F401  (the dumped catalog fixture)

CHARACTER_7 = {"id": "chars/Character 7.png", "w": 600, "h": 900}
CHARACTER_16 = {"id": "chars/Character 16.png", "w": 600, "h": 900}
LINE = "Line one is said now."



@pytest.fixture
def ctx(cat, tmp_path, monkeypatch):  # noqa: F811
    from hub.modules.generate_image import models
    monkeypatch.setattr(models, "_last", cat)
    c = FakeCtx("generate-image", tmp_path / "data", FakeEngine(cat), {"image": build.image_job})
    folder = tmp_path / "Characters"
    folder.mkdir()
    for name in ("Character 7.png", "Character 16.png"):
        Image.new("RGB", (600, 900)).save(folder / name)
    c.files = Files(tmp_path / "data", None, folder)
    c.bus = Bus()
    return c


def pick(ctx: Any, model: str, *boxes: dict, sound: dict | None = None) -> None:
    """The model picked and the boxes (and the Sound box) filled, as the window does."""
    ctx.doc(routes.DRAFT, {}).replace({"model": model})
    routes.session_part(ctx).update(references=list(boxes), sound=sound)


def shot(**extra: Any) -> dict:
    return {"subjects": [{"name": "Character 7", "look": "in a grey suit"}, {"name": "Character 16"}],
            "where": "a bare stage under hot lights", "camera": {"framing": "medium shot", "move": "slow push in"},
            "action": ["Character 7 walks to the front of the stage", "the character points at the camera"],
            "lines": [{"speaker": "Character 7", "words": LINE}], **extra}


async def put(ctx: Any, value: dict) -> dict:
    return await call(ctx, "set_generate_image_settings", {"shot": value})


async def refused(ctx: Any, value: dict) -> str:
    with pytest.raises(Invalid) as err:
        await put(ctx, value)
    return err.value.text


REF2VA_GOLDEN = (
    "subject_definitions: <Subject 1> is Character 7, from <Picture 1>; <Subject 2> is Character 16, "
    "from <Picture 2>.\n"
    "summary: [reference generation] Character 7 walks to the front of the stage.\n"
    "retention_analysis: <Subject 1> (appears in [Shot 1]): fully_preserved - Character 7.\n"
    "<Subject 2> (appears in [Shot 1]): fully_preserved - Character 16.\n"
    "detailed_description: a bare stage under hot lights. [Shot 1] (S1) <Subject 1>, in a grey suit. "
    "(S2) <Subject 2>. medium shot. slow push in. Character 7 walks to the front of the stage. the character points "
    "at the camera. "
    f"(S1) <Subject 1> says <d>{LINE}</d>.\n"
    "overall_soundscape: N/A\n"
    "non_diegetic_music: N/A")


async def test_ref2va_two_boxed_subjects_and_a_line(ctx):
    pick(ctx, REF2VA, CHARACTER_7, CHARACTER_16)
    seen = await put(ctx, shot())
    assert seen["draft"] == REF2VA_GOLDEN
    assert seen["shot"]["lines"][0]["words"] == LINE
    assert seen["frames"] == 124 and seen["seconds"] == round(124 / 24, 2), "4.5 s of line + 1 s, up the lattice"


REF2VA_VOICED = (
    "subject_definitions: <Subject 1> is Character 7, from <Picture 1>; <Subject 2> is Character 16, from <Picture 2>. "
    "<Audio 1> is the voice-timbre reference for <Subject 1> (S1).\n"
    "summary: [reference generation + audio reference] Character 7 walks to the front of the stage.\n"
    "retention_analysis: <Subject 1> (appears in [Shot 1]): fully_preserved - Character 7.\n"
    "<Subject 2> (appears in [Shot 1]): fully_preserved - Character 16.\n"
    "<Audio 1>: reference\n"
    "detailed_description: a bare stage under hot lights. [Shot 1] (S1) <Subject 1>, in a grey suit. "
    "(S2) <Subject 2>. medium shot. slow push in. Character 7 walks to the front of the stage. the character points "
    "at the camera. "
    f"(S1) <Subject 1> says, in the voice referenced from <Audio 1>, <d>{LINE}</d>.\n"
    "overall_soundscape: N/A\n"
    "non_diegetic_music: N/A")


async def test_ref2va_a_speaker_with_a_voice_sample_is_voiced_from_audio_1(ctx):
    """The six fields with the audio reference; a second speaker without a sample in H3's own voice; without
    the sample, or on the convert route, the plain golden."""
    from tests.fakes.wav import tiny_wav
    ctx.settings["voice_route"] = "reference"                 # the `reference` route; convert at the end
    wav = ctx.files.existing_media("chars/Character 7.png").with_suffix(".wav")
    wav.write_bytes(tiny_wav(seconds=3.0))
    pick(ctx, REF2VA, CHARACTER_7, CHARACTER_16)
    assert (await put(ctx, shot()))["draft"] == REF2VA_VOICED
    two = shot(lines=[{"speaker": "Character 7", "words": "Hi."}, {"speaker": "Character 16", "words": "Hello."}])
    text = (await put(ctx, two))["draft"]
    assert text.startswith(REF2VA_VOICED.split("\nsummary:")[0])
    assert text.count("<Audio") == 3 and "<Audio 2>" not in text
    assert "(S1) <Subject 1> says, in the voice referenced from <Audio 1>, <d>Hi.</d>. " \
           "(S2) <Subject 2> says <d>Hello.</d>." in text
    wav.unlink()
    assert (await put(ctx, shot()))["draft"] == REF2VA_GOLDEN
    wav.write_bytes(tiny_wav(seconds=3.0))
    ctx.settings["voice_route"] = "convert"
    assert (await put(ctx, shot()))["draft"] == REF2VA_GOLDEN, "converted after the render: no <Audio> in the prompt"


async def test_ref2va_a_described_subject_is_its_speaker_id_in_the_text_only(ctx):
    pick(ctx, REF2VA, CHARACTER_7)
    value = shot(subjects=[{"name": "Character 7"}, {"name": "Speaker 2"}],
                 lines=[{"speaker": "Speaker 2", "words": "Line 2?", "language": "French"}],
                 sound={"ambience": "an audience murmur", "music": "a soft jazz bed"}, ending="Character 7 freezes")
    text = (await put(ctx, value))["draft"]
    assert text.startswith("subject_definitions: <Subject 1> is Character 7, from <Picture 1>.\n")
    assert "(S2) Speaker 2. " in text
    assert "(S2) Speaker 2 says <d>[French] Line 2?</d>. Character 7 freezes.\n" in text, \
        "a language the line names in its brackets; the ending after the lines, nothing between"
    assert text.endswith("overall_soundscape: an audience murmur.\nnon_diegetic_music: a soft jazz bed"), \
        "the ambience as written"


FL2VA_GOLDEN = (
    "For the target video, at 0.00 seconds into the target video, <Picture 1> (from [Shot 1]) is fully referenced.\n"
    "integrated_multimodal_description: [Shot 1] a bare stage under hot lights. (S1) Character 7, in a grey suit. "
    "(S2) Character 16. medium shot. slow push in. Character 7 walks to the front of the stage. the character points "
    "at the camera. "
    f"(S1) Character 7 says <d>{LINE}</d>. [Shot 2] At 00:02.500, a close-up of Character 16.\n"
    "overall_soundscape: N/A\n"
    "non_diegetic_music: N/A")


async def test_fl2va_a_start_frame_takes_the_alignment_sentence(ctx):
    pick(ctx, FL2VA, CHARACTER_7)
    assert (await put(ctx, shot(cuts=[{"at": 2.5, "to": "a close-up of Character 16"}])))["draft"] == FL2VA_GOLDEN


async def test_fl2va_with_a_sound_asks_for_lip_movement_and_no_lines(ctx):
    pick(ctx, FL2VA, sound={"id": "sounds/line.wav", "seconds": 6.0})
    text = (await put(ctx, shot(lines=[])))["draft"]
    assert text == ("integrated_multimodal_description: [Shot 1] a bare stage under hot lights. "
                    "(S1) Character 7, in a grey suit. (S2) Character 16. medium shot. slow push in. "
                    "Character 7 walks to the front of the stage. the character points at the camera. "
                    "Character 7 is speaking with natural lip movements synchronized.\n"
                    "overall_soundscape: N/A\nnon_diegetic_music: N/A")
    assert "<d>" not in text and "advancedByModel" not in ctx.doc(routes.DRAFT, {}).get(), "the sound decides"
    assert await refused(ctx, shot()) == shotcheck.SOUND_WORDS


async def test_each_refusal_is_one_line_before_any_job(ctx):
    pick(ctx, REF2VA, CHARACTER_7)
    await put(ctx, shot())                          # Character 16, in Characters, goes into box 2
    assert [r["id"] for r in routes.session_part(ctx)["references"]] == ["chars/Character 7.png",
                                                                         "chars/Character 16.png"]
    pick(ctx, REF2VA, CHARACTER_7, CHARACTER_16)
    assert await refused(ctx, shot(lines=[{"speaker": "Character 4",
                                           "words": "Hi."}])) == "Character 4 speaks but is not a subject"
    for words in ("<d>[English] Hi.</d>", "Speaker 1: Hi.", "[shouting]"):
        assert await refused(ctx, shot(lines=[{"speaker": "Character 7", "words": words}])) == shotcheck.LINE_ONLY
    assert await refused(ctx, shot(cuts=[{"at": 3, "to": "x"}, {"at": 2, "to": "y"}])) == shotcheck.CUTS
    assert await refused(ctx, shot(cuts=[{"at": 30, "to": "x"}])) == shotcheck.CUTS
    many = [{"speaker": "Character 7", "words": " ".join(["word"] * 40) + "."}] * 3
    assert await refused(ctx, shot(lines=many)) == "The lines need 51.9 s and one clip holds 15.1 s: cut 96 words"
    with pytest.raises(Invalid, match="additional|unknown"):
        await put(ctx, {**shot(), "mood": "tense"})
    both = await call(ctx, "set_generate_image_settings", {"shot": shot(), "draft": "x"})
    assert both["draft"].startswith("subject_definitions:"), "a shot sent with a draft wins"
    pick(ctx, "z_image")
    assert (await refused(ctx, shot())).endswith("makes no clip; a shot is for a video model")
    assert not ctx.jobs.jobs, "nothing queued"


async def test_shot_and_draft_clear_each_other_and_a_plain_draft_is_as_today(ctx):
    pick(ctx, REF2VA, CHARACTER_7, CHARACTER_16)
    await put(ctx, shot())
    plain = await call(ctx, "set_generate_image_settings", {"draft": "A plain prompt."})
    assert (plain["draft"], plain["shot"]) == ("A plain prompt.", None)
    await put(ctx, shot())
    assert routes.session_part(ctx)["shot"] is not None
    await routes.put_draft(ctx, Req({"draft": ""}))
    assert routes.session_part(ctx).get("shot") is None, "the panel's Clear makes it a plain draft again"
    await routes.on_chat_cleared(ctx, {})
    assert screen.draft(ctx) == ""


async def test_the_press_renders_the_compiled_prompt(ctx):
    pick(ctx, REF2VA, CHARACTER_7, CHARACTER_16)
    await put(ctx, shot())
    await call(ctx, "generate_image", {})
    [(_, params)] = ctx.jobs.jobs.values()
    assert params["prompt"] == REF2VA_GOLDEN and params["frames"] == 124


def spoken(words: int, stops: int) -> str:
    """A line of `words` words ending in `stops` sentences."""
    cut = [round(words * k / stops) for k in range(stops + 1)]
    return " ".join(" ".join(["word"] * (b - a)) + "." for a, b in zip(cut, cut[1:], strict=False))


async def test_the_clip_is_as_long_as_its_story(ctx):
    """The budget passes and one word more is refused with the amount; `seconds` lengthens a clip and
    never shortens it; over the top is refused; a kept sound decides; neither: the Seconds setting."""
    pick(ctx, REF2VA, CHARACTER_7, CHARACTER_16)
    model = models.find(models.cached(), REF2VA)
    where = shotcheck.frame(ctx, model, "Omni")
    assert shotcheck.budget(ctx, model, where) == (31, 4) and round(shotcheck.top(ctx, model, where), 2) == 15.08
    assert (await put(ctx, shot(lines=[{"speaker": "Character 7", "words": spoken(31, 4)}])))["frames"] == 362
    assert await refused(ctx, shot(lines=[{"speaker": "Character 7", "words": spoken(32, 4)}])) == \
        "The lines need 15.4 s and one clip holds 15.1 s: cut 1 words"
    two = [{"speaker": "Character 7", "words": "Hi there."}]                              # 2.6 s with the lead
    assert (await put(ctx, shot(lines=two, seconds=10)))["frames"] == 243
    six = [{"speaker": "Character 7", "words": spoken(10, 2)}]                            # 6.6 s
    assert (await put(ctx, shot(lines=six, seconds=2)))["frames"] == (await put(ctx, shot(lines=six)))["frames"] == 175
    assert await refused(ctx, shot(seconds=16)) == "seconds is 16.0 and one clip holds 15.1 s"
    assert (await put(ctx, shot(lines=[], seconds=10)))["frames"] == 243, "the action alone"
    assert shotcheck.frames(ctx, model, shot(lines=[]), where) is None, "no lines, no seconds: the Seconds setting"
    assert (await put(ctx, shot(seconds=8)))["draft"] == REF2VA_GOLDEN, "the compiler does not read it"
    pick(ctx, FL2VA, sound={"id": "sounds/line.wav", "seconds": 6.0})
    fl2va = models.find(models.cached(), FL2VA)
    assert shotcheck.frames(ctx, fl2va, shot(lines=[], seconds=12), shotcheck.frame(ctx, fl2va, "FL2VA")) is None
    await put(ctx, shot(lines=[], seconds=12))
    assert "advancedByModel" not in ctx.doc(routes.DRAFT, {}).get(), "no frames set: the press takes the sound's"


def test_on_a_continue_the_top_is_the_step_and_the_budget_follows(ctx):
    """Ref2VA's step (481 less the overlap) is over its 362; a model whose step is under its fresh top is cut to it."""
    found = models.find(models.cached(), REF2VA)
    assert shotcheck.top(ctx, found, shotprompt.Frame(True, {}, False, True, False, {})) == 362 / 24
    model = {**found, "video": {**found["video"], "window_max": 300}}
    clip = models.video(model)
    fresh = shotprompt.Frame(True, {}, False, False, False, {})
    step = shotprompt.Frame(True, {}, False, True, False, {})
    cap = clip["window_max"] - chain.overlap(model) + 1
    lo, k = clip["frames"]["min"], clip["frames"]["step"]
    most = shotcheck.top(ctx, model, step)
    assert most == (lo + (cap - lo) // k * k) / clip["fps"] < shotcheck.top(ctx, model, fresh)
    words, _ = shotcheck.budget(ctx, model, step)
    assert words < 31 and shotcheck.need([{"words": spoken(words, -(-words // 8))}], None) <= shotcheck.top(
        ctx, model, step) < shotcheck.need([{"words": spoken(words + 1, -(-(words + 1) // 8))}], None)


class Req:
    def __init__(self, body: dict) -> None:
        import json
        self._raw = json.dumps(body).encode()

    async def body(self) -> bytes:
        return self._raw


def plan_of(*ends: float, fps: int = 24) -> dict:
    """A plan whose windows end at `ends` seconds (window 1 whole, later ones their new frames)."""
    windows, at = [], 0.0
    for n, end in enumerate(ends, 1):
        new = round((end - at) * fps)
        windows.append({"n": n, "frames": new if n == 1 else new + 17, "seconds": (new if n == 1 else new + 17) / fps,
                        "new_frames": new, "new_shot": False, "pictures": []})
        at = end
    return {"valid": True, "windows": windows, "total_seconds": at, "warnings": [], "errors": [], "notes": []}


def test_a_cut_lands_on_a_window_boundary_or_is_refused_naming_the_window():
    plan = plan_of(5.0, 9.5)
    shotcheck.cuts_on_plan({"cuts": [{"at": 5.0, "to": "x"}]}, plan)
    shotcheck.cuts_on_plan({"cuts": [{"at": 5.04, "to": "x"}]}, plan)
    shotcheck.cuts_on_plan({"cuts": [{"at": 7.0, "to": "x"}]}, None)
    shotcheck.cuts_on_plan({"cuts": [{"at": 7.0, "to": "x"}]}, {"windows": [plan["windows"][0]]})
    with pytest.raises(Invalid) as err:
        shotcheck.cuts_on_plan({"cuts": [{"at": 2.0, "to": "x"}, {"at": 7.0, "to": "y"}]}, plan)
    assert err.value.text == "Cut 1 at 2 s is inside window 1 (0.00 to 5.00 s); move it to 5.00 s or split the shot"
    with pytest.raises(Invalid) as err:
        shotcheck.cuts_on_plan({"cuts": [{"at": 8.0, "to": "y"}]}, plan)
    assert err.value.text == "Cut 1 at 8 s is inside window 2 (5.00 to 9.50 s); move it to 9.50 s or split the shot"


async def test_a_shot_with_a_cut_off_the_plan_is_refused_and_the_draft_cleared(ctx):
    pick(ctx, FL2VA, CHARACTER_7)
    ctx.engine.plan = plan_of(5.0, 9.5)
    kept = await put(ctx, shot(cuts=[{"at": 5.0, "to": "a close-up of Character 16"}]))
    assert kept["plan"] == ctx.engine.plan and kept["draft"].count("[Shot 2] At 00:05.000") == 1
    with pytest.raises(Invalid) as err:
        await put(ctx, shot(cuts=[{"at": 2.5, "to": "a close-up of Character 16"}]))
    assert err.value.text.startswith("Cut 1 at 2.5 s is inside window 1")
    seen = await call(ctx, "get_generate_image_settings", {})
    assert seen["draft"] == "" and not seen.get("shot"), "the shot and its draft are cleared"
    ctx.settings = {**ctx.settings, "plan_before_render": False}
    assert (await put(ctx, shot(cuts=[{"at": 2.5, "to": "a close-up of Character 16"}])))["draft"]


# the engine's syntax (§4.3) that may stand around the fields, and nothing else of the Hub's.
_SYNTAX = [re.compile(p, re.MULTILINE) for p in (                  # the longer forms first
    r"^(?:subject_definitions|summary|retention_analysis|detailed_description|overall_soundscape|non_diegetic_music|"
    r"integrated_multimodal_description): ", re.escape(shotprompt.ALIGN), r"<Audio \d+>: reference$",
    r"\(appears in \[Shot 1\]\): fully_preserved(?: - )?", r"says, in the voice referenced from <Audio \d+>,",
    r" is the voice-timbre reference for ", r"\[Shot \d+\](?: At \d\d:\d\d\.\d{3},?)?", r", (?=<)", r"\(S\d+\)",
    r"<(?:Subject|Picture|Audio) \d+>", r"\[[a-z +]+\]", r"\bsays\b", r"<d>(?:\[ *\] )?", r"</d>", r" is ",
    r", from ", r"; ", r"N/A")]


def hubs_own(text: str, fields: list[str]) -> str:
    """What is left of a compiled prompt with every field's text and every §4.3 token taken out."""
    for t in sorted(fields, key=len, reverse=True):
        text = re.sub(r", (?=" + re.escape(t) + ")", " ", text).replace(t, " ")
    for p in _SYNTAX:
        text = p.sub(" ", text)
    return text


def every_field(lines: bool) -> tuple[dict, list[str]]:
    words = [f"Field {n:02d}" for n in range(1, 13)]
    one = {"subjects": [{"name": "Character 1", "look": words[0]}, {"name": "Character 2"}], "where": words[1],
           "light": words[2], "camera": {"framing": words[3], "move": words[4]}, "action": [words[5], words[6]],
           "cuts": [{"at": 2.5, "to": words[7]}], "ending": words[8],
           "sound": {"ambience": words[9], "music": words[10]}}
    if lines:
        one["lines"] = [{"speaker": "Character 1", "words": words[11], "language": "Language 1"},
                        {"speaker": "Character 2", "words": "Line 2"}]
    return one, [*words, "Character 1", "Character 2", "Language 1", "Line 2"]


@pytest.mark.parametrize("lines", [True, False])
@pytest.mark.parametrize("where", [
    shotprompt.Frame(True, {"character 1": (1, (1,)), "character 2": (2, (2, 3))}, voices={"character 1": 1}),
    shotprompt.Frame(True, {"character 1": (1, (1,))}),
    shotprompt.Frame(False, {}, start=True)])
def test_no_sentence_of_the_hubs_reaches_the_clip(lines, where):
    one, fields = every_field(lines)
    text = shotprompt.compile_shot(one, where)
    left = hubs_own(text, fields)
    assert set(left) <= {" ", ".", "\n"}, f"the Hub's own text: {left!r} in {text!r}"
    assert "Language 1" in text and "<d>Line 2</d>" in text if lines else "<d>" not in text


def test_an_empty_field_sends_nothing():
    one = {"subjects": [{"name": "Character 1"}]}
    six = shotprompt.compile_shot(one, shotprompt.Frame(True, {"character 1": (1, (1,))}))
    assert "\nsummary: [reference generation]\n" in six and "\noverall_soundscape: N/A\n" in six
    three = shotprompt.compile_shot(one, shotprompt.Frame(False, {}))
    assert three == ("integrated_multimodal_description: [Shot 1] (S1) Character 1.\n"
                     "overall_soundscape: N/A\nnon_diegetic_music: N/A")
