"""The plain-value checks `hub.core.api` gives modules (`hub/core/checks.py`): bools refused, bounds, digit text for a
seed, seeds drawn or counted on and wrapped."""
from __future__ import annotations

import pytest

from hub.core.api import Invalid, number, seed_value, seeds, whole


def refused(fn, *args, **kwargs) -> tuple[str, str]:
    with pytest.raises(Invalid) as err:
        fn(*args, **kwargs)
    return err.value.field, err.value.text


def test_whole_takes_a_whole_number_in_bounds() -> None:
    assert whole(4, "steps", 1, 8) == 4 and whole(1, "steps", 1, 8) == 1 and whole(8, "steps", 1, 8) == 8
    for bad in (0, 9, True, False, 4.0, "4", None):
        assert refused(whole, bad, "steps", 1, 8) == ("steps", "steps must be a whole number from 1 to 8"), bad
    assert refused(whole, 9, "images", 1, 6, "Choose 1 to 6 images") == ("images", "Choose 1 to 6 images")


def test_number_takes_a_number_in_bounds() -> None:
    assert number(3, "guidance", 0, 50) == 3.0 and isinstance(number(3, "guidance", 0, 50), float)
    assert number(2.5, "guidance", 0, 50) == 2.5
    for bad in (-0.1, 50.5, True, "3", None):
        assert refused(number, bad, "guidance", 0, 50) == ("guidance", "guidance must be a number from 0 to 50"), bad
    strength = "LoRA strength must be 0 to 2"
    assert refused(number, 3, "loras", 0, 2, strength) == ("loras", strength)


def test_seed_value_is_random_or_a_whole_number_as_number_or_digits() -> None:
    assert seed_value("random", 99) is None
    assert seed_value(7, 99) == 7 and seed_value("42", 99) == 42 and seed_value(0, 99) == 0 and seed_value(99, 99) == 99
    text = ("seed", "seed must be random or a whole number from 0 to 99")
    for bad in (100, -1, True, 4.0, "4.0", "-3", "٣", " 7", "", None, "Random"):
        assert refused(seed_value, bad, 99) == text, bad


def test_seeds_count_on_from_the_first_and_wrap() -> None:
    assert seeds(5, 3, 99) == [5, 6, 7]
    assert seeds(98, 4, 99) == [98, 99, 0, 1], "past the top they wrap to 0"
    assert seeds(0, 0, 99) == []
    drawn = seeds(None, 50, 9)
    assert len(drawn) == 50 and all(0 <= s <= 9 for s in drawn) and len(set(drawn)) > 1
