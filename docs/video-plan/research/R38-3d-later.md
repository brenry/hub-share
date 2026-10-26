# R38 — 3D from the Hub later: local image-to-3D, the engine's 3D models, and 3D scenes driving video, 2026-10-17

Research note. Engine: upstream WanGP `af2ed29` (2026-10-12), read in a clone; its 3D models arrived in v18.00
(commit `5b41d55`, 2026-10-10; README dated 2026-10-11). Newest WanGP `fde3c7e` (2026-10-17, v18.17) read for later
changes: none about 3D. Shallow clones in `/tmp/r38/` (commit, date): TRELLIS.2 `75fbf01` 2026-06-05, Pixal3D `f7cf384`
2026-09-01, TripoSplat `d8db9e0` 2026-08-13, Hunyuan3D-2.1 `82920d6` 2025-10-17, Hunyuan3D-Omni `4d47c0c` 2025-10-17,
Hunyuan3D-Part `e96be06` 2025-12-05, TripoSG `fc5c409` 2025-04-18, Step1X-3D `cb5ac94` 2025-09-09, SPAR3D `fdc311b`
2025-05-05, SF3D `ff21fc4` 2025-01-22, Hi3DGen `c29f668` 2025-07-02, VGGT `a288dd0` 2026-05-18, MapAnything `3d10cf7`
2026-08-07, Depth Anything 3 `3d835ec` 2026-07-27, HY-World-2.0 `df9988e` 2026-08-13, HunyuanWorld-Mirror `c61300e`
2026-05-27, Lyra `9fffc9a` 2026-07-20, VideoX-Fun `13bb3c6` 2026-10-14, Uni3C `75ed6e2` 2025-09-20, ReCamMaster
`fcf98bc` 2025-11-28, Vista4D `0aebdee` 2026-05-28. The GitHub API and huggingface.co could not be reached from this
container (proxy refused), so release dates are from READMEs and commits, and Hugging Face model cards were not read;
web items marked (search summary) were not opened. Facts only.


> Correction (R41–R45): the engine has 12 3D models, not 13 (confirmed in the model files; R41).

## 1. Image-to-3D and scene reconstruction that runs locally
Objects (one image → asset). VRAM is what the authors' README states; "—" = the README states none.

| Model | Repo, license | Latest (README / commit) | VRAM stated | Output | Texture |
|---|---|---|---|---|---|
| TRELLIS.2 4B | microsoft/TRELLIS.2, MIT | commit 2026-06-05 | "at least 24GB" (README:60) | GLB (`o_voxel...to_glb`, :151-167) | PBR |
| Pixal3D | TencentARC/Pixal3D, MIT | "Sep 2026: multi-view inference code" (:34) | — (has `--low_vram`, :95-98) | GLB (:89-92) | PBR (TRELLIS.2 backbone, :36) |
| Hunyuan3D 2.1 | Tencent-Hunyuan/Hunyuan3D-2.1, Tencent community (excl. EU/UK/KR) | released 2025-06-13 (:29) | 10 GB shape, 21 GB texture, 29 GB both (:81) | GLB | PBR |
| Step1X-3D | stepfun-ai/Step1X-3D, Apache-2.0 | news 2025-06-09 (:29) | 27 GB / 29 GB geometry+texture (:117-120) | mesh | textured |
| TripoSG 1.5B | VAST-AI-Research/TripoSG, MIT | commit 2025-04-18 | "at least 8GB" (:85) | mesh | none |
| SPAR3D | Stability-AI/stable-point-aware-3d, Stability community | commit 2025-05-05 | 10.5 GB, ~7 GB low-VRAM (:48); "about 6GB" per image (:82) | GLB (:82) | textured |
| SF3D | Stability-AI/stable-fast-3d, Stability community | commit 2025-01-22 | ~6 GB per image (README:80) | GLB | textured |
| Hi3DGen | Stable-X/Hi3DGen, MIT | commit 2025-07-02 | — | mesh (normal bridging) | none |
| TripoSplat | VAST-AI-Research/TripoSplat, MIT (code + weights, :61-62) | commit 2026-08-13 | — | `.ply` / `.splat` 3DGS (:49) | splat colours |

- Hunyuan3D 3.x: no open weights found; a guide says the 3.x family is hosted-only (search summary, undated).
- SAM 3D Objects (Meta): SAM License, gated checkpoints, 32 GB VRAM and Linux per third-party guides, output a splat
  PLY (search summary; not verified against the repo).
- TripoSplat: weights published around 2026-06-02 under MIT (CGWorld, search summary); ComfyUI day-zero support v0.23.0.
- TRELLIS.2 and Pixal3D merged into ComfyUI core on 2026-08-22 (comfyui-wiki news, search summary).

Scenes (photos/video → 3D; world models):

| Model | Repo, license | Latest | VRAM stated | Output |
|---|---|---|---|---|
| WorldMirror 2.0 1.2B (HY-World 2.0) | Tencent-Hunyuan/HY-World-2.0, Tencent HY-World community (excl. EU/UK/KR) | news "July 2026: HY World 2.1" (:31); commit 2026-08-13 | — in README (FSDP offload options, DOCUMENTATION.md:80) | 3DGS, point cloud, depth, normals, cameras |
| HY-World 2.0 generation (HY-Pano-2 ~80B, WorldStereo-2 ~17B) | same | gen code 2026-05-18 (:32) | — | 3DGS / mesh world (:119) |
| MapAnything | facebookresearch/map-anything, Apache-2.0 code; Apache checkpoint `map-anything-apache` (:148) | commit 2026-08-07 | memory-efficient mode; "2000 views on 140 GB" (:158) | metric point cloud + cameras |
| Depth Anything 3 | ByteDance-Seed/depth-anything-3, Apache-2.0 | commit 2026-07-27 | DA3-Streaming "less than 12GB" for long video (:43) | glb, npz, depth, ply, 3DGS video (:71) |
| VGGT 1B | facebookresearch/vggt, VGGT License; commercial use only with VGGT-1B-Commercial (:36, :283) | 2026-05-15 memory fix, 2–3× more frames (:32) | — | cameras, depth, point maps; COLMAP export |
| Lyra 2.0 (Wan-14B based) | nv-tlabs/lyra, Apache-2.0 code; weights NVIDIA Internal Scientific R&D Model License (Lyra-2/README:216-218) | GUI + training code 2026-07-20 (:16) | runtime given on 1× H100 80GB: ~9 min / 80 frames (:87) | camera-path video → 3DGS / mesh |

- World Labs Atlas: early access, no weights (search summary, item dated September 2026).
- HY-World 2.0 on an AMD iGPU (Strix Halo): community port report; stack pinned to CUDA 12.4 wheels (search summary,
  undated). A third-party guide gives 12–24 GB for HY-World 2.0 (search summary, not in Tencent's README).

## 2. 3D in WanGP at af2ed29
- Yes, 13 model types. v18.00 notes: "WanGP enters the third dimension" (upstream `README.md:85-90`); model guide
  `docs/MODELS.md:233-269`. Folders under `models/`: hunyuan3d, trellis2, triposg, triposplat, recon3d, worldmirror,
  animate_any_mesh.

| Engine model (defaults/) | Input → output | Licence file in the engine |
|---|---|---|
| `hunyuan3d_21` / `hunyuan3d_21_shape` | image → GLB + PBR; shape only; or texture a supplied mesh (MODELS.md:244) | Tencent Hunyuan 3D 2.1 community |
| `trellis2` | image → GLB with PBR, vertex colours or shape only; 512 / 1024 / 1024 Cascade / 1536 Cascade, texture 1024–4096 (`models/trellis2/settings.py:4-14`) | MIT |
| `triposg`, `partcrafter` | image → untextured GLB; PartCrafter one mesh per part (MODELS.md:245-246) | MIT (TripoSG) |
| `triposplat` | image → splat PLY, up to 262 144 Gaussians (`defaults/triposplat.json`) | MIT |
| `worldmirror_2` | photos and/or video → splats or point cloud + cameras, depth, normals | Tencent HY-World 2.0 community |
| `mapanything`, `da3_points`, `moge2` | photos/video → point cloud + cameras (metric / relative); MoGe-2 one photo → points or textured GLB of the visible surface (MODELS.md:256-258) | Apache-2.0 (MapAnything), others under `models/recon3d/LICENSE_*` |
| `geosam2`, `animate_any_mesh` | mesh → parts; mesh + text → 16-frame morph-animated GLB, no rig (MODELS.md:264-265) | Apache-2.0 (AnimateAnyMesh) |

- Every one sets `mesh_outputs: True` (e.g. `models/trellis2/trellis2_handler.py:34`, `models/worldmirror/
  worldmirror_handler.py:35`); the engine reports media type `"3d"` for them (`wgp.py:8841`).
- VRAM the engine states: WorldMirror "about 8 GB at 952 px with 24 views (weights included), plus about 0.15 GB per
  extra view; about 6 GB at 518 px" (`models/worldmirror/prompts.py:34-35`); MoGe-2 "little VRAM"
  (`models/recon3d/prompts.py:5`). Other 3D models: none stated. All object models ship int8 variants beside fp16/bf16.
- The engine writes its generation settings into each 3D file: GLB extras or a PLY comment under key `wangp`
  (`shared/utils/mesh_outputs.py:15`, `:80-87`).
- Renderer `shared/mesh3d/render.py` has modes shaded, albedo, normal, depth, position, mask (`:19`, `:143-145`) and a
  `turntable()` video function (`:239`); no caller of `turntable` exists in the engine. The UI's 3D gallery saves a
  still view for use as a start image or reference (MODELS.md:269). Agents get `render_3d_views`
  (`shared/mcp/v2.py:55`).
- The Hub today: the catalog leaves out any model with `mesh_outputs` (`hub/worker/catalog.py:2-3`, `:176`); the worker
  sets `mesh_save_path` to its outbox (`hub/worker/wgpconfig.py:76-77`).

## 3. A 3D scene driving a video model
H3 at af2ed29:
- Control model: `minimax_h3_control` (33B) and `minimax_h3_control_pruned` (20B), "FL2VA with the VideoX-Fun
  ControlNet-Union 2.0 branch" (`defaults/minimax_h3_control.json`).
- `video_prompt_type` choices: `""`, `PV` Open Pose, `DV` depth, `EV` Canny, `SV` shapes/scribble, `CV` grayscale,
  `V` video already a control map (HED, MLSD, layout…), `MV` inpainting only; mask `A` / `NA`
  (`models/minimax_h3/minimax_h3_handler.py:548-553`, `:239`). Letter → process: `wgp.py:4893`.
- `V` "Use Control Video as is": upload a prepared Pose, Depth, Canny, HED, MLSD, Scribble, Layout or Gray map
  (`minimax_h3_handler.py:205`). Control strength `control_net_weight` 0–2; guidance 1; window ≤ 362 frames; no
  two-phase, no text-to-image (`:208`, `:234`, `:239`, `:554`).
- Output takes the control video's aspect ratio; H3 still generates stereo sound (`:196`). Start/end image or a
  continued video can be combined, kept consistent with the control (`:224`).
- No camera-path input on any H3 model. Ref2VA reference videos guide "appearance, motion or camera" (`:111`).
  VideoX-Fun lists "trajectory control" for H3 ControlNet-Union 2.0 (VideoX-Fun README:328); the engine's selection
  above has no trajectory letter.

Preprocessors at af2ed29 (`preprocessing/processors.py`):
- Pose: DWPose (`yolox_l.onnx` + `dw-ll_ucoco_384.onnx`) (`:31-39`). Depth: Depth Anything V2 vitl (default) or vitb, or
  DA3 metric large, by config `depth_anything_v2_variant` (`:41-67`; dropdown `plugins/configuration/plugin.py:520`).
  Canny and scribble share `netG_A_latest.pth` (`:72-83`); gray (`:68`); RAFT flow (`:84`).

Camera inputs elsewhere in the engine:
- `fun_camera_1.3B` (Plücker rays) and `uni3c` (14B; depth → point cloud → renders guide a ControlNet): preset or
  custom path, `.npz` `cam_c2w` + intrinsics or CameraCtrl/RealEstate10K `.txt`; 832×480, 81 frames, 16 fps, no sliding
  windows (`models/wan/camera_control/infos.py:30`, `:39`, `:80`, `:125`).
- `vista4d`: reshoot a video along preset or custom `.npz` path; `recam_1.3B`: presets, 81 frames
  (`models/wan/infos.py:141-153`).
- `ltx2_25_22B_layout_to_render`: "a viewport animation or playblast into a finished shot" with an appearance
  reference; IC-LoRA `ltx-2.5-22b-ic-lora-layout-to-render-1.0`, `video_prompt_type` `VGI`, 121 frames, 1920×1088
  default (`defaults/ltx2_25_22B_layout_to_render.json`; MODELS.md:88).
- VACE (`vace_*`) takes pose/depth/etc. control videos (`docs/VACE.md`, not read in detail here).

How people render passes from 3D tools now:
- LTX docs list "Blender/3D software — for synthetic depth renders" for the Depth IC-LoRA; consistent depth range,
  no flicker, resolution matching the generation (docs.ltx.video IC-LoRA page, undated; search summary).
- RunComfy "Blender to ComfyUI AI Renderer 2.0": Blender depth, outline or pose passes → Wan 2.1 VACE 14B (SkyReels
  R2V merge), with DA3-BASE (search summary, undated).
- ComfyUI `WanUni3CControlnetApply` takes a rendered guidance video such as a warped point-cloud render (docs.comfy.org,
  search summary).
- No dated guide (2026-08-18 onward) for Blender → H3 ControlNet was found; no exporter from Blender to the `.npz`
  camera format was found.

## 4. Community and release items, 2026-08-18 to 2026-10-17
- 2026-08-22: TRELLIS.2 and Pixal3D native in ComfyUI core (comfyui-wiki; search summary).
- 2026-08-24: H3 Fun ControlNet-Union released by Alibaba PAI, ~6.8 GB, Canny/Depth/HED/MLSD/Pose + inpaint,
  `control_context_scale` 0–1, guidance 1; Comfy docs: works with fl2va and ref2va, example uses SDPose (comfyui-wiki,
  docs.comfy.org; search summary). No quality measurements found.
- August 2026 (day not given): a Medium hands-on of TRELLIS.2 reports ~24 GB VRAM (search summary).
- Sep 2026: Pixal3D multi-view inference code (repo README:34).
- 2026-09-05: LTX-2.5 ReelBids dolly-in camera LoRA V2, seven speeds (roundup, search summary).
- 2026-09-19: HyperFlow 8-step H3 LoRA; one ComfyUI user: "closer to h3 quality, consistency/camera control/detail"
  (comfyui-wiki; search summary). Not a camera-control LoRA.
- 2026-10-11: WanGP v18.00 adds the 3D models and Fun Control-Camera / Uni3C (upstream README:67-96).
- No community VRAM or quality reports dated in the window were found for WanGP's 3D models, TripoSplat, WorldMirror
  2.0, Lyra 2.0 or Uni3C. A Hugging Face thread on the first TRELLIS (undated) has ">16GB" from the maintainer and one
  12 GB RTX 4070 success (search summary).

## 5. Not known
- VRAM and time of each WanGP 3D model on the server's card; only WorldMirror and MoGe-2 state figures.
- Whether WanGP's H3 control accepts a Blender depth render as `V` with the same result as its own `DV` depth
  (normalisation, near/far convention); the engine documents no expected depth encoding.
- Whether the ControlNet-Union "trajectory control" VideoX-Fun lists can be used through WanGP.
- Hunyuan3D 3.x open weights; the Hugging Face cards (licences, dates) of TripoSplat, Pixal3D, Lyra 2.0, SAM 3D.
- Any measured quality comparison of H3 depth/pose control or Uni3C against other camera methods.

## Sources
Engine: upstream WanGP `af2ed29` files cited above. Repos (GitHub, cloned): microsoft/TRELLIS.2, TencentARC/Pixal3D,
VAST-AI-Research/TripoSplat, VAST-AI-Research/TripoSG, Tencent-Hunyuan/Hunyuan3D-2.1, Tencent-Hunyuan/Hunyuan3D-Omni,
Tencent-Hunyuan/Hunyuan3D-Part, stepfun-ai/Step1X-3D, Stability-AI/stable-point-aware-3d, Stability-AI/stable-fast-3d,
Stable-X/Hi3DGen, facebookresearch/vggt, facebookresearch/map-anything, ByteDance-Seed/depth-anything-3,
Tencent-Hunyuan/HY-World-2.0, Tencent-Hunyuan/HunyuanWorld-Mirror, nv-tlabs/lyra, aigc-apps/VideoX-Fun, ewrfcas/Uni3C,
KwaiVGI/ReCamMaster, Eyeline-Labs/Vista4D, deepbeepmeep/Wan2GP. Web (search summaries):
[comfyui-wiki H3 ControlNet-Union](https://comfyui-wiki.com/en/news/2026-08-24-minimax-h3-fun-controlnet-union),
[Comfy docs H3 ControlNet](https://docs.comfy.org/tutorials/video/minimax/minimax-h3-fun-controlnet),
[comfyui-wiki TRELLIS.2/Pixal3D](https://comfyui-wiki.com/news/2026-08-22-trellis2-pixal3d-native-comfyui),
[comfyui-wiki HyperFlow](https://comfyui-wiki.com/en/news/2026-09-19-hyperflow-h3-8step-lora),
[CGWorld TripoSplat](https://cgworld.jp/flashnews/01-202606-TripoSplat.html),
[Medium TRELLIS.2](https://medium.com/@ammanakhtar8/one-image-in-3d-out-free-open-source-i-ran-trellis-2-3f7f5ed8e96c),
[LTX IC-LoRA](https://docs.ltx.video/open-source-model/usage-guides/ic-lo-ra),
[RunComfy Blender→ComfyUI](
https://www.runcomfy.com/comfyui-workflows/blender-to-comfyui-ai-renderer-2-0-workflow-cinematic-video-output),
[Comfy WanUni3CControlnetApply](https://docs.comfy.org/ja/built-in-nodes/WanUni3CControlnetApply),
[Last Week in Multimodal AI #65](https://thelivingedge.substack.com/p/last-week-in-multimodal-ai-65-video),
[HY-World on Strix Halo](https://sleepingrobots.com/dreams/hy-world-2-strix-halo),
[SAM 3D Objects](https://huggingface.co/facebook/sam-3d-objects),
[TRELLIS HF discussion](https://huggingface.co/spaces/microsoft/TRELLIS/discussions/8).
