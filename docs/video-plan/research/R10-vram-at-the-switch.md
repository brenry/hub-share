# R10 - VRAM at the image-to-video switch (the engine's "unsufficient VRAM" text)

Read-only research. `HP:` = the HocusPocus checkout's `app/` folder (engine); `MM:` = the `mmgp/` folder of the upstream Wan2GP checkout
(the only mmgp source read; the engine pins `mmgp==3.7.6`, `HP:requirements.txt:7`, this copy is 4.0.0, so MMGP
behaviour below is "as read in 4.0.0"). Hub paths relative to the repository root (read at `abd7e8c` and with
later edits to `hub/core/{plan,dispatch,engine,enginelane,vram}.py`; both states are noted). "Derived" = this note's arithmetic.

## 1. The text, its source, the wrapped exception

- Emitted at `HP:wgp.py:9135`, inside `except Exception as e:` of the `generate_video` try (try at `:8901`, the pipeline call
  `wan_model.generate` at `:8929`). Full sentence:
  "The generation of the video has encountered an error: it is likely that you have unsufficient VRAM and you should
  therefore reduce the video resolution or its number of frames."
- Chosen by substring of `str(e)` (`:9127`): `"CUDA out of memory"` or `"Tried to allocate"` -> VRAM text; `"CUDA error: out of memory"` or
  `"CUDA error: too many resources requested"` -> the RAM text (`:9137`, "unsufficient RAM and / or Reserved RAM ... 'perc_reserved_mem_max' ... a different Profile");
  anything else -> `gr.Error("... please check your terminal ... '<original>'")` (`:9139`).
- So the wrapped exception is a `torch.OutOfMemoryError`-style message ("CUDA out of memory. Tried to allocate ...") raised anywhere
  inside `wan_model.generate` (H3 transformer step, packed attention, VAE decode, text/vision tower). **The original message is discarded**:
  only the traceback is printed to the worker's stdout (`:9140-9141`); the Hub gets just the fixed sentence.
- Before the message is sent the handler cleans up: `clear_gen_cache()`, `offloadobj.unload_all()`, `release_special_loras`, `gc.collect()`,
  `torch.cuda.empty_cache()` (`:9104-9125`), then `send_cmd("error", ...)`, returns False.
- Hub side: `hub/worker/faults.py:failure` turns a message containing "out of memory" into "Out of GPU memory"; this engine sentence does
  not contain that phrase, so the Hub shows the sentence itself (first line, cut at 600 chars) plus the `(at file:line in fn)` frame.
  A card showing "you sh..." is a display cut, not a different text.

## 2. Does the engine unload the previous model before loading another family?

- Yes, on the API path. `shared/api.py:500` calls `wgp.generate_video` (no queue layer). There,
  `if model_type != transformer_type or reload_needed or profile != loaded_profile: release_model()` (`HP:wgp.py:7585-7586`), then
  `load_models(...)` (`:7599`). Image and video models share the one `transformer_type` slot, so image -> H3 is a release + load.
- `release_model()` (`:182-198`): `wan_model=None`, drops `offload.shared_state["_cache"]`, `offloadobj.release()`, `offload.flush_torch_caches()`
  (`MM:offload.py:2545-2554`: `gc.collect`, `cuda.synchronize`, `torch.cuda.empty_cache`), `gc.collect`, heap trim, `reload_needed=True`.
- A profile change (e.g. image profile 4, video profile 5) also forces the release/reload (`profile != loaded_profile`, `:7585`).
- NOT on this path: `services/generation_memory.py` (`prepare_queued_model`, unloads inactive image/tts/music families) is called only from
  the HocusPocus server's own queue worker (`HP:_launch_runtime.py:24641`), and only when available RAM < 24 GiB (RAM, not VRAM).
- Other engine unloads: `release_RAM()` button (`wgp.py:4512`, plugin button "Force Unload Models from RAM"), `unload_model_if_needed`
  (`:11768`, policy "U"), and `shared/api.py:289` (`close()`).
- What the Hub's "Clear the GPU cache" calls: web `bus.request('gpu.release', {})` (`web/src/screens/media/Bar.tsx:38-39`,
  `web/src/modules/generate-image/run/Taskbar.tsx:36-37`) -> `gpu_release` (`hub/core/routes.py:90-103`) -> `Vram.release(lanes not busy)`
  (`hub/core/vram.py:134`) -> `EngineLane.release` (`hub/core/engine.py:78`): **stops the whole worker process** (`sup.stop()`),
  freeing VRAM, RAM and the CUDA context. It does not call `release_model` or `empty_cache`; it is refused while a job runs.
- At a model switch the Hub does the same by itself: HEAD `plan.decide` returns "release" the lane whenever it holds a different model
  (`hub/core/plan.py:70`, `dispatch.py:98-108`); the working tree does it in `enginelane._before` (`hub/core/enginelane.py:60-65`) and in
  `_follow_profile` when the video profile differs. So image -> video normally runs in a fresh worker; the model the Hub's
  own worker held is gone. Memory held by any other process stays (see 4).

## 3. What H3 needs (handler `HP:models/minimax_h3/minimax_h3_handler.py`)

- Working reserve: `_TRANSFORMER_WORKING_VRAM_MB = 10 * 1024` (`:55`), passed as `workingVRAM={"transformer": 10240}` (`:2218-2220`).
  MMGP uses it as `device_mem_capacity - workingVRAM` for the model budget, where capacity is `get_device_properties(0).total_memory`
  (`MM:offload.py:3314,4939-4950`). Total, not free.
- But the engine overrides the transformer budget: `init_pipe` for profiles 2/4/5 sets `transformer: 100` MB, `text_encoder: 100`,
  `"*": 1000` (profile 5) or `3000` (profile 4) (`HP:wgp.py:4186-4195`). H3 does not set `budgets`. Derived: the 10 GB figure only
  matters if no smaller budget is set; with profile 4/5 the transformer streams in ~100 MB of resident blocks, the rest of the card is
  activations plus the other towers/VAEs.
- Profile 4 vs 5 (`MM:offload.py:5190-5200`, README `:84-85`): 4 keeps the transformer pinned in reserved RAM, other models budget 3000 MB;
  5 pins nothing (small staging ring), "*" models (vision tower, VAEs) get 1000 MB. Both send the transformer to the GPU block by block.
  Profile 5 = least RAM, slowest, a little less VRAM held by the secondary models; it is not a VRAM-for-activations lever for the transformer.
  Engine docs: "Profile 5: Minimum RAM usage" (`HP:docs/CLI.md:117`).
- Pass-length tables (frames per pass; first tier whose `max_vram_gb >= total VRAM` wins; bands top-down by pixel count): Full `:552`, Pruned `:623`,
  Fused `:700`; header comment `:543-551` (24 GB 4090 completes 345 frames at 1280x704). Minimum legal pass is 124 (`:63`), 17n+5 alignment.
  Canvases (presets `:440-480`): 720p 16:9 = 1280x704 (901,120 px; 1280x720 is aliased to it, `:859-870`), 540p 16:9 = 960x544 (522,240 px).

Frames per pass, 720p / 540p, by total VRAM (a card reporting just under a tier edge falls into the lower tier):

| Checkpoint (band hit 720p / 540p) | <=8 GB | <=12 | <=16 | <=24 | **>24, incl. 32 GB** |
|---|---|---|---|---|---|
| Fused 4-step, `:700` (800k / 500k px) | 124 / 124 | 124 / 243 | 243 / 243 | 345 / 345 (tier edge is 23) | **345 / 345** |
| Pruned, `:623` (800k / 500k px) | 124 / 124 | 124 / 243 | 243 / 345 | 243 / 345 | **345 / 345** |
| Full, `:552` (500k / 500k px) | none / none (use 480p) | 124 / 124 | 243 / 243 | 345 / 345 | **345 / 345** |

  (Fused references variant caps these at 243, `:786`; Ref2VA is never shrunk, `:1384`.) A 124-frame request is the legal minimum, so on
  a 32 GB card the policy never shrinks it: `apply_h3_window_memory_policy` returns None when `total_frames <= safe_window` (`:1431`).
  Tables are keyed on resolution pixels and total VRAM only; text-only vs start frame and profile 4 vs 5 are not inputs.
- Derived token load: patch (1,2,2) (`transformer.py:776`), VAE spatial x16 / temporal x4 (`video_vae.py:227-228,562-563`).
  Tokens per latent frame: 720p 40x22 = 880; 540p 30x17 = 510 (720p = 1.73x). 124 frames ~ 31 latent frames: ~27k video tokens at 720p vs
  ~16k at 540p, plus audio tokens (not computed). Attention memory grows with the packed sequence, so 720p is the bigger step.
- Text-only vs start frame (`minimax_h3_main.py:1198-1260,2127`; `conditioner.py:205-221`): a start frame (1) is encoded by the video VAE
  (result moved to CPU) and appended to the packed sequence as one keyframe latent (~+880 tokens at 720p, ~+3%), and (2) is passed to the
  Qwen3-VL conditioner as a picture, so the vision tower runs and its image tokens join the text sequence (handler comment `:2205-2208`:
  text-only FL2VA "never needs the vision tower"). Extra cost is real but small next to the 720p/540p step; no measured numbers exist in the tree.

## 4. Free-VRAM check before the run, and a second process holding ~5 GB

- Handler: no. The only GPU read is `torch.cuda.get_device_properties(0).total_memory` (`:2658-2662`) - total capacity. No `mem_get_info`
  anywhere under `models/minimax_h3/`. `load_model` / MMGP also size from total (`MM:offload.py:3314`). So 5 GB held by another process is
  invisible to the pass-length policy and to the MMGP budgets: the engine plans as if the whole card were free, and a peak that fits in
  ~32 GB minus the foreign 5 GB can OOM only when activations plus streamed blocks exceed ~27 GB (unmeasured here).
- Engine wide: `--vram-safety-coefficient` default 0.8 (`HP:wgp.py:2174-2179`) caps model budgets at 0.8 x total; again total, not free.
- Hub HEAD (`hub/core/plan.py:63-80`, `vram.py:70-90`): NVML reading before each job. Resident model already loaded: run if `free >= need - ours + margin`
  (margin 1024 MB). Different model: if a learned peak (`need`, per model, in memory only, last 3) exists, run only if
  `total - foreign - 500 >= need + margin`, else hold "<program> is using N GB on Server GPU"; with no learned peak, hold only when
  foreign >= 16384 MB (`FIRST_RUN_FOREIGN_MB`, `plan.py:10`). A 5 GB foreign process therefore never holds a first H3 run.
  Learned peaks are per model, not per size (`dispatch.py:228-231`; R3 section 4.2), so a 540p clip can teach a need that 720p exceeds.
- Hub working tree: `plan.decide` takes no memory input; "Memory other programs use never holds a job" (`hub/core/plan.py:1-5`). No check at all.
- `run_anyway` skips even the HEAD plan (R3 section 4.2).

## 5. The engine's own settings advice for a 32 GB card

- No 32 GB-specific recommendation in `docs/` (`CLI.md`, `INSTALLATION.md:296-297`, `TROUBLESHOOTING.md`: "Use lower resolution or shorter videos", "--profile 5",
  "--perc-reserved-mem-max 0.3", "Clear GPU cache between generations" at `TROUBLESHOOTING.md:75`). H3 is not in `docs/MODELS.md`.
- The handler is the only source: the tables above (32 GB falls in the unbounded top tier = full 345-frame pass at 540p and 720p for every
  checkpoint), "Full H3 ... roughly 54 GB of model RAM ... 64 GB system RAM recommended" (`:818-819,1339`; non-blocking warning), fused default
  243 frames, 1152x640, 4 steps (`:2224-2240`, steps allowed 4-8, `:73-74`), fused measured on 24 GB: 345 frames at 1280x704/1344x768 (`:690-697`).
  The tree sets no profile for H3; `docs/CLI.md:115` calls profile 4 "Default and recommended".
- The plan's statement "The 32 GB card runs 540p/720p one-pass" (the project plan, retired) matches the tables; no engine measurement for 32 GB is in the tree.

## Facts that bear on the failure

1. Nothing in the engine or handler checks free VRAM; a 124-frame 720p pass is inside the table for 32 GB, so the policy does not intervene.
2. The sentence hides the real exception; the engine's terminal/worker log holds the "Tried to allocate X GiB ... free" line (device total, allocated, free).
3. Image -> video: the worker is stopped/re-spawned by the Hub (or `release_model` runs), so the image model is not the cause unless it lives in another process.
4. Open measurements that would settle it: the traceback line, peak VRAM of a 540p vs 720p H3 run, and the foreign process's resident size at load time.
