"""The mix's finish: the master and the stems filed in Sounds and the record written, when the script is as it was
at the press. `write` returns the master as placed, or the one reason it kept none, and the finish's `finally` hands
that to `autolock.mix_note`, the Hub's line in its chat. The master is kept only when the mix built again from the
script as it is now has the press's hash; then `autolock.mix_done` presses once a change that came while it mixed.
"""
from __future__ import annotations

import asyncio
import shutil
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from hub.core.api import Ctx, Invalid

from . import lock, place, routes, scripts

CHANGED = "the script changed while it mixed"
UNPLACED = "the master could not be placed in Sounds"
UNWRITTEN = "the script could not be written"


def _place(src: Path, folder: Path, stem: str, record: Mapping[str, Any]) -> Path:
    """To `<stem>.wav` when free or the record's own (name, size), else `<stem>-<n>.wav` from 2."""
    folder.mkdir(parents=True, exist_ok=True)
    dest, n, own = folder / f"{stem}.wav", 2, str(record.get("file") or "").rsplit("/", 1)[-1]
    while dest.exists() and not (dest.name == own and dest.is_file() and dest.stat().st_size == record.get("size")):
        dest, n = folder / f"{stem}-{n}.wav", n + 1
    shutil.move(str(src), str(dest))
    return dest


class Finish:
    """The master and the stems filed and the record written, when the script is as it was at the press."""

    def __init__(self, ctx: Ctx, name: str, made: dict, stems: bool) -> None:
        self.ctx, self.name, self.made, self.stems = ctx, name, made, stems
        self.job: str | None = None

    async def __call__(self, landed: Mapping[int, str]) -> None:
        from . import autolock, mix, tools  # late: they read this module's neighbours

        got: Path | str | None = None
        try:
            if landed.get(1) is None:
                made = self.ctx.jobs.get(self.job) if self.job else None
                mix.failed[self.name] = str(getattr(made, "error", None) or mix.NOT_LANDED)
                return
            async with tools._guard():
                got = await asyncio.to_thread(self.write, landed)
        finally:
            if mix.running.get(self.name) == self.job:
                mix.running.pop(self.name, None)
            tools._publish(self.ctx, self.name)
            autolock.mix_note(self.ctx, self.name, got, self.made["mix"]["length_ms"])
            await autolock.mix_done(self.ctx, self.name)

    def _moved(self, script: dict) -> bool:
        """The mix built again from `script` (the room's length as the press measured it) has another
        hash than the press's, or is refused (a take gone, the script no longer mixable)."""
        from . import mix  # late: it reads this module

        try:
            again = mix.build(self.ctx, self.name, script, room_ms=self.made["mix"].get("room_ms"))
        except Invalid:
            return True
        return again["mix"]["hash"] != self.made["mix"]["hash"]

    def write(self, landed: Mapping[int, str]) -> Path | str:
        """-> the master as placed, or why none was kept (`CHANGED`, `UNPLACED`, `UNWRITTEN`)."""
        folder, files, keyed = routes.folder(self.ctx), self.ctx.files, (lambda t: {
            k: (v.get("file"), v.get("hash")) for k, v in t.items()})
        try:
            script = scripts.readable(folder, self.name, routes.characters(self.ctx))
        except Invalid:
            return CHANGED                               # the script gone or unreadable: the WAV stays where it landed
        if not lock.locked(script) or keyed(script.get("takes") or {}) != keyed(self.made["takes"]):
            return CHANGED                               # changed meanwhile: the WAVs stay where they landed
        if self._moved(script):
            return CHANGED                               # placed otherwise now (a move, a re-timed line)
        old, sounds = script.get("renders") or {}, files.roots["sounds"]
        try:
            track = _place(files.existing_media(landed[1]), sounds, self.name,
                           {"file": old.get("track"), "size": old.get("size")})
        except (Invalid, OSError):
            return UNPLACED
        stems = {} if self.stems else dict(old.get("stems") or {})
        for k, lane in enumerate(self.made["lanes"], 2):
            try:
                if self.stems and landed.get(k) is not None:
                    got = _place(files.existing_media(landed[k]), sounds / self.name / "stems",
                                 lane["name"].replace("/", "_").replace("\\", "_"),
                                 (old.get("stems") or {}).get(lane["name"]) or {})
                    stems[lane["name"]] = {"file": got.relative_to(sounds).as_posix(), "size": got.stat().st_size}
            except (Invalid, OSError):
                continue
        renders = {"track": track.name, "size": track.stat().st_size, "stems": stems}
        try:
            scripts.change(folder, self.name, routes.characters(self.ctx),
                           lambda s: place.apply(s, self.made["placed"], self.made["mix"], renders))
        except Invalid:
            return UNWRITTEN
        return track
