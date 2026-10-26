# R41 — WanGP's 3D models in the Hub: definitions, outputs, and what the catalog reads, 2026-10-17

Research note. Builds on R38 (cited "R38 §n", not repeated). Engine: upstream WanGP `af2ed29` (2026-10-12, v18.05),
read in a clone at `/tmp/upstream`. Hub: `main` at `32ccfb6` (2026-10-17). Web: sources dated 2026-08-18 onward only;
GitHub issue pages of deepbeepmeep/Wan2GP were fetched; no WanGP-specific 3D report turned up in web search. Facts only.

## 0. How many 3D types
- 12, not 13. The defaults files whose architecture a handler marks `mesh_outputs: True` are: `hunyuan3d_21`,
  `hunyuan3d_21_shape`, `trellis2`, `triposg`, `partcrafter`, `geosam2`, `triposplat`, `worldmirror_2`, `mapanything`,
  `da3_points`, `moge2`, `animate_any_mesh`. No defaults file sets `mesh_outputs` itself; the handlers do (below). No
  `finetunes/*.json` uses these architectures. The README names the same 12 (upstream `README.md:86-88`).
- Handlers (`query_supported_types`): `models/hunyuan3d/hunyuan3d_handler.py:39-40` (2 types),
  `models/trellis2/trellis2_handler.py:11-12`, `models/triposg/triposg_handler.py:36-37` (triposg, partcrafter,
  geosam2), `models/triposplat/triposplat_handler.py:11-12`, `models/recon3d/recon3d_handler.py:6`, `:20-21` (moge2,
  mapanything, da3_points), `models/worldmirror/worldmirror_handler.py:12-13`,
  `models/animate_any_mesh/animate_any_mesh_handler.py:18-19`.
- No `profiles/<type>` folder exists for any of the 12 (`profiles/` lists video and image families only), though every
  handler sets `profiles_dir: [base_model_type]`.

## 1. The definitions
Inputs: "I" = `image_ref_choices` letter (pictures as `image_refs`); "V" = `guide_custom_choices` letter (a reference
video); "mesh" = `custom_guide` file (`.glb .obj .ply .stl`). No 3D type sets `image_prompt_types_allowed` except
geosam2 (`""`, `triposg_handler.py:62`). Output: what the pipeline returns (`meshes` → `.glb`, `splats` → `.ply`).

| Type | Pipeline (`models/…`) | Inputs | `model_modes` | Output | Side files | int8 file |
|---|---|---|---|---|---|---|
| `hunyuan3d_21` | `hunyuan3d/hunyuan3d_main.py:233` | 1 I (alpha kept); mesh optional | shape_texture / shape / texture | GLB, PBR | — | yes |
| `hunyuan3d_21_shape` | same | 1 I | — | GLB, untextured | — | yes |
| `trellis2` | `trellis2/trellis2_main.py:282` | 1 I | 512 / 1024 / 1024 Cascade / 1536 Cascade | GLB: PBR, vertex colours or none | — | yes |
| `triposg` | `triposg/triposg_main.py:247` | 1 I | — | GLB, untextured | — | yes |
| `partcrafter` | same | 1 I | — | GLB, one node per part | — | yes |
| `geosam2` | `triposg/geosam2_main.py:658` | mesh (required); point prompts in `alt_prompt` | — | GLB, one node per part | `_views.png` | no |
| `triposplat` | `triposplat/triposplat_main.py:216` | 1 I | — | PLY splat | — | yes |
| `worldmirror_2` | `worldmirror/worldmirror_main.py:202` | I (many) and/or V | gaussians / points | PLY splat | `_points.ply`, `_cameras.json` | yes |
| `mapanything` | `recon3d/recon3d_main.py:156` | I (many) and/or V | — | PLY splat | `_points.ply`, `_cameras.json` | yes |
| `da3_points` | same | I (many) and/or V | — | PLY splat | `_points.ply`, `_cameras.json` | no |
| `moge2` | `recon3d/recon3d_main.py:156`, `:173` | 1 I | points / mesh | PLY splat, or GLB textured from the photo | `_cameras.json` (+ `_points.ply` for points) | no |
| `animate_any_mesh` | `animate_any_mesh/animate_any_mesh_main.py:180` | mesh (required) + English motion text | — | GLB, 16-frame morph animation, textures kept | — | no |

Per type (custom settings are `custom_settings` entries: id, type, default):
- `hunyuan3d_21` / `_shape` (`defaults/hunyuan3d_21*.json`): `octree_resolution` 196–512 (256), `max_faces` (40000
  textured / 0), textured adds `texture_views` 6_512/8_768/9_768 (8_768), `texture_size` 1024–4096 (2048)
  (`hunyuan3d_handler.py:18-34`). Mode "Texture a Mesh" needs the mesh (`:106-107`); `custom_guide` `:92-93`; `no_lora`
  (`:69`). Defaults 30 steps, guidance 5, texture guidance 3 (`:122-133`). Weights `URLs` (DiT) and `URLs2` (paint),
  plus shared files from repo `DeepBeepMeep/3D` (`:9-12`, `:100-102`).
- `trellis2`: `texture_mode` texture/vertex/none, `max_faces` 20k–2M (100000), `texture_size`, `max_tokens` (49152),
  `alpha_mode` opaque/blend (`models/trellis2/settings.py:9-19`); modes `:3-7` (default 2, 1024 Cascade). 12 steps,
  guidance 7.5, texture guidance 1 (`trellis2_handler.py:80-90`). UV unwrapping on the CPU: "about 30 s at 100,000
  faces, 1.5 min at 200,000" (`models/trellis2/prompts.py:34-35`).
- `triposg` / `partcrafter`: `mesh_resolution` 256/512 (512), `max_faces` (0), partcrafter `num_parts` 1–16 (4)
  (`triposg_handler.py:20-31`); 50 steps, guidance 7 (`:135-143`). PartCrafter drops parts with no surface (prints it,
  `triposg_main.py:227`).
- `geosam2`: `postprocess_pa` 0.01–0.035 (0.02), `auto_segment` 1/0 (`triposg_handler.py:10-17`); no step control
  (`:67`); `query_model_files` returns nothing (`:113-114`); seed 3 (`:133`).
- `triposplat`: `num_gaussians` 32K–256K (262144) (`models/triposplat/settings.py:3-8`); 20 steps, guidance 3, flow
  shift 3 (`triposplat_handler.py:77-87`); loads `flux2_vae.safetensors` from `DeepBeepMeep/Flux2`.
- `worldmirror_2`: `max_views` 1–64 (24), `max_resolution` 518–952 (952), `filtering` sky_edges/edges/none
  (`models/worldmirror/settings.py:7-15`); refuses runs with neither I nor V, or with photos already at `max_views`
  while V is on (`worldmirror_handler.py:69-77`). `_cameras.json` holds per view `camera_to_world`, `intrinsics`, FOV
  (`worldmirror_main.py:198-201`).
- `mapanything` / `da3_points` / `moge2`: `max_points` (1M), `max_frames` (16; da3 up to 128), `confidence`, da3
  `process_res` 504–1008, moge2 `max_size` 512–2048, `detail`, `edges` (`models/recon3d/settings.py:3-34`); one step,
  locked (`recon3d_handler.py:51-52`, `:103`). `da3_points` has no `URLs`: it uses the checkpoint of the engine's DA3
  depth preprocessor (`recon3d_handler.py:84-86`; `defaults/da3_points.json`). Only mapanything ships an int8 file.
- `animate_any_mesh`: `fps` 1–60 (10), `playback` forward/pingpong (16 or 31 frames), `trajectories`, `max_vertices`
  (50000) (`models/animate_any_mesh/settings.py:3-14`); 63 steps, guidance 3 (`animate_any_mesh_handler.py:78-85`); text
  encoder CLIP ViT-L/14 from `DeepBeepMeep/HunyuanVideo` (`text_encoder_URLs`, `:51`).
- The prompt is a name, not conditioning, for the object and scene models: `prompt_description` "Asset Name /
  Description (used for file names)" (e.g. `trellis2_handler.py:42`), "Scene Name…" (`worldmirror_handler.py:44`).

Writing the file (all 12):
- `wgp.py:8654-8656`: extension `glb` when the pipeline returns no `splats`, else `ply`; folder `mesh_save_path`. Name
  `<YYYY-MM-DD-HHhMMmSSs>_seed<seed>_<prompt>.<ext>` (`wgp.py:8674`), or the `output_filename` template (`:8668-8673`).
  One file per asset, `_1`, `_2`… for a batch (`:8689-8696`).
- Preview: `<stem>.png` beside each asset, from the pipeline's `x` tensor (`wgp.py:8695`;
  `shared/utils/mesh_outputs.py:101-105`).
- Settings embedded under key `wangp`: GLB `asset.extras`, PLY `comment wangp <json>` (`mesh_outputs.py:80-87`), written
  only when `metadata_type` is `metadata` or `json_metadata`; `json`/`json_metadata` also writes `<stem>.json`
  (`shared/utils/media_recording.py:39-48`).
- Side files: `<stem><suffix>` beside the asset plus `<file>.wangp-files.json`, written unless the caller asked for them
  back and no workspace is bound (`shared/utils/side_files.py:8-28`; `wgp.py:7116`, `:8839`).
- Media type reported "3d" (`wgp.py:8841`); post-processing and resolution are skipped for 3D (`:7145-7146`, `:1052`).

VRAM / time the engine states: WorldMirror and MoGe-2 only (R38 §2); TRELLIS.2 1536 Cascade "slower and more memory
hungry" (`models/trellis2/prompts.py:22`). No other figures in defaults, handlers, `docs/MODELS.md:233-269` or the
README.

## 2. The Hub's catalog today
- `hub/worker/catalog.py:176-177`: `entry` returns None for any definition with `mesh_outputs`; the module header says
  why (`:1-3`): the engine also sets `image_outputs` on these (all 12 handlers do), so without the check they would read
  as picture models. `mesh_outputs` is declared in `READS` (`:34`).
- Fields the catalog reads for a picture (`describe`, `:79-106`): `name`, `embedded_guidance`, `guidance_max_phases`,
  `image_ref_choices` (→ `ref_choices`, `modes` "new"/"refs", `:53-68`), `vae_block_size`, `lock_inference_steps`,
  `no_lora`, `hub_auto`/`hub_base`, `URLs` (presence, `:137-147`), `visible`, `image_outputs` (`:176-178`); factory
  settings `num_inference_steps`, `guidance_scale`, `embedded_guidance_scale`, `resolution` (`:23`).
- For a clip (`hub/worker/catalogvideo.py:23-29`, `:198-239`): `image_outputs`, `audio_only`, `t2v_class`,
  `image_prompt_types_allowed`, `fps`, `frames_minimum/steps/maximum`, block size, `resolution_presets`, encoders,
  `sliding_window_defaults`, `settings`. `video_facts` returns None when `image_outputs` is set (`:212`).
- Picture model ids feed `definitions.weights` (`hub/worker/wan2gp.py:175-176`), so 3D types are absent there too.
- The worker forces `metadata_type: "none"` (`hub/worker/wgpconfig.py:18`) and `mesh_save_path` = outbox (`:76-77`).
- The facts files (`hub/worker/adapters/upstream.facts.json`, `fork.facts.json`) contain no 3D model, `mesh` or `3d`
  entry.

Definition fields upstream provides that identify a 3D model and its inputs/outputs without names:
- `mesh_outputs: True` on all 12; the engine derives `main_output: ["3d"]` from it (`models/model_metadata.py:94-99`).
- `model_def["metadata"]` (`model_metadata.py:9`, `:253-280`; filled at `wgp.py:2883`): `main_output`, `inputs`
  (text/image/video/"3d", `:113-134`), `media_inputs` (`:146-188`: `image.reference`, `single_reference`,
  `multiple_references`, `video.reference`, `custom_file` {name, kinds ["3d"], file_types, required}), `setting_values`
  (`video_prompt_type` choices from `image_ref_choices`/`guide_custom_choices`, `model_mode` choices, `:221-251`),
  `specialities` (name, aliases, description).
- Raw fields: `image_ref_choices`, `one_image_ref_needed`, `one_image_ref_only`, `image_refs_keep_alpha`,
  `no_background_removal`, `guide_custom_choices`, `reference_video_enabled`, `video_guide_label`, `custom_guide`
  (`file_types`, `required`), `alt_prompt` (geosam2), `model_modes`, `custom_settings` (id, label, type, min, max, inc,
  choices, default), `prompt_description`, `inference_steps`, `lock_inference_steps`, `guidance_max_phases`,
  `alt_guidance`, `no_lora`, `image_batch_size_max`, `text_encoder_URLs`.

Facts the definitions do not carry:
- The file type of the result: GLB or PLY is decided at run time by what the pipeline returns (`wgp.py:8655`); nothing
  in the definition says which, and for `moge2`/`worldmirror_2` it depends on `model_mode` (only the mode labels say
  it).
- Whether the result is textured, animated, multi-part, or a splat: only in `description`, `specialities` and mode
  labels.
- Which side files a type writes and their suffixes.
- VRAM or time per type; no profile files.
- Which non-`URLs` companion files a type needs is only in the handler's `query_model_files` (e.g. DINO, Flux2 VAE), not
  in the definition; `da3_points` and `geosam2` defaults list no `URLs`.

## 3. Web, 2026-08-18 onward
- 2026-10-14 to 10-16, Wan2GP issue #2471 "Trellis 2 error": TripoSG and TripoSplat "work well"; TRELLIS.2 failed at
  decimation with `ModuleNotFoundError: fast_simplification`; a commenter: `xatlas` and `fast_simplification` were in
  `requirements.txt` but not installed on update, TRELLIS.2 always decimates while TripoSG skips it at Max Faces 0; then
  a Triton `tcc.exe` error; fixed by reinstalling WanGP outside Pinokio. No GPU or VRAM stated. At `af2ed29`
  `requirements.txt:80-83` lists `xatlas`, `fast-simplification`, `scikit-image>=0.26.0`; decimation imports
  `fast_simplification` in `shared/mesh3d/cleanup.py:146` and `shared/mesh3d/mesh_worker.py:81`.
- 2026-10-12, issue #2454: "scikit-image>=0.26.0 breaks Python 3.10 compatibility" (title only read).
- Issues opened 2026-10-10 to 10-17 (42, titles read): #2471 is the only one about a 3D model.
- No dated report (Reddit, forums, blogs) of VRAM, time or quality of any WanGP v18 3D model was found; four searches
  returned only undated pages about the upstream models, left out here.
- The proxy here refused the GitHub API and huggingface.co (R38 header); no Reddit page came up in search.

## 4. Not known
- VRAM, time and quality of any of the 12 on the server's card; no engine figures beyond WorldMirror and MoGe-2.
- Whether the installed engine environment has `xatlas`, `fast-simplification` and `scikit-image>=0.26` installed: the
  Hub's `install/install-engine.sh` uses the existing engine Python and was not seen installing requirements.
- Whether a Hub task through `shared.api` sets `return_side_files` (then no side files are written beside the asset) or
  not; the Hub's api options were not traced here.
- Why the task brief counts 13 types: 12 are found at `af2ed29`.
- How `presence` (`catalog.py:137-147`) would rate `da3_points` and `geosam2`, which have no `URLs`.
- Whether the engine's stdout prints in 3D pipelines (`worldmirror_main.py:156`, `:191`; `side_files.py:26`) matter to
  the worker's channel.

## Sources
Engine: upstream WanGP `af2ed29` files cited. Hub: `32ccfb6` files cited. R38
(`docs/video-plan/research/R38-3d-later.md`).
Web: [Wan2GP issue #2471](https://github.com/deepbeepmeep/Wan2GP/issues/2471) (2026-10-14..16, fetched),
[Wan2GP issues since 2026-10-09](https://github.com/deepbeepmeep/Wan2GP/issues?q=is%3Aissue%20created%3A%3E2026-10-09)
(fetched 2026-10-17, titles only).

