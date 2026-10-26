"""Free text is not refused for a quote mark, a '<', a '>' or the word
"says"; the compiler's `clean` takes only `<` and `>` out of the prompt's text (they open the engine's labels) and sends
every quote mark as typed; `lines` are not touched, `<d>` being the engine's."""
from __future__ import annotations

import copy

import pytest

from hub.modules.generate_image import build, shotcheck, shotprompt  # noqa: F401  (build first: the import order)

BASE = {"subjects": [{"name": "Character 7", "look": "in a grey suit"}, {"name": "Character 16"}],
        "where": "a bare stage", "light": "hot lights", "camera": {"framing": "medium shot", "move": "push in"},
        "action": ["Character 7 walks to the front", "the character points at the camera"],
        "lines": [{"speaker": "Character 7", "words": "Line one, everybody! You won't believe this one."}],
        "cuts": [{"at": 2.0, "to": "a close-up of Character 16"}], "ending": "the character bows",
        "sound": {"ambience": "a murmuring hall", "music": "a jazz sting"}}
MARKS = ['"', "“", "”", "„", "«", "»", "‘", "'", "’"]


def with_text(path: tuple, text: str) -> dict:
    shot = copy.deepcopy(BASE)
    *head, last = path
    at = shot
    for key in head:
        at = at[key]
    at[last] = text
    return shot


@pytest.mark.parametrize("mark", MARKS)
def test_a_quote_mark_in_free_text_is_not_refused_and_is_sent_as_typed(mark):
    shot = with_text(("action", 1), f"the character grins {mark}hello{mark} and waves")
    assert not hasattr(shotcheck, "no_speech"), "the refusal is withdrawn"
    assert shotprompt.clean(shot["action"][1]) == f"the character grins {mark}hello{mark} and waves"
    assert shotprompt.sentence(shot["action"][1]) == f"the character grins {mark}hello{mark} and waves."


@pytest.mark.parametrize("mark", ["<", ">"])
def test_an_angle_bracket_in_free_text_is_not_refused_and_is_not_in_the_prompt(mark):
    shot = with_text(("action", 1), f"the character grins {mark}hello{mark} and waves")
    assert shotprompt.clean(shot["action"][1]) == "the character grins hello and waves"
    assert shotprompt.sentence(shot["action"][1]) == "the character grins hello and waves."


def test_the_word_says_is_not_refused():
    for text in ("the character says hello", "Character 7 SAYS hi", "Says nothing"):
        assert shotprompt.clean(text) == text


def test_every_apostrophe_is_kept():
    assert shotprompt.clean("Character 7's grin widens; Character 16's eyes roll; the essays fall") == (
        "Character 7's grin widens; Character 16's eyes roll; the essays fall")
    assert shotprompt.clean("the 2010s hall’s stage") == "the 2010s hall’s stage"
    assert shotprompt.clean("the 4Ks' stage") == "the 4Ks' stage"
    assert shotprompt.clean("'tis late") == "'tis late"


def test_room_sound_is_sent_as_written():
    """No word of the typed ambience is replaced."""
    for text in ("a hall with crowd chatter and indistinct voices", "background chatter and murmuring conversations",
                 "a cheerful speaker and the audience"):
        assert shotprompt.clean(text) == text


def test_lines_are_untouched():
    shot = copy.deepcopy(BASE)
    shot["lines"] = [{"speaker": "Character 7", "words": "Speaker 1 says \"hi\" <loudly> and 'goes'."}]
    frame = shotprompt.Frame(False)
    assert "<d>Speaker 1 says \"hi\" <loudly> and 'goes'.</d>" in shotprompt.description(shot, frame)
