# R16 — What upstream WanGP wants for the Hub's pictures and H3 clips (for Stage 9 step 5)

Status: 2026-10-14, research only. Read from upstream WanGP `af2ed29` (v18.05,
settings_version 2.80; `UP:`, read in full; `W:` = `UP:wgp.py`, `H:` = `UP:models/minimax_h3/minimax_h3_handler.py`),
the fork (`FK:`) and the repo at `cf89e60` (`HUB:`). It extends R9 §2 and §5 with the exact keys. Everything here is
from reading code. The real capture (the Stage 10 upstream note, retired) confirms or corrects it.

## 1. How upstream checks a task (every family)

**The checks run in this order:** `submit_task` → `_normalize_task` → `run_cli_job` → `validate_task`
(`UP:shared/api.py:835-838`, `UP:shared/api_cli.py:149`). Factory settings are merged under the task by upstream
itself (W:1847-1859), so `factory_underneath = False` is right.

**Unknown keys are refused** (W:1047-1049). The accepted keys are:
- the keys of `UP:models/_settings.json`;
- `NON_SETTING_KEYS` (`model_type`, `settings_version`, `mode`, `priority`…);
- `DEPRECATED_SETTING_KEYS`, ignored silently (`MMAudio_setting` is one) (`UP:shared/utils/setting_names.py:17-29,
  :48-71`).

The error reads "Unknown setting(s): … Model-specific options belong in custom_settings", at stage `validation`
(`api_cli.py:149-153`). The adapter should assert its keys against `setting_names.accepted_setting_names()` before
submitting.

**Every Hub task is resolution-capped.** The session marks every task `plugin_data["api"]`
(`UP:shared/api.py:1039`), so `validate_agent_resolution` runs on it (W:9246-9250;
`UP:shared/resolutions.py:499-511`).
- The ceiling is the model's `resolution_budget`, else `DEFAULT_RESOLUTION_BUDGET = "1920x1088"`, which is
  2,088,960 px (`resolutions.py:12`, `:514-521`). The fork has no such check.
- Audio-only models are exempt (:501).

**Side files** (`return_side_files`, `UP:shared/api.py:1039`) are returned in memory and not written beside the media
(`UP:shared/utils/side_files.py:23-28`). The outbox gets the main file only.

## 2. Pictures

| Item | Upstream (evidence) | Hub today / rule |
|---|---|---|
| Ids | Flux 2 Klein (`flux2_klein_9b`, `_4b`, `_base_9b`, `_base_4b`) and Krea 2 (`krea2_raw`, `_turbo`, `_raw_edit`, `_turbo_edit`): same as the fork. Qwen Image 2.1: only `qwen_image_21_7B` and `qwen_image_21_turbo_7B`. | Map the fork's `qwen_image_21` to `qwen_image_21_7B`. The fork's other Qwen 2.1 variant ids (bf16, gguf and the rest) have no match. |
| Size cap | Klein and Qwen 2.1 have no budget, so 2.09 MP. Krea 2 is `2048x2048`, 4.19 MP (`UP:models/krea2/krea2_handler.py:73-74`). | The Hub's 4 MP choice (`HUB:hub/modules/generate_image/screen.py:24`) is refused for Klein and Qwen. The catalog publishes each model's budget, and the size menu hides sizes above it. |
| Block | Qwen 2.1 refuses sides that are not multiples of 32 (`qwen21/pipeline.py:225-226`); Krea 16. | The catalog's `block` already carries it. |
| Guidance | Klein distilled: none, forced to 1 (`flux_main.py:299`). Klein base: `guidance_scale` 4. Krea raw 3.5 and raw_edit 2; turbo none. Qwen 2.1: `guidance_scale` 4 (turbo 1) (`qwen21_handler.py:160-163`). | Send only the catalog's `guidance_key`. Read defaults from `get_factory_settings`, never from stored fork values (Qwen's fork default was 1). |
| Steps | Klein 4 (base 30); Krea per definition; Qwen 2.1 40. **Qwen Turbo must be exactly 8**, or it raises (`qwen21/schedulers.py:11-12`), and the definition publishes no lock. | The facts file locks Qwen Turbo at 8. |
| References | `image_ref_choices` "", KI, I on all three. Sending `image_refs` with no "I" letter makes upstream infer "KI" (`UP:shared/api.py:93-99`). | Send `video_prompt_type` "I" with `image_refs` (absolute paths) in box order. Send "" and no `image_refs` for New. |
| Reference caps | Qwen 2.1 at most 10, control image included (`pipeline.py:223-224`). Krea edit 2 (1 in image mode 2) (`krea2_handler.py:236-240`); raw and turbo strip references (W:3283-3284). Klein none. | `ref_caps` prefixes still match (`"qwen_image_21"` against `qwen_image_21_7B`; longest prefix, `HUB:models.py:75-80`). |
| Cut-out | `remove_background_images_ref` 0 or 1, task-wide; Flux forces it off (W:7181). | As today. |
| LoRAs | `activated_loras` are paths relative to the family folder, searched recursively (W:3926-3936), or absolute (:3837). Folders: `flux2_klein_9b`, `flux2_klein_4b`, `krea2`, **`qwen21`** (fork: `qwen`) (`UP:models/qwen/qwen_handler.py:143-146`). | Send the Hub's names as relative paths, never basenames (the fork adapter's basename rule is fork-only). Qwen 20B LoRAs do not load on 2.1. |
| Multipliers | Space-separated floats; `;` separates phases; `,` gives per-step values (`UP:shared/utils/loras_mutipliers.py:5-13`). | Unchanged. |
| `multi_prompts_gen_type` | "FG" natively; the integer 2 is normalised to "FG" (`UP:shared/utils/prompt_parser.py:10-20`). | Send "FG". The fork adapter's "FG"→2 is fork-only. |
| `output_filename` | "{date}-{seed}" is supported (`UP:shared/utils/filename_formatter.py:61-75`). | `FORCED_TASK` unchanged. |

## 3. H3 clips

### 3.1 Model map (keep it in `upstream.facts.json`)

| Fork type (Hub role) | Upstream type |
|---|---|
| `minimax_h3` (First / Last, pruned, Comfy fp8) | `minimax_h3_fl2va_pruned` |
| `minimax_h3_full` | `minimax_h3_fl2va` |
| `minimax_h3_ref2va` (Omni, pruned) | `minimax_h3_ref2va_pruned` |
| `minimax_h3_ref2va_full` | `minimax_h3_ref2va` |
| `*_fused_turbo` (4-step) | none. Nearest: `*_pruned_pdd` at 8 steps. Otherwise give it a `why_not`. |

- **Name trap:** upstream's `minimax_h3_ref2va` is the full 33B model, not the fork's pruned Omni.
- **Weights:** bf16 or int8 is chosen by server config `transformer_quantization`, not per task (W:3084-3110, :3455).

**Roles come from the map, not from letters.** Upstream lists "S" (start frame) for Ref2VA too, so letters would offer
Omni as a start-frame model (R9 §5).

### 3.2 Pictures in a clip

| Hub feature | Upstream keys (evidence) |
|---|---|
| Text only | `image_prompt_type ""`, `video_prompt_type ""` (W:1486-1509) |
| Start frame | `image_prompt_type "S"`, `image_start` (absolute). |
| Start + last | `"SE"`, `image_start`, `image_end`. `"E"` alone is also accepted (H:723, :798). |
| Fitting the start frame | `image_fit_mode` is **refused** upstream. Fitting is global server config `fit_canvas`: 0 = the picture's aspect at the pixel budget (default), 1 = fit inside, 2 = crop to exact WxH (`UP:shared/utils/utils.py:670-693`; W:7492, :7847). See §4, rule 6. |
| Continue | `image_prompt_type "V"`, `video_source` (absolute), `keep_frames_video_source ""`, `sliding_window_overlap 18`, `sliding_window_size` = N + 17; the output holds the source plus the new frames (H:715-722; W:1375, :1540). Ref2VA can continue too. |
| Identities | Ref2VA type, `video_prompt_type "I"`, `image_refs` = paths in box order, at most 9 images and 12 files (H:109, :724-732, :985-986). "KI" sizes the output from the first image; "FI" injects frames. |
| Per-reference name or intent | **No field exists.** Pictures are numbered: start, end, injected frames, then references. The prompt binds them as `<Picture N>` (H:109, :173, :179). The fork's `character_name` and `image_intent` have no upstream place. |
| Reference detail | Task-wide `image_refs_relative_size`, 50 to 400 (% of the output's pixel budget), default 100 (H:737-738, :1256; `pipeline.py:593-602`). The fork's "max" meant a 2048 px short edge. |
| Cut-out | Task-wide `remove_background_images_ref` 0 or 1 (Ref2VA default 0); FL2VA ignores it (H:817). Per-box cut-out has no upstream form. |

### 3.3 Length and passes

- **Frames.** Lengths are 17k + 5 with k ≥ 6: 107, 124, 141 … 362 … 481 (`frames_minimum` 107, `frames_steps` 17,
  `frames_offset` 5; H:581-583). There is no `frames_maximum` key. The fork's lattice was 124 to 345, step 17.
  - `video_length` may be an integer, or a string like "10s" (rounded to the lattice; `api.py:127-155`,
    `frame_scheduler.py:16-41`). fps is 24.
- **Windows.** `sliding_window_size` runs 124 to 481, default 362; overlap 1 to 120 on the 17n+1 lattice, default 18
  (H:719-720, :796-797, :905-908; `shared/extra_settings.py:334-348`).
- **One pass has no switch upstream** (the fork's `*_multi_window` is refused). A request is one pass when the
  default plan has one window (W:7621-7633; `frame_scheduler.py:225-246`):
  - text, S or SE: `video_length ≤ sliding_window_size`;
  - continue: `sliding_window_size ≥ video_length + overlap − 1`.
  - Also needed: no `[/…]` slash commands in the prompt, and `multi_prompts_gen_type` "FG".
  - The Hub sets `sliding_window_size = max(124, video_length)`. No upstream code shrinks windows.
- **Maximum per pass.** 481 frames (20.0 s) is the hard limit; the official range is 4 to 15 s, so 362. Upstream's
  schema publishes `frames_maximum` = 362 (H:106; `api.py:115-124`).
- **`duration_seconds`** applies only to the speech preset; H3 video ignores it.

### 3.4 Size, encoder, audio, sampling

- **Size.** `resolution "WxH"`, floored to multiples of 32 (`vae_block_size` 32; H:584-585, W:7185-7187).
  - There are no `resolution_presets`: any WxH passes, within the budget of 2048×2048, 4.19 MP (H:591-592; enforced
    for the Hub per §1).
  - The size tiers are the Hub's own, in the facts file.
- **Text encoder: per task.** The setting is `config = "<encoder>,<video VAE>,<DiT priority>,<user config>"`, with
  trailing commas dropped (H:690-709; `UP:shared/config_groups.py:2-38`; W:7140-7141, :7212-7222).
  - Encoder ids are the fork's: `bf16`, `int8`, `nvfp4_awq`, `gguf_q4_k_m`, `gguf_q2_k`. VAE ids: `bf16`, `fp8mix`,
    `int8_convrot`, or "" for Auto.
  - **An unknown id is reset to the default silently,** so the adapter validates ids itself.
  - A change of `config` reloads the model (W:4167-4170).
  - With no `config`, upstream uses [BF16, INT8] and picks by server `text_encoder_quantization` (default int8). The
    fork's default was `nvfp4_awq`.
- **Audio.**
  - H3 makes joint 32 kHz stereo audio by default (`returns_audio`, H:649). `audio_prompt_type ""` is that default
    on both FL2VA and Ref2VA (H:1251), so `FORCED_VIDEO`'s first key changes nothing.
  - `MMAudio_setting` is a deprecated key (accepted, ignored). The upstream equivalent is `postprocess_audio ""`.
  - For V3 later: FL2VA `"A"` keeps `audio_guide` as the soundtrack; Ref2VA `"AS"` or `"KS"` keep one (H:821-833,
    :769-785).
- **Sampling.**
  - Steps: default 20; PDD and VDN 8, and PDD forces euler (H:900-904, :1236-1256).
  - `guidance_scale` default 1.0, validated ≥ 1: do not send it.
  - `guidance_phases` 2 means two-phase or tiled refinement, not CFG.
  - `sample_solver`: euler, res_multistep or ralston_2s.
  - `image_mode` 0; `batch_size` 1.
  - `multi_prompts_gen_type` must be sent as "FG": H3 does not override the global "PG", and "G" or "PG" with a
    multi-paragraph prompt is refused (W:1083).

## 4. Translation rules for the upstream adapter

1. **Keys.** Assert every key against `accepted_setting_names()` before `submit_task`. Never send a fork key:
   `minimax_h3_multi_window`, `minimax_h3_text_encoder`, `minimax_h3_references`, `minimax_h3_reference_detail`,
   `image_fit_mode`, `MMAudio_setting`.
2. **Pictures:**
   - `multi_prompts_gen_type "FG"`;
   - references as `video_prompt_type "I"` plus absolute `image_refs`;
   - `activated_loras` as the Hub's relative names;
   - only the catalog's guidance key;
   - the size checked against the model's budget;
   - Qwen Turbo at 8 steps.
3. **Clip models** by the §3.1 map; the role comes from the map.
4. **Length:** `video_length` on 17k+5 (107 to 481; the menu offers up to 362); `sliding_window_size =
   max(124, video_length)`. Continue: overlap 18, window N + 17.
5. **Size:** `resolution "WxH"` with both sides multiples of 32, within 4,194,304 px. The tiers come from the facts
   file.
6. **The start frame's fit.** Recommended: `wgpconfig.FORCED_CONFIG` gains `fit_canvas: 2` (crop to exact WxH), the
   fork's per-task "crop".
   - It is global. Check it with one picture with references and one start-frame clip.
   - If picture references change, crop `image_start` and `image_end` to WxH in the worker instead (Pillow is in the
     engine env) and leave `fit_canvas` alone.
7. **Identities:**
   - Ref2VA type, `video_prompt_type "I"`, `image_refs` in box order (≤ 9), `image_prompt_type ""`.
   - `remove_background_images_ref` is 1 only when every box is cut out. Mixed boxes are refused in one line, since
     upstream has one switch.
   - `image_refs_relative_size` 100 for "match". For "max", the capture's first identity run sets the value
     (between 150 and 400).
8. **Names:** nothing in the task binds a picture to a name. Upstream reads `<Picture N>` in the prompt. The Hub
   adds no words to the prompt (invariant 6), so the binding is the assistant's: the system prompt block
   (`system-prompt-video-paragraph.md`) gains a line on writing `<Picture 1>`… for the boxes, in box
   order.
9. **Encoder:** `config = "<id>"` when the request names one, from the catalog's ids; omit it otherwise. Refuse an id
   not in the model's `system_configs` (upstream would reset it silently).
10. **Audio:** `audio_prompt_type ""`, `postprocess_audio ""`; drop `MMAudio_setting`.
11. **Sampling:** `num_inference_steps` always (20; 8 for PDD and VDN), `image_mode 0`, `batch_size 1`, an integer
    `seed`, no guidance.
12. **Catalog.** `video_facts` returns None for upstream H3 today (no `t2v_class`, `frames_maximum` or
    `resolution_presets`; `catalogvideo.py:205`, :214-218). The upstream adapter supplies the missing facts from its
    facts file: lattice max 362 (hard 481), tiers, the role by type and the encoder ids. Then H3 is listed.

## 5. Today's golden fixtures, read by upstream (`HUB:tests/fixtures/adapters/tasks-upstream.json`)

- **Refused as unknown:**
  - `minimax_h3_multi_window` (every clip);
  - `minimax_h3_text_encoder` (every clip);
  - `minimax_h3_references` and `minimax_h3_reference_detail` (identity);
  - `image_fit_mode` (start and end).
- **Do not exist upstream:** `model_type` `minimax_h3` and `minimax_h3_fused_turbo`. `"minimax_h3_ref2va"` silently
  means the 33B full model.
- **Identity:** the fixture has `video_prompt_type ""` and no `image_refs`, so Ref2VA would run without references.
- **The picture fixture** (Klein 9B) is accepted. Its `guidance_scale` would not be sent by the real Hub, and the
  engine ignores it.
- **`catalog-upstream.json` is belief.** Its version reads 17.17 against the real 18.05. Klein 9B's factory guidance
  is 1 against a real 5 (`UP:models/_settings.json:37`), and Krea turbo edit's resolution is 832×480 against a real
  1024×1024. The real capture replaces it.

## Needs the real capture

- Each type's `get_factory_settings` at 18.05; whether `deps.get_local_model_filename` exists upstream (the catalog's
  presence check uses it; R9 lists it as fork-only).
- The exact refusal text and stage for the size cap and for an unknown key, and how `faults.py` maps the
  `validation` stage.
- The value of `image_refs_relative_size` that matches the fork's "max", and identity fidelity with "I" and
  `<Picture N>` in the prompt.
- What `fit_canvas: 2` does to picture references.
- VRAM for one pass at 362 and 481 frames on the server's GPU. Upstream has no memory policy that shrinks windows.
- Whether the Qwen 2.1 LoRAs of the LoRA folders (fork `loras/qwen`) are 7B ones.
