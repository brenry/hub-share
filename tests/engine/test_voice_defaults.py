"""`layout.voice`, pure: a new line's pace the Hub's to two
decimals, the engine's 2.6 when none is handed in; no language and no emotion that was not sent, whatever the
script's other lines name. Nothing of the script changes; `edit.line_add` calls it."""
from __future__ import annotations

import copy
import inspect

from hub.modules.director import edit, layout


def script(*lines: tuple[int, dict]) -> dict:
    """One shot holding a line `l<n>` of each (n, its voice fields)."""
    events = [{"id": f"l{n}", "kind": "line", "start_ms": 0, "end_ms": 1000, "speaker": "Character 7", "words": "Hi.",
               **ln}
              for n, ln in lines]
    return {"version": 2, "scenes": [{"shots": [{"id": "s1", "start_ms": 0, "end_ms": 2000, "events": events}]}]}


def test_no_line_no_language_no_emotion_and_the_engines_pace() -> None:
    assert layout.voice(script()) == {"pace": 2.6}
    assert layout.voice(script(), None) == layout.voice(script(), layout.PACE)


def test_the_hubs_pace_to_two_decimals() -> None:
    assert layout.voice(script(), 2.4567)["pace"] == 2.46
    assert layout.voice(script(), 3)["pace"] == 3
    assert layout.voice(script(), 2.444)["pace"] == 2.44


def test_a_language_another_line_names_is_not_taken() -> None:
    held = script((1, {"language": "Language 1"}), (2, {"language": "Language 2"}), (3, {}))
    assert layout.voice(held, 2.5) == {"pace": 2.5}, "no language that was not sent"


def test_nothing_changes_and_line_add_calls_it() -> None:
    held = script((1, {"language": "Language 1", "emotion": "Emotion 1", "pace": 2.1}))
    before = copy.deepcopy(held)
    assert layout.voice(held, 2.9) == {"pace": 2.9}
    assert held == before
    assert "layout.voice(script, pace)" in inspect.getsource(edit.line_add), "line_add calls it"


def test_a_pace_of_0_is_the_engines() -> None:
    assert layout.voice(script(), 0)["pace"] == layout.PACE
