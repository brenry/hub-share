"""What Edit Video can do, declared for the tool server: the sequences (`list_sequences`), one sequence's items on
its two tracks (`list_sequence_clips`), adding the newest clip Generate Image made to track 1 (`add_last_clip`) and
queueing the save (`join_sequence`: an MP4 or a WAV). Seconds are rounded to two decimals; a place counts
from 1 on each track."""
from __future__ import annotations

import asyncio

from hub.core.api import Action, Ctx, Invalid, Listing

from . import last, routes

NAME = {"type": "string", "minLength": 1}
ONE: dict = {"type": "object", "additionalProperties": False, "required": ["sequence"],
             "properties": {"sequence": NAME}}
MISSING = "There is no sequence named "


def _seconds(pairs: list[list[tuple[dict, dict]]]) -> float:
    return round(routes.length(pairs), 2)


async def list_sequences(ctx: Ctx, args: dict) -> dict:
    return {"sequences": await asyncio.to_thread(ctx.files.sequences)}


async def list_sequence_clips(ctx: Ctx, args: dict) -> dict:
    seq = await routes.load(ctx, args["sequence"])
    pairs = await asyncio.to_thread(routes.with_facts, ctx, seq)
    return {"sequence": seq["name"], "seconds": _seconds(pairs), "clips": [
        {"track": n, "place": k, "kind": f["kind"], "clip": f["id"], "in_s": round(it["in"] / f["fps"], 2),
         "out_s": round(it["out"] / f["fps"], 2), "seconds": routes.kept(it, f["fps"]),
         **({"at_s": round(it["at"] / 1000, 2)} if n == 2 else {})}
        for n, track in enumerate(pairs, 1) for k, (it, f) in enumerate(track, 1)]}


async def add_last_clip(ctx: Ctx, args: dict) -> dict:
    clip = last.clip(ctx)
    if clip is None:
        raise Invalid("sequence", "No clip made in this session yet")
    facts = await asyncio.to_thread(ctx.files.clip_facts, clip)
    if facts is None:
        raise Invalid("sequence", "That clip is gone")
    try:
        seq = await routes.load(ctx, args["sequence"])
    except Invalid as e:
        if not e.text.startswith(MISSING):
            raise
        seq = await asyncio.to_thread(ctx.files.sequence_new, args["sequence"])
        routes.changed(ctx, seq["name"], seq["revision"])
    t1, t2 = seq["tracks"]
    tracks = [[*t1, {"clip": clip, "in": 0, "out": facts["frames"]}], t2]
    seq = await asyncio.to_thread(ctx.files.sequence_save, seq["name"], tracks, seq["revision"])
    routes.changed(ctx, seq["name"], seq["revision"])
    pairs = await asyncio.to_thread(routes.with_facts, ctx, seq)
    return {"sequence": seq["name"], "place": len(seq["tracks"][0]), "clip": clip,
            "clips": sum(len(t) for t in seq["tracks"]), "seconds": _seconds(pairs)}


async def join_sequence(ctx: Ctx, args: dict) -> dict:
    job = ctx.jobs.submit("join", {"name": args["sequence"]})
    summary = job.plan.summary
    return {"job": job.id, "kind": "clip" if summary["kind"] == "clip" else "sound", "clips": summary["clips"],
            "seconds": summary["seconds"]}


LISTINGS = (Listing("sequences", "Sequences by name, with the number of items and the seconds of each.", {},
                    list_sequences),
            Listing("sequence_clips", "Items of one sequence by track in play order: place, clip or sound id, in and "
                    "out in seconds, seconds kept, and where a track 2 item starts.", {"sequence": NAME},
                    list_sequence_clips, required=("sequence",)))
ACTIONS = (Action("add_last_clip", "Adds the newest clip Generate Image made to the end of a sequence's track 1, "
                  "whole; a new name starts a new sequence.", ONE, add_last_clip),
           Action("join_sequence", "Queues one file of a sequence, cut at in and out points: an MP4 into Clips when "
                  "track 1 holds clips, else a WAV into Sounds.", ONE, join_sequence))
