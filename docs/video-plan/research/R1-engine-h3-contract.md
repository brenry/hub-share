# R1 — The engine's MiniMax H3 contract (as the Hub's worker would drive it)

Read-only research. Scope: how the HocusPocus engine (Wan2GP 10.9875 lineage, `HP:wgp.py:103-104`) runs MiniMax H3
when a task arrives through `session.submit_task`, which is exactly the call the Hub's worker makes
(`hub/worker/wan2gp.py:258`). It extends and corrects `docs/architecture/parts/05-engine-lineage.md` §5.5 and
`parts/08-video-blueprint.md` §1; facts already stated there are not repeated unless corrected.

Path prefixes: `HP:` = the HocusPocus checkout's `app/` folder; `UP:` = the upstream Wan2GP checkout
(commit `6479db36`); Hub paths are relative to the repository root (commit 1a527f8). "Fact" = read in code at the cited line. "Proposed" = design, not built.

---

## 0. The path a task takes (Fact) — and what that means for H3

1. The worker builds `params = factory ⊕ hub settings ⊕ FORCED_TASK` (legacy flavour, `hub/worker/wan2gp.py:47-59`;
   HocusPocus has no `list_model_defs`, so it is "legacy", `:209`). For H3 the factory is `primary_settings`
   (`HP:models/_settings.json`), then `update_default_settings` (`HP:models/minimax_h3/minimax_h3_handler.py:2224-2261`),
   then the defaults-file settings (`hub/worker/catalog.py:60-76`).
2. `submit_task` wraps the dict as `{"id", "params", "plugin_data"}` and copies `prompt` up
   (`HP:shared/api.py:729-747`). Paths under `ATTACHMENT_KEYS` are made absolute against the caller's cwd
   (`HP:shared/api.py:806-834`; key list `HP:wgp.py:114-115`). **`minimax_h3_references` is not an attachment key**:
   its paths are used as given, so they must already be absolute (the worker's cwd is the engine root, `wan2gp.py:191`).
3. `validate_task` lays the params over `primary_settings` again and calls `validate_settings`
   (`HP:wgp.py:10145-10162`), which ends with the H3 handler's `validate_generative_settings`
   (`HP:wgp.py:1334-1338`). Any refusal is reported through `gr.Info(...)`; the session only emits
   **"Task 1 failed validation"** (`HP:shared/api.py:482-492`). The Hub never sees the engine's reason.
4. Only keys that are parameters of `generate_video` survive (`HP:shared/api.py:456`, `:497`). Unknown keys are dropped
   silently — but keys read during validation (e.g. `sliding_window_memory_override`) still act, because
   validation sees the whole dict.
5. Prompt pre-processing (`HP:wgp.py:799-820`): the prompt goes through `prompt_parser.process_template`, which
   **drops every line starting with `#`, treats a line starting with `!` as a macro, and removes empty lines**
   (`HP:shared/utils/prompt_parser.py:46-54`). H3 sets `single_block_prompt: True` (handler `:1753`), so the
   multi-line three-field prompt stays one prompt (`HP:wgp.py:817-820`); the worker's `multi_prompts_gen_type: 2`
   does the same (`wan2gp.py:56-57`; `HP:wgp.py:10157`). The runtime refuses anything but one string
   (`HP:models/minimax_h3/minimax_h3_main.py:1514-1515`).
6. The prompt enhancer can run only when `prompt_enhancer` is non-empty **and** `enhancer_mode == 0`
   (`HP:wgp.py:8380-8389`). The Hub forces both off (`wan2gp.py:38-44`). H3's own `prompt_enhancer.py` only holds
   system prompts for that same enhancer; nothing else calls it on this path. (Resolves 08 §1.7's open point.)

---

## 1. The task dictionary

### 1.1 Keys the engine reads for H3 (Fact)

| Key | Value for H3 | What the engine does with it |
|---|---|---|
| `model_type` | an id from §2 | required (`HP:wgp.py:10148-10151`) |
| `image_mode` | `0` | `> 0` would make it an image task (`HP:wgp.py:7504`, `:784`) |
| `prompt` | §3 | must be non-empty after template processing (`HP:wgp.py:805-809`) |
| `resolution` | `"WxH"`, both multiples of 32, or `auto_480p…auto_1080p` | floored to the 32 block (`HP:wgp.py:7707-7708`); `generate` raises on a non-multiple (`minimax_h3_main.py:1516-1517`). `auto_*` takes the start image's aspect within the tier's pixel budget, else the tier's fallback (`HP:wgp.py:840-885`, `:7645-7705`; budgets handler `:526-541`) |
| `video_length` | 124…345 on 17n+5 | rounded **up** to the lattice and clamped to the pass maximum (handler `:2593-2603`); a value above max+1 is kept as a multi-window total (`:2601-2602`) |
| `sliding_window_size` | = `video_length` for one pass | aligned and clamped to 124…345 (handler `:2605-2617`), then **may be shrunk** by the VRAM policy (§1.3) |
| `minimax_h3_multi_window` | `False` for the primitive | caps `video_length` to the window, before and after the VRAM policy (handler `:2618-2625`, `:2682-2689`); `generate_video` default is `True` (`HP:wgp.py:7450`) |
| `sliding_window_overlap` | leave (factory 18) | normalised to 17n+1 (handler `:2626-2632`, `:285-306`) |
| `num_inference_steps` | 20 (1–50); fused 4–8 | fused: refused outside 4–8 (handler `:2422-2428`, `:111-136`); runtime needs ≥2 grid points, turbo LoRA ≥4, PDD LoRA exactly 8 (`minimax_h3_main.py:1538-1560`) |
| `seed` | int; `-1` = engine draws | passed to `generate` |
| `batch_size` | 1 | forced to 1 for video anyway (`HP:wgp.py:7517-7518`) |
| `force_fps` | `""` | fps = model's 24; `generate` raises on any other fps (`minimax_h3_main.py:1519-1523`) |
| `image_prompt_type` | `""` text; `"S"` first; `"E"` last; `"SE"` both | `S` needs `image_start` (`HP:wgp.py:1205-1228`); `E` needs `image_end`, allowed alone because `end_frames_always_enabled` (handler `:1796`; `HP:wgp.py:1230-1249`). Omni allows none (handler `:1795`) |
| `image_start` / `image_end` | absolute image path, or a list of them | `clean_image_list` accepts a path or list (`HP:wgp.py:289-296`, `:940`); only the first start image is kept (`:1300`) |
| `image_fit_mode` | `""` or `"crop"` | default `fit_canvas` 1 fits the output canvas to the start image's aspect; `"crop"` crops the image to the requested canvas instead (`HP:wgp.py:8058-8065`) |
| `video_prompt_type` | `""` | FL2VA letters `GV` (control video), `KFI` (timed frames), `A`/`NA` (mask) (handler `:2032-2053`, `:2455-2575`) |
| `audio_prompt_type` | `""` | FL2VA: `A` soundtrack (`audio_guide`), `K` control-video audio, `2` keep video + new audio (handler `:2057-2069`); all need extra inputs (`:2506-2553`) |
| `activated_loras`, `loras_multipliers` | `[]`, `""` | LoRA folder `<lora_root>/minimax_h3` (handler `:2094-2095`); fused refuses any LoRA (`:2437-2447`) |
| `minimax_h3_text_encoder` | `nvfp4_awq` (default) \| `gguf_q2_k` \| `gguf_q4_k_m` \| `int8` \| `bf16` | picks the Qwen3-VL file (`HP:wgp.py:7547-7563`, `:4345-4367`); unknown value raises (`:4351-4355`); a change reloads the model (`:7553-7563`) |
| `minimax_h3_references` | Omni only, §1.5 | passed to the model only for `omni_reference` models (`HP:wgp.py:9080-9083`) |
| `minimax_h3_reference_detail` | `"match"` \| `"max"` | Omni only (handler `:2007-2011`) |
| `override_attention` | `""`; fused `"sla"` | fused forces `sla` unless `sdpa` (handler `:2435-2436`); `sol`/`sla` fall back to `sdpa` where unsupported (`HP:services/h3_runtime_policy.py:199-205`) |
| `minimax_h3_extended_duration` | absent | `True` lifts the pass maximum to 719 (`HP:models/minimax_h3/duration.py:5`, `:9-34`), but the runtime still refuses a pass over 15 s (`minimax_h3_main.py:1533-1537`; `packing.py:62-63`) |
| `prompt_enhancer`, `negative_prompt`, `alt_prompt`, `output_filename` | Hub's `FORCED_TASK` | negative is meaningless (`no_negative_prompt`, handler `:1808`); `output_filename` → §4 |

Inert on this runtime (sent or not, no effect): `guidance_scale`, `flow_shift`, `sample_solver`, `negative_prompt`.
`generate()` takes no guidance argument (`minimax_h3_main.py:1477-1508`), the schedulers are hard-coded video shift 12 /
audio shift 3 (`:1001-1004`), and the sampler comes from the definition (`euler`, fused `res_multistep`; handler
`:1933-1935`). The fused validator still rewrites guidance/flow keys (`:2429-2431`), which only affects metadata.

Turbo: `minimax_h3_turbo_mode` is **not** a `generate_video` parameter. HocusPocus applies its Turbo preset only in its
own HTTP layer (`HP:_launch_runtime.py:11107`; `HP:services/h3_runtime_policy.py:120-131`;
`HP:models/minimax_h3/turbo.py:272-378`). Through `submit_task`, Turbo means: the LoRA file in `activated_loras`, its
multiplier, and the exact step count (8 for PDD, ≥4 for the larger "standard_lora" ones).

### 1.2 Text → clip (minimal, as it reaches `submit_task`)

```python
{"model_type": "minimax_h3", "image_mode": 0,
 "prompt": "integrated_multimodal_description: [Shot 1] A slow push-in on a lighthouse keeper ... "
           "(S1) <d>[English] The light is ours tonight.</d> ...\n"
           "overall_soundscape: Waves on rock, wind against glass, a lamp mechanism ticking.\n"
           "non_diegetic_music: N/A",
 "resolution": "960x544", "video_length": 124, "sliding_window_size": 124, "minimax_h3_multi_window": False,
 "num_inference_steps": 20, "seed": 1234, "batch_size": 1, "multi_prompts_gen_type": 2,
 "image_prompt_type": "", "video_prompt_type": "", "audio_prompt_type": "",
 "activated_loras": [], "loras_multipliers": "", "minimax_h3_text_encoder": "nvfp4_awq",
 # FORCED_TASK (hub/worker/wan2gp.py:43-44)
 "prompt_enhancer": "", "negative_prompt": "", "alt_prompt": "", "output_filename": "{date}-{seed}"}
```

The factory underlay adds the rest (`sliding_window_overlap` 18, `denoising_strength` 1.0, `skip_steps_cache_type` "",
… handler `:2232-2260`).

### 1.3 Why `sliding_window_size = video_length` is not enough (correction to 08 §1.4)

`validate_generative_settings` reads the card's total memory (`torch.cuda.get_device_properties(0)`; under the Hub that
is the lane's GPU via `CUDA_VISIBLE_DEVICES`) and applies `apply_h3_window_memory_policy` (handler `:2656-2681`,
`:1372-1442`). For FL2VA it **shrinks `sliding_window_size`** when the checkpoint's table says the canvas is too big for
the card (Pruned table `:623-685`, Full `:552-621`, Fused `:700-781`), and refuses outright when even 124 frames is
not recommended (`:1408-1428`). With the default `minimax_h3_multi_window: True` a shrunk window silently becomes
several windows, i.e. several output files (§4.2). Two task levers exist:

- `minimax_h3_multi_window: False` → one pass; `video_length` is capped to the (possibly shrunk) window, so the clip
  can come back **shorter** than asked (handler `:2682-2689`).
- `sliding_window_memory_override: True` → the policy is skipped (`:1386-1387`); risk is OOM instead.

Worked values (Pruned): 960x544 = 522k px → band ≥500k: ≤8 GB 124, ≤12 GB 243, else 345 (`:669-676`); 1280x704 =
901k px → band ≥800k: ≤12 GB 124, ≤24 GB 243, else 345 (`:660-668`). On a 32 GB card nothing up to 1344x768 is shrunk;
on a 10–12 GB card 540p caps at 243 and 720p at 124. Omni is different: without `minimax_h3_reference_sequence` the
handler pins `sliding_window_size = video_length ≤ 345` and the policy is not applied (`:2586-2591`, `:1384`), so
Omni is always one pass.

### 1.4 Image → clip (first frame)

```python
{**T2V, "image_prompt_type": "S", "image_start": "/abs/path/first.png", "image_fit_mode": "crop",
 "prompt": "For the target video, at 0.00 seconds into the target video, <Picture 1> (from [Shot 1]) is fully referenced.\n"
           "integrated_multimodal_description: [Shot 1] ...\noverall_soundscape: ...\nnon_diegetic_music: N/A"}
```

- Last frame only: `"image_prompt_type": "E", "image_end": [path]`; both: `"SE"` with one of each
  (`HP:wgp.py:1244-1247` wants equal counts).
- Without `"crop"`, the output canvas follows the image's aspect (fit_canvas 1), so the clip's size may differ from
  `resolution`; the Hub must then read the size from the file (§4.3).
- The first-frame alignment sentence is the official form (`HP:models/minimax_h3/prompt_enhancer.py:120`;
  `HP:services/director/minimax_h3_prompting.py:20-23`).

### 1.5 References → clip (Omni / Ref2VA)

```python
{"model_type": "minimax_h3_ref2va", "image_mode": 0, "resolution": "960x544", "video_length": 124,
 "num_inference_steps": 20, "seed": 1234, "multi_prompts_gen_type": 2, "image_prompt_type": "",
 "minimax_h3_references": [
     {"type": "image", "path": "/abs/character-1.png", "image_intent": "identity", "character_name": "Character 1", "role": "the keeper"}],
 "minimax_h3_reference_detail": "match",
 "prompt": "subject_definitions:\n<Subject 1> (S1) is the keeper from <Picture 1>.\nsummary: [reference generation] ...\n"
           "retention_analysis: <Subject 1> (appears in [Shot 1]): fully_preserved - face, hair, coat.\n"
           "detailed_description: ... [Shot 1] ... <Subject 1> (S1) says <d>[English] ...</d>\n"
           "overall_soundscape: ...\nnon_diegetic_music: N/A",
 **FORCED_TASK}
```

Manifest shape, validated by `validate_reference_manifest` (`HP:models/minimax_h3/reference_manifest.py:33-159`):

| Field | Rule |
|---|---|
| `type` (or `kind`) | `image` \| `video` \| `audio` (`:64-66`); extension must match (`:20-22`, `:72-76`) |
| `path` | required; file must exist at generation (`:67-71`; `ref2va.py:1888`) |
| `role` | free text ≤500 chars (`:82`); `character_name` ≤120, `library_character_id` ≤128 (`:83-88`) |
| image | `image_intent` identity\|scene\|style\|composition, default identity (`:89-97`); `remove_background` bool, honoured only for identity (`:98-114`) |
| audio | `audio_intent` voice\|drive\|style, default voice (`:115-125`); at most one `drive` (`:155-159`) |
| video | `video_intent` character\|motion\|scene, default motion; `include_audio` (default true); optional `audio_path` (`:126-143`) |
| counts | ≤9 images, ≤3 videos, ≤3 audios, ≤12 total, at least one image or video (`:15-18`, `:52-55`, `:146-154`) |

Order is semantic: the runtime regroups images, then videos, then audio, and renumbers `<Audio N>` labels
(`HP:models/minimax_h3/ref2va.py:400-440`). The 2–15 s per-reference / 15 s total trimmer
(`reference_media.py:13-15`) has **no caller** anywhere in the tree (grep), and if called it writes under
`<cwd>/uploads/h3_reference_cache` (`reference_media.py:87`), i.e. the engine root under the Hub. Video/audio
references are therefore out of the primitive; image references need no preparation.

---

## 2. Models

### 2.1 HocusPocus ids (Fact; files `HP:defaults/<id>.json`)

| id | Class | Inputs | Default steps / frames / res | Weights named by URL | Notes |
|---|---|---|---|---|---|
| `minimax_h3` | Pruned FL2VA (20B) | text; S/E/SE; control video, soundtrack, timed frames | 20 / 124 / 864x480; window 345 | `minimax_h3_fl2va_pruned_fp8_scaled.safetensors` (Comfy-Org @0543966f) | "Recommended lighter" (json `:5`); LoRAs on |
| `minimax_h3_full` | Full FL2VA (33B) | as above | 20 / 124 / 864x480 | `MiniMax-H3-FL2VA_bf16` / `_int8_convrot` (DeepBeepMeep @fec7846a), chosen by `transformer_quantization` | needs ~54 GB pipeline RAM, 64 GB recommended, Triton for its INT8 fast path (handler `:814-819`, `:1298-1369`) |
| `minimax_h3_fused_turbo` | Fused turbo (experimental) | FL2VA inputs | 4 (4–8) / 243 / 1152x640; window 243 | `minimax_h3_fused_refdelta_r1024_turbo8_mystic07_int8_convrot` (MATLOWAI @3b51096a), 21 GB | res_multistep, SLA attention, LoRAs/Turbo/FBC refused (json `:10-31`; handler `:1939`, `:2422-2449`); needs INT8 ConvRot video VAE + LICENSE/NOTICE (json `:42-47`) |
| `minimax_h3_legacy` | Legacy sidecar | text, first/last | fixed 20 / 124 / 960x544 | Abiray INT8 ConvRot | **cannot run in-process**: `load_model` raises (handler `:2186-2191`) — through `submit_task` it always fails |
| `minimax_h3_ref2va` | Pruned Omni | references (§1.5) | 20 / 124 / 864x480 | `minimax_h3_ref2va_pruned_fp8_scaled` | always one pass |
| `minimax_h3_ref2va_full` | Full Omni | references | 20 / 124 / 864x480 | `MiniMax-H3-Ref2VA_bf16` / `_int8_convrot` | as Full |
| `minimax_h3_ref2va_fused_turbo` | Fused Omni | references | 4 / 243 / 1152x640 | same 21 GB file as Frames | 243-frame cap kept for references (handler `:783-812`) |
| `h3_advanced_*` (6) | upstream WanGP 1272 import | see 05 §5.5.4 | handler | DeepBeepMeep @fa7ed035 | own family `h3_advanced`; example prompts already in the three-field form with `(S1) <d>[English] …</d>` (`HP:defaults/h3_advanced_fl2va.json`) |

Companion files every in-process H3 id loads (`minimax_h3_main.py:952-967`, `:805-806`; handler `:2102-2170`),
relative to a checkpoints folder:

- `minimax_h3/vae/minimax_h3_video_vae_fp16.safetensors` (fused: `minimax_h3/vae/minimax_h3_video_vae_int8_convrot.safetensors`);
- `minimax_h3/vae/minimax_h3_audio_vae_fp32.safetensors`;
- `minimax_h3/processor/` (chat_template.json, merges.txt, preprocessor_config.json, tokenizer.json,
  tokenizer_config.json, video_preprocessor_config.json, vocab.json) and `minimax_h3/text_encoder/config.json`;
- the Qwen3-VL conditioner for the chosen variant, looked up with `extra_paths="minimax_h3"`
  (`HP:wgp.py:4368-4372`): nvfp4 `qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors` ~15.7 GB, native only on RTX 50
  (handler `:338-351`, `:422-423`); `gguf_q2_k` ~8.5 GB; `gguf_q4_k_m` ~14.6 GB; `int8` ~26.7 GB; `bf16` ~51.5 GB
  (`:353-400`).

The handler declares migration aliases (`compatible_model_paths`, `compatible_text_encoder_paths`, handler
`:1850-1907`), but **nothing in the tree reads them** (grep finds only the handler; `minimax_h3_main.py:981` reads
the qkv-layout map only). So weight files must carry exactly the URL basenames. A WanGP-named
`MiniMax-H3-FL2VA-pruned_rank8_int8_convrot.safetensors` would not satisfy `minimax_h3` unless a Hub pointer names it.

VRAM/RAM from the code: H3 reserves 10 GB working VRAM for the transformer independent of card size (handler `:49-55`,
`:2218-2220`); the text and vision towers are profiled separately (`:2204-2215`); the memory tables are calibrated on
a 24 GB 4090 completing 345 frames at 1280x704 (`:543-551`).

Licences (code-level only; 05 §5.5.3 has the texts): Comfy-Org/MiniMaxAI/DeepBeepMeep weights "remain governed by
their respective model terms" (`HP:models/minimax_h3/UPSTREAM.md`); fused weights declare "MiniMax Model License plus
upstream component licenses" and are "not an official MiniMax release" (fused json `:38-40`;
`H3_FUSED_NOTICE.md:20-25`). The fused entry fetches LICENSE and NOTICE as model assets (handler `:2147-2161`), so a
Stage 0 inventory sees whether they are on disk.

### 2.2 Upstream Wan2GP 17.17 (`UP:wgp.py:184-185`, settings 2.79 vs HocusPocus 2.57)

- Ids: `minimax_h3_fl2va`, `_fl2va_pruned`, `_fl2va_pdd`, `_fl2va_pruned_pdd`, `_ref2va`, `_ref2va_pruned`, `_ref2va_pdd`,
  `_ref2va_pruned_pdd`, `_tts_ref2va_pruned`, `_control`, `_control_pruned`, `_vdn`, `_vdn_pruned` (`UP:defaults/`).
  None matches a HocusPocus id; HocusPocus's `h3_advanced_*` are renamed copies of the upstream ones.
- Lattice: `frames_minimum` **107**, step 17, offset 5 (`UP:models/minimax_h3/minimax_h3_handler.py:576-578`);
  defaults 124 frames, window **362** (`:1211-1214`). HocusPocus: min 124, max 345.
- Guidance: upstream has real CFG (`guidance_max_phases` 2, 1 for PDD) and selectable solvers
  (`:581`, `:637`); HocusPocus has neither (handler `:1809`, `:1933`).
- PDD is a model id upstream (`"pdd": true`, `UP:defaults/minimax_h3_fl2va_pruned_pdd.json`); in HocusPocus it is a
  LoRA preset (`turbo_presets.json:51-91`).
- Upstream marks H3 `image_outputs: False` explicitly (`:505`, `:540`) and advertises `v2i_switch_supported` (`:573`).
- Upstream weights are the WanGP rank8 BF16/INT8 exports at `resolve/main` (`UP:defaults/minimax_h3_fl2va_pruned.json`),
  not the Comfy FP8 files HocusPocus names.

### 2.3 The first target

**`minimax_h3`** (Pruned FL2VA). It is the definition's own recommendation (json `:5`; handler `:1733-1736`); it
covers text and first-frame with one id; it runs the plain euler 20-step recipe with no experimental attention; its
companions are the standard VAEs; LoRAs (incl. a later Turbo) stay possible; and on a 32 GB card its memory table
never shrinks a ≤768p window. `minimax_h3_fused_turbo` is the speed option once its 21 GB file, INT8 VAE and
LICENSE/NOTICE are present; it is labelled experimental and non-official, so it should be opt-in.

---

## 3. The prompt contract (what the assistant must write)

### 3.1 FL2VA (text, first/last frame) — three fields, in this order

`HP:models/minimax_h3/prompt_enhancer.py:4-30`, `:89-109`; field names `HP:services/h3_prompt_policy.py:11-15`.

```
[optional alignment line for a start/end picture]
integrated_multimodal_description: [Shot 1] ... [Shot 2] At 00:03.500, ...
overall_soundscape: ...
non_diegetic_music: ... | N/A
```

- `[Shot 1]` has no timestamp; each later cut is `[Shot N] At MM:SS.mmm,` with strictly increasing times inside the
  clip (`:24`, `:94`). Prefer one continuous shot with camera movement over a cut for small changes (`:25`).
- Dialogue: **only** text inside `<d>[Language] …</d>` is spoken; text outside is never voiced (`:84`, `:100`). Inside
  the tag: the words and nothing else; the speaker ID `(S1)` and delivery go immediately before the tag (`:96`, `:106`).
  Speaker IDs stay stable (`:27`). `<scenetrans>` marks speech crossing a cut; `<cutoff>` speech truncated by the end
  (`:28`). Quoted lines in the request must be reproduced verbatim in their own language (`:102`). Language labels are
  broad names (English, Spanish, French, …) (`HP:models/minimax_h3/spoken_language.py:40-61`).
- `overall_soundscape`: one paragraph of ambience and physical sounds, never dialogue (`:98`); `non_diegetic_music`:
  score only, else `N/A` (`:30`, `:98`). Do not give voices to a scene nobody was asked to speak in (`:98`).
- Descriptive text in English (`:92`). The Director adds "after the last word … mouths closed" and a speech budget
  (`HP:services/h3_prompt_policy.py:76-91`): its check is **2.1 words per second** of clip
  (`HP:services/director/h3_dialogue.py:652-680`), i.e. ~10 words for a 5.2 s clip, ~30 for 14.4 s.
- First frame: first line `For the target video, at 0.00 seconds into the target video, <Picture 1> (from [Shot 1]) is
  fully referenced.` (`prompt_enhancer.py:120`); last frame: `<Picture 1>` aligns with the exact end time; both:
  `<Picture 1>` at 0.00 and `<Picture 2>` at the end (`:16-20`).

### 3.2 Ref2VA (Omni) — six sections

`subject_definitions`, `summary`, `retention_analysis`, `detailed_description`, `overall_soundscape`,
`non_diegetic_music` (`prompt_enhancer.py:36-58`, `:131`). `<Subject N>` for reusable content citing `<Picture N>`;
`<Picture N>` gets its own entry only as a keyframe/anchor; summary opens with a bracketed task type such as
`[reference generation]`; retention values `fully_preserved | partially_preserved | attribute_transfer |
weak_reference` (`:62-69`, `:133-142`). MiniMax recommends **350–500 English words** in `detailed_description`
(`:73`, `:144`). The runtime itself adds relationship bindings before encoding (`minimax_h3_main.py:1989-1997`).

### 3.3 Limits and what to avoid

- No hard length limit or truncation exists in the H3 conditioner path (`conditioner.py:192-215`, `:376-405` tokenise
  without `max_length`). The practical guide is the enhancer budget upstream: 1024 tokens FL2VA, 2048 Ref2VA
  (`UP:models/minimax_h3/minimax_h3_handler.py:660`). The Hub's `MAX_PROMPT` of 4000 characters
  (`hub/modules/generate_image/screen.py:28`) suits FL2VA but can cut a 350–500-word Ref2VA prompt; a video module
  wants its own cap (Proposed: 8000).
- No line may start with `#` or `!` (template parser, §0.5). Blank lines vanish, which is harmless.
- Negative prompts do not exist for H3 (handler `:1808`).
- One prompt per pass. With several windows the handler rewrites the prompt into a timed "continuation window k of N"
  contract and silences `<d>` lines outside the window's slice (handler `:1445-1580`, `:2391-2413`) — another reason to
  keep the primitive at one pass.

---

## 4. Outputs

### 4.1 What one pass writes (Fact)

`generate` returns `{"x": video, "audio": stereo float array, "audio_sampling_rate": 32000}`
(`minimax_h3_main.py:2601-2609`, `:219`). Because audio is present, `generate_video` takes the mux branch
(`HP:wgp.py:9155-9168`, `:9415`):

1. `save_video` writes `<outbox>/<name>_tmp.<container>` with imageio-ffmpeg and `video_output_codec`
   (`HP:wgp.py:9416-9418`; default `libx264_8` = libx264, quality 8, yuv420p, `audio_video.py:625-628`).
2. The audio goes to `<outbox>/tmp<YYYY-MM-DD-HHhMMmSSs>.wav` (`HP:wgp.py:9432-9434`).
3. `combine_and_concatenate_video_with_audio_tracks` runs the **system `ffmpeg`** (the one `download_ffmpeg` put on
   PATH, `HP:shared/ffmpeg_setup.py:17-60`): `-c:v copy -c:a aac -b:a 128k -ar 32000 -ac 2 -shortest`
   (`audio_video.py:361-468`, codec table `:175-184`; key `audio_output_codec`, default `aac_128`, `HP:wgp.py:9451`).
4. Both temporaries are deleted in `finally` (`HP:wgp.py:9454-9471`).

Result: one `<name>.mp4` (or `video_container`, `HP:wgp.py:9351-9353`) holding H.264 yuv420p 24 fps + AAC stereo
32 kHz. No separate audio file is registered: `audio_file_list` is used only for `audio_only` models
(`HP:wgp.py:9776-9781`), so `generated_files` (`HP:shared/api.py:693-697`) holds just the video. (Closes 05's gap.)

Name: with the Hub's `output_filename: "{date}-{seed}"` the file is `2026-10-13-14h30m45s-1234.mp4`
(`HP:wgp.py:9360-9364`; format `HP:shared/utils/filename_formatter.py:13`), with `(2)` appended if taken
(`HP:wgp.py:6071-6083`).

### 4.2 Several windows mean several files

The save block sits inside the window loop (`while not abort:` at `HP:wgp.py:8391`, save at `:9341-9474`, both in the
same loop body), and each pass appends to `file_list` (`:9775-9781`) a file holding **all frames so far**
(`frames_already_processed`, `:9335-9338`). A three-window clip therefore yields three growing MP4s in
`generated_files`; the worker emits one `output` per file (`hub/worker/wan2gp.py:286-287`). The primitive avoids this
with `minimax_h3_multi_window: False` (§1.3); a later multi-window stage must land only the last file.

### 4.3 How `land` sees them today

`land` is called once per `output` event, after the task finished (`hub/worker/wan2gp.py:283-287`;
`hub/core/engine.py:156-158`). For an `.mp4`, `clean.strip` raises, the file is deleted and the job fails with "The
engine wrote a picture the hub could not read" (`hub/core/enginecat.py:110-114`); 08 §2.4–2.5 has the video branch.
`sweep` already removes `_tmp.mp4` / `tmp*.wav` leftovers after a crash (`enginecat.py:95-101`).

### 4.4 What the engine embeds, and the switches

| Switch (`wgp_config.json`) | Effect | Source |
|---|---|---|
| `metadata_type: "metadata"` (engine default) | full settings **including the prompt** as JSON in the MP4 `©cmt` atom (mutagen) | `HP:wgp.py:9536-9549`; `HP:shared/utils/video_metadata.py:177` |
| `metadata_type: "json"` | sidecar `<name>.json` next to the clip | `HP:wgp.py:9539-9542` |
| `embed_source_images: True` | start/end images as MP4 cover art (`----:com.apple.iTunes:EMBEDDED_IMAGES`, `IMAGE_METADATA`) | `HP:wgp.py:9526`; `video_metadata.py:112-152` |
| `metadata_type: "none"` (Hub) | none of the above | `hub/worker/wan2gp.py:38` |

What remains with "none": the ffmpeg muxer's own `encoder=Lavf…` tag and x264's options SEI (08 §1.6) — not written by
wgp code, so only Stage 0 can show them.

### 4.5 Progress as the worker would relay it

The worker forwards only `progress` events (`hub/worker/wan2gp.py:264-271`); `status` events such as "Loading model
H3 First / Last — Pruned..." (`HP:wgp.py:7613-7615`) are dropped, which is why the worker emits its own
`model: loading` first (`:246-248`).

| Moment | Engine text (`p.status`) | `p.phase` (`api.py:890-910`) | step/steps |
|---|---|---|---|
| per pass, before sampling | "Encoding Prompt" (`HP:wgp.py:8880-8885`) | `encoding_text` | –, pct 18 (`api.py:917-918`) |
| sampler start | "Denoising \| 0s" (`minimax_h3_main.py:2386-2387`; `HP:wgp.py:4631-4633`) | `inference` | 0 / N |
| each evaluation | "Denoising \| m:ss" (`minimax_h3_main.py:2508-2509`) | `inference` | k / N, N = evaluations |
| last evaluation | "VAE Decoding \| m:ss" (`HP:wgp.py:4629-4630`) | `decoding` | N / N |
| video+audio decode, encode, mux | nothing | – | – |

With several windows every text is prefixed "Sliding Window k/N - " (`HP:wgp.py:10274-10290`, `:10321-10332`) and the
step count restarts each pass because the callback is rebuilt per window (`:8884`). The Hub's `enginecat.progress`
then sits at 100 % from the end of window 1 (`hub/core/enginecat.py:70-77`).

---

## 5. What the Hub's worker and catalog must do (Proposed)

### 5.1 Worker (`hub/worker/wan2gp.py`)

```python
# FORCED_CONFIG: one container the controller can land; codecs stay the engine config's (08 §2.6)
FORCED_CONFIG = {..., "video_container": "mp4"}

def translate(settings: dict, api: str, factory: dict) -> dict:
    ...                                                    # unchanged
    if out.get("image_mode") == 0:                         # video task: one pass, no engine-side chaining
        out.setdefault("minimax_h3_multi_window", False)
        refs = out.get("minimax_h3_references") or []
        if any(not os.path.isabs(str(r.get("path", ""))) for r in refs):
            raise ValueError("reference paths must be absolute")  # not an attachment key (§0.2)
    return out
```

- No forced `MMAudio_setting` / `minimax_h3_extended_duration` (correction to 08 §2.6): both are already off — 0 in
  `primary_settings` (`HP:models/_settings.json:64`) and `False` by default (`HP:wgp.py:7451`), and the factory never
  sets them (handler `:2224-2261`). Forcing them adds keys without effect.
- Output: unchanged; a one-pass task emits exactly one `output`. Proposed guard: if a video task reports more than one
  file, emit only the last (multi-window safety net, §4.2).
- Errors: validation reasons are lost (§0.3). The module must pre-check everything the handler refuses: lattice and
  pass maximum, 32-multiples, fused 4–8 steps, fused + LoRA, Omni manifest rules (§1.5), `S`/`E` with images.
- `Run one image` docstring (`:242`) and `task_done.ok = bool(files)` (`:289`) hold for a clip as they are.

### 5.2 Catalog (`hub/worker/catalog.py`)

The filter `if not model_def.get("image_outputs")` (`catalog.py:133`) is what keeps H3 out. Proposed second list:

```python
def video_entry(w, model_type, model_def, factory) -> dict | None:
    if model_def.get("image_outputs") or model_def.get("audio_only") or model_def.get("minimax_h3_legacy_sidecar"):
        return None
    if not (model_def.get("t2v_class") or model_def.get("i2v_class")):
        return None
    return {"fps": model_def.get("fps"),
            "frames": {k: model_def.get(f"frames_{k}") for k in ("minimum", "steps", "maximum")},
            "presets": model_def.get("resolution_presets"), "preset_order": model_def.get("resolution_preset_order"),
            "prompt_types": model_def.get("image_prompt_types_allowed", ""), "omni": bool(model_def.get("omni_reference")),
            "omni_limits": model_def.get("omni_reference_limits"), "audio_out": bool(model_def.get("returns_audio")),
            "steps": {"min": model_def.get("inference_steps_min"), "max": model_def.get("inference_steps_max")},
            "loras_disabled": bool(model_def.get("loras_disabled")),
            "memory_policy": model_def.get("sliding_window_memory_policy"),      # §1.3: the module mirrors it
            "text_encoders": sorted(model_def.get("minimax_h3_text_encoder_variants") or {})}
```

`build()` appends `{**describe(...), "video": video_entry(...)}` to `video_models` in the same loop; `models` and
`definitions.weights(…, image_types)` stay image-only. `presence()` (`:114-124`) counts a model "partial" when only the
transformer file exists, so the video list should offer `available` only (08 §1.7) and the module should name the
missing companion when a load fails. `describe` already gives `defaults`, `block` (32) and `lock_steps`.

With `memory_policy` in the catalog the module can refuse, before submit, a length the engine would cap on this lane's
card, instead of returning a shorter clip silently.

---

## 6. Stage 0 verification (read-only, on the engine host)

Variables: `ENGINE=<HocusPocus app folder>`, `PY=<engine python>`, `MODELS=<each owner model folder>`,
`LORAS=<lora root>`. Nothing below writes.

1. Engine version and H3 code present:
   `grep -nE '^(WanGP_version|settings_version)' $ENGINE/wgp.py` (expect 10.9875 / 2.57);
   `ls $ENGINE/defaults | grep -E '^(minimax_h3|h3_advanced)'`; `ls $ENGINE/models/minimax_h3/`.
2. Engine config keys that shape a clip (selects only these keys, no secrets):
   `$PY -c "import json;c=json.load(open('$ENGINE/wgp_config.json'));print({k:c.get(k) for k in ('video_container','video_output_codec','audio_output_codec','metadata_type','embed_source_images','fit_canvas','video_profile','transformer_quantization','text_encoder_quantization','attention_mode','checkpoints_paths','save_path')})"`.
3. Transformer files by exact name (§2.1):
   `find $MODELS $ENGINE/ckpts -maxdepth 3 \( -name 'minimax_h3_*pruned_fp8_scaled.safetensors' -o -name 'MiniMax-H3-*.safetensors' -o -name 'minimax_h3_fused_*.safetensors' \) -printf '%s\t%p\n'`.
4. Companions:
   `find $MODELS $ENGINE/ckpts -maxdepth 4 -path '*minimax_h3/*' -printf '%s\t%p\n' | sort -k2` — expect `vae/`
   (video fp16 and/or int8_convrot, audio fp32), `processor/` (7 files), `text_encoder/config.json`, the Qwen3-VL
   variant file, and for fused `fused_turbo/LICENSE`, `NOTICE`. Also `find … -path '*Qwen3-VL-32B-Instruct/*'`.
5. Each owner folder is listed in the Hub's `checkpoints_paths` one level deep (`hub/worker/wan2gp.py:122-137`), so
   `minimax_h3/vae/…` must sit directly under a model folder or under one of its first-level subfolders.
6. ffmpeg used for the mux: `ls $ENGINE/ffmpeg_bins`; `$ENGINE/ffmpeg_bins/ffmpeg -hide_banner -encoders | grep -E ' (libx264|aac) '`.
7. LoRAs (Turbo later): `ls $LORAS/minimax_h3/ 2>/dev/null`.
8. GPU and NVFP4: `$PY -c "import torch;print(torch.__version__,torch.cuda.get_device_name(0),torch.cuda.get_device_capability(0),torch.cuda.get_device_properties(0).total_memory>>30)"`
   (NVFP4 runs natively only on RTX 50, handler `:341-343`); `$PY -c "import triton;print(triton.__version__)"`
   (SLA/Sol and Full's fast path); `free -g`.
9. Owner-run task in HocusPocus's own UI: "H3 First / Last — Pruned", text only, Turbo off, 540p 16:9 (960x544),
   124 frames, 20 steps, a prompt in the §3.1 form with one `<d>[English] …</d>` line. Note wall time and peak VRAM;
   copy from the engine console the `[MiniMax H3 Perf]` line (`minimax_h3_main.py:2375-2384`) and confirm no
   `VRAM-aware FL2VA window` line (handler `:2674-2681`). Then on the produced file:
   - `ffprobe -v error -show_entries format=format_name,duration,size,bit_rate:format_tags:stream=index,codec_type,codec_name,profile,pix_fmt,width,height,r_frame_rate,avg_frame_rate,nb_frames,sample_rate,channels,channel_layout,bit_rate:stream_tags -of json <clip>.mp4`
     Expect `mov,mp4…`; video `h264`, `yuv420p`, 960x544, `24/1`, `nb_frames` 124, duration ≈5.167 s; audio `aac`,
     32000 Hz, 2 channels, `stereo`. Record `format_tags` (`encoder`, and `comment` if HocusPocus's own
     `metadata_type` is `metadata` — that is what the Hub's `none` removes).
   - `strings -n 6 <clip>.mp4 | grep -iE 'x264|lavf|seed|prompt|integrated_multimodal' | head`.
   - `ls` the HocusPocus output folder for `_tmp.mp4`, `tmp*.wav` or `.json` siblings.
   HocusPocus's UI path differs from `submit_task` (Turbo and text-encoder normalisation in
   `HP:_launch_runtime.py:11090-11112`), so Turbo must be off for the result to stand for the Hub's path.

---

## Corrections to 05 §5.5 and 08 §1 (summary)

1. `T` in `image_prompt_types_allowed` is the "Text Prompt Only" choice (value `""`) (`HP:wgp.py:12573-12574`).
2. Turbo default: the runtime reads `default_preset_id` (`turbo.py:58-62`) = Alibaba PAI PDD 8-step;
   `UPSTREAM.md:134-138` is stale. Turbo presets come from two repos, larryvrh (6 steps) and alibaba-pai (8-step PDD)
   (`turbo_presets.json:3`, `:57`, `:77`). Turbo mode is applied only in HocusPocus's HTTP layer, not by `submit_task`.
3. `sliding_window_size = video_length` does not guarantee one pass; use `minimax_h3_multi_window: False` (§1.3).
4. Multiple windows produce multiple growing output files (§4.2).
5. No separate audio file reaches `generated_files` (§4.1).
6. `image_start` may be a path or a list; only the first is used; paths are absolutised; reference paths are not.
7. `guidance_scale`, `flow_shift`, `sample_solver` are inert on HocusPocus H3 (§1.1); `guide_key` none is right.
8. Weight files must match URL basenames; the alias maps have no reader (§2.1).
9. Forcing `MMAudio_setting` / `minimax_h3_extended_duration` is unnecessary (§5.1).
10. Validation failures surface only as "Task 1 failed validation" (§0.3).
11. Prompt lines beginning `#` or `!` are eaten by the template parser (§0.5).
12. `minimax_h3_legacy` cannot run through `submit_task` at all (handler `:2186-2191`), not merely "should not".

---

## Unverified

- That `gr.Info` messages from validation are invisible to the worker in practice (they may reach the engine's
  stdout, which the worker does not relay).
- That the save block runs once per window as read (§4.2) — confirmed by indentation and loop structure only, not by
  a run.
- The exact behaviour of `fit_canvas` 1 vs `image_fit_mode: "crop"` on H3's canvas with a start image of a different
  aspect (output size may differ from `resolution`).
- The fused JSON lists the audio VAE under `minimax_h3/vae/` (`minimax_h3_fused_turbo.json:44`) while the handler's
  download group targets `minimax_h3/` with source folder `vae` (handler `:2124-2130`); the runtime reads
  `minimax_h3/vae/` (`minimax_h3_main.py:965-967`). Which path a real install has is for Stage 0.
- Whether `get_model_download_status` counts H3's VAEs, processor and text encoder, i.e. whether "available" in the
  catalog means "loadable".
- Whether the Comfy FP8-scaled transformer named by `minimax_h3` or the WanGP INT8 export is what the model folders hold; and
  which Qwen3-VL variant file is on disk (the task must name a present one).
- The encoder marks (Lavf tag, x264 SEI) on a real clip; output size per clip; seconds per clip and peak VRAM on the
  engine card.
- Whether `minimax_h3_extended_duration: True` is ever usable in-process given the 15 s per-pass check.
- That the HocusPocus checkout read here matches the installed engine (05's gap stands).
