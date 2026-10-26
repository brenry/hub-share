"""HTTP for media: `/files/<item>` (pictures; clips as `video/mp4`, with Range), `/thumbs/<item>/<size>`,
`POST /api/upload` (a picture from the browser lands in Temp), `POST /api/characters/sample?id=` (a
recording, made a WAV by the browser, as a character's voice), `POST /api/sounds/upload` (a recording
from the browser, made a WAV by the browser, kept in Sounds), `POST /api/sounds/audience` (a
sound kept as the scene's audience, `{id, kind}`), `POST /api/media/check` (the ids a page wants to use
as references, confirmed: pictures only).

Uploads: PNG, JPEG or WebP up to 25 MB; the magic bytes must match the content type, and Pillow must read a
header of at most 64 megapixels before the file is kept (in Temp, named by the time, its metadata cut). A voice
sample: `audio/wav` up to 4 MB (15 s at 32 kHz, two channels, 16-bit is 1.92 MB), held in a temp file in the Temp
while it is checked and copied in, then erased. A sound for Sounds: `audio/wav` up to 116 MB (10 minutes at 48 kHz,
two channels, 16-bit is 115.2 MB), received into the Temp, then moved into Sounds with only its sound kept.
Pictures, clips and thumbnails are sent with `no-store`: a browser keeps no copy of them.
"""
from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

from PIL import Image
from starlette.requests import Request
from starlette.responses import FileResponse, PlainTextResponse, Response
from starlette.routing import BaseRoute

from hub.core.api import Invalid
from hub.core.files import MEDIA_TYPES, Files
from hub.core.guard import Gate, http_route
from hub.core.thumbs import MAX_PIXELS

if TYPE_CHECKING:
    from collections.abc import Callable

MAX_UPLOAD = 25 * 1024 * 1024
UPLOAD_TYPES = {"image/png": (".png", "PNG"), "image/jpeg": (".jpg", "JPEG"), "image/webp": (".webp", "WEBP")}
BAD_UPLOAD = "PNG, JPEG or WebP up to 25 MB"
MAX_SOUND = 116_000_000


def magic_ok(head: bytes, ctype: str) -> bool:
    if ctype == "image/png":
        return head.startswith(b"\x89PNG\r\n\x1a\n")
    if ctype == "image/jpeg":
        return head.startswith(b"\xff\xd8\xff")
    return head[:4] == b"RIFF" and head[8:12] == b"WEBP"


def check_image(path: Path, ctype: str) -> None:
    """Raise Invalid unless `path` is a sane image of the declared type."""
    with open(path, "rb") as f:
        if not magic_ok(f.read(12), ctype):
            raise Invalid("image", BAD_UPLOAD)
    try:
        with Image.open(path) as im:
            if im.format != UPLOAD_TYPES[ctype][1]:
                raise Invalid("image", BAD_UPLOAD)
            if im.width * im.height > MAX_PIXELS:
                raise Invalid("image", "That image is too large (over 64 megapixels)")
            im.verify()
    except (Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise Invalid("image", "That image is too large (over 64 megapixels)") from None
    except Invalid:
        raise
    except Exception:
        raise Invalid("image", "That image could not be read") from None


async def _receive(request: Request, folder: Path) -> Path:
    """The request's body in a temp file in `folder` (the caller erases it); Invalid when it is empty."""
    fd, name = tempfile.mkstemp(dir=folder, prefix=".up-")
    tmp, size = Path(name), 0
    try:
        with os.fdopen(fd, "wb") as f:
            async for chunk in request.stream():
                size += len(chunk)
                f.write(chunk)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return tmp


def file_routes(gate: Gate, files: Files, changed: Callable[[str], None] | None = None) -> list[BaseRoute]:
    async def serve_file(request: Request) -> Response:
        try:
            path = files.existing_media(request.path_params["item"])
        except Invalid:
            return PlainTextResponse("Not Found", 404)
        # FileResponse answers Range itself (206 with Content-Range, 416 past the end), so a clip can be sought
        return FileResponse(path, media_type=MEDIA_TYPES[path.suffix.lower()], headers={"cache-control": "no-store"})

    async def serve_thumb(request: Request) -> Response:
        item, size = request.path_params["item"], request.path_params["size"]
        try:
            data = await asyncio.get_running_loop().run_in_executor(None, files.thumbnail, item, size)
        except Invalid:
            return PlainTextResponse("Not Found", 404)
        return Response(data, media_type="image/webp", headers={"cache-control": "no-store"})

    async def upload(request: Request) -> dict:
        ctype = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        ext = UPLOAD_TYPES[ctype][0]
        tmp = await _receive(request, files.roots["out"])
        try:
            if tmp.stat().st_size == 0:
                raise Invalid("image", BAD_UPLOAD)
            await asyncio.get_running_loop().run_in_executor(None, check_image, tmp, ctype)
            return {"id": files.take_in(tmp, ext)}
        finally:
            tmp.unlink(missing_ok=True)

    async def voice_sample(request: Request) -> dict:
        """The recording as the voice of the character `id` (`chars/<file>`): -> {id, seconds}."""
        tmp = await _receive(request, files.roots["out"])
        try:
            made = await asyncio.get_running_loop().run_in_executor(
                None, files.character_sample_put, request.query_params.get("id", ""), tmp)
        finally:
            tmp.unlink(missing_ok=True)
        if changed is not None:
            changed("characters")
        return made

    async def sound_upload(request: Request) -> dict:
        """The recording, as a WAV, into Sounds: -> {id, seconds}."""
        tmp = await _receive(request, files.roots["out"])
        try:
            made = await asyncio.get_running_loop().run_in_executor(None, files.take_in_sound, tmp)
        finally:
            tmp.unlink(missing_ok=True)
        if changed is not None:
            changed("sounds")
        return made

    async def keep_audience(request: Request) -> dict:
        """A sound of Sounds as the audience's applause, laughter or gasps (`sounds/audience/<kind>.wav`, replacing):
        {id, kind} -> {id}."""
        body = await request.json()
        body = body if isinstance(body, dict) else {}
        made = await asyncio.to_thread(files.keep_audience, body.get("id"), body.get("kind"))
        if changed is not None:
            changed("sounds")
        return {"id": made}

    async def check(request: Request) -> dict:
        """The ids a page wants to use: each one confirmed to be a picture the hub can read, as it is."""
        body = await request.json()
        items = body.get("items") if isinstance(body, dict) else None
        if not isinstance(items, list) or not items or not all(isinstance(i, str) for i in items):
            raise Invalid("items", "Send one or more media items")       # no count of the Hub's
        for item in items:
            files.existing_image(item)
        return {"placed": [{"item": item, "id": item} for item in items]}

    return [http_route(gate, "/files/{item:path}", "GET", serve_file, "screen"),
            http_route(gate, "/thumbs/{item:path}/{size:int}", "GET", serve_thumb, "screen"),
            http_route(gate, "/api/upload", "POST", upload, "screen", limit=MAX_UPLOAD, body="image"),
            http_route(gate, "/api/characters/sample", "POST", voice_sample, "screen", limit=MAX_SOUND, body="sound"),
            http_route(gate, "/api/sounds/upload", "POST", sound_upload, "screen", limit=MAX_SOUND, body="sound"),
            http_route(gate, "/api/sounds/audience", "POST", keep_audience, "screen"),
            http_route(gate, "/api/media/check", "POST", check, "screen")]
