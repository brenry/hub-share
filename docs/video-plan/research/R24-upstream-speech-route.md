# R24 — upstream's speech route: the task, its fields, what it writes, how a voice sample reaches it (2026-10-17)

Research for BACKLOG item 8 (Stage 12 voice). Facts only, no decision. Engine citations are **upstream WanGP at
`af2ed29`** (`install/install-engine.sh:14-15`), read in a clean clone at `/tmp/upstream`, written
`upstream <file>:<line>`. Hub citations are this repo at the commit this note lands on.

## 1. The model
- One shipped speech model: `defaults/minimax_h3_tts_ref2va_pruned.json` — name "TTS MiniMax H3 Voice Clone 20B",
  architecture `minimax_h3_tts_ref2va_pruned`, `"group": "tts"` (upstream `defaults/minimax_h3_tts_ref2va_pruned.json:3-4`,
  `:10`). Its description: 32 kHz stereo dialogue, one segment per speaker turn, one or two cloned voices, Whisper
  boundary cleanup; it "reuses the pruned H3 Ref2VA checkpoint, jointly denoises a hidden 32x32 video, and saves
  only audio" (`:5`). Weights: the same two files as Ref2VA pruned (`MiniMax-H3-Ref2VA-pruned_rank8_bf16` /
  `_int8_convrot`) (`:6-9`).
- Handled by the H3 handler: `TTS_REF2VA_PRUNED_ARCHITECTURE` (upstream `models/minimax_h3/minimax_h3_handler.py:48`);
  its definition is `_get_audio_generator_model_def` (`:349-420`), returned for that architecture (`:559-560`).
- The capture agrees: `family` `tts`, `definition.audio_only` true, `profile_type` `video`, `t2v_class` and
  `image_prompt_types_allowed` absent (`tests/fixtures/contract/upstream-18.05/engine.json`, entry
  `minimax_h3_tts_ref2va_pruned`; asserted at `tests/engine/test_upstream_capture.py:109-110`).

## 2. Definition fields that shape the task (upstream `minimax_h3_handler.py`)
| Field | Value | Line |
|---|---|---|
| `audio_only` | True | `:353` |
| `image_outputs` | False | `:355` |
| `profile_type` | `"video"` | `:356` |
| `preserve_empty_prompt_lines` | True | `:357` |
| `sliding_window` | False | `:358` |
| `guidance_max_phases` / `visible_phases` | 1 / 0 | `:359-360` |
| `no_negative_prompt` | True | `:361` |
| `fps` | 24 | `:365` |
| `supports_early_stop` | True | `:366` |
| `duration_slider` | "Maximum Total Audio Duration (seconds)", min 4, max `H3_DIALOGUE_MAX_TOTAL_SECONDS`, step 1, default 15 | `:368-375` |
| `audio_reference_max_total_duration` | 15 | `:378` |
| `audio_guide_label` … `audio_guide3_label` | "Voice / Audio Reference 1/2/3" | `:380-382` |
| `audio_prompt_type_sources` | selection `""`, `A`, `AB`, `ABD`; `letters_filter` `ABD` (`:391`); default `A` | `:383-395` |
| `enabled_audio_lora` | True | `:396` |
| `sample_solvers` | euler, res_multistep, ralston_2s | `:414` |
| `deepy_infos` | the field summary quoted in §3 | `:417` |

- `get_profile_type_for_model` returns the definition's `profile_type` when set, else `"audio"` for an `audio_only`
  model (upstream `wgp.py:3999-4005`): this model is filed under the **video** profile. The Hub writes the picked
  profile to `profile`, `video_profile`, `image_profile` and leaves audio's (`hub/worker/wgpconfig.py:21-24`, `:78-79`).
- `fix_settings` returns early for this architecture (upstream `minimax_h3_handler.py:1167-1168`).

## 3. The task: fields it reads
Engine's own summary (`deepy_infos`, upstream `minimax_h3_handler.py:417`): "Generate 32 kHz stereo audio from
`prompt`. `audio_prompt_type`: empty = no sample; `A` = voice/audio from `audio_guide`; `AB` = two audio guides;
`ABD` = three audio guides. For Speaker scripts, samples map to speakers 1 to 3. Each sample must be at least 2s;
above 15s combined, the 15s are split evenly across samples. `duration_seconds` caps the assembled audio."

| Task key | What it is | Source |
|---|---|---|
| `model_type` | `minimax_h3_tts_ref2va_pruned` | definition file |
| `prompt` | the script (§4) | `generate_media(prompt, …)` upstream `wgp.py:6970` |
| `audio_prompt_type` | `""`, `A`, `AB`, `ABD` | `minimax_h3_handler.py:383-395` |
| `audio_guide`, `audio_guide2`, `audio_guide3` | file paths of the voice samples | `wgp.py:7030-7032` (generate_media args), passed to the model `wgp.py:8300-8302` |
| `duration_seconds` | cap on the assembled audio, 4 to 300 s (validated) | `minimax_h3_handler.py:873-880`; `dialogue.py:19`; passed `wgp.py:8355` |
| `video_length` | 0 | definition file `:14`; `minimax_h3_handler.py:1221` |
| `num_inference_steps` | 20 | file `:16`; handler `:1223` |
| `guidance_phases` | 1 | file `:17`; handler `:1224` |
| `sample_solver` | `euler` | file `:18`; handler `:1227` |
| `multi_prompts_gen_type` | `FG` | file `:19`; handler `:1232` |
| `seed` | per-turn seeds derive from it (`base + index*1000`), a negative seed draws one | `dialogue.py:154-172` |
| defaults also set | `guidance_scale` 1.0, `flow_shift` 12.0, `attention_sparsity` 1.3, `skip_steps_start_step_perc` 25, `skip_steps_multiplier` 0.08 | handler `:1219-1233` |

- Validation for this architecture (handler `:873-899`): `duration_seconds` must be a number in 4…300 s; each
  sample named by the letters is read with `librosa.get_duration(path=…)`, an unreadable one is refused ("Unable to
  read Audio Reference N"), one under 2 s is refused ("Audio Reference N must be at least 2 seconds long"); over 15 s
  combined only raises a notice (`_notify_audio_reference_limit`, `:341-346`).
- The Hub's task builder makes only `image` and `video` tasks; any other kind raises "No engine task for a … request"
  (`hub/worker/adapters/tasks.py:198-204`).

## 4. The prompt: dialogue script mode
- Switch: `H3_DIALOGUE_GENERATION = True` (upstream `models/minimax_h3/dialogue.py:16`).
- Dispatch: when the pipeline is `audio_only`, the switch holds, and the prompt has a `Speaker N:` header, it runs
  `generate_dialogue`; otherwise one ordinary H3 pass (upstream `models/minimax_h3/pipeline.py:760-769`).
- Grammar (`dialogue.py:27-41`, `:44-45`): one turn per `Speaker N:` block (optional `{…}` directions in the header);
  `[ … ]` text is direction, not spoken; a language may be named in a direction and carries to later turns of that
  speaker (`:117-145`). A turn with no spoken text raises (`:130-131`).
- Planning (`dialogue.py:148-172`): a turn's length is words / 2.6 + 0.18 s per `.!?;:` + 1.4 s, clamped 4…45 s
  (`:17-18`, `:23`, `:148-151`); 0.18 s pause between turns (`:22`); turns that would leave under 4 s of the cap are
  dropped (`:163-164`).
- Per turn, the engine writes its own six-section Ref2VA prompt with `[Shot 1] Speaker N (SN) … says exactly,
  <d>[Language] text</d>` (`dialogue.py:175-201`) and runs one H3 pass with `dialogue_segment=True` (`:398-421`).
- After generation, Whisper medium transcribes each turn and trims speech before/after the expected line
  (`dialogue.py:301-343`, `:432-438`); turns are joined with the pause and cut to the cap (`:440-445`).
- Early Stop finishes the current turn and returns completed turns (`dialogue.py:379-380`, `:428`).

## 5. How a voice sample reaches it
1. A path in `audio_guide` / `audio_guide2` / `audio_guide3`, selected by `A` / `B` / `D` in `audio_prompt_type`
   (handler `:881-886`; `dialogue.py:361-370`). Speaker 1 ↔ `A`, 2 ↔ `B`, 3 ↔ `D` (`dialogue.py:362-370`).
2. `wgp.py` preprocessing of `audio_guide` writes extra files into `save_path` only for letters `V` (vocal
   isolation), `N` (volume normalisation) or `X` (speaker separation) (upstream `wgp.py:7534-7580`); this model's
   `letters_filter` is `ABD` (handler `:391`). With `A` set and no `audio_guide`, wgp writes a silent WAV into
   `save_path` and lists it as a temp file (`wgp.py:7473-7475`).
3. The pipeline reads each sample with `soundfile` (`sf.info`, `sf.read`), mono is duplicated to stereo, more than
   two channels are cut to two, and it is resampled to 32 000 Hz (upstream `pipeline.py:510-527`, `:546-564`,
   `AUDIO_SAMPLE_RATE` `:36`). Above 15 s combined each sample is cut to `15 / n` s from its start (`:550-562`).
   No format conversion beyond what `soundfile` reads; which containers `soundfile` accepts is not checked here.
4. A speaker with no sample takes the last ≤ 15 s of its own first generated turn as its voice for later turns
   (`dialogue.py:20`, `:346-348`, `:427`; stated `:41`).
- Engine MCP (not used by the Hub): `audio_guide`, `audio_guide2`, `audio_guide3` are among its path fields
  (upstream `shared/mcp/server.py:113`); which are offered per model, `:832-834`.
- Hub today: uploads take PNG, JPEG, WebP only (`hub/core/fileroutes.py:27`, `:77-78`; route body "image" `:105`).

## 6. What it writes
- The model returns `{"x": audio, "audio_sampling_rate": 32000, "overridden_inputs": {"resolution": "32x32",
  "video_length": …, "duration_seconds": …}}` — no video (upstream `pipeline.py:1734-1736`; dialogue path
  `dialogue.py:448-449`).
- `wgp.py` for `audio_only`: no frames kept (`wgp.py:8632-8635`); codec `server_config["audio_stand_alone_output_codec"]`,
  default `"wav"` (`:3528`, `:8650-8653`); folder `audio_save_path` (`:8653`); name
  `<YYYY-MM-DD-HHhMMmSSs>_seed<seed>_<prompt>.<ext>` unless `output_filename` is set (`:8648`, `:8673-8674`);
  written by `save_audio_file` (`:8680-8683`) → `write_wav_file` → `sf.write(path, audio, 32000)` for WAV
  (upstream `shared/utils/audio_video.py:56-59`, `:414-420`). Sample rate from the model's result
  (`wgp.py:8443`). The WAV subtype is soundfile's default; not checked here.
- The Hub points `audio_save_path` at its outbox, as it does the other three paths (`hub/worker/wgpconfig.py:76-77`).
  `FORCED_CONFIG` does not set `audio_stand_alone_output_codec` (`:18-20`).
- The Hub's `land` takes an MP4 (to Clips) or a picture (to Temp); any other suffix is deleted and the job fails
  "The engine wrote a file the hub does not take" (`hub/core/enginecat.py:119-143`). `MEDIA_TYPES` holds images and
  `.mp4` only (`hub/core/files.py:25-26`).

## 7. The Whisper companion
- Loaded at model load when the switch holds (upstream `minimax_h3_handler.py:1139-1141`; `dialogue.py:204-217`),
  listed as a download only while the switch holds (`minimax_h3_handler.py:1108-1111`; `shared/deepy/assets.py:16-21`):
  repo `DeepBeepMeep/Wan2.1`, folder `whisper_medium`, files `config.json`, `model.safetensors` (`assets.py:7-11`).
- Found with `fl.locate_folder("whisper_medium")`; **fetched if missing** (`process_files_def`) (upstream
  `shared/deepy/transcription.py:55-80`).
- The Hub's facts file names these two files as the model's companions (`hub/worker/adapters/upstream.facts.json:220-228`);
  `lacking` reads them (`hub/worker/adapters/upstream.py:267-269`); a job whose model lacks a companion is refused
  before the engine runs (`hub/worker/wan2gp.py:242-246`).

## 8. The catalog exclusion, and what it means for this model
- The catalog leaves the speech model out (audio only), with its family `tts`.
- Mechanism: `catalog` lists a model only if it has `image_outputs` or `video_facts` returns facts
  (`hub/worker/catalog.py:175-179`); `video_facts` returns None for `audio_only` (`hub/worker/catalogvideo.py:201`,
  `:212-214`), and also for a model with no `t2v_class` and no native clip (`:212-213`) — this model has neither
  (§1). The test asserts it is absent from the catalog: "a speech model is upstream's page's, not the Hub's"
  (`tests/engine/test_upstream_capture.py:111`).
- Consequences in today's code, as they stand: no catalog entry, so it is not in Generate's pulldown and has no
  `lacks` status (`catalog.py:197`); the task builder has no kind for it (§3); its WAV output would be refused by
  `land` (§6). The companion entry for it in the facts file exists although the model is not listed (§7).
- A spec that brings this model back says how (`docs/BACKLOG.md:41-44`).

## 9. Not found / not checked
- Non-dialogue prompt on this model (no `Speaker N:`): one H3 pass, `frame_num = duration_seconds * 24` normalised
  (`pipeline.py:794-798`); its practical length limit and quality were not checked.
- Which audio containers `soundfile` reads on the installed engine env, and the WAV subtype written.
- VRAM and time per line on the server's GPU: not measured.
- The engine's prompt enhancer for this model (`prompt_enhancer_button_label` "Write", handler `:419`): the Hub sets
  `enhancer_enabled: 0` (`hub/worker/wgpconfig.py:18`); not read further.
- R14/R15 are not in the repo.
