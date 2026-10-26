# R6 — Every frame and reference kind H3 accepts, and how each would enter the Hub

Read-only research, 2026-10-14. Planning only: nothing here is built. Prefixes: `HP:` = the `app/` folder of a HocusPocus source copy;
Hub paths are relative to the repository root. "Fact" = read in code at the cited line; "Proposed" = design; "Derived" =
worked out from code, not yet seen in a run. Extends `R1` §1.4–1.5 and the plan's Stage 4 and "Later" list.

**Built today (Stage 4).** First / Last model: box 1 is the start frame (`image_prompt_type "S"`, `image_start`,
`image_fit_mode "crop"`; `hub/modules/generate_image/build.py:24`, `:121-130`). Omni model: boxes 1 to N are an image
manifest under the key the defaults file names (`build.py:129`; `hub/worker/catalog.py:136-147`). The cap is the
engine's limit clamped to the bar's 3 boxes (`hub/modules/generate_image/models.py:135`; `cast.py:19`, `:58`). The web
boxes are a dense list: removing one shifts the rest left (`web/src/modules/generate-image/edits.ts:70-78`), so a box's
role can only depend on its position and on what it holds, never on a gap.

## 1. The inventory, ranked for a short film (value first, then cost)

| # | Kind | Model | Engine task keys | Boxes (of 3) | New control? |
|---|---|---|---|---|---|
| 1 | Start + last frame | First / Last | `image_prompt_type "SE"`, `image_start`, `image_end` | 1 start, 2 end | no |
| 2 | Continue a clip | First / Last | `"V"` (+`"E"`), `video_source`, `keep_frames_video_source`, `sliding_window_overlap` | 1 clip, 2 end | no (a clip in a box) |
| 3 | Named identities, detail, cut-out | Omni | manifest `character_name`, `role`, `remove_background`; `minimax_h3_reference_detail` | 1–3 identity | detail: one menu on the sheet |
| 4 | Scene / style / composition pictures | Omni | manifest `image_intent` | 1–3, role per box | yes: a role per box |
| 5 | Pictures at set times | First / Last | `video_prompt_type "KFI"`, `image_refs`, `frames_positions` | 1–3 frames | yes: a time per box; >3 boxes for start+end+2 |
| 6 | Video references | Omni | manifest `type "video"`, `video_intent`, `include_audio`, `audio_path` | any box holds a clip | yes: intent per box |
| 7 | Voice / sound references; a soundtrack | Omni; First / Last | manifest `type "audio"`, `audio_intent`; or `audio_prompt_type "A"`, `audio_guide` | a box holds a sound | yes: sound input; >3 boxes for 2 faces + 2 voices |
| 8 | Control video, mask, re-sound a clip | First / Last | `video_prompt_type "GV"`/`"A"`/`"NA"`, `video_guide`, `video_mask`, `denoising_strength`, `masking_strength`, `audio_prompt_type "K"`/`"2"` | 1 clip, 2 mask | yes: strength, area |
| 9 | Last frame alone | First / Last | `"E"`, `image_end` | 1 end | yes: start/end toggle on box 1 |

Why this order: a short film is a chain of shots. Rows 1 and 2 are what chain them (shot B starts on shot A's last
frame, or carries on from shot A's clip with its sound); both reuse the boxes as they are. Row 3 makes the cast speak
as themselves at almost no cost. Rows 4 to 9 each need a new control or a new kind of input file.

## 2. The `image_intent` the Hub sends: confirmed, with one correction

The allowed values are exactly `identity`, `scene`, `style`, `composition` (`HP:models/minimax_h3/reference_manifest.py:24`);
`identity` is also the default when the key is absent (`:90`). Audio intents: `voice`, `drive`, `style` (`:23`, default
`voice` `:116`); video intents: `character`, `motion`, `scene` (`:25`, default `motion` `:127`). So the Hub's "identity"
is a valid value and the clip it makes is right. The correction: the Hub sends its own **box role word** as the
engine's value (`build.py:129` sends `refs["role"]`, which `catalog.py:146` sets to the literal "identity"); the two
coincide by luck. No definition field announces the vocabularies (the handler publishes only `omni_reference`,
`omni_reference_limits`, `supports_reference_audio`, `omni_reference_detail_choices/_default`;
`HP:models/minimax_h3/minimax_h3_handler.py:1807`, `:2000-2011`). Proposed: keep the role word for the UI and **omit
`image_intent`** while the only intent is identity (same result, no engine word in the Hub). When row 4 is built, the
three vocabularies become one documented constant in `generate_image/models.py`, cited to `reference_manifest.py:23-25`,
pinned by a test against the fake engine — the one fact the definition does not publish, like the reference caps.

## 3. The common shape (Proposed)

**Catalog fact.** `video.references` grows from today's `{role, min, max, end}` / `{role, min, max, key}` into:
```
First / Last: {role: "frames", min: 0, max: 2, start: "S" in allowed, end: "E" in allowed,
               end_alone: end_frames_always_enabled, continue: "V" in allowed and video_continuation,
               overlap: factory sliding_window_overlap, timed: "KFI" in guide_custom_choices and custom_frames_injection}
Omni:         {role: "identity", min: 1, max: limits.image, key, limits: omni_reference_limits,
               audio: supports_reference_audio, detail: {choices: omni_reference_detail_choices, default: ..._default}}
```
Each field is read from the definition (`minimax_h3_handler.py:1755`, `:1795-1800`, `:1807`, `:2000-2011`, `:2032-2042`);
the worker still names no model. `max` stays clamped to `cast.BOXES` in `ui_model`.

**What a box holds.** Today a picture (`{id, w, h}`). Proposed: a box also holds a clip (`clips/...` id, `kind: "clip"`),
later a sound. The box's role is then a function of (model role, position, what it holds): First / Last box 1 = start
frame if a picture, clip to continue if a clip; box 2 = last frame. Omni: every box an identity (picture) or a video
reference (clip). `boxLabel` (`web/src/modules/generate-image/video.ts:83`) and `build._clip_pictures` read the same rule.

**`references` by name.** `cast.resolve` fills boxes 1, 2, 3 in order from Characters (pictures only, `cast.py:41-61`),
and a box handed back by the name it was reported under is kept as it is. That rule already carries rows 1, 3, 4, 5.
A clip has no character name; its box is reported by its file stem, so the assistant can keep a clip placed on screen
but cannot choose one. Choosing clips by name needs a listing of clips (a new tool or a field in `list_characters`):
out of scope while the six tools are fixed.

## 4. Each kind

### 4.1 Start + last frame (rank 1; cheapest)
- **Engine.** `"E"` needs `image_end` (`HP:wgp.py:1230-1238`); with `"S"` the counts must match (`:1244-1247`, the Hub's
  `multi_prompts_gen_type` 2). The model anchors the start at frame 0 and the end at the last frame
  (`HP:models/minimax_h3/minimax_h3_main.py:1697-1716`); the first keyframe is stretched to the canvas, the second
  cover-cropped (`packing.py:223-250`). `image_fit_mode "crop"` crops both to the asked canvas first (`HP:wgp.py:8058-8063`,
  `:8481-8487`). In one pass the end applies (`sliding_window_end_image_at_final` matters only for several windows,
  `:8474-8481`).
- **Announced by.** `"E"` in `image_prompt_types_allowed` (handler `:1795`); the catalog already reads it (`catalog.py:147`).
- **Boxes.** 1 "Start frame", 2 "Last frame", 3 shut. Auto aspect follows box 1 as today.
- **`references`.** `["Character 1"]` = start; `["Character 1", "Character 1 at the door"]` = start and end.
- **Task.** `image_prompt_type` = `"S"` or `"SE"`, `image_end: [path]` (an attachment key, `HP:wgp.py:114-115`).
- **Prompt.** One more alignment line: `<Picture 1>` at 0.00, `<Picture 2>` at the exact end time
  (`HP:models/minimax_h3/prompt_enhancer.py:16-20`). One sentence added to `system-prompt-video-paragraph.md`.
- **Refusals.** Box 2 filled on a model without `end` ("<model> takes one start frame"); the cap line as today.
- **VRAM.** One more keyframe condition row; no change to the token count of the clip. Negligible (Derived).
- **Tests.** Catalog `end` from a fake definition with and without "E"; `build` sends `"SE"` + `image_end` for two
  boxes and `"S"` for one; `cast.resolve` two names on First / Last; web `boxLabel(m, 1) === 'Last frame'`.

### 4.2 Continue a clip (rank 2; medium)
- **Engine.** `"V"` needs `video_source` (`HP:wgp.py:1088-1093`). `keep_frames_video_source`: empty keeps all, a
  non-zero integer truncates, negative from the end (`:1071-1076`, `:7846`, UI text `:12605`). The source's last
  `sliding_window_overlap` frames (factory 18, normalised to 17n+1, `minimax_h3_handler.py:76`, `:285-306`) become
  history plus the boundary frame (`minimax_h3_main.py:488-525`); the prompt is forced into same-shot continuity
  (handler `:2379-2389`). The landed file is **the whole source plus the new frames**, with the source's sound spliced
  in (`HP:wgp.py:9230-9241`, `:9262-9272`), so the extended clip lands as a new clip and the source stays.
  `"VE"` is allowed: carry on and land on a last frame (`:1240-1243`).
- **One pass (Derived; check in a run).** With a source, wgp adds `overlap - 1` to the length before deciding on
  windows (`HP:wgp.py:8023-8024`, `:8209-8211`). With today's `sliding_window_size = video_length` that becomes two
  windows. The clip task must send `sliding_window_size = video_length + overlap - 1` (141 for 124), so the longest
  new part is `max - (overlap - 1)` = 328 frames.
- **Announced by.** `"V"` in `image_prompt_types_allowed` and `video_continuation` (handler `:1755`, `:1795`); the
  overlap from the factory settings. Omni allows no `"V"` (`:1795` gives it `""`).
- **Boxes.** 1 holds a clip ("Continue clip"), 2 "Last frame", 3 shut. Needs: Send and drag from `/clips` into a box
  (both are off for clips today, plan §3 Stage 2), a box thumbnail from `<video preload="metadata">`, `build._image`
  accepting a clip id, Auto aspect from the clip's size.
- **`references`.** A clip is kept by its reported name; it cannot be chosen by name (§3).
- **Refusals.** A clip on a model without `continue`; a clip in box 2 or 3; a picture where a clip is expected is not an
  error (it becomes the start frame); frames above `max - (overlap - 1)`; a source shorter than the overlap.
- **VRAM.** The window is the same size; 17 of its frames are history. The source is decoded to RAM up to
  `keep_frames_video_source` (`HP:wgp.py:8451`), so a long source costs RAM, not VRAM. Peak unmeasured.
- **Tests.** Catalog `continue`/`overlap`; task keys and window arithmetic for 124 and the maximum; refusals; landing
  of the joined file (fake engine writes source+new length); web: a clip drops into box 1 on First / Last only.

### 4.3 Omni: names, detail, background (rank 3; small)
- **Engine.** `character_name` (≤120), `role` (≤500), `remove_background` (bool, honoured only for identity)
  (`reference_manifest.py:82-114`). The name and role bind a speaker to a picture (`ref2va.py:249-262`), which helps a
  named character speak with the right face. `minimax_h3_reference_detail` `match` | `max`; `max` scales each picture to a
  2048 px short edge (`ref2va.py:51`, `:1642-1647`; `minimax_h3_main.py:1932-1938`). Pictures must be within 1:4 to 4:1
  (`ref2va.py:1639-1640`).
- **Announced by.** `omni_reference_detail_choices` / `_default` (handler `:2007-2011`); the manifest fields are not
  announced (engine contract, as §2).
- **Boxes / `references`.** Unchanged; the character name a box was filled with goes into `character_name`.
- **Control.** Detail: one menu on the raised sheet, per model, like the text encoder. Background: a Settings card switch
  or nothing (default off, as the engine).
- **Refusals.** A picture outside 1:4–4:1, said before submit.
- **VRAM.** `match` keeps each picture at no more than the canvas's pixels (`ref2va.py:1645-1647`); `max` adds far more
  tokens per picture. Omni is always one pass and never shrunk by the memory policy (R1 §1.3), so a `max` clip at 720p
  is the likeliest out-of-memory. Unmeasured.
- **Tests.** Manifest carries `character_name` from a Characters box and none from a plain file; detail value sent and
  refused outside the announced choices; the aspect refusal.

### 4.4 Omni: scene, style, composition pictures (rank 4; a control)
Same manifest, other `image_intent` values (§2); a location or a look kept across shots. The prompt names them
differently (`ref2va.py:1286-1300`). **Control:** a role menu per box (Identity / Location / Style / Layout), stored
with the box in the draft. **`references`:** names alone cannot say the role; the tool would need `{name, as}` items,
which changes the setting's shape: keep the menu UI-only at first. **Refusal:** an intent outside the constant.

### 4.5 Pictures at set times (rank 5; a control, >3 boxes)
`video_prompt_type "KFI"` with `image_refs` and `frames_positions`, one 1-based frame number or `L` per picture
(`HP:wgp.py:1046-1063`; handler `:2032-2042`, `:2554-2575`); refused on Omni (`:2555-2559`). Announced by
`guide_custom_choices` and `custom_frames_injection` (handler `:1800`). **Control:** a time per box (seconds, snapped to a
frame). Start + end + two middle frames is 4 boxes. **Refusals:** a position past the clip; count mismatch.

### 4.6 Omni video references (rank 6)
Manifest `type "video"`, `video_intent` character | motion | scene (default motion), `include_audio` (default true),
`audio_path` (`reference_manifest.py:126-143`); ≤3 videos, ≤12 in all (`:15-18`). The runtime itself cuts each video to
the clip's length (`ref2va.py:1815`) and its sound to the clip's duration (`:1830-1870`), so the unused 2–15 s trimmer
(`reference_media.py:13-15`, no caller) is not needed for one pass: a correction to R1 §1.5. A video's sound becomes an
`<Audio N>` and renumbers the audio labels (`ref2va.py:400-440`). Needs a clip in a box (as 4.2) and an intent per box.
**VRAM:** each video adds up to a clip-length stream of reference frames at the canvas size: the heaviest kind.

### 4.7 Sound: Omni voice references; a First / Last soundtrack (rank 7; a new input kind)
- Omni: `type "audio"`, `audio_intent` voice | drive | style, ≤3, never alone, at most one `drive`
  (`reference_manifest.py:115-125`, `:146-159`); `supports_reference_audio` announces it (handler `:1807`). Through
  `submit_task` a `drive` item stays a creative reference that follows the timeline (`ref2va.py:1957-1966`): the exact
  soundtrack route (`split_exact_drive_audio_reference`, `reference_manifest.py:163`) has no caller and wgp never passes
  `minimax_h3_exact_drive_audio_ordinal`. Offer `voice` and `style` only.
- First / Last: `audio_prompt_type "A"` + `audio_guide`; `"K"` takes the control video's sound; announced by
  `audio_prompt_type_sources` (handler `:2054-2069`); refused without the file (`:2549-2550`), and `"2"` refuses `A`/`K` (`:2506-2511`). The clip keeps the given
  sound (`output_audio_is_input_audio`, `:2075`); length is not cut to the sound when asked (`video_length_not_limited_by_audio`, `:2074`; `HP:wgp.py:8175`).
- **Needs.** An audio upload and a place to keep sounds (no root holds audio today); a voice per character
  (Characters are pictures only, `cast.py:41-61`), so `references: ["Character 1"]` could add Character 1's voice beside that character's face.
  Two speaking characters with their voices is 4 boxes. **VRAM:** small (audio latents).

### 4.8 Control video, mask, re-sound (rank 8; several controls)
`"GV"` + `video_guide` edits a clip; it changes pictures only with `denoising_strength` < 1 or a mask
(`minimax_h3_main.py:1591-1595`). `"A"`/`"NA"` need `video_mask` (handler `:2485-2500`); strengths 0–1 (`:2464-2476`);
a short control video is padded with its last frame (`minimax_h3_main.py:1826-1841`). `audio_prompt_type "2"` keeps the
control video's pictures and makes new sound (handler `:2506-2525`; `minimax_h3_main.py:1574`). None on Omni. Announced by `guide_custom_choices`,
`video_to_video_inpaint`, `mask_preprocessing.selection` (handler `:2032-2053`). **Controls:** strength, area, a mask
clip. **VRAM:** an extra VAE encode of the control and mask; token count unchanged (Derived).

### 4.9 Last frame alone (a control)
`"E"` without `"S"` is allowed because `end_frames_always_enabled` (handler `:1796`; `HP:wgp.py:1230-1231`). With dense
boxes, box 1 cannot be "end" without a toggle on its label (Start / End). Without `crop` the canvas follows the end
picture (`HP:wgp.py:8488-8490`).

## 5. Fit modes
One per task, not per reference: `image_fit_mode` `""` (the engine's `fit_canvas`, default 1: the canvas follows the
picture), `"crop"` (crop to the asked canvas), `"source"` (`HP:wgp.py:8058-8065`); it applies to the start, the end and
the source clip alike (`:8445-8451`, `:8484`). Keep `"crop"`: the clip is the size asked and Auto already follows box 1.
Omni pictures are never cropped; they keep their shape at `match` or `max` detail (`ref2va.py:1627-1652`).
`remove_background` is the only per-reference option, and only for identities. A per-box fit is not offered by the engine.

## 6. Cost and memory at a glance

| Kind | Hub files touched | Boxes | VRAM over a text clip |
|---|---|---|---|
| Start + last | catalog, build, cast (role), video.ts, paragraph | 2 | negligible |
| Continue | + inputs/Slots (clip in a box), media Send for clips, enginecat landing check | 2 | same window; RAM grows with source |
| Names / detail | build, sheet menu | 3 | `max` detail large |
| Intents | draft box shape, Slots menu | 3 | as identities |
| Timed pictures | draft box time, Slots | 4+ | small |
| Video refs | as continue + intent | 3 | largest |
| Sound | new upload kind, Characters voices | 4+ | small |
| Control / mask | strength, area, mask | 2 | moderate |

## 7. Tests common to every step
The fake engine definitions (`tests/engine/fake_engine/fake_engine.json`) gain the announcing fields; each fact is pinned
from them, never from a model id. One plain refusal per rule above, tested by its text. The worker test asserts the task
reaches `submit_task` with absolute paths for the manifest (not an attachment key, R1 §0.2). A browser test per new box
role (label, drop accepted or struck). `rg -n "minimax|h3" hub/core hub/worker` stays empty.

## 8. Unverified
- The continuation window arithmetic (4.2) and that the joined file is one output; one run settles both.
- Peak VRAM for `max` detail, video references and continuation on the engine card.
- Whether the `image_prompt_types_allowed` filter (`HP:wgp.py:3310-3314`) runs on the `submit_task` path or only on
  saved settings; the Hub should pre-check the letters either way.
