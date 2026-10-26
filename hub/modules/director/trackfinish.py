"""Track's finish: the job's last step, whatever its end: every landed take filed in Sounds as
`<script>/<id>-<n>.wav` (kept, never overwritten), the best take of each line, cue and the room recorded in the
script's `takes` (one `scripts.change`), then the mix when every take is in (`mix.after_track`). An id with no take is
`failed` with its own reason, the line of its last failed take (`take <t> failed: <the task's error>`), else the job's
error, else `no take landed`. Last, the Hub's line in its chat and the press a change made while the job ran
(`autolock.track_ended`).
"""
from __future__ import annotations

import asyncio
import re
import shutil
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from hub.core.api import Ctx, Invalid, JobPlan, best_take

from . import cuetakes, layout, mix, routes, scripts, takejudge

_TAKE_NAME = re.compile(r"(.+)-(\d+)\.wav")


def _free(folder: Path, ident: str) -> int:
    """The next number after the takes of `ident` already in `folder` (1 for the first)."""
    numbers = [int(m.group(2)) for p in folder.glob("*.wav") if (m := _TAKE_NAME.fullmatch(p.name))
               and m.group(1) == ident]
    return max(numbers, default=0) + 1


def _why(takes: tuple, seen: Mapping[int, Any], error: Any, none: str) -> str:
    """The line of the group's last failed take (a take with no rank that did not pass), else the job's error,
    else `none`."""
    failed = [seen[j].line for take in takes for j in take
              if j in seen and not seen[j].passes and not seen[j].rank and seen[j].line]
    return failed[-1] if failed else str(error or none)


class Finish:
    """The job's last step, whatever its end: every landed take filed, each line's best recorded."""

    def __init__(self, ctx: Ctx, name: str, ids: list[str], hashes: Mapping[str, str],
                 judge: takejudge.TrackJudge, takes_of: tuple) -> None:
        self.ctx, self.name, self.ids, self.hashes, self.judge, self.takes_of = ctx, name, ids, hashes, judge, takes_of
        self.job: str | None = None
        self.more, self.lines, self.n = cuetakes.More(), len(ids), 1     # set by `job`

    async def __call__(self, landed: Mapping[int, str]) -> None:
        from . import autolock, tools, track  # late: they read this module's neighbours

        not_mixed = None
        try:
            made = self.ctx.jobs.get(self.job) if self.job else None
            seen = {**self.judge.seen, **(getattr(made, "takes", None) or {})}
            error = getattr(made, "error", None)
            filed = await asyncio.to_thread(self.file, landed)
            entries = self.entries(landed, filed, seen, error)
            if entries:
                async with tools._guard():
                    await asyncio.to_thread(self.record, entries)
            not_mixed = mix.after_track(self.ctx, self.name)  # the mix, when every take is in
        finally:
            if track.running.get(self.name, {}).get("job") == self.job:
                track.running.pop(self.name, None)
            track._publish(self.ctx, self.name)
            await autolock.track_ended(self.ctx, self.name, not_mixed)   # the line, the pending

    def file(self, landed: Mapping[int, str]) -> dict[int, str]:
        """Each landed take moved to `sounds/<name>/<id>-<n>.wav`, in take order -> task: its file under Sounds."""
        files = self.ctx.files
        folder = files.roots["sounds"] / self.name
        out: dict[int, str] = {}
        for ident, takes in zip(self.ids, self.takes_of, strict=True):
            for take in takes:
                item = landed.get(take[-1])
                if item is None:
                    continue
                try:
                    src = files.existing_media(item)
                    folder.mkdir(parents=True, exist_ok=True)
                    dest = folder / f"{ident}-{_free(folder, ident)}.wav"
                    shutil.move(str(src), str(dest))
                except (Invalid, OSError):
                    continue                             # it stays where it landed, in Sounds
                out[take[-1]] = f"{self.name}/{dest.name}"
        return out

    def entries(self, landed: Mapping[int, str], filed: Mapping[int, str], seen: Mapping[int, Any],
                error: Any) -> dict[str, dict]:
        """{line id: its take record} for each line with a best take filed; `failed` for each line with none, with
        its own reason."""
        from . import track  # late: track reads this module

        out = {}
        for g, (ident, takes) in enumerate(zip(self.ids, self.takes_of, strict=True), 1):
            plan = JobPlan("image", "", (), {}, takes=(takes,))
            pick = best_take(plan, 1, seen, {t: v for t, v in landed.items() if t in filed})
            if pick is None:
                track.failed[(self.name, ident)] = _why(takes, seen, error, track.NO_TAKE)
                continue
            found = self.judge.records.get(pick)
            tries = sum(1 for take in takes if take[0] in seen or take[-1] in landed)
            out[ident] = {"file": filed[pick], "hash": self.hashes[ident], "tries": max(1, tries),
                          "measured": found.measured if found else None,
                          "judge": found.judge if found else {"heard": None, "first_miss_ms": None,
                                                              "extra_speech": None, "verdict": "flagged",
                                                              "why": takejudge.NOT_HEARD if g not in
                                                              self.judge.kinds else takejudge.NOT_MEASURED}}
        return out

    def record(self, entries: Mapping[str, dict]) -> None:
        """One `scripts.change`: each line's entry replaced; the script gone or unreadable: nothing written."""
        folder = routes.folder(self.ctx)
        if not scripts.exists(folder, self.name):
            return

        def change(script: dict) -> dict:
            ids = {ev["id"] for shot in layout.shots(script) for ev in shot["events"]} | {cuetakes.ROOM_ID}
            script["takes"] = {**(script.get("takes") or {}), **{k: v for k, v in entries.items() if k in ids}}
            return {"did": "takes recorded", "shot": None}
        try:
            scripts.change(folder, self.name, routes.characters(self.ctx), change)
        except Invalid:
            return
