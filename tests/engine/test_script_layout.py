"""Where the script tools place events (`hub/modules/director/layout.py`): a line's length from its words
at the pace plus the turn pause (9 words at 2.6 -> 3 642 ms), lines one after another, a shot growing moves every
later shot and its events, an anchored pose follows its line, a pose holds until the next, the 15 080 ms cap."""
from __future__ import annotations

import copy
import json

import pytest

from hub.core.api import Invalid
from hub.modules.director import edit, frame, layout, remove

NINE = "Line one opens here, and the rest needs more."


def script() -> dict:
    return {"version": 2, "context": {"cast": [{"name": "Character 7"}, {"name": "Character 6"}]},
            "scenes": [{"title": "The scene", "cast": ["Character 7", "Character 6"], "shots": []}]}


def shot(s: dict, sid: str) -> dict:
    return edit.find_shot(s, sid)[1]


def ev(s: dict, ident: str) -> dict:
    return edit.find_event(s, ident)[2]


def refusal(fn, *args) -> dict:  # type: ignore[no-untyped-def]
    with pytest.raises(Invalid) as e:
        fn(*args)
    return json.loads(e.value.text)


def two_shots() -> tuple[dict, dict]:
    s, c = script(), {}
    frame.shot_add(s, c, {"scene": 1, "camera": "Wide"})
    frame.shot_add(s, c, {"scene": 1, "camera": "Close on Character 6"})
    return s, c


def test_a_line_lasts_its_words_at_the_pace_plus_the_turn_pause() -> None:
    assert layout.line_ms(NINE) == 3642
    assert layout.line_ms(NINE, 3.0) == 3180
    assert layout.max_words(15_080) == 38 and layout.max_words(100) == 0


def test_empty_shots_lie_end_to_end_one_second_each() -> None:
    s, _ = two_shots()
    assert [(x["id"], x["start_ms"], x["end_ms"]) for x in layout.shots(s)] == [("s1", 0, 1000), ("s2", 1000, 2000)]


def test_lines_follow_each_other_and_the_shot_grows_moving_the_later_shots() -> None:
    s, c = two_shots()
    edit.line_add(s, c, {"shot": "s2", "speaker": "Character 6", "words": "Thank you."})
    line = ev(s, "l1")
    assert (line["start_ms"], line["end_ms"]) == (1000, 1000 + layout.line_ms("Thank you."))
    edit.line_add(s, c, {"shot": "s1", "speaker": "Character 7", "words": NINE})
    edit.line_add(s, c, {"shot": "s1", "speaker": "Character 6", "words": NINE, "pace": 3.0})
    a, b = ev(s, "l2"), ev(s, "l3")
    assert (a["start_ms"], a["end_ms"], b["start_ms"], b["end_ms"]) == (0, 3642, 3642, 6822)
    assert (shot(s, "s1")["start_ms"], shot(s, "s1")["end_ms"]) == (0, 6822)
    moved = shot(s, "s2")
    assert (moved["start_ms"], ev(s, "l1")["start_ms"]) == (6822, 6822), "the later shot and its line moved along"
    assert moved["end_ms"] == 6822 + 1000, "a shot is at least one second"


def test_a_cue_goes_after_the_last_line_and_lasts_two_seconds() -> None:
    s, c = two_shots()
    edit.cue_add(s, c, {"shot": "s1", "cue": "music", "words": "A sting"})
    edit.line_add(s, c, {"shot": "s1", "speaker": "Character 7", "words": NINE})
    edit.cue_add(s, c, {"shot": "s1", "cue": "reaction", "words": "Applause"})
    assert [(ev(s, i)["start_ms"], ev(s, i)["end_ms"]) for i in ("c1", "l1", "c2")] == [(0, 2000), (0, 3642),
                                                                                       (3642, 5642)]
    assert shot(s, "s1")["end_ms"] == 5642


def test_an_anchored_pose_follows_its_line_and_a_pose_holds_until_the_next() -> None:
    s, c = two_shots()
    edit.cue_add(s, c, {"shot": "s1", "cue": "music", "words": "A sting"})
    edit.line_add(s, c, {"shot": "s1", "speaker": "Character 7", "words": "Hello."})
    edit.pose_add(s, c, {"shot": "s1", "character": "Character 7", "pose": "stand"})
    edit.pose_add(s, c, {"shot": "s1", "character": "Character 6", "pose": "sit",
                         "anchor": {"line": "l1", "at": "end"}})
    edit.pose_add(s, c, {"shot": "s1", "character": "Character 7", "pose": "point",
                         "anchor": {"line": "l1", "at": "end"}})
    end, l1 = shot(s, "s1")["end_ms"], ev(s, "l1")["end_ms"]
    assert end == l1 + 500 + layout.POSE_MIN_MS, "the speaker's pose 500 ms after l1 is seen a second, past the cue"
    assert (ev(s, "p2")["start_ms"], ev(s, "p2")["end_ms"], ev(s, "p2")["anchor"]) == (l1, end, {"line": "l1",
                                                                                                    "at": "end"})
    assert (ev(s, "p1")["start_ms"], ev(s, "p1")["end_ms"]) == (0, l1 + 500), \
        "at the speaker's own line end: 500 ms after"
    assert ev(s, "p3")["start_ms"] == l1 + 500 and "anchor" not in ev(s, "p3") and ev(s, "p3")["end_ms"] == end
    got = refusal(edit.event_change, copy.deepcopy(s), {"id": "l1", "fields": {"words": NINE}})
    assert got["problem"] == "Pose p3 of Character 7 starts inside Character 7's own line l1" and \
        got["hints"]["after_ms"] == 4142
    remove.event_remove(s, {"id": "p3"})
    edit.event_change(s, {"id": "l1", "fields": {"words": NINE}})
    assert ev(s, "p2")["start_ms"] == 3642 and ev(s, "p1")["end_ms"] == shot(s, "s1")["end_ms"], \
        "the anchored pose followed"
    assert shot(s, "s1")["end_ms"] == 3642 + layout.POSE_MIN_MS, "the last pose is seen a second"
    edit.pose_add(s, c, {"shot": "s1", "character": "Character 7", "pose": "point",
                         "anchor": {"line": "l1", "at": "end"}})
    assert ev(s, "p4")["start_ms"] == 4142 and shot(s, "s1")["end_ms"] == 5142, "500 ms after"
    assert shot(s, "s2")["start_ms"] == 5142
    assert refusal(edit.event_move, copy.deepcopy(s), {"id": "l1", "start_ms": 2500})["hints"]["after_ms"] == 6642
    remove.event_remove(s, {"id": "p4"})
    edit.event_move(s, {"id": "l1", "start_ms": 2500})
    assert ev(s, "p2")["start_ms"] == 2500 + 3642, "it follows a moved line too"


def test_the_cap_is_one_pass() -> None:
    s, c = two_shots()
    for _ in range(3):
        edit.line_add(s, c, {"shot": "s1", "speaker": "Character 7", "words": NINE})
    edit.line_add(s, c, {"shot": "s1", "speaker": "Character 6", "words": "Yes."})
    room = layout.SHOT_MAX_MS - shot(s, "s1")["end_ms"]
    got = refusal(edit.line_add, copy.deepcopy(s), dict(c), {"shot": "s1", "speaker": "Character 7", "words": NINE})
    assert got["problem"] == "Line l5 would carry shot s1 past 15.08 s"
    assert got["fix"] == "Split the words across two shots: shot_add, then line_add the rest there"
    assert got["hints"] == {"shot": "s1", "max_words": layout.max_words(room), "suggested_end_ms": layout.SHOT_MAX_MS}
    edit.line_add(s, c, {"shot": "s1", "speaker": "Character 7", "words": "One two three four five six seven eight."})
    assert shot(s, "s1")["end_ms"] <= layout.SHOT_MAX_MS
