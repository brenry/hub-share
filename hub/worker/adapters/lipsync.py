"""The sentence a clip that follows a sound asks for lip movement with. Stdlib only.

The engine's own guidance for a kept soundtrack (cited in the facts file, `soundtrack`): identify the character and
explicitly request `speaking with natural lip movements synchronized` or equivalent lip-sync wording, without
mentioning a supplied audio track; in a structured prompt, in its description section (`detailed_description`, or
`integrated_multimodal_description` for the three-section prompt). A prompt that already asks for lip movement goes
as it is; the sound is never named.
"""
from __future__ import annotations

import re

SENTENCE = "{} is speaking with natural lip movements synchronized."
ALONE = "speaking with natural lip movements synchronized."   # no named identity: the engine's phrase alone
SECTIONS = ("detailed_description", "integrated_multimodal_description")   # the description section, per prompt
# Every section header of the structured prompts: the six-section prompt's and the three-section prompt's.
HEADERS = frozenset((*SECTIONS, "subject_definitions", "summary", "retention_analysis", "overall_soundscape",
                     "non_diegetic_music"))
_ASKS = re.compile("lip", re.IGNORECASE)
_HEADER = re.compile(r"^[ \t]*([a-z_]+)[ \t]*:", re.MULTILINE)     # a section header: `name:` at a line's start


def ask(prompt: str, who: str | None) -> str:
    """`prompt` with the lip sentence at the end of its description section (or of the prompt when it has none),
    unless it already says `lip`."""
    if _ASKS.search(prompt):
        return prompt
    sentence = SENTENCE.format(who.strip()) if (who or "").strip() else ALONE
    headers = [m for m in _HEADER.finditer(prompt) if m.group(1) in HEADERS]
    at = next((i for i, m in enumerate(headers) if m.group(1) in SECTIONS), None)
    end = headers[at + 1].start() if at is not None and at + 1 < len(headers) else len(prompt)
    head, tail = prompt[:end], prompt[end:]
    body = head.rstrip()
    gap = head[len(body):] or ("\n" if tail else "")
    return f"{body} {sentence}{gap}{tail}" if body else f"{sentence}{gap}{tail}"
