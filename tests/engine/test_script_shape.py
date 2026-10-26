"""The script format (`hub/modules/director/scriptshape.py`, version 2): the shipped
example reads, and every check refuses with one line naming where."""
from __future__ import annotations

import copy
import json
from collections.abc import Callable
from pathlib import Path

import pytest

from hub.core.api import Invalid
from hub.modules.director import scriptshape

FIXTURE = Path(__file__).parents[1] / "fixtures" / "script-1.json"   # the neutral script the tests read
EXAMPLE = json.loads(FIXTURE.read_text(encoding="utf-8"))
CHARS = {"character 1", "character 2"}             # Characters holding both members' pictures


def events(script: dict) -> list[dict]:
    return [ev for sc in script["scenes"] for shot in sc["shots"] for ev in shot["events"]]


def test_the_shipped_example_reads() -> None:
    script = scriptshape.read(copy.deepcopy(EXAMPLE), CHARS)
    assert scriptshape.length_ms(script) == 24_000
    assert scriptshape.counts(script) == {"scenes": 1, "shots": 3, "lines": 3}
    kinds = [ev["kind"] for ev in events(script)]
    assert (kinds.count("line"), kinds.count("cue"), kinds.count("pose")) == (3, 4, 11)
    assert {ev["pose"] for ev in events(script) if ev["kind"] == "pose"} == set(scriptshape.POSES)
    assert [ev["cue"] for ev in events(script) if ev["kind"] == "cue"] == ["music", "reaction", "effect", "reaction"]
    assert script["scenes"][0]["cast"] == ["Character 1", "Character 2"]


def ev_of(script: dict, ident: str) -> dict:
    return next(ev for ev in events(script) if ev["id"] == ident)


def set_(path: Callable[[dict], dict], key: str, value: object) -> Callable[[dict], None]:
    def change(s: dict) -> None:
        path(s)[key] = value
    return change


def drop(path: Callable[[dict], dict], key: str) -> Callable[[dict], None]:
    def change(s: dict) -> None:
        del path(s)[key]
    return change


def top(s: dict) -> dict:
    return s


def scene(s: dict) -> dict:
    return s["scenes"][0]


def shot(k: int) -> Callable[[dict], dict]:
    return lambda s: s["scenes"][0]["shots"][k]


def ev(ident: str) -> Callable[[dict], dict]:
    return lambda s: ev_of(s, ident)


def v1(change: Callable[[dict], None]) -> Callable[[dict], None]:
    """The change on the example as version 1 (no context): what version 1 refuses, a version-2 script being written may
    hold."""
    def both(s: dict) -> None:
        del s["context"]
        s["version"] = 1
        change(s)
    return both


S1, S2, L1 = "Scene 1", "Scene 1, shot 2", "Scene 1, shot 1, event l1"
SPAN = "start_ms and end_ms are whole milliseconds, 0 ≤ start_ms < end_ms"
CASES = [
    (set_(top, "version", 3), "The script's version is 1 or 2"),
    (set_(top, "version", True), "The script's version is 1 or 2"),
    (set_(top, "extra", 1), "The script has a key the format does not know: extra"),
    (drop(top, "scenes"), "The script has no scenes"),
    (v1(set_(top, "scenes", [])), "The script has no scene"),
    (v1(set_(scene, "shots", [])), f"{S1}: the scene has no shot"),
    (v1(set_(shot(0), "id", "s1")), "Scene 1, shot 1: the shot has a key the format does not know: id"),
    (set_(scene, "title", ""), f"{S1}: the title is text, not blank"),
    (v1(set_(scene, "cast", [])), f"{S1}: the cast is a list of 1 or more names"),    # version 1 only
    (set_(scene, "cast", ["Character 1", "Character 2", "character 1"]), f"{S1}: character 1 is in the cast twice"),
    (set_(shot(1), "end_ms", 9000), f"{S2}: {SPAN}"),
    (set_(shot(1), "start_ms", 8000), f"{S2}: the shot starts before the shot before it ends"),
    (set_(shot(1), "camera", ""), f"{S2}: camera is text, not blank"),
    (set_(shot(1), "lens", "50mm"), f"{S2}: the shot has a key the format does not know: lens"),
    (set_(ev("l1"), "end_ms", 9001), f"{L1}: the event is not inside its shot"),
    (set_(ev("l1"), "start_ms", 1.5), f"{L1}: {SPAN}"),
    (set_(ev("l1"), "id", "l 1"), "Scene 1, shot 1: an event's id is 1 to 24 letters, digits, - or _"),
    (set_(ev("l1"), "id", "x" * 25), "Scene 1, shot 1: an event's id is 1 to 24 letters, digits, - or _"),
    (set_(ev("l2"), "id", "l1"), "Scene 1, shot 2, event l1: another event has this id"),
    (set_(ev("l1"), "kind", "song"), f"{L1}: kind is line, cue or pose"),
    (set_(ev("l1"), "speaker", "Character 4"), f"{L1}: the speaker Character 4 is not in the scene's cast"),
    (set_(ev("l1"), "words", "  "), f"{L1}: words is text, not blank"),
    (set_(ev("l1"), "emotion", ""), f"{L1}: emotion is text, not blank"),
    (set_(ev("l1"), "pace", 0), f"{L1}: pace is words per second, more than 0"),
    (set_(ev("l1"), "pace", "fast"), f"{L1}: pace is words per second, more than 0"),
    (set_(ev("l1"), "voice", "x"), f"{L1}: a line has a key the format does not know: voice"),
    (drop(ev("l1"), "words"), f"{L1}: a line has no words"),
    (set_(ev("c1"), "cue", "noise"), "Scene 1, shot 1, event c1: a cue is effect, music or reaction"),
    (set_(ev("p1"), "character", "Character 4"),
     "Scene 1, shot 1, event p1: the character Character 4 is not in the scene's cast"),
    (set_(ev("p1"), "pose", "dance"), "Scene 1, shot 1, event p1: a pose is one of " + ", ".join(scriptshape.POSES)),
    (set_(ev("p3"), "anchor", {"line": "l1", "at": "middle"}), "Scene 1, shot 1, event p3: an anchor's at is start "
                                                               "or end"),
    (set_(ev("p3"), "anchor", {"line": "l9", "at": "start"}), "Scene 1, shot 1, event p3: the anchor names no line "
                                                              "of this scene: l9"),
    (set_(ev("p3"), "anchor", {"line": "l1", "at": "end"}), "Scene 1, shot 1, event p3: the event does not start at "
                                                            "the end of line l1"),
    (set_(ev("p3"), "anchor", {"line": "l1"}), "Scene 1, shot 1, event p3: an anchor has no at"),
]


@pytest.mark.parametrize(("change", "line"), CASES)
def test_every_check_refuses_with_where(change: Callable[[dict], None], line: str) -> None:
    script = copy.deepcopy(EXAMPLE)
    change(script)
    with pytest.raises(Invalid) as e:
        scriptshape.read(script, CHARS)
    assert e.value.text == line


@pytest.mark.parametrize("change", [set_(scene, "title", "x" * 121), set_(ev("l1"), "words", "x" * 601),
                                    set_(ev("l1"), "language", "x" * 61), set_(ev("c1"), "words", "x" * 301),
                                    set_(shot(1), "camera", "x" * 301)])
def test_the_users_text_of_any_length_reads(change: Callable[[dict], None]) -> None:
    """No length cap of the Hub's on the script's words."""
    script = copy.deepcopy(EXAMPLE)
    change(script)
    scriptshape.read(script, CHARS)


def test_a_cast_of_nine_a_time_past_an_hour_and_a_pace_of_eight_read() -> None:
    """No most of the Hub's on a cast, a time or a pace."""
    nine = ["Character 1", "Character 2", *(f"Character {k}" for k in range(3, 10))]
    script = copy.deepcopy(EXAMPLE)
    v1(set_(scene, "cast", nine))(script)
    assert scriptshape.read(script, CHARS)["scenes"][0]["cast"] == nine
    script = copy.deepcopy(EXAMPLE)
    script["scenes"][0]["shots"][2]["end_ms"] = 3_600_001
    ev_of(script, "l1")["pace"] = 8
    assert scriptshape.read(script, CHARS)["scenes"][0]["shots"][2]["end_ms"] == 3_600_001


def test_names_and_optional_fields() -> None:
    script = copy.deepcopy(EXAMPLE)
    ev_of(script, "l1")["speaker"] = "CHARACTER 1"                     # any case
    for key in ("language", "emotion", "pace"):
        del ev_of(script, "l2")[key]                              # optional until the lock (Step 5)
    del script["scenes"][0]["shots"][0]["camera"]
    assert scriptshape.read(script, CHARS) is script


def test_an_anchor_to_a_line_of_another_scene_is_refused() -> None:
    script = copy.deepcopy(EXAMPLE)
    second = copy.deepcopy(script["scenes"][0])
    for sh in second["shots"]:
        sh["start_ms"] += 24_000
        sh["end_ms"] += 24_000
        sh["events"] = [{**e, "id": f"b{e['id']}", "start_ms": e["start_ms"] + 24_000, "end_ms": e["end_ms"] + 24_000}
                        for e in sh["events"] if e["kind"] != "line" and "anchor" not in e]
    second["shots"][0]["events"].append({"id": "x", "kind": "pose", "start_ms": 28_000, "end_ms": 29_000,
                                         "character": "Character 1", "pose": "stand",
                                         "anchor": {"line": "l1", "at": "start"}})
    script["scenes"].append(second)
    with pytest.raises(Invalid) as e:
        scriptshape.read(script, CHARS)
    assert e.value.text == "Scene 2, shot 1, event x: the anchor names no line of this scene: l1"


def test_a_version_2_script_being_written_reads() -> None:
    """No scene, a scene with no shot, a shot with no event, shot ids; their length 0 with no shot."""
    script = copy.deepcopy(EXAMPLE)
    script["scenes"] = []
    assert scriptshape.read(script, CHARS) is script and scriptshape.length_ms(script) == 0
    assert scriptshape.counts(script) == {"scenes": 0, "shots": 0, "lines": 0}
    script["scenes"] = [{"title": "One", "cast": ["Character 1"], "shots": []}]
    assert scriptshape.read(script, CHARS) is script and scriptshape.length_ms(script) == 0
    script["scenes"][0]["shots"] = [{"id": "s1", "start_ms": 0, "end_ms": 1000, "events": []},
                                    {"id": "s7", "start_ms": 1000, "end_ms": 2000, "events": []}]
    assert scriptshape.read(script, CHARS) is script and scriptshape.length_ms(script) == 2000


@pytest.mark.parametrize(("ident", "line"), [
    ("x1", "Scene 1, shot 2: a shot's id is s and a number"),
    (2, "Scene 1, shot 2: a shot's id is s and a number"),
    ("s1", "Scene 1, shot 2: another shot has this id"),
])
def test_a_shot_id_is_s_and_a_number_unique_in_the_script(ident: object, line: str) -> None:
    script = copy.deepcopy(EXAMPLE)
    script["scenes"][0]["shots"][0]["id"] = "s1"
    script["scenes"][0]["shots"][1]["id"] = ident
    with pytest.raises(Invalid) as e:
        scriptshape.read(script, CHARS)
    assert e.value.text == line


def panel(**fields: object) -> dict:
    return {"id": "f1", "kind": "panel", "at_ms": 9000, "picture": None, "stale": False, **fields}


def test_a_panel_reads_in_version_2() -> None:
    script = copy.deepcopy(EXAMPLE)
    script["scenes"][0]["shots"][1]["events"] += [panel(), panel(id="f2", at_ms=12_000, picture="out/2026-10-19/a.png",
                                                               stale=True)]
    assert scriptshape.read(script, CHARS) is script
    assert scriptshape.counts(script) == {"scenes": 1, "shots": 3, "lines": 3}


AT = "Scene 1, shot 2, event f1: at_ms is a whole millisecond at or after its shot's start and before its end"


@pytest.mark.parametrize(("value", "line"), [
    (panel(at_ms=8999), AT),
    (panel(at_ms=17_000), AT),
    (panel(at_ms=9000.5), AT),
    (panel(picture=3), "Scene 1, shot 2, event f1: picture is text of 1 to 300 characters"),
    (panel(picture=""), "Scene 1, shot 2, event f1: picture is text of 1 to 300 characters"),
    (panel(picture="x" * 301), "Scene 1, shot 2, event f1: picture is text of 1 to 300 characters"),
    (panel(stale=None), "Scene 1, shot 2, event f1: stale is true or false"),
    (panel(stale=1), "Scene 1, shot 2, event f1: stale is true or false"),
    (panel(id="l1"), "Scene 1, shot 2, event l1: another event has this id"),
    ({k: v for k, v in panel().items() if k != "stale"}, "Scene 1, shot 2, event f1: a panel has no stale"),
    (panel(start_ms=9000), "Scene 1, shot 2, event f1: a panel has a key the format does not know: start_ms"),
])
def test_a_panel_refused(value: dict, line: str) -> None:
    script = copy.deepcopy(EXAMPLE)
    script["scenes"][0]["shots"][1]["events"].append(value)
    with pytest.raises(Invalid) as e:
        scriptshape.read(script, CHARS)
    assert e.value.text == line


def test_a_panel_in_version_1_is_refused() -> None:
    script = copy.deepcopy(EXAMPLE)
    v1(lambda s: s["scenes"][0]["shots"][1]["events"].append(panel()))(script)
    with pytest.raises(Invalid) as e:
        scriptshape.read(script, set())
    assert e.value.text == "Scene 1, shot 2, event f1: a panel is version 2"


def test_the_lock_reads_in_version_2() -> None:
    for held in ({"locked": True, "at": "2026-10-20T09:15:02+02:00"}, {"locked": False, "at": None}):
        assert scriptshape.read({**copy.deepcopy(EXAMPLE), "lock": held}, CHARS)["lock"] == held


@pytest.mark.parametrize(("held", "line"), [
    ({"locked": "yes", "at": None}, "the lock's locked is true or false"),
    ({"locked": True, "at": None}, "the lock's at is text of 1 to 60 characters"),
    ({"locked": False, "at": "2026-10-20T09:15:02+02:00"}, "the lock's at is null when locked is false"),
    ({"locked": True}, "the lock has no at"),
])
def test_a_lock_refused(held: dict, line: str) -> None:
    with pytest.raises(Invalid) as e:
        scriptshape.read({**copy.deepcopy(EXAMPLE), "lock": held}, CHARS)
    assert e.value.text == line


def test_a_lock_in_version_1_is_refused() -> None:
    script = copy.deepcopy(EXAMPLE)
    v1(lambda s: s.update(lock={"locked": False, "at": None}))(script)
    with pytest.raises(Invalid) as e:
        scriptshape.read(script, set())
    assert e.value.text == "The script has a key the format does not know: lock"


TAKE = {"file": "Script 1/l1-1.wav", "hash": "3f9c0a1b77e2d415"}


JUDGED = {**TAKE, "tries": 2, "measured": {"speech_start_ms": 120, "speech_end_ms": 3400, "length_ms": 3600,
                                           "lufs": -24.1, "true_peak_dbtp": -3.2, "gain_db": 1.1},
          "judge": {"heard": 0.8, "first_miss_ms": 1400, "extra_speech": 0.0, "verdict": "flagged", "why": "a"}}


@pytest.mark.parametrize("takes", [{"l1": TAKE}, {"l1": JUDGED}, {"l1": {**TAKE, "measured": None, "judge": None}},
                                   {"gone": TAKE}, {}])
def test_takes_read_in_version_2(takes: dict) -> None:
    assert scriptshape.read({**copy.deepcopy(EXAMPLE), "takes": takes}, CHARS)["takes"] == takes


@pytest.mark.parametrize(("takes", "line"), [
    ([TAKE], "takes is an object"),
    ({"l 1": TAKE}, "takes: an event's id is 1 to 24 letters, digits, - or _"),
    ({"l1": "x"}, "takes, l1: a take is an object"),
    ({"l1": {"hash": "ab"}}, "takes, l1: a take has no file"),
    ({"l1": {"file": "a.wav"}}, "takes, l1: a take has no hash"),
    ({"l1": {**TAKE, "seed": 3}}, "takes, l1: a take has a key the format does not know: seed"),
    ({"l1": {**TAKE, "file": ""}}, "takes, l1: file is text of 1 to 300 characters"),
    ({"l1": {**TAKE, "hash": "x" * 65}}, "takes, l1: hash is text of 1 to 64 characters"),
    ({"l1": {**TAKE, "tries": 0}}, "takes, l1: tries is a whole number of 1 or more"),
    ({"l1": {**TAKE, "measured": []}}, "takes, l1: measured is an object or null"),
    ({"l1": {**TAKE, "judge": {"verdict": "bad"}}}, "takes, l1: a judge's verdict is ok or flagged"),
    ({"l1": {**TAKE, "judge": {"why": 3}}}, "takes, l1: a judge's why is text or null"),
])
def test_takes_refused(takes: object, line: str) -> None:
    with pytest.raises(Invalid) as e:
        scriptshape.read({**copy.deepcopy(EXAMPLE), "takes": takes}, CHARS)
    assert e.value.text == line


def test_takes_in_version_1_are_refused() -> None:
    script = copy.deepcopy(EXAMPLE)
    v1(lambda s: s.update(takes={}))(script)
    with pytest.raises(Invalid) as e:
        scriptshape.read(script, CHARS)
    assert e.value.text == "The script has a key the format does not know: takes"
