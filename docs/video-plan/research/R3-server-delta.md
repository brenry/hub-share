# R3 — Server delta for Generate Video (MiniMax H3)

This turns `docs/architecture/parts/08-video-blueprint.md` §2, §3 and §6 into a list of tasks that can be done one
file at a time. It corrects the blueprint where the code disagrees and settles its open choices. Line numbers refer
to the tree as it was read for this note. `hp:` means the `app/` folder of a HocusPocus source copy.

**R1 status.** `R1-engine-h3-contract.md` did not exist when this was written. The task keys in §2.5 come from the
engine source (`hp:wgp.py`, `hp:shared/api.py`, `hp:models/minimax_h3/*`, `hp:defaults/minimax_h3*.json`). Where
R1 says otherwise, R1 wins, and only §2.5 and §3.2 need to change.

The constraints, as they are applied below:
- A module imports only `hub.core.api` and its own package (`tests/core/test_rules.py:57-64`,
  `tests/engine/test_rules.py:39-45`). Core never imports a module (`:67-70`).
- No `.py` file over 300 lines (`tests/core/test_rules.py:73-75`). Ruff line length is 120 (`pyproject.toml:27`).
- Code that two modules need is lifted into core, never copied.
- Generate Image (GI) is only touched where code moves **out** of it into core. Every GI test that must change is
  named, line by line.

---

## 0. Corrections to the blueprint

| # | Blueprint says | The code says | Resolution |
|---|---|---|---|
| C1 | §2.2: add `Engine.last` to the lane (`hub/core/engine.py`) | `engine.py` is 297 lines. The 5–6 lines it needs would take it past 300 | Put `last` on a core **EngineView** in `context.py`, shared by every module (L4) |
| C2 | §2.2: "the cache key needs no change" | `catalog_key` (`enginecat.py:28-41`) only marks engine files and folders. A catalog cached before the change has no `video_models`, and it is served until a folder changes | Add a format mark to the key (T4) |
| C3 | §2.12: a clip sent to a reference socket is refused as `kind` | `delivery._precheck` calls `existing_image` first (`delivery.py:104-107`), so a clip is refused as `bad_item`, "That image is no longer available" | Use `existing_media` there, then the `kind` check applies (L7) |
| C4 | §2.7: only `files.py` is image-only | `drive.IMAGES` (`drive.py:19,88`) also filters the Drive listing. A clip moved to the Drive would vanish from Media | Add `drive.MEDIA` for the listing. Characters keep `IMAGES` (`characters.py:47`) (L7) |
| C5 | §1.4: `sliding_window_size = video_length` is "Unverified, maybe needed" | Pruned defaults to 345 (`hp:defaults/minimax_h3.json`), so it is harmless there. Fused defaults to **243** (`hp:defaults/minimax_h3_fused_turbo.json`), so a 260–345-frame fused clip would run as two windows | Required. Always send it (§2.5) |
| C6 | §2.6: force `MMAudio_setting: 0` and `minimax_h3_extended_duration: False` on **every** task | `minimax_h3_extended_duration` is a keyword whose default is already False (`hp:wgp.py:7451`), and the module caps frames at the one-pass maximum anyway. `MMAudio_setting` is a required input (`hp:wgp.py:923`). Forcing H3 keys on image tasks is contamination | Add `FORCED_VIDEO = {"MMAudio_setting": 0}`, applied only when `image_mode == 0` (§3.1) |
| C7 | §2.4/§2.5: `land` returns `(id, w, h)` plus seconds | Returning a 4-tuple makes `engine.py:158` longer than 120 characters | `land` returns a dict `{item, w, h, seconds}`. `engine.py` stays at 297 lines (L6) |
| C8 | §2.3: `Files.size(item) -> (w, h)` | Media also needs `seconds` and `kind` for every tile (`library.py:66-80`) | One call, `Files.info(item) -> {kind, w, h, seconds}` (L5) |
| C9 | §3.1: a `cast.py` for video | Once box resolution is in core (L3), what is left is a cap check of 6 lines | No `cast.py`. The check lives in `screen.py` |
| C10 | §3.2: `/defaults` routes for video | GI's defaults are per mode, text vs refs (`generate_image/routes.py:165-188`). Video has one model setting | No `/defaults` route and no `/seed/random`. Fewer routes, nothing copied |
| C11 | §3.3: `aspect` is a fixed choice list | That list would be a module copy of the engine's tier table, which the blueprint itself rules out (§1.3) | `aspect` and `resolution` are live choices, checked against the catalog |
| C12 | §2.14: the module validates its defaults "at start" | `ctx.settings` is replaced on every settings save (`apply.py:37-38`) | Merge and check at every read (`models.conf(ctx)`). An invalid key falls back to its default, and the card says so |
| C13 | §8: `api.py` goes 254 → ~285 | Draft protocol + checks + Files + MEDIA_TYPES would come to ~300 | Move `Invalid` and the pure checks into a new stdlib `hub/core/values.py`, re-exported by `api.py`. `api.py` ends at ~270 (L1) |
| C14 | §2.12: Range support "Unverified on 1.7.0" | The installed Starlette in this sandbox is 1.6.0, and its `FileResponse` source handles `Range` | Still add the 206 test. The lock says 1.7.0 (`requirements/controller.lock:20`) |
| C15 | §3.7: move `list_characters` to Media | That changes GI's tool list with nothing moving into core | Leave it in GI for the primitive. Open decision D1 |
| C16 | §8 risk: gate video on `min_vram_gb` | `Ctx` has no VRAM view. A module cannot see GPU totals | Dropped from the primitive. Open decision D7 |
| C17 | §3.3: `models_allowed: ["minimax_h3"]` | That prefix also matches `minimax_h3_ref2va*` (Omni). Omni cannot take a first frame (`image_prompt_types_allowed: ""`, handler `:1795`), and references are Stage 4 | `models_excluded` default is `["minimax_h3_legacy", "minimax_h3_ref2va"]` until Stage 4 (D4) |

---

## 1. Core lifts

Each lift lists: what, where it lives now, where it goes, who calls it afterwards, the line budget, and the tests.

### L1 — Plain-value checks → `hub/core/values.py` (new, stdlib, ~70 lines)

- **What.** `Invalid` (moved from `api.py:22-27`). `NO_ARGS`.
  - `whole(value, field, lo, hi, text=None) -> int`. The default text is GI screen's
    `"{field} must be a whole number from {lo} to {hi}"`.
  - `number(value, field, lo, hi, text) -> float`.
  - `seed_setting(value, hi) -> dict`: `"random"`, digits or an int becomes `{"mode": …}`.
  - `draw_seeds(spec, count, hi) -> list[int]`.
  - `one_line(exc, default) -> str`.
  - `item_name(item_id) -> str`: the file stem. A character's name is its file stem (`characters.py:3-4`).
- **Now.** GI `build.py:22-40` (`_int`, `_number`, `_seeds`), GI `screen.py:113-127` (`_whole`, `_seed`), GI
  `tools.py:20` and `core/features.py:14` (`NO_ARGS`), GI `models.py:33-35` (`reason`), GI `cast.py:22-25` (`label`).
- **After.** `api.py` does `from hub.core.values import NO_ARGS, Invalid, draw_seeds, item_name, number, one_line,
  seed_setting, whole`, and lists them in `__all__`. Every core file keeps `from hub.core.api import Invalid`.
  `features.py` imports `NO_ARGS` from api. GI keeps the exact texts it passes today, so no GI test changes.
  - `values.py` imports nothing from `hub`, so there is no import cycle.
- **Callers after.** GI `build`, `screen`, `tools`, `models`, `cast`. Video `build`, `screen`, `routes`, `tools`.
- **Budget.** `api.py` 254 → 249 (−7 for `Invalid`, +2 for the import). GI `build.py` 138 → ~118, `screen.py`
  254 → ~238, `models.py` 111 → ~110, `tools.py` 93 → 92. GI `cast.py` stays at 67 here; L3 shrinks it.
- **Tests.** New `tests/core/test_values.py`: bounds, bool refusal, text defaults, seed text/number/random, seed
  wraparound, `one_line`. `tests/engine/test_build.py` and `test_generate_image.py` pass unchanged; they pin the
  texts.

### L2 — Media kinds in one table (`api.py`)

- **What.** `MEDIA_TYPES: Mapping[str, tuple[Kind, str]] = {".png": ("image", "image/png"), ".jpg": …, ".jpeg": …,
  ".webp": …, ".mp4": ("video", "video/mp4")}` (+6 lines). Plus a docstring line on `LaneKind` (`api.py:19`): "image"
  means the Wan2GP engine lane, which runs clips too.
- **Now.** `files.IMAGE_TYPES` (`files.py:23`), `drive.IMAGES` (`drive.py:19`), `media/library.IMAGES`
  (`library.py:21`).
- **After.**
  - `files.IMAGE_TYPES = {s: t for s, (k, t) in MEDIA_TYPES.items() if k == "image"}`. It keeps its name, so
    `fileroutes.py:131` is unchanged.
  - `drive.IMAGES` becomes derived the same way. `drive.MEDIA = tuple(MEDIA_TYPES)`.
  - Media's `library.IMAGES` is deleted (T8).
- **Budget.** `api.py` 249 → 255.
- **Tests.** Covered by the `test_files` and `test_media` additions (§5).

### L3 — Reference boxes by character name → `hub/core/characters.py`

- **What.**
  - `picture(files, item_id) -> {"id", "w", "h"}` (Pillow size).
  - `boxes(files, names, held) -> list[dict]`: each name is a character (any case, `find`), or a held box whose
    `item_name` matches. Otherwise it raises `Invalid("references", 'No character "X"; list_characters names
    them')`.
  - Exposed as `Files.pictures(names, held)` (protocol +1 line, class +2 lines).
- **Now.** GI `cast.py:34-56` (`_picture` and the name/kept loop of `resolve`).
- **After.**
  - GI `cast.resolve` = `ctx.files.pictures(names, routes.session_part(ctx).get("references") or [])` followed by
    its own cap check (`cast.py:57-62`, unchanged). `cast.py` 67 → ~45, and its `PIL` import goes.
  - `cast.label` = `item_name`.
  - Video `screen.py` calls the same core method.
- **Budget.** `characters.py` 188 → ~215. `files.py` +2.
- **Tests.** `tests/core/test_characters.py`: boxes by name in any case, a kept box by label, an unknown name with
  the exact text, w/h read. `FakeFiles` gains `pictures` (delegating to `characters.boxes`). GI
  `test_generate_image.py:520-540` (references) stays as it is: same box shape `{id, w, h}`.

### L4 — Last catalog answer → `EngineView` in `hub/core/context.py`

- **What.** `class EngineView` (~14 lines).
  - `query(what, **args)` forwards to `core.engine` and remembers the answer per `what`.
  - `last(what) -> dict | None`.
  - One view per Core (`runtime.py:82`: `self.engine_view = EngineView(lambda: self.engine)`).
  - `ModuleCtx.engine` returns it (`context.py:100-102`).
  - `api.Engine` gains `def last(self, what: str) -> dict | None: ...` (+1).
- **Now.** GI `models.py:18-30` (`_last`, `catalog`, `cached`), a module-global that only GI fills.
- **After.**
  - GI `build.py:88` uses `ctx.engine.last("models")`. GI `models.catalog` stays as the one-line query wrapper with
    the `rescan` doc. `_last` and `cached` are deleted.
  - Video `build` reads the same view.
  - Because the view is shared, GI's warm-up at start (`generate_image/manifest.py:15-26`) also fills it for video.
    Video needs **no** warm-up of its own, so there is nothing to copy.
- **Budget.** `context.py` 110 → ~126. `runtime.py` 253 → 254. `api.py` 255 → 256. GI `models.py` → ~100.
- **Tests.** `FakeEngine` gains `_last` (set in `query`) and `last()`. `test_build.py:29-31,63-65` pass unchanged:
  they call `models.catalog(c)` first. New case in `tests/core/test_session.py`: the view remembers per `what`; a
  `NoEngine` failure leaves `last` as None.

### L5 — `Files`: media kinds, existing media, info (`hub/core/files.py`)

- **What.**
  - `existing_media(item_id) -> Path`: suffix in `MEDIA_TYPES` and a file.
  - `kind(item_id)` returns `MEDIA_TYPES[suffix][0]` or None (`files.py:118-119`).
  - `info(item_id) -> {"kind", "w", "h", "seconds"}`: Pillow for images (seconds None), `clip.probe` for video.
  - `delete`, `move` and `regroup` use `existing_media` (`files.py:153,168,187`).
  - `thumbnail` stays `existing_image` (`:242`): no server thumbnail for a clip (§4.3).
  - Protocol: `existing_media`, `kind`, `info` (+3 in `api.py`). `kind` is used by core today but missing from the
    protocol.
- **Now.**
  - Four Pillow size reads: GI `cast.py:36`, GI `routes.py:198`, `media/library.py:72`, `enginecat.py:119`. The
    first two go away with L3 and L8. Library uses `info` (T8). `enginecat` reads the path it has just landed (L6).
- **Budget.** `files.py` 243 → ~262. `api.py` 256 → 259.
- **Tests.** `tests/core/test_files.py`: `kind("out/d/a.mp4") == "video"`; `existing_image` still refuses `.mp4`
  (keep `:53-61`, add `.mp4` to its refusals); `existing_media` takes it; delete, regroup and move work on a clip;
  `thumbnail` on a clip raises `Invalid`; `info` on a clip and a PNG. `FakeFiles` gains `existing_media`, `kind`,
  `info` (delegating to `Files` logic, as `regroup` does).

### L6 — Clips land (`hub/core/clip.py` new, `hub/core/enginecat.py`, `engine.py`)

- **`clip.py`** (stdlib, ~170 lines). An ISO-BMFF walker that reads boxes by seeking and loads `moov` only.
  - `probe(path) -> (w, h, seconds)`.
    - w and h from the video trak's `tkhd` (last 8 bytes, 16.16). The video trak is the one whose
      `mdia/hdlr.handler_type == b"vide"`.
    - seconds = `mvhd.duration / mvhd.timescale` (v0/v1).
  - `strip(path)`, in place (`r+b`), with sizes unchanged, so `stco`/`co64` stay valid wherever `moov` sits.
    1. Refuse (`ValueError`) without `ftyp`+`moov`+`mdat`, with a `moof` (fragmented), or with a box size that runs
       past the end of the file.
    2. Top-level and `moov`-level `udta`, `meta` and `uuid` are retyped `free`, payload zeroed. So are `trak/udta`
       and `trak/meta`. This removes `©too "Lavf…"` (ffmpeg's `encoder` tag, written by the imageio writer and
       again by the `-c:v copy` audio mux, `hp:shared/utils/audio_video.py:440-443`).
    3. Zero the creation and modification times in `mvhd`, `tkhd` and `mdhd`.
    4. SEI. Take the video trak's `stsd` entry:
       - `avc1`/`avc3`: `avcC` gives the NAL length size (byte 4 & 3, plus 1).
       - `hvc1`/`hev1`: `hvcC` gives it (byte 21 & 3, plus 1).
       - Read the **first sample**: offset from the first `stco`/`co64` entry, size from `stsz`.
       - Walk its NAL units. An SEI is H.264 type 6, or HEVC type 39/40.
       - In each `user_data_unregistered` message (payloadType 5), overwrite every printable byte (0x20–0x7E) after
         the 16-byte UUID with 0x20. Lengths, NUL terminators and any emulation-prevention bytes stay put.
       - This blanks x264's `"x264 - core … options: …"`, and x265's info string if x265 is configured.
       - Any other codec entry: leave the samples alone. Metadata boxes are still blanked.
  - Answer to the brief: **the engine's own options do not suffice**.
    - `metadata_type: "none"` (`hub/worker/wan2gp.py:38`) only stops the settings JSON (`hp:wgp.py:9536-9549`).
    - The codec presets (`hp:shared/utils/audio_video.py:625-650`) add no `-bitexact`, `-map_metadata -1` or SEI
      filter.
  - Pillow-free stdlib can do it: `struct` and seek.
- **`enginecat.land`** (`enginecat.py:104-123`).
  - Branch on `MEDIA_TYPES.get(suffix)`:
    - image: `clean.strip` plus a Pillow size, as now;
    - video: `clip.strip` plus `clip.probe`;
    - none: unlink, then `EngineFailed("runtime", "The engine wrote a file the hub does not take")`.
  - The failure text for unreadable files becomes "The engine wrote a file the hub could not read".
  - Returns `{"item", "w", "h", "seconds"}`.
- **`enginecat.catalog_key`.** Add `"catalog:2"` to `marks` (`:31`, C2).
- **`engine.py:158-159`.** `landed = await asyncio.to_thread(enginecat.land, …)` then
  `emit("output", {"task": k, **landed})`. Still 297 lines.
- **Budget.** `enginecat.py` 123 → ~133. `engine.py` 297 → 297.
- **Tests.**
  - New `tests/fakes/mp4.py`: `tiny_mp4(w, h, seconds, encoder="Lavf61.7.100", sei=b"x264 - core 164 …",
    codec="avc1") -> bytes`. moov holds mvhd, a trak (tkhd, mdia(mdhd, hdlr vide, minf/stbl(stsd avc1+avcC, stsz,
    stco))) and udta/meta/ilst/©too; mdat holds one AVCC sample (SEI + one fake slice).
  - New `tests/core/test_clip.py`: probe values; strip keeps the file length and every `stco` offset; no `Lavf` and
    no `x264` bytes remain; the UUID is still there; times are zero; a PNG, a truncated file and a `moof` file are
    refused; an HEVC variant.
  - `tests/engine/test_engine_lane.py:243`: `landed = enginecat.land(...)`; `(landed["w"], landed["h"]) == (6, 4)`.
    Add `test_landing_a_clip_blanks_encoder_marks` and `test_landing_refuses_other_files`.

### L7 — Core callers that assume pictures

- **`fileroutes.serve_file`** (`fileroutes.py:169-174`): `existing_media`, `media_type=MEDIA_TYPES[suffix][1]`.
  `thumbs` and `check` stay image-only; references must be pictures.
- **`delivery._precheck`** (`delivery.py:105`): `existing_media` (C3).
- **`drive.listing`** (`drive.py:88`): `MEDIA` (C4).
- **`dispatch._ev_output`** (`dispatch.py:211-221`): `kind = self.files.kind(item)`; `"kind": kind`;
  `"thumb": self.files.thumb_url(item) if kind == "image" else None`; `"seconds": d.get("seconds") if kind ==
  "video" else None`.
- **Budget.** fileroutes +1 line, delivery 0, drive +1, dispatch 233 → ~235.
- **Tests.**
  - `test_files.py::test_files_and_thumbs_over_http`: a clip is served as `video/mp4`. `Range: bytes=0-99` gives
    206 and 100 bytes. `/thumbs/<clip>/336` gives 404.
  - `tests/core/test_drive.py`: the listing includes `.mp4`.
  - A delivery case: a clip to an image socket is refused with reason `kind`.
  - `test_jobs.py`: see §5.

### L8 — Characters list for Tab completion → core route `GET /api/characters`

- **What.** In `fileroutes.py`, next to `/api/media/check`. Answers `{"items": [{name, id, w, h, thumb}]}` from
  `files.characters()` and `files.info`, without notes, exactly as GI's route does today.
- **Now.** GI `routes.py:191-204` and its manifest entry (`manifest.py:40`).
- **After.** GI's route and its `PIL` import are deleted. GI web `compose/complete.ts:14-15` points at
  `/api/characters` (R4, W6). Video web uses the same route.
- **Budget.** `fileroutes.py` 104 → ~120. GI `routes.py` −15.
- **Tests.**
  - Move the route's case into `tests/core/test_files.py` (HTTP, through the harness).
  - `test_generate_image.py:76`: drop `("GET", "/characters")` from the expected route set.
- **Depends on R4** deciding that Generate Video has Tab completion. If it does not, defer L8 (D2).

### L9 — The draft in two parts → `hub/core/draft.py` (new, ~80 lines) + `api.Draft`

- **What.** `ctx.draft(saved: tuple[str, ...], session: tuple[str, ...], name="draft") -> Draft` with:
  - `settle()`: the disk keeps saved fields only;
  - `saved()`;
  - `session()`: the live dict, created on use;
  - `get()`: `{**saved, **held}`, never creating a part;
  - `put(changes) -> dict`: a merge-PUT into each part. It replaces the doc every time, as now;
  - `clear(fields) -> bool`: empties the held text fields; False and no part made when none held text;
  - `window() -> bool`: `(bus.presence().get("screens") or {}).get("workspace")`.
- **Where held.** `ModuleCtx.held: dict[str, dict]`, keyed by doc name. `Core._session_ended` (`runtime.py:93-96`)
  clears every `ctx.held` before it emits `session.ended`. Modules no longer listen for `session.ended` to drop
  their parts.
- **Now.** GI `routes.py:25-58` (`SESSION_FIELDS`/`SAVED_FIELDS` stay as GI's policy; `_session`, `settle`,
  `session_part`, `on_session_ended` and the body of `on_chat_cleared` go), `routes.py:134-149` (get/put body),
  `screen.py:202` (presence check).
- **After.**
  - GI: `routes.draft(ctx) = ctx.draft(SAVED_FIELDS, SESSION_FIELDS)`.
  - `session_part(ctx)` stays as a one-line accessor, `return draft(ctx).session()`, because `screen`, `cast` and
    `build` all use it.
  - `on_chat_cleared` = `if draft(ctx).clear(("prompt", "draft")): publish`.
  - The manifest `listens` keeps only `chat.cleared`.
  - Video uses the same calls with its own field tuples.
- **Budget.** `context.py` ~126 → ~134; `runtime.py` 254 → 256; `api.py` 259 → ~269 (`Draft` protocol 8 lines,
  `Ctx.draft` 1, `Files.pictures` 1); GI `routes.py` 204 → ~165 (with L8).
- **Tests.** New `tests/core/test_draft.py`: merge-PUT keeps the other fields; session fields are never on disk;
  `settle` drops a stale prompt from disk; `clear` with nothing held makes no part and returns False; `window()`
  follows presence; through the Core harness, a session end empties every module's held parts.

  `tests/engine/helpers.py::FakeCtx` gains `held = {}`, `draft()` (built on the real `hub.core.draft.Draft` over a
  `FakeDoc`) and `end_session()` (clears `held`).

  GI test edits (no behaviour change):

  | Line | Now | After |
  |---|---|---|
  | `test_generate_image.py:84` | listens has `session.ended` | `{"chat.cleared": routes.on_chat_cleared}` |
  | `:145`, `:279`, `:452` | `await routes.on_session_ended(ctx, {})` | `ctx.end_session()` |
  | `:454` | `ctx.data_dir not in routes._session` | `ctx.held == {}` |
  | `:42` (`box`) | `routes.session_part(ctx).update(...)` | unchanged |

### L10 — Not lifted, on purpose

| Candidate | Why not |
|---|---|
| Canvas/size math (`generate_image/screen.py:50-68`) | Image-only: aspect × megapixels, rounded to 16. Video uses the engine's tier table. No shared logic |
| `ref_caps` (`hub/settings.py:34,138-143`) | Video caps come from engine facts (`first_frame`, `ref_manifest`) and the module's box count. Nothing to share |
| `list_characters` (`generate_image/tools.py:84-91`) | Stays in GI (D1). Video setting texts name it. Tool names are global (`registry.py:115`) |
| Settings defaults for video | Module-owned `DEFAULTS` (`models.conf`). No change to `hub/settings.py` (C12) |
| Thumbnails for clips | None on the server (§4.3) |
| GI warm-up at start (`generate_image/manifest.py:15-26`) | Not needed by video: the shared EngineView (L4) is filled by GI's warm-up, by `/models` and by the tool's catalog read |

---

## 2. The module `hub/modules/generate_video/`

### 2.1 `manifest.py` (~30 lines)

```python
MODULE = Module(
    id="generate-video", title="Generate Video",
    tab=Tab(label="Generate Video", order=20),                       # GI is 10 (generate_image/manifest.py:32)
    lanes=("changed",),                                              # → "generate-video.changed", workspace role
    sockets=(SocketGroup("reference", "Reference", ("image",), screen.BOXES),),
    routes=(Route("GET", "/models", routes.get_models),
            Route("GET", "/draft", routes.get_draft),
            Route("PUT", "/draft", routes.put_draft, body_limit=262_144)),
    jobs={"video": build.video_job},                                 # → kind "generate-video.video"
    card=Card(title="Generate Video", order=890, state=routes.card),  # between GI 880 and Network 900
    listens={"chat.cleared": routes.on_chat_cleared},
    screen=tools.SCREEN, listings=tools.LISTINGS, actions=tools.ACTIONS,
    start=start)                                                     # start: routes.draft(ctx).settle()
```

- `screen.BOXES = 1` in the primitive (first frame only). It becomes 3 in Stage 4 for Omni.
- The socket max is the module's constant, because the registry needs it at import (`registry.py:85-87`).

### 2.2 `models.py` (~110 lines): video models as the UI and MCP see them

- **`DEFAULTS`** (overridden in `settings.json` → `modules.generate-video`):

  ```python
  {"models_allowed": ["minimax_h3"], "models_excluded": ["minimax_h3_legacy", "minimax_h3_ref2va"],
   "tiers_offered": ["480p", "540p", "720p"], "only_available": True, "seconds": 5, "resolution": "540p",
   "aspect": "16:9"}
  ```

- **`conf(ctx) -> (dict, list[str])`**: the defaults with each valid owner value on top, plus the names of invalid
  keys (for the card).
- **`offered(ctx, cat)`**: `cat.get("video_models", [])` filtered:
  - by prefix allowed and not excluded;
  - by `status == "available"` (or also `partial` when `only_available` is false);
  - by a complete `video` block (fps, frames, at least one tier in `tiers_offered`).
  - Sorted like GI `present`.
- **`find(ctx, cat, model_id)`**.
- **`ui_model(ctx, m)`**:

  ```
  {id, label, family, fps,
   frames: {min, step, max},
   tiers: [{id, sizes: {aspect: [w, h]}}]          # only the offered tiers, in tier_order
   steps: {default, min, max, locked},             # min/max from video.steps, else screen.STEPS
   firstFrame: bool,
   references: int,                                # 1 if first frame, else 0 (Stage 4: Omni → BOXES)
   referencesAs: "first frame" | None,
   audio: bool}
  ```

- **`frames_for(seconds, video) -> int`**: `n = max(fmin, ceil(round(seconds * fps, 6)))`, then
  `fmin + ceil((n - fmin) / step) * step` (the `round` stops `124/24*24` from becoming 125). Raises `Invalid("seconds", f"{label} makes {fmin/fps:.1f} to {fmax/fps:.1f} seconds")` above `fmax`.
- **`size(m, tier, aspect) -> (w, h)`** from `video.tiers[tier][aspect]` (`"WxH"`). There is no rounding: the tiers
  are already multiples of 32 (handler `:1748`).
- **What differs from image models.** No `guidance_key` use (H3: `guidance_max_phases: 0`, handler `:1809`), no
  LoRAs, no `ref_choices`/`video_prompt_type`. Video adds frames, fps, tiers, audio and a steps range.

### 2.3 `screen.py` (~200 lines): the settings, written in GI's style

| Setting | Kind | Bounds / choices | Lives | Text |
|---|---|---|---|---|
| `draft` | text | `hi=MAX_PROMPT` (4000) | session | "The assistant's draft prompt, shown beside the chat" |
| `model` | choice (live) | — | disk | "Id of the video model, as list_video_models lists it" |
| `seconds` | number | `lo=1, hi=30` (`SECONDS`) | disk | "Length of the clip in seconds, rounded up to the model's frame grid" |
| `resolution` | choice (live) | the model's offered tiers | disk | "Resolution tier, as list_video_models lists it" |
| `aspect` | choice (live) | that tier's shapes | disk | "Shape of the clip, as list_video_models lists it" |
| `steps` | integer | `lo=1, hi=100` (`STEPS`); the model's range is checked in `apply` | disk, per model | "Steps the model runs" |
| `seed` | seed | `lo=0, hi=SEED_MAX` (999,999,999) | disk, per model | "Seed of the clip" |
| `references` | names | `hi=BOXES` | session | "The first frame by character name, as list_characters lists it; [] empties it" |

- `SESSION = {"draft", "references"}`. `ADVANCED = ("steps", "seed")` is kept per model in `advancedByModel`, as in
  GI.
- **`read(ctx)`**: the saved values, with `models.conf` defaults for a missing `seconds`/`resolution`/`aspect`.
- **`pick_model(ctx, cat, saved, wanted)`**: as GI `screen.py:103-110`, over `models.offered`. With none offered, it
  raises `Invalid("model", "No video model can run; list_video_models names them")`.
- **`view(ctx, cat, model)`**:

  ```
  {draft, model, model_name, seconds (exact, from frames), frames, resolution, aspect, width, height,
   steps, seed ("random" | number as text), last_seeds, references (labels via item_name),
   references_as, audio: true}
  ```

- **`apply(ctx, cat, changes)`**, as GI `screen.py:207-227`:
  - `seconds` is checked with `values.number`, then `models.frames_for` (which refuses above the maximum), and saved
    as given;
  - `resolution` must be in `offered tiers ∩ model tiers`;
  - `aspect` must be in that tier;
  - `steps` uses `values.whole` against the model range;
  - `seed` uses `values.seed_setting`;
  - `draft` is refused when `not draft.window()`, with "No Generate window is open";
  - `references` go through `ctx.files.pictures(names, held)`, then the cap. With cap 0: "{label} can't start from a
    picture". With cap 1: "{label} takes one first frame".
  - Then `ctx.bus.publish("changed", "draft", {})`, and the view is returned.

### 2.4 `routes.py` (~80 lines)

- **On disk.** `<data>/generate-video/draft.json`, doc name `draft` (each module has its own data folder,
  `context.py:91`). `SAVED_FIELDS = ("model", "seconds", "resolution", "aspect", "advancedByModel")`.
- **Session.** `SESSION_FIELDS = ("prompt", "draft", "references", "selected")`, held by core (L9).
- **`draft(ctx)`**, `get_draft`, `put_draft`. Bodies are checked with `values` and a JSON-object check.
  - The 8-line `_body` in GI `routes.py:124-131` is the same check. Lift it into `values.json_object(raw, field)` in
    the same task as L1 to avoid a copy (+6 lines in `values.py`).
- **`on_chat_cleared`**: `if draft(ctx).clear(("prompt", "draft")): ctx.bus.publish("changed", "draft", {})`.
- **`get_models`**: `?rescan=1` as in GI.
  - The answer is `[models.ui_model(ctx, m) for m in models.offered(ctx, cat)]`.
  - On an engine error: `JSONResponse({"code": "unavailable", "text": values.one_line(exc, NO_LIST)}, 503)`.
- **`card(ctx)`** (sync, from memory: `ctx.engine.last("models")` and the doc):
  - `"<tier> · <aspect> · <s> s"` with status `ok`;
  - `"No video model in the model folders"` with `attention` when the last catalog offers none;
  - `"Check settings.json: <key>"` with `attention` when `conf` found an invalid key;
  - `"Unavailable"` with `off` before any catalog.

### 2.5 `build.py` (~110 lines): `video_job(params, ctx) -> JobPlan`

- **Params, as the window and the action send them:**

  ```
  {model, prompt, frames, resolution, aspect, steps|None, seed: {mode, value?}, references: [item ids]}
  ```

- **Checks, in order** (texts in GI's style):
  1. `model` is in `models.offered` of `ctx.engine.last("models")`. Otherwise "Choose a model".
  2. `prompt` is 1..`MAX_PROMPT`. Otherwise "Write a prompt" / "Prompt is too long (n / 4,000)".
  3. `frames`: `values.whole` within `[fmin, fmax]` and on the lattice `(frames - fmin) % step == 0`. Otherwise
     "Choose a length the model can make".
  4. `resolution` and `aspect` map to `(w, h)` via `models.size`. Otherwise "Choose a resolution" / "Choose a shape".
  5. `steps`: None means the model default. Otherwise `values.whole` within the model range.
  6. `seed`: `values.draw_seeds(spec, 1, SEED_MAX)[0]`.
  7. `references`: at most `ui["references"]` items. Each goes through `ctx.files.existing_image(id)` and resolves to
     an absolute path. An `Invalid` from core becomes "An image is missing; add it again".
- **Task, text → clip:**

  ```python
  {"model_type": m["id"], "image_mode": 0, "prompt": prompt, "resolution": f"{w}x{h}",
   "video_length": frames, "sliding_window_size": frames,           # C5: one pass, also on fused
   "num_inference_steps": steps, "seed": seed, "batch_size": 1,
   "multi_prompts_gen_type": "FG", "image_prompt_type": "", "video_prompt_type": "",
   "remove_background_images_ref": 0, "activated_loras": [], "loras_multipliers": ""}
  ```

- **Image → clip (FL2VA first frame).** The same task, plus `"image_prompt_type": "S", "image_start": [abs path]`.
  - `"S"` is in `image_prompt_types_allowed: "TSEV"` (handler `:1795`).
  - `image_start` is an attachment key (`hp:wgp.py:107,114`). `shared.api` makes list items absolute
    (`hp:shared/api.py:806-831`). The UI keeps it as a list and the engine reads `image_start[0]`
    (`hp:wgp.py:1300`).
- **Not sent.**
  - No guidance (H3 has none).
  - No `force_fps`: 24 comes from the model (handler `:1740`).
  - No negative prompt: `FORCED_TASK` empties it.
  - No `minimax_h3_*` keys: the signature defaults hold (`hp:wgp.py:7437-7451`).
- **Summary:**

  ```
  {"title": f"Clip · {frames / fps:.1f} s · {label}", "prompt", "model": label, "model_id",
   "mode": "text" | "first_frame", "seconds", "frames", "width", "height", "steps", "seed"}
  ```

  The title is used by `jobs.py:195`, and `model` by the hold texts (`dispatch.py:97`, `plan.py:72-73`).
- `draft(ctx).session()["last_seeds"] = {"model", "seeds": [seed]}`, in memory, as GI `build.py:137` does.
- Returns `JobPlan("image", m["id"], (task,), summary)`. It uses the same engine lane (§4.1).

### 2.6 `tools.py` (~70 lines)

- `SCREEN = Screen(screen.SETTINGS, read_settings, write_settings)`. Core publishes `get_generate_video_settings`
  and `set_generate_video_settings` (`features.py:65-79`).
- `LISTINGS = (Listing("video_models", "Video models that can run, with their lengths, sizes and default steps.",
  {}, list_video_models),)`.
  - `list_video_models` answers
    `{"models": [{id, name, seconds: {min, max, step}, resolutions: {tier: [aspects]}, steps, first_frame, audio,
    loaded}]}`.
- `ACTIONS = (Action("generate_video", "Render the draft as a clip with the screen's settings, as the Generate
  button does.", NO_ARGS, generate_video),)`.
  - The action builds params from `read` + `draft()`, with `frames = models.frames_for(saved seconds)`.
  - It submits `"video"` and returns `{state}`, plus `held` when the job is held. Same as GI `tools.py:50-78`.
- Both descriptions are under 200 characters and end with a period (`registry.py:117`). No tool name is reused.

---

## 3. Worker

### 3.1 `hub/worker/wan2gp.py` (294 → ~298)

- `FORCED_CONFIG` (`:38-40`) gains `"video_container": "mp4"` on the existing last line, so 0 new lines. Landing
  only takes MP4 (L6).
- `FORCED_VIDEO: dict[str, Any] = {"MMAudio_setting": 0}`, with a 1-line comment: never a second audio model (it
  would be a download).
- `translate` (`:47-59`): `extra = FORCED_VIDEO if settings.get("image_mode") == 0 else {}`, and both returns
  spread `**FORCED_TASK, **extra`. Image tasks are byte-for-byte what they are today.
- `video_output_codec` and `audio_output_codec` stay the engine config's, seeded from the engine config (`:146-158`).
- `run()` (`:241-294`) needs no change: one `output` per generated file (`:286-287`) covers an MP4. The engine
  writes `*_tmp.mp4` and a temporary wav to `save_path` (= outbox, `:158`); `sweep` removes them after `task_done`
  (`enginecat.py:95-101`).
- **Budget check:** 298 ≤ 300. No other change may go into this file in this stage.

### 3.2 `hub/worker/catalog.py` (157 → ~190)

- `build()` (`:127-157`) keeps `models` exactly as it is.
- It adds `video_models` from the same loop:
  - a definition with `t2v_class` or `i2v_class`, no `image_outputs`, and not `audio_only`;
  - each entry is `describe(...)` + `"video": video_facts(model_def)`.
- **`video_facts(model_def)`** (~20 lines):

  ```python
  {"fps": int(fps) or None,
   "frames": {"min": frames_minimum, "step": frames_steps, "max": frames_maximum},   # None when absent
   "tiers": {tier: {aspect: "WxH"} for each preset, without the "auto" entry},   # resolution_presets (handler :439-524)
   "tier_order": resolution_preset_order,
   "first_frame": "S" in image_prompt_types_allowed,
   "last_frame": "E" in image_prompt_types_allowed,
   "ref_manifest": bool(model_def.get("supports_reference_audio")) or not image_prompt_types_allowed,   # Stage 4; R1 to confirm
   "audio": bool(returns_audio),
   "steps": {"min": inference_steps_min, "max": inference_steps_max} or None}            # fused json
  ```

- `describe()` and `DEFAULT_KEYS` are unchanged, so image entries keep their exact shape.
- `wan2gp.Engine.catalog()` (`:217-226`) still passes only image ids to `definitions.weights`. Video weights never
  reach the Image models panel.
- Cost: `factory_settings` now runs for every video definition too (`catalog.py:60-76`). On HocusPocus that is
  dozens of models. Stage 0 times one catalog query (Unverified).

### 3.3 Protocol, progress, cancel

- **`protocol.py`.** No change to the wire format. Docstring `:6`: "one image" becomes "one image or clip". 1 MiB
  lines are fine: `output` carries a path.
- **Progress.** The worker forwards `phase`, `current_step`, `total_steps`, `progress` and `status`
  (`wan2gp.py:270-271`).
  - A one-pass clip has one denoise loop, so `enginecat.progress` and the dispatcher ETA
    (`dispatch.py:190-209`) work as they do for one image.
  - VAE decode, audio decode and mux carry no steps. The bar holds near 100% and the phase text changes. Accepted.
  - The window fold (`step' = (w-1)·steps + step`) is only needed once sliding windows are allowed. That is after
    Stage 5, worker-only.
- **Cancel.** Unchanged path: `EngineLane.cancel` → `op: cancel` → `job.cancel()` (`wan2gp.py:234-239`).
  Denoising stops at the next step. Whether decode and mux can be interrupted is Unverified; if not, the cancel
  lands after decode and the job still ends `cancelled` (`dispatch.py:152-153`), possibly with the clip already in
  Temp, as for an image cancelled between `output` and `task_done`.

---

## 4. Jobs, VRAM, landing

### 4.1 Lane

- Video uses the **existing engine lane**: `lane_kind="image"` (`engine.py:31`, `jobs.py:79-83`). There is no
  second worker on the same GPU, and one engine session runs one generation at a time
  (`hp:shared/api.py:324`).
- **Consequence.** One FIFO per lane with head-of-line blocking (`dispatch.py:1`). An image queued behind a clip
  waits. Every change between an image model and H3 is a full release and load (`plan.py:70-74`).
- `queue.max_waiting` (`hub/settings.py:29`) is shared with images (`jobs.py:84-85`).

### 4.2 Learned peaks and hold texts

- **Peaks.**
  - `_ev_task_done` learns `peak - baseline` under `f"{plan.model}|{gpu_uuid}"` and keeps the last 3. `need` is
    the max of those (`dispatch.py:223-229`, `vram.py:65-72`).
  - A clip's peak depends on frames × w × h. A 480p/5 s run teaches less than a 720p/14 s run needs, so the plan
    may say green and the run may then fail with OOM. The reverse case makes small runs wait.
  - Primitive: no change. Option (D3): add `JobPlan.vram_key: str | None = None` (api +1). Dispatch uses
    `plan.vram_key or plan.model` in `gpu.plan(..)`'s need lookup and in `learn` (+2 lines in `dispatch.py`,
    +1 parameter in `vram.plan`). The video builder sets `f"{id}@{tier}:{frames}"`, and each new size runs as
    "First run of this model".
- **Hold texts.** `plan.py` builds every text from `summary["model"]`: "Loading H3 First / Last — Pruned",
  "Switching to …", "First run of this model", "<program> is using N GB on Server GPU". Nothing changes.
- **Idle unload.** `vram.arm_idle` (`vram.py:175-182`) uses the global `idle_minutes` (default 10) for H3 too.
  After a clip, H3 stays resident in VRAM and RAM (mmgp streaming) until then, or until the next image job
  releases it. A per-model idle time is not in scope (D6).
- **`run_anyway` for a clip** (`jobs.py:139-144`). Allowed only on a `vram`/`ram` hold. It skips the plan and
  starts loading H3 next to whatever is in memory; if memory is short, the job fails on the load or the first steps
  with one plain line (`faults.failure`). A failed task still teaches a peak when one was measured
  (`dispatch.py:226-229`). No text changes.

### 4.3 Landing and showing

1. The worker emits `output {file: <outbox>/<date>-<seed>.mp4}` (`FORCED_TASK["output_filename"]`,
   `wan2gp.py:43-44`).
2. `land` (L6) checks the file is in the outbox, runs `clip.strip`, then moves it to
   `out/<YYYY-MM-DD>/<HHMMSS-mmm>.mp4` (`files.temp_path`, `files.py:31-41`) and probes it.
   - The name is the time. Nothing about the clip is in it.
3. The `output` event goes to the lane as `{task, item, w, h, seconds}`.
4. Dispatch publishes on `media` (L7):

   ```
   generation {item: {id, kind: "video", url: /files/<id>?v=…, thumb: null, w, h, seconds, created, job}}
   ```

   The item id is appended to `job.outputs`.
5. Media (module, T8) lists the clip:
   - `rel_of` and `ids` accept `MEDIA_TYPES` suffixes;
   - `describe` uses `ctx.files.info`. A clip gives `{id, kind: "video", url, thumb: null, w, h, seconds,
     createdAt, group, fav}`;
   - favorite, move and delete work through L5;
   - `_ids` text: "Only Temp and Drive items".
6. **Poster frame.** There is no server thumbnail.
   - The controller has no H.264 decoder (`thumbs.render` is Pillow, `thumbs.py:65-85`), and nothing about a clip
     may be written.
   - The browser draws the poster from the file: `<video preload="metadata" muted playsinline src=url#t=0.1>`.
   - `/thumbs/<clip>/…` answers 404 (`fileroutes.py:176-182`).
   - The tile, Stage and Clip views are R4's.

---

## 5. Tests, file by file

**New shared fakes**
- `tests/fakes/mp4.py`: the stdlib builder (L6). It is used by core tests, `fake_lane`, `fake_worker` and the fake
  engine.
- `tests/fixtures/catalog_video.json`: the existing fixture shape plus `video_models` with `minimax_h3`,
  `minimax_h3_fused_turbo` (steps 4–8), `minimax_h3_ref2va`, `minimax_h3_legacy`, one `missing` model and one Wan
  t2v model with no tiers. The values are copied from the hp definitions above.
- `tests/engine/helpers.py`:
  - `FakeFiles`: `existing_media`, `kind`, `info`, `pictures`;
  - `FakeEngine`: `last`;
  - `FakeCtx`: `held`, `draft()`, `end_session()`;
  - a `video_catalog()` loader.

**tests/core**

| File | Add / change |
|---|---|
| `test_values.py` (new) | L1 |
| `test_clip.py` (new) | L6: probe, strip (length/offsets kept, no Lavf/x264, UUID kept, times zero), HEVC, refusals |
| `test_draft.py` (new) | L9, including a Core-harness case where a session end clears held parts |
| `test_files.py` | L5 + L7 HTTP: clip served as `video/mp4`, Range 206, thumb 404, `/api/characters` (L8) |
| `test_characters.py` | L3 `boxes` |
| `test_drive.py` | Listing includes `.mp4`; characters still ignore it |
| `test_jobs.py` | `FakeLane(suffix=".mp4")` (`fake_lane.py:96-98` writes `tiny_mp4` and emits `seconds`). Assert one `generation` with `kind: "video"`, `thumb: None`, `seconds`; the title from `summary["title"]` |
| `test_session.py` | EngineView `last` stays after a session end; held parts cleared |
| `test_rules.py` | Unchanged. It already checks size and imports for the new files |

**tests/engine**

| File | Add / change |
|---|---|
| `fake_engine/fake_engine.json` | Architecture `minimax_h3`: family `minimax_h3`, `t2v_class`, `i2v_class`, `fps: 24`, `frames_minimum: 124`, `frames_steps: 17`, `frames_maximum: 345`, `vae_block_size: 32`, `image_prompt_types_allowed: "TSEV"`, `returns_audio`, `guidance_max_phases: 0`, two tiers. The `t2v` architecture stays as it is (no `t2v_class`), so existing counts hold |
| `fake_engine/defaults/minimax_h3.json` | New, `video_length: 124`, `sliding_window_size: 345` |
| `fake_engine/wgp.py` | `generate`: when `image_mode == 0`, write `tiny_mp4` (with Lavf + SEI) instead of a PNG. Move the writers into `fake_engine/fakemedia.py` to keep `wgp.py` readable (it is 290 lines; the 300-line rule covers `hub/` only) |
| `test_worker.py` | `video_models` holds `minimax_h3` with the right `video` block and `models` does not. `FORCED_CONFIG["video_container"] == "mp4"`. `translate` adds `MMAudio_setting` only when `image_mode == 0` (both flavours). A video task's output is an `.mp4` |
| `test_engine_lane.py` | `land` dict (`:243`), clip landing, other-suffix refusal, catalog key changes with the format mark |
| `test_media.py` | A Temp `.mp4` is listed with `kind: "video"`, `seconds` and `thumb: None`, can be a favorite, can be deleted; Drive lists it |
| `test_generate_image.py` | Only the L8/L9 edits (`:76`, `:84`, `:145`, `:279`, `:452`, `:454`) |
| `test_generate_video.py` (new) | Manifest (routes, socket, lanes, card 890, jobs, listens). Exact tool names, descriptions and schemas, as GI `:24-35`. `seconds` snapping (5 → 124 frames, 5.17; 14.4 → 345; 15 refused with the text). Tier/aspect → WxH. Steps outside the fused 4–8 refused. Draft refused with no window. `chat.cleared` clears prompt and draft. `conf` override and fallback. `list_video_models` filters (legacy, ref2va, missing, Wan without tiers are absent) |
| `test_generate_video_build.py` (new) | Exact task dicts for text → clip and first frame, summary and title, random/fixed seed, the lattice check, the reference cap, a missing picture, absolute paths, `last_seeds` |
| `test_with_core.py` (extend) | Fake worker in a `video` mode (`tests/fakes/fake_worker.py` writes `tiny_mp4` when `image_mode == 0`): submit `generate-video.video`, the job reaches done, the Temp file has no `Lavf`, Media lists it, then an image job runs after it. Also cancel mid-clip |
| `test_rules.py` | Add `generate_video` to `OURS` (`:9-12`), so the no-logging and import rules cover it |

---

## 6. Ordered tasks

Each task leaves the whole suite green. "Lines" is the expected size after the task (≤300).

| T | Task | Depends | Files → lines |
|---|---|---|---|
| T1 | L1 `values.py`; `api.py` re-exports; GI `build`/`screen`/`tools`/`models`/`cast.label` and `features.NO_ARGS` switched; `values.json_object` | — | values ~76, api ~249, features 98, GI build ~118, screen ~238, tools 92, models ~110 |
| T2 | L2 `MEDIA_TYPES`; `clip.py` + `tests/fakes/mp4.py` + `test_clip.py` | T1 | api ~255, clip ~170 |
| T3 | L5 `Files` (`existing_media`, `kind`, `info`, delete/move/regroup); `drive.MEDIA`; L7 `serve_file`, delivery; FakeFiles | T2 | files ~262, drive ~145, fileroutes ~106, delivery 139 |
| T4 | L6 `land` + `catalog_key` mark; `engine.py` output dict; L7 dispatch item; `fake_lane` mp4 | T3 | enginecat ~133, engine 297, dispatch ~235 |
| T5 | L4 EngineView; GI `models._last`/`cached` deleted, GI build uses `last` | T1 | context ~126, runtime 254, api ~256, GI models ~100, GI build ~118 |
| T6 | L9 `draft.py` + `api.Draft`; GI routes/screen/manifest migrated; GI test edits; FakeCtx | T5 | draft ~80, context ~134, runtime 256, api ~266, GI routes ~180, GI manifest 52 |
| T7 | L3 `characters.boxes`/`picture`, `Files.pictures`; GI `cast` shrinks; L8 `/api/characters` (if D2 = yes), GI route deleted | T3, T6 | characters ~215, files ~264, api ~267, fileroutes ~120, GI cast ~45, GI routes ~165 |
| T8 | Media `library.py` on `MEDIA_TYPES` + `info`; `routes._ids` text | T3 | library ~95, media routes 202 |
| T9 | Worker: `catalog.video_models` + `video_facts`; `FORCED_CONFIG`/`FORCED_VIDEO`/`translate`; protocol docstring; fake engine H3 + mp4 | T4 | catalog ~190, wan2gp ≤298, protocol 75 |
| T10 | Module: `models`, `screen`, `routes`, `tools`, `build`, `manifest`; `catalog_video.json`; `test_generate_video*.py`; engine `test_rules` OURS | T6, T7, T9 | models ~110, screen ~200, routes ~80, tools ~70, build ~110, manifest ~30 |
| T11 | End to end: fake worker `video` mode; `test_with_core` clip + cancel + image after clip | T8, T10 | tests only |
| T12 | Final checks (below) | all | — |

**T12 checks**
- `pytest` passes, and `ruff` passes.
- `wc -l hub/**/*.py | awk '$1>300'` is empty. Watch especially `wan2gp.py`, `engine.py`, `api.py` and `runtime.py`.
- `rg -n "_last|def cached|_session\b|def session_part|IMAGES = \(" hub/` finds only what is intended:
  `drive.IMAGES` derived, and GI's `session_part` accessor.
- `rg -n "from PIL" hub/modules/generate_image` is empty after T7.
- `rg -n "minimax|h3" hub/core hub/worker` is empty. Core and worker name no model.

Later (not in the primitive):
- **T13.** Stage 4 Omni: `BOXES = 3`, `minimax_h3_references` items `{type: "image", path, image_intent:
  "identity", character_name}` (`hp:models/minimax_h3/reference_manifest.py:15-24,84-87`). Remove `ref2va` from
  `models_excluded`.
- **T14.** D3 `vram_key`, if it is picked.

---

## Open decisions (picked in the chat)

| # | Question | Options (recommended first) |
|---|---|---|
| D1 | Where `list_characters` lives | Stays in GI, no change (if GI is disabled, video has no character list) · move to Media · core publishes tools |
| D2 | Tab completion in Generate Video (R4) | Yes: L8 moves GI's `/characters` into core · No: skip L8 |
| D3 | Learned VRAM peaks | Per model, as now · per model × size via `JobPlan.vram_key` |
| D4 | Omni (`minimax_h3_ref2va*`) in the primitive | Excluded until Stage 4 · offered as text → clip only |
| D5 | `only_available` | True (every file present; the engine's check may be strict, `catalog.py:114-124`) · allow `partial` as GI does |
| D6 | Idle unload for H3 | Global `idle_minutes` · a module setting with a core hook |
| D7 | GPU gating (`min_vram_gb`) | None in the primitive (`Ctx` cannot see GPUs) · add a read-only `ctx.gpus()` later |
| D8 | Engine output with another suffix (a stray `.wav`) | Fail the job, loudly · skip it silently |
| D9 | Default `tiers_offered` | `["480p", "540p", "720p"]` · add 768p/1080p |
| D10 | Owner codec other than H.264/H.265 | Blank the metadata boxes and skip the SEI pass · refuse such clips |

## Unverified

- R1's contract. Specifically: `image_start` as a one-item list of absolute paths, and `image_prompt_type: "S"`
  with no `"T"`.
- That H3's `generated_files` holds exactly one `.mp4`, with no separate audio file (D8).
- Which marks a real clip carries: `©too "Lavf…"` in `moov/udta`, possibly per-trak `udta`, x264's SEI only in the
  first sample, and whether `mvhd` times are non-zero. Also that blanking the SEI text in place plays everywhere.
  Stage 0 `strings`/`ffprobe` (blueprint §6).
- `MMAudio_setting` really defaults to 0 in `primary_settings` (`hp:wgp.py:923` needs the key; the default was not
  found).
- Whether H3's VAE and audio decode can be cancelled.
- The phases the session reports after denoising.
- Catalog time with every video definition described on the legacy flavour.
- That the H3 definitions expose `t2v_class`, `fps`, `frames_*` and `resolution_presets` through
  `w.get_model_def()`, as merged by the handler, on the legacy flavour. That fused entries inherit them from
  `minimax_h3`.
- The `ref_manifest` detection rule in `video_facts` (Stage 4, R1).
- Range 206 on Starlette **1.7.0** (checked in source on 1.6.0 only).
- `minimax_h3_text_encoder` defaults to `"nvfp4_awq"` (`hp:wgp.py:7439`). Is that variant's file local on the server
  (Stage 0)?
- That H3 weight files in the model folders show correctly in GI's Image models panel (`autoreg`). They are
  named in definitions (`definitions.py:43-50`) but are not image models.
