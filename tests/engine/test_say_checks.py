"""A message's operations checked before anything is applied (`hub/modules/director/saycheck.py`), pure:
round 2's five messages each with a right and a wrong operation list; the paraphrase refused naming the message's words;
the message's 30 s kept as 15 refused; an add for a change refused; the wrong line named refused; a length nobody wrote
dropped; "one scene" with two scenes refused; apostrophes are not spans; "a second line" is no ordinal
reference and no length; minutes × 60."""
from __future__ import annotations

from hub.modules.director import saycheck

STORY = "Script: Seven asks Eight about a favourite colour, about 15 seconds."
TOLD = "Eight, good to see you. Tell me about your favourite colour."
EMPTY = {"scenes": []}


def lines(text: str, *ops: dict, new: bool = False, title: str | None = None) -> list[str]:
    value = {"operations": list(ops), **({"title": title} if title else {})}
    return saycheck.check(value, text, EMPTY, new)[1]


def blamed(text: str, *ops: dict) -> set[int]:
    return saycheck.check({"operations": list(ops)}, text, EMPTY, False)[2]


SCENE = {"op": "add_scene", "title": "The meeting", "cast": ["Seven", "Eight"], "seconds": 15}
LINE = {"op": "add_line", "speaker": "Seven", "words": "Eight, what is in the box?"}


def test_the_story_keeps_the_users_length() -> None:
    assert lines(STORY, SCENE, LINE, new=True, title="Seven Asks Eight") == []
    assert lines(STORY, {**SCENE, "seconds": 30}, LINE, new=True, title="Seven Asks Eight") == [
        "the message writes 15 seconds; operation 1 says 30"]
    assert lines(STORY, SCENE, LINE, new=True) == ["a new script needs its title"]


def test_the_users_words_after_to_are_held_exactly() -> None:
    said = f"Change Seven's first line to: {TOLD}"
    ref = {"speaker": "Seven", "nth": 1}
    assert lines(said, {"op": "change_line", "ref": ref, "words": TOLD}) == []
    wrong = {"op": "change_line", "ref": ref, "words": "Eight, good to see you. What's your favourite colour?"}
    assert lines(said, wrong) == [f'the message writes "{TOLD}"; no operation holds it as written (operation 1 has '
                                  '"Eight, good to see you. What\'s your favourite colour?")']
    assert blamed(said, wrong) == {1}


def test_the_line_the_user_named_is_the_one_changed() -> None:
    said = "Take out Seven's second line."
    assert lines(said, {"op": "remove", "ref": {"speaker": "Seven", "nth": 2}}) == []
    assert lines(said, {"op": "remove", "ref": {"speaker": "Seven", "nth": 1}}) == [
        "the message names Seven's second line; operation 1 says Seven's 1st line"]


def test_a_change_is_never_an_add() -> None:
    said = "Make shot 2 a close shot on Eight."
    assert lines(said, {"op": "change_shot", "ref": {"shot": 2}, "framing": "Close-up of Eight", "on": ["Eight"]}) \
        == []
    got = lines(said, {"op": "add_shot", "shot": 2, "framing": "Close-up of Eight", "on": ["Eight"]})
    assert got == ["operation 1 (add_shot) needs seconds",
                   "the message asks for a change; change what it names (change_shot shot 2), never add one "
                   "(operation 1 is "
                   "add_shot)"]


def test_the_users_30_seconds_is_never_15() -> None:
    said = "Make the scene 30 seconds."
    assert lines(said, {"op": "set_length", "seconds": 30}, LINE) == [], "lines that reach the length"
    assert lines(said, {"op": "set_length", "seconds": 15}, LINE) == [
        "the message writes 30 seconds; operation 1 says 15"]
    assert blamed(said, {"op": "set_length", "seconds": 15}) == {1}


def test_a_length_nobody_wrote_and_a_count_the_user_wrote() -> None:
    story = "Script: Seven asks Eight in one scene."
    unnamed = {**SCENE, "seconds": 25}
    assert lines(story, unnamed, LINE, new=True, title="T") == [], "dropped, never refused"
    assert "seconds" not in unnamed
    assert lines(story, {k: v for k, v in SCENE.items() if k != "seconds"}, LINE, new=True, title="T") == []
    two = {k: v for k, v in SCENE.items() if k != "seconds"}
    assert lines(story, two, two, LINE, new=True, title="T") == ["the message writes one scene; the operations add 2"]


def test_quotes_apostrophes_ordinals_and_minutes() -> None:
    said = 'Script: Seven says "Hello, Eight!" and Eight\'s \'big\' answer.'
    assert saycheck.spans(said) == ["Hello, Eight!"], "single quotes are apostrophes, not spans"
    assert lines(said, SCENE | {"seconds": None}, {**LINE, "words": "Hello, Eight! Sit down."}, new=True,
                 title="T") == []
    assert lines(said, {**LINE, "words": "Hello, my friend Eight."}, new=True, title="T") == [
        'the message writes "Hello, Eight!"; no operation holds it as written '
        '(operation 1 has "Hello, my friend Eight.")']
    add = "Add a second line for Seven."
    assert saycheck.lengths(add) == [] and not saycheck.LINE_REF.search(add) and not saycheck.is_change(add)
    assert lines(add, LINE) == []
    assert saycheck.lengths("half a minute, then 2 minutes, a minute, twenty-five secs") == [30, 120, 60, 25]
    assert saycheck.lengths("Make the scene 30 seconds.") == [30] and saycheck.lengths("about 15s") == [15]


def test_which_messages_are_changes() -> None:
    for said in ("Change Seven's first line to: x", "Take out Seven's second line.", "Please, make shot 2 wide.",
                 "Ok so Seven, cut the joke.", "Make the scene 30 seconds."):
        assert saycheck.is_change(said), said
    for said in ("Seven asks Eight", "Make two more lines", "Add a shot", "Also change shot 2"):
        assert not saycheck.is_change(said), said


def test_the_users_new_words_after_to_are_never_a_signal() -> None:
    """The change is read before "to:"; the to: check runs on every message that is not a new story."""
    said = "Change Seven's first line to: Eight, tell me more about your favourite colour."
    told, ref = said.split("to: ", 1)[1], {"speaker": "Seven", "nth": 1}
    assert saycheck.is_change(said) and saycheck.is_change("Change Seven's first line to: I also love blue.")
    assert lines(said, {"op": "change_line", "ref": ref, "words": told}) == []
    paraphrase = {"op": "change_line", "ref": ref, "words": "Eight, tell me about colour."}
    assert lines(said, paraphrase) == [f'the message writes "{told}"; no operation holds it as written (operation 1 '
                                       'has "Eight, tell me about colour.")'] and blamed(said, paraphrase) == {1}
    add = {"op": "add_line", "speaker": "Seven", "words": "Eight, tell me all about colour."}
    assert blamed(said, add) == {1} and any("never add one (operation 1 is add_line)" in x for x in lines(said, add))
    also = "Also, Seven's first line to: Eight, hi there."
    assert not saycheck.is_change(also)
    assert lines(also, {"op": "change_line", "ref": ref, "words": "Eight, hello."}) == [
        'the message writes "Eight, hi there."; no operation holds it as written (operation 1 has "Eight, hello.")']
    story = "Script: Seven says to: Eight, good to see you."
    assert lines(story, {k: v for k, v in SCENE.items() if k != "seconds"}, LINE, new=True, title="T") == []
