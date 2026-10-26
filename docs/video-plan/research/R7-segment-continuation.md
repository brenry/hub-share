# R7 — Longer scenes from segments that continue each other

Read-only research, 2026-10-14. Question: how a scene longer than one H3 pass is made of segments of about 5 s, each
continuing the previous one, without the VRAM of any pass growing. Prefixes: `HP:` = the `app/` folder of a HocusPocus source copy;
Hub paths are relative to the repository root. "Read" = seen in code at the line cited, not run. "Computed" = arithmetic from
read values. "Proposed" = design, not built. R1 (`research/R1-engine-h3-contract.md`) is assumed; it is not repeated.

---

## 1. The engine's own chaining inside one job (multi-window)

**What decides it.** H3 declares `sliding_window: True`, `video_continuation: True`, `sliding_window_exact_total_frames`,
`sliding_window_trim_to_requested`, `sliding_window_end_image_at_final` (FL2VA only) and `sliding_window_audio_history`
(`HP:models/minimax_h3/minimax_h3_handler.py:1754-1767`). In `generate_video` a job is split when the frames to make exceed
`sliding_window_size` (`HP:wgp.py:8208-8214`); the number of windows is `1 + ceil((total - window + discard) /
(window - discard - reuse))` (`HP:wgp.py:284-286`, used at `:8267-8269`). Later windows are sized by
`compute_next_sliding_window_length`, capped at the window so a later pass can never be larger than the first
(`HP:wgp.py:2998-3022`). `minimax_h3_multi_window` is only read by the handler: `False` caps `video_length` to the window
(handler `:2618-2625`, `:2682-2689`); `wgp.py` itself never reads it beyond its default (`HP:wgp.py:7450`).

**What is kept between windows.** Read:
- Pixels: the last `reuse_frames = min(window - 17, overlap)` frames of the window just made (`HP:wgp.py:8210`,
  `:9213-9218`). H3 splits them into 17 clean history frames (kept as latent conditions, `keep_all_latents`) and one
  boundary frame used as the next pass's first-frame anchor (`HP:models/minimax_h3/minimax_h3_main.py:488-525`, `:1650-1678`,
  `:1695-1714`). The history frames are put back in front of the output (`minimax_h3_main.py:2560-2564`) and the assembler
  cuts the whole overlap from every later window (`HP:wgp.py:9247-9252`).
- Sound: the trailing `reuse_frames` of generated audio (`HP:wgp.py:9206-9211`) becomes the next window's
  `input_waveform` (`:8526-8527`), which H3 encodes as audio history and boundary rows (`minimax_h3_main.py:1344-1392`,
  `:2079-2088`). Voice and ambience therefore carry across windows inside one job.
- Prompt (FL2VA; an Omni prompt is left whole, handler `:2391-2392`): one prompt is paced across the windows, each
  gets a timed "continuation window k of N" slice (handler `:2398-2413`, `:1445-1580`); with one window the prompt is
  untouched (`:1473-1474`). An end picture is used only by the last window (handler `:1761`; `HP:wgp.py:8470-8479`).
- Omni: only with `minimax_h3_reference_sequence: True`; then each window gets the history frames, the boundary frame as
  its first anchor, and the full reference manifest again (`minimax_h3_main.py:1680-1693`; handler `:2582-2591`). This is
  the only engine path that holds identity pictures and motion continuity together.
- Seed: the same seed every window, unless the opt-in `h3_long_sequence_vary_seed` custom setting adds a stride per
  window (handler `:187-195`).

**Overlap and discard on H3.** The overlap is honoured but forced onto H3's 17n+1 lattice: default 18, at most 103 and at
most `window - 17` (handler `:76-93`, `:285-306`, re-applied after the memory policy `:2693-2699`; `HP:wgp.py:7950-7953`).
`sliding_window_discard_last_frames` is **not** honoured: the handler overwrites it with 0, or 17 when the opt-in custom
setting `h3_long_sequence_clean_tail` is on in a multi-window job (handler `:139-149`, `:2643-2653`). Overlap noise and
colour correction are forced to 0 (`:2654-2655`).

**VRAM and RAM.** Each window is its own model call, so VRAM per pass is bounded by the window (and the memory policy may
shrink the window, never the total: handler `:1372-1442`). RAM is not bounded: every window's frames are kept as uint8 in
`frames_already_processed` and the audio in `full_generated_audio` (`HP:wgp.py:9333-9336`, `:9279`), and the save block
sits inside the window loop, so each window writes a new file holding all frames so far (R1 §4.2). A K-window job encodes
1+2+…+K windows' worth of video and emits K growing outputs to the Hub's worker.

**Quality cost.** Each window regenerates the boundary frame and spends 17 frames of sequence on history: computed, 18/141
≈ 13 % extra work at a 141-frame window, 18/345 ≈ 5 % at 345. The overlap goes through a VAE decode/encode round trip each
window, so small errors compound. The engine ships opt-in remedies "for investigating very long FL2VA continuations"
(single-frame handoff after window 3, a reset every third window, a per-window seed, the clean tail; handler `:96-106`,
`:152-205`), which says drift over many windows is a known effect.

**For the Hub.** One job holds the lane for the whole scene (images wait), a cancel loses the windows not yet made, there
is no review between windows, and the worker must keep only the last of the growing outputs (R1 §5.1 guard). Its one real
advantage over separate jobs is the audio history (§2.3).

---

## 2. Continuation across separate jobs

### 2.1 `video_source` with "V" (the engine's Extend)

FL2VA allows the letters `TSEV` (handler `:1795`); "V" needs `video_source` (`HP:wgp.py:1088-1093`), which is an attachment
key and so made absolute by the session (`HP:wgp.py:114-115`; R1 §0.2). `keep_frames_video_source` can only shorten the
source from its start or end (`HP:wgp.py:1071-1076`, `:7846`, `:5444-5446`); it cannot keep just the tail. Read path of one
continuation pass:
1. The engine decodes the **whole** source in-process (decord, or its ffmpeg helper for HDR/odd-pixel files), resampled
   to the model's 24 fps and fitted to the canvas (`HP:wgp.py:8451`, `:5422-5452`; up to 15000 frames, `:105`). The canvas
   then follows the source: `resolution` no longer decides the size (`HP:wgp.py:8456`, `:8464-8466`).
2. The frames to make become `video_length + overlap - 1` (`HP:wgp.py:8023-8024`; the validator says the same,
   `:1268-1271`). **With today's `sliding_window_size = video_length` this always becomes two windows** (124 + 17 = 141 >
   124), i.e. two passes and two outputs. HocusPocus's own UI hits the same rule and subtracts the overlap from
   `video_length` (HocusPocus `ui/src/stores/useStore.ts:5405-5414`).
3. The last 18 source frames are the conditioning (`HP:wgp.py:8457-8459`); H3 uses 17 as history and the last as the
   first-frame anchor, so the target is `frame_num - 17` frames, which must lie on 17n+5 (`minimax_h3_main.py:1715-1727`).
4. The handler prefixes the prompt with its "SOURCE-VIDEO CONTINUATION CONTRACT" (same take, same camera, no cut at the
   boundary) on window 1 of a "V" task (handler `:2379-2390`, `:1583-1611`).
5. The output is the **source plus the new frames**: `cat(prefix_video, sample[:, 18:])` (`HP:wgp.py:9235-9245`). The source
   audio is re-encoded for the source part and the new audio appended after it (`HP:wgp.py:9415-9450`;
   `HP:shared/utils/audio_video.py:361-421`). The joined file is re-encoded as a whole (libx264 `libx264_8`,
   `audio_video.py:625-628`).

**One pass per segment (computed from the above).** Send `video_length = N` (124…328, on 17n+5), `sliding_window_size =
N + 17` (also on the lattice, ≤ 345), `sliding_window_overlap = 18`, `minimax_h3_multi_window: False`. Then the frames to
make are N + 17 = the window, one pass; the pass is N + 17 frames, the target N; 17 + N frames come back, 18 are cut, so
the scene grows by **N − 1 frames** (123 = 5.125 s for N = 124; the longest step is N = 328, 13.6 s).

**Sound does not continue across jobs.** In window 1 `input_waveform` comes only from a soundtrack or from a previous
window (`HP:wgp.py:8526-8545`); the source clip's audio is not passed, so H3 gets no audio history rows
(`minimax_h3_main.py:2079-2088`) and pads the history span with silence that is then cut (`:2580-2596`). Read, not run:
voice, room tone and music may jump at each joint. The draft must restate the soundscape in the same words.

**Costs that grow with the scene.** Each Continue decodes and re-encodes everything before it: one more x264 generation on
the earlier segments per step (the visible loss is for Stage 0 to measure), and RAM for the decoded source plus the joined
copy. Computed at 3 bytes per pixel: 960x544 is 1.57 MB a frame (37.6 MB per second of scene), 1280x704 is 2.70 MB
(64.9 MB/s); held about twice (source tensor and joined sample) a 60 s scene adds roughly 4.5 GB at 540p and 7.8 GB at
720p to the engine's RAM. VRAM does not grow: only the 18 tail frames enter the model.

### 2.2 A start frame (last frame of the previous clip as `image_start`)

Each segment is its own N-frame clip that opens on a still. No motion history, no audio history, and an explicit start
picture switches H3's history off even if a source were given (`has_explicit_start`, `minimax_h3_main.py:503-504`, `:1654`).
Getting the last frame:
- **Pure Python: not realistic.** The MP4 boxes give the last sample's bytes easily (`hub/core/clip.py` already walks
  them), but that sample is a P or B frame of an x264 GOP; decoding needs a full H.264 decoder (CABAC, prediction,
  deblocking) and the whole GOP before it. Pillow has none.
- **Ask the engine: realistic.** The worker runs in the engine's Python; the engine has `get_video_frame(path, n,
  return_last_if_missing=True)` (`HP:shared/utils/utils.py:178-230`, cv2 in-process). It would need a new worker message
  ("one frame of this file into the outbox"), landed as a picture. More protocol for a weaker continuation.
- **Not usable:** the engine's "L" letter takes the newest MP4 in its own `save_path` (`HP:wgp.py:7976-7981`), which is the
  Hub's outbox, emptied on landing; `embed_source_images` embeds inputs, not outputs (R1 §4.4).

### 2.3 Which one, and identities

"V" is the realistic route: the engine does the decoding, the motion carries over (17 frames of history), the engine
writes the continuation contract itself, and the joined file *is* the scene, so no stitching is needed. The start-frame
route needs a new worker message and continues less (a still, no motion). The in-job route (§1) is the only one that
carries sound, at the cost of no review between segments; keep it as a later "make it longer in one job".

Identities: FL2VA has no reference manifest; the subject is held only by the history frames. Omni (Ref2VA) has no "V"
(`image_prompt_types_allowed` is empty for Omni, handler `:1795`), so a separate-job Omni continuation is not offered by the
definition. Its options are the in-job reference sequence (§1) or an Omni clip with the previous clip as a `type: video`
reference (`video_intent` scene or character, manifest rules in R1 §1.5), which conditions but does not continue pixels
(unverified; the engine's reference trimmer has no caller, R1 §1.5). FL2VA "V" + "E" (continue, then land on a picture,
`TSEV`) can re-anchor a look at the end of a segment; that is a later option.

---

## 3. Per-segment VRAM and RAM

- Stated by the engine: a fixed 10 GB of working VRAM for the packed sequence beyond the streamed weights (handler
  `:49-55`); the pass-length tables per resolution band and card size (Pruned `:623-685`), calibrated on a 24 GB card that
  completes 345 frames at 1280x704 (`:543-551`). Each pass prints `[MiniMax H3 Perf] WxH, frames, packed rows`
  (`minimax_h3_main.py:2375-2384`): the row count is the real size of the pass.
- A continuation pass is N + 17 frames, not N: the 17 history frames are sequence rows too (`keep_all_latents`,
  `minimax_h3_main.py:1672-1678`). The memory policy compares `video_length`, not the pass: with N at the card's safe
  length it does not shrink anything and the pass is 17 frames over the table (handler `:1430-1432`). If it does shrink
  (N above the safe length), the window falls below N + 17 and the job silently becomes two windows. On the Hub's 32 GB
  card neither happens at 540p or 720p (every band allows 345 above 24 GB, `:660-685`).
- Measured by the Hub: the worker samples peak VRAM (whole card) and peak RSS per task and returns them with `task_done`
  (`hub/worker/wan2gp.py:71-80`, `:187-229`); `hub/core/vram.py:25` learns peaks in memory only. Stage 3 measured the
  load, not a clip: memory profile 4 pinned about 40 GB of RAM (peak 40.8 GB) on a 62 GB machine, profile 5 does not pin. No per-clip VRAM, time or file size is recorded yet (Stage 0 debt).
- RAM per Continue grows with the scene (§2.1): the Hub must cap the source length, set from a measured `peak_rss_mb`.

---

## 4. Proposed Hub shape (minimal, no new module, no new tool, no database)

**Catalog.** A clip model `continues` when "V" is in `image_prompt_types_allowed` and it is not Omni (`hub/worker/catalog.py`
next to `picture_refs`, `:136-147`); the fact goes into `video_facts` (`:150-177`). No model name in core or worker.

**MP4 facts, pure Python.** `hub/core/clip.py` gains `facts(path) -> {frames, w, h, fps, seconds}` from `tkhd` (size),
`mdhd` (timescale, duration), `stts`/`stsz` (sample count) of the video track, reusing `_top`/`_head`; never decoded. It
tells the build step the source's size, length and frame rate, and refuses a file that does not walk.

**The task (`build.clip_job`, `hub/modules/generate_image/build.py:133-173`).** When box 1 holds a `clips/` id on a model
that `continues`:
```python
{**today_minus_size_and_pictures,
 "resolution": f"{w}x{h}",                  # the source's own size (the engine follows it anyway)
 "video_length": N, "sliding_window_size": N + 17, "sliding_window_overlap": 18,
 "minimax_h3_multi_window": False,          # from catalog `one_pass`, as today
 "image_prompt_type": "V", "video_source": "<abs path of the clip>", "keep_frames_video_source": ""}
```
N is the per-model Seconds setting (frames). 17 is the model's `frames_steps` and 18 its overlap default; both come from
the definition through the catalog (`sliding_window_defaults`, handler `:83-94`), not from literals. Seed: the bar's seed
policy as for any clip (random by default; "keep the seed" reuses `last_seeds`). The clip file carries no seed or model
(metadata off, name = time), so "same model" means: the model of the job that made it while that job is in the list,
else the bar's current model if it `continues`, else the refusal below.

**Summary.** Adds `continues: <clip id>`, `mode: "continue"`, `frames: N`, `seconds: (N-1)/fps` (new part) and
`scene_seconds: (S+N-1)/fps`. Job kind stays `image`, `kind: "clip"`.

**Where it lands (the folder is the record).** A sequence is a group folder `clips/<day>/<group>/`, `<group>` = the stem of
the first clip (its time). On success the core moves a loose source into `<its day>/<its stem>/` with the existing
`files.regroup` (`hub/core/files.py:199-221`) and lands the new clip in the source's folder, still named by its time
(`temp_path`, `files.py:35-45`; `land` gains a target folder, `hub/core/enginecat.py:106-125`). Order by time is chain
order. Every file in the folder is self-contained (each Continue holds everything before it), so deleting earlier ones or
continuing the same clip twice (a branch) is harmless; the longest file is the scene.

**Media (`/clips`).** A "Continue" action on a clip: switches the bar to that clip's model as above, puts the clip in box 1
(a video tile), greys the size menu (the size is the clip's), and keeps Seconds as the step length (shown "+5.1 s").
The clips tree shows group folders under days as sequences; tiles in time order with their seconds.

**Stitching.** Not needed on this route (the engine writes the joined file). For independently made segments a stdlib
concat next to `clip.py` is feasible: same `avcC` and `esds` bytes required (else refuse), stbl tables appended (`stts`,
`ctts`, `stss` + sample offset, `stsz`, `stsc` renumbered, `co64` rebuilt), durations summed, the first file's edit list
kept, `mdat` streamed. Known seams: each later AAC segment carries 1024 priming samples (32 ms at 32 kHz) unless its first
audio packet is dropped; a start-frame chain repeats one frame per joint. About 200 lines; only after an ffprobe check in
Stage 0.

**Refusals (one plain line each, before submit).**
- "The clip to continue is gone" (box 1 id missing or not in the clips root).
- "<model> cannot continue a clip" (no `continues`; Omni included, with "use First / Last").
- "A continued clip takes only box 1" (boxes 2…N filled).
- "Each step is at most <(max-17)/fps> s" (N + 17 over the pass maximum).
- "This clip is not an MP4 the hub can read" (`facts` fails) and "This clip's size is not one the model makes" (size
  not a multiple of 32 or outside the tiers).
- "The scene is <S> s; the longest that can be continued is <cap> s" (RAM cap, from measured peaks).
- Worker guard: a video task reporting more than one file emits only the last (R1 §5.1).

**Tests.** Build: the exact task for a continue (keys above, absolute path, window N + 17, overlap 18, one pass) and each
refusal with its line; for every N on the lattice, N + 17 is on the lattice and the engine's window count
(`HP:wgp.py:284-286` arithmetic) is 1. `clip.facts` on the tiny MP4 fixture (frames, size, fps) and a torn file. Landing:
a continue lands in the source's group, a loose source is regrouped first, a branch adds a sibling. Catalog: `continues`
from the letters, false for Omni. Fake worker: a "V" task yields one file whose frames are source + N − 1. Web: the
Continue action fills box 1 and greys size; the tree lists a group as a sequence.

---

## 5. The Open WebUI side

No new tool. Two small additions to existing shapes: `get_generate_image_settings` reports `last_clip` (id and seconds of
the newest clip this screen made; memory only, like `last_seeds`), and `references` on a model that `continues` accepts a
clip id. Paragraph line for the system prompt:

"Continue: <what happens next>" -> call get_generate_image_settings, set references to [last_clip] and write the
draft in the same call, then call generate_image. The draft describes only what happens from the clip's last moment on:
no <Picture 1> line, the same overall_soundscape words as the previous draft, speech only for the new seconds. If
last_clip is empty, ask one short question.

So a scene is driven by one chat line per step ("Continue: the character turns to the window and the rain gets louder"); each
step shows on `/clips`, and the next line says "Continue" again or re-rolls the step from the same clip.

---

## Unverified

- That a "V" task with `sliding_window_size = N + 17` runs as one pass and returns source + N − 1 frames (read only).
- That the source's sound is never passed as history across jobs (read only), and how audible the joint is.
- The generation loss of re-encoding earlier segments at `libx264_8`; the RAM figures (computed, not measured).
- Omni with a `type: video` reference of the previous clip; Omni with "V" sent anyway.
- That every H3 clip the Hub lands has identical `avcC` across segments (needed only for the concat).
