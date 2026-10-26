"""A long spoken line as the engine's turns: whole sentences grouped under the target by the engine's own
estimate (upstream `dialogue.py:148-151`), one `Speaker 1:` block each, the line's direction opening every block; a
line at or under the target goes as it did before."""
from __future__ import annotations

import pytest

from hub.worker.adapters import tasks, turns
from hub.worker.engineapi import SpeechRequest
from tests.engine.test_engine_contract import CATEGORIES
from tests.engine.test_speech_task import ENTRY
from tests.engine.test_upstream_rules import SPEECH

# About 20 seconds by the engine's estimate.
LONG = ("word word word word word word. word word word word word word word word. word word word word word word word. "
        "Mr. word word word word word word word word word 3.5 word word... word word word word. word word word word "
        "word word word. word word word word word. word word word word word word word word.")


def test_turns_reads_no_engine_name():
    assert tuple(turns.READS) == CATEGORIES and not any(turns.READS.values()), "it mirrors numbers, reads no names"


def estimate(text: str) -> float:
    """The engine's formula, written out again from the upstream file (not through `turns`)."""
    import re
    words = re.findall(r"[a-z0-9]+(?:'[a-z0-9]+)?", re.sub(r"\[[^\[\]\n]+\]", " ", text).casefold())
    return len(words) / 2.6 + len(re.findall(r"[.!?;:]", re.sub(r"\[[^\[\]\n]+\]", " ", text))) * 0.18 + 1.4


def script(task: dict) -> list[str]:
    """The block bodies of a task's prompt."""
    parts = task["prompt"].split("Speaker 1:\n")
    assert parts[0] == ""
    return [p.rstrip("\n") for p in parts[1:]]


@pytest.mark.parametrize("text, count", [
    ("Mr. Speaker 1 came. Dr. Speaker 2 left.", 2), ("It cost 3.5 dollars. Then more.", 2), ("Wait... What? No!", 3),
    ("Apples, pears, etc. are fruit.", 1), ("Speaker 1 said \"go.\" Speaker 2 went.", 2), ("One. Two", 2)])
def test_sentences_do_not_split_at_titles_numbers_or_inside_an_ellipsis(text, count):
    assert len(turns.sentences(text)[1]) == count


def test_the_leading_direction_is_taken_off_and_returned_apart():
    assert turns.sentences("[calm, low] One. Two.") == ("[calm, low] ", ["One.", "Two."])


def test_a_sentence_longer_than_the_target_is_one_block():
    long_one = "This sentence goes on and on with many many words that take far more than five seconds to say aloud."
    _, groups = turns.blocks(f"Short start here now. {long_one} And a closing line of words here.", 5.0)
    assert long_one in groups


def test_a_short_last_sentence_joins_the_one_before():
    _, groups = turns.blocks("The first sentence takes a while to say. Yes.", 5.0)
    assert groups == ["The first sentence takes a while to say. Yes."]


def test_every_block_stays_under_the_target_but_a_single_sentence():
    _, groups = turns.blocks(LONG, 5.0)
    assert len(groups) > 2 and " ".join(groups) == " ".join(LONG.split())
    for group in groups[:-1]:
        assert estimate(group) <= 5.0 or len(turns.sentences(group)[1]) == 1, group
    assert all(turns.planned(g) == pytest.approx(estimate(g)) for g in groups)


@pytest.mark.parametrize("target", [None, 5.0, 45.0])
def test_a_line_at_or_under_the_target_is_sent_as_before(target):
    line = "[calm] Who goes there?"
    task = tasks.task(SpeechRequest(SPEECH, line, 7, 300, direction="low, slow", turn_seconds=target), ENTRY)
    assert task == {"model_type": SPEECH, "prompt": "Speaker 1:\n[low, slow] [calm] Who goes there?", "seed": 7,
                    "batch_size": 1, "multi_prompts_gen_type": "FG", "duration_seconds": 300, "audio_prompt_type": ""}


def test_a_long_line_without_a_target_is_one_block_as_before():
    task = tasks.task(SpeechRequest(SPEECH, LONG, 7, 300), ENTRY)
    assert task["prompt"] == f"Speaker 1:\n{LONG}"


def test_without_a_sample_the_voice_words_and_the_direction_open_every_block():
    task = tasks.task(SpeechRequest(SPEECH, f"[tired] {LONG}", 7, 300, direction="low, slow", turn_seconds=5.0),
                      ENTRY)
    blocks = script(task)
    assert len(blocks) > 2 and task["prompt"].count("Speaker 1:") == len(blocks)
    assert all(b.startswith("[low, slow] [tired] ") for b in blocks)
    assert " ".join(b.removeprefix("[low, slow] [tired] ") for b in blocks) == " ".join(LONG.split())
    assert (task["seed"], task["duration_seconds"], task["audio_prompt_type"]) == (7, 300, "")


def test_with_a_sample_no_voice_words_appear_in_any_block():
    task = tasks.task(SpeechRequest(SPEECH, f"[tired] {LONG}", 7, 300, sample="/chars/Character 7.wav",
                                    direction="low, slow", turn_seconds=5.0), ENTRY)
    blocks = script(task)
    assert len(blocks) > 2 and all(b.startswith("[tired] ") for b in blocks)
    assert "low, slow" not in task["prompt"]
    assert (task["audio_prompt_type"], task["audio_guide"]) == ("A", "/chars/Character 7.wav")

