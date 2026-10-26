"""Director's first cut: a shot the assistant fills becomes the model's prompt, written here and never by
the language model. Pure: no I/O; `shotcheck` gathers the boxes and checks the shot first.

The prompt is the engine's own structure (upstream's own prompt rules for the clip family; R21 §1.1, R22 §A): an
identity model takes six labelled fields (`subject_definitions`, `summary`, `retention_analysis`,
`detailed_description`, `overall_soundscape`, `non_diegetic_music`, `:284`), any other clip model three
(`integrated_multimodal_description`, `overall_soundscape`, `non_diegetic_music`, `:252`), one line each, no blank
line. In the description: `[Shot 1]` first, later cuts `[Shot N] At MM:SS.mmm, ...` (`:254`); each subject's stable
speaker id `(SN)`; exact speech only inside `<d>[Language] words</d>` (`:256`); a boxed character is `<Subject N>`
from its `<Picture N>`s (`:286`, `:308`), the continued frame being `<Picture 1>` (its handler, `:109`). A
start frame takes the engine's alignment sentence (`:30`). With a kept soundtrack there are no `<d>` lines and the
description asks for lip movement in the engine's words (`:34`, the Hub's `lipsync` sentence), the track unnamed.
A speaker with a voice sample (`Frame.voices`) is voiced from `<Audio N>` (the engine's label for an audio
reference, upstream `text_encoder.py:139-140`): its definition `<Audio N> is the voice-timbre reference for
<Subject M> (SM).`, the tag `audio reference`, its retention line `<Audio N>: reference`, and each of its lines `says,
in the voice referenced from <Audio N>,` before the `<d>` (the engine's own example, `:236`; R22 §D.3).
What is sent (R21 §4.3): the shot's fields as written (typed, or by the Director and left), each
joined to the next by a full stop when it has none, with `<` and `>` taken out; the engine's labels and marks above;
`[Language]` in a `<d>` only when the line names one; `N/A` for an empty field. No sentence, default or replacement
word of the Hub's.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from hub.core.api import lipsync

ALIGN = "For the target video, at 0.00 seconds into the target video, <Picture 1> (from [Shot 1]) is fully referenced."
NONE = "N/A"
VOICED = "says, in the voice referenced from <Audio {}>,"   # the engine's own example, :236
_MARKS = re.compile(r"[<>]")     # they open the engine's labels and its `<d>`; every other mark is kept


def clean(text: Any) -> str:
    """Free text as the engine may read it: the whitespace closed up and no angle bracket (`<d>` and the labels are
    the engine's); nothing else of `text` changes (R21 §4.3)."""
    return _MARKS.sub("", " ".join(str(text or "").split())).strip()


@dataclass(frozen=True)
class Frame:
    """What the compiler needs besides the shot: whether the model's boxes are identities (six fields), each boxed
    subject's number and pictures by lower-cased name, a start frame in box 1, a continued clip, a kept sound, and each
    voiced speaker's audio number by lower-cased name."""
    identities: bool
    boxed: dict[str, tuple[int, tuple[int, ...]]] = field(default_factory=dict)
    start: bool = False
    continues: bool = False
    sound: bool = False
    voices: dict[str, int] = field(default_factory=dict)


def sentence(text: Any) -> str:
    """A field as written, cleaned (`clean`), with a full stop when it has no closing mark: the join between fields
    that share one engine field; no capital, no word added."""
    words = clean(text)
    if not words:
        return ""
    return words if words[-1] in ".!?…)" else words + "."


def stamp(seconds: float) -> str:
    """`MM:SS.mmm` (the engine's cut time)."""
    ms = round(float(seconds) * 1000)
    return f"{ms // 60000:02d}:{ms % 60000 // 1000:02d}.{ms % 1000:03d}"


def _key(name: Any) -> str:
    return " ".join(str(name or "").split()).lower()


def labels(shot: dict, frame: Frame) -> dict[str, str]:
    """Each subject's label by lower-cased name: `<Subject N>` when boxed, else the name as written."""
    out = {}
    for s in shot["subjects"]:
        boxed = frame.boxed.get(_key(s["name"])) if frame.identities else None
        out[_key(s["name"])] = f"<Subject {boxed[0]}>" if boxed else " ".join(str(s["name"]).split())
    return out


def speakers(shot: dict) -> dict[str, int]:
    """Each subject's speaker number (S1, S2, … in the shot's order) by lower-cased name."""
    out: dict[str, int] = {}
    for s in shot["subjects"]:
        out.setdefault(_key(s["name"]), len(out) + 1)
    return out


def description(shot: dict, frame: Frame) -> str:
    """`[Shot 1]` and what happens: the subjects, the camera, the action, the lines (or the lip sentence with a kept
    sound), the cuts, the ending. On an identity model the place and light come first as the global treatment."""
    names, ids = labels(shot, frame), speakers(shot)
    camera = shot.get("camera") or {}
    place = [sentence(shot.get("where")), sentence(shot.get("light"))]
    parts = [] if frame.identities else place[:]
    for s in shot["subjects"]:
        look = sentence(s.get("look"))
        parts.append(f"(S{ids[_key(s['name'])]}) {names[_key(s['name'])]}" + (f", {look}" if look else "."))
    parts += [sentence(camera.get("framing")), sentence(camera.get("move")), *map(sentence, shot.get("action") or [])]
    if frame.sound:
        parts.append(lipsync.SENTENCE.format(names[_key(shot["subjects"][0]["name"])]))
    for line in shot.get("lines") or []:
        who = _key(line["speaker"])
        language = " ".join(str(line.get("language") or "").split())
        words = " ".join(str(line["words"]).split())
        says = VOICED.format(frame.voices[who]) if who in frame.voices else "says"
        named = f"[{language}] " if language else ""          # only a language the line names
        parts.append(f"(S{ids[who]}) {names[who]} {says} <d>{named}{words}</d>.")
    for n, cut in enumerate(shot.get("cuts") or [], 2):
        parts.append(f"[Shot {n}] At {stamp(cut['at'])}, {clean(cut['to'])}")
        parts[-1] = parts[-1] if parts[-1][-1] in ".!?" else parts[-1] + "."
    parts.append(sentence(shot.get("ending")))
    body = "[Shot 1] " + " ".join(p for p in parts if p)
    return " ".join([*(p for p in place if p), body]) if frame.identities else body


def soundscape(shot: dict, frame: Frame) -> str:
    """`sound.ambience` as written (`sentence`), else `N/A`."""
    return sentence((shot.get("sound") or {}).get("ambience")) or NONE


def music(shot: dict, frame: Frame) -> str:
    score = " ".join(str((shot.get("sound") or {}).get("music") or "").split())
    return score if score and not frame.sound else NONE


def _tags(frame: Frame) -> str:
    """The summary's task tags (`:288`): reference generation, video continuation, audio reuse, audio reference, as
    they apply."""
    tags = ["reference generation"] if frame.boxed or not (frame.continues or frame.sound) else []
    tags += ["video continuation"] if frame.continues else []
    tags += ["audio reuse"] if frame.sound else []
    tags += ["audio reference"] if frame.voices else []
    return " + ".join(tags)


def _audio(shot: dict, frame: Frame) -> tuple[list[str], list[str]]:
    """The voiced speakers' definition and retention sentences, in audio-number order."""
    defs, kept = [], []
    for who, n in sorted(frame.voices.items(), key=lambda kv: kv[1]):
        boxed, spoken = frame.boxed.get(who), speakers(shot).get(who)
        if boxed and spoken:
            defs.append(f"<Audio {n}> is the voice-timbre reference for <Subject {boxed[0]}> (S{spoken}).")
            kept.append(f"<Audio {n}>: reference")
    return defs, kept


def compile_shot(shot: dict, frame: Frame) -> str:
    """The prompt for the shot: six fields on an identity model, three on any other."""
    sound = f"overall_soundscape: {soundscape(shot, frame)}\nnon_diegetic_music: {music(shot, frame)}"
    if not frame.identities:
        head = f"{ALIGN}\n" if frame.start and not frame.continues else ""
        return f"{head}integrated_multimodal_description: {description(shot, frame)}\n{sound}"
    names, boxed = labels(shot, frame), []
    for s in shot["subjects"]:
        found = frame.boxed.get(_key(s["name"]))
        if found and (found[0], s) not in boxed:
            boxed.append((found[0], s))
    defs = "; ".join(f"<Subject {n}> is {' '.join(str(s['name']).split())}, from "
                     + ", ".join(f"<Picture {p}>" for p in frame.boxed[_key(s['name'])][1]) for n, s in boxed)
    kept = "\n".join(f"{names[_key(s['name'])]} (appears in [Shot 1]): fully_preserved - "
                     f"{' '.join(str(s['name']).split())}." for _, s in boxed)
    voiced, retained = _audio(shot, frame)
    defs = " ".join([defs + "." if defs else "", *voiced]).strip()
    kept = "\n".join([kept, *retained]).strip()
    first = sentence((shot.get("action") or [""])[0])        # the tags alone with no action
    return (f"subject_definitions: {defs or NONE}\n"
            f"summary: {' '.join(x for x in (f'[{_tags(frame)}]', first) if x)}\n"
            f"retention_analysis: {kept or NONE}\n"
            f"detailed_description: {description(shot, frame)}\n{sound}")
