"""A scene's judge step: each shot's take judged as it lands, a re-take allowed within the scene's bound,
and the lines shown on screen. Nothing of it is written: the verdicts live in the job's notes, in memory (`CLAUDE.md`).

`ShotJudge` is the plan's `JobPlan.judge`. The dispatcher hands it every `task_done` of a take's task (`done`): it
keeps each task's measured `seconds`, and for a take's first task (its render, the one the worker judged) returns a
`Take`: whether it passes every judge that ran, its rank and its line. The lane asks `again(shot,
take)` before a re-take: the re-takes' seconds so far plus this shot's take 1 within `scene_retake_minutes`.
A judge that did not run is left out of the pass and the rank, and the line names it; none ran: the take passes.
A spoken take whose speech runs over `scene_unscripted_seconds` before or after the line's words fails.
`lines` gives the scene's verdict line and each landed take's chip, keyed by its item id.

A Generate press is judged the same way: a clip by `ShotJudge` on its one shot, a spoken line by
`LineJudge` on its words alone (`speech_words_bar` and the words judge's sentences); `presstakes` builds both.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from hub.core.api import Ctx, Take

from . import takes

NOT_JUDGED = "Not judged: {}"
NO_JUDGE = "no judge ran"
CHIP = "Take {} · {} · {}"
USED = "re-takes used {:.1f} of {:g} min"
MISSED = "Heard {}% of the words; the first miss at {} s"


def _who(name: Any) -> str:
    return " ".join(str(name or "").split())


def _framed(framing: str | None) -> bool:
    words = set(str(framing or "").casefold().replace("-", " ").split())
    return any(words & set(keys) for _, keys, _ in takes.BANDS)


def unscripted(mouth: Any, words: Any) -> float | None:
    """The seconds of speech before the line's first heard word and after its last, from the mouth
    judge's spans (`speech_from`, `speech_to`) and the words judge's (`first`, `last`); None when one is missing."""
    got = [r.get(k) if isinstance(r, dict) else None
           for r, k in ((mouth, "speech_from"), (mouth, "speech_to"), (words, "first"), (words, "last"))]
    if not all(isinstance(v, (int, float)) for v in got):
        return None
    start, end, first, last = (float(v) for v in got)
    return round(max(0.0, first - start) + max(0.0, end - last), 2)


class ShotJudge:
    """`shots`: each shot as planned (its `lines`, `camera.framing`); `takes_of`: the plan's `takes`; `seconds_cap`:
    the re-takes' bound in seconds; `again_ok` False (a redo): never rendered again by itself. `numbers`: each
    shot's number in the scene and its first take's number (a redo's shot 2, take 3); default (k, 1)."""

    def __init__(self, ctx: Ctx, shots: list[dict], takes_of: tuple, seconds_cap: float, again_ok: bool = True,
                 numbers: list[tuple[int, int]] | None = None) -> None:
        s = ctx.settings
        self.shots, self.takes_of, self.cap, self.again_ok = shots, takes_of, float(seconds_cap), again_ok
        self.numbers = numbers or [(k, 1) for k in range(1, len(shots) + 1)]
        self.words_bar = float(s.get("scene_words_bar") or 0.8)
        self.face_bar, self.lips_bar = float(s.get("clip_face_bar") or 0.3), float(s.get("clip_lips_bar") or 0.6)
        self.close, self.wide = float(s.get("frame_close") or 0.3), float(s.get("frame_wide") or 0.12)
        self.unscripted_bar = float(s.get("scene_unscripted_seconds") or 2.5)
        self.seconds: dict[int, float] = {}
        self.seen: dict[int, Take] = {}
        self.short: dict[int, str] = {}      # a take's failing judges in a few words, for the scene's line

    def _at(self, task: int) -> tuple[int, int, tuple[int, ...]] | None:
        for n, shot in enumerate(self.takes_of, 1):
            for t, take in enumerate(shot, 1):
                if take[0] <= task <= take[-1]:
                    return n, t, take
        return None

    # ---------------------------------------------------------------- api.Judge
    def done(self, task: int, d: Mapping[str, Any]) -> Take | None:
        if isinstance(d.get("seconds"), (int, float)):
            self.seconds[task] = float(d["seconds"])
        at = self._at(task)
        if at is None or task != at[2][0]:
            return None
        judge = d.get("judge")
        take, short = self.verdict(judge if isinstance(judge, dict) else None, at[0])
        self.seen[task], self.short[task] = take, short
        return take

    def again(self, shot: int, take: int) -> bool:
        """A re-take runs when the re-takes' measured seconds so far plus this shot's take 1 stay within the
        bound."""
        if not self.again_ok or self.cap <= 0 or not 1 <= shot <= len(self.takes_of):
            return False
        used = self.used()
        first = sum(self.seconds.get(j, 0.0) for j in self.takes_of[shot - 1][0])
        return used + first <= self.cap + 1e-9

    def used(self) -> float:
        """The render seconds every take after a shot's first has used."""
        return sum(self.seconds.get(j, 0.0) for shot in self.takes_of for take in shot[1:] for j in take)

    # ---------------------------------------------------------------- the verdict, its rank and line
    def verdict(self, judge: dict | None, shot: int) -> tuple[Take, str]:
        """Shot `shot`'s (1-based) take judged: (its `Take`, its failing judges in a few words)."""
        plan = self.shots[shot - 1]
        lines, results, short, unseen = [], [], [], []   # results: (passes, value ÷ bar or None)
        spoken = bool(plan.get("lines"))
        worded = any(str(x.get("words") or "").strip() for x in plan.get("lines") or [] if isinstance(x, dict))
        if judge is None:
            return Take(True, (1.0, 0.0, 1.0), NOT_JUDGED.format(NO_JUDGE)), ""
        face = judge.get("face")
        if "face" in judge and not isinstance(face, dict):
            unseen.append(takes.UNSEEN.format(judge.get("why") or "no face was scored"))
        lowest = None
        for name, v in (face or {}).items():
            if not isinstance(v, dict) or v.get("median") is None:
                continue
            median, lost = float(v["median"]), v.get("lost_at") is not None
            passes = median >= self.face_bar and not (lost and float(v.get("first") or 0) >= self.face_bar)
            lines.append(takes.face_line(judge, name, 0.0 if lost else median, self.face_bar))
            results.append((passes, median / self.face_bar))
            if not passes:
                short.append(f"{_who(name)}'s face {median:.2f}")
            lowest = name if lowest is None or median < float(face[lowest]["median"]) else lowest
        lines += [takes.FACELESS.format(n) for n in judge.get("faceless") or []]
        mouth = judge.get("mouth")
        speaker = mouth.get("speaker") if isinstance(mouth, dict) else None
        if spoken and isinstance(mouth, dict):
            line, bad = takes.mouth_line(judge, self.lips_bar)
            lips, moving = mouth.get("lips"), mouth.get("moving")
            still = moving is not None and moving < takes.STILL_SHARE
            ratio = moving / takes.STILL_SHARE if still else lips / self.lips_bar if lips is not None else 1.0
            lines.append(line)
            results.append((not bad, ratio))
            if bad:
                who = _who(speaker or "the speaker")
                short.append(f"{who}'s mouth is still" if still else f"{who}'s mouth {lips:.2f}")
        elif spoken:
            unseen.append(takes.mouth_line(judge, self.lips_bar)[0])
        framing = (plan.get("camera") or {}).get("framing")
        if _framed(framing) and judge.get("frame") and lowest is not None:
            name = takes.frame_subject(judge, framing, speaker, lowest)
            if ((judge["frame"].get(name) or {}).get("size")) is not None:
                line = takes.frame_line(judge, name, framing, self.close, self.wide)
                results.append((line is None, None))
                if line:
                    lines.append(line)
                    short.append(f"{_who(name)}'s face size {judge['frame'][name]['size']:.2f}")
        if spoken and worded:                                # a kept sound's clip: its words not judged
            words = judge.get("words")
            if isinstance(words, dict) and isinstance(words.get("heard"), (int, float)):
                heard = float(words["heard"])
                said = takes.HEARD.format(round(heard * 100))
                lines.append(said[0].lower() + said[1:] if lines else said)
                results.append((heard >= self.words_bar, heard / self.words_bar))
                if heard < self.words_bar:
                    short.append(f"heard {round(heard * 100)}%")
            else:
                unseen.append(takes.UNHEARD)
            extra = unscripted(mouth, words)
            if extra is not None and extra > self.unscripted_bar:
                who = _who(speaker or next((x.get("speaker") for x in plan["lines"] if isinstance(x, dict)), None)
                           or "the speaker")
                lines.append(takes.UNSCRIPTED.format(who, f"{extra:.1f}"))
                results.append((False, self.unscripted_bar / extra))
                short.append(f"{who} {extra:.1f} s not the line")
        if not results:
            why = "; ".join(unseen) or NO_JUDGE
            return Take(True, (1.0, 0.0, 1.0), NOT_JUDGED.format(why)), ""
        passes = all(ok for ok, _ in results)
        values = [v for _, v in results if v is not None]
        rank = (1.0 if passes else 0.0, float(sum(ok for ok, _ in results)), min(values) if values else 1.0)
        return Take(passes, rank, "; ".join([*lines, *unseen])), ", ".join(short)

    # ---------------------------------------------------------- the lines on screen
    def lines(self, landed: Mapping[int, str], chosen: Mapping[int, int | None],
              seen: Mapping[int, Take] | None = None) -> tuple[str, dict[str, str]]:
        """The scene line and each landed take's chip (`Take t · in the cut | not used · <line>`), by item id.
        `chosen`: each shot (1-based) -> the last task of its take in the cut; `seen`: every take's verdict (the
        job's, failed takes included), else the ones judged here."""
        seen = dict(self.seen if seen is None else seen)
        parts, chips = [], {}
        for n, shot in enumerate(self.takes_of, 1):
            number, first = self.numbers[n - 1]
            pick = chosen.get(n)
            said = f"shot {number} not made"
            others = []
            for t, take in enumerate(shot, first):
                verdict = next((seen[j] for j in take if j in seen and not seen[j].rank), seen.get(take[0]))
                if take[-1] in landed:
                    used = "in the cut" if take[-1] == pick else "not used"
                    chips[landed[take[-1]]] = CHIP.format(t, used, verdict.line if verdict else NOT_JUDGED.format(
                        NO_JUDGE))
                if take[-1] == pick:
                    said = f"shot {number} take {t}"
                    if verdict is not None and not verdict.passes:
                        said += f", under the bar: {verdict.line}"
                    elif verdict is not None and verdict.line.startswith(NOT_JUDGED[:10]):
                        said += f", {verdict.line[0].lower()}{verdict.line[1:]}"
                elif verdict is not None and not verdict.rank:
                    others.append(verdict.line)
                elif verdict is not None and not verdict.passes:
                    others.append(f"take {t}: {self.short.get(take[0]) or verdict.line}")
            parts.append(said + (f" ({'; '.join(others)})" if others else ""))
        line = "; ".join(parts)
        if self.again_ok and any(len(shot) > 1 for shot in self.takes_of):
            line += "; " + USED.format(self.used() / 60, self.cap / 60)
        return line[:1].upper() + line[1:], chips


class LineJudge(ShotJudge):
    """A spoken line's takes: a take passes when the words judge heard `speech_words_bar` of its words;
    rank (passes, heard, no miss, the first miss later); no reading (Whisper absent): it passes, `takes.UNHEARD`.
    `again` and `used` are the shot's: the re-takes' measured seconds within the bound."""

    def __init__(self, ctx: Ctx, takes_of: tuple, seconds_cap: float) -> None:
        super().__init__(ctx, [{}], takes_of, seconds_cap)
        self.bar = float(ctx.settings.get("speech_words_bar") or 0.9)

    def verdict(self, judge: dict | None, shot: int) -> tuple[Take, str]:
        words = (judge or {}).get("words")
        if not isinstance(words, dict) or not isinstance(words.get("heard"), (int, float)):
            return Take(True, (1.0, 0.0, 0.0, 0.0), takes.UNHEARD), ""
        heard, miss = float(words["heard"]), words.get("first_miss")
        passes, pct = heard >= self.bar, round(heard * 100)
        line = takes.HEARD.format(pct) if passes or miss is None else MISSED.format(pct, miss)
        rank = (1.0 if passes else 0.0, heard, 1.0 if miss is None else 0.0, float(miss or 0.0))
        return Take(passes, rank, line), "" if passes else f"heard {pct}%"
