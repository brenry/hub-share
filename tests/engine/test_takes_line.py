"""`takesline.line`, pure, on real script shapes: a version-2 script whose
`takes` are records as Track writes them (the line's hash with its speaker's sample facts, `takejudge.verdict`'s judge,
read by `scriptshape`'s `check_takes`), states as `/script` reads them (`audioscript.take` with the voices, the files
present and Track's live states), and a Track job's card as the queue holds it (`JobBook.record`'s keys)."""
from __future__ import annotations

import copy

from hub.modules.director import audioscript, cuetakes, scriptshape, takejudge, takesline

VOICES = {"character 7": [48_000, 1_760_000_000], "character 8": [52_000, 1_760_000_100]}
BARS = {"words_bar": 0.9, "unscripted_s": 1.0}
LEVEL = {"speech_start_ms": 100, "speech_end_ms": 2_000, "length_ms": 2_200, "lufs": -24.0, "true_peak_dbtp": -6.0,
         "extra_s": 0.0}
NAME = "Character 7 Meets Character 8"


def ev(ident: str, at: int, speaker: str = "Character 7", **more: object) -> dict:
    out = {"id": ident, "kind": "line", "start_ms": at, "end_ms": at + 1_500, "speaker": speaker,
           "words": f"Words of {ident}.", "language": "English", "emotion": "neutral", "pace": 2.6}
    return {**out, **more}


def cue(ident: str, at: int) -> dict:
    return {"id": ident, "kind": "cue", "start_ms": at, "end_ms": at + 2_000, "cue": "reaction", "words": "Laughter"}


def made(events: list[dict]) -> dict:
    return {"version": 2, "context": {"cast": []}, "lock": {"locked": True, "at": "2026-10-20T10:00:00+02:00"},
            "scenes": [{"title": "One", "shots": [{"id": "s1", "start_ms": 0, "end_ms": 15_000, "events": events}]}],
            "takes": {}}


def record(script: dict, ident: str, heard: float = 0.97) -> None:
    """The take Track records for `ident`: its hash at the press, the judge of a take heard at `heard`."""
    e = next(x for x in script["scenes"][0]["shots"][0]["events"] if x["id"] == ident)
    got = takejudge.verdict({"heard": heard}, LEVEL, BARS) if e["kind"] == "line" else \
        takejudge.cue_verdict({**LEVEL, "lufs": -27.0}, "reaction")
    script["takes"][ident] = {"file": f"{NAME}/{ident}-1.wav", "hash": audioscript.sound_hash(
        e, audioscript.voice_of(e, VOICES)), "tries": 1, "measured": got.measured, "judge": got.judge}


def four() -> dict:
    """Four lines, three heard, l2 heard 62 %."""
    script = made([ev("l1", 0), ev("l2", 1_500, "Character 8"), ev("l3", 3_000), ev("l4", 4_500, "Character 8")])
    for ident in ("l1", "l3", "l4"):
        record(script, ident)
    record(script, "l2", heard=0.62)
    audioscript.check_takes(script["takes"], scriptshape.ID)
    return script


def present(script: dict) -> set[str]:
    return {t["file"] for t in script["takes"].values()}


def test_the_plans_example() -> None:
    script = four()
    assert script["takes"]["l2"]["judge"]["why"] == "heard 62 %"
    assert takesline.line(script, voices=VOICES, present=present(script)) == "4 takes: 3 ok, 1 flagged: l2 heard 62 %"
    assert takesline.line(script, None, voices=VOICES) == "4 takes: 3 ok, 1 flagged: l2 heard 62 %", "not asked"


def test_without_the_sample_facts_every_line_reads_stale() -> None:
    """As `/script` would without them: the hash Track recorded holds the sample."""
    assert takesline.line(four()) == "4 takes: 4 to take"


def test_stale_none_failed_and_rendering() -> None:
    script = four()
    script["scenes"][0]["shots"][0]["events"][0]["words"] = "Changed words."       # l1 stale
    del script["takes"]["l3"]                                                      # l3 none
    files = present(script) - {f"{NAME}/l4-1.wav"}                                 # l4's file gone: none
    assert takesline.line(script, voices=VOICES, present=files) == "4 takes: 1 flagged: l2 heard 62 %, 3 to take"
    live = {"l1": ("failed", "no take landed"), "l3": ("rendering", None)}
    assert takesline.line(script, voices=VOICES, present=files, live=live) == \
        "4 takes: 1 flagged: l2 heard 62 %, 1 failed: l1 no take landed, 2 to take"


def test_cues_count_and_the_room_does_not() -> None:
    script = four()
    script["scenes"][0]["shots"][0]["events"].append(cue("c1", 6_000))
    record(script, "c1")
    script["takes"][cuetakes.ROOM_ID] = {"file": f"{NAME}/room-1.wav", "hash": "0123456789abcdef", "tries": 1,
                                         "measured": None, "judge": None}
    audioscript.check_takes(script["takes"], scriptshape.ID)
    assert takesline.line(script, voices=VOICES) == "5 takes: 4 ok, 1 flagged: l2 heard 62 %"
    del script["takes"]["c1"]
    assert takesline.line(script, voices=VOICES) == "5 takes: 3 ok, 1 flagged: l2 heard 62 %, 1 to take"


def test_three_ids_a_state_then_the_rest_counted_each_why_cut_to_60() -> None:
    script = made([ev(f"l{n}", n * 1_500) for n in range(1, 7)])
    for n in range(1, 6):
        record(script, f"l{n}", heard=0.5 + n / 100)
    record(script, "l6")
    long = "x" * 70
    script["takes"]["l1"]["judge"]["why"] = long
    script["takes"]["l2"]["judge"]["why"] = None
    got = takesline.line(script, voices=VOICES)
    assert got == f"6 takes: 1 ok, 5 flagged: l1 {'x' * 60} · l2 · l3 heard 53 % · +2"
    live = {f"l{n}": ("failed", f"why {n}") for n in range(1, 5)}
    assert takesline.line(script, voices=VOICES, live=live) == \
        "6 takes: 1 ok, 1 flagged: l5 heard 55 %, 4 failed: l1 why 1 · l2 why 2 · l3 why 3 · +1"


def test_the_order_is_the_scripts_and_a_why_keeps_its_own_words() -> None:
    script = made([ev("l2", 0), ev("l1", 1_500)])
    record(script, "l1", heard=0.4)
    record(script, "l2", heard=0.3)
    script["takes"]["l2"]["judge"]["why"] = "heard 30 %; 2.1 s of sound outside the words"
    assert takesline.line(script, voices=VOICES) == \
        "2 takes: 2 flagged: l2 heard 30 %; 2.1 s of sound outside the words · l1 heard 40 %"


def test_after_follows_the_none_running_form_only() -> None:
    script = four()
    tail = "Track refused: Pick a speech model in Generate"
    assert takesline.line(script, voices=VOICES, after=tail) == \
        f"4 takes: 3 ok, 1 flagged: l2 heard 62 %; {tail}"
    card = {"id": "j7", "state": "queued", "position": 1, "progress": None, "summary": {"step_names": ["l1"]}}
    assert takesline.line(script, card, voices=VOICES, after=tail) == "takes: Track queued (job j7, 1 on the queue)"


def test_no_line_and_no_cue() -> None:
    assert takesline.line(made([])) == "0 takes"
    assert takesline.line(made([ev("l1", 0)])).startswith("1 take: ")  # the singular, never "1 takes"


def steps() -> list[str]:
    return ["l1", "l1 · take 2", "l1 · take 3", "l2", "l2 · take 2", "l2 · take 3", "c1", "room"]


def card(state: str, **more: object) -> dict:
    return {"id": "a1b2", "tool": "director", "kind": "track", "state": state, "position": None, "progress": None,
            "summary": {"prompt": f"Track · {NAME}", "step_names": steps()}, **more}


def test_running_queued_and_ended_cards() -> None:
    script = four()
    running = card("running", progress={"phase": "", "index": 5, "count": 8, "pct": 40, "text": ""})
    assert takesline.line(script, running) == "takes: 4 of 8 · l2 being spoken (job a1b2)"
    first = card("running", progress={"phase": "", "index": 1, "count": 8, "pct": 0, "text": ""})
    assert takesline.line(script, first) == "takes: 0 of 8 · l1 being spoken (job a1b2)"
    room = card("running", progress={"phase": "", "index": 8, "count": 8, "pct": 90, "text": ""})
    assert takesline.line(script, room) == "takes: 7 of 8 · room tone (job a1b2)"     # the room tone named
    assert takesline.line(script, card("running")) == "takes: 0 of 8 (job a1b2)", "the model loading: no progress yet"
    assert takesline.line(script, card("queued", position=2)) == "takes: Track queued (job a1b2, 2 on the queue)"
    for ended in ("done", "failed", "cancelled"):
        assert takesline.line(script, card(ended), voices=VOICES) == "4 takes: 3 ok, 1 flagged: l2 heard 62 %"


def test_pure() -> None:
    script = four()
    before = copy.deepcopy(script)
    running = card("running", progress={"index": 2, "count": 8})
    held = copy.deepcopy(running)
    takesline.line(script, running, voices=VOICES, present=present(script), live={"l1": ("rendering", None)})
    takesline.line(script, voices=VOICES)
    assert script == before and running == held
