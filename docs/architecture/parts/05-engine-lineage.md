# 5. The engine, the worker, and the lineage

> **Status 2026-10-17:** the live engine is upstream WanGP 18.05 at `af2ed29`; the fork described in 5.1–5.2 is the old engine, kept untouched in its own folder. `HP:`/`UP:` citations are reads of checkouts outside the repo; neither source is in the repo.

This section covers where the Hub's image engine comes from and how the Hub drives it. It describes the worker process, the model catalog and registry, and the GPU memory guard. It ends with the facts a future video module would build on.

Notation:

- A plain path such as `hub/worker/wan2gp.py:37` is in the Hub repository (with the Stage 6 to 9 work).
- `HP:` is a checkout of the HocusPocus source. Its engine lives under `HP:app/`.
- `UP:` is a checkout of upstream Wan2GP.
- "The engine" is Wan2GP's `wgp.py` together with its `shared/` and `models/` packages.

---

## 5.1 Lineage: Wan2GP → Maestro → HocusPocus → the Hub

### 5.1.1 The chain as the sources state it

| Layer | What it is | Source |
|---|---|---|
| **Wan2GP / WanGP** (deepbeepmeep) | The generation pipeline. The upstream reference copy reports `WanGP_version = "17.17"` and `settings_version = 2.79`. | `UP:wgp.py:181-182`; credited at `HP:README.md:385` |
| **Maestro** (Blaine Brown, `Blizaine/Maestro`) | "A local AI video, image, and music studio built on the Wan2GP pipeline". Its first public release (1.0.0) already had Studio mode, **Director mode** (an LLM plans a music video or short film end to end), Music mode, Edit modes, Tools, Voice, hardware auto-tune and LoRA management. | `HP:CHANGELOG.md:521-551`; `HP:README.md:5`, `:384` |
| **HocusPocus** | "an experimental, **non-commercial** fork of Blizaine/Maestro … We keep that foundation and add the missing production layer". Product version `0.10.0`. | `HP:README.md:5`; `HP:VERSION` |
| **The Hub** | Uses only the engine (`wgp.py` through `shared.api`), driven in-process by its own worker. | `hub/worker/wan2gp.py:1-8` |

The README states the lineage in one line: "**Wan2GP → Maestro → HocusPocus**, plus Hunyuan3D, MiniMax H3, ostris's H3 style corpus, Pinokio, and the models credited below" (`HP:README.md:372`).

On versions, the HocusPocus changelog says: "Product version comes from the repo-root `VERSION` file. Historical Maestro releases below 0.9.0 are the upstream lineage. WanGP pipeline history lives in app/docs/CHANGELOG.md" (`HP:CHANGELOG.md:3-5`). Entry `[0.9.0]` is the "First HocusPocus preview. Product versioning is independent of the Maestro lineage" (`HP:CHANGELOG.md:75-78`). Entries `[1.0.0]` to `[1.6.5]` are Maestro releases.

### 5.1.2 What HocusPocus presents as its additions

The following are taken from the README and CHANGELOG. Some of these features first appear in the Maestro-lineage changelog entries; the table marks where.

| Feature | What the source says | Source | First changelog appearance |
|---|---|---|---|
| **Director** | "takes a brief (or a song) and turns it into reviewable shots, prompts and references … Auto mode runs analyze → plan → images → clips → assemble" | `HP:README.md:39` | Maestro 1.0.0 ("Director mode", `HP:CHANGELOG.md:534-537`) |
| **Productions** | "keeps the whole thread so you can resume or retake one shot"; "serializes that state so a crash is a resume" | `HP:README.md:39`, `:365` | HocusPocus 0.10.0 ("Productions and music videos", `HP:CHANGELOG.md:35-40`) |
| **Studios** (Character Creator, Lips Creator) | "Open **Studios → Lips Creator**, next to **Character Creator**" | `HP:README.md:55`, `:105-109` | 0.10.0 (Lips Creator, `HP:CHANGELOG.md:42-46`) |
| **Wizard** | "an in-app director: 'open the concert scene'…"; "**Wizard** and **MCP** call the same backend tools the buttons use" | `HP:README.md:233`, `:367` | – |
| **Characters** | Character Creator: "one photo → H3 360° turntable → … Hunyuan multi-view mesh"; Series Lab "characters in one click" | `HP:README.md:207`; `HP:CHANGELOG.md:11-13` | 0.10.0 |
| **Video 3D** | "a real compositor (not a video model pretending to be a camera)"; renders in the browser with Three.js | `HP:README.md:209`, `:366` | 0.10.0 (`HP:CHANGELOG.md:42-46`) |
| **MiniMax plates** | The hero image is "a real **Video 3D** production (world compositor, image lip-sync, MiniMax plates on the screens)" | `HP:README.md:15` | – |
| **MiniMax H3** | "Pick MiniMax H3 for picture + native stereo audio"; FL2VA and Ref2VA | `HP:README.md:43`, `:195` | Maestro 1.5.5 ("native local H3 Base FL2VA generation", `HP:CHANGELOG.md:222-228`) |
| Story Lab, Comics, Series Lab, Video Editor, Style sheet | Listed under "What you can do" | `HP:README.md:165-279` | mixed |

The README also describes the overall stack (`HP:README.md:358-370`):

1. Pinokio owns Install / Start / Update / Reset.
2. FastAPI (`app/`) is the studio server and the React UI (`ui/`) is the control surface.
3. Generation "still runs on the WanGP lineage Maestro already integrated — Wan, Hunyuan Video, LTX, Flux, audio models — plus an isolated **MiniMax H3** ComfyUI runtime … and an isolated **Hunyuan3D** env".
4. Director is a multi-pass LLM planner.

### 5.1.3 The engine HocusPocus carries

- `HP:app/wgp.py:99-101`: `target_mmgp_version = "3.7.6"`, `WanGP_version = "10.9875"`, `settings_version = 2.57`.
- The HocusPocus `shared/api.py` has no `list_model_defs`; upstream has it at `UP:shared/api.py:601`. The Hub uses that method to tell the two apart: the HocusPocus engine is the "legacy" flavour: `Upstream.probe` accepts a session that has the method (or a root whose `shared/api.py` defines it), and `Fork.probe` takes what upstream declines (`adapters/upstream.py:36-44`, `:65-80`; `adapters/fork.py:87-100`; probe order, `adapters/__init__.py:18`).
- The change record confirms the live server of that time: the server's engine was the fork HocusPocus carries (WanGP 10.9875, no `list_model_defs`).
- The fork's engine is installed in its own folder on the server and runs with its `app/env/bin/python`. The Hub's installer of that time refused to run unless both existed (§A of the change record, as it then stood).
- Licence: "**WanGP Non-Commercial Evaluation License 1.1**, inherited through Maestro from Wan2GP" (`HP:README.md:422-424`).

### 5.1.4 What the Hub keeps, and what it does not use

The Hub keeps **only the generation engine**. The worker imports `shared.api` from the engine root and calls `api.init(...)`. That call imports `wgp` into the worker's own process (`hub/worker/wan2gp.py:138-143`).

Nothing else of HocusPocus is started. The Hub uses the engine's built-in programming interface (`shared.api`) and nothing of HocusPocus: it does not start it, its window or its services. The worker's own code imports only the standard library and its sibling modules (`hub/worker/*.py` import lists).

| HocusPocus subsystem | Where it lives | Used by the Hub? |
|---|---|---|
| React UI | `HP:ui/` | No |
| Pinokio launchers | `HP:pinokio.js`, `install.js`, `start.js`, `update.js`, `reset.js`, `*_install.js` | No. The Hub installer only checks that `wgp.py` and the env Python exist. |
| FastAPI studio server | `HP:app/launch.py`, `_launch_runtime.py`, `core_runtime.py`, `HP:app/routers/` (71 entries) | No |
| Director pipeline | `HP:app/services/director_*.py`, `services/director/` | No |
| Studios / Series / Video 3D / Comics | `HP:app/services/series_*`, `world3d_*`, `routers/scene*`, `routers/comics.py`, … | No |
| Task database | `HP:app/services/task_manager.py:32` (`.maestro-tasks-v1.sqlite3`) | No. `wgp.py` does not import `task_manager` directly. |
| Prompt enhancer | `HP:app/shared/prompt_enhancer`, `models/minimax_h3/prompt_enhancer.py` | No. It is forced off; see `FORCED_CONFIG` and `FORCED_TASK` below. |
| Plugins | `HP:app/plugins/` (nine `wan2gp-*` folders), `plugins.json` | No. `enabled_plugins: []` is forced and the plugin keys are dropped. |
| Engine `services` config block, LLM engines | `server_config["services"]`, `llm_engines` | No. These keys are dropped from the Hub's config copy. |
| MCP / Wizard | `HP:app/services/local_mcp.py`, `mcp_*.py`, `routers/wizard_workflow_executor.py` | No. The Hub has its own tool server (part 4). |

**One nuance.** `wgp.py` itself imports helper modules from HocusPocus's `app/services/` package. So these run inside the Hub's worker as part of the engine:

- `services.job_lifecycle` at import time (`HP:app/wgp.py:85`).
- `memory_trim`, `hardware_detect`, `perf_recommend`, `managed_preprocessors`, `mix_concat`, `wangp_submission` and `h3_runtime_policy`, imported lazily or later in the file (`HP:app/wgp.py:191`, `:2683-2684`, `:5525`, `:6668`, `:7243`, `:7636`).

They are engine dependencies, not the HocusPocus service layer.

**The requirement.** The engine the Hub drives must not depend on the HocusPocus/Maestro install. At this snapshot it did in three ways: the engine root and the Python that runs it are HocusPocus's own (`engine.root`, `engine.python`, 5.1.3), `wgp.py` imports the helper modules above from HocusPocus's `app/services/`, and the Hub writes its pointer definitions into that install's `finetunes/` folder (5.3.4). 5.6 records what the seam changes and what is not yet done.

### 5.1.5 Engine facts the Hub keeps

- **Both flavours kept.** The legacy translation stays alongside upstream. That means factory defaults underneath the task, `FG`→2 for the multi-prompt type, and flat LoRA names. Nothing of HocusPocus but `shared.api` is used.
- **Pointer definitions.** Pointers live in `<engine>/finetunes/`. `autoreg.refresh` deletes any `hub_auto` file left in `data/engine/definitions/` (`hub/core/autoreg.py:229-237`).
- **Empty folders in the scratch folder.** A failed fetch can leave an empty `pose/` folder and a `.cache/` in the Hub's scratch folder `data/engine/gpu0/config/ckpts`. Because that scratch folder is searched first, an empty folder would hide the complete bundle in the model folder, for every model, on every restart. `tidy_scratch` removes them at every worker start.
- **Pointer models.** Whether an `auto_…` model generates on the server is recorded as **unverified**.
- **Hand patches.** Patches on the server to `hub/core/jobs.py`, `hub/core/supervisor.py` and `hub/worker/wan2gp.py` have never had their contents verified.

---

## 5.2 The worker

### 5.2.1 Spawn and lifetime (`hub/core/supervisor.py`)

- **Command line.** `make_spawn` builds the command (`supervisor.py:59-64`); `worker_args` passes `--root`, `--state`, one `--models` per folder, `--profile N` only when a memory profile is chosen, then `--` and the engine args (`:74-81`). The child runs as `python -B -s -X utf8 hub/worker/main.py --fd N --parent PID …`. It gets a `socketpair` end via `pass_fds` and `start_new_session=True` (`:166-173`).
- **Memory profile.** `engine.profile` is `"engine"` (leave the engine config's own) or one of the engine's numbers. `engine.profile_video` is `"same"` (follow `engine.profile`), `"engine"` or a number. `job_profile(engine, kind)` returns `profile_video` for a job on a model whose catalog `kind` is `"video"` unless it is `"same"`, else `profile` (`:67-71`). `LaneMemory._follow_profile` (`hub/core/enginelane.py:72-82`) runs before every job (`_before`, `:60-65`): when the arguments for that job's model kind differ from the running spawn's, it replaces them and stops the worker, so `_ensure` starts it again with the new `--profile`. The worker reads `--profile` as a float (`hub/worker/main.py:132`), hands it to `Engine` (`:154`, `:205`), and `seed_config` writes it under `profile`, `video_profile` and `image_profile` of its config file (5.2.2, 5.2.3). So the profile is fixed per worker start, never changed under a loaded model; a picture after a clip, or the reverse, restarts the worker only when the two profiles differ. The lane also stops the worker after every clip job and before a job on another model (5.4.4), so in practice each clip runs in a worker started for it.
- **Environment.** `worker_env` builds a clean environment: `PATH`, `HOME=<data>/engine-home`, `LANG=C.UTF-8`, `CUDA_DEVICE_ORDER=PCI_BUS_ID`, `CUDA_VISIBLE_DEVICES=<gpu uuid or index>`, plus `protocol.OFFLINE_ENV`, and `LD_LIBRARY_PATH` if set (`supervisor.py:40-46`).
- **States.** `none | starting | ready | stopping | down` (`supervisor.py:124`).
- **Ready.** The worker becomes `ready` on its `ready` event (`supervisor.py:209-213`).
- **Start timeout.** 600 s (`:121`); on expiry the state becomes `down` with "The engine took too long to start" (`_start_timeout`, `:193-197`).
- **Crashes.** Backoff is 2 s, 10 s, 30 s. Three crashes within 600 s set `down` (`supervisor.py:27-29`, `_watch` `:224-248`). Any failure while starting also sets `down` (`:238-240`). `reset()` clears `down` (`:135-139`). The `engine.start` bus message calls it (`hub/core/routes.py:105-110`), but no screen sends that message.
- **OOM.** A worker taken by the kernel for memory reports "Engine stopped unexpectedly (signal KILL)" (`exit_text`, `:110-116`) and the lane restarts it lazily. The unit sets `OOMPolicy=continue` (`deploy/hub.service:15`), so systemd leaves the Hub running when its child is the one the kernel takes.
- **Stop.** Send `{"op":"stop"}`, wait 5 s, then SIGTERM, wait 3 s, then SIGKILL (`supervisor.py:259-278`).
- **Orphans.** A pidfile `<data>/run/worker-<gpu>.pid` records pid and start time. `kill_orphan` kills a leftover worker with the same pid, start time and script (`supervisor.py:91-107`, `_write_pidfile` `:186-191`).
- **Dying with the controller.** The worker sets `PR_SET_PDEATHSIG=SIGKILL` (`hub/worker/main.py:61-67`). It also exits on EOF or on any send failure to the socket (`main.py:51-58`, `:63-73`).
- **Lane creation.** `create` picks the first GPU marked `engine` in settings, else GPU 0. The state directory is `<data>/engine/<gpu id>` (`hub/core/engine.py:212-229`). If the engine's Python or root is missing, the lane starts `down` with "run hub init" (`engine.py:227-228`).

### 5.2.2 Boot: `Engine.open` (`hub/worker/wan2gp.py:124-149`)

1. `chdir` to the engine root, "as the engine expects" (`:127`).
2. Empty and re-create `<state>/outbox` and `<state>/settings` (`:128-132`).
3. Delete `queue.zip` and `error_queue.zip` from both the engine root and `<state>/config` (`QUEUE_FILES`, `:37`; `:133-136`).
4. `seed_config(root, <state>/config, outbox, model_folders, profile)` (`hub/worker/wgpconfig.py:56-90`, called at `wan2gp.py:137`) writes the Hub's own `wgp_config.json`:
   - It starts from the engine's `wgp_config.json`. If that is missing it uses a minimal default (`attention_mode: auto`, `transformer_quantization: int8`, `text_encoder_quantization: int8`, …) (`wgpconfig.py:64-72`).
   - It deletes every `notification_*` key and every `DROPPED_CONFIG` key (`:73-75`).
   - It applies `FORCED_CONFIG`, plus `save_path`, `image_save_path` and `audio_save_path`, all set to the outbox (`:76`).
   - If a memory profile is picked in Settings it writes it under `profile`, `video_profile` and `image_profile` (`PROFILE_KEYS`, `:24`, `:77-78`); with no pick the engine config's own stays.
   - If model folders are set, it writes `checkpoints_paths = search_paths(...)` (`:79-80`).
   - It writes atomically with mode 0600 (`:81-89`).
   - The docstring explains why the file must exist before start: "otherwise the engine falls back to reading the root's config and writes the result into ours" (`:60-62`).
5. `search_paths` (`wgpconfig.py:38-53`). The first entry is the Hub scratch folder `<state>/config/ckpts`, which is "the engine's write target". Then come each owner model folder and its first-level subfolders, without following symlinks. `tidy_scratch` runs here.
6. `tidy_scratch` (`wgpconfig.py:27-35`) removes `<scratch>/.cache` and every empty folder under the scratch folder. This is the empty-folder fix (5.1.5).
7. The engine root is put on `sys.path` and `shared.api.init(root=…, config_path=…, output_dir=outbox, cli_args=[*args, "--settings", <state>/settings], console_output=False)` is called (`wan2gp.py:138-142`). `init` creates a `WanGPSession` and calls `ensure_ready()` (`HP:app/shared/api.py:965-983`).
8. `self.w = sys.modules["wgp"]` (`:143`). `adapters.select(root, session)` picks the engine line's adapter (`:144`; 5.6): `Upstream` when the opened session has `list_model_defs`, else `Fork`. The flavour word `self.api` is the adapter's (`adapter.flavour`, `"upstream"` or `"legacy"`, `:147`); no other code in `wan2gp.py` names an engine line.
9. The worker replaces `w.get_lora_dir` with `catalog.lora_dir` bound to the adapter, because the engine's own version creates missing folders (`:145-146`; `hub/worker/catalog.py:1-6`, `:82-99`).
10. `w.server_config.update(FORCED_CONFIG)` applies the forced values again at runtime (`:148`).
11. `open` returns `{api, version, settings_version}` (`:149`). The worker sends it in its `ready` event (`main.py:211`).

### 5.2.3 The forced and dropped keys

The config keys are defined in `hub/worker/wgpconfig.py:17-24`; the task keys in the adapters (`hub/worker/adapters/fork.py:24-27` and `upstream.py:22-24`, the same values in each). `wan2gp.py` re-exports `FORCED_CONFIG` (`:32`).

**`DROPPED_CONFIG`.** These keys are deleted from the copied config (`wgpconfig.py:17`), together with any `notification_*` key (`:74`).

| Key | Why (code comment `wgpconfig.py:11-16` and engine use) |
|---|---|
| `services` | Keys of the engine's config that "never carry over" (`wgpconfig.py:13`). In HocusPocus this block holds FlashVSR and auto-performance settings (`HP:app/wgp.py:2681`, `:6010-6013`). |
| `llm_engines` | Language-model engine configuration. Not used. |
| `enabled_plugins` | No plugins. |
| `installed_remote_plugins` | No plugins. |
| `notification_*` | "no notifications" |

**`FORCED_CONFIG`.** These keys are written into the file and re-applied in memory after start (`wgpconfig.py:18-20`, `:76`; `wan2gp.py:148`).

| Key | Value | Why |
|---|---|---|
| `image_output_codec` | `"png"` | "plain PNGs". The engine's default is `jpeg_95` (`HP:app/wgp.py:3479`). `save_image` renames the file extension to match the codec (`HP:app/shared/utils/audio_video.py:694-695`). |
| `metadata_type` | `"none"` | "no metadata". The engine writes metadata only for `"json"` or `"metadata"` (`HP:app/wgp.py:9525-9534`). |
| `enhancer_enabled` | `0` | "no prompt enhancer". A value above 0 makes the engine provision enhancer assets (`HP:app/wgp.py:3919-3926`). |
| `enhancer_mode` | `1` | Not automatic. Mode 0 means automatic enhancement (`HP:app/wgp.py:10860`). |
| `enabled_plugins` | `[]` | "no plugins" |
| `save_queue_if_crash` | `0` | "no queue written out after an error (it would hold the prompts)" |
| `embed_source_images` | `False` | Source images are not embedded in outputs (the engine default is also `False`, `HP:app/wgp.py:3476`). |
| `video_container` | `"mp4"` | A clip is an MP4 whatever the engine config says; `enginecat.land` takes only `.mp4` for a clip (part 1, 1.5). |

**`FORCED_TASK`.** These are laid on top of every task's settings, in both flavours, by each adapter's `translate` (`fork.py:45-54`, `upstream.py:47-50`).

| Key | Value | Why |
|---|---|---|
| `prompt_enhancer` | `""` | The per-task enhancer is off: the typed prompt reaches the model unchanged. |
| `negative_prompt` | `""` | No negative prompt. |
| `alt_prompt` | `""` | No alternative prompt. |
| `output_filename` | `"{date}-{seed}"` | "a file name that says nothing (the engine's default puts the prompt in it)". The default name is `{time}_seed{seed}_{prompt}` (`HP:app/wgp.py:9349-9356`). |

**`FORCED_VIDEO`.** Laid on top as well, but only for a task whose `image_mode` is 0, that is a clip (each adapter's `translate`).

| Key | Value | Why |
|---|---|---|
| `audio_prompt_type` | `""` | "never driven by a soundtrack": the clip keeps the sound its model makes. Both lines. |
| `MMAudio_setting` | `0` | "never a second audio model". The fork only: upstream deprecates the key (accepted, ignored). |
| `postprocess_audio` | `""` | upstream's form of the same: no audio post-process (R16 §3.4). Upstream only. |

A picture task (`image_mode` 1) does not get these keys; `tests/engine/test_video_engine.py::test_translate_forces_video_values_only_for_a_clip` pins both sides.

### 5.2.4 Engine lines and `translate` (`hub/worker/adapters/`)

`Engine._params` (`wan2gp.py:166-172`) hands the Hub's task to the adapter's `translate`, with the model's factory settings when the adapter wants them underneath (`factory_underneath`); the factory settings are cached per model.

- **`upstream`** (`Upstream.translate`, `upstream.py:47-50`). The task is the Hub's settings, deep-copied, with `FORCED_TASK` on top.
- **`legacy`** (the fork, `Fork.translate`, `fork.py:45-54`). The task is built as `factory ⊕ settings ⊕ FORCED_TASK`. The docstring explains: "Legacy engines start every task from generic defaults (30 steps, 832x480...), so the model's own defaults go underneath".
  - `multi_prompts_gen_type: "FG"` becomes `2`.
  - `activated_loras` are reduced to base names, because legacy engines "find LoRAs by file name in a flat folder".
- **Factory defaults.** The upstream adapter uses `w.get_factory_settings` (`upstream.py:53-54`; `UP:wgp.py:3257`). The fork adapter rebuilds them (`fork.py:57-71`):
  - start from `w.primary_settings`;
  - add `settings_version`;
  - set a resolution of 1280x720 or 832x480 from the base type name, and a `flow_shift`;
  - call the handler's `update_default_settings`;
  - lay the definition's `settings` on top.

### 5.2.5 Running one task (`Engine.run`, `hub/worker/wan2gp.py:181-242`)

- **Loading.** If the requested `model_type` is not the loaded one (`loaded()` reads the private globals `wan_model` and `transformer_type`, `:151-153`), the worker emits `{"ev":"model","state":"loading"}` (`:187-189`).
- **Submission.** Under the lock, a cancel that arrived before the run is honoured. Otherwise `job = self.session.submit_task(params)` is called (`:195-200`). `submit_task` is the engine's documented single-task call (`HP:app/shared/api.py:277`; `HP:app/docs/API.md:31`, `:136`).
- **Events.** The worker iterates `job.events.iter(timeout=0.5)` (`:202-212`):
  - `error` events are collected;
  - for each `progress` event it samples memory, emits `model: loaded` on the first non-`loading_model` phase, and emits `{ev:"progress", phase, step, steps, pct, text}` from the engine's `ProgressUpdate` (`HP:app/shared/api.py:596-629`).
- **Result.** `job.result()` is read. The worker then joins the private `job._thread` for up to 30 s, because "the engine resets its state after the result" (`:213-217`).
- **Chained passes.** For a clip task (`image_mode` 0) that returns more than one file, the worker deletes all but the last and emits only that one: each file the engine writes for a chained pass holds the ones before it (`:227-231`). `Engine.made` keeps how many files the engine returned (`:226`), which `probe.py` reads.
- **Outputs.** One `{ev:"output", file:<abs path>}` is emitted per path left in `result.generated_files` (`:234-235`). In HocusPocus that list is the new entries of the engine's `file_list` plus `audio_file_list` (`HP:app/shared/api.py:706-710`).
- **Done.** `task_done` reports `ok` (files present, no errors, not cancelled), `seconds`, `model`, `peak_vram_mb` and `peak_rss_mb`. When the task failed it adds `error = faults.failure(...)` (`:238-241`).
- **Busy.** The worker runs one task at a time. A `run` that arrives while busy is answered with `task_done ok:false` "The engine is busy" (`hub/worker/main.py:91-93`). The run executes on a daemon thread. An exception, including `SystemExit` from the engine, still produces a `task_done` (`main.py:94-109`).

**Cancel.** `Engine.cancel(job_id)` calls `job.cancel()` on the running engine job. If the job has not started yet, it records `_cancel_pending` (`hub/worker/wan2gp.py:174-179`). On the core side, `EngineLane.cancel` sends `{"op":"cancel"}` or remembers the id for a job not yet running (`hub/core/engine.py:95-101`). The core checks `_cancelling` before each task (`engine.py:116-117`).

**Memory sampling (`Peaks`, `hub/worker/wan2gp.py:65-102`).**

- At construction it calls `torch.cuda.reset_peak_memory_stats()` and records the device's used memory (`mem_get_info`: total − free, whole card) and `memory_reserved`.
- `sample()` runs at every progress event and takes the max of whole-card used memory.
- The final sample also adds `start + max_memory_reserved − reserved_at_start` to cover the gaps between events.
- RSS comes from `/proc/self/status` `VmRSS` (`rss_mb`, `:53-62`). For a clip the final sample also takes `VmHWM`, the process's own high-water mark since it started (`sample(final=True, mark=True)`, `:90-102`; `:223-224`), which a worker started for one clip makes its true peak.

**Faults (`hub/worker/faults.py`).** `failure(errors, cancelled)` reduces the engine's errors to one line:

- `{stage:"cancelled", text:"Cancelled"}` if cancelled;
- `{stage:"oom", text:"Out of GPU memory"}` if the message contains "out of memory";
- otherwise the first non-empty message (up to 600 characters) plus `where()`. `where()` gives the raising frame from a live traceback, or the last two `File …` lines of a text traceback (`faults.py:12-37`).

The core's `EngineFailed` stages are `validation | generation | cancelled | runtime | oom | crashed` (`hub/core/supervisor.py:32-37`).

### 5.2.6 The protocol (`hub/worker/protocol.py`)

The wire format is NDJSON over a socketpair, one JSON object per line, with at most `MAX_LINE = 1 MiB` per line and `PROTO = 2` (Stage 9 step 3): `run` carries the Hub's request, which the worker's adapter turns into the engine's task. The supervisor refuses a worker whose `ready` names another `proto` ("The engine's worker speaks protocol <n>; the Hub speaks 2 (install the Hub again)", `OTHER_PROTO`). The Hub-side event types of 5.6 (`Loading`, `Loaded`, `Progress`, `Output`, `Done`) are still not on the wire: the events below keep their shape and the engine's phase words still cross in `progress` (a Stage 9 debt, 5.6.2).

| Direction | Message | Fields |
|---|---|---|
| core → worker | `run` | `job, task, request` (a `PictureRequest`, `ClipRequest` or `JoinRequest` plus `kind`, `engineapi.py`; checked by `enginewire.request_parse` on both sides: the lane before it sends, the worker when it reads) |
| core → worker | `cancel` | `job` (cooperative; ends with `ok=false`, stage `cancelled`) |
| core → worker | `query` | `id, what:"catalog"` (read-only engine facts) |
| core → worker | `stop` | – (exit now; frees the CUDA context) |
| worker → core | `ready` | `pid, proto, engine:{api, version, settings_version}` |
| worker → core | `fatal` | `text` (start failed; the worker exits) |
| worker → core | `model` | `state: loading\|loaded, model, rss_mb` |
| worker → core | `progress` | `job, task, phase, step, steps, pct, text` |
| worker → core | `output` | `job, task, file` (absolute path in the outbox) |
| worker → core | `task_done` | `job, task, ok, seconds, model, peak_vram_mb, peak_rss_mb, error?:{stage,text}` |
| worker → core | `reply` | `{id, data}` or `{id, error}` |

The supervisor adds a synthetic `exit` event (`{text, crash}`) when the process ends (`hub/core/supervisor.py:224-248`).

A malformed line makes the worker exit with code 2 (`main.py:82-85`). In the core, a malformed line kills the worker (`supervisor.py:218-222`).

`main.py` also runs three jobs that need no controller, chosen by its arguments (`parse`, `main.py:121-148`; `main`, `:187-217`):

- `--dump-catalog OUT.json` opens the engine and writes the catalog (`dump`, `:151-168`).
- `--dump-engine OUT.json` writes the engine's own facts in one sterile file (`dump_engine`, `:170-185`; `hub/worker/enginedump.py`). It
  opens the engine on an empty state folder of its own (a temporary one, removed after), never the model folders, and refuses
  `--models`, `--profile` and `--dump-catalog`. It reads and submits nothing: no task, no model load, no weight file opened, no
  download or presence call (the catalog is built through `_Quiet`, `enginedump.py:139-153`, which finds no file). `FORMAT = 1`
  (`:28`). The file holds the engine's flavour and version, which of the engine names the Hub reads exist (`PROBE`, `:30-34`),
  every class `shared.api` defines, the parameters of `generate_video`, each architecture's handler methods, the families, the
  primary settings, the config keys, each shipped model's definition, settings and factory values, and the catalog built from
  those (`build`, `:155-192`). The definitions (`finetunes/`) and the Hub's pointers (`hub_auto`) are left out whole
  and counted under `left_out`. `redact` (`:203-231`) turns paths into `<path>` and URLs into base names and drops the
  catalog's roots, weight facts and presence; `write` (`:264-274`) then refuses to write when the finished text still names the
  engine root, the state folder, the home folder or the host name (`Leak`, a one-line message, nothing written). The fake engine
  is rebuilt from such a file by `tests/engine/fake_engine/rebuild.py`, with `overlay.json` for the test-only edits
  (`tests/engine/test_dump_engine.py`, `test_fake_rebuild.py`).
- `--probe-continue CLIP [--chain K] [--model ID] [--frames N]` (`hub/worker/probe.py`; needs `--state` and a `--chain` of 1
  or more) measures a continue before the scene cap is set. It opens the engine as `--dump-catalog` does, picks the first catalog
  model whose facts say `continues` (or `--model`), and runs K steps: step 1 continues CLIP, step k the file step k-1 made. Each
  step sends the same task the Hub builds (`continue_task`, `probe.py:63-73`, the "V" route of part 2, 2.10.7) with seed 1, the
  model's default steps and a fixed prompt, moves the output from the outbox to `<state>/step<k>.mp4`, and prints one JSON line:
  the window, the files the engine returned, the source's and the output's frames, size and seconds, the growth against the
  expected `n − 1`, the peak VRAM and RSS, the process's `VmHWM` and the seconds (`step`, `:76-93`). The clips' facts come from the
  Hub's own MP4 reader (`hub/core/clip.py`) loaded by its path. Nothing is written in the engine root or the Hub's data. The
  default length is the model's default capped at the longest step (`frames`, `:54-60`). Run on a real engine, it gives the
  measures the scene cap (part 2, 2.10.7) lacks.

### 5.2.7 Offline and the network guard

- **Environment.** `OFFLINE_ENV` (`protocol.py:29-38`) sets `HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1`, `HF_HUB_DISABLE_TELEMETRY=1`, `DO_NOT_TRACK=1`, `GRADIO_ANALYTICS_ENABLED=False`, `PYTHONDONTWRITEBYTECODE=1`, `PYTHONNOUSERSITE=1` and `PYTHONUNBUFFERED=1`. It is applied both in the spawn environment (`supervisor.py:43`) and again by the worker (`main.py:189`).
- **Audit hook.** `netguard.install()` adds a Python audit hook before anything else loads (`main.py:191`; `netguard.py:44-45`):
  - `socket.connect`, `socket.sendto` and `socket.sendmsg` are refused unless the address is `None`, the socket is `AF_UNIX`, or the IP is loopback (`netguard.py:13`, `:28-34`);
  - `socket.getaddrinfo`, `gethostbyname` and `gethostbyname_ex` are refused for any host that is not a literal IP (`:14`, `:35-36`);
  - `socket.gethostbyaddr` and `getnameinfo` are refused unless the target is loopback (`:15`, `:37-41`).
- **Limit.** The module docstring warns: "Native code can bypass audit hooks; the offline environment and the OS firewall remain the wall" (`netguard.py:1-5`).
- **Effect.** A missing file fails with Hugging Face's "cannot find in local cache" and nothing is downloaded.

### 5.2.8 The core side of a task (`hub/core/engine.py`)

- **Lane.** `EngineLane` is the image lane: `kind = "image"` (`engine.py:36-37`; `api.LaneKind = Literal["image"]`, `hub/core/api.py:19`). A clip is a job on this same lane; there is no separate video lane. The catalog half of the class is the mixin `CatalogQueries` (`hub/core/enginequery.py:17`).
- **Job.** `run(job, emit)` (`engine.py:103-127`) takes the lane lock. It reads the model's catalog kind (`LaneMemory._kind`, `enginelane.py:43-49`), runs `_before` (`enginelane.py:60-65`: the profile of that kind, 5.2.1, and a stop of the worker when it holds another model, 5.4.4) and `_ensure()`, which starts the worker if needed and re-reads the catalog in the background (`engine.py:144-153`). It then runs `job.plan.tasks` in order, emitting `task {task, of}`. At the end `_after` stops the worker after a video-kind job, made or failed (`enginelane.py:67-70`).
- **Task loop.** `_task` sends `run`, records the task's model as the worker's `_resident` and consumes events (`engine.py:155-182`):
  - `model` is forwarded;
  - `progress` is rescaled to the whole job by `enginecat.progress`;
  - `output` is landed with `enginecat.land(file, outbox, outputs, clips)` and forwarded as `output {task, item, kind, w, h}` with `seconds` for a clip;
  - `exit` raises `EngineFailed("cancelled"|"crashed"|"runtime")`;
  - `task_done` is forwarded, then `enginecat.sweep` empties the outbox, then a not-ok result raises `EngineFailed`.
- **Progress.** `enginecat.progress` makes `pct` cover the whole job and never go back; loading phases do not move it (`hub/core/enginecat.py:72-79`).
- **Landing.** `enginecat.land` (`enginecat.py:119-159`) refuses a file that is not directly in the outbox (`:126-128`), then sorts it by suffix:
  - **A clip** (`.mp4`, `CLIP_TYPES`): `clip.strip` cuts the muxer's tags and `clip.facts` reads its size and length from its boxes; the file is linked or copied to `temp_path(<data>/clips, ".mp4")`; the result is `{id: "clips/<day>/<name>.mp4", kind: "clip", w, h, seconds}` (`:130-142`); every clip lands flat in its day folder. A file those two calls refuse is deleted and fails the job. Part 1, 1.5, has the box walk.
  - **A picture** (`IMAGE_TYPES`): `clean.strip` cuts its metadata, deleting the file and failing if Pillow cannot read it; it is linked or copied to `temp_path(outputs, suffix)`, which is `<data>/outputs/<YYYY-MM-DD>/<HHMMSS-mmm>[-n]<suffix>` (`hub/core/files.py:35-47`); `w, h` come from Pillow; the result is `{id: "out/<day>/<name>", kind: "image", w, h}` (`:146-159`).
  - **Anything else** is deleted and fails the job: "The engine wrote a file the hub does not take" (`:143-145`).
- **Sweep.** `enginecat.sweep` removes every file and folder left in the outbox (`enginecat.py:97-103`).

---

## 5.3 Models

### 5.3.1 How the engine discovers models

`wgp.py` globs `defaults/*.json` plus `finetunes/*.json` relative to the engine root (`HP:app/wgp.py:3388`). Each definition is then passed through `init_model_def` (`HP:app/wgp.py:3367`), where the family handler's `query_model_def` fills in the architecture's capabilities.

Definitions are read only when the engine starts. This is why the Hub restarts the worker after it writes or removes a pointer (`_reread`, `hub/core/enginequery.py:98-109`). HocusPocus ships 222 files in `app/defaults/`; upstream ships 239.

### 5.3.2 The catalog (`hub/worker/catalog.py`, `hub/worker/catalogvideo.py`)

`build(w, root, adapter)` (`catalog.py:123-164`) walks `sorted(w.models_def)`. `keys = adapter.families` (`:126`) is the engine line's key rules (`KeyFamilies`, 5.6): every clip helper in `catalogvideo.py` takes `keys=` and names no key family itself, and `switches = engine_switches(w, keys=keys)` is read once (`:128`).

**Filter.** It keeps a definition that is `visible` (not false) and either has **`image_outputs` truthy** (a picture model) or yields video facts (`catalogvideo.video_facts` is not None: a native clip model; `:134-136`). Audio-only models, models that cannot take a text prompt or a reference manifest, models that run in a sidecar runtime and models without a frame lattice or resolution tiers are left out. The entry says which it is with `kind` (`"image"` or `"video"`). Part 2, 2.10.1, lists every definition field the clip facts read.

**Entry.** Each entry is built by `describe` (`catalog.py:61-79`), then `kind` and `video` are added (`:151-156`):

| Field | Source |
|---|---|
| `id`, `name` | model type; `model_def.name` |
| `family` | `w.get_model_family(…, for_ui=True)` mapped through `families_infos` |
| `status` | `presence()` mapped `0/1/2 → missing/partial/available` (`STATUS`, `:20`) |
| `defaults` | `num_inference_steps`, `guidance_scale`, `embedded_guidance_scale`, `resolution` from factory settings (`DEFAULT_KEYS`, `:19`) |
| `guidance_key` | `embedded_guidance_scale` if `embedded_guidance`; `guidance_scale` if `guidance_max_phases ≥ 1`; else none (`:40-46`) |
| `ref_choices` | the `video_prompt_type` values of `image_ref_choices.choices` (`:49-58`) |
| `block` | `vae_block_size` or 16 |
| `lock_steps` | `lock_inference_steps` |
| `loras`, `lora_dirs`, `lora_recursive` | LoRA folders: primary first, plus the read-only "linked" dirs the adapter knows of (`lora_dirs`, `:102-107`, from `adapter.lora_search`); recursive only for upstream (`adapter.lora_recursive`); false for a clip model whose definition sets `loras_disabled` (`:156`) |
| `base` | `hub_base` when the definition is marked `hub_auto`, else none |
| `kind`, `video` | `"image"` and `None`, or `"video"` and the clip facts: `fps`, `frames {min, step, max, default}`, `steps`, `tiers [{name, sizes}]`, `references` (an identity role may carry `detail {key, choices, default}`), `one_pass`, `continues`, `overlap`, `text_encoders`, `text_encoder_default`, `text_encoder_names`, `text_encoders_found` (`video_facts`, `catalogvideo.py:196-225`) |
| `video_task`, `steps_range` | a clip model only: the task key the text encoder goes under with its default, and the definition's step bounds (`catalog.py:154-155`) |

**Entry shape mark.** `SHAPE = 7` (`catalog.py:21`) is hashed into the controller's catalog cache key (5.3.5), so a catalog cached before a change to the entry shape is not served. Shape 7 added the clip facts `continues` and `overlap` and the identity role's `detail`.

**Continue and detail facts** (`catalogvideo.py`, read from the definition and the model's settings, no model named):

- `continuation(model_def, settings, step, lo, hi, keys=)` (`:152-165`) is the overlap a model continues a clip with, or None. "V" must be in `image_prompt_types_allowed` and the model must not be a reference-manifest model; the overlap is `sliding_window_defaults["overlap_default"]`, else the settings' `sliding_window_overlap`, a whole number above 1 with `overlap − 1` on the frame lattice and `min + overlap − 1 <= max`. `video_facts` sets `continues` to whether it is not None and `overlap` to its value (`:221-225`). One pass of a continue is `frames + overlap − 1` frames and the clip grows by `frames − 1` (5.5.1, part 2, 2.10.7).
- `reference_detail(model_def, settings, keys=)` (`:138-149`) is the reference detail a manifest model announces: its `omni_reference_detail_choices` (label, value pairs, in the engine's order), `omni_reference_detail_default` and the one setting ending `_reference_detail` as the task key. None when any part is missing or the default is not a value. `picture_refs` attaches it to the identity role (`:132-133`). The field and suffix names these helpers match come from the adapter's facts file (5.6), not from this module.

**Presence.** `presence()` (`catalog.py:110-120`) first asks the engine's own `get_model_download_status`. If that says missing (0), the model still counts as `partial` (1) when any variant of its main `URLs` file is found by `deps.get_local_model_filename`. A path URL, as a pointer has, is used as it is.

**Top level.** The catalog also carries `engine: {api, version, settings_version, root, loras_root, checkpoints}` (`:159-163`; `api` is the adapter's flavour word). `Engine.catalog()` adds `weights` from `definitions.weights` for the picture models only; if that fails, the key is left out (`hub/worker/wan2gp.py:155-164`). `--dump-engine` builds the same catalog through `_Quiet` and drops the weights (5.2.6).

### 5.3.3 Weight facts (`hub/worker/definitions.py`)

`weights(w, deps, root, image_types)` (`definitions.py:43-62`) returns three things:

- **`named`.** Every `.safetensors` / `.sft` base name mentioned anywhere in the engine's own definitions (`:31-40`).
- **`types`.** All of the engine's own model ids.
- **`models`.** For each image model whose main file is present: its `files`, its `architecture` (`get_base_model_type`) and its definition `source` path (`:17-28`, `:52-61`).

Definitions marked `hub_auto` are left out of all three. "so the hub's own files never count as naming a weight file, as a model to match against, or as a taken model id" (`:1-8`, `:47`).

### 5.3.4 The registry: pointer files and "auto_" models (`hub/core/autoreg.py`)

- **Scan.** `weight_files` walks every model folder at any depth, skipping LoRA folders (`autoreg.py:70-80`).
- **Statuses.** Each file gets a panel record with status `known`, `pointer` or `unknown` (`autoreg.py:191-219`):
  - **known**: the engine's own definitions name the file (`os.path.basename in named`), or its real path is a present model's file (`:197-199`);
  - **pointer**: a valid `hub_auto` pointer already names it, or one is written now (`:210-219`);
  - **unknown**: anything else, with `candidates` and `suggested`.
- **Matching** (`autoreg.py:1-14`, `:29`, `:200-205`):
  - the tensor-name Jaccard overlap must be at least `MATCH = 0.9`, using only the safetensors header (`hub/core/fingerprints.py`);
  - the size must be between `LOW = 0.25` and `HIGH = 1.3` times the matched model's file;
  - candidates are ranked by `rank()`: overlap, then a definition naming its own file, then shared name words, then the finetune, then the closest size, then the plainest definition (`:117-125`).
- **Writing.** `register` writes `<engine>/finetunes/<id>.json` (`autoreg.py:147-163`). The id is `slug(stem) = "auto_" + lowercased stem with non-alphanumerics as "_"`, with `_2`, `_3`… appended if taken (`:143-152`). The file holds:
  - `model: {name, description, architecture, URLs:[full path], hub_auto:true, hub_file, hub_base}`;
  - plus `num_inference_steps`, `guidance_scale` and `resolution` from the matched definition (`POINTER_KEYS`, `SETTINGS_KEYS`, `:35-36`).

  Nothing else is copied, because "a copied model field such as image_ref_choices makes the handler want helper files (pose models) and fetch them" (`:32-34`). A pointer that holds other keys is `stale` and is rewritten (`:99-101`, `:182-185`).
- **Base selection.** For a file, `pick` is:
  1. the choice saved in `<data>/engine/choices.json` (path → model id, `""` = "not a model");
  2. else the base of a stale pointer being redone;
  3. else the best fit (`:206-209`, `:247-264`).

  `found.bases` lists the present models a file can be set up like: the engine's own and the definitions, never a pointer (`:189`, `:267-273`).
- **Deletion.** A pointer is deleted when its file leaves the folders, when an engine definition starts naming the file, when a second pointer names it, when "Not a model" is picked, or when another base is chosen (`:177-187`, `:213-216`).
- **Trigger.** `EngineLane._fetch_catalog` runs `autoreg.refresh` on every catalog fetch. When `found.changed`, it restarts the worker once to re-read definitions, then recomputes the cache key (`hub/core/enginequery.py:84-96`).

### 5.3.5 Catalog cache and output handling (`hub/core/enginecat.py`)

- **Cache key.** `catalog_key(engine)` is the first 16 hex characters of a SHA-256 over (`enginecat.py:29-43`):
  - the entry shape mark `shape:<SHAPE>` (`catalog.SHAPE`, 7 at this tree; `enginecat.py:32`);
  - the Python path, the root, the args and the model folders;
  - the mtimes of `wgp.py`, `defaults/`, `finetunes/`, `ckpts/`, each model folder, and the first-level subfolders of `ckpts` and of each model folder.
- **Cache file.** `read_cache` / `write_cache` keep `{key, catalog}` in `<data>/engine/catalog.json`, written atomically through `mkstemp` (`enginecat.py:46-59`; path at `hub/core/engine.py:46`).
- **Queries.** `EngineLane.query("models", rescan=…)` is `CatalogQueries.query` (`hub/core/enginequery.py:43-67`):
  - recomputes the key (`:54-57`);
  - drops the cached catalog on a rescan or a key change (`:58-59`);
  - otherwise reads the cache file (`:60-61`);
  - fetches from the worker if needed, single-flight under `_fetching` (`_load`, `:69-82`);
  - stops a worker it started only for the query, unless a model is loaded (`:80-82`).
  - `cached_catalog` (`:37-41`) answers from memory or the cache file and never starts a worker; `LaneMemory._kind` (to know a model's kind before the worker is up) and the Settings view's video sizes use it.
- **LoRA folders.** `with_lora_roots` adds `lora_extra`: the model's family folder name inside each of the LoRA roots (`enginecat.py:62-69`).
- **Outputs.** `land` (a picture to Temp, a clip to the clips root, flat in its day) and `sweep` are covered in 5.2.8.

### 5.3.6 Reference caps

The engine publishes no number for how many reference images a picture model takes (`hub/modules/generate_image/models.py:1-5`; `hub/settings.py:4-6`).

- **Setting.** The table is `modules.generate-image.ref_caps`: model-id prefix → 1 to 6. The default is `{"qwen_image_21": 6, "krea2_": 2}` (`hub/settings.py:40`), validated at `hub/settings.py:204-207`.
- **Lookup.** `ref_cap(model, caps)` uses the longest matching prefix of `model.base or model.id`, so a pointer inherits its base's cap. Otherwise it returns `DEFAULT_REF_CAP = 3` (`models.py:23`, `:75-80`).
- **Flags.** `ref_flags` picks `"I"` if the model offers it, else the first choice containing `I` (for example `"KI"`) (`models.py:83-88`).
- **A clip model** does not use the table. Its pictures and their number come from its own definition (`catalogvideo.picture_refs`), and the cap is that number clamped to the bar's three boxes (`models.ui_model`, `models.py:183-185`; part 2, 2.10).
- **Enforcement.** `build._images` refuses more references than the cap for a picture model (`hub/modules/generate_image/build.py:49-60`); `build._clip_refs` does the same for a clip (`:91-111`), and `cast.resolve` at set time (`cast.py:103-107`). The engine's own validation "stays the final word".

### 5.3.7 The weights panel

- **Core.** `EngineLane.query("weights", rescan, choose=(path, base))` saves a choice with `autoreg.choose`, forces a rescan when needed, and returns `autoreg.panel(...)`: `{bases:[{id,name}], files:[records]}` (`hub/core/enginequery.py:46-50`; `autoreg.py:267-273`).
- **Routes.** `get_weights`, `rescan` and the choose path are in `hub/modules/generate_image/routes.py:76-100` (`_panel`, `get_weights`, `rescan`, `choose_base`). The record shape is documented there: `{path, name, folder, size_mb, status: known|pointer|unknown, model, base, suggested, candidates, chosen}`.
- **Web.** `web/src/shell/settings/ImageModels.tsx`:
  - shows pointer files and files with candidates or a choice (`:24`);
  - offers "Not a model" plus each base, the suggested one marked (`:61-62`);
  - tags known files "Engine's own" and unmatched ones "Not recognised" (`:75-78`);
  - counts the rest in one line (`:27`).

---

## 5.4 GPU and VRAM

### 5.4.1 Readings (`hub/core/vram.py`)

- **When.** NVML is read only at decision points: a job's start and end, a new screen, a lane change, a refresh, and boot. Two reads within 1 s share one reading. A residency change reads at once and again `settle_s = 2 s` later (`vram.py:1-6`, `:28`, `:36-41`, `:81-98`).
- **Only the lane's own processes are looked at.** The lane's pids give its usage in a reading (`_usage`, `:46-48`). The reading is used for the baseline and for the gauge in the web; no other program's memory is a reason to wait for a job. Other programs run on the same GPU on purpose.
- **Learned needs.** `learn("vram", model, uuid, mb)` keeps the last three peaks per model and GPU, in memory only. `need()` returns their maximum (`vram.py:54-61`). Dispatch records `peak_vram_mb − baseline` from each `task_done` (`hub/core/dispatch.py:187-193`). The baseline is everything except this lane at job start (`vram.py:63-67`; `dispatch.py:96`). A learned need changes the plan's text only (5.4.2).

### 5.4.2 The plan (`hub/core/plan.py`)

`decide(Situation(lane, model, label, resident, need))` returns `Plan(light, action, text, release)` (`plan.py:28-36`). `Vram.plan` fills the situation from the lane's residency and the learned need (`vram.py:70-74`). The plan is run-or-release; it never refuses a job.

| Situation | Plan |
|---|---|
| The model is resident in the lane | green / `run`, "<label> loaded" |
| Another model is resident | amber / `release` the lane's own worker, then run: "Switching to <label>" when a need is known, else "First run of this model" |
| Nothing is resident | amber / `run`: "Loading <label>" when a need is known, else "First run of this model" |

`dispatch._once` takes the head of the queue when the lane is ready and idle, plans it, and runs `gpu.release(plan.release, "for <label>")` first when the plan names a lane (`dispatch.py:82-100`). A lane that is offline or busy leaves the job queued; the lane's own change (a worker ready, a job ended) kicks the pump again (`gpu.on_change`, `dispatch.py:44`; `kick`, `:57-64`). Nothing re-checks on a timer.

### 5.4.3 What waits, and what does not

- **A queued job** waits for the lane only. `JobBook.TRANSITIONS` (`hub/core/jobs.py:20-24`) has `queued → running | cancelled`; a queued job has no state other than its place in the queue.
- **Engine state.** A lane that is down ("Engine is offline") or busy leaves the job in the queue; its text on the screen is the lane's state (part 2, 2.1.6).
- **Other programs.** Memory they use is shown in the GPU gauge and never changes what the lane does.
- **After a release**, `_once` checks again that the job is still first in the queue and the lane idle (`dispatch.py:91-92`) and returns without running it if not; the next kick tries again. `Vram.release` reports whether every lane released (`vram.py:134-143`); the dispatcher does not act on a refusal.

### 5.4.4 Release and idle unload

- **What a release is.** Stopping the worker frees VRAM, RAM, pinned memory and the CUDA context. The engine's own swap inside one process frees less, so the lane stops the worker itself (`hub/core/enginelane.py:1-12`, `LaneMemory`).
- **When the lane releases** (`LaneMemory`, `enginelane.py:25-82`):
  - **Before a job on a different model.** `_resident` is the model of the last task sent to the running worker (`engine.py:_task`, `_resident = model`); `_before` stops the worker when it holds another model (`:60-65`). The same model is never released.
  - **After every video-kind job**, made or failed (`_after`, `:67-70`; the kind is the catalog's, or "video" when the plan's tasks are all `image_mode` 0 and the catalog is not read yet, `_kind`, `:43-49`). Each clip therefore pays a worker start and a full model load.
  - **When the job's kind wants another memory profile** than the worker was started with (`_follow_profile`, `:72-82`; 5.2.1).
  - **When settings change** the engine's paths or model folders (`configure`, `engine.py:129-141`), after a running job.
  - **Press and idle.** `EngineLane.release()` stops the worker for the "Clear the GPU cache" press and for idle unload; it is refused while a job holds the lane lock (`engine.py:79-86`). `Vram.release(lane_ids, reason)` marks the lanes `unloading` and releases them in parallel (`vram.py:134-143`).
- **`gpu.release` (bus message).** With a `lane`, it releases that lane if idle; without one, it releases every idle lane, reason `"owner"` (`hub/core/routes.py:90-103`). It is sent by "Clear the GPU cache" in the Generate taskbar and the Media bar (`web/src/modules/generate-image/run/Taskbar.tsx:37`; `web/src/screens/media/Bar.tsx:41`).
- **Idle unload.** `arm_idle` arms a timer of `idle_minutes × 60 s` after a job ends. It does so only if `idle_unload` is on, the lane holds a model, is not busy and has nothing queued. When the timer fires it re-checks and releases with reason `"idle"` (`vram.py:153-175`). Defaults are `idle_unload: true` and `idle_minutes: 10`, with a range of 5–120 (`hub/settings.py:36`, `:194-195`).
- **Lane states** published on the `gpu` bus lane: `unloading`, `loading`, `busy`, `down`, `ready` or `idle` (`vram.py:119-128`).
- **What it costs.** A worker start and a full model load for every clip and for every change of model. The learned peaks are kept per model, in memory, so a Hub restart forgets them (the text then says "First run of this model").

---

## 5.5 Video: the engine's facts, and what the Hub took from them

This part describes what the engine source holds about video tasks, and in 5.5.2 what the Hub did with each place its image path assumed. The Hub now lists the engine's native clip models as models of the Generate Image screen (part 2, 2.10; part 8). It reads their facts from the definitions, sends one clip task per press, and lands the MP4 in its own root. The rest of 5.5 (5.5.3 to 5.5.6) is the engine's side, kept as reference for the roadmap in part 8.

### 5.5.1 How a video task differs from an image task in `wgp.py`

The task fields are the parameters of `generate_video(...)` (`HP:app/wgp.py:7245` onward; H3-specific ones at `:7437-7451`). The video-relevant ones:

| Concern | Image task | Video task | Source |
|---|---|---|---|
| Mode switch | `image_mode: 1` (`> 0` = image) | `image_mode: 0` | `is_image = image_mode > 0` at `HP:app/wgp.py:7493`, `:6472` |
| Length | – | `video_length` (frames); also `duration_seconds` | signature `:7256`ff |
| Frame grid | – | per family: `frames_minimum`, `frames_steps` (H3 also `frames_maximum`, alignment 17n+5) | handlers (5.5.4–5.5.5) |
| FPS | – | `force_fps` (`"auto"`, `"control"`, `"source"` or an integer); else `model_def.fps`, default 16 | `get_model_fps` / `get_computed_fps`, `HP:app/wgp.py:3013-3034` |
| Start / end images | `image_refs` (references) | `image_prompt_type` letters with `image_start`, `image_end` (S/E), `video_source` (V) | `HP:app/wgp.py:1077`, `:1205-1240`, `:6427-6429` |
| Long clips | – | `sliding_window_size`, `sliding_window_overlap`, `sliding_window_discard_last_frames` | signature; H3 defaults below |
| Audio in | – | `audio_guide…audio_guide6`, `audio_source`, `audio_prompt_type`; H3: `minimax_h3_references` | signature |
| Output folder | `image_save_path` | `save_path` (`audio_save_path` for audio-only) | `HP:app/wgp.py:3470-3472`, `:9343-9353` |
| Output file | `<name>.jpg`, renamed by `save_image` to the codec's extension (PNG under the Hub) | `<name>.<video_container>` | `HP:app/wgp.py:9332-9342`, `:9406-9413`; `audio_video.py:694-695` |
| Codec | `image_output_codec` (engine default `jpeg_95`; the Hub forces `png`) | `video_output_codec` default `libx264_8`; `video_container` default `mp4`; `audio_output_codec` default `aac_128` | `HP:app/wgp.py:3474-3480` |
| With audio | – | written to `<name>_tmp.<container>`, then muxed with the audio tracks into the final file by `combine_and_concatenate_video_with_audio_tracks`; the temp file is removed | `HP:app/wgp.py:9404-9459` |
| Without audio | – | `save_video(...)` straight to the final path | `HP:app/wgp.py:9463` |
| Reported files | `file_list` | `file_list`, plus `audio_file_list` for audio outputs; both come back in `generated_files` | `HP:app/shared/api.py:706-710`; `HP:app/wgp.py:9766-9769` |

`seed_config` sets `save_path`, `image_save_path` and `audio_save_path` all to the outbox (`hub/worker/wgpconfig.py:76`). So a video task's file lands in the worker's outbox too.

`FORCED_CONFIG` sets `video_container` to `"mp4"` (`wgpconfig.py:20`), so a clip is an MP4 whatever the engine config holds. It does not set `video_output_codec`: that is the engine config value, or the engine's default (`libx264_8`). `enginecat.land` reads what the file is, not the codec (5.2.8).

`metadata_type: "none"` suppresses metadata for every output kind: the branch writes only for `json` or `metadata` (`HP:app/wgp.py:9525-9534`).

The engine's own API doc shows a video task: `model_type`, `prompt`, `resolution`, `num_inference_steps`, `video_length`, `duration_seconds`, `force_fps` (`HP:app/docs/API.md:20-31`). Its image examples add `image_mode: 1` (`HP:app/docs/API.md:125-160`).

### 5.5.2 What the Hub's image path assumed, and what it does now

Each row names a place that assumed a picture, and what the Hub did with it. "Built" means in the tree described by part 2, 2.10.

| Assumption | Where | Now |
|---|---|---|
| Lane kind is only `"image"` | `hub/core/api.py:19`; `hub/core/engine.py:37` | Unchanged on purpose: a clip is a job on the image lane, so a clip and a picture wait for each other and each switch loads a model. |
| Catalog lists only `image_outputs` models | `hub/worker/catalog.py` | Built: native clip models are listed with `kind "video"` and their facts (5.3.2). |
| Weight facts and the registry match only image models | `hub/worker/wan2gp.py:160-161`; `hub/core/autoreg.py:128-140` | Unchanged: `weights` is built from the `kind == "image"` ids only. |
| Every task is `image_mode: 1`, `batch_size: 1`, `multi_prompts_gen_type: "FG"` | `hub/modules/generate_image/build.py:262-268` | Built: a clip task sets `image_mode: 0` and its own keys (`clip_job`, `build.py:199-204`; part 2, 2.10.5). |
| One task = one image; N tasks = N seeds | `build.py:281`; `hub/worker/wan2gp.py:184-185` | A clip is one task, count 1. |
| `FORCED_CONFIG` sets only the image codec (PNG) | `hub/worker/wgpconfig.py:18-20` | Built: it also sets `video_container` `"mp4"`; `FORCED_VIDEO` is laid over a clip task (5.2.3). |
| `land` treats every output as a picture | `hub/core/enginecat.py:106-159` | Built: an `.mp4` is stripped of its tags by `hub/core/clip.py` and lands in the clips root; any other non-picture file still fails the job (5.2.8). |
| `sweep` after every `task_done` deletes anything else in the outbox, such as a separate audio file not reported as output | `hub/core/engine.py:178`; `enginecat.py:97-103` | Unchanged. |
| Media items published as `kind: "image"` with a thumbnail URL | `hub/core/dispatch.py:173-186` | Built: the item's `kind` is `"image"` or `"clip"`; a clip has no thumbnail URL and carries `seconds` (part 1, 3.4). |
| Served and uploaded types are only PNG, JPEG and WebP | `hub/core/files.py:24-26`; `hub/core/fileroutes.py:27`; `hub/core/drive.py:19` | Built for serving: `/files` serves an MP4 from the clips root with Range. Uploads and the Drive stay pictures only. |
| Thumbnails are produced with Pillow | `hub/core/thumbs.py` (via `files.thumb_url`) | A clip has none; the browser draws its first frame. |
| Progress pct assumes one sampling pass per task | `hub/core/enginecat.py:72-79` | Unchanged; a clip's decode, audio and mux show no phase. |
| Job titles say "image"/"images" | `hub/core/jobs.py` `record` | The job line says "Done · clip in …" for a clip (part 2, 2.10.5). |
| VRAM learning is keyed by model only, not by resolution × length | `hub/core/vram.py:54-61` | Unchanged. |

### 5.5.3 MiniMax H3 in HocusPocus: files and their roles

The integration is in `HP:app/models/minimax_h3/` ("MiniMax H3 audio-video model integration for Maestro", `__init__.py`). Roles below are taken from each file's header or docstring.

| File | Role (from its header) |
|---|---|
| `minimax_h3_main.py` | "Native MiniMax H3 Base (T2VA / FL2VA / Ref2VA) runtime for Maestro." Sampling follows the official Diffusers implementation pinned in `UPSTREAM.md`. Model construction lets MMGP stream Comfy-Org's compact weights "on machines that cannot hold the full 42.5 GB stack in VRAM". |
| `minimax_h3_handler.py` | "Maestro family handler for MiniMax H3 Base FL2VA and Ref2VA." Model types `minimax_h3`, `minimax_h3_legacy`, `minimax_h3_full`, `minimax_h3_ref2va`, `minimax_h3_ref2va_full` (`:1616-1623`). Family `minimax_h3`, label "MiniMax H3" (`:1630-1635`). Pinned repos: Comfy-Org, MiniMaxAI, DeepBeepMeep, Kijai, MATLOWAI (header constants). |
| `turbo.py` + `turbo_presets.json` | "Compatibility helpers for MiniMax H3 low-step Turbo adapters". Turbo steps "are model evaluations, not sigma-grid points"; `MINIMAX_H3_TURBO_MIN_STEPS = 4`. The JSON lists four presets: `v1-ckpt500` (legacy, 6 steps, 0.5), `v4-step600-ema` (validated, 6 steps, 1.0), `alibaba-pai-fl2va-pdd-8step` and `alibaba-pai-ref2va-pdd-8step` (official, 8 steps, runtime `pdd`). `default_preset_id` is `alibaba-pai-fl2va-pdd-8step`. |
| `ref2va.py` | "Official MiniMax H3 Ref2VA media preparation and packed layout", a local-file port of Diffusers' Ref2VA blocks. |
| `reference_manifest.py` | "Dependency-light validation for MiniMax H3 Omni reference manifests" (standard library only). Limits: 9 images, 3 videos, 3 audios, 12 total (`:15-18`). Accepted extensions per kind, image intents `identity/scene/style/composition`, audio intents `voice/drive/style`. `validate_reference_manifest` requires at least one image or video (`:33-110`). |
| `reference_media.py` | "Prepare Ref2VA media to the official per-reference duration envelope": 2–15 s per reference, 15 s total. |
| `duration.py` | "Opt-in extended H3 output duration". The VAE grid is `17*n+5` at 24 fps. `H3_EXPERIMENTAL_MAX_FRAMES = 719` (29.958 s), "outside the published 15s envelope". Enabled by the task flag `minimax_h3_extended_duration`. |
| `video_vae.py` | Apache-2.0 header, "Copyright 2026 The MiniMax and HuggingFace Teams". |
| `audio_vae.py` | Apache-2.0 header. "MiniMax-H3 audio autoencoder. Waveform in / waveform out — there is no mel front-end and no separate vocoder". |
| `semantic_bridge.py` (+ `SEMANTIC_BRIDGE.md`) | "Optional conditioning adapter; independent implementation of published math". Pinned to `speach1sdef178/MiniMax-H3-Semantic-Bridge` with SHA-256. Default off; FL2VA only. |
| `prompt_enhancer.py` | "Prompt guidance and enhancer system prompts for MiniMax H3". Defines the three-part prompt `integrated_multimodal_description / overall_soundscape / non_diegetic_music`, `[Shot N] At MM:SS.mmm` cuts, and `<Picture N>` anchors. |
| `spoken_language.py` | "Models-safe H3 language tags. No services, runtime, or torch imports." |
| `UPSTREAM.md` | Provenance and pins (see below). |
| `H3_FUSED_NOTICE.md` | Notice for the optional fused 4-step checkpoint (see below). |
| `SLA_LICENSE.txt` | MIT licence for the SLA attention code (see below). |
| Others | `checkpoint.py` (checkpoint adapters, Apache-2.0); `conditioner.py` (Qwen3-VL layer-50 conditioning); `packing.py` (packed sequence, Apache-2.0); `scheduler.py` (rectified-flow Euler / RES multistep, Apache-2.0); `transformer.py` ("MMGP-native MiniMax H3 transformer for the compact consumer checkpoints"); `pdd.py` (Parallel Decoding Distillation for Alibaba PAI Acc-LoRAs); `fused_turbo.py` (4–8 evaluations, `res_multistep`); `lora_affine.py` (Full↔Pruned AdaLN LoRA conversion, "WanGP Community License 2.0"); `first_block_cache.py`; `convrot_layout.py`; `sla_attention.py`, `sla_block_map.py`, `sla_kernel.py` (MIT, PlagueKind); `sol_attention.py` (Apache-2.0). |

**Licence and provenance terms, verbatim.**

- `SLA_LICENSE.txt` is the MIT License, "Copyright (c) 2026 PlagueKind". It includes: "Permission is hereby granted, free of charge, to any person obtaining a copy of this software … to deal in the Software without restriction … subject to the following conditions: The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software." It also includes the standard "AS IS" warranty disclaimer.
- `H3_FUSED_NOTICE.md`: "The checkpoint contains multiple fused components and is not an official MiniMax release. Review and comply with the model repository's current license and NOTICE before use. Model files are downloaded on demand and are not redistributed in the Maestro source tree." It pins revision `3b51096a…` with transformer SHA-256 `4262e4e9…`, and the Kijai INT8 ConvRot video VAE at `a3e7d8da…` with SHA-256 `9bb2d96f…`.
- `UPSTREAM.md`:
  - "The video VAE, audio VAE, scheduler, FL2VA packing, and Ref2VA reference preparation/packing in this directory are derived from the Hugging Face Diffusers MiniMax H3 implementation at commit `abc5e9bf…`. Those files retain their upstream Apache-2.0 copyright and license headers."
  - On weights: "Those model weights are downloaded at runtime and are not distributed in the Maestro repository. They remain governed by their respective model terms and any authorization or waiver required for […] location."
  - Its last section, "Hocuspocus adoption", says the runtime was adapted from `Blizaine/Maestro` commit `a5dddd4f…`, and that "Hocuspocus keeps its own Director compiler, request architecture, legacy sidecar, compact default checkpoints and consumer-memory policies".
- `SEMANTIC_BRIDGE.md`: "The weights are distributed under the MiniMax H3 Community License Agreement".
- The fused defaults declare `"license_name": "MiniMax Model License plus upstream component licenses"` (`HP:app/defaults/minimax_h3_fused_turbo.json`).
- `h3_advanced/VENDOR.md`: "WanGP adaptations use the Community License 2.0 … Model weights are downloaded separately and retain their own licenses, including H3/Viggle territorial terms."

**Pinned weight sources** (`UPSTREAM.md`; handler constants):

- `MiniMaxAI/MiniMax-H3` @ `5d9b308a…` for the processor and text-encoder configuration;
- `Comfy-Org/MiniMax-H3` @ `0543966f…` for the scaled-FP8 FL2VA/Ref2VA transformers, the NVFP4-AWQ conditioner and the compact VAEs;
- `DeepBeepMeep/MiniMax-H3` @ `fec7846a…` for the full 33B checkpoints and the optional conditioners.

**Two ways to run H3, and a contradiction.**

- The `minimax_h3_legacy` model is a "legacy sidecar". Its handler refuses to load it in-process: `raise RuntimeError("H3 Legacy Quality must run through Maestro's isolated ComfyUI service.")` (`minimax_h3_handler.py:2186-2191`).
- The other H3 types load `MiniMaxH3Model` in-process (`:2192`ff).
- The README's architecture paragraph describes H3 as "an isolated MiniMax H3 ComfyUI runtime" (`HP:README.md:364`). The changelog says Maestro 1.5.5 "added native local H3 Base FL2VA generation" (`HP:CHANGELOG.md:222`). The handler shows both routes exist.

### 5.5.4 H3 defaults (`HP:app/defaults/minimax_h3*.json`, `h3_advanced_*.json`)

| model_type (file) | Name | architecture | Inputs | Steps | `video_length` | Resolution | Window |
|---|---|---|---|---|---|---|---|
| `minimax_h3` | H3 First / Last — Pruned | `minimax_h3` | text; first, last or both frames; not reference audio | 20 | 124 | 864x480 | size 345, overlap 1 |
| `minimax_h3_full` | H3 First / Last — Full (33B) | `minimax_h3_full` | as above | 20 | 124 | 864x480 | 345 / 1 |
| `minimax_h3_fused_turbo` | H3 Fused 4-Step — Frames (Experimental) | `minimax_h3` | text, start/end/timed frames, audio-driven, control video | 4 (range 4–8) | 243 | 1152x640 | 243 / 18 |
| `minimax_h3_legacy` | H3 Legacy Quality — ConvRot | `minimax_h3_legacy` | text or first/last frame (ComfyUI sidecar only) | 20 (fixed) | 124 | 960x544 | – |
| `minimax_h3_ref2va` | H3 Omni — Pruned | `minimax_h3_ref2va` | ordered image/video/audio references (`minimax_h3_references`) | 20 | 124 | 864x480 | – |
| `minimax_h3_ref2va_full` | H3 Omni — Full | `minimax_h3_ref2va_full` | as above | 20 | 124 | 864x480 | – |
| `minimax_h3_ref2va_fused_turbo` | H3 Fused 4-Step — References (Experimental) | `minimax_h3_ref2va` | references | 4 (4–8) | 243 | 1152x640 | 243 / 18 |
| `h3_advanced_fl2va` | H3 Advanced FL2VA 33B | `h3_advanced_fl2va` | text, first, last or both | handler | handler | handler | – |
| `h3_advanced_fl2va_pruned` | H3 Advanced FL2VA Pruned 20B | `h3_advanced_fl2va_pruned` | as above | handler | handler | handler | – |
| `h3_advanced_ref2va` | H3 Advanced Ref2VA 33B | `h3_advanced_ref2va` | text + reference images, video and/or audio | handler | handler | handler | – |
| `h3_advanced_ref2va_pruned` | H3 Advanced Ref2VA Pruned 20B | `h3_advanced_ref2va_pruned` | as above | handler | handler | handler | – |
| `h3_advanced_vdn` | H3 Advanced VDN 8-Step 33B | `h3_advanced_fl2va` | FL2VA + VDN attention, auto-loaded 8-step LoRA | 8 (euler, flow_shift 12) | handler | handler | – |
| `h3_advanced_vdn_pruned` | H3 Advanced FL2VA Pruned VDN 8-Step 20B | `h3_advanced_fl2va_pruned` | as above | 8 | handler | handler | – |

Every `minimax_h3*` default sets `guidance_scale: 1.0` and `image_prompt_type: ""`. The Ref2VA defaults set `minimax_h3_references: []` and `minimax_h3_reference_detail: "match"`. The `h3_advanced_*` files carry only `model` (with a `wangp_1272` marker), so their settings come from `HP:app/models/h3_advanced/` (imported from WanGP commit `362c3467…`, `h3_advanced/VENDOR.md`). That handler sets `"image_outputs": False` (`h3_advanced/minimax_h3_handler.py:236`).

**H3 capabilities** from `query_model_def` (`minimax_h3_handler.py:1662`ff):

- `fps: 24`;
- `frames_minimum: 124`, `frames_steps: 17`, `frames_maximum: 345` (`:63-64`, `:75`, `:1740-1746`), with the comment "H3's video VAE accepts only 17*n+5 frames. 124 is the first valid count at or above five seconds; 345 is the last at or below fifteen seconds";
- `vae_block_size: 32`;
- `sliding_window: True`;
- `t2v_class: True`, `i2v_class` true for FL2VA only (`:1788-1789`);
- `image_prompt_types_allowed: "TSEV"` for FL2VA, `""` for Omni (`:1795`);
- `returns_audio: True` (`:1801`);
- `supports_reference_audio` for Omni only (`:1807`);
- `no_negative_prompt: True` (`:1808`);
- `guidance_max_phases: 0`, which means `catalog.guidance_key` would give none.

There is no `image_outputs` key, so `catalog.build` excludes H3.

**Resolutions.** `_RESOLUTIONS` lists 34 sizes, from `608x352 (16:9 minimum)` through the `*x480 low VRAM`, `*x544`, `*x640`, 720p (`1280x704`…) and "high" (`1344x768`…) tiers, up to `2528x1088 (21:9 experimental)` (`:821-856`).

**LoRAs.** The LoRA folder is `<lora_root>/minimax_h3` (`:2094-2095`).

**Defaults in `update_default_settings`** (`:2224`ff): 20 steps (4 for fused), `video_length` 124 (fused: recommended frames), resolution `864x480` (fused: `1152x640`), `guidance_scale` 1.0, empty `image_prompt_type` and `video_prompt_type`.

### 5.5.5 Upstream Wan2GP H3 ids, for comparison

Upstream ships `minimax_h3_fl2va`, `_fl2va_pruned`, `_fl2va_pdd`, `_fl2va_pruned_pdd`, `_ref2va`, `_ref2va_pruned`, `_ref2va_pdd`, `_ref2va_pruned_pdd`, `_tts_ref2va_pruned`, `_control`, `_control_pruned`, `_vdn` and `_vdn_pruned` (`UP:defaults/minimax_h3_*.json`). These ids differ from HocusPocus's `minimax_h3`, `minimax_h3_ref2va`, … Upstream also has `models/minimax_h3/`.

### 5.5.6 Other video families present in the HocusPocus engine

| Family | Example ids (defaults) | Inputs (`image_prompt_types_allowed`) | Default res / frames / steps | FPS | Audio out | Source |
|---|---|---|---|---|---|---|
| Hunyuan Video 1.5 (8B) | `hunyuan_1_5_t2v`, `hunyuan_1_5_i2v`, `hunyuan_1_5_480_t2v`, `hunyuan_1_5_480_i2v`, `_lightx2v`, `_step_distilled`, `hunyuan_1_5_upsampler(_1080)` | i2v: `SVL`; upsampler: `TVL`; t2v: not traced | 1280x720 or 832x480 / 97 / 30, guidance 6.0 | 24 | – | `HP:app/defaults/hunyuan_1_5_*.json`; `models/hyvideo/hunyuan_handler.py:56-59`, `:73-75` (frames min 5, step 4), `:117-121` |
| Wan 2.2 i2v (14B) | `i2v_2_2`, `i2v_2_2_Enhanced_Lightning_v2`, `_svi2pro`, `_multitalk` | i2v: `SEVL` | from handler / primary settings; guidance 3.5, flow_shift 5 | 16 (5B: 24) | – | `HP:app/defaults/i2v_2_2*.json`; `models/wan/wan_handler.py:275-288`, `:750-775` |
| Wan 2.2 ti2v (5B) | `ti2v_2_2`, `ti2v_2_2_fastwan` | `TSVL` | 1280x720 / 121 / 50 | 24 | – | `HP:app/defaults/ti2v_2_2.json`; `wan_handler.py:762` |
| LTX-2 / 2.3 | `ltx2_19B`, `ltx2_distilled`, `ltx2_22B`, `ltx2_22B_distilled`, `_fp8`, `_nvfp4`, `_gguf_*`, `_1_1`, … | `TSEV` | 1280x720 (22B) / 241 / 30–40 (8 distilled), guidance 3.0 | 25 (`ltx2_22B`) else 24 | yes (`returns_audio`) | `HP:app/defaults/ltx2_*.json`; `models/ltx2/ltx2_handler.py:160-200` (frames min 17, step 8) |
| MiniMax H3 | see 5.5.4 | FL2VA `TSEV`, Omni `""` + references | 864x480 / 124 / 20 | 24 | yes, stereo | 5.5.3–5.5.4 |

Letter meanings traced in `wgp.py`: `S` = `image_start` (`:6434`), `E` = `image_end` (`:6436`), `V` = `video_source` (`:1095`), `L` = continue from the last video (`:1247`, `:7983`). `T` was not traced; the H3 help text describes FL2VA as "text alone, a first frame, a last frame, or both" (`minimax_h3_handler.py` `workflow_help`).

### 5.5.7 What a video task would have to carry

These are facts about the engine's inputs, not a design.

- **H3 FL2VA:**
  - `model_type` (for example `minimax_h3`);
  - `prompt` in the three-part H3 structure the enhancer documents (`prompt_enhancer.py` `FL2VA_PROMPT_INFOS`);
  - `resolution` from `_RESOLUTIONS`;
  - `video_length` on the 17n+5 grid, 124–345 (or up to 719 with `minimax_h3_extended_duration`);
  - `num_inference_steps`, `guidance_scale: 1.0`;
  - `image_prompt_type` letters with `image_start` / `image_end`;
  - `image_mode: 0`, which a picture task does not send; `clip_job` sends it (`build.py:200`).
- **H3 Omni:**
  - `minimax_h3_references`: a list of `{type: image|video|audio, path, role?, image_intent?, …}` validated by `reference_manifest.validate_reference_manifest`;
  - `minimax_h3_reference_detail` (`"match"` by default);
  - wgp passes both to the H3 model (`HP:app/wgp.py:7426-7427`, `:9081-9082`).
- **Under the legacy flavour,** `translate` lays the model's factory settings underneath a clip task as it does for a picture, and these come for H3 from `update_default_settings`. It also strips `activated_loras` to base names (`Fork.translate`, `hub/worker/adapters/fork.py:45-54`).
- **The output** would be one `.mp4`, or another container per `video_container`, in the outbox. Where audio was generated it is muxed into that file (5.5.1).

---

## 5.6 The engine seam: adapters, and the way to an engine of the Hub's own

### 5.6.1 What is built (Stage 9 steps 1 and 2)

`hub/worker/engineapi.py` (298 lines, stdlib only) is the Hub's side of the seam. It holds:

- the Hub-side types: `EngineInfo`, `ModelFacts` (with `Steps`, `Guidance`, `Loras`, `References`, `Video`, `Frames`, `Tier`, `Encoders`), the requests `PictureRequest` and `ClipRequest`, and the events `Loading`, `Loaded`, `Progress`, `Output`, `Failure`, `Done` (`:25-172`);
- `KeyFamilies` (`:175-202`): how one engine names a key per model family (the reference-manifest field and its limits, the reference detail's choices and default, the suffixes of the reference list, the detail, the one-pass switch, the sidecar flag and the text encoder with its default and variants). The shared catalog helpers apply these rules and name no family themselves;
- the `Adapter` protocol (`:205-224`): `name`, `flavour`, `families`, `factory_underneath`, `lora_recursive`, `READS`, `probe(root, session)`, `facts()`, `translate(task, factory)`, `factory_settings(w, model_type)`, `lora_root(w)`, `lora_search(w, model_type)`;
- `select(root, adapters, session)` (`:240-245`), which returns the first adapter whose `probe` accepts the root and raises `NoAdapter` with one line when none does; `wire` and `parse` (`:248-297`), a strict round trip between these dataclasses and plain JSON dicts that refuses an unknown or missing field and a wrong type.

`hub/worker/adapters/` holds the two adapters, in probe order `Upstream`, then `Fork` (`__init__.py:18`; `select`, `by_flavour`): `upstream.py` (current Wan2GP, flavour `upstream`) and `fork.py` (the HocusPocus line, flavour `legacy`), each with a `*.facts.json` next to it (`families` and `models`). These two files and the facts files are the only place in `hub/` where an engine key family is named. What moved there from `wan2gp.py` and `catalog.py`: `FORCED_TASK`, `FORCED_VIDEO`, `translate`, `factory_settings`, `lora_root`, `lora_search` and the flavour probe (`upstream.py:36-44`, `:65-80`; `fork.py:41-44`, `:87-100`). `Engine.open` calls `adapters.select(root, session)` (`wan2gp.py:144`); `catalog.build` and every helper in `catalogvideo.py` take the adapter's `families` as `keys` (5.3.2). The model-name guard (`tests/engine/test_video_engine.py:138`, `test_core_and_worker_name_no_model`) still covers `hub/core` and all of `hub/worker` except the facts files. `upstream.facts.json` copies the fork's `families` for now: a real upstream capture is expected to fail the contract test by name, which is the signal to split them (Stage 9 step 5).

Each reader of the engine declares what it reads: a `READS` table of `wgp`, `api`, `definition`, `settings`, `generate_video` and `suffixes` names, each tagged `both`, `legacy` or `upstream` (`wan2gp.py:39-50`, `catalog.py:23-37`, `catalogvideo.py:20-33`, `definitions.py:16`, `fork.py:29-39`, `upstream.py:26-34`).

Tests: `tests/engine/test_engineapi.py` (the types round-trip through the wire; `parse` refuses what it does not know; `select` picks each flavour and refuses a stranger; every adapter meets the protocol; the facts files name families and known models only; no family means no match), `test_adapter_golden.py` (the catalog per flavour, the fork's crafted tasks and upstream's tasks made from the Hub's requests on its own H3 definitions are byte-identical to `tests/fixtures/adapters/{catalog,tasks}-{legacy,upstream}.json`; the Hub's requests equal the fork's stored tasks; every stored upstream key is one upstream accepts), `test_engine_contract.py` (over every capture under `tests/fixtures/contract/<flavour>-<version>/engine.json`: each name a module reads is published, each field is held by a shipped model, the fake agrees with the capture on every field read, the one-pass answer is pinned, and an AST walk finds no read a module left out of its `READS`), `tests/engine/test_rules.py` (`test_no_engine_key_family_outside_the_adapters`, `:59`). The one capture there is made from the fake engine itself (`fake-17.17`), so the machinery is tested and no real capture is beside it yet.

### 5.6.1a Stage 9 steps 3 to 5

- **Requests on the wire.** `engineapi.py` adds `Reference` (`path`, `role`: `reference`, `start`, `end`, `source` or `identity`; an identity's `name` and `cutout`), `PictureRequest`, `ClipRequest` (frames, steps, LoRAs, pictures, `encoder`, `detail`, `one_pass`), `JoinRequest`, and `KIND_ROLES` (the roles each kind takes). `enginewire.py` holds `wire`, `parse`, `request_wire` and `request_parse`; the last refuses an unknown kind, field or role and a role its kind does not take. A whole number stays one across the wire (guidance 4 is sent as 4).
- **The adapters build every task.** `Adapter.task(request, entry)` turns a request into the engine task from the model's catalog entry (`Engine.entry`, once per worker); `adapters/tasks.py` holds the Wan2GP shape both lines share, the fork's conventions by default and the upstream line's differences in a `Line` (no per-task crop). A picture whose role the model does not take is refused in one line (`faults.Refused`, shown without a frame), never dropped: an identity on a start-frame model, an end without a start, two starts, a source beside another picture, a source on a model that does not continue, more identities than the cap, a reference on a picture model with no reference choice; so is a cut-out or a name the model does not take, and a detail on a model that announces none.
- **The upstream adapter on upstream's own H3** (R16 §4; `upstream.native` for the architectures its facts file lists): frames 107 to 362 on 17k+5 (`window_default`, the official 15 s), a window of `max(124, frames)` (`window_min`) and, continuing, `frames + 17` never above 481 (`window_max`, `tasks.STEP_MAX`); the text encoder in `config`, its ids from the definition's `system_configs` (default the definition's `text_encoder_variant`, else the server's quantization); identities as `image_refs` with "I" (at most 9, no names, `remove_background_images_ref` 1 only when every box is cut out, mixed boxes refused); `fit_canvas` 2 forced through `forced_config`; the control and Viggle models a `why_not` line; the speech model out (audio only).
- **What a definition does not say** (`Adapter.line_facts`, `catalog.line_facts`): `budget` (the resolution budget an API task must stay within, upstream's default 1920×1088), `was` (the fork's ids, the facts file's `renamed`, R16 §3.1), and a step lock (`lock_steps` and `steps`: Qwen Image 2.1 Turbo at 8). The fork's is empty, so its catalog is unchanged. `Adapter.window(task)` gives the window a task was sent with (the continue probe reports it).
- **Keys upstream accepts.** The upstream `translate` refuses any key outside `shared.utils.setting_names.accepted_setting_names()` when the engine has it (R16 §1). The test root carries the fixture's list there (`make_engine_root(h3=True)`).
- **The capture and the fixture.** The `--dump-engine` of upstream 18.05 is `tests/fixtures/contract/upstream-18.05/engine.json` (with the venv's `env.lock`). `tests/fixtures/upstream-18.05/h3.json` is written from it (`tests/engine/test_upstream_capture.py` checks the two agree): the H3 line, the speech model and Qwen Image 2.1, each with its definition, own settings, factory settings and LoRA folder, and the engine's families and accepted settings; the fake's 18.05 root (`make_engine_root(h3=True)`) is built from it. `tests/engine/test_upstream_rules.py` holds the rules against it, and `tasks-upstream.json` is the Hub's requests through the upstream adapter on those definitions. `tests/engine/capture_engine.py` answers the catalog from the capture itself, so the catalog the worker builds is checked against the one the release built on the server.
- **3D models are not pictures.** A definition with `mesh_outputs` (18.05 has 12) is left out of the catalog, though it also says `image_outputs` (its preview).

### 5.6.2 What is not built

- **The Stage 9 debts:** `autoreg` and `catalog_key` through the adapter (waits for Stage 10); the catalog reply still carries engine fields (`defaults` keys, `guidance_key`, `ref_choices`, `video_task`, `video.one_pass`, `references.key`) and `ModelFacts` is unused; the Hub-word events are not on the wire.
- **Steps 6 and 7.** Hub-owned media facts and the second-engine drill (a new engine touches only `hub/worker/adapters/` and `tests/fixtures/contract/`).
- **The continue probe on the real engine.** Not run (5.2.6). `--dump-engine` has run on upstream 18.05; the HocusPocus engine was never captured.

### 5.6.3 Stage 10: the Hub's own engine

The requirement (5.1.4) is that the engine the Hub drives does not depend on the HocusPocus/Maestro install. The adapter seam makes an engine line replaceable by one adapter file and one capture; it does not by itself remove the dependency, because both adapters still drive a Wan2GP root that HocusPocus carries. Stage 10, an engine of the Hub's own, is the step after Stage 9 steps 3 to 5. What was built is below. Built (the switch-only change):

- **Layout.** `<prefix>/engine/app` (an upstream checkout at the pinned `af2ed29`, made by the engine install's step 1 block), `env` (its uv venv, Python 3.11.14, torch 2.10 cu130), `env.lock`, `python` (the venv's base Python copied out of uv's folder), `.installed` (the record), `.settings-before.json`. `app/wgp_config.json` is the app's own; `app/outputs` takes the page run's files. No weights live here: the model and LoRA folders are the ones set on the Settings screen.
- **`install/install-engine.sh`** (switch only). `--dry-run` lists the plan: the engine switch, the Settings' model and LoRA folders (unchanged), the config's source. It asks before the first switch; a later run is a repair with no question. Checks: the Hub installed and new enough, the app an upstream checkout at the pin with no local change, the env's Python starts, `engine/` holds only its own entries; gcc and g++ found (`brew`'s folder searched too); ffmpeg on the service's PATH or in `app/ffmpeg_bins`; the saved engine arguments checked against upstream's own parser (`install/engineargs.py`: what it refuses is left out and named). Then, each step in the record and undone on any failure: the Hub stopped; `app/outputs`; the base Python copied and the venv pointed at it (`helpers.py base-python`, checked by running it; left alone under `/usr`); `hub engine set` (the app, its Python, the compilers as `engine.cc` and `engine.cxx`, the kept arguments; the model and LoRA folders untouched; on the first switch the settings it replaced go to `.settings-before.json`, on a repair to the run's stage, for its rollback only; either is recorded before the change); an `app/wgp_config.json` it did not make kept as `.app-config-before.json` (kind `restore`); the app's config (`helpers.py config`, from the old engine's on the first switch, else the app's own: no secret, no path inside its source, the app's own `ckpts` as its only checkpoint folder (the page run's download target; upstream run by hand never searches or prunes the folders, which reach the worker from the Hub under its hold), upstream's default LoRA root (the LoRA folders reach jobs from the Hub, `lora_extra`), every save path `app/outputs`, the prompt enhancer off); the smoke (the compiler runs in the worker's environment, and `--dump-catalog` opens the engine offline on the Settings' model folders); the Hub started again.
- **Undo.** `uninstall.sh --engine` undoes what the record lists: the engine settings go back to `.settings-before.json` (`hub engine restore`; the model folders as they are now), the app's config and `app/outputs` (when empty) go; an app config it did not make comes back; the base Python copy stays recorded until `--purge`, which also removes the code, env and base Python and refuses, changing nothing, while a Settings folder lies inside them. A failed run is undone step by step; what cannot be put back is said and kept in the record.
- **The weights are never erased** (`hub/worker/keep.py`): while the engine imports, every file under the model folders, the root's `ckpts` and the checkpoint folders its config names is held (a download's working files and hidden folders left out), so upstream's import-time deletion of "deprecated" files and its ltx-2 rename leave them (each told on stderr). `Upstream.prepare` refuses a `wgp.py` that removes files at import past the hold (`keep.removals`: a remover reached through a module other than `os`, `shutil` or `pathlib`), so a pin whose deletion loop leaves `os.remove` is refused at its first start.
- **The page run** (`hub/worker/pagerun.py <app> [wgp args]`, by the engine's Python, the Hub stopped): the same hold for the whole run over the app config's checkpoint roots, then `wgp.py` as the page, fetching what the weights lack into `app/ckpts` (on hold: where downloads go is not decided).
- **Upstream's pre-check** (`adapters/upstream_weights.py`): `lacking` lists what upstream would fetch before a model loads, by its own presence calls (`model_dropdowns` core and secondary entries, the handler's bundles through `download_def_missing_files`, queried with the definition as the load resolves it, `runtime_def`) and the facts file's `companions` (Whisper medium for the speech model); `opened(w)` puts a one-line refusal in place of every fetch ("Not in the engine's weights: <file>").
- **The registry and the cache key through the adapter** (review item 14): `Adapter.pointers` (`adapters/pointers.py`) holds a Hub pointer's form, its folder, the reading of a definition file and the root entries the catalog key watches; `hub/core/autoreg.py` and `enginecat.catalog_key` ask the root's adapter, called as a library (no worker runs for either).

---

## Gaps / unverified

- **H3 weights on the server.** The codec, tags, size and time of a clip made through the Hub are not written down. This guide did not inspect the model folders or the `ckpts` of the engine's folder. With `HF_HUB_OFFLINE=1` and the network guard, any missing H3 asset would fail rather than download. The H3 assets include the transformer, VAEs, the Qwen3-VL conditioner and processor files (`minimax_h3_handler.py:2102`ff `query_model_files`).
- **The server's engine copy.** It is not verified that the HocusPocus source copy read for this guide is identical to the installed engine on the server.
- **Pointer (`auto_…`) models.** Whether they generate on the server is not verified.
- **Unused bus messages.** No screen sends `gpu.refresh`, `gpu.plan` or `engine.start`. `gpu.release` is sent by "Clear the GPU cache" in the code read here (`Taskbar.tsx:37`, `Bar.tsx:41`).
- **Transitive imports.** Not traced: whether HocusPocus `services.*` modules imported by `wgp.py` pull in further HocusPocus code, such as the task database or the FastAPI app.
- **Separate audio files from H3.** Not traced: whether an H3 run with generated audio ever reports a separate audio file in `generated_files` in addition to the muxed video. If it does, the Hub's `land` would fail the job on it ("The engine wrote a file the hub does not take", `enginecat.py:143-145`).
- **The H3 Turbo default.** `UPSTREAM.md` states "Maestro's current default is … `minimax_h3_turbo_v4_step600_ema`", but `turbo_presets.json` has `default_preset_id: "alibaba-pai-fl2va-pdd-8step"`. The two sources disagree; which is used at runtime was not traced.
- **The `T` letter** in `image_prompt_types_allowed`, and the defaults for Hunyuan 1.5 t2v inputs, were not traced in `wgp.py`.
- **The README and the code disagree about H3.** The README describes H3 as an isolated ComfyUI runtime (`HP:README.md:364`); the handler also has an in-process path for every type except `minimax_h3_legacy`. Which path HocusPocus's own UI uses by default was not traced.
- **Wan i2v_2_2 resolution and length** come from the handler or primary settings, not its defaults file. The values were not extracted.
