# R43 — InfiniteTalk (single, multi) and LongCat Avatar 1.5 through the Hub: definitions, catalog, task, 2026-10-17

Research note building on R36 (lipsync bake-off) and R33 (local lipsync models); neither is repeated. Engine:
upstream WanGP `af2ed29` (2026-10-12), read in `/tmp/upstream`. Hub read at `32ccfb6` (2026-10-17):
`hub/worker/catalog.py`, `catalogvideo.py`, `catalogspeech.py`, `definitions.py`, `adapters/upstream.py`,
`adapters/upstream.facts.json`, `adapters/tasks.py`, `adapters/lipsync.py`, `hub/modules/generate_image/clipsound.py`.
The R36 lines this note relies on were re-read at `af2ed29`. The window plans in §3 were worked out here by calling
the engine's own pure-stdlib `build_default_window_plan` (`shared/utils/frame_scheduler.py:225`) with the inputs
shown. Nothing ran in the engine. Web: Wan2GP's issue list, issues #1971, #2073 and PR #2441 were read; GitHub search
through `gh` was refused here (session-bound). Facts only.

## 1. What the upstream definitions declare
Model types: `infinitetalk` and `infinitetalk_multi` (both `"architecture": "infinitetalk"`, so both have the base
type `infinitetalk`), and `longcat_avatar_v1_5`. Handlers: `models/wan/wan_handler.py` (family `wan`) and
`models/longcat/longcat_handler.py` (family `longcat`).

| Field (model_def unless noted) | `infinitetalk` / `infinitetalk_multi` | `longcat_avatar_v1_5` |
|---|---|---|
| defaults file | `defaults/infinitetalk.json`, `defaults/infinitetalk_multi.json` | `defaults/longcat_avatar_v1_5.json` |
| speakers flag (defaults file) | `one_speaker_only` (`infinitetalk.json:13`); `multi_speakers_only` (`infinitetalk_multi.json:13`) | neither: single and two-speaker |
| `t2v_class` | False (`wan_handler.py:206`; multitalk excluded `:48`, `:53-54`) | absent |
| `i2v_class` / `multitalk_class` | True / True (`:205`, `:207`; list `:36`) | absent / absent |
| `image_outputs` / `audio_only` | absent / absent | absent / absent |
| `image_prompt_types_allowed` | `TSVL` (`:934-935`) | `TSVL` (`longcat_handler.py:45`, `:95`) |
| `any_audio_prompt`, `returns_audio` | True, True (`:281-285`) | True, True (`:77-78`) |
| `audio_prompt_choices` | True (`:283`) | True (`:79`) |
| `audio_prompt_type_sources` | absent; the page builds `A` or `XA CAB PAB` from the speakers flag (`wgp.py:12409-12425`) | selection `A XA CAB PAB`, default `A` (`:80-85`) |
| `speaker_locations` | absent (uses `multitalk_class`, `wgp.py:7402`) | True (`:86`) |
| `image_ref_choices` | absent; `guide_custom_choices` `KI` / `RUV` / `GUV` (default `KI`) and `0` Sharp (`:629-660`) | one choice `KI`, hidden (`:87-92`) |
| `video_length_not_limited_by_audio` | absent | absent |
| `sliding_window` | True (`:350`) | True (`:43`) |
| `sliding_window_defaults` | absent | absent |
| `fps` | 25 (`:333-334`) | 25 (`:72`) |
| `frames_minimum` / `frames_steps` | 5 / 4 (`:346`) | 5 / 4 (`:41-42`) |
| `frames_maximum` | absent | absent |
| `resolution_presets` / `resolutions` / `resolution_budget` | absent | absent |
| `guidance_max_phases` | 3 (`:352`) | 1 (`:44`) |
| `audio_guidance` | True (`:966-967`) | True (`:76`) |
| `system_configs` (text-encoder group) | absent | absent |
| distill fields | — | `distill_only`, `num_distill_sample_steps` 8, sampler list `distill` only (`:102-105`) |
| LoRA folder (`get_lora_dir`) | `wan_i2v` (`wan_handler.py:127`, `:135-136`) | `longcat_avatar_v1_5` (`longcat_handler.py:29-34`) |
| profiles folder | `wan_i2v` (`:308`) | `longcat_avatar_v1_5` (`:73`) |

Factory defaults (`wgp.py:3304-3318`: `_settings.json`, then 832×480 and flow shift at `:3312-3313`, then the
handler, then the defaults file's top-level keys):
- **InfiniteTalk:** window 81, overlap 9, guidance 5.0, flow shift 7, `euler`, `video_prompt_type` `0KI`,
  `remove_background_images_ref` 0 (`wan_handler.py:1255-1265`); `image_prompt_type` `S` (`:1235-1236`); audio
  guidance 4 (`:1433-1434`); steps 30, `video_length` 81, `audio_prompt_type` `""`, `speakers_locations`
  `0:45 55:100`, 832×480 (`models/_settings.json:20-26`, `:30`). The description says "Sliding Window size must be
  81 frames" (`defaults/infinitetalk.json:12`).
- **LongCat 1.5:** window 93, overlap 13, 8 steps, guidance 1.0, audio guidance 1.0, `video_length` 93,
  `video_prompt_type` `""`, `distill` (`longcat_handler.py:201-213`); prompt and negative prompt
  (`defaults/longcat_avatar_v1_5.json:15-16`); flow shift 5.0 (`wgp.py:3313`, no `i2v_class`); 832×480.
- **LongCat steps:** not locked. A count other than 8 picks a subset of the 8 distilled sigmas
  (`models/longcat/longcat_main.py:582-584`); any sampler but `distill` raises (`:711-712`).
- **Letter meanings** (`wgp.py:12413-12419`): `A` one speaker; `XA` two speakers, auto-separated from one file; `CAB`
  two files played in a row; `PAB` two files in parallel. `B` needs `audio_guide2`; `X`/`B` read `speakers_locations`
  (`wgp.py:1319-1323`, `:7402-7404`). LongCat with a second sound builds per-speaker masks, default boxes
  `[5,10,45,90]` / `[55,10,95,90]` (`longcat_main.py:553-554`, `:870-877`).
- **LongCat's references, as read.** `fix_settings` sets `video_prompt_type` `KI` for every avatar type, unconditionally
  (`longcat_handler.py:118-120`). Every API task passes through `clean_settings` (`wgp.py:9242`, `shared/api.py:750`),
  which calls it (`wgp.py:1853`, `:3293`). With `I`, an empty `image_refs` is refused: "You must provide at least
  one Reference Image" (`wgp.py:1414-1416`). R36 §1–§2 list a start frame `S` alone as a LongCat option; by this
  code path a LongCat task also needs `image_refs`. This was not run.

## 2. What the Hub's catalog accepts, and where each model stops
A clip model reaches Generate's pulldown when `catalog.entry` returns a `kind: "video"` entry with `video` facts. The
tests, in order:
1. A definition that is a dict, is `visible`, and has no `mesh_outputs` (`catalog.py:176-177`). Both pass.
2. Not `image_outputs` (`:178`). Not a speech model: `speech_facts` needs `audio_only` (`catalogspeech.py:30-31`).
   Both pass, because neither has `audio_only`.
3. `adapter.native` (`catalog.py:183`): the facts file's `models` is keyed by base type
   (`adapters/upstream.py:221-223`). It lists only the H3 types and `viggle_animate` (`upstream.facts.json`
   `models`). Neither `infinitetalk` nor `longcat_avatar_v1_5` is there → `native` None, no `why_not`.
4. `video_facts(...)` must not be None (`catalog.py:186`), or the model is dropped. Inside it:
   - a. `image_outputs`/`audio_only` false, and `t2v_class` true or `native.clip` (`catalogvideo.py:212-214`).
     **Both stop here.** InfiniteTalk carries `t2v_class` False and LongCat carries none; neither has `native`.
   - b. "T" in `image_prompt_types_allowed`, or the reference manifest (`:217-219`). Both carry `TSVL`, so both
     would pass.
   - c. No flag ending `_sidecar` (`:220-221`). Both would pass.
   - d. `fps`, `frames_minimum`, `frames_steps`, and `frames_maximum` or `native.frames_max`, plus tiers from
     `resolution_presets` or `native.tiers` (`:222-227`). Both would fail: no `frames_maximum`, no
     `sliding_window_defaults.window_default` (what `native` reads, `upstream.py:226-228`), and no resolution field.
5. Past `video_facts`, a sound needs `video.soundtrack` (`tasks.py:193-194`; `clipsound.py:41-42`), which comes only
   from the facts file's `soundtrack` (`upstream.py:236-237`). Neither definition carries Hub-readable soundtrack
   letters.
- **Fields the definitions carry that test 4 reads:** `fps` 25, `frames_minimum` 5, `frames_steps` 4, `TSVL` (for
  `picture_refs`, a start picture: `catalogvideo.py:136-137`), and factory `sliding_window_overlap` 9 / 13. Each has
  `(overlap - 1) % 4 == 0`, so `continuation` would report a continue (`:160-167`).
- **Fields that carry the sound facts, without naming a model:** `any_audio_prompt`, `returns_audio` (the output is
  the input sound, `wgp.py:7582`), `audio_prompt_type_sources.default` `A` (LongCat only), and the speakers flags.
  The Hub reads none of these for a clip today (`catalogvideo.READS`, `:20-33`).
- **Facts the definitions do not carry:**
  - a frame maximum (the engine's API derives one from the handler's `sliding_window_size`, 81 / 93, and puts it
    in its model metadata, not in the definition: `shared/api.py:115-124`, `:827-828`);
  - resolution tiers;
  - InfiniteTalk's letter list (only its UI builds it);
  - an all-of-it flag like H3's `output_audio_is_input_audio`.
- **What `native` would add if listed:** an entry is by base type, so one `infinitetalk` entry covers single and multi.
  `identities` would read LongCat's `KI` choice as identity pictures with min 1, because there is no "" choice
  (`upstream.py:206-214`). `encoders` returns None (no `system_configs`).
- **LoRAs:** `describe` would list `<loras root>/wan_i2v` and `<loras root>/longcat_avatar_v1_5` (`catalog.py:109-126`).

## 3. A clip task: one picture + one .wav → one clip
| Key | Hub's H3 sound clip today | InfiniteTalk needs | LongCat 1.5 needs |
|---|---|---|---|
| `model_type` | the H3 type | `infinitetalk` (multi: `infinitetalk_multi`) | `longcat_avatar_v1_5` |
| `image_mode` | 0 | 0 | 0 |
| `prompt` | owner's + lip sentence (`lipsync.py:13`, `:23-35`) | any (factory: generic i2v prompt) | any (factory: the def's, `:15`) |
| `negative_prompt` | `""` forced (`upstream.py:56`) | factory `""` | factory: the def's (`:16`); the Hub's `""` replaces it |
| `resolution` | a tier size (`tasks.py:71-72`) | factory 832×480 | factory 832×480 |
| `video_length` | clip frames (`tasks.py:203-205`) | ≥ the sound's frames | ≥ the sound's frames |
| `sliding_window_size` | = `video_length` (`tasks.py:205`) | 81 (def text) | 93 |
| `sliding_window_overlap` | not sent | factory 9 | factory 13 |
| `num_inference_steps` | request (entry default) | factory 30 | factory 8 |
| `guidance_scale` | not sent for a clip | factory 5.0 | factory 1.0 |
| `audio_guidance_scale` | never | factory 4 | factory 1.0 |
| `sample_solver`, `flow_shift` | never | factory `euler`, 7 | factory `distill`, 5.0 |
| `seed`, `batch_size`, `multi_prompts_gen_type` | request, 1, `FG` | same keys | same keys |
| `image_prompt_type` + `image_start` | FL2VA `S` + path (`tasks.py:166-171`) | `S` + path, or `""` with refs | `S` + path allowed; see `image_refs` |
| `video_prompt_type` | `""`, or `I` for Ref2VA (`tasks.py:162`, `:232`) | `""` (start picture) or `0KI`/`KI` | `KI` forced by `fix_settings` (§1) |
| `image_refs` | Ref2VA only | with `KI`: one per window (`any2video.py:668-677`) | required with `KI` (§1) |
| `remove_background_images_ref` | Ref2VA only (`tasks.py:163`) | factory 0 (`no_background_removal`) | `no_background_removal` (`:94`) |
| `audio_prompt_type` | facts `soundtrack` `A` / `AS` (`tasks.py:206`) | `A`; multi `XA`, `CAB`, `PAB` | `A`, `XA`, `CAB`, `PAB` |
| `audio_guide` | the sound or its padded copy (`clipsound.py:58`, `:70-83`) | the .wav | the .wav |
| `audio_guide2`, `speakers_locations` | never | with `B` / `X` | with `B` / `X` |
| `prompt_enhancer`, `alt_prompt`, `output_filename`, `postprocess_audio` | forced (`upstream.py:56-58`) | accepted | accepted |
- All keys above are in the engine's accepted list (R36 §2, `shared/utils/setting_names.py:48-49`).
- Without `A` in `audio_prompt_type`, `audio_guide` is dropped (`wgp.py:1382-1386`). The API infers `A` from a
  supplied `audio_guide` only when the definition has `audio_prompt_type_sources` (`shared/api.py:102-111`). That
  covers LongCat, not InfiniteTalk. It infers `I` from `image_refs` only through `image_ref_choices`
  (`shared/api.py:93-99`), again LongCat only.
- An InfiniteTalk task with `image_start` and no `image_refs` uses the start picture's frame as the reference
  (`wgp.py:7845-7850`; `any2video.py:673-675`). `validate_generative_settings` strips `I`/`K` only with `V` or `L`
  (`wan_handler.py:1462-1468`).
- **Length from the sound** (both models; neither sets `video_length_not_limited_by_audio`, `wgp.py:7583`):
  `min(normalize(int(25 · seconds) + 4), video_length)` on the 5 + 4k lattice (`wgp.py:7586-7587`;
  `normalize_frame_count`, `frame_scheduler.py:16-20`). The `+ 4` adds up to one lattice step past the sound.
  - 10.0 s → 257 frames; 20.0 s → 505 frames.
  - The Hub's own length rule (`clipsound.frames`, `clipsound.py:61-67`) gives 253 and 501, which the `min` keeps.
  - InfiniteTalk embeds the whole sound at once (`get_full_audio_embeddings`, `wgp.py:7593-7596`).
  - LongCat slices it per window from `window_start_frame_no` (`longcat_main.py:530-546`, `:864-869`).
- **Window split** (`wgp.py:7612-7634`; overlap floored to `(o - 1)//4·4 + 1`, `:7374-7377`, so 9 and 13 stay):
  frames per window, as planned by `build_default_window_plan`. A start picture shares frame 1 (`wgp.py:384-386`,
  `initial_shared_frames`).

  | Sound | Frames | InfiniteTalk (81 / 9) | LongCat 1.5 (93 / 13) |
  |---|---|---|---|
  | 10 s, engine length | 257 | 4: 81, 81, 81, 41 | 4: 93, 93, 93, 17 |
  | 10 s, Hub length | 253 | 4: 81, 81, 81, 37 | 3: 93, 93, 93 |
  | 20 s, engine length | 505 | 7: 6 × 81, 73 | 7: 6 × 93, 25 |
  | 20 s, Hub length | 501 | 7: 6 × 81, 69 | 7: 6 × 93, 21 |

  - Each later window adds `size − overlap` new frames: 72 for InfiniteTalk, 80 for LongCat.
  - R36 §5's "LongCat 3 (93 + 2×80)" for 10 s holds at 253 frames. At the engine's 257 frames it is 4 windows.
  - With the Hub's `_sound` as written, `sliding_window_size` = `video_length` gives one window of 253 / 501
    frames (`tasks.py:205`). The engine floors the window to the lattice and caps it nowhere in `validate_settings`
    (`wgp.py:7371-7372`; no check found in `:1040-1560`).
  - API tasks have no 737-frame cap (that is the page's slider, R36 §1). The engine's source-frame constant is 3000
    (`wgp.py:188`).

## 4. Web, 2026-08-18 onward
- No report with a VRAM figure, a time figure or settings for InfiniteTalk or LongCat 1.5 in WanGP was found in the
  window (searches 2026-10-17).
- Wan2GP #2323 (2026-09-16, open, read): step skipping requested for LongCat Avatar, "6GB VRAM laptop, DMD 8-step";
  no reply (R36 §4).
- Wan2GP PR #2441 (opened 2026-10-10, open, read): latent save/decode/continue for Wan, LongCat, LTX2 and H3; touches
  `longcat_main.py` and `any2video.py`; no figures.
- Outside the window, for context only:
  - Wan2GP #1970/#1971 (Jul 2026, closed 2026-08-05): LongCat "You must provide at least one Reference Image" with no
    way to add one in the page; no maintainer reply shown.
  - #2073 (2026-08-05, open): LongCat 1.5 output "nothing like the reference image"; no reply.
  - A January 2026 Reddit thread: 8 s of InfiniteTalk in 20–30 min on a rented RTX PRO 6000 *(search summary)*.
- Engine changelog: "LongCat 1.5 Avatar … fast (8 steps distilled) … potentially unlimited gens using Sliding
  Windows" (`docs/CHANGELOG.md:346`). It is not dated in the line read.

## 5. Not known
- Whether a LongCat 1.5 task with only `image_start` is refused by the engine (the code path in §1 says so; not run).
- Whether one window of 253 / 501 frames runs on either model, or what it does to lipsync and VRAM.
- Whether InfiniteTalk's 480p module runs at the Hub's tier sizes (e.g. 864×480); no resolution field in either def.
- VRAM and time for either model on any GPU, in the window.
- What the model folders hold of the files R36 §3 lists.

Sources (web): [Wan2GP issues, longcat OR infinitetalk](https://github.com/deepbeepmeep/Wan2GP/issues?q=longcat+OR+infinitetalk),
[Wan2GP #2323](https://github.com/deepbeepmeep/Wan2GP/issues/2323),
[Wan2GP PR #2441](https://github.com/deepbeepmeep/Wan2GP/pull/2441),
[Wan2GP #1971](https://github.com/deepbeepmeep/Wan2GP/issues/1971),
[Wan2GP #2073](https://github.com/deepbeepmeep/Wan2GP/issues/2073),
[Reddit snapshot, InfiniteTalk speed](https://reddit.sentinel-team.org/posts/1ql7ky8/snapshots/2026-01-24T06%3A20%3A15.99052Z),
[LongCat-Video-Avatar 1.5 model card](https://huggingface.co/smartdigitalnetworks/LongCat-Video-Avatar-1.5).
