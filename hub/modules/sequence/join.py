"""The save job (`sequence.join`): one task on the engine lane that loads no model (`NO_MODEL`).

The task is a join request (`api.JoinRequest`); the worker runs ffmpeg on it and the file lands in Media as the
newest: an MP4 in Clips when track 1 holds clips (stream copy when every clip is whole and alike and track 2 is
empty, else an encode at the first clip's size and rate), else a WAV in Sounds:

    JoinRequest(items=[JoinItem(path, in, out, fps, w, h, frames, audio, sound)],   # track 1, play order
                canvas=Canvas(w, h, fps),                    # the first clip's; a WAV: 0, 0, 1000
                audio=[JoinSound(path, at_ms, in, out, fps, level, fade_in, fade_out, duck)],  # track 2, cut at the end
                crf, preset, out_kind,                        # settings: join_crf, join_preset; "mp4" or "wav"
                duck=Duck(threshold, ratio, attack, release))  # settings duck_*

A sound counts its milliseconds as frames (`fps` 1000). The file is as long as track 1, or, with track 1 empty, as
the end of track 2's last item; a track-2 item past the end is cut there, one that starts after it is left out, and
a clip on track 2 without sound adds nothing (its picture is not used: video over video is later).
"""
from __future__ import annotations

import math
import os

from hub.core.api import NO_MODEL, Canvas, Ctx, Duck, Invalid, JobPlan, JoinItem, JoinRequest, JoinSound, request_wire

from . import routes

CRF, PRESET = 18, "medium"


def _path(ctx: Ctx, f: dict) -> str:
    return os.path.realpath(ctx.files.existing_media(f["id"]))


def plan(params: dict, ctx: Ctx) -> JobPlan:
    seq = routes.read(ctx, params.get("name"))
    if not any(seq["tracks"]):
        raise Invalid("name", "The sequence is empty")
    t1, t2 = routes.with_facts(ctx, seq)
    if len(t1) + len(t2) < sum(len(t) for t in seq["tracks"]):
        raise Invalid("name", "An item of the sequence is gone")
    end = routes.length([t1, t2])
    items = [JoinItem(_path(ctx, f), int(it["in"]), int(it["out"]), float(f["fps"]), int(f["w"]), int(f["h"]),
                      int(f["frames"]), bool(f["audio"]), f["kind"] == "sound") for it, f in t1]
    sounds = []
    for it, f in t2:
        start = it["at"] / 1000
        if not f["audio"] or start >= end:
            continue
        out = min(int(it["out"]), int(it["in"]) + math.floor((end - start) * f["fps"] + 1e-6))
        if out > it["in"]:
            sounds.append(JoinSound(_path(ctx, f), int(it["at"]), int(it["in"]), out, float(f["fps"]),
                                    float(it.get("level", 1)), int(it.get("fade_in") or 0),
                                    int(it.get("fade_out") or 0), bool(it.get("duck"))))
    video = next((i for i in items if not i.sound), None)
    kind = "mp4" if video is not None else "wav"
    canvas = Canvas(video.w, video.h, video.fps) if video is not None else Canvas(0, 0, 1000.0)
    st = ctx.settings
    duck = Duck(float(st.get("duck_threshold", 0.05)), float(st.get("duck_ratio", 6.0)),
                float(st.get("duck_attack_ms", 50.0)), float(st.get("duck_release_ms", 400.0)))
    request = JoinRequest(items, canvas, sounds, int(st.get("join_crf", CRF)), str(st.get("join_preset", PRESET)),
                          kind, duck)
    n = len(items) + len(sounds)
    return JobPlan(lane_kind="image", model=NO_MODEL, tasks=(request_wire(request),),
                   summary={"kind": "clip" if kind == "mp4" else "sound", "mode": "join",
                            "title": f"Save · {seq['name']} · {n} item{'' if n == 1 else 's'}", "clips": n,
                            "seconds": round(end, 2)})
