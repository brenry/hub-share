# R12 - the companion-file check against the engine's own fetch rules

Facts only. Hub = the repository root. Engine = the HocusPocus checkout's `app/` folder (the locator is `app/shared/utils/files_locator.py`).
"False refusal" means the Hub refuses but the engine would fetch nothing. "Missed fetch" means the Hub passes but the engine would fetch.
## 1. Where the check runs
- `Engine.run` calls `lacking(model)` only when the model changes (`loading = model != self.loaded()`). It refuses with the first
  entry: "The engine lacks a companion file: <basename>" (`hub/worker/wan2gp.py:210-217`). If the check raises an exception, nothing is refused (`:176-184`).
- The engine fetches inside `load_models`: main and URLs2 at file_type 0, modules at file_type 1 (`wgp.py:4324-4330`), and the text encoder
  at file_type 2 (`:4359-4372`). Only a file_type 0 call runs the shared list, the mask set, MMAudio and `query_model_files` (`:3915-3940, 4009-4013`).
- The cwd is the engine root (`wan2gp.py` `open`: `os.chdir(self.root)`), so relative roots resolve as they do for the engine. `_APP_DIR` is set when the locator is imported (`files_locator.py:14`).
- Checkpoint roots: `[<state>/config/ckpts (scratch, write target), each --models DIR, each DIR's first-level subfolders]`
  (`hub/worker/wgpconfig.py:38-53`). Owner folders outside the app are "external" (`files_locator.py:22-38`).
## 2. Rule by rule
| # | Rule (engine) | Hub | Verdict |
|---|---|---|---|
| 1 | Empty file list: fetch if `locate_folder(target/source)` is None (`wgp.py:3704-3711`) | `wanted` `fork.py:131-133`, same key, same call | identical |
| 2 | `independent_files`: per file `locate_file(folder/file)`, any root (`:3714-3725`) | `fork.py:135-137` | identical |
| 3 | No folder: per file `locate_file(file)`, any root (`:3771-3779`) | `fork.py:135` (`not parts`) | identical |
| 4 | Folder set: fetch the files missing from `targetRoot` when no single root holds all of them, or when the folder exists in `targetRoot` with files missing (`:3735-3770`) | `fork.py:138-142`: `top` from the same `get_smart_download_root(target or source)`, the same `get_checkpoints_paths()` loop, the same partial test. It names `nowhere or short`, and `nowhere` is a subset of `short` (locate_file only searches roots), so it is non-empty exactly when the engine fetches | identical |
| 5 | Second checkpoint root: a file found in any root counts (rules 2 and 3). A folder set counts only when one root holds the whole set (rule 4) | same calls | identical. A set split across two roots is a true refusal |
| 6 | Folder present but partial in the download root: `get_smart_download_root` skips external roots other than [0] (`files_locator.py:91-109`), so the scratch's partial folder blocks a complete copy in an owner root | same call | identical (true refusal). `tidy_scratch` removes only empty folders and `.cache` (`wgpconfig.py:27-35`) |
| 7 | `fl` order: `locate_file` and `locate_folder` search `_checkpoints_paths` from first to last (`files_locator.py:123-173`) | same functions via `w.fl` | identical; for existence, only "found anywhere" matters |
| 8 | Shared list (`wgp.py:3916-3924`) | `fork.facts.json` `companions.shared`, checked file by file | identical (22 files in 9 folders, plus RIFE) |
| 9 | RIFE: `flownet.pkl` if `rife_version` is absent or "v3", else `rife4.26.pkl` (`:3903-3924`) | `by_config` (`fork.py:151-152`), same config (`seed_config` keeps the key) | identical |
| 10 | Mask: `query_matanyone_download_def(server_config)` (`:3927`; `model_assets.py:103-109`) | `fork.py:158-159`, a copy of the config | identical |
| 11 | Prompt enhancer when `enhancer_enabled>0` (`:3930-3938`) | omitted. `FORCED_CONFIG` sets `enhancer_enabled: 0` (`wgpconfig.py:18`, `wan2gp.py:150`) | identical (forced off) |
| 12 | MMAudio, gated on `get_mmaudio_settings(server_config)[0]`, i.e. `mmaudio_mode != 0` (`:3782-3786, 2744-2770`) | `fork.py:153-156`, same gate | gate identical. Picture jobs need MMAudio too when the config enables it: the engine fetches at every load, and per-task `MMAudio_setting` does not affect it |
| 13 | MMAudio modes 1 and 2: set `mmaudio/[synchformer, v1-44, weight]` (`:3796-3800`) | `audio(config)[4]` basename added to the set | identical |
| 14 | MMAudio mode 3: set `mmaudio/[synchformer, v1-44]` only. The mode-3 weight is checked separately by `locate_file("mmaudio/<mode-3 weight>")`, any root (`:3797-3800, 3809-3811`) | the mode-3 weight is put inside the folder set | **FALSE REFUSAL** (F1) |
| 15 | Main file: `get_model_filename` picks one variant by quantization and dtype (`:3119-3148`), unless `prefer_installed_variants` (`weight_variants.py:4-10`). The engine fetches it if that variant is not found; skipped if `source` (`:3949-3962`) | refuses only when no URL variant is found (`fork.py:181-182`) | no false refusal. **Missed fetch**: another variant present, the preferred one absent |
| 16 | `preload_URLs` (recursive), `VAE_URLs` (own): `get_local_model_filename(url)` (`:3968-3991`) | `fork.py:183-186`, same lookup | identical |
| 17 | `wangp_1272` and "/loras/" in a preload URL: `check_loras_exist(..., True)` can download (`:3976-3981`) | skipped | **missed fetch** |
| 18 | Definition `loras`: `resolve_lora_path(model_type, name)`, then isfile (`:3993-4007`) | `fork.py:187-189`, same function. Both see the Hub's `get_lora_dir` patch (`wan2gp.py` `open`) | identical |
| 19 | `query_model_files(computeList, base, model_def)` (`:4010-4013`) | `fork.py:190-194`, same handler (`get_model_handler`), same `computeList` | identical. No handler reads per-task settings: only `model_def` fields (`minimax_h3_fused_turbo`, `video_vae_file`) or module constants (`H3_DIALOGUE_GENERATION`). The text-encoder choice and resolution do not enter it |
| 20 | URLs2 (submodel 2) main file (`:4269-4300`) | not checked | **missed fetch** |
| 21 | `modules` (file_type 1: module file, preload, VAE, loras) (`:4301-4321`) | not checked | **missed fetch** |
| 22 | Text encoder: `text_encoder_URLs`, or the `minimax_h3_text_encoder_variants` entry chosen by task kwargs. Looked up in `text_encoder_folder` first (`:4345-4374`) | not checked | **missed fetch** for every picture model. Example: flux2_klein_9b's `qwen3_8b/qwen3_8b_{bf16,quanto_bf16_int8}.safetensors` (`flux_handler.py:128-136`) |
| 23 | No main URLs but `modules` present: no file_type 0 call at all, so no shared, mask, MMAudio or `query_model_files` (`:4325-4330`) | always checks these | **FALSE REFUSAL** (F2). Theoretical: no definition in `defaults/` or `finetunes/` has `modules` without `URLs` |
| 24 | ffmpeg: `_resolve_path` order `ffmpeg_bins`, root (after quarantining a root `ffmpeg`), PATH. `_libs_present` (`ffmpeg_setup.py:87-140`) | `prepare` (`fork.py:95-114`) | identical on Linux |
## 3. False refusals and one-line fixes
- **F1 (MMAudio `mmaudio_mode` 3).** Refused when `synchformer_state_dict.pth` and `v1-44.pth` are complete in one root and
  the mode-3 weight (the third name in `wgp.py:3797-3800`) is in another root, or when the scratch's `mmaudio/` holds the pair but not that weight.
  Fix (`fork.py:155-156`): when `audio(config)[1] == 3`, leave the weight out of the `mmaudio` group and append
  `{"sourceFolderList": ["mmaudio"], "fileList": [[weight]], "independent_files": True}` to `defs`.
- **F2 (modules-only definition).** Fix (`fork.py:169`): when `listed("URLs")` is empty and `listed("modules")` is not, skip `_every_model` and `query_model_files`.
- None found for: second roots, partial download-root folders, `fl` order, the RIFE choice, the MMAudio gate (modes 0, 1, 2), text-encoder variants,
  definition LoRAs, or per-settings `query_model_files`.
## 4. Diagnostic gap (not a refusal mismatch)
- `--check-weights` opens on a fresh temporary state (`main.py:193-205`), so its scratch root is empty. The job's scratch
  (`<state>/config/ckpts`) can hold a partial folder, and rule 4 then refuses a job that `--check-weights` reports clean. The reverse also happens:
  files the job's scratch already holds are listed as missing. A comparison follows a check of `<state>/config/ckpts` for partial folders.
## 5. Every-model list for a picture job (as `--check-weights` prints keys: `folder/file (every model)`)
Each folder's files must be together in one root (a `--models` DIR or one of its first-level subfolders), with no partial copy in the scratch.
- `pose/dw-ll_ucoco_384.onnx`, `pose/yolox_l.onnx`
- `scribble/netG_A_latest.pth`
- `flow/raft-things.pth`
- `depth/depth_anything_v2_vitl.pth`, `depth/depth_anything_v2_vitb.pth`
- `wav2vec/config.json`, `feature_extractor_config.json`, `model.safetensors`, `preprocessor_config.json`, `special_tokens_map.json`, `tokenizer_config.json`, `vocab.json`
- `chinese-wav2vec2-base/config.json`, `pytorch_model.bin`, `preprocessor_config.json`
- `roformer/model_bs_roformer_ep_317_sdr_12.9755.ckpt`, `model_bs_roformer_ep_317_sdr_12.9755.yaml`, `download_checks.json`
- `pyannote/pyannote_model_wespeaker-voxceleb-resnet34-LM.bin`, `pytorch_model_segmentation-3.0.bin`
- `det_align/detface.pt`
- `flownet.pkl` (no folder, any root). It is `rife4.26.pkl` if the config's `rife_version` is set to anything other than "v3".
- `mask/sam_vit_h_4b8939_fp16.safetensors`, `mask/matanyone.safetensors` (`matanyone2.safetensors` if `matanyone_version` is v2), `mask/config.json`
- Only if the config enables MMAudio: `mmaudio/synchformer_state_dict.pth`, `mmaudio/v1-44.pth`, plus a weight that depends on the mode:
  mode 1 `mmaudio_large_44k_v2.pth`, mode 2 `mmaudio_large_44k_gold_8.5k_final_fp16.safetensors`, mode 3 the third weight named at `wgp.py:3797-3800`.
  Also `DFN5B-CLIP-ViT-H-14-378/open_clip_config.json`, `open_clip_pytorch_model.bin` and `bigvgan_v2_44khz_128band_512x/config.json`, `bigvgan_generator.pt`.
- Example of a per-model list, flux2_klein_9b (`flux_handler.py:303-325`):
  - main file: `flux-2-klein-9b.safetensors` or the `_quanto_bf16_int8` variant
  - `qwen3_8b/` tokenizer set: `config.json`, `generation_config.json`, `added_tokens.json`, `chat_template.jinja`, `merges.txt`, `special_tokens_map.json`, `tokenizer.json`, `tokenizer_config.json`, `vocab.json`
  - `flux2_vae.safetensors`
  - the text encoder (row 22): needed, but not checked.
