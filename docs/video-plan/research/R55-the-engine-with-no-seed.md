# R55 — the engine with no seed: a task without the `seed` key, and a negative seed

Written for the open question of what the engine does with a task that holds
no `seed` key. Facts only; no decision. Upstream WanGP read at the pinned commit `af2ed29`
(`install/install-engine.sh:14-15`), cloned outside the repo. Citations: `upstream <file>:<line>` at `af2ed29`; repo
lines as `<file>:<line>`.

## Question
For each task kind the Hub sends (picture, clip, line of speech, cue or sound, room, audience sound, sketch still,
and the voice remux): what does upstream do with a task whose settings carry no `seed` key, and with `seed` -1 or
another negative number?

## 1. The path from the Hub into upstream
- Every engine task of the Hub, the remux too, is handed to `session.submit_task(params)`
  (`hub/worker/wan2gp.py:250-254`; the remux `hub/worker/adapters/voiceconvert.py:134-138`). The session is opened by
  `api.init(...)` with no `webui_state` (`hub/worker/wan2gp.py:147-148`), so it runs headless: `_use_webui_queue` is
  False (`upstream shared/api.py:599`, `:1653`) and a job runs through `run_cli_job` (`upstream shared/api.py:1058-1064`).
- On upstream, the Hub's `translate` sends the task as built, the forced keys on top, no factory settings underneath
  (`hub/worker/adapters/upstream.py:114-125`, `factory_underneath = False` `:247`). None of the forced keys is `seed`
  (`FORCED_TASK`, `FORCED_VIDEO` `upstream.py:56-58`).
- `submit_task` → `_normalize_task` (`upstream shared/api.py:835-838`, `:1284-1320`): wraps the settings as `params`,
  adds `settings_version`, video length and media flags; it neither reads nor adds `seed`.
- `run_cli_job` → `_run_tasks_worker`: `wgp.validate_task(task, state)` (`upstream shared/api_cli.py:149`), then
  `wgp.generate_media(task, send_cmd, ..., **filtered_params)`, where `filtered_params` keeps only the settings that are
  parameters of `generate_media` (`upstream shared/api_cli.py:123`, `:155-163`).

## 2. Where defaults are merged (a generation task: picture, clip, speech, sound)
- `validate_task`, for a task whose `mode` does not start with `edit_` (`upstream wgp.py:1964-1965`): `inputs =
  params.copy()`, then `clean_settings(model_type, inputs)` (`upstream wgp.py:9242-9248`), then `validate_settings`
  (`:9255-9258`).
- `clean_settings` (`upstream wgp.py:1847-1859`): `merged = get_factory_settings(model_type)`, then the task's values on
  top, **except a value that is `None` for a key the factory settings hold** (`:1850`); then every key of
  `primary_settings` the result lacks is set (`:1854-1855`).
- `get_factory_settings` (`upstream wgp.py:3303-3324`): a copy of `primary_settings`, the model's custom settings
  defaults, a few size keys, then the model handler's `update_default_settings`, then the model definition's own
  `settings` on top (`:3315-3318`).
- `primary_settings` is `models/_settings.json` (`upstream wgp.py:2636-2637`), which holds `"seed": -1`
  (`upstream models/_settings.json:32`).
- A model definition's `settings` are every top-level key of its definition file beside `"model"`
  (`upstream wgp.py:3406-3421`), read from `defaults/*.json` and `finetunes/*.json` (`:3377`).
- `validate_settings` (`upstream wgp.py:1040-1616`) has no line that reads or writes `seed`.
- Not on this path: `wgp.get_default_settings` (`upstream wgp.py:3326-3339`), which reads the per-model settings file
  and applies the `--seed` argument; `validate_task` and `clean_settings` do not call it. The session's own
  `get_default_settings` (`upstream shared/api.py:686-693`) returns the factory settings and is not called by
  `submit_task` either.

### 2.1 A missing `seed` key
- It is filled by `clean_settings`: the model's factory `seed` if its definition or handler sets one, else
  `primary_settings`' -1 (`upstream wgp.py:1849-1850`, `:3305-3318`, `models/_settings.json:32`).
- A `seed` key whose value is `None` is treated the same: the factory value replaces it (`upstream wgp.py:1850`).
- Raise: `generate_media` takes `seed` as a required positional parameter with no default (`upstream wgp.py:6965-6978`),
  so a call without it would raise `TypeError`; on this path it is always present after `clean_settings`
  (`primary_settings` holds it, `:1854-1855`). No path where the key stays missing was found.
- Definition files at `af2ed29` that set a `seed` other than -1 (`grep -rn '"seed"' defaults finetunes`):
  `upstream defaults/hunyuan_t2v_fast.json:18` (42), `defaults/hunyuan_t2v_accvideo.json:16` (42),
  `defaults/triposg.json:17` (42), `defaults/triposplat.json:18` (42), `defaults/geosam2.json:15` (3),
  `defaults/partcrafter.json:17` (0), `defaults/hunyuan3d_21.json:23` (1234), `defaults/hunyuan3d_21_shape.json:17`
  (1234). The files that set -1: `defaults/t2v_fusionix.json:18`, `t2v_nexus_1.3B.json:15`,
  `vace_14B_fusionix.json:17`, `vace_multitalk_14B.json:21`, `vace_14B_sf.json:21`,
  `ltx2_25_22B_alpha_gen.json:28`, `ltx2_25_22B_layout_to_render.json:28`. No file in `finetunes/` holds `seed`.
  One handler sets a seed in `update_default_settings`: `upstream models/triposg/triposg_handler.py:133` (3; its
  definition file's 42 is applied after it, `wgp.py:3315-3318`). For every other model, the factory seed is -1.

### 2.2 A seed of -1 or another negative number
- `generate_media`: `seed = None if seed == -1 else seed` (`upstream wgp.py:7365`); no line between it and
  `seed = set_seed(seed)` (`:7635`) reads `seed`.
- `set_seed` (`upstream wgp.py:6057-6065`): `None` or any value `< 0` → `random.randint(0, 999999999)`; it seeds
  `torch`, CUDA, `numpy` and `random` with the result and returns it. So -1 and every other negative number get the
  same treatment: a fresh draw.
- The model's generate call receives that returned, non-negative seed (`seed=seed`, `upstream wgp.py:8283`).
- After each finished output inside the repeat loop (`while not abort`, `upstream wgp.py:7665`), `seed =
  set_seed(-1)` (`:8862`): a second and later generation of one task (`repeat_generation` > 1) is drawn afresh even
  when a fixed seed was sent. The Hub's tasks do not send `repeat_generation` (`hub/worker/adapters/tasks.py`,
  `soundtask.py:22`), so the factory value applies: 1 in `primary_settings` (`upstream models/_settings.json:57`) unless the model's
  definition sets another.
- The speech route's own negative rule (`upstream models/minimax_h3/dialogue.py:154-170`: `None` or `< 0` → a draw,
  then `base + index*1000` per turn) is reached with the seed `set_seed` already returned (`generate_dialogue`, `dialogue.py:350-356`, imported by
  `models/minimax_h3/pipeline.py:25`), so on this path its draw branch does not run (read from the
  order of the lines; not run).

## 3. The voice remux (an edit task)
- The Hub calls `build_audio_remux_settings(..., seed=request.seed)` (`hub/worker/adapters/voiceconvert.py:115-118`).
  Its parameter is `seed: int = -1` and it writes `"seed": int(seed)` (`upstream shared/api.py:1562`, `:1571`).
  Called without `seed`, the task holds -1. Called with `seed=None`, `int(None)` raises `TypeError` there, before
  anything is submitted.
- `validate_task` for an `edit_` task (`upstream wgp.py:9176-9178`): `inputs = primary_settings.copy()`, the task's
  values on top; a missing `seed` takes -1. No factory settings of a model are merged on this branch.
- `generate_media` sends an `edit_` task to `edit_media` with the raw seed (`upstream wgp.py:7121-7123`), before the
  line `:7365`; `edit_media` calls `seed = set_seed(seed)` (`:6179`): a negative seed is a fresh draw, and after each
  output `seed = set_seed(-1)` (`:6420`).

## 4. Per task kind (upstream adapter)
Every kind below is a generation task on the path of §2 (the request types: `hub/worker/enginerequests.py:34`, `:47`,
`:158`, `:175`, `:183`; the builders `tasks.py:107`, `:237`, `:244`, `:282`, `soundtask.py:22`).

| Kind (Hub builder) | No `seed` key | `seed` -1 or other negative |
|---|---|---|
| Picture, sketch still (`PictureRequest`, `tasks.py:107`) | the model's factory seed (§2.1); -1 unless its definition sets one; -1 → a draw | a draw, `wgp.py:7365`, `:6057-6065`, `:7635` |
| Clip, a Storyboard or First cut clip, a cast, a pan (`ClipRequest`, `tasks.py:237`, `:244`) | as above | as above |
| Line of speech (`SpeechRequest`, `tasks.py:282`) | as above | as above; the per-turn seeds derive from the drawn one (`dialogue.py:158-170`) |
| Cue, room, audience sound (`SoundRequest`, `soundtask.py:22`; `director/cuetakes.py:138`, `generate_image/audience.py:109`) | as above | as above |
| Voice remux (`voiceconvert.py:118`) | argument left out: -1 (`shared/api.py:1562`), then a draw (`wgp.py:6179`); key missing in the task: -1 from `primary_settings` (`wgp.py:9177-9178`) | a draw (`wgp.py:6179`); `seed=None` passed: `TypeError` (`shared/api.py:1571`) |

No kind found where a missing key raises (the remux's `seed=None` argument aside).

## 5. Not known
- Which model is picked for each kind is the pulldown's; whether it is one of the definition files of §2.1 with a
  fixed seed is not known here. A definition file added by hand outside `defaults/` and `finetunes/` was not read.
- The fork adapter: `hub/worker/adapters/fork.py:55-60` puts `factory_settings` (`:67-81`, the fork's
  `primary_settings`, the handler's defaults, the model's `settings`) under the task. The fork's source was not read;
  what its `primary_settings` hold for `seed`, and how the fork treats a negative seed, is not known.
- Whether each model's own pipeline reads a seed from anywhere but the `seed` argument it is given was not read beyond
  `models/minimax_h3/dialogue.py` and `pipeline.py` (which seed their generators from that argument,
  `upstream models/minimax_h3/pipeline.py:1118`).
- Nothing above ran; it is read from the source at `af2ed29`.
