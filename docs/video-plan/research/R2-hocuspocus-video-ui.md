# R2 — How HocusPocus (and Maestro before it) presents video generation

Research note for the Hub's first video module ("Generate Video", MiniMax H3). Read-only study of the HocusPocus
source (a `hocuspocus-main` checkout, VERSION `0.10.0`) and of the earlier planning notes (`PLAN/`, since
retired). Written 2026-10-13.

Path prefixes used below:

| Prefix | Means |
|---|---|
| `UI/` | `hocuspocus-main/ui/src/` |
| `APP/` | `hocuspocus-main/app/` |
| `HP/` | `hocuspocus-main/` (README, CHANGELOG, roadmap) |
| `i18n:` | `UI/i18n/locales/en/<namespace>.json:<line>` |
| `PLAN/` | the earlier planning notes (retired) |
| `HUB/` | the repository root |

Every claim cites `path:line`. Where a value was derived by reading code rather than observed at runtime, the text
says "derived". The final section lists what was not verified.

---

## 0. Lineage in one paragraph (what "Maestro-era" means here)

The CHANGELOG carries two numbering schemes: Maestro releases 1.0.0 → 1.6.5 (2026-07-08 → 2026-08-08) are the
upstream lineage, and HocusPocus restarts at 0.9.0 ("First HocusPocus preview", 2026-08-24) and 0.10.0
(2026-10-04) (`HP/CHANGELOG.md:3-5,75-78`). **MiniMax H3 itself is Maestro work:** native FL2VA arrived in 1.5.5
(`HP/CHANGELOG.md:222-228`), Omni/Ref2VA, Full 33B variants, Director H3 bounded shots and the encoder picker in
1.6.0 (`:129-218`), Turbo on Full in 1.6.1 (`:119-125`), and Turbo on Pruned, the 1280x704 "720p" tier, window
locking, First Block Cache and the H3 window storyboard in 1.6.5 (`:82-115`). HocusPocus 0.9.0 has no itemised notes;
0.10.0 adds Series Lab end to end, Video 2D/3D authoring over MCP, Productions/music videos from one spec,
"comic to film and trailer structure", and export quality levels (`HP/CHANGELOG.md:11-53`). The planning notes
already record the chain Wan2GP → Maestro → HocusPocus → the copy on the server (`PLAN/02-HOCUSPOCUS-FIELD-GUIDE.md:23-35`).

---

## 1. Map of the video-related sections

The shell groups entry points as **Direct generation**, **Studios** ("Develop guided creative projects") and
**Production** ("Prepare, supervise and edit productions") (i18n:navigation:32-34,42-45). Gallery tabs include
Videos, Videoclips, Trailers, Scenes, Series Lab, Video Editor, Productions, Music productions, Video 2.5D, Video 3D
and Multi-clip (i18n:navigation:99-121).

**1.1 Direct generation → Video (Maestro "Studio mode").** One panel, `DirectGenerationWorkspace`, renders every
direct mode; its title is "Direct generation · Video" (`UI/components/Sidebar/Sidebar.tsx:43,81-89`). The nav
description is "Create one video or continue an existing clip" (i18n:navigation:80). It produces exactly one queued
generation per press (or N with output count / prompt scheduler) and chains nothing: the result lands in the gallery,
from where it can be re-rolled, extended, retaken, used as a reference frame or opened in the Video Editor (§3).
Video is the store's default mode (`UI/stores/useStore.ts:2299`). Era: **Maestro 1.0.0** introduced "Studio mode —
Video (Frames / Multi-Shot / Extend / Blend sub-modes, each with its own isolated working set)" and the unified Inputs
panel (`HP/CHANGELOG.md:528-532`); every H3 control on it is Maestro 1.5.5–1.6.5 (§0). HocusPocus renamed the area
"Direct generation" and grouped the column into "Input and references / Instructions / Model and options · Run"
(i18n:studio:groups; `Sidebar.tsx:155,162,207,234`).

**1.2 "Studio" vs "Studios".** In Maestro, "Studio" *is* the manual bench above (`HP/README.md:179-181`: "Studio is
the manual bench: pick image, video or audio, write the prompt, add references and LoRAs, generate"). In HocusPocus,
"Studios" is a separate menu of guided labs (Story Lab, Series Lab, Comics, Video 2.5D, Video 3D;
i18n:navigation:63-68). Studios do not own a video form: Story Lab hands canon to Director/trailers/videoclips
(`HP/README.md:165-169`), and the 2.5D/3D editors render their own MP4 (§1.6). Era: Studios labs are HocusPocus.

**1.3 Director: film, videoclip, trailer.** "Prepare and supervise multi-shot productions" (i18n:navigation:65).
Director takes a brief or a song and runs analyze → plan → images → clips → assemble, in Manual (approve each step) or
Auto mode (`HP/README.md:37-45`; auto-mode label "* Dangerously Skip Human Intervention", i18n:director:104).
It chains the LLM planner, the image model (start frames), and the *same* video task as Direct generation, then joins
the clips (§4). Era: music video and short film are **Maestro 1.0.0** (`HP/CHANGELOG.md:533-536`); H3 bounded-shot
Director is Maestro 1.6.0 (`:129-137`); comic-to-film and trailer structure are **HocusPocus 0.10.0** (`:35-40`;
trailer planner `APP/services/production_structure.py:1-12`). Podcast and Viral video exist only in the backend
(`APP/services/director/orchestrator.py:68-74`; `PLAN/01-WHAT-HOCUSPOCUS-DOES.md:46`).

**1.4 Productions / Music productions.** "Review prepared productions and their progress" and "Shots, takes and the
montage of a music video" (i18n:navigation:71-72). Productions keep the whole Director thread so one shot can be
retaken without starting over (`HP/README.md:39-41,290`). The shot panel regenerates one shot either through an HTTP
route recorded with the shot or through the Series native batch (`UI/features/production-shots/regenerate.ts`, the
`executeRegeneration` function, executors `http` / `series_native`). It chains Director/Series state → one
regeneration → rejoin. Era: Maestro 1.4.0 already had the Director Dashboard repair/rejoin workflow
(`HP/CHANGELOG.md:295-300`); the Productions catalog, review split and "music video from one spec over MCP" are
HocusPocus 0.10.0 (`:35-40`).

**1.5 Video Editor.** "Assemble and export existing clips" (i18n:navigation:66). Trim, split, reorder, add one
soundtrack, export as a queued FFmpeg job (`POST /api/v1/video-editor/export`, `UI/api/video-editor.ts:140`;
`APP/_launch_runtime.py:35231`). It "never regenerates pixels" (`HP/docs/video-editor/HOWUSEIT.md:3-5`). Clips arrive
from the gallery action "open in Video Editor" (`UI/components/MainContent/OutputActionBar.tsx:141`). Era: not in the
Maestro changelog; its guide is branded "Loreframe Lab" (`HOWUSEIT.md:3`) and the roadmap lists its Wizard migration
(`HP/WIZARD_AUTOMATION_ROADMAP.md:85-103,489`), so it is treated here as HocusPocus-era (see Unverified).

**1.6 Scene 2D / 3D ("Video 2.5D" and "Video 3D").** Two compositors that produce video *without* a diffusion
model: Video 2.5D is "layers, plates and frame-percent motion" and Video 3D is a "Real 3D world editor: metres,
cinematic cameras, objects and background" (i18n:navigation:67-68). The tab key `scene3d` is labelled "Video 2.5D" and
`world3d` "Video 3D" (i18n:navigation:116-117), so the folder names mislead. Export is browser-side WebCodecs
(`UI/features/scene3d/exportMp4.ts:41,72`) or a server render job (`UI/features/render/serverSceneExport.ts:9-11`).
H3 clips can be placed as "MiniMax plates on the screens" (`HP/README.md:15`). Era: HocusPocus (0.10.0 extends them:
`HP/CHANGELOG.md:42-50`).

**1.7 Series Lab.** "Plan a series and create its episodes" (i18n:navigation:63). Each shot has a production method
`generated_video | animation_2d | animation_3d | imported_video` (`UI/features/series/productionMethods.ts:3`;
`APP/services/series_production.py:6`); the series' video model defaults to H3 (`UI/features/series/model.ts:81`;
`SeriesShotDurationControl.tsx:32`). It chains canon → script → shots → takes → per-language cut with subtitles.
Era: HocusPocus 0.10.0 (`HP/CHANGELOG.md:11-25`).

**1.8 Smaller video entries.** Multi-Shot, Extend and Blend are sub-modes of Direct Video (`UI/components/Sidebar/
ModeToggle.tsx:27-31`), Maestro 1.0.0. Edit (Retake, Inpaint, Outpaint, Repaint, Recast) is a sibling direct mode
(`Sidebar.tsx:70-75`), Maestro 1.0–1.5. The H3 "Style sheet" imports the `ostris/minimax_h3_1k` caption library
(`HP/README.md:197-199`), HocusPocus.

---

## 2. The Direct Video form for a MiniMax H3 job

### 2.1 The H3 models the picker offers

| Model id | Label (model JSON `name`) | Notes |
|---|---|---|
| `minimax_h3` | "H3 First / Last — Pruned" | recommended; text, first, last or both frames; 20 steps, 124 frames, 864x480, guidance 1.0 (`APP/defaults/minimax_h3.json`) |
| `minimax_h3_full` | "H3 First / Last — Full" | 33B |
| `minimax_h3_fused_turbo` | "H3 Fused 4-Step — Frames (Experimental)" | 4 steps (range 4–8), 243 frames, 1152x640, guidance locked, LoRAs disabled (`minimax_h3_fused_turbo.json`) |
| `minimax_h3_ref2va` / `_full` / `_fused_turbo` | "H3 Omni — Pruned" etc. | ordered image/video/audio references (`minimax_h3_ref2va.json`) |
| `minimax_h3_legacy` | legacy ComfyUI route | fixed 20-step recipe, no LoRAs (`APP/models/minimax_h3/minimax_h3_handler.py:1960-1993`) |
| `h3_advanced_*` | "H3 Advanced FL2VA 33B" etc. | separate WanGP 12.7.2 family (`h3_advanced_fl2va.json`), not covered here |

The picker is `ModelSelector` in the bottom bar (`Sidebar.tsx:253-255`). Fused models are renamed "H3 · Fast mode —
{workflow}" (i18n:studio:891); badges "First / Last", "Audio Out", "Audio In" come from model capabilities
(i18n:studio:248-256; `UI/components/Sidebar/ModelSelector.tsx:201-209`). Selecting a model loads
`GET /api/v1/defaults/{model}` and `GET /api/v1/model-options/{model}` (`UI/api/generation.ts:208`;
`APP/_launch_runtime.py:6529`). The store's starting model is LTX, not H3 (`UI/stores/useStore.ts:2026-2043`).

The backend capability record that drives every control (`minimax_h3_handler.py:1738-1940`): `fps 24`,
`frames_minimum 124`, `frames_maximum 345`, lattice `17n+5` with `ceil` alignment (`:1740-1752`; constants `:57-64`),
`sliding_window True` (`:1754`), `image_prompt_types_allowed "TSEV"` for FL2VA and `""` for Omni (`:1795`),
`returns_audio True` (`:1801`), `no_negative_prompt True` (`:1808`), `supports_auto_aspect True` (`:1834`),
`loras_disabled` only for fused (`:1939`), Omni limits 9 images / 3 videos / 3 audio / 12 total (`:2001-2006`).

### 2.2 Every control, in screen order

Column order is fixed in `Sidebar.tsx:162-224`; the bottom bar is `:232-262`; most numbers live in the Advanced
drawer (`UI/components/Sidebar/AdvancedSettings.tsx`). "Label" is the English i18n text.

| # | Control | Label (i18n) | Default | Validation / visibility | Request field |
|---|---|---|---|---|---|
| 1 | Sub-mode tabs | "Frames / Multi-Shot / Extend / Blend" (i18n:studio:26-29) | Frames (`image_mode 0`) | tab shown only if the model's letters allow it; Omni shows none (`ModeToggle.tsx:27-52`) | `image_mode` (forced back to 0 for video at submit, `useStore.ts:5427-5429`) |
| 2 | Duration slider (seconds) | "Duration" (i18n:studio:185) | 5 s (`UI/stores/studioConfigurationSlice.ts:146`) | min = 124/24 = 5.17 s; max 300 s when windows are on, else 14.375 s; step 0.1 (`UI/components/Sidebar/DurationSlider.tsx:72-82,156-163`); setter clamps and aligns to `17n+5` (`studioConfigurationSlice.ts:147-183`) | `video_length` frames (`useStore.ts:4941-4950`) + `_duration_seconds` (`:5137-5145`) |
| 3 | 30-second pass | "Allow 30s clips · Experimental" (i18n:studio:194) | off | H3 only (`DurationSlider.tsx:164-174`); max 719 frames (`UI/lib/h3ExtendedDuration.ts:3`) | `minimax_h3_extended_duration` |
| 4 | Turbo toggle + preset | preset label from catalog, "H3 acceleration preset" (i18n:studio:879), warning "Speed preset: prompt/style fidelity can drop…" (:262) | off; FL2VA default preset `alibaba-pai-fl2va-pdd-8step` (`APP/models/minimax_h3/turbo_presets.json:4-8`) | on: activates the preset's LoRA at its weight and sets steps to the preset's (`UI/components/Sidebar/MiniMaxH3TurboToggle.tsx:26-50`); Advanced then locks steps ("Turbo mode locks this preset to {{steps}} steps.", `AdvancedSettings.tsx:834-838`) | `minimax_h3_turbo_mode`, `minimax_h3_turbo_preset`, `activated_loras`, `loras_multipliers`, `num_inference_steps` |
| 5 | AI writing | "AI writing": "AI Faithful / AI Creative" (i18n:studio:866-870) | faithful | hidden for legacy (`UI/components/Sidebar/H3PromptControls.tsx:19-29`) | `minimax_h3_planning_style` (normalised in `UI/lib/h3OptionalSettings.ts:19-32`) |
| 6 | Enhance | "Plan / enhance prompt" (i18n:studio:871) | — | LLM rewrite into H3 Context-IR (`H3PromptControls.tsx:31-33`) | rewrites `prompt` |
| 7 | Scene audio | "Scene audio": "Native ambience and dialogue / Previous dialogue-only policy" (i18n:studio:872-874) | native | — (`H3PromptControls.tsx:35-43`) | `minimax_h3_audio_policy` |
| 8 | Reference sequence | "Continue references across windows" (i18n:studio:875) | off | Omni only (`H3PromptControls.tsx:44-47`) | `minimax_h3_reference_sequence` |
| 9 | Attention | "Attention": Automatic dense / SDPA / Sol-Attn / SLA (i18n:studio:876-878) | auto (fused: SLA) | (`H3PromptControls.tsx:48-57`) | `override_attention` |
| 10 | Semantic Bridge | "Semantic Bridge (experimental)" (i18n:studio:882) | alpha 0 (off) | FL2VA Pruned/Full only (`UI/lib/h3OptionalSettings.ts:3-16`) | `minimax_h3_semantic_bridge_alpha`, `_magnitude` |
| 11 | Inputs panel tiles (FL2VA, Frames) | tiles "Start", "End", injected "Frame", "Soundtrack", "Control video" (i18n:studio:116-124) | empty (= T2V) | start frame → `S`, end frame → `E`; audio tile sets `audio_prompt_type` + `audio_guide`; control video sets `K` + `video_guide` (`UI/components/Sidebar/InputsPanel.tsx:16-31,707-716`) | `image_start`, `image_end`, `image_prompt_type`, `audio_guide`, `video_guide`, injected frames |
| 12 | Omni references (Omni models) | "Omni References"; "Add images, videos, or audio"; role "Who or what is this? (helps Enhance)"; audio intent "Voice reference / Drive / reuse audio / Sound / music style"; detail "Match output / Maximum detail" (i18n:studio:600-624) | none; detail `match` | 9/3/3, total 12 (`UI/components/Sidebar/OmniReferenceSection.tsx:44-46,81-82`); ≥1 image or video required (`UI/components/Sidebar/GenerateButton.tsx:42-43`; "Add at least one image or video reference. Audio cannot be the only reference.", i18n:studio:56); video refs 2–15 s (`InputsPanel.tsx:11-13`) | `minimax_h3_references[]` `{type, path, role, audio_intent, …}`, `minimax_h3_reference_detail` |
| 13 | Prompt | placeholder "Describe your video..." or, when windows apply, "Describe the complete video idea—HocusPocus will plan {{count}} H3 windows." (i18n:studio:67,74) | "" | not blocked when empty for video (only image needs a prompt, `GenerateButton.tsx:62`); backend rejects blank (`APP/_launch_runtime.py:10962-10963`) | `prompt` |
| 14 | Prompt scheduler | "Prompt scheduler" / "Generate one video per line break" (i18n:studio:99) | off | Frames only; each line becomes its own job, submitted in order (`useStore.ts:4294-4309`) | N separate requests, `repeat_generation 1`, `multi_prompts_gen_type 2` (`:4932-4939`) |
| 15 | Resolution tier | "Resolution" (i18n:studio:1149) | `720p` (`studioConfigurationSlice.ts:124`) | buttons from `resolution_preset_order` 480p/540p/720p/768p/1080p (`UI/components/Sidebar/ResolutionPresets.tsx:17-21`; `minimax_h3_handler.py:439-525`); 1080p marked experimental | `resolution` "WxH" or `auto_<tier>` |
| 16 | Aspect | "Aspect Ratio" (hard-coded English, `UI/components/Sidebar/AspectRatioGrid.tsx:26`) | `16:9` (`studioConfigurationSlice.ts:135`) | Auto + 21:9, 16:9, 9:16, 1:1, 4:3, 3:4 (`AspectRatioGrid.tsx:4-11,20-22`) | folded into `resolution` (e.g. 720p+16:9 → `1280x704`) |
| 17 | H3 text encoder | "H3 Text Encoder", hint "Changing this reloads the H3 model." (i18n:studio:388) | `nvfp4_awq` | (`AdvancedSettings.tsx:309-329`) | `minimax_h3_text_encoder` |
| 18 | First Block Cache | "First Block Cache", threshold, warmup (i18n:studio:390) | off | not on fused | `skip_steps_cache_type`, `skip_steps_multiplier`, `skip_steps_start_step_perc` (`useStore.ts:5002-5032`) |
| 19 | Window size / overlap / lock | "Window Size", "Window Overlap" (i18n:studio:199,208) | auto-tracks duration; overlap 18 frames | lock icon; VRAM advice lines (`DurationSlider.tsx:201-344`) | `sliding_window_size`, `_overlap`, `_discard_last_frames`, `_memory_override` (`useStore.ts:4952-4982`) |
| 20 | Plan across windows | "Plan Prompt Across Windows" (i18n:studio:394) | on when windows > 1 | FL2VA only | `minimax_h3_window_storyboard`, `h3_window_prompts`, `h3_window_plan` (`useStore.ts:5538-5561`) |
| 21 | Seed | "Seed", placeholder "-1 for random", button "Random" (i18n:studio:409-410) | -1 | any integer (`AdvancedSettings.tsx:573-589`) | `seed` |
| 22 | Start image fit / preserve style | "Start image fit": "Fit with black bars · no distortion / Crop to fill canvas"; "Preserve source image style" (i18n:studio:414-417) | contain; preserve on | only with a start image (`AdvancedSettings.tsx:610-635`); preserve prepends a fixed style sentence to every line (`useStore.ts:5505-5520`) | `image_fit_mode`; prompt prefix |
| 23 | Inference steps | "Inference Steps" (i18n:studio:443) | 20 (4 fused) | 1..50, fused 4..8 (`AdvancedSettings.tsx:215,814-845`; `minimax_h3_handler.py:1915-1920`) | `num_inference_steps` |
| 24 | Guidance | "Guidance Scale" (i18n:studio:446) | 1.0 | slider 0..20 step 0.1; hidden when the model locks it (fused) (`AdvancedSettings.tsx:224-231,848-867`) | `guidance_scale` |
| 25 | Negative prompt | "Negative Prompt" (i18n:studio:462) | "" | **hidden for every H3 model** (`no_negative_prompt`; `AdvancedSettings.tsx:232-235,961-973`) | `negative_prompt` |
| 26 | MMAudio | "MMAudio (Soundtrack)" (i18n:studio:464) | off | shown for any video model, H3 included (`AdvancedSettings.tsx:976-1014`) | `MMAudio_setting`, `_prompt`, `_neg_prompt` |
| 27 | LoRAs | LoRA selector + CivitAI button "Browse LoRAs on CivitAI" | none | disabled for fused (`AdvancedSettings.tsx:1020`; `Sidebar.tsx:244-252`) | `activated_loras`, `loras_multipliers` |
| 28 | Output count | "Output Count" (i18n:studio:469) | 1 | slider 1..10 (`AdvancedSettings.tsx:1030-1041`) | `repeat_generation` |
| 29 | Voice reference (ID-LoRA) | `VoiceRefSection` | off | hidden in Frames/Extend (`Sidebar.tsx:224`) | `voice_reference`, `identity_guidance_scale` (`useStore.ts:5522-5536`) |
| 30 | Generate | "Generate"; "Preparing…"; "Queue {{count}}"; blocked labels "Need image", "Need reference" (i18n:studio:47-62) | — | blocked when an i2v-only model has no start image or Omni lacks a visual reference (`GenerateButton.tsx:40-68`) | — |

Not exposed as a control: fps (fixed 24 by the model, `minimax_h3_handler.py:1740`), batch size, H3 audio shift
(only on the legacy settings panel, `UI/components/SettingsDrawer/ModelOptionsPanel.tsx:113-133`). A separate
`h3_audio_prompt` "audio direction" field exists only in that legacy panel and in the Wizard's `audioDirection`
(`UI/features/studio/actions.ts:237`). **Duration is always edited in seconds and sent in frames.**

The Wizard's "prepare video" command is a useful minimal list of what a non-human caller needs: `prompt, modelType,
durationSeconds, resolutionPreset | resolution, aspectRatio, negativePrompt, seed, inferenceSteps, guidanceScale,
outputCount, audioDirection, turbo` (`UI/features/studio/commands.ts:6-20`; applied in `actions.ts:184-239`).

### 2.3 End to end: one text-to-video H3 press

1. **Click.** `GenerateButton.handleClick` guards double submits and calls `startGeneration(undefined,
   newUserGenerationContext())` (`GenerateButton.tsx:70-86`).
2. **Store entry.** `startGeneration` (`useStore.ts:4275`). Video is not the image command path (`:4276-4282`). The
   prompt scheduler may split the prompt (`:4294-4309`). A loaded chat LLM is unloaded to free VRAM (`:4311-4317`).
   i2v-only / Omni-without-reference guards return silently (`:4325-4342`).
3. **Params snapshot.** `params = projectStudioH3RequestParams({...state.params, generation_mode, workspace})`
   (`useStore.ts:4926-4928`). Frames come from seconds (`:4941-4950`, `UI/lib/h3ExtendedDuration.ts:75-104`,
   `alignFrameCount` `useStore.ts:668-692`). Window fields are added (`:4952-4982`). Omni fields are stripped for FL2VA
   (`:4985-4998`). A stale "references" mode with a lone start image is turned back to FL2VA (`:5058-5097`).
   `image_mode` is forced to 0 (`:5427-5429`). FL2VA drops image/video/audio refs (`:5434-5498`).
4. **Choose transport.** `prepareStudioSubmission` sends image/speech/music/SFX through typed commands but leaves
   video on the legacy path: `submit: () => api.submitGeneration(params)` (`UI/features/studio/studioSubmission.ts:
   19-45`).
5. **Placeholder.** A queued job tile is prepended before the POST ("Submitting..." or "Planning H3 windows...")
   (`useStore.ts:5564-5583`).
6. **HTTP.** `POST /api/v1/generate` with the params as JSON (`UI/api/generation.ts:216-242`). Response
   `{job_id, task_id, root_task_id, status, h3_window_plan?}`.
7. **Backend route** `generate()` (`APP/_launch_runtime.py:10923`): requires `model_type` and `prompt`
   (`:10958-10966`); resolves media (`prepare_generation_inputs`, `APP/services/wangp_submission.py:44`); normalises
   Semantic Bridge (`:10989-10993`); **may change `video_length` to fit scripted dialogue**, or refuse with a "split"
   error (`apply_h3_dialogue_duration`, `:11044-11061`; `APP/services/minimax_h3_duration.py:382-390`); validates the
   Omni manifest (`:11063-11087`) and the encoder (`:11088-11100`); bumps the sliding window past `video_length` to
   avoid a stray second window (`:11358-11423`); captures the workspace, deduplicates, persists the job and starts a
   non-daemon thread (`:11425-11476`).
8. **Deferred prep.** `_run_generation_with_preparation` runs the H3 window planner (an LLM) outside the GPU lane and
   unloads it afterwards (`APP/_launch_runtime.py:10750-10770,10906-10920`).
9. **wgp task.** `_run_generation` (`APP/_launch_runtime.py:23766`) builds `manifest = [{"id": wgp.task_id,
   "params": raw_params, "plugin_data": {}}]` (`:24442-24446`), parses it with `wgp._parse_task_manifest`
   (`:24448`), points `wgp.save_path` at the job's workspace folder (`:24474-24482`), validates each task
   (`:24614`), filters the params to `generate_video`'s signature and calls `wgp.generate_video(task, send_cmd, …)`
   (`:24631-24647`). The H3 kwargs (`minimax_h3_references`, `minimax_h3_text_encoder`, `h3_window_prompts`,
   `minimax_h3_planning_style`, `minimax_h3_audio_policy`, `minimax_h3_turbo_preset`, …) are named parameters of
   `generate_video` (`APP/wgp.py:7437-7450`).
10. **Polling.** The UI polls `GET /api/v1/status/{job_id}` every 2 s (`useStore.ts:5613-5664`;
    `UI/api/generation.ts:244`; route `APP/_launch_runtime.py:26326`).

Derived request body for "5 s, 720p, 16:9, FL2VA Pruned, no frames, Turbo off" (not captured from a live run):

```json
{"prompt": "…", "model_type": "minimax_h3", "generation_mode": "video", "workspace": "default",
 "image_mode": 0, "resolution": "1280x704", "video_length": 124, "_duration_seconds": 5,
 "num_inference_steps": 20, "guidance_scale": 1.0, "seed": -1, "negative_prompt": "", "repeat_generation": 1,
 "activated_loras": [], "loras_multipliers": "",
 "sliding_window_size": 141, "sliding_window_overlap": 18, "sliding_window_discard_last_frames": 0,
 "minimax_h3_window_storyboard": false, "minimax_h3_planning_style": "faithful",
 "minimax_h3_audio_policy": "native", "minimax_h3_semantic_bridge_alpha": 0,
 "minimax_h3_semantic_bridge_magnitude": "per_token", "skip_steps_cache_type": "", "provenance": {…}}
```

`video_length 124` is 5 s rounded up to the `17n+5` lattice (5.17 s; comment at `useStore.ts:660-667`); the window
of 141 frames comes from the auto-track rule "duration + one native step" (`DurationSlider.tsx:104-136`).

### 2.4 The typed command that the UI does not use

`generation.video` exists as a closed command shared by HTTP and MCP (`APP/routers/studio_video_commands.py:1-31`).
Version 2 admits only Wan 2.1 `t2v` (`UI/lib/videoGenerationCommand.ts:8,106`; `APP/services/
video_generation_spec.py:38-39`). **Version 3 is a typed H3/LTX shot**: `VideoV3Params` = `prompt, model_type,
resolution, video_length, sliding_window_size?, seed, num_inference_steps?, guidance_scale?, image_start?,
image_end?, audio_prompt_type "" | "A", audio_guide?, references[]?, minimax_h3_reference_detail?,
minimax_h3_extended_duration` with `extra="forbid"` (`APP/services/video_generation_v3.py:215-231`). It checks
lengths against `124+17k` and resolutions against the preset table without snapping (`:120-126,290-296`), and
assembles the same generate payload (`:428-450`). Note: v3 **FL2VA requires `image_start`**
(`video_generation_v3.py:330-336`), so plain text-to-video H3 is reachable only through the legacy route. Studio
uses the command only to clone or retry an inspected attempt (`UI/features/generation-inspector/submit.ts:43-45`).
This v3 shape is the closest existing analogue to a Hub job payload.

---

## 3. How a finished clip is presented

**Queue item.** A `GenerationJob` (`UI/types/index.ts:339-366`): `id, taskId, rootTaskId, status
(queued|waiting_resource|running|cancelling|completed|failed|cancelled), progress, step, totalSteps, phase, message,
outputFiles, error, createdAt/startedAt/finishedAt, queuePosition, taskTimings, oomInfo, h3WindowPlan,
generationDetails`. The tile exists before the POST (§2.3 step 5). On `completed` the tile is **removed** and the
gallery refreshes with the toast "New output ready"; on `failed`/`cancelled` it **stays** with the error until it
is dismissed (`useStore.ts:5646-5660`). While running, the gallery is refreshed so sliding-window partial saves
appear (`:5641-5644`). The H3 window plan rides on the job so the prompt column can show "Window n · Generating now"
(i18n:studio:94,96).

**Gallery item.** `ApiOutput` (`UI/api/outputs.ts:14-45`): `name, type ('video'…), mode, favorite, size, created_at,
completed_at, url, thumbnail_url, width, height, color, edit_sub_mode, result_kind (music_video | trailer |
series_episode | chapter), asset_id, workspace_id, path`.

**Poster frame.** Tiles never load the video. They load `/api/v1/outputs/thumbnail/{name}?size=sm|md` (≤320 / ≤640
px) (`UI/components/MainContent/galleryThumbnail.ts:4-27`). The server makes it lazily with ffmpeg at `-ss 0.1`,
falling back to the first frame, and caches it with an immutable one-year header (`APP/_launch_runtime.py:33749-33776`;
`APP/services/media_thumbnails.py:77-110,178-194`).

**Playback.** The feed card shows the poster; a click opens the details dialog with `<video controls playsInline
preload="metadata" poster=thumbnail_url>` (`UI/components/common/ImagePreviewDialog.tsx:109`). The older main
player loops with controls (`UI/components/MainContent/VideoPlayer.tsx:32-38`). Under the card a line reads
model label · resolution · seed · total generation time, then the prompt (`UI/components/MainContent/
MediaFeedItem.tsx:400-411`), loaded lazily from the sidecar (`:157-170`).

**Actions on a clip** (`UI/components/MainContent/OutputActionBar.tsx`): Save as Recipe (`:416`), Re-generate with
same settings (`:432`), Retake a time region (`:442`), Extend (`:449`), Copy prompt (`:468`), Use current frame as
reference image (`:509`), Download (`:542`), Move to workspace (`:555`), open in Video Editor (`:141`), and the pencil
"Load Settings" that restores the form from the sidecar (`:117`).

**Where files go.** Into the job's output folder: `save_path` from `wgp_config.json`, or `save_path/<workspace>` for
a named workspace (`APP/_launch_runtime.py:1056-1083`); the path is locked per job at submit time (`:11425-11426,
24474-24482`). The resolved seed is in the file name (`…_seed<N>_…`, read back by `_extract_output_seed`,
`:12370-12376`).

**Metadata kept.** One sidecar per media file, `<output>.meta.json` (`APP/services/asset_manifest.py:171-172`),
holding `params` (with the resolved seed and post-processing values), `upload_filenames`, `generation_mode`,
`job_id`, `task_id`, `root_task_id`, `generation_time`, `created_at/queued_at/started_at/completed_at`, provider,
command/workflow/run ids and project/production links (`APP/_launch_runtime.py:24499-24578,704-757`). It also
persists jobs to disk before the worker starts (`:11451-11453`) and a per-workspace task registry
(`PLAN/02-HOCUSPOCUS-FIELD-GUIDE.md:108-111`). **The Hub keeps none of this:** its worker forces `metadata_type
"none"` and a `"{date}-{seed}"` file name (`HUB/docs/architecture/parts/02-generate-image.md:417-429`). The Hub's job
card already carries a summary (`summary.seeds`, `model_id`) for the seed line, which is the only part worth
mirroring (`02-generate-image.md:144-148,402-410`).

---

## 4. Director / Trailer pipeline in one page — OUT OF SCOPE for the Hub's first module

**Inputs.** `POST /api/v1/director/pipeline/start` (`UI/api/director.ts:217-228`; `APP/_launch_runtime.py:9790`)
with the brief or song, optional reference photo ("Used to generate unique start images for each clip", i18n:director:109), `pipeline_type` (`music_video | short_film | comic_movie`; `podcast`, `viral_video` backend
only; `APP/services/director/orchestrator.py:68-74`), `video_model`, image model, `auto_mode`, `seamless`, spoken
language, LoRAs. A "Direct video · T2V only · no images" mode repeats an "Immutable master prompt" in every clip
(i18n:director:42-52).

**Stages** (status `phase`, `UI/api/director.ts:166`): `planning` → `polishing_prompts` → `preparing_direct_video`
or `generating_images` → `preview_ready` (Manual stops here) → `generating_video` → `completed` (plus `rejoin` for
repairs). In code: disk preflight, Phase 1 LLM planning, optional third-pass prompt polish, Phase 2 start images with
an art-style lock, Phase 3 video (`APP/services/director_pipeline.py:7438,7507,7641,7966,8005,8305`). A crash resumes
from saved plans and existing images (`:7379-7388`).

**How it calls the same video task.** `_submit_and_wait` builds an ordinary job dict and calls the monolith's
`_run_generation(job_id)` directly — no HTTP (`director_pipeline.py:4882-4945`, injected at `:4720-4723`). One job
carries the whole shot list: `per_clip_frames`, lists of `image_start` / `image_end`, `per_clip_minimax_h3_references`,
`per_clip_negative_prompts`, `multi_clip_concat_audio`, `per_clip_keyframes` (`:13960-14030`). The monolith expands
it into one wgp task per clip (`APP/_launch_runtime.py:24153-24418`).

**What it adds.**
- *Shot lists:* planners per type (`director/planners/short_film.py`, `music_video.py`, `comic_movie.py`) produce a
  `ProductionPlan` of `ShotPlan`s, validated and compressed (`orchestrator.py:1-12,40-47`).
- *Bounded H3 shots:* the model publishes `director_video_strategy` = `bounded_start_end` (FL2VA) or
  `omni_reference` (`minimax_h3_handler.py:1771-1786`; `APP/services/director_video_strategy.py:20-35`). Each shot is
  an independent native pass of 5–15 s; long scenes are split into valid shots before queueing (`HP/CHANGELOG.md:
  110-115,129-132`). Each shot prompt gets a self-contained context anchor (world, cast, wardrobe, blocking) instead of
  depending on an earlier render (`director_video_strategy.py:451-604`).
- *References per shot:* `_director_h3_reference_manifest` builds an ordered Omni manifest per shot from character,
  location, composition, soundtrack and voice references (`director_pipeline.py:3050-3148,13701-13778`).
- *Assembly and repair:* rerun one clip's image or video, select an attempt, rejoin with the song
  (`director_pipeline.py:2777,3249,2370,4163`); a server-owned repair job resumes batches (`:4391-4561`).
- *Trailer:* five beats share the duration — presentation 14 %, tension 28 %, escalation 30 %, reveal 16 %, close 12 %
  — snapped to bars; escalation cuts re-frame clips already generated with a different camera, "so a trailer is not
  thirty clips" (`APP/services/production_structure.py:1-12,20,92-130`). Story Lab's trailer is a 6–12 beat arc of
  15–180 s (`HP/README.md:45`).

**Ideas worth keeping for later (not module 1):**
1. **Per-clip references as a manifest.** The Hub's reference boxes could become an ordered list with a role per
   entry (identity / scene / style; voice for audio), which is exactly Omni's contract and Director's per-shot
   manifest. Start with images only.
2. **Bounded shots instead of rolling windows.** Keep every press inside one native pass (≤345 frames, 14.4 s) and
   make longer pieces by *sequencing independent shots* with a carried last frame. This avoids the window planner, the
   window-size VRAM table and the LLM storyboard in module 1.
3. **Redo one clip, then rejoin.** A clip remembers its inputs so it can be regenerated alone; joining is a cheap
   FFmpeg step, separate from generation (Director Dashboard; Video Editor).

---

## 5. Comparison: HocusPocus video control → Hub Generate Image equivalent → what is new

Hub column sources: the bar (`HUB/docs/architecture/parts/02-generate-image.md:89-106`), the LoRA sheet (`:108-131`),
the settings card (`:150-160`), the MCP settings (`:479-493`). "Blueprint" refers to
`HUB/docs/architecture/parts/08-video-blueprint.md:448-486`.

| HocusPocus control (§2.2 #) | Hub Generate Image today | New for video |
|---|---|---|
| Model picker, H3 variants (2.1) | `ModelPicker` in the LoRA sheet; MCP `model`; Card default models "Text to image" / "Reference to image" | Same picker, video catalog. The text/refs default pair maps naturally to FL2VA (`minimax_h3`) / Omni (`minimax_h3_ref2va`). Exclude legacy and `h3_advanced_*` (blueprint `models_excluded`). |
| Sub-mode tabs Frames/Multi-Shot/Extend/Blend (#1) | none | Module 1 = Frames only; no tabs. |
| Duration slider, seconds (#2) | none (the bar has Count and Size) | **New** `seconds` setting; show the snapped value ("5 s → 5.17 s, 124 frames"); lattice `17n+5`, 24 fps, 124..345. |
| Allow 30 s (#3) | none | Leave out. |
| Window size / overlap / lock, plan across windows (#19, #20) | none | Leave out: one native pass per press (§4 idea 2). |
| Turbo toggle + preset (#4) | Steps on the bar; LoRAs in the sheet | Turbo is a managed LoRA plus a step count. Module 1 can rely on Steps alone; Turbo can come later as a preset over the existing LoRA stack. |
| AI writing, Enhance (#5, #6) | the assistant writes the draft through MCP `draft`; the system prompt box is chat input | Nothing new on screen: H3 Context-IR writing belongs to the assistant. |
| Scene audio policy (#7), Semantic Bridge (#10), Attention (#9), Text encoder (#17), First Block Cache (#18) | none | Keep off the screen (engine defaults). |
| Inputs tiles: Start / End frame (#11) | 3 reference boxes on the bar; MCP `references` by character name | **New meaning** for boxes on FL2VA: box 1 = first frame, box 2 = last frame (roles, not identity). Mode follows the boxes as in the Hub (`refs` iff references). |
| Inputs tiles: injected frame, soundtrack, control video (#11) | none | Leave out of module 1. |
| Omni references image/video/audio, role, detail (#12) | 3 image boxes, character names | Images map directly (identity refs ≤ 3 boxes vs H3's 9). Video and audio references, roles and the detail switch are new; later. |
| Prompt (#13) | the draft is what renders (`02-generate-image.md:11-15`) | Same; H3 prompts carry sound and dialogue, so the draft limit (4000) may need checking against Context-IR length. |
| Prompt scheduler (#14) | none | Leave out. |
| Resolution tier 480p…1080p (#15) | Size menu in megapixels 1/1.5/2/4 | **New**: a tier menu (480p/540p/720p) replaces megapixels; W×H comes from the model's tier table, not from math. |
| Aspect (#16) | Aspect menu: auto + 1:1, 4:3, 3:4, 3:2, 2:3, 16:9, 9:16 | Reuse the menu with H3's set: auto, 21:9, 16:9, 9:16, 1:1, 4:3, 3:4 (no 3:2 / 2:3). Auto follows the first frame. |
| Inference steps (#23) | Steps on the bar; MCP `steps`; per model | Same; per-model range (1..50, fused 4..8). |
| Guidance (#24) | Guidance in the sheet and Card; MCP `guidance` only when the model has a key | H3 runs at 1.0; blueprint drops it. Expose no guidance. |
| Seed (#21) | Card seed; SeedLine under the prompt; "Seed back to random"; MCP `seed` | Same. HocusPocus records the resolved seed in the file name; the Hub records it in the job summary. |
| Negative prompt (#25) | forced `""` by the worker | Nothing: H3 has no negative prompt. |
| MMAudio (#26), Voice reference (#29) | none | Leave out: H3 makes its own stereo sound. |
| LoRAs (#27) | LoRA sheet + MCP `loras` | Same mechanism later; blueprint keeps LoRAs out of module 1. Fused checkpoints disable LoRAs. |
| Start image fit / preserve style (#22) | none | Small option or a fixed default (contain) once frames exist. |
| Output count 1..10 (#28) | Count on the bar 1..6; MCP `count` | Blueprint: one clip per press in module 1. |
| Generate + blocked labels (#30) | Generate + `blockingReason` list (`02-generate-image.md:307-317`) | New reasons: Omni needs an image (or video) reference; a fused/i2v-only model needs a first frame. |
| Queue tile, poster, playback (§3) | job line, seed line, Media screen | **New**: a poster frame per clip (ffmpeg early frame) and a player in Media; no sidecar. |

---

## Unverified

- No HocusPocus instance was run. Every request body and frame/window number in §2.3 is **derived** from the code;
  the 141-frame window and the exact key set have not been captured from a live POST.
- i18n line numbers were checked with grep; the Generate Image comparison relies on the Hub's own architecture note
  (commit 7834eb2), not on a fresh read of the Hub web code.
- The Video Editor's origin (Maestro vs HocusPocus) is inferred from its absence in the Maestro changelog and its
  "Loreframe Lab" branding; Video 2.5D/3D are inferred to predate 0.10.0 because 0.10.0 describes "new" sets for them.
  HocusPocus 0.9.0 has no itemised notes.
- That Studio's H3 path stays on the legacy `POST /api/v1/generate` was read from `studioSubmission.ts:45`; whether
  any other UI route sends H3 through `generation.video` v3 was not exhaustively searched (only the inspector clone
  path was found).
- `apply_h3_dialogue_duration` changing `video_length` server-side was read from its docstring and call site, not
  exercised.
- Director stage list and the multi-clip expansion were read from the code outline and key blocks of a 14,096-line
  file and the 37k-line monolith; branch details (seamless vs independent, comic renderer) were not traced line by
  line.
- The copy of the engine may differ: the field guide notes a "Video sidebar cleanup" and changed H3 defaults
  (4-step turbo at 864x480) that are not in this source tree (`PLAN/02-HOCUSPOCUS-FIELD-GUIDE.md:236-240`).
