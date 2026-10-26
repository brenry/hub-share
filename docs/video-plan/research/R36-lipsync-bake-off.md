# R36 — A lipsync bake-off on the server: H3 soundtrack, InfiniteTalk, LongCat Avatar 1.5, 2026-10-17

Research note on lipsync routes, building on R33 (which models exist; not repeated).
Engine: upstream WanGP `af2ed29` (2026-10-12), read in a clone at `/tmp/upstream`. Hub read:
`hub/worker/adapters/tasks.py`, `upstream.py`, `upstream.facts.json`, `lipsync.py`,
`hub/worker/catalog.py`, `catalogvideo.py`. Web: Wan2GP's GitHub issue list and issue #2323 read; huggingface.co
and ai-muninn.com could not be fetched (proxy 403 / DNS), so model file sizes were not read and items marked
*(search summary)* are from search-result summaries. Facts only.


> Correction (R41–R45): LongCat Avatar 1.5 cannot start from a picture alone: it always asks for a reference picture (longcat_handler.py:118-120) and refuses the job without one (wgp.py:1414-1416); R43.

## 1. Inputs each route takes in the engine
| | (a) H3 kept soundtrack | (b) InfiniteTalk single | (c) LongCat Avatar 1.5 |
|---|---|---|---|
| Model type | `minimax_h3_fl2va`[`_pruned`], `_ref2va`[`_pruned`] | `infinitetalk` | `longcat_avatar_v1_5` |
| Base | H3 33B / pruned 20B | Wan2.1 i2v 14B + InfiniteTalk module | LongCat 13.6B, distilled |
| Picture | FL2VA start frame S; Ref2VA refs I | refs KI or start frame S | start frame S or anchor refs KI |
| Audio | `audio_guide`; FL2VA A, Ref2VA AS | `audio_guide`; A (1 speaker) | `audio_guide`; A (XA CAB PAB) |
| fps / frame lattice | 24 / 107 + 17k | 25 / 5 + 4k | 25 / 5 + 4k |
| Window / overlap | 362 / 18 (window 124–481) | 81 / 9 | 93 / 13 |
| Steps / guidance | 20 / 1.0, shift 12, euler | 30 / 5.0, audio 4, shift 7, euler | 8 / 1.0, audio 1.0, distill |
| Length vs sound | the task's (not limited by audio) | capped by the sound | capped by the sound |
| Default resolution | Hub tiers (480p 16:9 = 864×480) | 832×480 | 832×480 |

Citations (upstream unless `hub/`):
- **H3.** Defs: `defaults/minimax_h3_fl2va.json:4`, `_fl2va_pruned.json:4`, `_ref2va.json:4`, `_ref2va_pruned.json:4`.
  fps 24, `frames_minimum` 107, `frames_steps` 17, `frames_offset` 5, `resolution_budget` 2048×2048
  (`models/minimax_h3/minimax_h3_handler.py:577-591`). Windows 124–481, default 362, overlap 18 (`:719`, `:796`);
  Ref2VA `frames_selection_maximum` 737 (`:721`). FL2VA audio sources `""`, `A`, `K`, `2`, `A` = "Generate Video
  based on Soundtrack and Text Prompt (Soundtrack Kept)", `output_audio_is_input_audio` (`:821-835`). Ref2VA sources
  include `AS` (`:769-786`); any `S` makes the sound a kept soundtrack, not a voice reference (`:978-979`); both set
  `video_length_not_limited_by_audio` (`:787`, `:834`). Defaults: video_length 124, window 362, overlap 18, 20 steps,
  guidance 1.0, flow shift 12, euler, `audio_prompt_type` `""` (`:1236-1254`). Kept audio at output:
  `wgp.py:7916`. Prompt wording rule: R33 §1 ("How H3 itself conditions").
- **InfiniteTalk.** Def `defaults/infinitetalk.json`: module URLs (`:6-10`), `one_speaker_only` (`:13`), base
  `"URLs": "i2v"` (`:14`), "Sliding Window size must be 81 frames" (`:12`). Multitalk class
  (`models/wan/wan_handler.py:53-54`), `audio_prompt_choices`, `any_audio_prompt`, `returns_audio` (`:281-285`);
  fps 25 (`:333-334`); lattice 5 + 4k (`:346`); picture modes `KI` (default), `RUV`, `GUV`, and "Smooth"/"Sharp"
  transitions (`0`) (`:629-660`);
  `image_prompt_types_allowed` `TSVL` (`:934-935`); audio guidance on (`:966-967`). Defaults: guidance 5, flow
  shift 7, overlap 9, window 81, euler, `video_prompt_type` `0KI`, no background removal (`:1255-1265`); start-image
  mode `S` (`:1235-1236`); audio guidance 4 (`:1433-1434`); 30 steps and `audio_prompt_type` `""` from the shared
  defaults (`models/_settings.json:20`, `:30`); 832×480 (`wgp.py:3312`). No `image_refs` → the start image's frame is
  used (`wgp.py:7847-7866`; `models/wan/any2video.py:668-677`), else "Missing Reference Image" (`:674`).
- **LongCat 1.5.** Def `defaults/longcat_avatar_v1_5.json`: two URLs (`:6-9`), `reference_image_enabled`,
  `ref_img_index` 10, `mask_frame_range` 3 (`:10-13`), default prompt "A person speaking naturally with expressive eye
  contact and accurate lip sync." (`:15`), 8 steps, guidance 1.0, audio guidance 1.0, 93 frames (`:17-21`). Handler:
  lattice 5 + 4k, `TSVL` (`models/longcat/longcat_handler.py:41-46`); fps 25 (`:72`); sources `A`, `XA`, `CAB`,
  `PAB`, default `A`; `speaker_locations`; anchor `KI` hidden (`:79-96`); distill only, 8 steps, Whisper-large-v3
  encoder, DMD LoRA (`:100-112`). Defaults: window 93, overlap 13, `video_prompt_type` `""` (`:202-213`); a settings
  fix sets `KI` (`:121-123`). Help: "do not substitute new words in the prompt" (`models/longcat/infos.py:15`). A
  missing sound raises "Audio guide is required for LongCat Avatar." (`models/longcat/longcat_main.py:864-865`).
- **Shared engine rules.** With `A` and no `audio_guide`, the engine makes a silent WAV (`wgp.py:7473-7475`). For a
  model without `video_length_not_limited_by_audio`, frames = min(sound frames on the lattice, `video_length`)
  (`wgp.py:7586-7587`). `V` in `audio_prompt_type` separates vocals first (`:7539-7545`). Speaker boxes
  (`speakers_locations`) are read only with `B`/`X` (`wgp.py:1318-1323`). UI frame cap for sliding-window models:
  737 frames (`wgp.py:12672`), times `max_frames_multiplier` (`:11678-11680`).

## 2. The task the Hub sends today, and what each route would need
- **What the Hub sends (both H3 lines).** The Hub uses `A` for FL2VA and `AS` for Ref2VA, per the model picked
  (`hub/worker/adapters/upstream.facts.json` `models.*.soundtrack`; `hub/worker/adapters/upstream.py:236-237`).
  The model is the one picked in the pulldown.
- Base clip task (`hub/worker/adapters/tasks.py:229-234`): `model_type`, `image_mode` 0, `prompt`, `resolution`,
  `video_length`, `sliding_window_size`, `num_inference_steps`, `seed`, `batch_size`, `multi_prompts_gen_type`
  `FG`, `image_prompt_type`, `video_prompt_type`, plus picture keys (`:152-170`): FL2VA start frame
  `image_prompt_type` `S` + `image_start`; Ref2VA identity `video_prompt_type` `I` + `image_refs` +
  `remove_background_images_ref` (`:158-163`; letters `I`, `upstream.py:213-214`).
- Sound keys (`tasks.py:186-207`): `audio_prompt_type` (the soundtrack letters), `audio_guide` (path),
  `video_length` = shortest lattice length holding the sound, window = that length; the prompt gets the lip sentence
  (`hub/worker/adapters/lipsync.py:24-35`). Refused above `window_max` (481 frames) and with a continue
  (`tasks.py:191-200`). Short sounds padded with silence (`hub/core/sound.py`).
- `translate` adds `prompt_enhancer`, `negative_prompt`, `alt_prompt` `""`, `output_filename`, `postprocess_audio`
  `""`, keeps `audio_prompt_type` when `audio_guide` is set, and refuses a key outside the engine's
  `accepted_setting_names` (`upstream.py:56-58`, `:114-125`). The engine merges factory settings under the task
  (`upstream.py:5`), so unsent keys take the def/handler defaults in §1.
- Every key §1 lists for (b) and (c) is in the engine's accepted list (`models/_settings.json`: `audio_guide`,
  `audio_guide2`, `audio_guidance_scale`, `speakers_locations`, `image_refs`, `image_start`, `sliding_window_overlap`,
  `sample_solver`, `flow_shift`; `shared/utils/setting_names.py:48-49`).
- **Minimal task (b) InfiniteTalk, as engine keys:** `model_type` `infinitetalk`, `image_mode` 0, `prompt`,
  `resolution`, `video_length` (≥ sound frames; sound caps it), `audio_prompt_type` `A`, `audio_guide`,
  `video_prompt_type` `0KI` + `image_refs` [picture] (or `image_prompt_type` `S` + `image_start`); window 81 /
  overlap 9 and steps/guidance from the defaults.
- **Minimal task (c) LongCat 1.5:** `model_type` `longcat_avatar_v1_5`, `image_mode` 0, `prompt`, `resolution`,
  `video_length`, `audio_prompt_type` `A`, `audio_guide`, `image_prompt_type` `S` + `image_start` (or
  `video_prompt_type` `KI` + `image_refs`); 8 steps, distill, window 93 / overlap 13 from the defaults.
- **What the Hub has no adapter for.** Neither model reaches the Hub's catalog: `video_facts` returns None for a model
  with no `t2v_class` that the facts file's `models` does not list (`hub/worker/catalogvideo.py:212-214`), and
  `catalog.py:186` then drops it. `infinitetalk` has `t2v_class` False (multitalk excluded,
  `wan_handler.py:48`, `:206`); LongCat's handler sets no `t2v_class`; neither def has `frames_maximum`
  (needed at `catalogvideo.py:222-227`). So no Generate pulldown entry, no `video.soundtrack`, no `fps`/lattice for
  `tasks._sound` (`:195-197`).
- Keys the Hub never writes in a clip today: `audio_guidance_scale`, `sample_solver`, `flow_shift`,
  `speakers_locations`, `audio_guide2`, `sliding_window_overlap` outside a continue (`tasks.py:225`), the `0`/`K`
  letters, `guidance_scale` (sent for pictures only, `tasks.py:102-104`).
- `CLAUDE.md`: engine keys only in `hub/worker/adapters/`; model facts in `adapters/*.facts.json`.
- **Outside the Hub.** All three run from the WanGP page itself, where the same keys are form fields
  (`wgp.py:12403-12480` for the audio rows). R33 §1 lists the labels.

## 3. Model files and the engine's memory notes
Sizes: none stated in any def or handler.
- **H3:** `MiniMax-H3-{FL2VA,Ref2VA}[-pruned_rank8]_{bf16,int8_convrot}.safetensors`; video VAE fp16; audio VAE
  fp32; latent upscaler; Qwen3-VL-32B layer-50 text encoder (bf16, quanto int8, other variants).
- **InfiniteTalk:** `wan2.1_infinitetalk_single_14B_{mbf16,quanto_mbf16_int8,quanto_mfp16_int8}` plus the base
  `wan2.1_image2video_480p_14B_*` (same three); umt5-xxl; CLIP xlm-roberta-large; Wan2.1 VAE; `chinese-wav2vec2-base`.
- **LongCat 1.5:** `longcat_avatar_v1_5_{bf16,quanto_bf16_int8}`; `longcat_avatar_v1_5/dmd_lora.safetensors`;
  umt5-xxl; `whisper-large-v3`; `Wan2.1_VAE_bf16`.

- Sources: `defaults/*.json` above; `defaults/i2v.json:7-11`; H3 `minimax_h3_main.py:24-30`,
  `minimax_h3_handler.py:30-31`, `:1079-1103`; Wan `wan_handler.py:1004-1024`, `models/wan/multitalk/assets.py:5`,
  `multitalk.py:151-155`; LongCat `longcat_handler.py:110`, `:134-157`.
- Hub rule: nothing is downloaded (CLAUDE.md); the worker refuses every fetch, naming the file
  (`upstream.py:285-287`). Each route's files must already be in the model folders.
- Engine memory: profiles 1, 2, 3, 4 (recommended), 4+, 5 (`wgp.py:11702-11708`). README (2026-10-07, v17.17,
  MMGP v4): "15 seconds of H3 video at 1080p used to require 25 GB of VRAM, now you just need 11 GB … only 5-6GB …
  at 480p"; Profile 4 "up to 50% less VRAM" (`README.md:100-108`). H3 handler tags pruned "lighter", full "large"
  (`minimax_h3_handler.py:574`). No per-model figure for InfiniteTalk or LongCat 1.5 in the engine.
- Accelerator presets: `profiles/wan_i2v` (FusioniX 10 steps, lightx2v 4 steps, guidance 1, audio guidance 1) apply
  to InfiniteTalk (`wan_handler.py:307-308`, `wan_i2v` for the i2v class); "Infinitetalk works with all the Loras
  accelerators" (`docs/CHANGELOG.md:1248`). H3: `profiles/minimax_h3*` Turbo presets. LongCat 1.5: no profile folder.

## 4. VRAM / time figures published 2026-08-18 onward
- **H3:** engine README, 2026-10-07 (above). ai-muninn series on one RTX 5090 (not WanGP): 15 s at 1344×768 in
  518 s; two-character clip in 437 s; post dates not known *(search summary)*; its 864×480 10 s / 175 s post is
  dated 2026-08-04, outside the window *(search summary)*. No figure for a kept-soundtrack run found.
- **InfiniteTalk:** not found in the window. Search returned only undated tutorial guidance (≥ RTX 4090 recommended;
  8 GB+ claimed elsewhere) *(search summary)*.
- **LongCat Avatar 1.5:** not found in the window. Wan2GP issue #2323 (2026-09-16, read): a request for step
  skipping "Use case: 6GB VRAM laptop, DMD 8-step inference"; no figure, no reply. Release coverage (May 2026,
  outside the window): "10-second video … about 1 minute", GPU not named *(search summary, ithome.com)*.
- Wan2GP issue list for `longcat OR infinitetalk` (read 2026-10-17): no VRAM or time figure in any title; the only
  GPU named is a 5070 Ti (PR #1950, closed 2026-07-02). Reddit not reachable here.

## 5. Same-inputs test matrix: constraints
Held equal by choice: one picture, one `.wav`, one seed, one resolution where allowed. What each route does with them:
- **Frame rate.** H3 24 fps; InfiniteTalk and LongCat 25 fps. Same seconds → different frame counts.
- **Length lattice.** H3 107 + 17k frames (4.46 s minimum, 0.71 s steps); the other two 5 + 4k (0.16 s steps).
  The Hub's H3 clip is the shortest lattice length holding the sound, padded with silence; the other two stop
  at the sound's frames on their lattice (`wgp.py:7586-7587`).
- **Length cap.** Hub H3: one window, ≤ 481 frames (20.0 s). InfiniteTalk / LongCat: sliding windows, so a sound
  longer than one window runs several (81 / 93 frames, overlap 9 / 13); UI cap 737 frames (29.5 s at 25 fps).
  Arithmetic for a 10 s sound (250 frames): InfiniteTalk 4 windows (81 + 3×72), LongCat 3 (93 + 2×80), H3 1.
  Only a sound ≤ 3.24 s fits one InfiniteTalk window; ≤ 3.72 s one LongCat window; ≥ 4.46 s is one H3 window.
- **Picture role.** FL2VA: the picture is frame 1. Ref2VA: an identity reference (not frame 1). InfiniteTalk: a
  reference per window (`KI`) or start frame. LongCat: start frame, or anchor reference `KI` at `ref_img_index` 10.
- **Resolution.** H3 block 32, budget 2048×2048; Wan / LongCat block 16. 832×480 is a multiple of 32 and of 16;
  the Hub's H3 480p 16:9 tier is 864×480 (`upstream.facts.json` `tiers.h3`), not 832×480. InfiniteTalk's module is
  the 480p model (`defaults/infinitetalk.json:3`).
- **Sound in the output.** H3 keeps the `.wav` as the clip's audio (§1). InfiniteTalk / LongCat `returns_audio`;
  the original file is the output (`wgp.py:7582`), unless padded or combined (`:7601`).
- **Prompt.** H3 needs the lip-sync wording (Hub adds it, `lipsync.py`); LongCat ships its own default prompt;
  InfiniteTalk the engine's generic i2v prompt. A same prompt is accepted by all three; its effect differs by model.
- **Steps.** 20 (H3), 30 (InfiniteTalk), 8 locked distill (LongCat); accelerator presets change H3 / InfiniteTalk.
- **Through the Hub:** only route (a) runs today; (b) and (c) run only from the WanGP page (§2).

## 6. Not known
- File sizes of every URL in §3 (huggingface.co not reachable here).
- Any VRAM or time figure in the window for InfiniteTalk or LongCat 1.5, on any GPU; any for H3 with a kept
  soundtrack.
- Whether the 737-frame cap applies to an API task, or only to the WanGP page's slider.
- Whether 864×480 runs on the 480p InfiniteTalk model as well as 832×480.
- Which H3 model is picked for the bake-off (FL2VA `A` or Ref2VA `AS`).
- How the three compare in lipsync on the same inputs (R33 §4).

Sources (web): [Wan2GP issues, longcat OR infinitetalk](https://github.com/deepbeepmeep/Wan2GP/issues?q=longcat+OR+infinitetalk),
[Wan2GP #2323](https://github.com/deepbeepmeep/Wan2GP/issues/2323),
[ai-muninn H3 on RTX 5090 series](https://ai-muninn.com/en/blog/series/minimax-h3-on-rtx-5090),
[ithome LongCat 1.5 release](https://www.ithome.com/0/953/861.htm),
[Next Diffusion InfiniteTalk tutorial](https://www.nextdiffusion.ai/tutorials/create-lip-sync-videos-from-images-with-infinitetalk-in-comfyui),
[DEV Community InfiniteTalk](https://dev.to/localfaceswap/infinitetalk-unlimited-digital-human-generation-with-local-privacy-protection-4lgj).
