"""A scene's judge step, pure. A take passes when every judge that ran passes (the words over
`scene_words_bar`, each face's median over `clip_face_bar` and not lost, the mouth moving with the words, the face's
size in the band the shot asked for); a silent shot is not judged on its mouth or words. A judge that did not run
is left out and named; none ran, the take passes. The ranks; the retake bound in measured seconds; the chips and the
scene's line."""
from __future__ import annotations

import copy
from types import SimpleNamespace
from typing import Any

from hub.core.api import Take
from hub.modules.generate_image.judgeshot import ShotJudge
from hub.settings import DEFAULTS

SPOKEN = {"subjects": [{"name": "Character 6"}], "camera": {"framing": "medium shot"},
          "lines": [{"speaker": "Character 6", "words": "Thank you, Character 7."}]}
SILENT = {"subjects": [{"name": "Character 7"}], "camera": {"framing": "wide shot"}}


def ctx(**settings: Any) -> Any:
    return SimpleNamespace(settings={**copy.deepcopy(DEFAULTS["modules"]["generate-image"]), **settings})


def face(median: float, first: float | None = None, last: float | None = None, lost_at: float | None = None) -> dict:
    return {"min": min(median, first or median), "median": median, "first": first if first is not None else median,
            "last": last if last is not None else median, "drift": 0.0, "lost_at": lost_at, "present": 1.0}


def judged(name: str = "Character 6", median: float = 0.44, lips: float | None = 0.71, moving: float = 0.6,
           heard: float | None = 1.0, size: float = 0.2, **f: Any) -> dict:
    out: dict = {"face": {name: face(median, **f)}, "frame": {name: {"size": size}},
                 "mouth": {"speaker": name, "lips": lips, "moving": moving}}
    if heard is not None:
        out["words"] = {"heard": heard, "first_miss": None}
    return out


def judge(*shots: dict, takes: int = 2, minutes: float = 15, **settings: Any) -> ShotJudge:
    plan, k = [], 1
    for _ in shots:
        plan.append(tuple((k + t,) for t in range(takes)))
        k += takes
    return ShotJudge(ctx(**settings), list(shots), tuple(plan), minutes * 60)


def test_a_take_that_holds_everything_passes_with_its_line():
    take, _ = judge(SPOKEN).verdict(judged(), 1)
    assert take.passes and take.rank == (1.0, 4.0, 1.1833333333333333)
    assert take.line == ("Character 6's face held (0.44); Character 6's mouth moves with the words (0.71); "
                         "heard 100% of the words")


def test_the_words_under_the_bar_fail_the_take():
    take, short = judge(SPOKEN).verdict(judged(heard=0.75), 1)
    assert not take.passes and short == "heard 75%" and take.line.endswith("heard 75% of the words")
    assert judge(SPOKEN, scene_words_bar=0.7).verdict(judged(heard=0.75), 1)[0].passes


def test_a_late_face_passes_on_its_median_and_a_lost_face_fails():
    late, _ = judge(SPOKEN).verdict(judged(median=0.4, first=0.21, last=0.5, lost_at=0.0), 1)
    assert late.passes and late.line.startswith("Character 6's face matched poorly at the start (0.21) and held by the "
                                                "end (0.50)")
    lost, short = judge(SPOKEN).verdict(judged(median=0.35, first=0.5, last=0.1, lost_at=2.1), 1)
    assert not lost.passes and short == "Character 6's face 0.35"
    assert lost.line.startswith("Character 6's face was lost after 2.1 s (0.50 → 0.10)")


def test_a_still_mouth_fails_and_a_frame_outside_the_band_fails():
    still, short = judge(SPOKEN).verdict(judged(moving=0.1, lips=0.7), 1)
    assert not still.passes and short == "Character 6's mouth is still"
    close = {**SPOKEN, "camera": {"framing": "close-up"}}
    framed, short = judge(close).verdict(judged(size=0.2), 1)
    assert not framed.passes and short == "Character 6's face size 0.20"
    assert "Character 6's face is 0.20 of the frame's height; the shot asked for a close-up" in framed.line


def test_a_silent_shot_is_not_judged_on_its_mouth_or_words():
    take, _ = judge(SILENT).verdict(judged("Character 7", lips=0.1, moving=0.05, heard=None, size=0.05), 1)
    assert take.passes and take.line == "Character 7's face held (0.44)" and take.rank[1] == 2.0


def test_a_judge_that_did_not_run_is_left_out_and_named():
    verdict = {"face": None, "why": "the face files are not in the engine", "mouth": {"speaker": "Character 6",
                                                                                     "lips": 0.71, "moving": 0.6},
               "words": {"heard": 0.5}}
    take, _ = judge(SPOKEN).verdict(verdict, 1)
    assert not take.passes, "the words judge ran and failed"
    assert take.line.endswith("The face judge did not run: the face files are not in the engine")
    nothing, _ = judge(SPOKEN).verdict({"face": None, "why": "no face found", "mouth_why": "no face"}, 1)
    assert nothing.passes and nothing.line == ("Not judged: The face judge did not run: no face found; The mouth "
                                               "judge did not run: no face; The words judge did not run")
    off, _ = judge(SPOKEN).verdict(None, 1)
    assert off.passes and off.line == "Not judged: no judge ran"


def test_ranks_order_passing_then_judges_passed_then_the_lowest_value():
    j = judge(SPOKEN)
    good, worse, worst = (j.verdict(v, 1)[0].rank for v in (judged(), judged(heard=0.7), judged(heard=0.5,
                                                                                                    median=0.2)))
    assert good > worse > worst


def test_a_retake_is_allowed_within_the_minutes_and_refused_past_them():
    j = judge(SPOKEN, SPOKEN, SPOKEN)                             # tasks: shot 1 = 1, 2; shot 2 = 3, 4; shot 3 = 5, 6
    j.done(1, {"task": 1, "seconds": 400.0})
    assert j.again(1, 2), "400 s of 900"
    j.done(2, {"task": 2, "seconds": 400.0})
    j.done(3, {"task": 3, "seconds": 600.0})
    assert not j.again(2, 2), "400 used + 600 measured would pass 15 min"
    j.done(5, {"task": 5, "seconds": 500.0})
    assert j.again(3, 2), "400 used + 500 measured: within"
    assert not judge(SPOKEN, minutes=0).again(1, 2), "scene_retake_minutes 0 refuses all"
    assert not ShotJudge(ctx(), [SPOKEN], (((1,), (2,)),), 900, again_ok=False).again(1, 2), "a redo never"


def test_done_gives_a_take_for_a_takes_first_task_alone():
    j = ShotJudge(ctx(), [SPOKEN], (((1, 2), (3, 4)),), 900)
    assert j.done(2, {"task": 2, "seconds": 3.0}) is None and j.seconds[2] == 3.0
    take = j.done(1, {"task": 1, "seconds": 60.0, "judge": judged()})
    assert take is not None and take.passes and j.seen[1] is take


def test_the_chips_and_the_scenes_line():
    j = judge(SPOKEN, SPOKEN, SPOKEN)
    j.done(1, {"task": 1, "seconds": 60.0, "judge": judged()})
    j.done(3, {"task": 3, "seconds": 60.0, "judge": judged(median=0.21, first=0.21, last=0.3, lost_at=0.0)})
    j.done(4, {"task": 4, "seconds": 90.0, "judge": judged()})
    j.done(5, {"task": 5, "seconds": 60.0, "judge": judged(moving=0.12)})
    j.done(6, {"task": 6, "seconds": 84.0, "judge": judged(moving=0.1)})
    landed = {1: "c/1.mp4", 3: "c/3.mp4", 4: "c/4.mp4", 5: "c/5.mp4", 6: "c/6.mp4"}
    line, chips = j.lines(landed, {1: 1, 2: 4, 3: 5})
    assert line == ("Shot 1 take 1; shot 2 take 2 (take 1: Character 6's face 0.21); shot 3 take 1, under the bar: "
                    "Character 6's face held (0.44); Character 6's mouth is still while speaking "
                    "(12% of the speaking frames move), "
                    "another take or a shorter line; heard 100% of the words (take 2: Character 6's mouth is still); "
                    "re-takes used 2.9 of 15 min")
    assert chips["c/3.mp4"].startswith("Take 1 · not used · Character 6's face matched poorly at the start (0.21)")
    assert chips["c/4.mp4"] == ("Take 2 · in the cut · Character 6's face held (0.44); Character 6's mouth moves with "
                                "the words (0.71); heard 100% of the words")
    failed = {**j.seen, 2: Take(False, (), "take 2 failed: Out of memory")}
    j.done(2, {"task": 2, "seconds": 30.0})
    line, _ = j.lines({1: "c/1.mp4"}, {1: 1, 2: None, 3: None}, failed)
    assert line.startswith("Shot 1 take 1 (take 2 failed: Out of memory); shot 2 not made (take 1: Character 6's face "
                           "0.21); shot 3 not made")


def line_judge(minutes: float = 15, **settings: Any):
    from hub.modules.generate_image.judgeshot import LineJudge
    return LineJudge(ctx(**settings), (((1,), (2,), (3,)),), minutes * 60)


def test_a_lines_take_passes_on_its_words_and_says_what_was_heard():
    """`LineJudge` passes at `speech_words_bar`; under it the line names the first miss; no reading:
    it passes and says the judge did not run."""
    good = line_judge().done(1, {"judge": {"words": {"heard": 0.95, "first_miss": None}}})
    assert good.passes and good.line == "Heard 95% of the words"
    j = line_judge()
    bad = j.done(1, {"judge": {"words": {"heard": 0.6, "first_miss": 1.2}}})
    assert not bad.passes and bad.line == "Heard 60% of the words; the first miss at 1.2 s"
    assert j.short[1] == "heard 60%"
    unheard = line_judge().done(1, {"judge": {"words": None}})
    assert unheard.passes and unheard.line == "The words judge did not run"
    assert line_judge().done(1, {}).line == "The words judge did not run", "the judge off: no reading"
    assert line_judge(speech_words_bar=0.5).done(1, {"judge": {"words": {"heard": 0.6, "first_miss": 1.2}}}).passes


def test_a_lines_rank_and_the_minutes_bound():
    j = line_judge()
    ranks = [j.verdict({"words": w}, 1)[0].rank for w in ({"heard": 0.95, "first_miss": None},
                                                           {"heard": 0.8, "first_miss": 3.0},
                                                           {"heard": 0.8, "first_miss": 1.0},
                                                           {"heard": 0.5, "first_miss": None})]
    assert ranks == sorted(ranks, reverse=True), "passing, then more heard, then no miss, then the later miss"
    j.done(1, {"seconds": 600.0})
    assert j.again(1, 2), "take 1's 10 min fit in the 15"
    j.done(2, {"seconds": 600.0})
    assert not j.again(1, 3), "10 min of re-takes + take 1's 10 are over 15"
    assert not line_judge(minutes=0).again(1, 2)


def test_a_kept_sound_clip_is_judged_on_the_mouth_not_the_words():
    """A clip that speaks a kept sound has lines with no words: the mouth is judged, the words left out
    and not named."""
    kept = {**SPOKEN, "lines": [{"speaker": "Character 6", "words": ""}]}
    take, _ = judge(kept).verdict(judged(heard=None), 1)
    assert take.passes and take.line == \
        "Character 6's face held (0.44); Character 6's mouth moves with the words (0.71)"
    still, _ = judge(kept).verdict(judged(heard=None, moving=0.05, lips=None), 1)
    assert not still.passes and "mouth is still" in still.line


def placed(words: tuple[float, float] | None, spans: tuple[float, float] | None, **kw: Any) -> dict:
    """A take whose words sit at `words` and whose speech spans run `spans`."""
    out = judged(**kw)
    if spans is not None:
        out["mouth"] = {**out["mouth"], "speech_from": spans[0], "speech_to": spans[1]}
    if words is not None:
        out["words"] = {**out["words"], "first": words[0], "last": words[1]}
    return out


def test_speech_that_is_not_the_line_fails_the_take_and_says_how_much():
    take, short = judge(SPOKEN).verdict(placed((5.0, 9.6), (0.2, 9.8)), 1)
    assert not take.passes and short == "Character 6 5.0 s not the line"
    assert take.line.endswith("heard 100% of the words; Character 6 makes 5.0 s of speech that is not the line")
    assert take.rank[0] == 0.0 and take.rank[2] == 2.5 / 5.0, "ranked by bar ÷ value"
    assert judge(SPOKEN, scene_unscripted_seconds=6.0).verdict(placed((5.0, 9.6), (0.2, 9.8)), 1)[0].passes


def test_speech_that_is_only_the_line_passes_as_today():
    take, _ = judge(SPOKEN).verdict(placed((1.1, 9.0), (0.9, 9.2)), 1)
    today, _ = judge(SPOKEN).verdict(judged(), 1)
    assert take == today


def test_a_missing_reading_leaves_the_unscripted_judge_out():
    today, _ = judge(SPOKEN).verdict(judged(), 1)
    for words, spans in (((5.0, 9.6), None), (None, (0.2, 9.8)), ((None, None), (0.2, 9.8))):
        assert judge(SPOKEN).verdict(placed(words, spans), 1)[0] == today
    silent, _ = judge(SILENT).verdict(placed((5.0, 9.6), (0.2, 9.8), name="Character 7", size=0.05), 1)
    assert silent.passes, "a shot with no lines: not judged on its speech"
