"""A cast's prompt: A, the Casting fields as typed inside the engine's labels, then, when the tab's Prompt
box holds text, "\n\n" and that text byte for byte. Nothing else: the Hub ships no prompt text of its own.

A: `subject_definitions:` "<Subject 1> is the character shown in <Picture 1>." (the engine's definition of a subject
from its pictures) with the Description box as typed when given, then one line per picture with a keep line,
`<Picture N>: <keep>`; `retention_analysis:` and one line per picture with an ignore line, `<Picture N>: <ignore>`,
when any. A costume's A names the two approved face frames as boxes 1-2, its pictures from box 3, and the costume's
words as typed, one line ending in "." after the keep lines. "\n\n" between A and the box, as A has no closing
newline. The prompt is sent whole, whatever its length (no cap of the Hub's). A field is one line: its whitespace is
closed up; the box is not a field and goes as typed.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

WHO = "<Subject 1>"
SUBJECT = f"{WHO} is the character shown in <Picture 1>."
SEPARATOR = "\n\n"
FACES = "<Picture 1> and <Picture 2>"


def line(value: Any) -> str:
    """A keep, ignore or fact as one line: text with its whitespace closed up; anything else is ""."""
    return " ".join(value.split()) if isinstance(value, str) else ""


def facts_sentence(facts: Mapping[str, Any] | None) -> str:
    """The Description box (kept as `build`) as typed; "" when empty. No age field."""
    return line((facts or {}).get("build"))


def a_text(pictures: Sequence[Mapping[str, Any]], facts: Mapping[str, Any] | None) -> str:
    """A: `pictures` in box order, each {keep, ignore} (box 1 the character's picture)."""
    subject = " ".join(t for t in (SUBJECT, facts_sentence(facts)) if t)
    keeps = [f"<Picture {n}>: {k}" for n, p in enumerate(pictures, 1) if (k := line(p.get("keep")))]
    ignores = [f"<Picture {n}>: {i}" for n, p in enumerate(pictures, 1) if (i := line(p.get("ignore")))]
    return "\n".join([f"subject_definitions: {subject}", *keeps, *_retention(ignores)])


def _retention(ignores: list[str]) -> list[str]:
    """`retention_analysis:` with the ignore lines, after a blank line; nothing when none."""
    return ["", f"retention_analysis: {ignores[0]}", *ignores[1:]] if ignores else []


def costume_a(pictures: Sequence[Mapping[str, Any]], facts: Mapping[str, Any] | None, words: Any) -> str:
    """A costume's A: `pictures` the costume's, boxes 3 on, each {keep, ignore}; `words` the costume said."""
    subject = " ".join(t for t in (f"{WHO} is the character shown in {FACES}.", facts_sentence(facts)) if t)
    keeps = [f"<Picture {n}>: {k}" for n, p in enumerate(pictures, 3) if (k := line(p.get("keep")))]
    ignores = [f"<Picture {n}>: {i}" for n, p in enumerate(pictures, 3) if (i := line(p.get("ignore")))]
    said = line(words).rstrip(". ")
    return "\n".join([f"subject_definitions: {subject}", *keeps, *([f"{said}."] if said else []),
                      *_retention(ignores)])


def with_box(a: str, box: Any) -> str:
    """A, then "\n\n" and the box byte for byte when it holds any non-space character."""
    return a + SEPARATOR + box if isinstance(box, str) and box.strip() else a


def prompt(pictures: Sequence[Mapping[str, Any]], facts: Mapping[str, Any] | None, box: Any = "") -> str:
    """A cast's (cast or audience) whole prompt: its A, then the box when it holds text."""
    return with_box(a_text(pictures, facts), box)


def costume(pictures: Sequence[Mapping[str, Any]], facts: Mapping[str, Any] | None, words: Any, box: Any = "") -> str:
    """A costume's whole prompt: its A, then the box when it holds text."""
    return with_box(costume_a(pictures, facts, words), box)
