# R9. Independence from the fork: the surface the Hub uses, a seam, and a plan

Notation: plain paths are in the Hub repository. `HP:` is the HocusPocus/Maestro checkout (engine under `HP:app/`,
WanGP 10.9875). `UP:` is the upstream Wan2GP reference copy (WanGP 17.17). "Fork-only" below means found in `HP:`
and not in `UP:` by a search of `wgp.py`, `shared/`, `models/` and `defaults/`; it is static evidence, not a run.

## 1. The surface the Hub uses today

### 1.1 `shared.api` calls and engine objects (all in the worker)

- `importlib.import_module("shared.api")`, then `api.init(root=, config_path=, output_dir=, cli_args=[..., "--settings", dir], console_output=False)` (`hub/worker/wan2gp.py:142-144`; `HP:app/shared/api.py:952-970`).
- Flavour probe: `hasattr(session, "list_model_defs")` (`wan2gp.py:147`; present only at `UP:shared/api.py:601`).
- `session.submit_task(params)` (`wan2gp.py:196`; `HP:app/shared/api.py:264`).
- `job.events.iter(timeout=0.5)`; `event.kind` in `error` / `progress`; `ProgressUpdate.phase`, `.current_step`, `.total_steps`, `.progress`, `.status` (`wan2gp.py:199-209`; `HP:app/shared/api.py:36-44`, `:583-616`).
- `job.result()`, `job.cancel_requested`, `job.cancel()`, and the private `job._thread` joined for 30 s (`wan2gp.py:175`, `:210-214`).
- `result.generated_files`, `result.errors`; each error's `.stage`, `.message`, and any traceback attribute (`wan2gp.py:221-226`; `hub/worker/faults.py:12-36`).
- Engine module globals, reached as `sys.modules["wgp"]` (`wan2gp.py:145`): `server_config` (updated, `:148`), `WanGP_version`, `settings_version` (`:149`), private `wan_model`, `transformer_type` (`:153`), private `_get_dropdown_deps()` (`:161`, `hub/worker/catalog.py:261`), `get_lora_dir` replaced by the Hub's own (`wan2gp.py:146`).
- Catalog reads (`hub/worker/catalog.py`): `models_def`, `get_model_def`, `get_model_family(for_ui=True)`, `families_infos` (`:263-279`); `model_dropdowns.get_model_download_status`, `deps.get_local_model_filename`, `get_model_recursive_prop` (`:250-256`); `get_factory_settings` (upstream only) or `primary_settings` + `get_model_handler(t).update_default_settings` (fork) (`:192-208`); `get_lora_root` (upstream only), `args.loras`, `args.lora_config`, `DEFAULT_LORA_ROOT`, `get_lora_search_dirs` (fork only) (`:211-243`); `server_config["checkpoints_paths"]` (`:291`).
- Weight facts for pointers: `models_def[*]["path"]`, `get_base_model_type` (`hub/worker/definitions.py:43-62`).

### 1.2 Task keys the Hub sends

Image task (`hub/modules/generate_image/build.py:206-218`): `model_type`, `prompt`, `resolution` "WxH", `batch_size` 1, `image_mode` 1, `multi_prompts_gen_type` "FG", `video_prompt_type` (reference letters, `models.py:63-68`), `remove_background_images_ref` 0, `activated_loras`, `loras_multipliers`, `num_inference_steps`, the guidance key the catalog names (`guidance_scale` or `embedded_guidance_scale`), `image_refs`, `seed`.

Clip task (`build.py:154-164`): `model_type`, `image_mode` 0, `prompt`, `resolution`, `video_length`, `sliding_window_size` (= `video_length`), the catalog's `one_pass` dict, `num_inference_steps`, `seed`, `batch_size` 1, `multi_prompts_gen_type` "FG", `image_prompt_type` "", `video_prompt_type` "", the catalog's `video_task` (the text encoder key), the chosen encoder, LoRA keys when active. Pictures (`build.py:24`, `:121-130`): a start frame as `image_prompt_type` "S", `image_fit_mode` "crop", `image_start` path; or identities as the list under the catalog's `references.key`, each `{type: "image", path, image_intent: "identity"}`.

Added by the worker (`wan2gp.py:38-57`): `FORCED_TASK` `prompt_enhancer` "", `negative_prompt` "", `alt_prompt` "", `output_filename` "{date}-{seed}"; for `image_mode` 0 `FORCED_VIDEO` `audio_prompt_type` "", `MMAudio_setting` 0. For the fork flavour the model's factory settings go underneath, "FG" becomes 2, and LoRA names become base names (`:53-57`).

### 1.3 Definition fields the catalog reads

`visible`, `image_outputs`, `name`, `embedded_guidance`, `guidance_max_phases`, `image_ref_choices.choices`, `vae_block_size`, `lock_inference_steps`, `no_lora`, `hub_auto`, `hub_base` (`catalog.py:22-61`, `:265-267`); for clips `audio_only`, `t2v_class`, `settings`, `image_prompt_types_allowed`, `omni_reference`, `omni_reference_limits.image`, any setting ending `_references` that is a list, any setting ending `_multi_window`, any field ending `_sidecar`, `fps`, `frames_minimum`, `frames_steps`, `frames_maximum`, `block_size`, `resolution_presets[*].values` (with `auto`), `resolution_preset_order`, `auto_resolution_budgets`, `<key>_text_encoder_default` with `<key>_text_encoder_variants` (`name`, `URLs`), `text_encoder_folder`, `inference_steps_min/max`, `loras_disabled` (`catalog.py:76-189`, `:289`); factory keys `num_inference_steps`, `guidance_scale`, `embedded_guidance_scale`, `resolution`, `video_length` (`:16`, `:173`); `URLs`, `path` (`definitions.py:17-28`, `:59-61`).

### 1.4 Config keys forced and dropped (`hub/worker/wgpconfig.py`)

Dropped: `services`, `llm_engines`, `enabled_plugins`, `installed_remote_plugins` and every `notification_*` (`:17`, `:73-75`). Forced in the file and again in memory (`:18-20`, `:76`; `wan2gp.py:148`): `image_output_codec` png, `metadata_type` none, `enhancer_enabled` 0, `enhancer_mode` 1, `enabled_plugins` [], `save_queue_if_crash` 0, `embed_source_images` False, `video_container` mp4; `save_path`, `image_save_path`, `audio_save_path` = the outbox (`:76`); `checkpoints_paths` (`:80`); the memory profile under `profile`, `video_profile`, `image_profile` (`:24`, `:77-78`). Minimal config when the root has none (`:64-65`). Queue files removed at start (`wan2gp.py:36`, `:135-138`).

### 1.5 Output-file contract

The engine writes into the outbox only because of the save paths above. The session returns the new entries of its `file_list` and `audio_file_list` (`HP:app/shared/api.py:693-697`). The worker emits one `output` per path (`wan2gp.py:224-225`). The controller lands each (`hub/core/enginecat.py:106-141`): the real path must sit directly in the outbox (`:111-112`); `.mp4` is stripped of tags by `hub/core/clip.py` and linked into `<data>/clips` with a time name, w/h None (`:114-125`); a picture is cleaned and linked into `<data>/outputs` (`:129-141`); anything else fails the job (`:126-128`). The outbox is swept after every `task_done` (`hub/core/engine.py:168`; `enginecat.py:97-103`). A task is ok only with files, no errors, no cancel (`wan2gp.py:227`).

### 1.6 Progress and error events

Wire (`hub/worker/protocol.py:5-18`): `ready {pid, proto, engine}` (`hub/worker/main.py:168`), `fatal` (`:166`), `model loading|loaded` (`wan2gp.py:186`, `:207`, `:223`), `progress {phase, step, steps, pct, text}` (`:208-209`), `output`, `task_done {ok, seconds, model, peak_vram_mb, peak_rss_mb, error?}` (`:228-231`), `reply` (`main.py:105-111`); busy refusal (`main.py:85-86`). Errors reduce to one line with stage `cancelled`, `oom` or the engine's stage (`faults.py:27-37`). The controller turns progress into job percent, ignoring loading phases (`enginecat.py:72-79`), and a bad `task_done` into `EngineFailed` (`engine.py:165-172`). Phase names are the engine's normalised set (`HP:app/shared/api.py:890-911`).

## 2. Upstream, fork-only, per-model

- Session surface: upstream. `init`, `submit_task`, `SessionEvent`, `ProgressUpdate`, `GenerationResult.generated_files/errors`, `GenerationError.stage` exist in both (`UP:shared/api.py:182-262`, `:1594`). Upstream adds `artifacts`, a web-UI bridge and listing calls; the fork's file is an older, smaller copy (1002 vs 1661 lines). `job._thread`, `wan_model`, `transformer_type`, `_get_dropdown_deps` are private in both.
- Engine globals: `get_lora_search_dirs` and `get_local_model_filename` in `wgp.py` are fork-only (`HP:app/wgp.py:2517`, `:3680`); `get_factory_settings` and `get_lora_root` are upstream-only (`UP:wgp.py:3261`, `:2544`).
- Image task keys: all upstream. The fork differs only in reading the prompt mode as an integer and LoRAs by flat name, which `translate` already handles.
- Clip task keys: `image_fit_mode` is fork-only (`HP:app/wgp.py:7368`, `:8059`; upstream fits through the `fit_canvas` config). `MMAudio_setting` is a `wgp.py` key in the fork; upstream has it only in `shared/utils/setting_names.py` and `postprocessing/`. `image_start`, `image_prompt_type`, `video_length`, `sliding_window_size`, `audio_prompt_type` are upstream.
- Config: `services` is fork-only in `wgp.py`; the forced keys exist in both.
- Definition fields, fork-only: `omni_reference`, `omni_reference_limits`, every `*_multi_window`, `*_text_encoder_default/_variants`, `*_sidecar`, `resolution_presets`, `resolution_preset_order`, `auto_resolution_budgets`, `inference_steps_min/max`, `loras_disabled`. Upstream-only: `no_lora`. Common: the rest of 1.3, including `frames_maximum` (though upstream H3 does not set it).
- Per-model (the fork's H3 handler, `HP:app/models/minimax_h3/minimax_h3_handler.py`): `fps` 24, `frames_minimum/steps/maximum` 124/17/345 (`:63-64`, `:1740-1746`); `image_prompt_types_allowed` "TSEV" for First/Last and "" for Omni (`:1795`); the tier tables (`:1832-1835`); `minimax_h3_text_encoder_default/_variants` (`:1842-1843`); `inference_steps_min/max` (`:1914-1917`); `loras_disabled` (`:1939`); `minimax_h3_legacy_sidecar` (`:1963`); `omni_reference`, `omni_reference_limits` (`:2000-2006`). Task keys: `minimax_h3_references` with the `{type, path, image_intent}` manifest (`HP:app/defaults/minimax_h3_ref2va.json`; `reference_manifest.py:15-24`, `:33-110`), `minimax_h3_text_encoder` (`HP:app/wgp.py:7439`), `minimax_h3_multi_window` (`HP:app/wgp.py:7450`, default True; read at handler `:2618-2625`, `:2682-2689`). The Hub names none of these: the module copies whatever the catalog discovered by suffix.

Finding to verify first: no file in the fork sets `minimax_h3_multi_window` as a model setting. `HP:app/defaults/minimax_h3.json` and `HP:app/models/_settings.json` do not hold it, and the handler's `update_default_settings` (`:2224-2260`) does not add it; it exists only as the `generate_video` default (`wgp.py:7450`). The catalog finds a one-pass key only among settings (`catalog.py:160-162`), so on the real fork `one_pass` should come out None and no one-pass flag is sent; if the handler's memory policy then shrinks the window (`:2665-2680`), the engine chains passes. The fake engine sets the key in its defaults (`tests/engine/fake_engine/defaults/minimax_h3.json`), so `tests/engine/test_video_engine.py:187-195` passes against a shape the real fork does not have. A `--dump-catalog` run on the real engine settles it.

## 3. The adapter boundary

Goal: the fork (or upstream, or another engine) is named in one adapter file; core, modules and the wire speak Hub terms.

`hub/worker/engineapi.py` (stdlib, types and one protocol only):
- `EngineInfo`: `engine` (adapter id), `version`, `watch` (paths whose change invalidates the catalog; replaces the layout list in `enginecat.py:38`).
- `ModelFacts`: `id`, `name`, `family`, `status`, `kind` (image | video), `base`, `steps` {default, min, max, locked}, `guidance` {default} or None, `block`, `loras` {dirs, recursive} or None, `references` {roles, min, max} where role is `subject`, `people`, `start`, `start_end` or `identity`, `video` {fps, frames {min, step, max, default}, tiers [{name, sizes}], encoders {ids, names, default, found}, `one_pass` (bool: the adapter can guarantee one pass)} or None, `why_not` (one plain line when the engine has the model but the adapter cannot drive it).
- `Request`: `kind`, `model`, `prompt`, `size` (w, h), `seed`, `steps`, `guidance`, `loras` [(name, strength)], `references` [(path, role)], `frames`, `encoder`, `one_pass` (always True for now).
- `Event`: `Loading(model)`, `Loaded(model)`, `Progress(phase, step, steps, text)`, `Output(path)`, `Done(ok, model, error)`; `Failure(stage, text)` with stages `cancelled`, `oom`, `generation`, `runtime`.
- `Adapter` protocol: `probe(root) -> bool`, `open(root, state, args, model_folders, profile) -> EngineInfo`, `catalog() -> (list[ModelFacts], weight facts)`, `run(request, emit) -> Done`, `cancel()`, `loaded() -> str | None`, `pointer(stem, path, base, defaults) -> (relative path, document)`.
- `select(root) -> Adapter`: the first adapter whose `probe` accepts the root.

Adapters behind it: `hub/worker/adapters/wan2gp_fork.py` (today's "legacy") and `wan2gp_upstream.py`, each holding its own key tables: reference letters and the manifest builder, the text encoder key, the one-pass key, forced task and config keys (today's `FORCED_*`, `DROPPED_CONFIG`), the private globals. `wgpconfig.py`, `catalog.py`, `definitions.py`, `faults.py` become shared helpers the two Wan2GP adapters import. A per-engine facts file (`adapters/wan2gp_fork.facts.json`) carries what the engine does not publish (for example the one-pass key by architecture); it is the only place a model name may appear. The wire bumps to `PROTO = 2`: `run` carries a `Request`, `reply` carries `ModelFacts`. `autoreg` asks the adapter for the pointer document instead of writing Wan2GP JSON itself (`hub/core/autoreg.py` today); `enginecat.catalog_key` uses `EngineInfo.watch`.

Tests that pin the seam:
- The fake engine (`tests/engine/fake_engine`) becomes the contract fixture. Its `fake_engine.json` architectures and `defaults/*.json` are regenerated from a captured real dump per engine version (`tests/fixtures/contract/<engine>-<version>/`), never edited by hand; a test checks that every field an adapter reads (a `READS` tuple per adapter) has the same value in the fake as in the capture. That test would have caught the one-pass drift above.
- One contract suite, parametrised over adapter x fake flavour: catalog to `ModelFacts` invariants (lattice, tiers, roles, encoders), `Request` to the params the engine received (golden files from `last_task.json`, `tests/engine/fake_engine/wgp.py:283-284`), event mapping (progress, OOM, cancel, busy), output contract (one MP4 or picture in the outbox; anything else fails).
- `tests/fakes/fake_worker.py` speaks Hub terms, so every core test exercises the wire without Wan2GP keys.
- Guards: extend `tests/engine/test_video_engine.py:126-130` and `:198-201` from "no model name" to "no Wan2GP key" (`image_mode`, `*_prompt_type`, `sliding_window`, `_multi_window`, `_references`, `activated_loras`, `num_inference_steps`) outside `hub/worker/adapters/`.

## 4. What the Hub owns, and what it never owns

Owns already: the outbox, landing and cleaning (`enginecat.land`, `sweep`; `hub/core/clean.py`; `hub/core/clip.py`), the seeded config copy, pointer definitions, VRAM accounting by model id (`hub/core/vram.py`, engine-agnostic), seeds, validation of every value before submit.

Must add:
- MP4 facts without decoding: width, height, fps, frame count, duration and audio presence from `moov` (`tkhd`, `mdhd`, `stsz`/`stts`, handler types), in `clip.py`'s box walker. Today a clip lands with w/h None (`enginecat.py:125`). The Hub then checks the clip against the `Request` (frames, size) instead of trusting any engine.
- Frame extraction for continuation: the last frame of a landed clip as a PNG, cleaned and landed in Temp, then sent as a `start` reference. Pillow cannot decode H.264. The Hub would call the server's system `ffmpeg` (already required for the engine's mux) as a fixed-argument subprocess. This revises the rule "no ffmpeg in the controller" of the parked full-module design (part 8, 8.C); the alternative is running it in a short-lived Hub helper process.
- Joining continued clips (stream copy, same tool), when a sequence feature exists.
- Definitions it may mirror: only facts an engine does not publish or publishes in an engine-specific way (one-pass key, reference role and cap, frame lattice, tiers), kept in the adapter's facts file and used only when the definition lacks them. The reference-cap table of the settings stays (`hub/modules/generate_image/models.py:3-5`).

Never owns: weights, downloads, inference, model code, VAEs, the mux inside a generation, prompt enhancement, or the engine's own definitions (only the Hub's `hub_auto` pointers).

## 5. Risks

- `image_prompt_type` letters drift. The fork's First/Last allows "TSEV" and Omni ""; upstream H3 allows "TSEVL" for both First/Last and Ref2VA (`UP:models/minimax_h3/minimax_h3_handler.py:710`, `:786`). `catalog.picture_refs` reads "S" as a start-frame model (`catalog.py:147`), so upstream Ref2VA would be offered as a start-frame model. Reference letters ("I", "KI", "FI", `UP:...:712-718`) also change.
- Manifest shape. The fork's Omni takes `minimax_h3_references` [{type, path, image_intent}]; upstream Ref2VA takes ordered `image_refs`, `video_guide`..`video_guide3`, audio guides and letters (`UP:...:108-114`). The Hub finds the key as "the one `*_references` list setting" (`catalog.py:145`), a convention only this fork follows.
- `*_multi_window` convention. Fork-only, and (section 2) not even published as a setting by the real fork. Upstream bounds windows through `sliding_window_defaults` (`UP:...:707-708`). `sliding_window_size = video_length` alone does not guarantee one pass.
- Upstream H3 publishes no `frames_maximum` or `resolution_presets` and starts at 107 frames with `frames_offset` (`UP:...:572-580`), so `video_facts` returns None and upstream lists no H3 at all (`catalog.py:171`, `:268`), silently.
- Text encoder: fork `minimax_h3_text_encoder_default/_variants`; upstream `text_encoder_variant` on the definition (`UP:...:562-563`); the suffix rule (`catalog.py:100-109`) finds nothing upstream.
- Private attributes (`job._thread`, `wan_model`, `transformer_type`, `_get_dropdown_deps`, the `get_lora_dir` patch) can change in any release of either line.
- Output list: an engine that returns a side file (a WAV, a JSON) fails the job by design (`enginecat.py:126-128`); upstream's `artifacts` path is not read.
- The fork's `wgp.py` imports HocusPocus `services.*` modules at import (`docs/architecture/parts/05-engine-lineage.md` 5.1.4); a fork change there breaks worker start.
- Fixture drift: the fake encodes what the authors believed; without capture, tests pin belief.

## 6. Staged plan

1. Capture reality. Run `main.py --dump-catalog` on the real fork (exists, `tests/engine/test_worker.py:209`) plus a capture of each video architecture's merged definition and factory settings; check them in under `tests/fixtures/contract/`. Done when the one-pass question in section 2 has an answer from the dump and the fake is corrected or the catalog fixed.
2. Fake from capture. A tool regenerates the fake's architectures and defaults from a capture; the `READS` equality test is green. Done when hand edits to `fake_engine.json` fail a test.
3. Hub terms. Add `engineapi.py` and `PROTO = 2`; a shim in the worker maps today's entries and tasks both ways, so modules do not change yet. Done when the full suite is green with the fake worker speaking Hub terms.
4. Modules on Hub terms. `build.py` emits a `Request`; `models.py` reads `ModelFacts` (roles, encoder ids, `one_pass` bool). Done when the key guard is green and the golden engine params are byte-identical for every existing image and clip test.
5. Split the adapters. Fork and upstream adapters behind `select`; the facts file carries the one-pass key; `autoreg` and `catalog_key` go through the adapter. Done when the contract suite passes for both fake flavours and the upstream flavour shows H3 either driven or with a one-line `why_not`.
6. Hub-owned media. MP4 facts from boxes; last-frame extraction through the system ffmpeg; clip checked against its request. Done when a landed clip carries w, h, seconds and audio presence, and "continue from last frame" produces a start reference with no engine call.
7. Second-engine drill. Point a dump at the upstream reference copy, diff its capture against the fork's, and drive one image and one clip through the upstream adapter. Done when adding it touched only `hub/worker/adapters/` and `tests/fixtures/contract/`.
