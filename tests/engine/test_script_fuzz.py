"""Every hint lands, and the line end holds through the script tools on a
version-2 script in a temp folder, with seeded random calls. Its own copy of the hint table (the contract, not
`landing.py`): each refusal holds at most one correction, only on a call the table sends it back to; sent back as the
table says it is accepted, or refused with another problem that carries none; no refusal names one of the Hub's own
keyframes (`auto`); after every accepted write each speaker's keyframes from a run's start to its end hold the pose of
the speaker's keyframe at the run's start, none inside one of the speaker's lines."""
from __future__ import annotations

import json
import random
import re
from pathlib import Path
from typing import Any

import pytest

from hub.core.api import Invalid
from hub.modules.director import scriptshape
from tests.engine.test_script_tools import NINE, Ctx, call, framed, on_disk

VALUED = ("latest_start_ms", "suggested_start_ms", "after_ms", "max_words", "max_seconds", "anchor")
WORDS = (NINE + " " + NINE + " " + NINE + " " + NINE).split()


async def threed(ctx: Ctx) -> None:
    """Script 1: scene 1 (Character 7, Character 6), shots s1, s2 and s3."""
    await framed(ctx)
    await call(ctx, "shot_add", {"scene": 1, "camera": "Close on Character 7"})


def shots(script: dict) -> list[dict]:
    return [shot for sc in script["scenes"] for shot in sc["shots"]]


def event(script: dict, ident: str) -> dict | None:
    return next((ev for shot in shots(script) for ev in shot["events"] if ev["id"] == ident), None)


def table(name: str, args: dict, got: dict, script: dict) -> tuple[int, list[tuple[str, dict]]] | None:
    """The hint table: (the row, the calls that send the correction back); None when the refusal carries none."""
    h = got["hints"]
    if "max_words" in h and name in ("line_add", "event_change"):
        n = h["max_words"]
        if name == "line_add":
            return 5, [(name, {**args, "words": " ".join(args["words"].split()[:n])})]
        words = args["fields"].get("words") or event(script, args["id"])["words"]
        return 5, [(name, {**args, "fields": {**args["fields"], "words": " ".join(words.split()[:n])}})]
    if "max_seconds" in h and name == "event_change":
        return 6, [(name, {**args, "fields": {**args["fields"], "seconds": h["max_seconds"]}})]
    if "anchor" in h and name == "cue_add":
        return 7, [(name, {**args, "anchor": h["anchor"]})]
    when = h.get("after_ms", h.get("suggested_start_ms"))
    if when is not None and "id" in h:
        return 2, [("event_move", {"id": h["id"], "start_ms": when, "shot": h["shot"]}), (name, args)]
    if "after_ms" in h and name == "event_change" and "pose" in args["fields"]:
        who = event(script, args["id"])["character"]
        return 3, [("pose_add", {"shot": h["shot"], "character": who, "pose": args["fields"]["pose"],
                                 "start_ms": h["after_ms"]})]
    if name in ("pose_add", "event_move"):
        when = h.get("latest_start_ms", h.get("suggested_start_ms", h.get("after_ms")))
        row = 1
        if when is None and "end_ms" in h and "id" not in h and "starts inside" in got["problem"]:
            when, row = h["end_ms"], 4
        if when is not None:
            sent = {k: v for k, v in args.items() if k != "anchor"}
            sent["start_ms"] = when
            if name == "event_move":
                sent["shot"] = h["shot"]
            return row, [(name, sent)]
    return None


async def attempt(ctx: Ctx, name: str, args: dict) -> dict | None:
    """None when accepted; else the refusal."""
    try:
        await call(ctx, name, args)
    except Invalid as e:
        return json.loads(e.text)
    return None


def draw(rng: random.Random, script: dict) -> tuple[str, dict]:
    every = shots(script)
    shot = rng.choice(every)
    sid = shot["id"]
    lines = [ev for ev in shot["events"] if ev["kind"] == "line"]
    events = [ev for s in every for ev in s["events"] if ev["kind"] in ("line", "cue", "pose")]
    marks = [ev[k] - shot["start_ms"] for ev in lines for k in ("start_ms", "end_ms")]
    when = rng.choice([*(m + d for m in marks for d in (0, 0, 1, -1, 300, 500, 700)), 14_080, 14_081, 13_500,
                       rng.randrange(0, 15_080)] or [0])
    when = max(0, min(15_080, when))
    kind = rng.choices(["line", "cue", "pose", "move", "change", "remove"], [6, 3, 6, 4, 5, 1])[0]
    who = rng.choice(["Character 7", "Character 6"])
    if kind == "line" or (kind in ("move", "change", "remove") and not events):
        return "line_add", {"shot": sid, "speaker": who, "words": " ".join(WORDS[:rng.choice([3, 6, 9, 9, 14, 30])])}
    if kind == "cue":
        args = {"shot": sid, "cue": rng.choice(scriptshape.CUES), "words": "Applause"}
        if lines and rng.random() < 0.6:
            args["anchor"] = {"line": rng.choice(lines)["id"], "at": rng.choice(["start", "end"])}
        return "cue_add", args
    if kind == "pose":
        args = {"shot": sid, "character": who, "pose": rng.choice(scriptshape.POSES)}
        if lines and rng.random() < 0.3:
            args["anchor"] = {"line": rng.choice(lines)["id"], "at": rng.choice(["start", "end"])}
        else:
            args["start_ms"] = when
        return "pose_add", args
    ev = rng.choice(events)
    if kind == "remove":
        return "event_remove", {"id": ev["id"]}
    if kind == "move":
        args = {"id": ev["id"], "start_ms": when}
        if rng.random() < 0.25:
            args["shot"] = rng.choice(every)["id"]
        return "event_move", args
    if ev["kind"] == "line":
        return "event_change", {"id": ev["id"], "fields": {"words": " ".join(WORDS[:rng.choice([2, 9, 20, 36])])}}
    if ev["kind"] == "cue":
        return "event_change", {"id": ev["id"], "fields": {"seconds": rng.choice([0.5, 2.0, 6.0, 10.0, 15.0])}}
    return "event_change", {"id": ev["id"], "fields": {"pose": rng.choice(scriptshape.POSES)}}


def own(name: str, args: dict, script: dict) -> set[str]:
    """The event the call acts on: its `id`, or the keyframe `pose_add` replaces (the Director's now)."""
    if "id" in args:
        return {args["id"]}
    shot = next((s for s in shots(script) if s["id"] == args.get("shot")), None)
    if name != "pose_add" or shot is None:
        return set()
    return {ev["id"] for ev in shot["events"] if ev["kind"] == "pose" and ev["character"] == args["character"]
            and ev["start_ms"] - shot["start_ms"] in (args.get("start_ms"), *[x - shot["start_ms"] + 500 for x in
                                                                              (e["end_ms"] for e in shot["events"])])}


def contract(name: str, args: dict, got: dict, script: dict) -> None:
    """On one refusal: at most one correction, only where the table sends it; no `auto` keyframe named."""
    held = [k for k in VALUED if k in got["hints"]]
    assert len(held) <= 1, got
    assert not held or table(name, args, got, script) is not None, (name, args, got)
    autos = {ev["id"] for shot in shots(script) for ev in shot["events"] if ev.get("auto")} - own(name, args, script)
    named = set(re.findall(r"\bp[0-9]+\b", got["problem"])) | ({got["hints"]["id"]} if "id" in got["hints"] else set())
    assert not named & autos, (name, args, got)


def holds(script: dict) -> None:
    """Each speaker's keyframes from a run's start to its last line's end hold the run's start pose; none lies
    inside one of the speaker's lines."""
    for shot in shots(script):
        lines = sorted((ev for ev in shot["events"] if ev["kind"] == "line"), key=lambda ev: ev["start_ms"])
        for who in {ln["speaker"] for ln in lines}:
            mine = [ln for ln in lines if ln["speaker"] == who]
            kfs = [ev for ev in shot["events"] if ev["kind"] == "pose" and ev["character"].casefold() == who.casefold()]
            runs: list[list[dict]] = []
            for ln in mine:
                if runs and runs[-1][-1]["end_ms"] == ln["start_ms"]:
                    runs[-1].append(ln)
                else:
                    runs.append([ln])
            for run in runs:
                start, end = run[0]["start_ms"], run[-1]["end_ms"]
                first = [kf["pose"] for kf in kfs if kf["start_ms"] == start]
                assert len(first) == 1, (shot["id"], who, start, kfs)
                bad = [kf for kf in kfs if start < kf["start_ms"] <= end and kf["pose"] != first[0]]
                assert not bad, (shot["id"], who, run, bad)
            inside = [kf for kf in kfs for ln in mine if ln["start_ms"] < kf["start_ms"] < ln["end_ms"]]
            assert not inside, (shot["id"], who, inside)


async def step(ctx: Ctx, rng: random.Random, rows: dict[int, int], check: Any = None) -> None:
    """One drawn call; its refusal's correction sent back per the table."""
    script = on_disk(ctx)
    name, args = draw(rng, script)
    got = await attempt(ctx, name, args)
    if got is None:
        if check:
            check(on_disk(ctx))
        return
    contract(name, args, got, script)
    found = table(name, args, got, script)
    if found is None:
        return
    row, calls = found
    rows[row] = rows.get(row, 0) + 1
    for n, (tool, sent) in enumerate(calls):
        before = on_disk(ctx)
        again = await attempt(ctx, tool, sent)
        if again is not None:
            assert n == len(calls) - 1, ("a correction's first call refused", name, args, got, tool, sent, again)
            assert again["problem"] != got["problem"], ("the same refusal again", name, args, got, sent, again)
            contract(tool, sent, again, before)
            assert table(tool, sent, again, before) is None, ("two corrections in a row", got, sent, again)
            return
        if check:
            check(on_disk(ctx))


@pytest.fixture
def ctx(tmp_path: Path) -> Ctx:
    return Ctx(tmp_path)


async def test_two_hundred_calls_every_hint_lands(ctx: Ctx) -> None:
    await threed(ctx)
    rng, rows = random.Random(61), {}
    for _ in range(200):
        await step(ctx, rng, rows)
    assert sorted(rows) == [1, 2, 3, 4, 5, 6, 7], f"each of the table's seven rows sent back at least once: {rows}"


async def test_a_hundred_seeds_hold_the_line_start_pose(tmp_path: Path) -> None:
    for seed in range(100):
        (tmp_path / str(seed)).mkdir()
        ctx = Ctx(tmp_path / str(seed))
        await threed(ctx)
        rng: random.Random = random.Random(seed)
        for _ in range(40):
            await step(ctx, rng, {}, holds)
