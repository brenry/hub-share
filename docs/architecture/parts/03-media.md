# 3. Media

Media is the Hub's picture library: the screen at `/media` and the server module `media`. It shows three roots
of files on disk (Temp, Drive, Characters), organises them (move, rename, delete), and sends pictures to the open tool's
reference boxes. It keeps no record about any picture: the file on disk is the only record. A fourth root, the
**clips**, holds the MP4 clips the engine makes; the same window shows it as the **Clips** section of its tree, between
Characters and the Drive (3.7.4, 3.7.11), and `/clips` opens the window on that section. The Temp never lists a clip. A
clip can be played, listed, continued and erased there, and nothing else: it is no reference, favorite or character.

Sources for this section:

- Server module: `hub/modules/media/manifest.py`, `routes.py`, `library.py`, `favorites.py`.
- Core pieces it uses: `hub/core/files.py`, `drive.py`, `characters.py`, `named.py`, `temp.py`, `pngtext.py`,
  `clean.py`, `thumbs.py`, `enginecat.py` (`land`, `sweep`), `fileroutes.py`.
- Web screen: `web/src/screens/media/` (`Media.tsx`, `Stage.tsx`, `Clip.tsx`, `Tree.tsx`, `Characters.tsx`, `Grid.tsx`,
  `Bar.tsx`, `media.ts`, `selection.ts`, `send.ts`, `useSend.ts`, `gridMath.ts`, `fit.ts`).
- Clips: `hub/core/clip.py` (MP4 tags and facts), `hub/core/files.py` (the root and the kinds), `hub/core/web.py:64`
  and `web/src/main.tsx:17-18` (the path `/clips` serves the same window, opened on its Clips section). Continue is the Generate module's (`hub/modules/generate_image/chain.py`,
  part 2, 2.10.7); this screen calls it through `web/src/lib/module.ts` (`continueClip`).

---

## 3.1 The module at a glance

`hub/modules/media/manifest.py:12-33` declares the module:

| Field | Value |
|---|---|
| `id` | `"media"`. Routes are mounted under `/api/media` (`hub/core/api.py:127`, "routes /api/<id>/"). |
| `screens` | `("media",)` |
| `lanes` | `("changed",)`. It is published as `media.changed` (`hub/core/context.py:54-65`, `ModuleBus._prefixed`). |
| `routes` | 16 routes (table in 3.1.1) |

The module has no `handlers`, `jobs`, `listens`, `card`, `screen`, `listings` or `actions`. The assistant reads
characters through the generate-image module, not this one (3.4.6).

### 3.1.1 Routes

All handlers are in `hub/modules/media/routes.py`. Each blocking file operation runs in
`asyncio.to_thread`.

| Method + path | Handler | Body / query | Returns | Publishes `media.changed` with `what` |
|---|---|---|---|---|
| `GET /api/media` | `list_media` (:60) | `?root=out\|clips` (default `out`; anything else is refused with "List out or clips"), `&before=<id>&limit=1..500` (default 100) | `library.page` | — |
| `POST /api/media/favorite` | `favorite` (:73) | `{ids, on}` | `{moved:[{from,to}], on}`; a clip id is refused ("Only pictures can be favorites") | `favorites` |
| `GET /api/media/favorite-folders` | `favorite_folders` (:87) | — | `{folders:[{path,name,ok}]}` | — |
| `POST /api/media/favorite-folders` | `favorite_folder` (:91) | `{path, on}` | `{folders}` | `favorite-folders` |
| `GET /api/media/drive` | `drive_list` (:105) | `?path=` | `{path,name,dirs,items,unset}` | — |
| `POST /api/media/drive/folder` | `drive_folder` (:116) | `{path, name}` | `{path}` | `drive` (+`path`) |
| `POST /api/media/drive/rename` | `drive_rename` (:123) | `{path, name}` | `{path}` | `drive` (+parent `path`) |
| `POST /api/media/drive/move` | `drive_move` (:131) | `{paths, to}` | `{paths}` | `drive` (`path=""`) |
| `POST /api/media/drive/remove` | `drive_remove` (:141) | `{path}` | `{path}` | `drive` (+parent `path`) |
| `GET /api/media/characters` | `characters_list` (:151) | — | `{unset, items}` | — |
| `POST /api/media/characters` | `character_put` (:165) | `{name, id}` | `{id}`; a clip id is refused ("Only pictures can be characters", :169-171) | `characters` |
| `POST /api/media/characters/rename` | `character_rename` (:178) | `{id, name}` | `{id}` | `characters` |
| `POST /api/media/characters/remove` | `character_remove` (:186) | `{id}` | `{name}` | `characters` |
| `POST /api/media/characters/notes` | `character_notes` (:194) | `{id, notes}` | `{id}` | `characters` |
| `POST /api/media/move` | `move` (:203) | `{ids, to}` | `{moved:[{from,to}]}`; a clip id is refused ("Only pictures can go to the Drive", :205) | `move` (+`to`) |
| `POST /api/media/delete` | `delete` (:211) | `{ids}` | `{ids}`; a clip is erased like a picture | `delete` (+`ids`) |

Common checks in `routes.py`:

- `_body` (:27-34) refuses anything that is not a JSON object (`Invalid("body", "Send a JSON object")`).
- `_ids` (:37-43) requires a list of 1 to `MAX_IDS = 500` ids, each passing `library.is_media` (a Temp, clips, Drive
  or Characters id).
- `_pictures` (:46-49) refuses a list that holds a clip, with the text the caller gives. Favorite, move and the
  Characters put use it (or the same `is_clip` test); delete does not.
- `_path` (:52-56) requires a string.
- `_changed` (:23-24) calls `ctx.bus.publish("changed", "changed", {"what": ..., **extra})`.

Four more media routes are core's, not the module's. `hub/core/fileroutes.py:103-106` registers them, and
`hub/core/runtime.py:136` mounts them:

| Route | Handler | Notes |
|---|---|---|
| `GET /files/{item:path}` | `serve_file` (:60) | `Files.existing_media` (a picture or a clip), else 404; `cache-control: no-store`. A clip is `video/mp4` through Starlette's `FileResponse`, which answers `Range` itself: 206 with `Content-Range`, 416 past the end (:65-66). Pinned by `tests/core/test_clips_http.py::test_a_clip_is_served_as_mp4_with_ranges` |
| `GET /thumbs/{item:path}/{size:int}` | `serve_thumb` (:68) | WebP from `Files.thumbnail`; `no-store`; a clip is 404 (it has no thumbnail) |
| `POST /api/upload` | `upload` (:76) | raw image body, `limit=MAX_UPLOAD` (25 MB), `body="image"` |
| `POST /api/media/check` | `check` (:93) | `{items}` 1..50 strings, each `existing_image` (so a clip is refused); returns `{placed:[{item,id}]}` with `id == item` |

All four use auth `"screen"`.

---

## 3.2 The roots and item ids

### 3.2.1 `Files.roots`

`hub/core/files.py:66-100` (`class Files`) owns the roots:

- `"out"` is Temp: `<data_dir>/outputs`. It always exists, and `Files.__init__` creates it (:72-73).
- `"clips"` is the clips root (`CLIPS`, :27): `<data_dir>/clips`. It is the Hub's own like Temp: fixed, always present
  and created in `__init__` (:72-73, :94). It holds the MP4 clips the engine makes and nothing else.
- `"drive"` is the Drive folder. It is set only when a path is given (:95-96).
- `"chars"` is the Characters folder. It is set only when a path is given (:97-98).

The docstring (`files.py:45-47`) says: "The Drive and the Characters folder are set in Settings, used as they are and never
created; until chosen, none." `set_drive` (:79) and `set_characters` (:84) re-point a root and
call `_build`. They move nothing. `_build` also caches each root's `realpath` in `self._real` (:100).
`set_storyboards` (:89-91) keeps the Drive-relative folder whose pictures may hold text (`named.text_allowed`, part 1).

The values come from settings: `hub/settings.py:258-268` (`drive_root`, `characters_root`) read
`settings["paths"]["drive"]` and `["characters"]`, which default to `""` (`hub/settings.py:31`).
`hub/core/runtime.py:82` builds `Files(data_dir, drive_root(settings), characters_root(settings))`.
`hub/core/apply.py:26-29` calls `set_drive` / `set_characters` when a setting changes. In the UI the paths are
the "Drive" and "Characters" rows in `web/src/shell/settings/CoreList.tsx:79-80`.

Path validation for both owner folders is `pathrules.drive_root` (`hub/pathrules.py:76`). It requires a
writable folder, refuses the Hub's own folder (Temp), and refuses the engine, model and LoRA folders. Only
Characters may be set back to empty (`hub/settings_edit.py:65-66`).

### 3.2.2 Item ids

An item id is `<root>/<relative posix path>` (`hub/core/files.py:1-8`):

- `out/<YYYY-MM-DD>/[<group>/]<HHMMSS-mmm>[-n].<ext>` is a Temp picture.
- `clips/<YYYY-MM-DD>/<HHMMSS-mmm>[-n].mp4` is a clip, flat in its day. Folders under a day that earlier
  continues made still exist on disk and their clips keep their four-part ids; nothing makes a new one. Only an `.mp4`
  under `clips/` is a clip; a picture under `clips/` and an `.mp4` anywhere else have no kind.
- `drive/<folder path>/<file>` is a Drive picture.
- `chars/<file>` is a Characters picture. It is always at the top level (`hub/core/named.py:32`, `pictures`).

`Files.resolve` (:102-113) refuses the following, always with `Invalid("item", "That image is no longer
available")`:

- a non-string, or a length outside 3..512;
- NUL, a backslash, or a leading `/`;
- fewer than two segments, an unknown root, or an empty, `.` or `..` segment;
- any real path outside the root, or the root itself (this catches symlinks that lead out).

`existing_image` (:115-119) also requires an image kind (`kind(item_id) == "image"`: a suffix from `IMAGE_TYPES`,
`.png .jpg .jpeg .webp`, :24, outside the clips root) and a regular file, so a clip never passes it.
`existing_media` (:121-126) requires any kind (a picture or a clip) and a regular file; `/files` and delete use it.
`kind` (:144-149) is "clip" for an `.mp4` (`CLIP_TYPES`, :25) under `clips/`, "image" for a picture suffix anywhere
else, and `None` otherwise (a picture under `clips/` or an `.mp4` elsewhere). `item_for` (:136-142) maps a
filesystem path back to an id. `url` (:157-159) and `thumb_url` (:160-164) add `?v=<st_mtime_ns>` so a changed file
gets a new URL; `thumb_url` is `None` for a clip.

### 3.2.3 `is_media` and Temp id rules

`hub/modules/media/library.py`:

- `rel_of(item_id, root="out")` (:33-41) returns the path inside a listed root for a valid id of it. It requires
  the prefix `<root>/`, no backslash or NUL, and no empty, `.`, `..` or dot-leading segments. The name must end in
  one of the root's suffixes, `ROOTS` (:24): `.png .jpg .jpeg .webp` for `out`, `.mp4` for `clips`. Otherwise it
  returns `None`.
- `is_clip(item_id)` (:44-45) is `rel_of(item_id, "clips") is not None`.
- `is_media(item_id)` (:48-51) is true for a valid Temp id, a valid clip id, or any string that starts with
  `drive/` or `chars/`. Drive and Characters ids are checked fully later, by `Files.resolve`.
- `group_of(item_id)` (:54-58) returns the folders between the day and the file of a Temp or clips id, joined with
  `/`, or `""`. For Temp that is the group (Favorites); a clip that lands has none, and only a clip in a
  folder under its day gives a name.

Because `is_media` accepts `chars/` ids, `/api/media/move` and `/api/media/delete` accept Characters ids too.
The error text still says "Only Temp and Drive images" (`routes.py:42`). See 3.4.7.

### 3.2.4 Temp layout and naming

`hub/core/files.py:35-47` (`temp_path(root, suffix)`) names a new Temp file, and a new clip in the clips root
the same way. The folder is `<root>/<YYYY-MM-DD>` in local time (`temp_path` takes no folder argument). It is created if
missing. The stem is `<HHMMSS>-<mmm>` (milliseconds). Collisions take `-2` … `-999`
before the suffix. The suffix is lower-cased. The docstring says "The name is the time, nothing else."

A Temp group is any folder between the day folder and the file. `library.ids(root, name)` (:61-71) walks the whole of
one listed root (`outputs`, or the clips). It skips dot-folders, dot-files and symlinks, and returns every id whose
suffix belongs to the root, sorted by id string, descending ("newest first"). The sort is lexicographic on the full id. Within one day, a group subfolder whose
name sorts after the digits (for example `Favorites`) therefore comes before the time-named files. The test
`tests/engine/test_media.py:87` asserts the order `out/2026-10-09/Favorites/…` before
`out/2026-10-09/080000-500_d.png`.

At start, `forget_older_records` (`files.py:50-63`) erases files an older Hub kept (`OLDER_RECORDS`: `inputs`,
`cache`, `media/favorites.json`, `loras/covers`, `loras/thumbs`, `core/learned.json`,
`generate-image/prompts.json`). It also erases any dot-file under `outputs` and under `clips`, which would be an
upload or a clip left half taken in (`files.py:61-63`).

### 3.2.5 How an engine file lands: `enginecat.land` / `sweep`

`hub/core/engine.py:155-182` (`_task`) handles worker events. On `ev == "output"` (:168-171) it runs
`enginecat.land(msg["file"], self.outbox, self.outputs, self.clips)` in a thread and emits `output` with
`{task, item, kind, w, h}`, plus `seconds` for a clip (the dict `land` returns, with `id` renamed `item`). On
`task_done` (:175-182) it runs `enginecat.sweep(self.outbox)`. The outbox is `<state>/outbox` (`engine.py:45`).
Outputs is `<data>/outputs` and the clips folder `<data>/clips` (`engine.py:44`). A plan names no folder to land in,
so a continued clip lands flat like any other.

`hub/core/enginecat.py:119-159` (`land`) first checks the file, then takes a road by suffix:

1. It resolves `src` by `realpath`. It raises `EngineFailed("runtime", "The engine wrote an image outside its
   outbox")` unless the file sits directly in the outbox and is a regular file (:126-128).
2. A clip (`CLIP_TYPES`, an `.mp4`; :130-142):
   - It runs `clip.strip(path)` (the MP4's tags are cut, 3.2.9) and `clip.facts(path)` (its size and length are read
     from its boxes). If either raises `OSError`/`ValueError`, it unlinks the file and raises
     `EngineFailed("runtime", "The engine wrote a clip the hub could not read")`.
   - It picks `dest = temp_path(root, ".mp4")`, where `root` is the `clips` argument, else `<data>/clips` beside
     `outputs`: the clip lands in its day folder.
   - It links or copies the file there (`link_or_copy`) and unlinks the outbox file.
   - It returns `{id: "clips/<rel>", kind: "clip", w, h, seconds}`, where `w`, `h` and `seconds` come from the
     file's boxes.
3. Any other suffix that is not a picture: the file is unlinked and the job fails with `EngineFailed("runtime", "The
   engine wrote a file the hub does not take")` (:143-145).
4. A picture (`IMAGE_TYPES`; :146-159):
   - It runs `clean.strip(path)`. If that raises `OSError`/`ValueError`, it unlinks the file and raises
     `EngineFailed("runtime", "The engine wrote a picture the hub could not read")`.
   - It picks `dest = temp_path(outputs, path.suffix)`, then `link_or_copy(path, dest)` (:82-94). That is a hard
     link, or on `EXDEV` (another filesystem) a copy to a dot-temp then a link. It never replaces an existing file.
     It unlinks the outbox file.
   - It reads the size with Pillow and returns `{id: "out/<rel>", kind: "image", w, h}`, with `w`/`h` `None` if
     unreadable.

`land` returns `kind` in every case, so the core never guesses it from the id: `Dispatcher._ev_output` calls
`files.kind(item)` itself (3.6.2). `sweep` (:97-103) deletes every non-symlink file and folder left in the outbox,
such as a sidecar or a half-written file. `tests/engine/test_continue_land.py` pins the flat landing: a continued clip lands in its day
folder as `clips/<day>/<time>.mp4` and the source never moves.

The core dispatcher then publishes the item on the `media` lane. See 3.6.2.

### 3.2.6 `clean.strip`: exactly what is cut

`hub/core/clean.py` is applied where a file becomes a Temp picture (`land`, `take_in`) and when a picture is
copied in as a character (`characters.put`). `strip(path)` (:27-39) works like this:

- If the file "leans" (`_leans`, :42-48: EXIF orientation tag 0x0112 present and not 1), it is rewritten from
  pixels (`_rewrite`).
- Otherwise it is cut losslessly (`_cut`, :69-76) by format, detected from magic bytes. If the cut returns
  `None` (unparsable or unknown format), the file is rewritten.
- If the output equals the input, nothing is written. Otherwise it writes `.<name>.clean` and `os.replace`s it.

Per format:

| Format | Kept | Cut |
|---|---|---|
| PNG (`_png`, :79-92) | chunks in `PNG_KEEP` (:20-21): `IHDR PLTE IDAT IEND tRNS gAMA cHRM sRGB iCCP sBIT bKGD pHYs acTL fcTL fdAT` | every other chunk (`tEXt`, `zTXt`, `iTXt`, `eXIf`, `tIME`, private chunks) and anything after `IEND` |
| JPEG (`_jpeg`, :107-140) | SOI; non-APP segments; APP0 (JFIF), APP2 only when it starts `ICC_PROFILE\0`, APP14 (Adobe) (`JPEG_KEEP_APP`, :22); every SOS scan with its entropy data (`_scan_end`, :95-104); standalone markers RST/SOI/TEM; EOI | all other APPn (APP1 EXIF/XMP, etc.), APP2 that is not ICC, COM (0xFE) anywhere including between scans, and every byte after EOI (a trailer or second picture) |
| WebP (`_webp`, :143-161) | every chunk except those in `WEBP_DROP` | `EXIF` and `XMP ` chunks; the VP8X flags byte has its EXIF and XMP bits (0x0C) cleared; RIFF size recomputed |

`_rewrite` (:51-66) opens the picture and applies `ImageOps.exif_transpose`. It saves in its own format
(`FORMATS`, PNG for anything else), keeping only `icc_profile`. JPEG is saved at `quality=95, subsampling=0`.
WebP is saved `lossless=True`.

### 3.2.7 Uploads and `take_in`

`hub/core/fileroutes.py:76-91` (`upload`) handles an upload:

1. The guard accepts only `image/png`, `image/jpeg`, `image/webp` bodies (`hub/core/guard.py:38-39`,
   `body="image"`). The size limit is 25 MB (`MAX_UPLOAD`, :25).
2. The body streams into `tempfile.mkstemp(dir=outputs, prefix=".up-")`, a dot-file inside Temp. An empty body
   is refused.
3. `check_image` (:38-55) runs in an executor. The magic bytes must match the content type (`magic_ok`,
   :30-35). The Pillow format must match. The picture must be at most `MAX_PIXELS` = 64,000,000
   (`hub/core/thumbs.py:17`). `im.verify()` must pass. A decompression bomb is refused.
4. `files.take_in(tmp, ext)` (`files.py:166-175`) runs `clean.strip`, then `os.replace`s the file to a
   `temp_path`. It returns `out/<rel>`.
5. The `finally` block unlinks the temp file if it is still there.

`tests/core/test_files.py:137` pins the HTTP statuses: 400 for a mismatched type, a GIF body, an empty body or
a bomb; 415 for `text/plain` or `image/gif`; 413 over 25 MB.

### 3.2.8 Thumbnails

`hub/core/thumbs.py` keeps thumbnails in memory only. `ThumbStore` is an LRU of WebP bytes capped at
`CAP_MB = 256`. `render` (:65-85) refuses pictures over 64 MP, applies `exif_transpose`, converts to RGB/RGBA,
and saves WebP quality 80. `Files.thumbnail` (`files.py:269`) refuses a clip first ("A clip has no thumbnail"),
then allows only `THUMB_SIZES = (96, 336, 1024)`. The Hub makes no thumbnail of a clip; a clip tile draws the
clip's first frame in the browser (3.7.5).
It keys the store by `"<path>|<mtime_ns>|<size>"`. `_drop_thumbs(src)` (`files.py:177-178`) forgets every key
with prefix `"<path>|"`. Every delete, move, regroup and character operation calls it.

### 3.2.9 The clips root and `clip.py`

A clip is the MP4 an engine writes for a video model. It has its own root so that a picture list never shows one.

- **Root.** `clips` is a fixed folder `<data>/clips` (3.2.1). Ids are `clips/<day>/<time>.mp4`. Names are
  the time, like Temp's (`temp_path`, 3.2.4). `Files.kind` says "clip" for such an id and `None` for a picture under
  it. `forget_older_records` clears half-taken dot-files there too.
- **No groups.** Clips are flat by day, newest first, listed through the same function as Temp (no
  separation of clips into groups). Continue makes a new clip beside its source and moves nothing; it was once filed into a
  group folder named by the first clip's stem, and that code (`JobPlan.land_in`, `enginecat.group_folder`,
  `temp.regroup` for clips) is gone. Folders earlier continues made stay on disk and are listed as they were. The core
  keeps no record of a chain. The order a film plays in is the sequence's job (Stage 11, part 8), not a folder's.
- **What the core does with a clip.** `existing_media` accepts it (so `/files` serves it and `delete` erases it);
  `existing_image` does not (so `/api/media/check`, `/thumbs`, the Drive, Characters and the reference boxes can never
  take one). `Files.delete` takes clips (`files.py:180-191`) and `regroup` takes Temp (`out`) ids only
  (`Files.regroup` :213 calls `temp.regroup`, `hub/core/temp.py:28-51`; `Files.file_clip` :216 calls
  `temp.file_clip`, `:61-78`, which can file a clip in a named folder under its day; only the storyboard skeleton
  calls it, and the storyboard stage, when built, removes that call). `Files.move` refuses any
  clip with "Clips stay in the clips folder for now" (:193-198).
  The refusal text for a missing clip is `GONE`, "That image is no longer available" (`files.py:29`).
- **Serving.** `GET /files/clips/...` is `video/mp4`, `no-store`, and answers `Range` (206, 416), so the browser can
  seek (3.1.1). The MP4s carry no fast-start index, so the browser reads the file's end before it plays.
- **Tags cut at landing — `hub/core/clip.py`.** `clip.strip(path)` (:40-46, `_strip` :126-152) rewrites the MP4
  without what the muxer wrote about the file: every `udta` box (at the top level and inside `moov`, its tracks and
  their media boxes) and any `meta` box directly under `moov` (encoder tags, `©too`, `©cmt`, iTunes-style `ilst`
  items). The file is walked as ISO-BMFF boxes and never decoded (`_head` :153-171, `_top` :172-187); parent sizes are
  rebuilt, 64-bit box headers keep their form and the top-level boxes keep their order. Only `moov` is read into
  memory (cap `MOOV_CAP`, 256 MB, :27); `mdat` is streamed in 1 MB blocks (`_copy`, :254-264). When a box ahead of the
  media data shrinks or goes, the chunk offsets in `stco`/`co64` follow the data (`_mover` :188-203, `_offsets`
  :230-244). A fragmented file (`moof`, `sidx`...: `FRAGMENTS`, :26) carries offsets the walk does not rewrite, so
  each cut box there becomes a zeroed `free` box of the same size and nothing moves. The new file is written beside
  the old as `.<name>.clean` and `os.replace`d over it; a clip with nothing to cut is not rewritten (`strip` returns
  `False`). A file that does not walk as an MP4 raises `ValueError`.
- **Facts read at landing — `clip.facts(path)`** (:49-68, `_video` :69-91). From the same walk it returns
  `{w, h, fps, frames, seconds, audio}`: the first video track's size (`tkhd`, 16.16 fixed point), its length
  (`mdhd` timescale and duration), its frame count (`stts`, checked against `stsz`) and whether any track is sound
  (`hdlr` `soun`). It also checks that every chunk offset lies inside the media data. A file without a readable video
  track raises `ValueError`. `land` uses `w`, `h` and `seconds` (3.2.5).
- **Tests.** `tests/core/test_clips.py` (root, kinds, urls and no thumbnail, delete and regroup, time names, a clip
  landing without Pillow, a picture still landing in Temp, any other file failing the job, the lane landing a
  clip and failing on a sound file; the tag cut: `test_tags_are_cut_and_offsets_follow_the_data_when_moov_comes_first`,
  `test_offsets_stay_when_moov_comes_after_the_data`, `test_a_fragmented_clip_keeps_every_byte_in_place`,
  `test_an_untagged_clip_is_not_rewritten`, `test_a_file_that_is_not_an_mp4_is_refused`,
  `test_a_tagged_clip_lands_without_its_tags`), `tests/core/test_clips_facts.py` (facts from the boxes, following the
  file, surviving the cut, a landed clip reporting size and length, an unreadable clip refused, the generation item
  carrying size and seconds), `tests/core/test_clips_http.py`. The MP4s are synthetic (`tests/fakes/mp4.py`).

---

## 3.3 Temp: listing, groups, favorites

### 3.3.1 Paging

`library.page(ctx, before, limit, root="out")` (`library.py:106-122`). `root` is `out` (the Temp) or `clips`; the
route passes `?root=` (`routes.py:61-70`). Everything below holds for either root, except where it says Temp:

- It computes `every = ids(ctx.files.roots[root], root)` on every call, walking the whole tree of that root.
- It iterates ids `< before` (string comparison), calls `describe`, and stops after `limit` readable items.
- `more` is true if any id remains after that point.
- `total` is `len(every)`.
- `groups` is a `Counter` of `group_of` over `every`, with `Favorites` always present (count 0 if empty) for the
  Temp only. It excludes `""` and is sorted case-insensitively.

`describe(ctx, id)` (:87-103) returns `None` if the file is gone or unreadable. Otherwise it returns exactly:
`id, kind:"image", url, thumb:"/thumbs/<id>/336?v=<mtime_ns>", w, h, createdAt (mtime), group, fav`.
`fav` is true when `group_of(id) == "Favorites"`. `tests/engine/test_media.py:75` asserts this exact key set.

For a clip id `describe` returns `describe_clip` (`library.py:74-81`): `id, kind:"clip", url, thumb:None, w:None,
h:None, createdAt (mtime), group, fav:False`. The file is not opened, so a listed clip has no size; the page that
shows it takes the size from the file in the browser (3.7.11). A clip that arrives live carries `w`, `h` and `seconds`
(3.6.2). The item's `group` for a clip is `group_of` (`""` for every clip that lands flat in its day);
the window derives its own group string from the id (3.7.1).

### 3.3.2 Favorites as a group folder

A favorite is a Temp file moved into `<day>/Favorites/` (`library.py:1-8`, `FAVORITES = "Favorites"` at :26).

`routes.favorite` (:72-94) works like this:

- It requires `on` to be a bool. Every id must be a Temp id (`rel_of`). Otherwise it raises
  `Invalid("ids", "Only Temp images can be favorites")`.
- It calls `ctx.files.regroup(ids, "Favorites" if on else "")`.

`Files.regroup` (`files.py:213`) calls `temp.regroup` (`hub/core/temp.py:28-52`), which works like this:

- It skips non-`out/` ids, ids with fewer than three segments, and missing files.
- The destination is `outputs/<day>/<group>` (or `outputs/<day>` for `""`). The day is the id's second segment.
- It skips files already in the destination. On a name clash it takes `drive.free_name` (`name (2)`, …).
- It drops thumbnails and runs `shutil.move`.
- When moving back to the day (`group == ""`), it removes the source folder if it is now empty.
- It returns `(old id, new id)` pairs.

No list of favorite pictures exists anywhere. `tests/engine/test_media.py:87` asserts that no
`favorites.json` is present.

---

## 3.4 Characters

### 3.4.1 Model

`hub/core/characters.py:1-16` defines a character as one picture file at the top of the Characters folder.
Its name is the file stem (`Character 1.png` is "Character 1"). The module keeps the listing and the policy; putting a
picture in, renaming it and writing its text are `hub/core/named.py`, shared with the other folders of named pictures
(part 1).

- `named.pictures(folder)` (`named.py:32-40`) lists top-level, non-dot image files, sorted by `st_mtime`, newest first.
- `listing(files)` (`characters.py:38-46`) keeps the first file seen per `stem.casefold()`, so the newest file wins a
  shared name. It returns `[{name, id:"chars/<file>", notes}]` sorted by `name.casefold()`, or `[]` when no folder is
  set.
- `find(files, name)` (`characters.py:49-52`) matches `name.strip().casefold()` against listed names. It is
  case-insensitive.

`Files.characters/character/character_put/_rename/_remove/_notes` (`files.py:223-251`) delegate to this module, and
`character_put` is `Files.put_picture("chars", …)` (`files.py:229-235`).

### 3.4.2 Put

`characters.put(files, name, item_id)` (`characters.py:55-58`) is `named.put(files, "chars", name, item_id)`
(`named.py:139-165`). It makes a picture the character called `name`:

- The name is checked by `drive.name_ok`: one segment, 1..120 chars, no `/`, `\`, NUL, or leading `.`.
- The source may be any existing image: Temp, Drive or Characters.
- The destination is `<folder>/<name><src suffix lowercased>`.
- If the source already is that character (same folder, same stem casefolded), it returns its id unchanged.
- Otherwise it copies to `.<name>.hub-new` and runs `clean.strip` on the copy. A failure unlinks the copy and
  raises "That image could not be read".
- It reads the text (the notes) of the newest file already holding the name, when the folder may hold text
  (`named.text_allowed`).
- It drops thumbnails for every file of that name and unlinks those not equal to `dest`.
- It `os.replace`s the copy into place.
- If there was text, it rewrites the file with it (`named.write_text`), which turns it into a PNG.

The source picture stays where it was. The character is a copy.

### 3.4.3 Rename and remove

`characters.rename(files, item_id, name)` (`characters.py:72-76`) checks `_own` (`:61-69`: an id `chars/<file>` with no
further `/`, and the file must be in the folder now) and calls `named.rename(files, item_id, name, TAKEN)`
(`named.py:168-182`):

- A name held by another file is refused: `A character is already called <name>`.
- It `os.rename`s to `<new><same suffix>`, then unlinks any other file still holding the old stem. A change of
  case only keeps the renamed file.

`characters.remove(files, item_id)` (`characters.py:79-85`) erases every file with that stem and returns the stem.
Nothing goes to a trash.

### 3.4.4 Notes: the one metadata exception

The module docstring (`characters.py:9-15`) states the exception. A character may carry the notes as one PNG
text field, `Description` (`NOTES_KEY = pngtext.KEY`, `characters.py:29`), inside its own file. The file work is
`hub/core/pngtext.py`, the only writer of picture text (`tests/core/test_pngtext.py`), reached through `named`:

- `notes_of` (`characters.py:30`) is `pngtext.read` (`pngtext.py:19-28`): `""` for a non-PNG file or one that cannot
  be read, otherwise `im.info["Description"]` when it is a string.
- `named.write_text(files, folder, src, text)` (`named.py:112-124`) calls `pngtext.write` (`pngtext.py:31-52`), which
  re-saves the picture as `<stem>.png`, pixel for pixel. It keeps `icc_profile` and `transparency`, and converts
  unusual modes to RGB/RGBA. It writes `text` as an iTXt `Description` (none if empty) via a `.<stem>.hub-text` temp
  file. A JPEG or WebP source is unlinked afterwards, and so is any older file of the same stem.
- `characters.set_notes(files, item_id, text)` (`characters.py:88-97`) requires a string without NUL. It strips the text
  and caps it at `MAX_NOTES = 1000` (the core's own ceiling is `pngtext.MAX` = 16,384). It calls `named.write_text` and
  returns the (possibly new `.png`) id.
- `named.text_allowed` (`named.py:79-99`) says which pictures may hold text: `chars/<file>` at the top of Characters,
  and, once the storyboards folder is set, `drive/<storyboards>/<name>/<file>` exactly one level under it. Only the
  first is used by this screen.

The notes belong to the name. A rename keeps the file, so it keeps the notes. `put` under an existing name carries the
notes over (`named.py:157,163-164`). A picture put under a new name starts without notes, because `clean.strip` cut
every PNG text chunk. `tests/core/test_character_notes.py` pins each of these rules.

### 3.4.5 Routes

| Route | Behaviour |
|---|---|
| `GET /api/media/characters` | `{unset:true, items:[]}` when `"chars"` is not in `ctx.files.roots`. Otherwise each listed character goes through `library.describe` plus `name` and `notes`, and unreadable ones are skipped (`routes.py:151-162`). |
| `POST /api/media/characters` | `{name, id}`. The `id` must pass `is_media` (Temp, Drive or Characters). Calls `character_put` (`routes.py:165-175`). |
| `POST /api/media/characters/rename` | `{id, name}` to `{id}` (:178-183) |
| `POST /api/media/characters/remove` | `{id}` to `{name}` (:186-191) |
| `POST /api/media/characters/notes` | `{id, notes}` to `{id}`. `""` clears the notes (:194-199). |

Each POST publishes `media.changed` with `what: "characters"`.

### 3.4.6 What the assistant and Generate read

- The MCP listing `characters` (`hub/modules/generate_image/tools.py:84-91`, `list_characters`) returns
  `{"characters": cast.listing(ctx)}`. `cast.listing` (`hub/modules/generate_image/cast.py:115-117`) gives
  `{name}` plus `notes` only when non-empty. The assistant sees names and notes, never pictures or ids.
- `cast.resolve` (`cast.py:74-112`) turns reference names into pictures with `ctx.files.character(name)`, a
  case-insensitive lookup. It raises `No character "<name>"; list_characters names them`. A box that holds a character
  sends its name to the engine as an identity's `character_name` (`cast.character_name`, `cast.py:45-48`), and it may
  carry a cut-out flag (part 2, 2.10.3, 2.10.5).
- `GET /api/generate-image/characters` (`hub/modules/generate_image/routes.py:217-230`, `get_characters`)
  serves the prompt box's Tab completion: name, id, w, h and thumb. Its docstring says "Never the notes."

### 3.4.7 Characters through the generic routes

`library.is_media` accepts `chars/` ids (3.2.3), so:

- the Media window's Delete (`Media.tsx:99-107` to `media.erase` to `POST /api/media/delete`) can erase a
  character's file through `Files.delete`. That deletes only the one file, unlike `characters.remove`, which
  erases every file of the stem;
- `POST /api/media/move` with a `chars/` id moves the file into the Drive (`Files.move`, `files.py:193-211`);
- `POST /api/media/favorite` with a `chars/` id is refused (`rel_of` is `None`).

This is how the code behaves. No test asserts the Delete-on-a-character path.

---

## 3.5 Drive and favorite folders

### 3.5.1 Drive operations

`hub/core/drive.py`. A folder path is relative posix with `""` as the root. `_rel` (:25-31) refuses a
backslash, NUL, a path over 2048 chars, and `.`, `..` or dot-leading segments. `folder` (:52-61) resolves the
real path, refuses anything outside the root, and by default requires that the folder exists. `root` (:45-49)
raises `NO_DRIVE` ("Choose the Drive folder in Settings → Storage") when there is no Drive.

| Function | Behaviour |
|---|---|
| `listing(files, path)` (:75-90) | `{path,name,dirs,ids}`. Non-dot subfolders and image files, each sorted case-insensitively. Returns `{…, unset:True}` with empty lists when there is no Drive. |
| `make(files, path, name)` (:93-100) | `mkdir` of `name_ok(name)`. Refuses an existing name. |
| `rename(files, path, name)` (:103-111) | Refuses the root and an existing sibling name. |
| `move(files, paths, to)` (:114-132) | 1..100 folders. Refuses the root, and a move into itself or a descendant. A folder already in `to` is a no-op. A name clash is refused. |
| `remove(files, path)` (:135-143) | Refuses the root. Drops thumbnails of every file inside, then `shutil.rmtree`. |
| `free_name(folder, name)` (:64-72) | `name`, `name (2)`, `name (3)` … |

`Files.move(ids, to)` (`files.py:193-211`) moves Temp or Drive files into a Drive folder. It skips missing
files and files already in place, and returns `(old, "drive/<rel>")` pairs. `Files.delete(ids)` (`files.py:180-191`)
unlinks each existing picture or clip and drops its thumbnails. There is no trash.

`routes.drive_list` (`routes.py:105-113`) maps each id through `library.describe` and drops `None`.

### 3.5.2 Favorite folders: a list of paths

`hub/modules/media/favorites.py`. A favorite folder is a Drive folder pinned under Favorites in the tree.
Nothing is moved, copied or linked (:1-7). The record is the JSON doc `favorite-folders`
(`{"version":1,"folders":[]}`, :15-16), stored at `<data>/media/favorite-folders.json`
(`hub/core/context.py:104-107`; asserted by `tests/engine/test_media_drive.py:146`).

| Function | Behaviour |
|---|---|
| `paths(ctx)` (:25-27) | The saved list, keeping non-empty strings. |
| `clean(body)` (:44-50) | Validates `on` (bool) and `path` (str), and normalises the path (drops empty segments). |
| `check(files, path)` (:30-36) | The folder's path as `folder_list` returns it, or `None` (not there, or no Drive). |
| `refuse(files, path)` (:61-65) | `NO_DRIVE`, "The Drive itself is always in the tree" (for `""`), or `NOT_THERE`. |
| `pin(ctx, path, on)` (:53-58) | Removes then appends the path (once, at the end), or removes it. |
| `renamed(ctx, old, new)` (:72-78) | Entries at or under `old` are rewritten to `new…`, then deduplicated. |
| `removed(ctx, folder)` (:81-84) | Entries at or under `folder` are dropped. |
| `describe(files, listed)` (:39-41) | `[{path, name (last segment), ok}]`. `ok` is whether the folder exists now. |

Wiring in `routes.py`:

- `drive_rename` calls `favorites.renamed` (:126).
- `drive_move` calls `renamed` for each `(old, new)` pair (:135-136).
- `drive_remove` calls `favorites.removed` (:145).

A folder renamed or removed outside the Hub stays listed with `ok:false` until it is unpinned.
`tests/engine/test_media_drive.py:106` asserts that.

---

## 3.6 Live updates

### 3.6.1 `media.changed`

Every mutating Media route calls `_changed` (`routes.py:23`). That becomes lane and type `media.changed`
through `ModuleBus` (`hub/core/context.py:54-65`). `hub/core/runtime.py:124` registers each module lane with
the roles `("workspace", *mod.screens)`, which is `("workspace", "media")` here. `Bus.default_lanes`
(`hub/core/bus.py:104-105`) subscribes those roles by default.

On the web, `Media.tsx:69` runs `useBusEvent('media.changed', () => refresh())`. `media.ts:184-187` (`refresh`)
re-fetches five things: the Temp first page, the clips first page, the favorite folders, the characters, and every
Drive folder already in the `drive` store. A folder that fails to load is removed from the store. `Media.tsx:59-60`
also calls `refresh()` on every (re)connect (`connects` store). Nothing polls (`media.ts:1-5`).

### 3.6.2 `generation` on the core `media` lane

`hub/core/dispatch.py:173-185` (`_ev_output`) takes `kind = files.kind(item)` (an output whose id has no kind is
dropped) and publishes
`bus.publish("media", "generation", {"item": {id, kind, url, thumb, w, h, created, job}})` for each landed output.
For a picture `kind` is "image" and `thumb` its URL. For a clip `kind` is "clip", `thumb` is `None` (`Files.thumb_url`),
`w`/`h` are the size read at landing and the item carries `seconds` (`dispatch.py:179-183`). `"media"` is a core lane (`hub/core/messages.py:17`). It is a default lane for role `media`,
not for `workspace` (`messages.py:18-22`).

`Media.tsx:61-68` handles it, on both pages of the window alike:

- `fromGeneration` (`media.ts:84-88`) builds a `MediaItem`; the group string comes from the id
  (`fromGeneration`): `""` for a clip that lands flat in its day.
- `prepend` (`media.ts:126-133`) puts the item first in the store of its kind (`clips` for a clip, `temp` for a picture),
  bumps `total`, and for a picture adds a missing group to the Temp's groups and bumps its count.
- If the view shows the item (`shows`, `Media.tsx:34-35`: a picture in the Temp or its group, a clip in the Clips view
  that holds it, `inClips`), `selection.follow` makes the new item the single selection and the Stage image, unless
  2+ items are selected. Otherwise a toast says "New clip" or "New generation".

The Web type is `GenerationItem` (`web/src/lib/protocol.ts:56-59`; its `kind` is `'image' | 'clip'`, `thumb`, `w` and `h`
may be null, and it does not type `seconds`).

### 3.6.3 What Media never does

These follow from the code and are stated in the module docstrings:

- **No trash.** `Files.delete`, `drive.remove` and `characters.remove` unlink at once (`files.py:172-183`,
  `drive.py:135-143`, `characters.py:79-85`; `routes.py:5-6`). `tests/engine/test_media_drive.py:86` and
  `tests/core/test_files.py:64` pin this.
- **No metadata.** Engine outputs, uploads and character copies are stripped (`clean.py`). `describe` reads
  only size and mtime (`library.py:84-100`). Thumbnails are memory-only (`thumbs.py:1-4`). The only exception is
  a character's `Description` notes (3.4.4).
- **No side records.** The only file the module writes is `favorite-folders.json`, which holds paths.
  `forget_older_records` erases what an older Hub kept (`files.py:49-63`). Pictures and thumbnails are served
  `cache-control: no-store` (`fileroutes.py:65,72`).
- **No logs.** None of the media server files calls a logger. Grep `hub/modules/media`, `files.py`,
  `drive.py`, `characters.py`, `clean.py`, `thumbs.py` and `fileroutes.py` for `logging`/`log.`: none. On the
  web, `main.tsx:32-34` sends page errors to a toast and never to the console.

---

## 3.7 The Media window (web)

`web/src/main.tsx:16-18` maps `/media` and `/clips` to role `media` and lazy-loads `screens/media/Media.tsx` for both.
It is one window: `/clips` is the same screen opened on its Clips section (`startView`, `media.ts:35`: the path `/clips`
gives the `CLIPS` view, any other path `TEMP`). The server serves the same shell for both (3.7.11).

### 3.7.1 Stores and views (`media.ts`)

| Store | Shape |
|---|---|
| `temp` | `{items, more, ready, total, groups}` (`media.ts:29`) |
| `clips` | the same shape, for the clips root (`:30`) |
| `drive` | `Record<path, Folder>` of loaded Drive folders (`:31`) |
| `favFolders` | `FavFolder[]` (`:32`) |
| `characters` | `{unset, items: Character[]}`, starting `unset:true` (`:33`) |
| `view` | `View` = `{kind:'temp', group}` \| `{kind:'clips'}` \| `{kind:'drive', path}` \| `{kind:'chars', focus}`, default `startView(pathname)` (`:16`, `:36`) |
| `naming` | `{id, value} \| null`: a picture waiting for a character name (`:38`) |

`itemsOf(view)` (`:91-97`) gives the items a view shows:

- drive: that folder's items;
- chars: all characters;
- clips: every loaded clip, one flat list newest first, as the server lists it;
- temp: the loaded Temp items, filtered by group when one is set (a Temp group view shows only the pages already loaded).

The page size is `PAGE = 200` (`:23`). `loadMore(root)` (`:109-123`) fetches `before=<last id>` for `out` or `clips` (the
query adds `root=clips` for the clips, `:45`). `loadRoot` (`:99-102`) reads a first page; `loadClips` (`:105`) is the
clips' refetch that Continue and a landing clip use. Mutations are:

- `erase` (`:197-202`), which drops ids from every store and lowers the `total` of the root each id belongs to;
- `favorite` (`:206-210`), which reloads Temp and returns the new ids;
- `moveTo` (`:213-218`);
- `folderNew/Rename/Move/Remove` (`:220-223`);
- `putCharacter`, `renameCharacter`, `saveCharacterNotes`, `removeCharacter` (`:158-181`), each reloading the
  characters.

A clip has no day rows and no group rows: `norm` (`:49-52`) keeps its kind, `thumb: null` and a size of 0 when unknown.
`CLIPS` (`:29`) is the one clips view; the window loops a clip on the Stage when `looping` is on.

### 3.7.2 Layout (`Media.tsx`)

`Media.tsx:160-180` renders a `Frame` with:

- `stageBox`: the `Stage` for the current item, keyed by its URL so each picture starts at Fit; for a clip item
  (`current.kind === 'clip'`) it is `Clip` instead (3.7.11);
- `side`, holding three things:
  - the tree column (`data-region="tree-col"`, `inert` when shut): `Tree`, the same on every view;
  - the grid box (`data-region="thumbs-box"`, `inert` when the thumbnails are down): the `Grid`, labelled "Clips" in
    the Clips view and "Images" otherwise;
  - the `Bar`;
- one context `Menu` labelled "Image" ("Clip" in the Clips view).

There are two flags. `open` is the tree; `thumbs` is the thumbnails. `toggleTree` and `toggleThumbs`
(`:88-91`) keep these rules:

- the tree never shows without the thumbnails;
- folding the thumbnails folds both;
- whatever opens comes up on Temp (`setView(TEMP)`).

`setView` (`:85`) clears the selection when the view changes. The empty-grid text depends on the view (`empty`, `:31`);
in the Clips view it is "No clips yet.". The grid pages the Temp or the clips, whichever the view shows (`more`,
`:157`); the Drive and Characters views are not paged.

### 3.7.3 Stage (`Stage.tsx`)

- **Fit** (:29-37): `sc = min(W/w, H/h)` over the board's client size. The picture is centred:
  `x = (W - w·sc)/2`, `y = (H - h·sc)/2`. A `ResizeObserver` re-fits only while `fitted` (:39-45).
- **Zoom** (:52-61): at the cursor, clamped to `[0.5·fit, 32]`. Landing within 1e-4 of fit snaps back to Fit.
  The wheel factor is `exp(-deltaY·0.0015)` (:63-73). Both plain wheel and Ctrl+wheel zoom.
- **Keys** (:74-86): Ctrl/Cmd+0 fits. Ctrl/Cmd+1 sets 100% at the centre. Space is `preventDefault`ed while
  over the board or dragging.
- **Pan** (:97-115): a primary or middle press captures the pointer and drags. Panning sets `fitted:false`.
- **Double-click** (:116-121): toggles Fit and 100% at the cursor. It is ignored inside an edge zone.
- **Look**: `image-rendering: pixelated` at scale ≥ 2. A zoom label (`Fit` or `NN%`) flashes for 900 ms (:47-51).
- **Edge zones** (:88-96, :109-115) exist only when `edges` is passed. Media passes it only while the thumbnails
  are folded (`Media.tsx:164-165`).
  - `edges.at()` returns the left edge of the bar's `[data-region="count"]` element (`Media.tsx:84`).
  - The right zone runs from that x to the board's right edge. The left zone is the same width from the board's
    left edge.
  - A primary press that starts and ends in the same zone calls `edges.step(±1)`, the same as the bar's
    previous and next.
  - `web/tests/e2e/media-edges.spec.ts` pins these rules.

### 3.7.4 Tree (`Tree.tsx`, `Characters.tsx`)

The rows, in order (`Tree.tsx:145-170`):

1. **Library** label, then the **Temp** row (count = `total`, a dot that dims when empty). When open, one row per
   group except Favorites (`:147-150`). A click shows the group's view.
2. **Favorites** row (count from the `Favorites` group) (`:152-155`). Clicking it shows the Favorites group view.
   Dropping media on it calls `favorite(ids, true)`. When open it lists the favorite folders (`:156`):
   - `favRows` (`:130-137`) for `ok` folders: expandable into subfolders, with the star menu only. They take no
     drops, no drags and no folder operations.
   - `goneRow` (`:138-141`) for missing ones: dimmed, and a click toasts "That folder is not in the Drive now".
     Its only menu item is "Remove from Favorites".
3. **Characters** section (`Characters.tsx`, mounted at `Tree.tsx:158`):
   - The heading row (view `{kind:'chars', focus:''}`) accepts a media drop, which sets `naming` and asks for a
     name.
   - The name input (shown while `naming` is set) handles keys: Enter or blur commits, Escape cancels
     (:89-93). The commit toasts "added" or "replaced", matching names case-insensitively (:34-41).
   - One row per character: a click focuses it (`{kind:'chars', focus:id}`). A drop on it replaces that
     character's picture (:107). A title holds the notes, and a dot marks a character with notes.
   - Right-click opens a menu: "Notes…", "Rename", "Delete character" (:67-75). The notes box is a textarea,
     `maxLength=1000`, saved by Ctrl/Cmd+Enter or blur, cancelled by Escape. Unchanged notes (after trim) send
     nothing (:53-62).
   - With no folder set, a paragraph points to Settings → Storage → Characters, and the heading takes no drops.
4. **Clips** section, between Characters and the Drive (`:160-163`). It is always open, with no fold and no drops:
   - The **Clips** row (id `clips`; count = the clips store's `total`, a dot that dims when empty) shows every clip
     of every day in one list, newest first (`{kind:'clips'}`); a new clip lands at the top. It has no day rows and no
     scene rows.
   - The active row is the one whose view is the current one (`clipsActive`, `:143`). Clips take no drag: only pictures
     go to Favorites, a Drive folder or a character, and a dragged clip goes into the `MEDIA_DRAG` payload with `kind: 'clip'` and its seconds (3.7.10); only box 1 of Generate (to continue it) and, from Stage 11, the Edit Video strip take it.
5. **Drive** label with a "New folder" `+` button (hidden when unset), then `driveRows('', 0)` (`:115-127`).
   - Each folder row shows its item count, expands when it has subfolders, and runs `pickDrive` on click (shows
     the folder, opens it, and loads it if needed).
   - Each row is draggable (`FOLDER_DRAG`) except the root. It accepts media drops (`moveTo`) and folder drops
     (`folderMove`).
   - The right-click menu (`folderMenu`, `:81-89`) has "Add to Favorites"/"Remove from Favorites" (not on the
     root), "New folder inside", "Rename", and "Delete folder". Rename and delete are not on the root.
   - Inline inputs for new and rename commit on Enter or blur and cancel on Escape (`:109-113`, `:54-67`).
   - With no Drive, a paragraph points to Settings → Storage → Drive (`:167`).

Open state is a `Set` of row ids. The default is `temp`, `fav`, `drive:` (`:32`). Row ids are `temp`,
`temp/<g>`, `fav`, `fav:<pinned>`, `fav:<pinned>><path>`, `clips`,
`drive:<path>`, `chars` and `char:<name>` (`data-row`).

### 3.7.5 Grid (`Grid.tsx`, `gridMath.ts`)

The grid has two square tiles per row (`COLS = 2`, `:21`), with a gap of `0.625rem` (`:38`).

- `geometry` (`gridMath.ts:5-8`): `tile = (width - gap·(cols-1))/cols`, `rowH = tile + gap`.
- `windowRange` (:11-16): renders the visible rows ± 3 rows of overscan.
- `totalHeight` (:18) sizes the canvas.

Behaviour:

- Prepending keeps the first visible row's item in place by adjusting `scrollTop` (`Grid.tsx:47-62`).
- A change of `sel.current` scrolls it into view. A new arrival does not (`:64-73`).
- Scrolling within 4 rows of the bottom calls `more()` when it is set (`:75-80`). `more` is the next-page loader of the
  Temp or Clips view, else null (`Media.tsx:157`).
- Tiles show a dot for Temp ids and a ★ for favorites (`:110-111`). A clip tile is its still (`ui/ClipStill.tsx`,
  `lib/stills.ts`): one hidden player at a time draws the frame at 0.1 s into a JPEG in the window's memory; a
  picture tile is the `<img>` of its thumbnail. The grid keeps its scrollbar's room (`scrollbar-gutter: stable`).
- The grid is a `listbox` with `aria-multiselectable` and `aria-activedescendant`.

### 3.7.6 Bar (`Bar.tsx`)

Left to right (`:47-77`):

1. The tree fold button (`data-region="fold"`) and the thumbnails fold button (`thumbs`).
2. Previous (`prev`), the counter `at / shown` (`count`), and next (`next`). The buttons are disabled at the
   ends. They call `onStep`, which is `selection.move` with ArrowLeft or ArrowRight (`Media.tsx:83`).
3. `<Live>`, the connection light.
4. The launch fold-up (`data-region="launch"`), shown only `insideDesktop()`. Its entries come from
   `launchTargets()` and open in a new window (`:38`).
5. The utilities fold-up (`utilities`): "Clear the GPU cache" (`bus.request('gpu.release')`) and "Seed back to
   random" (`tool.randomSeed`, off when no tool has one) (`:39-46`).
6. **Continue** (`data-region="continue"`, title "Continue this clip"), shown while the Stage shows a clip and a
   registered module has `continueClip` (`onContinue`, `Media.tsx:175`; `Bar.tsx:67-69`). It runs the same action as the
   menu item (3.7.8).
7. Generate (`data-region="generate"`), shown when a registered module has `queue`
   (`tool = modules.find(m => m.queue)`, `:15`). It queues that tool's saved draft and toasts the reason or
   "Queued" (`:27-31`).

Fold-ups open just above the footer (`above`, `:33`).

### 3.7.7 Selection model and keys (`selection.ts`, `Media.tsx`)

`Selection = {ids, anchor, current}` (`selection.ts:2`). `order` is the grid order.

| Function | Behaviour |
|---|---|
| `click` (:6-19) | A plain click selects one. Ctrl/Cmd toggles, keeping grid order. Shift selects the range from the anchor. |
| `selectAll` (:21-22) | Selects every id in `order`. |
| `move` (:25-39) | Arrows step by 1 or by `cols` (2). Home and End jump to the ends. The result is a single selection. |
| `clear` (:42) | Escape: empties `ids` but keeps `current` (the Stage image stays). |
| `targets` (:45-48) | The selection in grid order, else `[current]`. Send, Favorite and Delete act on this. |
| `afterDelete` (:51-57) | The next older item, else the previous one. |
| `follow` (:60-63) | A new generation becomes the single selection unless 2+ are selected. |

The window keydown handler (`Media.tsx:128-142`) handles these keys:

| Key | Action |
|---|---|
| Ctrl/Cmd+A | select all |
| Arrows, Home, End | `move` |
| Enter | `send(targets)` |
| Delete | `remove()`: erase at once and toast "Deleted" / "N deleted" |
| F | `star()`: toggle favorite on all targets (on unless all are already favorites) |
| Escape | `clear` |

The handler ignores typing targets, menus (`[role="menu"]`), and Enter/Space on a button. Other Ctrl, Meta or
Alt combinations are ignored. With a clip among the targets, Enter and F toast one line instead
(`NO_SEND`, `NO_FAV`, `Media.tsx:25-28,135,137`); Delete works on clips.

When the view is `chars` with a `focus`, an effect selects that character (`Media.tsx:71-75`). When `current` leaves
`order`, it falls back to the first item (`:76-81`).

### 3.7.8 Right-click menu (`Media.tsx:144-158`)

A right-click on an unselected tile first selects it (`Grid.tsx:106`). The menu then acts on `targets`. Items,
in order (`menuItems`, `Media.tsx:146-156`):

1. **Send**. The label comes from `useSend`, for example "Add as reference" or "Add N as references". Its key
   is Enter. It is disabled with the `sendState` reason. When exactly one image is chosen and the tool already
   has a filled reference ("Replace …" in the menu), it gains a `sub` list with one entry per reference socket
   ("Put in"/"Replace" `<label>`). Each entry sends to that socket.
2. **Continue**, only when a clip is among the targets (`:149-150`). It is off with "One clip at a time" when more
   than one is chosen and with "Generate Image is not here" when no registered module has `continueClip`
   (`tool = modules.find(m => m.continueClip)`, `:29`). It runs `goOn(id)` for the one chosen clip.
3. **Favorite** or **Remove favorite** (key F). It shows "Remove favorite" when every target is already a
   favorite.
4. **Add to Characters**. It is off when the Characters folder is unset or when not exactly one picture is
   chosen. It opens the tree and thumbnails and sets `naming` (`{id, value:''}`) so the Characters section asks
   for a name.
5. A separator.
6. **Delete** or **Delete N** (key Del, `danger`).

When a clip is among the targets, Send, Favorite and Add to Characters are off, each with its own reason ("Only
pictures can be references", "Only pictures can be favorites", "Only pictures can be characters", `Media.tsx:25-28,
147,151,152`); Delete stays on. The server refuses the same three calls for a clip (3.1.1).

**Continue** (`goOn`, `Media.tsx:108-117`) calls the Generate module's `continueClip(id)` (`web/src/lib/module.ts:14`;
`web/src/modules/generate-image/continue.ts:7`), which posts the id to `POST /api/generate-image/continue` (part 2,
2.10.7). The reply is null when the clip is in box 1 of a model that continues one, else the hub's one-line reason:

- A reason is shown as a toast and nothing changes.
- Otherwise the toast says `Continue: <stem> is in box 1`. The source stays where it is, still selected and on the Stage; nothing moves
 .

The bar's Continue button (3.7.6) calls the same `goOn` with the clip on the Stage.

### 3.7.9 Smart Send (`send.ts`, `useSend.ts`)

`sendState(linkOn, focus, presence, n)` (`send.ts:18-34`) checks these conditions in order. The first that
holds sets the state:

| Condition | State |
|---|---|
| link off | disabled, "Reconnecting…" |
| `n === 0` | disabled, "Select an image" |
| no focused tool | disabled, "No tool is open" |
| workspace offline | disabled, "`<tool>` is offline" |
| no sockets | disabled, "This model takes no images" |
| `primary === 'reference'`, no free reference slot | disabled, "References are full (k of k)", keeping the menu |
| `primary === 'reference'`, a free slot | enabled, "Add as reference" / "Add N as references" / "Add F of N as references", socket `'reference'` |
| otherwise | pick, "Send to `<tool>`…" |

`useSend.send(ids, socket?)` (`useSend.ts:29-39`) sends bus message `send` `{tool, socket, items}` with a fresh
id. It allows one request at a time, waits up to `WAIT_MS = 6000` for a `delivery` whose `re` matches, and
toasts `deliveryText`. The server side is `hub/core/delivery.py` (send, deliver, received, delivery; results are
kept 10 minutes).

### 3.7.10 Drag-and-drop protocol

| MIME type | Set by | Payload | Accepted by |
|---|---|---|---|
| `application/x-hub-media` (`MEDIA_DRAG`, `web/src/lib/protocol.ts:78-79`) | `Grid.onDrag` (`Grid.tsx:81-88`): the whole selection if the dragged tile is selected, else that tile | JSON `DraggedMedia[] = [{id, w, h}]`, pictures only: a clip is left out of it (`Grid.tsx:84`), and the key is not set when no picture is left (`:85`). `text/uri-list` is also set to absolute file URLs, clips included. `effectAllowed = 'copyMove'`. | Tree: Favorites row (favorite), Drive folder rows (move) (`Tree.tsx:49-53`). Characters heading (first id, asks for a name) and a character row (replace) (`Characters.tsx:12-15`). Generate's reference boxes (below). |
| `application/x-hub-folder` (`FOLDER_DRAG`, local constant `Tree.tsx:13`) | Drive folder rows except the root (`Tree.tsx:96`) | the folder's relative path (string) | Drive folder rows: `folderMove([from], path)` unless `from === path` (`Tree.tsx:98-101`, :121) |

**Drop onto Generate's reference boxes.** `web/src/modules/generate-image/run/Slots.tsx:24-34` (`drop`) reads
`MEDIA_DRAG` and calls `addMedia(items, target, model)`. Dropped files call `addFiles` instead. A payload id under
`clips/` is sent to the Continue route instead, but the Grid never puts a clip in the payload (above), so a clip
reaches Continue from the menu or the bar only.

`addMedia` (`web/src/modules/generate-image/inputs.ts:104-125`) works like this:

1. It plans indexes against the model's `refCap` (`dropPlan`).
2. It calls `api.check(ids)`, which is `POST /api/media/check` (`web/src/modules/generate-image/api.ts:26`).
3. It places each confirmed id as `{id, w, h}`. No copy is made: the reference is the media id.

Both empty and filled boxes accept the drop when a model is set (`Slots.tsx:48-49`, :40-41).

### 3.7.11 The Clips section

The clips are a section of the one Media window. The path `/clips` opens that window on its Clips view; the server serves
the same shell as for `/media` (`hub/core/web.py:64`, public like `/` and `/media`; pinned by
`tests/core/test_clips_http.py::test_the_clips_page_is_the_shell`), and `web/src/main.tsx:17-18` maps it to the same
screen. Differences, all keyed on the view:

- **Data** (`media.ts`). The `clips` store holds the clips root's items and its own `total`; `GET /api/media?root=clips`
  fills it (`loadRoot`, `:99-102`) and pages it (`loadMore('clips')`). `refresh` loads the Temp and the clips both
  (`:184-187`), so the Clips section is filled whatever page opened the window. `norm` (`:49-52`) keeps a clip's kind,
  `thumb: null` and a size of 0 when unknown. `erase` lowers the `total`
  of the root each id belongs to (`:200`).
- **Tree** (`Tree.tsx:160-163`, 3.7.4). The Clips row alone, no day or scene rows; it shows every clip newest first.
  The section is always open.
- **Stage** (`Clip.tsx`). A `<video controls preload="metadata" playsInline>` fitted like a picture (`fitBox`,
  `fit.ts`) at its natural size, so its own controls keep their size; while the thumbnails are up it fits left of the
  side column, so no control sits under it (`measure`, `Clip.tsx:22-33`). A clip listed without a size fills the fit
  box until the file reports its own (`onLoadedMetadata`, :71-72). There is no zoom or pan. Space plays or pauses
  while the Stage has focus (`onKey`, :41-48). With the thumbnails folded, `edges` gives the same two edge zones as
  for a picture; a press that steps there is not also the player's click or double-click (:50-70).
- **Grid and bar.** Clip tiles draw the first frame (3.7.5); the grid label is "Clips". The bar, selection and keys are
  the same; Send, Favorite and Add to Characters are off for a clip (3.7.7, 3.7.8), and **Continue** is on the menu and
  the bar (3.7.8).
- **Live.** A clip landing arrives as a `generation` item with `kind: 'clip'`; it is prepended to the clips store, the
  clips are read again, and if the view shows it (`shows`) `follow` makes it the Stage's clip (3.6.2).

There are no scenes in the clips list (3.2.9). This screen moves nothing: no drop, rename or move touches a
clip; the order of a film is a sequence, kept in the Edit Video tab (Stage 11, part 8).

Tests: `web/tests/unit/clips.test.ts` (kind and thumbnails, a clip lands in the clips store only, the root query, the
flat order and a new clip on top, the fit math) and `web/tests/e2e/media-clips.spec.ts` (the Clips section in the tree, tiles
as players, Space, no send/favorite/character and Delete, a new clip landing, edge zones that step and never play);
`web/tests/e2e/video-continue.spec.ts` for Continue (part 2, 2.8).

---

## 3.8 Tests that pin behaviour

### Python (`tests/`)

| File | What it guards |
|---|---|
| `tests/core/test_files.py` | Resolver refuses escapes (:48) and accepts only images (:53). Delete erases the file and thumbnail with no trash (:64). Thumbnails are in-memory WebP (:75). `take_in` names by time and strips metadata (:88). `regroup` stays within the day (:102). `/files` and `/thumbs` over HTTP (:122). Upload checks and statuses (:137). `/api/media/check` confirms without copying (:159). Older records are erased at start (:169). |
| `tests/core/test_clean.py` | Metadata goes and pixels stay, per format (:29). Other formats are rewritten as PNG, and a broken file is refused (:60). JPEG comments between scans and trailers after EOI (:78). An orientation-tagged photo is turned upright (:102). An unparsable file is rewritten from pixels (:117). |
| `tests/core/test_drive.py` | No Drive until chosen (:30). Listing (:40). Make, rename and move folders (:51). Move files in from Temp and between folders (:71). Delete purges files and folders (:83). |
| `tests/core/test_characters.py` | Listing is top-level pictures by name (:54). Newest wins a shared name (:70). Case-insensitive find (:80). Put copies (:88), from the Drive or another character (:98), replaces every holder of the name (:105), changes the extension with the type (:119), is a no-op onto its own name (:126), strips metadata (:134), and refuses bad names or missing pictures (:149). No folder set (:164). `set_characters` leaves the Drive alone (:175). |
| `tests/core/test_characters_edit.py` | Rename keeps the type (:36), allows a case-only change (:46), takes older same-name files with it (:52), and refuses a taken name (:59) or a bad name (:69). Only in-folder characters can be edited (:78). Delete erases every file of the name (:87). Nothing is written outside the folder (:98). No folder (:107). |
| `tests/core/test_character_notes.py` | Notes are saved in the file and listed (:40). A JPEG becomes a PNG pixel for pixel (:52). Empty notes clear the field (:62). Bad notes are refused (:72). Only in-folder characters take notes (:81). Notes stay with the name (:87). A new name starts empty (:99). Older same-name files go (:109). Nothing is written outside (:116). |
| `tests/engine/test_media.py` | Paging newest first (:37). Listing works without the engine (:53). Delete goes through core `Files` and bad bodies are refused (:59). `rel_of` rules (:69). The thumb URL changes with the file, and the item key set is fixed (:75). A favorite is a file in `Favorites/`, with no favorites list (:87). |
| `tests/engine/test_media_drive.py` | Temp lists its groups (:28). Favorites are a folder, not a list (:41). Drive folders over HTTP (:66). Move in and purge (:86). Favorite folders are a list of paths that follows rename, move and remove (:106). |
| `tests/engine/test_media_characters.py` | Unset folder and refused put (:21). List, put, replace and delete (:35). Folder chosen and cleared live through settings (:81). `chars/` ids are media ids (:111). Routes over a fake ctx (:117). Rename and delete over HTTP (:138). Notes over HTTP (:166). |
| `tests/engine/test_engine_lane.py` | A run lands images and leaves the outbox empty (:57). Landing strips whatever metadata the engine wrote (:231). |
| `tests/core/test_named.py`, `test_temp.py`, `test_pngtext.py` | `named.put`, `rename`, the text allowed in Characters and under the storyboards folder; `temp.regroup`, `file_clip` and `newest_temp` (a clip filed by name, a redo numbered, a picture or a missing clip refused); `pngtext` as the only writer of picture text (3.4). |
| `tests/engine/test_continue_land.py` | A continued clip lands flat in its day folder and the source never moves (3.2.5). |
| `tests/core/test_clips.py`, `test_clips_facts.py`, `test_clips_http.py` | The clips root, its kinds, urls and missing thumbnail; delete and regroup; the tag cut and the facts read at landing; `/files` answering `Range`; the `/clips` path serving the shell; the listing apart from Temp; delete yes, favorite, move and character no (3.2.9, 3.1.1). |

### Web (`web/tests/`)

| File | What it guards |
|---|---|
| `unit/selection.test.ts` | click, Ctrl, Shift; select all and Escape; arrows by columns; `targets`; `afterDelete`; `follow` keeping a multi-selection. |
| `unit/send.test.ts` | `sendState` reasons in order, reference verbs, full references keeping Replace, the pick state, `deliveryText`. |
| `unit/misc.test.ts:79-86` | `geometry`, `windowRange` and `totalHeight` from `gridMath.ts`. |
| `e2e/media.spec.ts` | Layout, the right-click menu, Del/F/keys, the organizer (groups, Drive folder new/rename/delete, drop-to-move), Stage zoom, a new generation following, and the unset Drive. |
| `e2e/media-bar.spec.ts` | Folds, the Generate button, the utilities fold-up, the Desktop launch list, previous/next, reopening on Temp, and Stage Fit. |
| `e2e/media-edges.spec.ts` | Edge-zone stepping only when folded, same-zone press only, no zoom on double-click in a zone, the boundary following the counter. |
| `e2e/media-favorites.spec.ts` | Pinning Drive folders under Favorites. Nothing moves, and images have no such menu line. |
| `e2e/characters.spec.ts` | Section placement and count, heading and name views, drop replace, drop on the heading asking for a name, unset state, the Settings → Storage row. |
| `e2e/characters-menu.spec.ts` | Add to Characters flow, replaced vs added, off states, the name menu, rename and delete behaviour. |
| `e2e/characters-notes.spec.ts` | Notes dot and title, the box cap, Ctrl+Enter/blur save, clear, unchanged sends nothing, Escape, the id following a JPEG-to-PNG change. |
| `e2e/fit.spec.ts` | The `media` screen at four viewports: nothing overlaps or is cut off. |
| `unit/clips.test.ts`, `e2e/media-clips.spec.ts` | The Clips section and the Clips start view (3.7.4, 3.7.11). |
| `unit/continue.test.ts`, `e2e/video-continue.spec.ts` | Continue on the menu and the bar (the source stays where it is), a picture without Continue (3.7.8, part 2, 2.8). |

The e2e specs run against a fake server (`web/tests/e2e/fixtures/controller.ts` `FakeHub`,
`fixtures/api.ts`), not the Python Hub.

---

## 3.9 Recipes

### 3.9.1 Add a tree section

Model it on Characters.

1. **Server data.** Add the operation to `hub/core/` and expose it on `class Files` (`hub/core/files.py`). Add
   its signature to the `Files` protocol (`hub/core/api.py:203-227`).
2. **Routes.** Add handlers in `hub/modules/media/routes.py`. Each mutation must call `_changed(ctx, "<what>")`.
   Register them in `hub/modules/media/manifest.py` `routes=(...)`. Paths are relative to `/api/media`.
3. **Web store and loader.** In `web/src/screens/media/media.ts`:
   - add a `createStore`, a `load…()` and the mutation helpers;
   - add the loader to `refresh()` (`:184-187`) so `media.changed` and reconnect refresh it;
   - if the section shows items in the grid, extend `View` (`:16`), `sameView` (`:81-82`) and `itemsOf` (`:91-97`).
4. **Component.** Create `web/src/screens/media/<Section>.tsx` with rows styled from `Tree.module.css`
   (`s.row`, `s.on`, `s.drop`, `s.count`, `s.unset`). Mount it in `Tree.tsx` between the `s.sep` dividers
   (`:151-164`); the Clips section is the example of one that draws its rows in `Tree.tsx` itself.
5. **Media window.** Add an empty-grid text in `Media.tsx:31` (`empty`) for the new view kind.
6. **Tests.** Add Python route tests beside `tests/engine/test_media_characters.py`. Add e2e coverage with the
   `FakeHub` fixtures in `web/tests/e2e/fixtures/`.

### 3.9.2 Add a menu item

There are three menus:

| Menu | Where | Notes |
|---|---|---|
| Image (thumbnail) menu | `Media.tsx:146-156` (`menuItems`) | Items act on `chosen` (`targets(sel, order)`). |
| Folder menu | `Tree.tsx:81-89` (`folderMenu`) | Favorite-folder rows use only `starItem` (`:76-80`). |
| Character menu | `Characters.tsx:67-75` (`openMenu`) | — |

An item is a `MenuItem` (`web/src/ui/Menu.tsx:8`): `{label, icon?, key?, danger?, off?: string|null, run,
sub?}`. `off` is the reason text when disabled. If it has a key, also add the key to the keydown switch in
`Media.tsx:128-142`. If it needs the server, add a route as in 3.9.1, steps 1–2.

### 3.9.3 Add a root

1. **`hub/core/files.py`.** Add the constructor parameter and a `set_<root>()` setter, and add the key to
   `roots` in `_build` (:87-93). `resolve`, `existing_image`, `item_for`, `url` and the thumbnails then work for
   `<key>/…` ids. Update the `Files` docstring and the `roots` comment in `hub/core/api.py:204`.
2. **Settings.** Add the default in `hub/settings.py:31` (`paths`), validation at :163-166, a
   `<root>_root(settings)` reader near :243-253, and, in `hub/settings_edit.py`, `_EDITABLE` (:11-13), `_ROOT_NAMES`
   (:45) and `_check_paths` (:48-78, using `pathrules.drive_root` or a new rule in `hub/pathrules.py`).
   A root that is the Hub's own, like the clips, needs none of this: it is fixed under `<data>` (3.9.4).
3. **Wiring.** Pass the root in `hub/core/runtime.py:82`. Re-point it in `hub/core/apply.py:apply` (:24-29).
4. **Accept its ids.** Extend `library.is_media` (`hub/modules/media/library.py:48-50`) so `_ids`,
   `character_put` and the other routes accept them.
5. **Listing route.** Add a listing route, as with `drive_list` or `characters_list`, that returns
   `{unset:true}` until chosen.
6. **Settings UI.** Add a `PathRow` in `web/src/shell/settings/CoreList.tsx:79-80`.
7. **Tree section.** Add one per 3.9.1.

### 3.9.4 Add a Hub-owned root (the clips are the example)

A root the Hub owns needs no setting: add it to the folders `Files.__init__` makes (`files.py:72-73`) and to
`roots` in `_build` (`:94`), give its files a kind in `Files.kind` (`:144-149`) and a media type in `MEDIA_TYPES`
(`:26`), say what `existing_image` and `existing_media` accept, and add it to `forget_older_records` (`:61-63`). In Media,
add it to `ROOTS` (`library.py:24`), teach `rel_of`/`is_media` its ids, add the `root` value to `list_media`
(`routes.py:60-70`), decide per route what refuses it (`_pictures`), and give the web a `Root` value and a store in
`media.ts` (`:43-44`), a `View` kind, and a section in `Tree.tsx` like the Clips rows (`:160-163`). The engine side lands
into it in `enginecat.land` (3.2.5).

---

## Gaps / unverified

- The line numbers in the clips material in 3.2.9 and 3.7.11 and the Continue material in 3.2.5, 3.7.4 and 3.7.8
  were read from a tree that was still being edited.
- `clip.strip` and `clip.facts` have run only on the synthetic MP4s of `tests/fakes/mp4.py`. Which boxes a real
  engine MP4 carries, and whether `facts` accepts them, is unmeasured.
- The Clips section lists clips from `GET /api/media?root=clips`, which gives no size or length for a clip; only a clip
  that landed while the window was open carries them. The Stage takes the size from the file itself.
- The Grid puts a clip in the `MEDIA_DRAG` payload (`Grid.tsx:81-87`, `dragged` in `media.ts`); Generate's boxes continue a
  clip whose id is in it (`Slots.tsx:24-34`) and the Edit Video strip takes it (Stage 11).
- `web/tests/e2e/fit.spec.ts:28` lists `[data-region="actions"]` as a Media column. No element in `web/src`
  sets `data-region="actions"`. How `fitProblems` treats a missing selector was not read.
- `/api/media/delete` and `/api/media/move` accepting `chars/` ids (3.4.7) is read from code only. No test
  covers it. The Media window's Delete in the Characters view therefore erases only the one file, not every
  file of the stem.
- `library.page` walks all of Temp on every request, and Temp order is lexicographic by id rather than by file
  time. Both are read from code. No performance test was found.
- The exact server-side semantics of `delivery.py` (pre-check reasons, the received timeout) were only skimmed
  for this section. They belong to the bus/delivery section.
- `Menu` (`web/src/ui/Menu.tsx`): a menu opened from the keyboard focuses its first enabled item once it is visible (`:32`), and the arrow keys walk every `[role=menuitem]` of the open menu whatever wraps it, a fold-out list's items apart (`enabled`, `:14`; `key`, `:36-47`); pinned by `web/tests/e2e/media-bar.spec.ts` (Enter opens, item 1 focused, ArrowDown wraps, ArrowUp, Enter picks). The fold-out list's own keyboard behaviour (ArrowLeft and ArrowRight, `:39-40`) was only skimmed.
- The "no logs" claim rests on reading the listed files. Callers outside them, such as the guard or the
  runtime, were not audited for request logging.
