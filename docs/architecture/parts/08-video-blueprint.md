# 08 — Video: what was built, the roadmap, the parked full module

This part has three layers, in this order.

- **8.A What was built (Stages 0 to 4).** The scope: H3 is one more model of the Generate Image
  screen, and its clips land in the Clips section of the Media window. No new module, tab or tool. Written from the
  code, with `file:line` citations.
- **8.B The roadmap.** Stages 5 to 10, from the research notes R6 to R9, with the
  status of each. Nothing in 8.B is a promise: each stage is decided in the chat. Where 8.B says a thing is built,
  it is in the code; where it says Proposed or not built, it is not. Continue (Stage 6) and Omni (Stage 7) are
  described in part 2 (2.10), the Clips section in part 3 (3.7.11), the storyboard module's tools in part 4 (4.9) and the
  adapter seam in part 5 (5.6).
- **8.C The parked full module.** The earlier design for a separate Generate Video module (own tab, core lifts, new
  tools). It is kept as reference. Sections 1 to 8 below belong to it.

Sources: `docs/video-plan/research/R1`–`R9` and the code. Citations are `file:line`.

---

## 8.A What was built: Stages 0 to 4, a model of Generate Image

**The rule that shaped it.** A native clip model of the engine is listed in the same model menu as the picture models,
shown on the same bar, rendered by the same Generate button and the same `generate_image` tool. The six tools and their
schemas did not change. There is no `hub/modules/generate_video/`, no second tab and no second job kind: the clip job's
kind is still `image` (`build.py:211`). Nothing in `hub/core`, `hub/worker` or `hub/modules` names a model; every fact is
read from the engine's definitions (`tests/engine/test_video_engine.py::test_core_and_worker_name_no_model`).

**The stages.**

| Stage | What it holds |
|---|---|
| 0 | The Stage 0 checks on the server (ffmpeg and ffprobe, the weight files, one clip made in the engine's own UI). The measured codec, tags, size and time are not on record. |
| 1 | The engine side, no UI: the catalog lists clip models with their facts; the clip task; `FORCED_VIDEO`; `land` to the clips root; the `clips` files root; `/files` with Range. |
| 2 | Clips shown in Media (the Clips section of the Media window); the size menu as tiers; count 1; Seconds per model in the Settings card; the job line "Done · clip in …". |
| 3 | Clips from the chat. Memory profile 4 pins about 40 GB of RAM on the first load, which lets the kernel take the engine child; profile 5 does not pin. systemd's default stops the whole unit on that event, so the unit has `OOMPolicy=continue`. The identity model cannot run text only. The 4-step and 8-step LoRA rule is checked against the model's step range. |
| 4 | A picture as the clip's first frame; identity references; the text encoder on the raised sheet. |

**Where each piece lives now.**

| Piece | Where |
|---|---|
| Clip models in the catalog (`kind`, `video`, `video_task`, `steps_range`; `SHAPE` 7, `catalog.py:21`) | `hub/worker/catalog.py:123-164`, `hub/worker/catalogvideo.py:196-235`; part 2, 2.10.1; part 5, 5.3.2 |
| The model as the bar sees it (offered tiers, `refCap` clamped to the bar's three boxes) | `hub/modules/generate_image/models.py:142-151`, `:180-199`; part 2, 2.10.2 |
| Roles of the reference boxes: start frame, identities | `catalogvideo.py:118-136`, `build.py:91-160`, `web/src/modules/generate-image/video.ts:101-107`; part 2, 2.10.3 |
| Size as a tier, aspect Auto snapping to the start frame, Seconds, the text encoder | `screen.py:67-80`, `models.py:173-178`, `video.ts`, `Card.tsx`, `library/LoraLibrary.tsx`; part 2, 2.10.4 |
| The clip task (one pass, the catalog's `one_pass`, the pictures) | `build.py:161-211`; part 2, 2.10.5 |
| Forced values for a clip (`audio_prompt_type ""`, the fork's `MMAudio_setting 0` or upstream's `postprocess_audio ""`, container mp4) | `FORCED_VIDEO` in the adapters (`hub/worker/adapters/fork.py`, `upstream.py`), `hub/worker/wgpconfig.py:18-20`; part 5, 5.2.3 |
| Landing an MP4 (tags cut, size and length read) | `hub/core/enginecat.py:119-160` (`land`), `hub/core/clip.py:40-65`; part 1, 1.5 |
| The clips root, `Files.kind`, no thumbnail, no move to the Drive | `hub/core/files.py:25-27`, `:121-133`, `:144`; part 1, 3.2 |
| Range playback; the path `/clips` serving the Media window | `hub/core/fileroutes.py:60-66`; `hub/core/web.py:64`; part 3, 3.9.4 |
| The `generation` item with `kind` and `seconds` | `hub/core/dispatch.py:173-186` |
| Memory profile per model kind; video sizes offered | `hub/settings.py:33`, `:40`, `hub/core/supervisor.py:67-71`, `web/src/shell/settings/CoreList.tsx:91-108`; part 1, 1.5 and 5.2 |
| `OOMPolicy=continue` | `deploy/hub.service:15` |

**What a clip model cannot do on this screen.** No guidance, count 1, no negative prompt, no audio choice (the clip keeps
the sound its model makes), no pictures at set times, no audio or video references (part 2, 2.10.6). Stages 5 to 7 added
what the first four lacked: a last frame, MP4 facts, a memory profile per model kind (Stage 5); Continue on a clip
and the Seconds step (Stage 6); Omni names, detail and cut-out (Stage 7).

**Debts on record:** the first-clip measurements are unrecorded; the size menu's megapixel-to-tier mapping
is a convenience; a clip and a picture share the engine lane, so each waits behind the other and each switch loads a model;
learned VRAM peaks are per model, not per size; progress shows no phase for decode, audio and mux; the Clips section has no
favourites, Drive or Characters (it has no groups one flat list, newest first); the "no longer available" text still says "image" for a
missing clip; `/files` sends `no-store` for clips.

---

## 8.B The roadmap: R6 to R9, Stages 5 to 10

The roadmap goes from one clip to short
films: a storyboard of cells, each a picture and the text of one clip, rendered into clips that play in order, with a
longer shot made of segments that continue each other. Each stage keeps the invariants of part 0 (§0.3). Its stages:

| Stage | Content | State |
|---|---|---|
| 5 | 5a start and last frame; 5b the one-pass fix; 5c MP4 facts; 5d the PNG text lift; 5e a memory profile per model and a tier setting | Built |
| 6 | Continue a clip with the engine's "V" route | Built. Its probe (`--probe-continue`) has not been run on the real engine, so `continue_max_seconds` (60) is a computed default |
| 7 | Omni: names, detail, cut-out | Built. The five Omni memory cases are unmeasured on the real card |
| 8 | A storyboard module (`hub/modules/storyboard/`, eight tools) | The core lifts (`named`, `temp`, `checks`, `clipplan`, the `Files` additions) are built. The module skeleton is built and off by default through `modules_disabled`. The storyboard web part is not built; its decisions are open, except where joins run, which is answered |
| 9 | An engine adapter seam | Steps 1 to 5 built: `--dump-engine`, `rebuild.py`, `engineapi.py`, the fork and upstream adapters, the contract test; the Hub's requests on the wire (`PROTO` 2) and the adapters building every task; the upstream adapter driving H3 on upstream's own terms (R16), held against the capture of upstream 18.05; the debts are in the roadmap |
| 10 | The Hub's own engine install, so the Hub no longer depends on the HocusPocus/Maestro install | BUILDING: upstream 18.05 installed beside the Hub and captured (steps 1 and 2); `install-engine.sh`, the hold on the weights, the page run and upstream's pre-check built (steps 3 and 4); the installer switches the engine only, the weights stay in the Settings folders; the install block is next |
| 11 | The sequence: an Edit Video tab, sequence files beside the clips, joins by ffmpeg in the engine's worker | BUILDING |

**Next.** Stage 10, the Hub's own engine (the requirement that the engine not depend on the
HocusPocus/Maestro install, part 5, 5.1.4 and 5.6.3); the storyboard web part with its open decisions, and Stage 11; and the
run on the engine host that the built stages wait on (the Continue probe; the `--dump-engine` capture of upstream is in).

The roadmap lists five decisions: the storyboard record (a Drive folder of numbered PNGs with each cell's text in
the PNG text field, or one JSON file); widening the PNG text exception from the Characters folder to the storyboards folder;
the default clip model for a storyboard; reversing the rule "no ffmpeg in the controller" for a last-frame read or a stream-copy
join; and the scope, since Stage 8 is a new module with new tools while the 2026-10-13 scope is "no new module, no new
tools" (Stages 5 to 7 stay inside it). Each stage names the research section it rests on, the files it lifts, its tests and its
memory cost. The four research notes, one paragraph each:

**R6 — every frame and reference kind the clip models accept, and how each would enter the Hub.** Read-only research that
ranks nine kinds for a short film, cheapest first: a start and a last frame in boxes 1 and 2; continuing a clip; Omni names,
detail and cut-out; scene, style and composition pictures; pictures at set times; video references; voice and sound
references; a control video with a mask; a last frame alone. Rows 1 and 2 chain shots and reuse the boxes as they are; the
rest each need a new control or a new kind of input file. It finds one correction to the code as of Stage 4: the Hub sends
its own box role word as the engine's `image_intent`, which coincides with a valid value by luck, so it proposes to omit the
intent while identity is the only one. It proposes one catalog shape for `video.references` (a role, `min`, `max`, and per
role the letters, limits and detail choices the definition announces, all read from the definition), boxes that may also
hold a clip, and a role per box that depends only on the model's role, the position and what the box holds, because the web
boxes are a dense list. It notes that the engine has one fit mode per task, not per picture, so the Hub keeps `crop`.
Unverified: the continuation window arithmetic and the peak VRAM of `max` detail, video references and continuation.

**R7 — longer scenes from segments that continue each other.** Compares two routes. Inside one job the engine chains
windows and carries pixels, audio history and prompt pacing across them, but the job holds the lane for the whole scene,
there is no review between windows, a cancel loses the rest, RAM grows with every window and every window writes a growing
file so only the last may land. Across separate jobs the engine's "V" route takes the previous clip as `video_source`, decodes
it whole and writes the joined file itself: the landed file is the whole source plus the new frames, so no stitching is needed.
The Hub must send a window of N + 17 frames and an overlap of 18, with chaining off, or the engine splits the job in two; the
scene then grows by N − 1 frames per step. Sound does not carry across jobs, so the draft restates the soundscape. VRAM does not
grow (only 18 tail frames enter the model); RAM grows with the scene, computed at about 37.6 MB per second at 540p and 64.9 MB
at 720p, so the scene length needs a cap from a measured peak. A start-frame route (the previous clip's last frame as the next
start) needs a decoder the controller lacks or a new worker message. It feeds Stage 6.

**R8 — a storyboard for short films.** Describes HocusPocus's Comic and Director flow: the shot list is one JSON that exists only
in the browser, and pictures reach video by a browser capture and upload. It proposes to take the cell contract (a first frame,
the motion text, seconds, a camera note, a cast) and the one-to-one rule between cells and clips, and to leave the canvas editor,
the planner, fusion and the joining step. The proposal: a storyboard is a Drive folder of numbered pictures, each cell's text in the
one PNG text field the Characters notes already use; a declarations-only module with no tab at first, whose tools list storyboards and
cells, make or move a cell, draw a cell's picture and render the storyboard by submitting `generate-image.image` one cell at a time on
`job.finished`; clips land in a group folder named after the storyboard (the skeleton's design; when the storyboard stage is built, the render instead writes the storyboard's order into a sequence of the same name, Stage 11, and no clip moves). It lists the lifts
this needs in core (the PNG text, a Drive put, plain-value checks, a clip-facts call, regroup with a name). It feeds Stage 8.

**R9 — independence from the fork.** Lists the surface the Hub uses on the engine: the `shared.api` calls, the private
attributes the worker reaches, the task keys, the definition fields, the forced config keys, the output-file contract and the
progress and error events, and marks each as present in the fork, upstream or both. Its first finding: the real fork publishes no
`*_multi_window` setting, so the catalog found no one-pass key and none was sent, while the fake engine held the key and the test
passed against a shape the fork lacks; the tree now reads the key from the engine's `generate_video` signature (8.A), and a capture
from the real engine (`main.py --dump-engine`) is to confirm it. It proposes an adapter seam: `hub/worker/engineapi.py` with
`ModelFacts`, `Request`, `Event` and an `Adapter` protocol, one adapter per engine flavour holding every engine key, a wire
`PROTO = 2` speaking Hub terms, a fake engine regenerated from a captured real dump and never edited by hand, and a test that
no engine key appears outside the adapters. It feeds Stage 9. Built: `engineapi.py`, the `fork` and `upstream` adapters, the
test that no engine key family appears outside them and no engine task key on the Hub's side (`tests/engine/test_rules.py`),
and `PROTO = 2` carrying the Hub's requests.

Later, each with a one-page note first: in-job multi-window for continuous sound, pictures at set times, video and audio
references, stitching independent segments, and the items carried from the plan's old list (scene and style pictures, a control
video and mask, the last frame alone, a mute option, VRAM peaks per model and size, a clips tree with favourites, a video tab or
tool switch if the shared screen gets in the way). The roadmap's risk list (R9 §5) names the engine drift that can break
the catalog reads: prompt letters, the Omni manifest shape, the fork-only switch, missing frame limits and tier tables upstream,
the text-encoder suffix rule, private engine attributes, side files from an engine, and a fake that pins belief rather than fact.

---

## 8.C The parked full module

The design below (sections 1 to 8) is the first plan: a module `hub/modules/generate_video/` with its own tab and tools,
core lifts (`hub/core/clip.py`, a media-kind table in `api.py`, server thumbnails, a separate video list and lanes) and a
staged plan from Stage 0 to an audio stage. The scope was then narrowed to 8.A; this file keeps the design as reference for later steps.

How to read it:

- **Taken into the code (8.A):** the catalog's video facts in the one model list with a `kind` (2.1, 1.3, 1.4); `land` to a
  clips root (2.5); the forced video values (2.6); the `clips` root (2.7); the `generation` item's `kind` (2.9); Media on
  another root (2.12); one pass per clip (1.4); `hub/core/clip.py` and blanked tags (2.4, 1.6); Stage 0 (6); references and a first frame (Stage 4).
- **Still parked:** the module and tab (3, 4); new tools (5.1); server thumbnails (2.8); the separate video list and lanes
  (2.2, 2.10); audio (Stage 5 of this design); a core lift of shared code (3.7, 4.2).
- **Dated.** Each "Fact" below predates the video work. Where a fact says the catalog keeps only
  `image_outputs` models, that `land` runs `clean.strip` on every output, that no video file can land, or that the
  boxes are struck through for video, it was true then and is not now; those lines are not rewritten. Where the code and
  this design differ, the code and 8.A are right. The "Proposed" marks still mean what they said: not built.
- The staged plan in section 6 is the parked module's. The stages that were built are the ones in 8.A, which keep their
  own numbers (0 to 4); the roadmap's numbering (5 to 9) is in 8.B.

The constraints that every Proposed item had to meet are unchanged: an expansion module on the existing pattern;
Generate Image and Media separate; the assistant handles what is outside a module's scope; modules import only
`hub.core.api` and their own package; Python files at most 300 lines, ts/tsx/css at most 250; no logs, no telemetry, no
metadata in outputs, nothing fetched; anything that may be set differently is a setting; no zombie code.

---

## 1. What H3 needs from the engine

### 1.1 Model ids

The engine's model id (`model_type`) is the file stem of the definition in `hp:defaults/`.

| model_type | Name in the file | Architecture | Notes |
|---|---|---|---|
| `minimax_h3` | "H3 First / Last — Pruned" (`hp:defaults/minimax_h3.json:22`) | `minimax_h3` | Text or first/last frame → video and stereo audio. 20 steps, 124 frames, 864x480 (`:28-34`) |
| `minimax_h3_full` | "H3 First / Last — Full" (`hp:defaults/minimax_h3_full.json:3`) | `minimax_h3_full` | 33B, two weight files bf16/int8 (`:8-9`) |
| `minimax_h3_fused_turbo` | "H3 Fused 4-Step — Frames (Experimental)" (`hp:defaults/minimax_h3_fused_turbo.json:24`) | `minimax_h3` | 4 steps, 243 frames, 1152x640 (`:71-76`). Steps 4–8 (`:48-49`). LoRAs disabled (`:46`). SLA attention (`:35-36`, `:79`) |
| `minimax_h3_legacy` | "H3 Legacy Quality — ConvRot" (`hp:defaults/minimax_h3_legacy.json:17`) | `minimax_h3_legacy` | "isolated ComfyUI runtime" sidecar (`:19-20`) |
| `minimax_h3_ref2va` | "H3 Omni — Pruned" (`hp:defaults/minimax_h3_ref2va.json:19`) | `minimax_h3_ref2va` | Ordered image/video/audio references (`:20`). `minimax_h3_references: []` (`:31`) |
| `minimax_h3_ref2va_full` | "H3 Omni — Full" (`hp:defaults/minimax_h3_ref2va_full.json:3`) | `minimax_h3_ref2va_full` | 33B Omni |
| `minimax_h3_ref2va_fused_turbo` | "H3 Fused 4-Step — References (Experimental)" (`hp:defaults/minimax_h3_ref2va_fused_turbo.json:3`) | `minimax_h3_ref2va` | Same 21 GB checkpoint as the Frames entry (`:6`) |
| `h3_advanced_fl2va`, `h3_advanced_fl2va_pruned`, `h3_advanced_ref2va`, `h3_advanced_ref2va_pruned`, `h3_advanced_vdn`, `h3_advanced_vdn_pruned` | "H3 Advanced …" (`hp:defaults/h3_advanced_*.json:3`) | `h3_advanced_*` | Separate family `h3_advanced` (`hp:models/h3_advanced/handler.py:14-15`). The VDN entries auto-load an 8-step LoRA (`hp:defaults/h3_advanced_vdn.json:14-22,26`) |

Fact: the `minimax_h3` handler declares the five base types `minimax_h3`, `minimax_h3_legacy`, `minimax_h3_full`,
`minimax_h3_ref2va` and `minimax_h3_ref2va_full`
(`hp:models/minimax_h3/minimax_h3_handler.py:8-12,1616-1624`). The `fused_turbo` entries reuse a base architecture
and set `minimax_h3_fused_turbo: true`.

Proposed (primitive): offer only `minimax_h3`, `minimax_h3_fused_turbo`, `minimax_h3_ref2va` and
`minimax_h3_ref2va_fused_turbo`.
- The Full variants appear only when their files are present (the catalog's own presence check).
- `minimax_h3_legacy` is never offered. It runs a separate ComfyUI process, and nobody has checked whether the
  worker's network seatbelt (`hub/worker/netguard.py:1-4`) covers that process. See §8.
- The `h3_advanced_*` family comes after Stage 5.
- The offered list is a module setting (`models_allowed`: id prefixes), default `["minimax_h3"]` minus legacy. So it
  is not hard-coded.

### 1.2 Inputs

| What | Engine key | Fact |
|---|---|---|
| Video, not image | `image_mode: 0` | `image_mode` is a `generate_video` argument (`hp:wgp.py:7252` signature). Generate Image sends `1` (`hub/modules/generate_image/build.py:250`) |
| Prompt | `prompt` | No negative prompt: `no_negative_prompt: True` (`hp:models/minimax_h3/minimax_h3_handler.py:1808`). No guidance control: `guidance_max_phases: 0` (`:1809`) |
| Text only | `image_prompt_type: ""` | Default in every H3 json (e.g. `hp:defaults/minimax_h3.json:37`) |
| First / last frame (FL2VA) | `image_prompt_type` ⊂ `"TSEV"`, `image_start`, `image_end` | `image_prompt_types_allowed: "TSEV"` for FL2VA and `""` for Omni (`…handler.py:1795`). `image_start` and `image_end` are `generate_video` arguments (`hp:wgp.py:7252+39,40`) |
| References (Omni / Ref2VA) | `minimax_h3_references: [{type, path, image_intent, character_name, role}]` | Validated by `hp:models/minimax_h3/reference_manifest.py:33-130`: at most 9 images, 3 videos, 3 audios, 12 in all (`:15-18`). Image intents: identity, scene, style, composition (`:24`). `character_name` is kept, up to 120 characters (`:84-87`) |
| Seed | `seed` | `generate_video` argument (`hp:wgp.py:7252+13`) |
| Steps | `num_inference_steps` | 20 by default (`hp:defaults/minimax_h3.json:30`). 4 for fused (`hp:defaults/minimax_h3_fused_turbo.json:71`) |
| Frames | `video_length` | See §1.4 |
| Resolution | `resolution: "WxH"` | See §1.3 |

### 1.3 Resolution tiers

Fact: the tiers are `_H3_RESOLUTION_PRESETS` (`…handler.py:439-524`), in the order 480p, 540p, 720p, 768p, 1080p
(`:525`). The model publishes them as `resolution_presets` and `resolution_preset_order` (`…handler.py:1831-1833`).
Sizes are multiples of 32 (`"block_size": 32`, `:1748`).

| Tier | 16:9 | 9:16 | 1:1 | 4:3 | 3:4 | 21:9 |
|---|---|---|---|---|---|---|
| 480p | 864x480 | 480x864 | 640x640 | 640x480 | 480x640 | 1120x480 |
| 540p | 960x544 (`:457`) | 544x960 | 736x736 | 736x544 | 544x736 | 1280x544 |
| 720p | 1280x704 | 704x1280 | 704x704 | 928x704 | 704x928 | 1632x704 |
| 768p (native) | 1344x768 | 768x1344 | 768x768 | 1024x768 | 768x1024 | 1792x768 |
| 1080p (experimental, `:506-508`) | 1920x1088 | 1088x1920 | 1088x1088 | 1440x1088 | 1088x1440 | 2528x1088 |

The fused entries default to 1152x640, which is not a preset tier (`hp:defaults/minimax_h3_fused_turbo.json:76`).
`_RESOLUTIONS` lists 1152x640 and 640x1152 as plain choices (`…handler.py:840-841`).

Proposed: the module reads tiers and aspects from the catalog (§2.1). It never keeps its own table.
- Module setting `tiers_offered`, default `["480p","540p","720p"]`. This keeps experimental 1080p and the heavy 768p
  away until turned on in Settings.
- Screen default: tier `540p`, aspect `16:9` (960x544).

### 1.4 Duration, fps and the frame lattice

Facts:
- fps is 24 (`…handler.py:1740`).
- The video VAE takes `17*n+5` frames. The minimum is 124 (≈5.17 s) and the one-pass maximum is 345 (≈14.375 s),
  in steps of 17 (`…handler.py:57-64,75,1744-1746`).
- The engine rounds a requested length **up** onto the lattice (`normalize_h3_clip_frame_count`,
  `…handler.py:220-245`).
- Clips longer than 345 frames continue through sliding windows (`"sliding_window": True`, `:1754`).
- There is an opt-in experimental limit of 719 frames (`hp:models/minimax_h3/duration.py:3-6`).

The legal one-pass lengths:

| frames | 124 | 141 | 158 | 175 | 192 | 209 | 226 | 243 | 260 | 277 | 294 | 311 | 328 | 345 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| seconds | 5.17 | 5.88 | 6.58 | 7.29 | 8.00 | 8.71 | 9.42 | 10.13 | 10.83 | 11.54 | 12.25 | 12.96 | 13.67 | 14.38 |

Proposed:
- The screen's `seconds` setting is a number. `write` snaps it up to the model's lattice, using `fps` and
  `frames_*` from the catalog, and reports back both `seconds` (exact) and `frames`.
- The primitive caps the length at the one-pass maximum (`frames_maximum`). So sliding windows, and their progress
  problem (§8), stay out of the first stages.
- The module sends `sliding_window_size = video_length`, so every clip is exactly one pass. Whether the engine needs
  this key is Unverified.

### 1.5 Steps and turbo presets

Facts:
- Pruned and Full default to 20 steps (`hp:defaults/minimax_h3.json:30`).
- Fused entries default to 4 steps, allow 4–8, and lock guidance (`hp:defaults/minimax_h3_fused_turbo.json:47-52,50`).
- The turbo presets are LoRAs listed in `hp:models/minimax_h3/turbo_presets.json`. They come from Hugging Face repo
  `larryvrh/MiniMax-H3-Turbo-Lora` (`:3`) at 6 steps (e.g. `:24,44`), and the workflow defaults are PDD 8-step
  (`:4-8`).

Proposed:
- Steps are per model. The model's default comes from the catalog. The bounds are `inference_steps_min/max` when
  the definition has them, otherwise the module's `STEPS` bound.
- Turbo presets are **not** in the primitive. They would need LoRA files the Hub must never fetch (§1.7). A later
  stage can offer them through the same LoRA library as images, if their files are already in a LoRA folder.

### 1.6 Output format

Facts:
- The container is `server_config["video_container"]`, default `mp4` (`hp:wgp.py:3482,9340-9342`).
- The codec is `video_output_codec`, default `libx264_8` (`hp:wgp.py:3481`). That maps to imageio-ffmpeg `libx264`,
  quality 8, yuv420p (`hp:shared/utils/audio_video.py:625-628`).
- H3 returns audio (`"returns_audio": True`, `…handler.py:1801`). The stereo track is muxed by an ffmpeg call with
  `-c:v copy` (`hp:shared/utils/audio_video.py:440-443`). The audio codec is `audio_output_codec`, default `aac_128`
  (`hp:wgp.py` in the mux call before 9474).
- The file goes to `save_path` (`hp:wgp.py:9349`). The worker points `save_path` at its outbox
  (`hub/worker/wan2gp.py:111`).
- So a clip is an **MP4: H.264 video + AAC stereo audio**, 24 fps.

What the file says about itself:
- With `metadata_type` `"none"` the engine writes no settings JSON into the file (`hp:wgp.py:9532-9545`). The Hub
  already forces this (`hub/worker/wan2gp.py:35`).
- Two encoder marks still reach the file:
  - the muxer's `encoder` tag (Lavf), in `moov/udta`;
  - x264's version-and-options SEI, in the first video sample.
  The SEI comes from the libx264 path (`…audio_video.py:627-628`). Both marks are Unverified until Stage 0's `strings`
  check (§6).

### 1.7 What the Hub must keep off

- **Downloads.** Every H3 definition lists Hugging Face URLs (e.g. `hp:defaults/minimax_h3.json:25-27`). Companion
  assets include the Qwen3-VL text encoder and the video and audio VAEs (`…handler.py:1838-1842`;
  `hp:defaults/minimax_h3_fused_turbo.json:63-68`).
  - Fact: the worker blocks outbound sockets and name lookups (`hub/worker/netguard.py:27-45`). A missing file
    therefore fails when the model loads.
  - Proposed: Stage 0 confirms every file is local. The model list shows only `available` models for video, not
    `partial`. Generate Image accepts both today (`hub/modules/generate_image/models.py:188`).
- **Prompt enhancer.** Already forced off: `enhancer_enabled: 0` and `prompt_enhancer: ""`
  (`hub/worker/wan2gp.py:35-39`). H3 also ships its own `prompt_enhancer.py`
  (`hp:models/minimax_h3/prompt_enhancer.py`). Proposed: Stage 0 confirms it does not run with
  `prompt_enhancer: ""`.
- **Embedded source images.** Already off: `embed_source_images: False` (`hub/worker/wan2gp.py:35`).

---

## 2. What changes in core

Each item lists the file, what exists (Fact), and the change (Proposed). The goal is the smallest change that lets a
module make, land, list, serve and show a clip, while keeping Generate Image and Media separate.

### 2.1 `hub/worker/catalog.py`: video models in the catalog

- Fact: the catalog keeps only models with `image_outputs` (`hub/worker/catalog.py:265`). The H3 model definition
  sets no `image_outputs` (`…handler.py:1738-1830`), so H3 never reaches the Hub today.
- Fact: the catalog entry has `defaults` (steps, guidance, resolution: `catalog.py:16,48`), `block`, `ref_choices`
  and LoRA fields (`:43-61`).
- Proposed: `build()` returns a second list, `video_models`. It is built by the same loop and the same `describe()`
  for definitions with `t2v_class` or `i2v_class` and no `image_outputs`. Each entry adds a `video` block:
  `{fps, frames: {min, step, max}, tiers: resolution_presets, tier_order, returns_audio, prompt_types (image_prompt_types_allowed), omni: bool, ref_images_max, steps_range}`.
  - The `models` list is unchanged, so Generate Image and the Image models panel (`definitions.weights(…,
    image_types)`, `hub/worker/wan2gp.py:164-165`) are unaffected.
  - The file grows by ~25 lines (157 → ~182).
- Test: `tests/engine/test_worker.py` gains a fake `wgp` with one `t2v_class` definition. It asserts the definition
  is in `video_models` and not in `models`.

### 2.2 `hub/core/engine.py` and `api.Engine`: asking for the video list

- Fact: `query("models")` returns the catalog plus the resident model (`hub/core/engine.py:193-217`). The catalog is
  cached on disk under a key that follows the engine and its folders (`hub/core/enginecat.py:29-43`).
- Proposed: no new question. `query("models")` already returns the whole catalog dict, so `video_models` rides
  along, and the cache key needs no change.
- Proposed: add `Engine.last(what) -> dict | None` to `api.Engine` (`hub/core/api.py:246-248`). It returns the most
  recent answer, synchronously, for job builders, which are synchronous (`api.py:135`).
  - Generate Image keeps its own `_last` copy for exactly this reason
    (`hub/modules/generate_image/models.py:35-47`). Generate Video would copy it.
  - With the lift, Generate Image's `_last`, `catalog()` and `cached()` are removed, so no zombie code is left.

### 2.3 `hub/core/api.py`: media kinds in one place

- Fact: `Kind` already includes `"video"` (`api.py:15`), and the registry accepts it for socket groups
  (`hub/core/registry.py:21`).
- Fact: the image suffixes are written twice:
  - `IMAGE_TYPES` in core (`hub/core/files.py:24`);
  - `IMAGES` in Media (`hub/modules/media/library.py:23`).
- Proposed: one table in `api.py`:
  `MEDIA_TYPES: Mapping[str, tuple[Kind, str]] = {".png": ("image","image/png"), …, ".mp4": ("video","video/mp4")}`.
  - `files.py` and Media's `library.py` both read it, and their own tuples go.
  - `.webm` is not added: wgp writes the container from config (`hp:wgp.py:9347`) and §2.6 forces `mp4`.
- Proposed `api.Files` additions. `existing_image` stays, for references, which must be pictures.
  - `existing_media(item_id) -> Path`: an image or a video file.
  - `size(item_id) -> tuple[int, int] | None`: width and height. Pillow reads images; §2.4's box reader reads MP4.
    - This also centralizes four copies of "open with Pillow, read the size":
      `hub/modules/generate_image/cast.py:40`, `hub/modules/generate_image/routes.py:224`,
      `hub/modules/media/library.py:92` and `hub/core/enginecat.py:153`.
- Proposed: a docstring on `LaneKind` (`api.py:19`) saying "image" means *the Wan2GP engine lane*. The literal stays
  as it is (§2.10).
- Budget: `api.py` is 254 lines. These additions and §2.9's draft protocol add ~30 lines, which stays under 300.

### 2.4 New `hub/core/clip.py` (stdlib, ~150 lines): a clip is its pictures and sound

- Fact: `land()` runs `clean.strip` on every output (`hub/core/enginecat.py:145`).
  - `clean.py` handles only PNG, JPEG and WebP (`hub/core/clean.py:19-24`) and opens files with Pillow (`:45,53`).
  - On an MP4 it raises. `land` then deletes the file and fails the job with "The engine wrote a picture the hub
    could not read" (`enginecat.py:146-148`).
  - The size read in `land` (`:138`) also uses Pillow.
- Proposed `clip.py`, an ISO-BMFF box walker in pure Python (no ffmpeg in the controller). It does three things:
  1. `strip(path)`:
     - Overwrites `moov/udta`, `moov/meta` and every `trak/udta` and `trak/meta` with `free` boxes of the same size,
       with the payload zeroed. Because the size does not change, `stco`/`co64` chunk offsets stay valid, wherever
       `moov` sits.
     - Zeroes the creation and modification times in `mvhd`, `tkhd` and `mdhd`.
     - Overwrites the payload text of any H.264 SEI *user_data_unregistered* message (NAL type 6, payload type 5)
       in the first video sample with spaces, keeping lengths. The UUID stays. Decoders ignore this payload.
     - Refuses (`ValueError`) anything without `ftyp` + `moov` + `mdat`.
  2. `size(path)`: width and height from the video `tkhd` (16.16 fixed point).
  3. `seconds(path)`: `mvhd` duration / timescale. Media uses it for the tile badge.
- Tests (`tests/core/test_clip.py`): the test builds a tiny synthetic MP4 in memory (ftyp, moov(mvhd, trak(tkhd,
  mdia(mdhd, …)), udta(meta(ilst ©too "Lavf…"))), mdat with one AVCC sample holding an SEI). It asserts:
  - size and offsets are unchanged;
  - no `udta` or `Lavf` bytes remain;
  - the SEI text is blank;
  - w, h and seconds are read correctly;
  - a non-MP4 is refused.
- Alternative (Proposed B): the worker remuxes in the outbox with the engine's ffmpeg
  (`-map_metadata -1 -bsf:v filter_units=remove_types=6 -c copy -movflags +faststart`). It is simpler, but the
  outcome then depends on the engine's ffmpeg, and core cannot check it. The recommendation is A, with B as optional
  `+faststart` later if seeking is slow.

### 2.5 `hub/core/enginecat.py`: `land`

- Fact: `land(src, outbox, outputs)` checks the file is inside the outbox (`:110-112`). It then cleans the file,
  names it by the time (`temp_path`, `hub/core/files.py:35-46`), moves it, and returns `(id, w, h)` (`:109-139`).
- Proposed: branch on `MEDIA_TYPES[suffix]` (§2.3):
  - image → `clean.strip` and a Pillow size, as now;
  - video → `clip.strip` and `clip.size`;
  - any other suffix → refused with "The engine wrote a file the hub does not take".
- The time name and the `out/<day>/HHMMSS-mmm.mp4` layout stay. `sweep` (`:100-106`) already removes what wgp leaves
  in the outbox (`*_tmp.mp4`, the temporary wav: `hp:wgp.py:9414,9443-9456`).

### 2.6 `hub/worker/wan2gp.py`: `translate`, `FORCED_CONFIG` and `FORCED_TASK`

- Fact: `FORCED_CONFIG` pins `image_output_codec`, `metadata_type: none`, the enhancer, plugins, crash queue and
  `embed_source_images` (`:35-35`). `FORCED_TASK` empties the enhancer, negative and alt prompts and sets
  `output_filename: "{date}-{seed}"` (`:38-39`).
- Fact: `translate` puts the model's factory settings under the Hub's settings on the legacy flavour, which is what
  HocusPocus is (`:44-57`). So H3's `sliding_window_*` and other defaults come from the definition unless the task
  sets them.
- Proposed `FORCED_CONFIG` addition: `"video_container": "mp4"`. Landing takes only MP4, so an engine config set to
  `mkv` must not break video.
- Proposed: the codec (`video_output_codec`) and the audio codec stay the **engine config's**. They are seeded from the
  engine's `wgp_config.json` (`:146-158`) and never hard-coded by the Hub. The risk of x265 not playing in the
  browser is in §8.
- Proposed `FORCED_TASK` additions, applied to every task, since none apply to image tasks:
  - `"MMAudio_setting": 0`. MMAudio would be a second audio model and a download (`hp:wgp.py:9336`).
  - `"minimax_h3_extended_duration": False` (`hp:models/minimax_h3/duration.py:12`).
  - The key names are confirmed in the engine source cited. Whether forcing them has any effect on image models is
    Unverified (they should be ignored).
- `translate` needs no video branch. The module sends `image_mode: 0`, `video_length` and the rest explicitly, and
  `fps` comes from the model (`force_fps` left unset).
- Fact: the worker emits one `output` event per generated file (`:283-287`). That already covers an MP4.

### 2.7 `hub/core/files.py`

- `kind()` (`:130-131`) returns `"image"` only. Proposed: `MEDIA_TYPES[suffix][0]`.
- `delete`, `move` and `regroup` call `existing_image` (`:171,168,187`), so a clip could not be deleted, favorited
  or moved. Proposed: these three use `existing_media`. Characters stay images
  (`hub/core/characters.py:1-13`).
- `thumbnail()` (`:238-243`) stays image-only. A video thumbnail request fails at `existing_image` → `Invalid` → 404
  (`hub/core/fileroutes.py:68-73`). §2.8 explains why that is acceptable.
- Line budget: 243 → ~260.

### 2.8 Thumbnails for video

- Fact: `thumbs.render` decodes only what Pillow can open (`hub/core/thumbs.py:65-85`). It cannot decode H.264.
  Thumbnails live only in memory (`thumbs.py:1-5`).
- Proposed (Stage 3): **no server thumbnail for a clip.**
  - Media's tiles show a clip with `<video muted preload="metadata" playsinline src=url#t=0.1>`, which is a poster
    frame drawn by the browser from the file itself.
  - Nothing is written anywhere, and the controller needs no decoder.
  - `thumb` is `null` for a clip in every item shape (§2.9, §2.12).
- Proposed (later, optional): the worker can hand a 336 px WebP of a mid frame, as base64, inside the `output` event,
  well under the 1 MiB line limit (`hub/worker/protocol.py:26`). `land` then puts it in `ThumbStore` under the clip's
  key (`thumbs.py:56-62`). It is memory-only like every thumbnail and is lost on restart, when the `<video>` poster
  takes over again. Only worth doing if tiles of many clips prove slow.

### 2.9 `hub/core/dispatch.py`: the `generation` item

- Fact: `_ev_output` drops any item whose `files.kind` is None (`:213`). It then publishes
  `{"id", "kind": "image", "url", "thumb", "w", "h", "created", "job"}` on the `media` lane (`:217-221`).
- Proposed: `"kind": self.files.kind(item)`, `"thumb": None` for video, and `"seconds"` for video (read by
  `clip.seconds` in `land` and passed in the event).
- The web type `GenerationItem` already has `kind: string` (`web/src/lib/protocol.ts:56-59`). It gains
  `seconds?: number`.
- Test: `tests/core/test_jobs.py` (or a new `test_dispatch_output.py`). A fake lane emits an `output` with an `.mp4`
  item. Assert one `generation` with `kind: "video"` and `thumb: null`.

### 2.10 Lanes and the job kind

- Fact: the job kind is registered as `<module id>.<kind>` (`hub/core/runtime.py:125-126`). A module's bare kind
  means its own (`hub/core/context.py:72-77`), so `jobs={"video": …}` becomes `generate-video.video`.
- Fact: `JobBook.submit` picks a lane whose `kind == plan.lane_kind`. It prefers one where the model is resident,
  otherwise the shortest queue (`hub/core/jobs.py:78-82`).
- Fact: there is one engine lane per GPU marked `engine` (`hub/core/engine.py:275-287`).
- Fact: one engine session runs one job at a time ("already has a generation in progress",
  `hp:shared/api.py:324`).
- Proposed: video jobs use the **existing engine lane** (`lane_kind="image"`). A second lane on the same GPU would be
  a second worker competing for the same VRAM, which is what the VRAM manager exists to prevent.
- Consequence (Fact, `hub/core/dispatch.py:1`): head-of-line blocking is deliberate. An image job queued behind a
  multi-minute clip waits, and every switch between an image model and H3 is a full unload/load. See §8.
- Proposed (only if later asked for): rename the literal to `"engine"` in `api.py` with the lead, in one
  commit touching `api.py:19`, `engine.py:34`, `hub/core/routes.py:84` and both builders.

### 2.11 `hub/core/jobs.py`: card titles

- Fact: a job's title is `plan.summary["title"]` when set, otherwise "N image(s) · model" (`hub/core/jobs.py:172-173`).
- Proposed: **no core change.** The video builder sets `summary["title"]`, e.g. `"Clip · 5 s · H3 First / Last — Pruned"`.

### 2.12 Media (module, not core) and the Media screen

- `library.py`:
  - Fact: `rel_of`, `ids` and `is_media` accept image suffixes only (`hub/modules/media/library.py:33-48,53-63`).
  - Fact: `describe` opens files with Pillow and sets `"kind": "image"` (`:84-100`).
  - Proposed: `rel_of`/`ids` use `MEDIA_TYPES` from `hub.core.api`. `describe` uses `ctx.files.kind/size` and adds
    `"kind"`, `"seconds"` (video) and `"thumb": null` (video).
  - With this, `is_media` covers clips with no further change, and favorites, move and delete work through §2.7.
- Web:
  - Fact: `MediaItem` has no `kind` (`web/src/screens/media/media.ts:10`).
  - Fact: tiles are `<img src={it.thumb}>` (`web/src/screens/media/Grid.tsx:107`).
  - Fact: the Stage is an `<img>` with zoom and pan (`web/src/screens/media/Stage.tsx:123-133`), mounted at
    `web/src/screens/media/Media.tsx:163`.
  - Proposed:
    - `MediaItem` gains `kind` and `seconds?`.
    - A new `screens/media/Clip.tsx` (~60 lines) shows `<video controls loop playsinline>`, fitted like the Stage, with
      no zoom.
    - `Media.tsx` picks `Clip` or `Stage` by `current.kind`.
    - The Grid tile renders `<video>` for a clip, with a duration badge.
    - `Stage.tsx` itself is unchanged.
  - Fact: sending a clip to Generate Image's reference sockets is refused by delivery, because the item's kind is
    not in the socket's `accepts` (`hub/core/delivery.py:108`; `hub/core/bus.py:277-278`).
- Serving:
  - Fact: `/files/{item}` serves only `existing_image` files with an image media type (`hub/core/fileroutes.py:60-65`).
  - Proposed: `existing_media`, with the type from `MEDIA_TYPES`.
  - Starlette is 1.7.0 (`requirements/controller.lock:20`). Its `FileResponse` answers HTTP Range requests, which a
    `<video>` needs to seek. Unverified on this exact version: Stage 1 has a test that sends `Range: bytes=0-99` and
    expects 206.

### 2.13 Progress for a clip

- Fact: `enginecat.progress` turns step/steps into a fraction that never goes back (`hub/core/enginecat.py:72-79`).
  The dispatcher's ETA counts `(task-1)*steps+step` (`hub/core/dispatch.py:154-163`).
- Fact: the engine session tracks `window_no` and `total_windows` (`hp:shared/api.py:313-314`). The worker forwards
  only phase, step, steps, pct and status (`hub/worker/wan2gp.py:212-213`).
- For a one-pass clip (the primitive), steps run once. The bar fills during denoising, then stays near 100% through
  VAE decode, audio decode and muxing, which carry no steps. That is acceptable; the phase text shows "decoding".
- Proposed (only with sliding windows, after Stage 5): the worker folds the window into the step count
  (`step' = (w-1)*steps + step`, `steps' = W*steps`). Core is unchanged.

### 2.14 Settings

- Fact: a module's defaults currently live in core: `DEFAULTS["modules"]["generate-image"]` (`hub/settings.py:34`),
  merged and validated at `hub/settings.py:174-180`. The module reads them read-only through `ctx.settings`
  (`hub/core/api.py:254`).
- Proposed: Generate Video keeps its defaults in its own package (`screen.py` `DEFAULTS`), merged under
  `ctx.settings`, and validates them itself at `start`.
  - This keeps core from naming the new module and needs no change to `hub/settings.py`.
  - Whether to move Generate Image's `ref_caps` the same way is the lead's call. It would remove the only
    module name in core settings.

### 2.15 What core does **not** get

- No video lane.
- No ffmpeg in the controller.
- No thumbnail files.
- No `video` flag in `JobPlan`.
- No new bus lanes: the module publishes its own `generate-video.changed`, like Generate Image's `changed`
  (`hub/modules/generate_image/manifest.py:33`).

---

## 3. The module: `hub/modules/generate_video/`

### 3.1 Files (Proposed)

| File | ≈Lines | Role |
|---|---|---|
| `__init__.py` | 1 | |
| `manifest.py` | 50 | `MODULE` |
| `models.py` | 90 | Video models as the UI and MCP see them, from `catalog["video_models"]`: offered, present, label, tiers, lattice |
| `screen.py` | 230 | Settings, bounds, `DEFAULTS`, `read`, `view`, `apply` |
| `cast.py` | 50 | References by character name. Only module policy (box count, model cap); lookup and size are core |
| `build.py` | 120 | `video_job(params, ctx) -> JobPlan` |
| `routes.py` | 120 | `/models`, `/draft` (GET/PUT), `/defaults`, card |
| `tools.py` | 90 | `SCREEN`, `LISTINGS`, `ACTIONS` |

### 3.2 `manifest.py` (Proposed)

```python
MODULE = Module(
    id="generate-video", title="Generate Video",
    tab=Tab(label="Generate Video", order=20),
    lanes=("changed",),
    sockets=(SocketGroup("reference", "Reference", ("image",), 3),),
    routes=(Route("GET", "/models", routes.get_models),
            Route("GET", "/draft", routes.get_draft),
            Route("PUT", "/draft", routes.put_draft, body_limit=262_144),
            Route("GET", "/defaults", routes.get_defaults),
            Route("PUT", "/defaults", routes.put_defaults)),
    jobs={"video": build.video_job},
    card=Card(title="Generate Video", order=890, state=routes.card),
    listens={"session.ended": routes.on_session_ended, "chat.cleared": routes.on_chat_cleared},
    screen=tools.SCREEN, listings=tools.LISTINGS, actions=tools.ACTIONS,
    start=start)
```

- Tab order 20 puts it after Generate Image (order 10, `hub/modules/generate_image/manifest.py:32`). Card order 890
  sits between Generate Image 880 and Network 900 (`hub/core/api.py:65`).
- `listens` uses the events Generate Image already hears (`hub/modules/generate_image/manifest.py:48`).
  `chat.cleared` is emitted by the assistant module as a core event (`hub/modules/assistant/chat.py:51`), so this
  creates no import.
- No `/weights` routes. Video weights are not offered in the Image models panel.
- No `/characters` route. §3.7 lifts it into core.

### 3.3 `screen.py`: the settings (Proposed)

| Setting | Kind | Bounds / choices | Where it lives | Text |
|---|---|---|---|---|
| `draft` | text | `hi=MAX_PROMPT` (4000) | session | "The assistant's draft prompt, shown beside the chat" |
| `model` | choice (live) | — | disk | "Id of the video model, as list_video_models lists it" |
| `seconds` | number | `lo=1, hi=60` (the module's; `write` snaps to the model's lattice and limit) | disk | "Length of the clip in seconds, rounded up to the model's frame grid" |
| `resolution` | choice (live) | the model's offered tiers | disk | "Resolution tier, as list_video_models lists it" |
| `aspect` | choice | `16:9, 9:16, 1:1, 4:3, 3:4, 21:9` (the tier table's keys) | disk | "Shape of the clip" |
| `steps` | integer | `lo=1, hi=100`; the model's range is checked in `write` | disk, per model | "Steps the model runs" |
| `seed` | seed | `lo=0, hi=SEED_MAX` | disk, per model | "Seed of the clip" |
| `references` | names | `hi=3` (the module's `BOXES`) | session | "Reference pictures 1-3 by character name, as list_characters lists them; [] empties them" |

- No `guidance` (H3 has no guidance phases, §1.2).
- No `loras` in the primitive (§1.5).
- No `count`. One clip per press; a count is a later setting.
- Proposed `DEFAULTS`, overridable in `settings.json` → `modules.generate-video`:
  `{"models_allowed": ["minimax_h3"], "models_excluded": ["minimax_h3_legacy"], "tiers_offered": ["480p","540p","720p"], "seconds": 5, "resolution": "540p", "aspect": "16:9", "only_available": true}`.
- `view()` reports what a press would render: `model`, `model_name`, `seconds`, `frames`, `width`, `height`,
  `steps`, `seed`, `last_seeds`, `references`, and `audio: true` (H3 always makes sound, §1.6).

### 3.4 `build.py`: the JobPlan (Proposed)

```python
def video_job(params: dict, ctx: Ctx) -> JobPlan:
    model = models.find(ctx.engine.last("models"), params.get("model"))   # §2.2
    # checks: model offered and available; prompt 1..MAX_PROMPT; seconds -> frames on the model's lattice;
    # tier+aspect -> "WxH" from the model's own tier table; steps within the model's range; seed drawn here if random;
    # references: absolute paths of existing images, at most the model's cap.
    task = {"model_type": model["id"], "image_mode": 0, "prompt": prompt, "resolution": f"{w}x{h}",
            "video_length": frames, "sliding_window_size": frames, "num_inference_steps": steps,
            "seed": seed, "batch_size": 1, "multi_prompts_gen_type": "FG",
            "activated_loras": [], "loras_multipliers": "", "image_prompt_type": ""}
    # Stage 4: FL2VA first frame -> image_prompt_type "S", image_start [path];
    #          Omni -> minimax_h3_references [{type: "image", path, image_intent: "identity", character_name}]
    summary = {"title": f"Clip · {secs:g} s · {label}", "prompt": prompt, "model": label, "model_id": model["id"],
               "seconds": secs, "frames": frames, "width": w, "height": h, "steps": steps, "seed": seed}
    return JobPlan("image", model["id"], (task,), summary)
```

- Every value is sent explicitly, as in Generate Image (`hub/modules/generate_image/build.py:1-7`).
- The last seed is kept in memory only, as `generate_image/build.py:267` does.
- Unverified: whether `image_start` is a path or a list of paths in this fork's `generate_video`
  (`hp:wgp.py:7252+39`). Stage 4 settles it against the engine.

### 3.5 `tools.py` (Proposed)

- `SCREEN = Screen(settings=screen.SETTINGS, read=read_settings, write=write_settings)`. The core publishes it as
  `get_generate_video_settings` and `set_generate_video_settings` (`hub/core/features.py:66-79`).
- `LISTINGS = (Listing("video_models", "Video models that can run, with their lengths, resolutions and default steps.", {}, list_video_models),)`
  is published as `list_video_models` (`features.py:82-86`).
- `ACTIONS = (Action("generate_video", "Render the draft as a clip with the screen's settings, as the Generate button does.", NO_ARGS, generate_video),)`.
  It returns `{state}`, exactly like `generate_image` (`hub/modules/generate_image/tools.py`).
- The registry refuses a tool name used twice and any description over 200 characters or without a final period
  (`hub/core/registry.py:115-118`). The texts above meet both.

### 3.6 `routes.py`: the draft, on disk and in the session (Proposed)

- Same split as Generate Image (`hub/modules/generate_image/routes.py:3-8,25-29`):
  - **on disk** (`draft.json` in `<data>/generate-video/`): `model`, `seconds`, `resolution`, `aspect`,
    `advancedByModel` ({steps, seed});
  - **session** (memory): `prompt`, `draft`, `references`, `selected`.
- `session.ended` forgets the session part. `chat.cleared` empties `prompt` and `draft`.
- The `draft` setting is refused when no window is open, as `generate_image/screen.py:223-232` does.

### 3.7 Shared through core, and duplicated by design

The rule: a module may import only `hub.core.api` and its own package (`tests/core/test_rules.py:57-64`;
`tests/engine/test_rules.py:40-46`). So anything both generate modules need either lives behind `api.py` or is
written twice. Writing it twice is forbidden, so each such piece is lifted.

| Need | Today (Fact) | Proposed lift |
|---|---|---|
| Name → character picture | Core `Files.character(name)` (`api.py:220`), used by `cast.py:87` | Already shared. No change |
| Picture size | Four Pillow copies (§2.3) | `Files.size(item_id)` in core |
| Characters list for Tab completion (name, id, w, h, thumb) | `GET /api/generate-image/characters` (`generate_image/routes.py:217-230`), and Media's own list with notes (`media/routes.py:150-161`) | Core route `GET /api/characters` in `hub/core/fileroutes.py`, next to `/api/media/check`. Generate Image's route is deleted. Media keeps its list (it adds notes and their editing) but builds it on `Files.size` |
| `list_characters` MCP tool | Declared by Generate Image (`generate_image/tools.py:90-91`). A tool name may exist once (`registry.py:115`) | Move the `Listing("characters", …)` to **Media**, which owns the Characters screen (`media/manifest.py:22-26`). Both generate modules name it in setting texts, and neither imports the other. Alternative: core publishes it. Core publishes no tools today (`runtime.py:129-130`), so the Media move is the smaller change |
| Draft split (disk fields + session fields, settle, merge-PUT, `session.ended`, `chat.cleared`) | ~70 lines in `generate_image/routes.py:25-58,134-151` plus `session_part` used by `screen.py`, `cast.py`, `build.py` | A core service `ctx.draft(saved=(…), session=(…)) -> Draft`, with `get() / put(part) / session() / clear(fields) / settle()`, implemented in `hub/core/draft.py` (~90 lines), with a `Draft` protocol in `api.py`. Core drops the session parts on `session.ended` by itself. Generate Image migrates in the same stage (no zombie) |
| Plain-value checks (whole number in bounds, seed "random"/number) | `_int`, `_number`, `_seeds` in `generate_image/build.py:26-35` and `_whole`, `_seed` in `screen.py:119-133` | `api.whole(value, field, lo, hi)`, `api.number(…)`, `api.seed_of(value, hi)` as pure functions in `api.py` (stdlib). The bounds stay each module's (`api.py:73-79`) |
| Catalog copy for the sync builder | `models._last` (`generate_image/models.py:35-47`) | `Engine.last(what)` (§2.2) |
| Engine reason line, 503 shape | `models.reason`, `routes.unavailable` (`generate_image/models.py:50-52`, `routes.py:71-73`) | Leave in each module. It is two lines of module wording, not shared logic |
| Model presence | `models.present` (`generate_image/models.py:186-189`) | Leave. Video filters differently (available only, allowed prefixes) |

Duplication that remains by design (Proposed): `cast.py` box policy (count, per-model cap), the `view()` shape, and
the screen bounds. These are each module's own facts. Two modules having similar *policy* is not shared logic.

---

## 4. The web module: `web/src/modules/generate-video/`

### 4.1 What exists and how it is coupled (Fact)

- Tabs are found by `import.meta.glob('../modules/*/manifest.ts')` (`web/src/shell/registry.ts:4`). A module may
  import only react, `ui/`, `lib/` and its own folder (`web/tests/unit/guards.test.ts:71`). Files are at most 250
  lines (`guards.test.ts:22`).
- Generate Image's parts and what ties them to its own store:
  - `run/BarMenu.tsx` imports only `ui/Popover`, `ui/cx` and `./Run.module.css` (`:1-4`). It is store-free and can
    be lifted as it is.
  - `run/Slots.tsx` reads `draft`, `edits` and `inputs` (`:2-11`). Only its inner `Slot` (`:24-44`) is presentational.
  - `chat/Article.tsx` (the page turner) reads `draft`/`edit` (`:4`).
  - `chat/Chat.tsx` and `chat/assistant.ts` hold the chat store and New chat. New chat calls this module's
    `clearWords`/`settled` (`chat/assistant.ts:10,42-45`). The chat column is mounted only in Generate Image
    (`GenerateImage.tsx:78`).
  - `compose/complete.ts` fetches `/api/generate-image/characters` (`:14-15`). `compose/PromptBox.tsx` ties
    completion to the chat, LoRA triggers and the reference boxes (`:5-13`).
  - `draft.ts`: the debounced field-merge store with session handling (`:11-94`). It is generic apart from the
    `generate-image.draft` event name (`:94`) and its types.
  - `run/jobs.ts`/`run/Queue.tsx`: the queue for this tool (`TOOL`), worded in images (`run/jobs.ts:1-12`).
- Existing coupling to note: the shell's Settings → Image models imports Generate Image internals
  (`web/src/shell/settings/ImageModels.tsx:4-6`). Generate Video must not repeat this pattern.

### 4.2 The lift list (Proposed; each lift moves code, and Generate Image switches to it in the same commit)

| # | From (generate-image) | To | Shape after the lift |
|---|---|---|---|
| W1 | `run/BarMenu.tsx` + its classes from `run/Run.module.css` | `ui/BarMenu.tsx`, `ui/BarMenu.module.css` | Unchanged API |
| W2 | `run/Slots.tsx` inner `Slot` | `ui/RefSlot.tsx` | Props: `thumb, badge, label, open, lit, onRemove, onDrop` |
| W3 | `chat/Article.tsx` | `ui/Pager.tsx` | Props: `text, onClear` |
| W4 | `chat/assistant.ts` + `chat/Chat.tsx` (+css) | `lib/assistant.ts`, `ui/Chat.tsx` | `lib/assistant.ts` owns the chat store and `say()`, plus `onNewChat(fn: () => Promise<void>)`. Each module registers its `clearWords`+`settled`. The chat column is then mounted by both tabs. The server side already broadcasts `chat.cleared` to every module |
| W5 | `draft.ts` | `lib/draftStore.ts` | `createDraft<T>({load, save, event, sessionKeys, empty})` returns `{store, ready, edit, load, settled, clearWords}`. Generate Image's `draft.ts` shrinks to its config |
| W6 | `compose/complete.ts` + `compose/Picker.tsx` | `lib/characters.ts`, `ui/NamePicker.tsx` | URL → core `/api/characters` (§3.7) |
| W7 | `run/jobs.ts` (queue view) | `lib/queueView.ts` | Parameterized by `tool` and a `noun(n)` |
| W8 | `run/Seed.tsx` presentational part | `ui/SeedField.tsx` | Value, last seeds, and onChange |

`PromptBox.tsx` is **not** lifted whole: its LoRA trigger highlighting (`compose/triggers.ts`) is image-specific.
Generate Video gets its own small `Compose.tsx` built from W4, W6 and `lib/keys`.

### 4.3 New in Generate Video (Proposed)

| File | ≈Lines | Role |
|---|---|---|
| `manifest.ts` | 10 | `id: 'generate-video'`, `order: 20`, `load`, `queue` |
| `GenerateVideo.tsx` | 80 | Layout as Generate Image: Pager (the assistant's draft) + Compose on the left, Chat + bar on the right |
| `api.ts`, `types.ts`, `draft.ts` (config over W5), `edits.ts`, `job.ts` | 30–80 each | `job.ts`: the pure payload of one press (as `generate-image/job.ts:53-80`) plus lattice snapping, which mirrors `screen.py` |
| `run/VideoBar.tsx` | 90 | Model, tier (W1), aspect (W1), **Duration**, steps, seed (W8), reference boxes (W2), Generate |
| `run/Duration.tsx` | 50 | Steps through the model's legal lengths (5.2 s … 14.4 s). Shows seconds and frames on hover |
| `run/ClipPreview.tsx` | 50 | The last clip of this tool (from the job's `outputs`), as `<video controls loop muted>` above the bar. Media remains the place clips are browsed |

### 4.4 Media's Clip view

See §2.12: `screens/media/Clip.tsx` and the Grid tile. These belong to the Media screen, not to the video module.
Media shows what lands. It knows nothing about H3.

---

## 5. The assistant contract

### 5.1 Tools (Proposed, all generated by core from declarations; `hub/core/features.py:1-7`)

| Tool | From | Returns |
|---|---|---|
| `get_generate_video_settings` | `Screen.read` | The `view()` of §3.3 |
| `set_generate_video_settings` | `Screen.write` | The settings after, or `Invalid{field,text}`, e.g. "seconds: H3 First / Last — Pruned makes 5.2 to 14.4 seconds" |
| `list_video_models` | `Listing("video_models")` | `[{id, name, seconds: {min, max, step}, tiers: [...], steps, references: n, loaded}]` |
| `generate_video` | `Action` | `{state}`. The clip lands in Media |
| `list_characters` | moved to Media (§3.7) | Unchanged for the assistant |

### 5.2 Routing (Proposed text for the Open WebUI system prompt)

- Fact: the Hub sends the conversation as it is. Open WebUI applies its own model and system prompt
  (`hub/modules/assistant/chat.py:1-5`). Tool descriptions are factual labels that never say when to call
  (`hub/core/features.py:4-6`). **The Hub injects nothing**, and that stays so.
- Lines like these go into the system prompt in Open WebUI. This is example wording, not Hub code:

> A *clip*, *video*, *animation* or *shot* request uses the Generate Video tools: write the prompt with
> `set_generate_video_settings` (`draft`, and `references` by character name from `list_characters`), then call
> `generate_video` only when the chat message asks to render. A *picture*, *image* or *photo* request uses the Generate Image tools
> the same way. Ask when unclear.

- Example: "make a clip of Character 1 flying over the city"
  1. `list_characters` (Character 1 is listed).
  2. `set_generate_video_settings({draft: "...", references: ["Character 1"]})`. The window shows the draft; the
     reference box fills.
  3. `generate_video` if the system prompt's rule says to render at once.
  4. The job card shows "Clip · 5 s · …". The clip lands in Media.
- In the primitive, a reference picture on an FL2VA model means *first frame*, and on an Omni model it means
  *identity*. `view()` and `list_video_models` state which one applies (`references_as: "first frame" | "identity"`),
  so the assistant can explain it.

---

## 6. Staged plan

### Stage 0 — verify on the server (read-only; no Hub change)

Engine root: `<prefix>/engine/app`, or the engine's folder named in the settings (19`). Each check is one line
and writes nothing:

1. `ls <prefix>/engine/app/defaults/ | grep -E '^(minimax_h3|h3_advanced)'` — the definitions
   are there.
2. `jq -r '.engine.model_folders[]' <data>/settings.json | xargs -I{} find {} -maxdepth 3 -iname '*h3*' -printf '%s\t%p\n'`
   — transformer weights, VAEs and text encoder present. Compare against `URLs` and `required_model_assets` (§1.7).
3. `find <prefix>/engine/app/ckpts -maxdepth 3 -ipath '*minimax_h3*' -printf '%s\t%p\n'` — assets
   in the engine's own ckpts.
4. `nvidia-smi --query-gpu=index,name,memory.total,memory.used --format=csv` — which card is the engine's.
5. `free -g` — RAM for weight streaming.
6. `<prefix>/engine/env/bin/python -c "import imageio_ffmpeg,sys; print(imageio_ffmpeg.get_ffmpeg_exe())"`
   — the encoder in use.
7. **One** text-only task is run in HocusPocus's own UI: `minimax_h3` (or `minimax_h3_fused_turbo`), 540p
   16:9, 124 frames, default steps. The seconds taken and the peak VRAM are noted. Then, read-only on the produced
   file:
   - `ffprobe -v error -show_entries format=format_name,duration:format_tags:stream=codec_name,width,height,r_frame_rate,channels,sample_rate:stream_tags -of compact <clip>.mp4`
   - `strings -n 6 <clip>.mp4 | grep -i -E 'x264|lavf|seed|prompt' | head`

**Done when:** one clip played. Its codec, size, fps and audio are recorded. Every needed file is local. The
seconds per clip and the peak VRAM are written into §8 of this document. If a step fails, the plan stops and the
gap is recorded here.

### Stage 1 — core lifts and video plumbing (no new tab)

Files:
- `hub/core/api.py`: `MEDIA_TYPES`, `Files.existing_media/size`, `Engine.last`, `Draft` protocol, checks.
- `hub/core/clip.py` (new).
- `hub/core/enginecat.py`: `land`.
- `hub/core/files.py`.
- `hub/core/fileroutes.py`: serve video; `GET /api/characters`.
- `hub/core/dispatch.py`: item kind.
- `hub/core/draft.py` (new).
- `hub/worker/catalog.py`: `video_models`.
- `hub/worker/wan2gp.py`: `video_container`, forced task keys.
- Generate Image migrated onto `ctx.draft`, `Engine.last`, `api.whole/seed_of` and `Files.size`; its `/characters`
  route deleted; `list_characters` moved to Media.
- Media `library.py` on `MEDIA_TYPES`.
- Web lifts W1–W8, with Generate Image switched to them.

Tests that must exist:
- `tests/core/test_clip.py` (§2.4).
- `test_files.py`: kind video, `existing_media`, delete/move/regroup a clip, thumbnail 404 for a clip, Range 206.
- `test_jobs.py`: a video `generation` item.
- `tests/engine/test_worker.py`: `video_models`; `FORCED_CONFIG["video_container"] == "mp4"`.
- `tests/engine/test_media.py`: an `.mp4` in Temp is listed with `kind: "video"`, can be favorited and deleted.
- `tests/core/test_draft.py`: merge-PUT, session drop on `session.ended`, settle.
- The existing `test_generate_image.py`, `test_build.py` and `test_mcp*.py` pass unchanged in behaviour.
  `list_characters` is still published, now from Media.
- Web: `guards.test.ts` passes. Unit tests cover `lib/draftStore` and `lib/queueView`.

**Done when:** all tests pass. A hand-placed `.mp4` in `<data>/outputs/<day>/` shows and plays in Media and can be
deleted. Generate Image behaves exactly as before. No file over its line limit. `rg` finds no dead copy of a lifted
function.

### Stage 2 — module skeleton, settings, MCP

Files: `hub/modules/generate_video/{manifest,models,screen,routes,tools}.py`; `web/src/modules/generate-video/`
(manifest, layout, draft, VideoBar without Generate).

Tests (`tests/engine/test_generate_video.py`):
- The registry accepts the manifest.
- The four tools are published with the expected names and schemas.
- `seconds` snaps up to the lattice and refuses above the model's maximum.
- `resolution`/`aspect` → the right `WxH` from a fake catalog.
- Steps outside the model's range are refused.
- The `draft` setting is refused with no window open.
- `chat.cleared` empties the prompt and draft.
- Settings defaults are overridable through `ctx.settings`.

**Done when:** in a fake-engine run the tab shows the models, the bar edits the settings, and
`set_generate_video_settings` from the MCP driver (`tests/core/mcp_driver.py`) redraws an open window. Nothing
renders yet.

### Stage 3 — render path and Media landing

Files: `build.py`, the `generate_video` action, the Generate button, `run/ClipPreview.tsx`, Media `Clip.tsx` and the
Grid tile.

Tests:
- `test_generate_video.py::test_plan` checks the exact task dict and summary title.
- With the fake worker (`tests/fakes/fake_worker.py`) emitting an `.mp4` output: the job finishes, `land` cleans it
  (no `udta`), Media gets `generation{kind: video}`, and the clip is listed.
- Cancel during a clip.
- The queue-full refusal is shared with images (`hub/core/jobs.py:83-84`).
- Web e2e: a clip item plays on the Stage and the Grid tile has no `<img>`.

**Done when:** on the server, text → clip from the button and from `generate_video` lands in Media, plays with sound,
and `strings` finds no `Lavf`/`x264` text and no prompt in the file. A following image job runs normally after the
H3 unload.

### Stage 4 — references and characters

Files: `cast.py`; `build.py` (FL2VA first frame via `image_prompt_type "S"` + `image_start`; Omni via
`minimax_h3_references` with `image_intent: "identity"` and `character_name`); the sockets declaration
(Media → Send → reference); Tab completion via W6.

Tests:
- Names resolve through `Files.character`.
- The cap is the model's (Omni up to 3 boxes of 9 allowed; FL2VA 1).
- A non-image reference is refused.
- The task carries absolute paths only.
- The `references_as` wording in `view()`.

**Done when:** "a clip of Character 1…" with Character 1 in the Characters folder gives a clip where the character is recognisable
(Omni). A Temp picture sent from Media becomes the first frame (FL2VA).

### Stage 5 — audio (later)

- Omni audio references (`audio_intent: voice | drive | style`, `reference_manifest.py:23`).
- FL2VA soundtrack input. This needs an `audio` socket kind (already in `Kind`, `api.py:15`) and audio uploads
  (`guard.py` body types today: json and image, `hub/core/guard.py:39`).
- Sliding windows beyond 14.4 s, with the progress fold of §2.13.
- Turbo LoRAs if their files are local.
- Each of these is its own design note before code.

---

## 7. What stays out, explicitly

None of these in the primitive: `h3_advanced_*` models, the legacy sidecar, Director or Studio workflows, MMAudio,
the prompt enhancer, video upload, video as a reference, timelines or editing.

The assistant does not orchestrate multi-shot sequences through the Hub. Its tools render one clip per call.

---

## 8. Risks

| Risk | Why (Fact where cited) | Mitigation (Proposed) |
|---|---|---|
| VRAM on a 10–12 GB card | H3 reserves 10 GB of working VRAM on top of the streamed weights (`…handler.py:49-55`). Its memory policy is calibrated on a 24 GB 4090 at 345 frames 1280x704 (`…handler.py:549-551`). A 10–12 GB card is far below that | Video models are offered only when the engine lane's GPU has at least the module setting `min_vram_gb` (default 24). With one engine lane (`engine.py:275-287`), this is a property of that lane's GPU, not a choice per job |
| VRAM on the GPU | Peak depends on frames × pixels. The VRAM manager learns peaks **per model only** (`hub/core/vram.py:54-61`), so a 540p 5 s run teaches a number that a 720p 14 s run exceeds | Stage 0 measures. A later core change could key learning by `(model, plan.summary["frames"]*w*h bucket)`. It is out of the primitive; a run whose peak exceeds the card ends as the engine's out-of-memory error, and the lane frees the worker after every clip (part 1, 3.7) |
| RAM | Weight streaming (mmgp) keeps the transformer in RAM. Fused is 21 GB (`hp:defaults/minimax_h3_fused_turbo.json:62`). The Full checkpoint is larger | Stage 0 `free -g`. Offer Full only when present and when it has been added to `models_allowed` |
| Time per clip | Unknown until Stage 0. 20 steps over a ~124×960×544 packed sequence is minutes, not seconds | Fused 4-step as the suggested model when present. The job card shows the ETA from steps (`dispatch.py:154-163`) |
| Head-of-line blocking and model swaps | One FIFO per lane, by design (`dispatch.py:1`). Every switch between an image model and H3 unloads and loads tens of GB | Documented behaviour. A job can be cancelled. A later option is a separate "video" lane on a second GPU, if one is ever marked `engine` |
| Progress for video | Steps only during denoising. Decode and mux show no movement. Windows reset the step count (§2.13) | One pass in the primitive. Phase text shown. The fold is for later |
| Output size and Temp growth | x264 quality 8 at 960x544, 24 fps, 5–14 s is a few MB to tens of MB per clip (estimate; Stage 0 measures). Temp has no quota | Same as images: deleted in Media. A setting-backed Temp quota is not in scope |
| Codec the browser can't play | The codec is the engine config (§2.6). x265 options exist (`hp:plugins/wan2gp-configuration/plugin.py:271`); HEVC in MP4 does not play in every browser | The tile and Clip view show "This clip's codec doesn't play here" on the `<video>` error. The configured codec stays libx264 |
| Metadata left in the clip | Lavf tag and x264 SEI (§1.6), Unverified until Stage 0 | `clip.strip` (§2.4), with a test, plus the Stage 3 `strings` check |
| Missing companion files | Downloads are blocked (`netguard.py`). Partial models would fail at load | Video lists `available` models only. Stage 0 inventory |
| Separate process in the legacy sidecar | ComfyUI subprocess (`hp:defaults/minimax_h3_legacy.json:19-20`). The audit hook is per interpreter (`netguard.py:3-4`) | Excluded by default (`models_excluded`) |
| Worker protocol | 1 MiB per line (`protocol.py:26`). Output events carry a path, not bytes | Fine. The optional poster (§2.8) stays far below the limit |
| Range requests | `<video>` seeks with Range. Unverified on Starlette 1.7.0 | Stage 1 test for 206 |
| Line budgets | `api.py` 254 → ~285. `files.py` 243 → ~260 | Watched by `test_files_stay_small_and_typed` (`tests/core/test_rules.py:73-79`). If `api.py` would pass 300, the checks go to the `Draft` service's file and are exposed as `ctx` methods instead |

---

## Unverified

- That this fork's `generate_video` takes `image_start` as a list of paths, and that `sliding_window_size =
  video_length` is needed (rather than merely harmless) for a single pass.
- That `MMAudio_setting: 0` and `minimax_h3_extended_duration: False` are harmless for image models when forced on
  every task.
- That H3's own prompt enhancer (`hp:models/minimax_h3/prompt_enhancer.py`) stays off with `prompt_enhancer: ""` and
  `enhancer_enabled: 0`.
- Which encoder marks a produced clip actually carries (the Lavf `encoder` tag in `udta`, x264's SEI), and that
  blanking the SEI payload in place leaves every player happy.
- That Starlette 1.7.0's `FileResponse` answers Range requests with 206.
- Which GPU is the engine's on the server, the H3 files present, the seconds per clip and the peak VRAM. Stage 0 records
  them.
- That the `h3_advanced_*` family and the fused entries are listed by the worker's catalog with `t2v_class` set (the
  fused entries take it from their base architecture, `minimax_h3`).
- That the legacy sidecar escapes the worker's audit hook. Assumed, and the reason for excluding it.
- The output-size estimate in §8.
