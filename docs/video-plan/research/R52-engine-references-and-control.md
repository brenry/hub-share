# R52 — Engine facts for sketch panels (references + layout) and for the control route (blueprint §15, §17, §19)

Research note, 2026-10-20. Read-only. Engine: upstream WanGP at `af2ed29` (the commit `install/install-engine.sh`
pins), read from a read-only clone outside the repository (`git log -1` =
`af2ed29a83db…`, "Merge branch 'main'", 2026-10-12; working tree clean). Cited as `upstream <file>:<line>`. Hub files
cited as `hub <file>:<line>`. Everything not marked **inference** is read in code at the cited line.

Read in the repo first: BLUEPRINT-director.md §15, §17, §18, §19; R48 §7 and blueprint §9 (unknowns);
`hub/worker/adapters/upstream.facts.json`; `hub/modules/generate_image/models.py`, `build.py`;
`hub/worker/adapters/tasks.py`, `hub/worker/catalog.py`; HANDOFF.md "Not verified" item 1.

---

## 0. How the engine passes pictures to an image model (common to every family)

- **References** = `image_refs` (a list of files) plus a reference letter in `video_prompt_type`: `I` (people/objects)
  or `KI` (first picture is the main scene). Validation: `I` needs at least one picture
  (`upstream wgp.py:1414-1416`); a model with `one_image_ref_only` refuses more than one (`:1420-1421`). wgp.py has
  **no general maximum** on the count; caps are per family (below).
- **A guide / control image** = `image_guide` (a file) plus `V` in `video_prompt_type`, with an optional process letter
  before it: `P` pose, `D` depth, `S` scribble/shapes, `E` canny, `C` gray, `M` inpaint (`upstream wgp.py:4893`);
  `V` alone = no processing ("raw", `wgp.py:7975-7980`). In image mode `V` requires `image_guide`
  (`wgp.py:1426-1429`); the image is turned into a one-frame `video_guide` (`wgp.py:7167-7172`). `image_guide` is an
  accepted setting (`upstream models/_settings.json:107`; attachment key, `wgp.py:205`).
- **Order when both are given**: every family that takes both prepends the processed guide image to the references,
  so the layout becomes picture 1 and `image_refs` follow (Qwen 20B edit: `upstream models/qwen/qwen_main.py:231-232`;
  Qwen 2.1: `models/qwen21/pipeline.py:220-222`; Flux 2: `models/flux/flux_main.py:328-329`; Krea 2 edit:
  `models/krea2/krea2_main.py:814-815`; HiDream O1: `models/hidream/hidream_main.py:234-238`, after a start image).
- **Output size with a guide**: the processed guide sets the canvas (`wgp.py:8038-8040`; the guide is fitted at its
  own aspect, `wgp.py:5735-5736`). Without a guide, with `K`, the first reference is resized to the exact canvas
  (`upstream shared/utils/utils.py:704-708`, `any_background_ref`, `wgp.py:7490-7491`); other references keep their
  own aspect at the canvas's pixel count (`utils.py:724-728`; `fit_into_canvas_image_refs` 0 for every image family
  below).
- **Sizes**: the API refuses a size above the model's budget (`wgp.py:9249`, `shared/resolutions.py:499-510`); the
  default budget is `1920x1088` (`resolutions.py:12`). No image family read sets a minimum (`resolution_min`
  appears only in the finetune editor and `resolutions.py:363`, default 0). Sides must divide by the family's block.
- **What the Hub sends today**: a picture task is `image_refs` + one reference letter, never `image_guide`
  (`hub hub/worker/adapters/tasks.py:86-109`; the letter is `I` when the model offers it, else the first choice with
  `I`, `tasks.py:80-84`, so `KI` is never sent on Qwen/Flux2/Krea2 edit). The Hub's cap is its own table, not the
  engine's: `ref_caps` default `{"qwen_image_21": 6, "krea2_": 2}` (`hub hub/settings.py:46`), any other model 3
  (`hub hub/modules/generate_image/models.py:28`, `:121-126`).

## A. Sketch panels: each image family

| Family (engine id) | References: count, how | Pose / layout image | Combine guide + refs in one job | Size facts |
|---|---|---|---|---|
| **Qwen-Image Edit Plus 2509 / 2511** (`qwen_image_edit_plus_20B`, `_plus2_20B`) | `image_refs`, `KI` or `I` (`models/qwen/qwen_handler.py:78-85`); passed as separate pictures, `Picture N:` per image (`pipeline_qwenimage.py:220-224`), not stitched (`qwen_main.py:243-247` stitches only non-Plus). **No count cap in code**. | **Yes**: `image_guide` with `PV` pose, `DV` depth, `SV` shapes, `CV` recolor, or `V` "Qwen Raw Format" (`qwen_handler.py:103-107`); engine help: "Edit Plus … offer Control Image Process for pose, depth, sketch or edge guidance" (`models/qwen/infos.py:21-22`). | **Yes**: guide prepended as picture 1, refs after (`qwen_main.py:231-232`). | Sides ÷16 (`pipeline_qwenimage.py:681-683`); each picture to the vision encoder at ~384² area (`:722`, `:736`); latents of a reference at its own (wgp-resized) size (`:729-734`). Default budget 1920×1088. |
| Qwen-Image Edit (2508) (`qwen_image_edit_20B`) | `image_refs` `KI`/`I` (`qwen_handler.py:78-85`), **stitched side by side into one picture** (`qwen_main.py:243-247`). | No guide process (none set for this id; inpaint only, `qwen_handler.py:72-101`). | — | ÷16. |
| Qwen-Image T2I (`qwen_image_20B`, `qwen_image_2512_20B`) | **None** (no `image_ref_choices`, `qwen_handler.py:54-70`). | No (inpaint `VA` only, `:56`). | — | ÷16. |
| Qwen-Image 2.1 7B / Turbo (`qwen_image_21_7B`, `_turbo_7B`) | `image_refs` `KI`/`I` (`models/qwen21/qwen21_handler.py:135`). | **Yes**: `PV`,`DV`,`SV`,`CV`,`V` "Control Image" (`qwen21_handler.py:130`). | **Yes**, guide inserted first; **at most 10 pictures in total, guide included** (`models/qwen21/pipeline.py:220-224`). | Categories up to 4096² (`qwen21_handler.py:84`); default budget applies to API. Turbo must run 8 steps (Hub facts, `schedulers.py:11-12`). |
| Flux 2 dev / **Flux 2 Klein 4B/9B** (`flux2_*`) | `image_refs` `KI`/`I` (`models/flux/flux_handler.py:187-195`); each encoded separately (`flux_main.py:368-371`); **≤1024² px each when more than one**, ≤2024² for one (`models/flux/flux2_adapter.py:116-119`). No count cap in code. | Declared: `PV` (pose extraction) and `MV` only (`flux_handler.py:220-222`). Raw `V` is **not declared**; no code found that refuses it (wgp filters only `guide_custom_choices`, `wgp.py:1229-1232`) — **inference**: a raw layout would go through as picture 1. | **Yes**: guide prepended (`flux_main.py:328-329`). | latent grid ÷16 (`flux_main.py:331`). Klein default 4 steps, guidance 1 (`flux_handler.py:429-438`). |
| Flux 1 Kontext / DreamOmni2 / UMO / USO | Kontext: refs **stitched into one** (`flux_main.py:416-421`); USO: 1 ref + ≤2 style (`flux_handler.py:175-185`). | No guide process; a guide is used only when there are no refs (`flux_main.py:422-423`). | No. | — |
| **Z-Image Turbo** (`z_image`, TwinFlow) | **None**: the reference choice is commented out (`models/z_image/z_image_handler.py:56-61`). | No (plain `z_image`). | — | default 1024² (`defaults/z_image.json`). |
| Z-Image Fun ControlNet-Union (`z_image_control`, `_control2`, `_control2_1`) | **None** (same). | **Yes, a real ControlNet**: `PV`,`DV`,`EV`, or `V` "Use Z-Image Raw Format" (`z_image_handler.py:32-44`); weight `control_net_weight` (`:38-39`, default 0.75 `:190-193`). | No refs to combine: layout + words only. | `z_image_control2_1` default 1920×1088 (`defaults/z_image_control2_1.json`). |
| **Krea 2 Turbo / Raw Identity Edit** (`krea2_turbo_edit`, `krea2_raw_edit`) | `image_refs` `KI`/`I` (`models/krea2/krea2_handler.py:96-104`); **at most 2** (1 in inpaint mode) (`:237-240`). | A "Control Image" `V` (hidden choice, `:49-55`); it is prepended as reference 1 (`krea2_main.py:814-815`, help text `krea2_handler.py:90`). Not a pose ControlNet. | **Yes**, but control + ≤2 refs = 3 pictures. | Budget 2048×2048 (`krea2_handler.py:73-74`); sides ÷16 (`krea2_main.py:306-309`, compression 8 × patch 2). |
| Krea 2 T2I (`krea2_turbo`, `krea2_raw`) | None (edit-only choice, `:87`). | Control image for inpainting only. | — | same. |
| HiDream O1 (`hidream_o1*`) | `image_refs` `KI`/`I` (`models/hidream/hidream_handler.py:50-58`). | **Yes**: `V`,`PV`,`DV`,`EV` (`:46-48`). | **Yes** (`hidream_main.py:231-238`). | `vae_block_size` 32 (`hidream_handler.py:41`). |
| SenseNova U1, Ming-Image design | refs `KI`/`I` (`models/sensenova_u1/sensenova_u1_handler.py:87-96`; `models/ming_image/ming_handler.py:219`). | No `guide_preprocessing` found. | — | — |
| Model 1 and Model 2 (two of the image-edit model files) | **Not in the engine** (no match for either file's name in `defaults/`, `finetunes/`, `models/`). The Hub sets a loose weight file up like an engine model by tensor fit or by name (`hub hub/core/autoreg.py:1-9`; pointer holds the architecture only, `hub hub/worker/adapters/pointers.py:8-10`). Which base each is set up as is in the cached catalog, not in code. **Inference** (outside knowledge, not code): both are Qwen-Image-Edit-2509/2511 derivatives, so would be set up as `qwen_image_edit_plus*_20B` and inherit that row. | | | |
| Model 3 (a quantized Krea 2 edit file, gguf) | Set up by name like `krea2_turbo_edit` — **inference** from the name rule; the cached catalog decides. | | | |

**PV on a stick-figure picture**: `P` runs the pose detector on the guide (`wgp.py:4893` → `pose`), the same trap R48
§7 records for the control video; the layout is already a pose drawing, so the letter is `V` (raw) on every family that
declares it. **Inference**: on Flux 2, whose only declared process is `PV`, the detector would be run on a drawing.

### A — conclusion
- **Can draw a sketch from {layout of stick figures} + {set plate} + {up to 3 sheet frames} in one job:** the
  **Qwen-Image Edit Plus family** (and so Model 1 / Model 2 **if** the cached catalog sets them up as
  `qwen_image_edit_plus*`), and **Qwen-Image 2.1** (≤10 pictures, guide counted). Both declare a raw control image
  `V` and take any number of separate references (`qwen_handler.py:103-107`, `qwen_main.py:231-232`;
  `qwen21_handler.py:130`, `qwen21/pipeline.py:220-224`). Flux 2 Klein takes the same five pictures mechanically, but
  raw `V` is not one of its declared choices (inference above). HiDream O1 also can (not in the model folders).
- **Cannot** (as §19.3 needs it): Krea 2 edit (control + at most 2 references: layout + plate + 1 sheet,
  `krea2_handler.py:237-240`); Z-Image Turbo (no references, no guide); Z-Image Control (layout, no references);
  Qwen-Image T2I (nothing).
- **What the Hub must send** (Qwen Edit Plus / Qwen 2.1; keys from the code above, the payload is **inference**):
  `image_mode` 1; `image_guide` = the control frame PNG (stick figures, no labels, drawn on the panel canvas);
  `video_prompt_type` = `V` + `KI` (plate as main scene) or `V` + `I`; `image_refs` = [plate, sheet 1, sheet 2,
  sheet 3]; `resolution` = the panel canvas. The engine numbers them **Picture 1 = layout, Picture 2 = plate,
  Picture 3-5 = sheets** (prepend, above), so the prompt's words must name them in that order. None of this path exists
  in the Hub today (`tasks.py:86-109` sends no `image_guide`, no `V`, never `KI`; the Hub caps a Qwen Edit Plus at 3
  references, `models.py:28`).
- **Fallback when the configured model takes no pose image** (Krea 2, Z-Image Turbo, Qwen T2I): (1) on Krea 2 edit, the
  layout composited onto the plate as **one** reference (the Hub draws the figures over the plate) + 1 sheet, or the
  layout as its control image + plate + 1 sheet — two characters cannot both be shown by sheet; (2) on a model with no
  references, the layout as words ("Character 1 screen right, close, facing left") as §19.7 says. Whether a composite reads as
  layout to the model is quality (the runs on the server). **Inference**.

## B. Route 1 on MiniMax H3: references + control video + kept sound in one generation?

**No** — no model definition in the engine combines Ref2VA identity pictures with the ControlNet-Union branch.

The code path:
1. The ControlNet model is **FL2VA, not Ref2VA**. `minimax_h3_control(_pruned)` takes its model definition from FL2VA
   (`upstream models/minimax_h3/minimax_h3_handler.py:528-530`), its weights are FL2VA's (`defaults/minimax_h3_control_pruned.json`
   `"URLs": "minimax_h3_fl2va_pruned"` + the rank-8 module in `"modules"`; full: `"minimax_h3_fl2va"`), and it is loaded
   with `reference_mode` False (`minimax_h3_handler.py:1129`: only Ref2VA, TTS and Viggle are reference mode).
2. The FL2VA pipeline refuses references: `if not self.reference_mode and (input_ref_images or …): raise
   ValueError("Image, video, and audio references require the Ref2VA checkpoint")` (`pipeline.py:967-968`). The control
   definition offers no reference choice (FL2VA has none, `minimax_h3_handler.py:790-836`; its frame-injection choice is
   removed for control, `:532-533`).
3. Its letters: `guide_preprocessing` `PV`,`DV`,`EV`,`SV`,`CV`,`V` ("Use Control Video as is"),`MV` (`:548-552`); sound
   `A` (kept `audio_guide`) or `K` (the control video's track) (`:556`, meaning `:66`). So control **V + kept A** in one
   job is legal; identities are not.
4. Ref2VA has **no ControlNet**: its pose/depth/edge choices are commented out, "superseded by the FL2VA ControlNet-Union
   model" (`:744-746`); the Ref2VA definitions list no control module (`defaults/minimax_h3_ref2va*.json`), and the
   ControlNet rows run only when the transformer has control layers from a module file
   (`minimax_h3_main.py:164`, `pipeline.py:831`). Engine help says the same: "Use Reference Video for motion transfer to
   image-reference characters; for depth, pose or edge control use the MiniMax H3 FL2VA ControlNet-Union model"
   (`minimax_h3_handler.py:111`).
5. **Unknown / not offered** (inference): a hand-written finetune with `architecture: minimax_h3_ref2va_pruned` plus the
   control module in `modules` would load control layers (`minimax_h3_main.py:164` reads any module file) in reference
   mode; nothing upstream defines, documents or tests it, the branch was trained on FL2VA (`:196`), and Ref2VA's
   choices have no plain `V`. Not a route.

**Single-pass alternatives the code does allow** (each lacks something §17.4 wants):
- **FL2VA ControlNet + start frame**: `image_start` / `image_end` combine with the control video (`:224`; FL2VA's
  `image_prompt_types_allowed` "TSEVL", `:798`, not removed for control, `:532-533`) with `V` + `A`. Identity only from
  a first frame (e.g. a panel drawn with the sheets), no reference pictures; "the control model was trained without
  such anchors, so keep them consistent with the control video" (`:224`).
- **Viggle-Animate** (`viggle_animate`, Ref2VA-pruned based, `:494-526`): control video `VU` + **exactly one** edited
  frame as `image_refs` (`one_image_ref_needed`, `:515`; `wgp.py:1406-1409`) + `A` custom audio kept
  (`:519-525`, `:978`) in one job. Limits: windows fixed at 124 frames (`:508-509`, refused above, `:871-872`); the
  prompt is ignored (fixed prompt, `models/minimax_h3/viggle.py:32`, `defaults/viggle_animate.json`); "Lip-sync, interacting
  characters and shots with cuts remain challenging" (`models/minimax_h3/viggle.py:34`); the edited frame must be a
  frame of that control video (`viggle.py:16-21`). The Hub marks it `why_not` (`upstream.facts.json:204-206`).

**Route 2 is possible** (blueprint §17.5):
- Pass 1 (previz) on `minimax_h3_control(_pruned)`: `video_guide` = control clip, `video_prompt_type` `V`
  (not `PV`), `audio_prompt_type` `A` + `audio_guide` = the shot's slice; one phase only (`pipeline.py:901-902` raises
  for two phases; guidance 1, `:234`); windows ≤ 362 frames (`:546`); lengths ≥ 107 and 17n+5 (`:581-583`); output at
  the control video's aspect (`:196`; `wgp.py:8038-8040`); overlap default 18 (`:1258`, `constants.py:8` False).
- Pass 2 on Ref2VA: `video_prompt_type` `V-U` (+ `I` or `KI`) with `video_guide` = the previz window, `image_refs` =
  plate + sheets, `audio_prompt_type` `AS` + `audio_guide` = the slice (choices `:739-752`, `:769-781`). Constraints:
  reference video ≥ 2 s (`:999-1000`); only its first 362 frames (15 s) kept (`:757`, `:1004`, `:1014-1015`); 17n+5
  frames after preprocessing (`pipeline.py:632-633`); resized within 768×1344 (`:758`); "given whole to every sliding
  window" (`:111`); ≤ 9 images (`:985-986`), ≤ 3 videos (`:987-988`), ≤ 12 files (`:1065-1067`); a kept soundtrack
  (`S`) is not an audio reference (`:978-979`). The Hub already sends `V-U` and `AS` (`upstream.facts.json:182-197`).
- Variant 2b (code allows, behaviour unknown): Ref2VA `VU` "In-Context Guide" instead of `V-U`: the control video is cut
  per window (`pipeline.py:1013`) and shown as a reference video before the target, not frame-aligned
  (`H3_ALIGNED_CONTROL_VIDEO = False`, `pipeline.py:47-50`); "Without such a LoRA, it behaves like a Reference Video that
  follows the control video section by section" (`minimax_h3_handler.py:154`). Combines with `I` refs and `AS` (no
  validation against it, `:958-1068`).

## C. Limits that bear on §19 / §17 as written

1. **Picture order** (§15.1, §17.4 say the plate is `<Picture 1>`; §15.5b says the layout goes first): on every
   family that takes a guide, the guide is always picture 1 and `image_refs` follow (§0 citations). In a sketch job with
   a layout the plate is Picture 2. On H3 Ref2VA (no image guide) the plate stays `<Picture 1>`.
2. **Reference counts**: Krea 2 edit ≤ 2 references (`krea2_handler.py:237-240`) — layout + plate + 3 sheets impossible;
   Qwen 2.1 ≤ 10 including the guide (`qwen21/pipeline.py:223-224`); H3 Ref2VA ≤ 9 images, ≤ 12 files
   (`minimax_h3_handler.py:985-986`, `:1065-1067`). Hub-side (not engine): picture models capped by `ref_caps`
   (default 3, Qwen 2.1 6, Krea 2 2; `hub settings.py:46`, `models.py:28`); a clip takes at most `cast.BOXES` = 3
   pictures (`hub hub/modules/generate_image/cast.py:21`, `models.py:234-235`), so plate + 3 in-frame sheets (§17.4)
   does not fit the Hub's bar today.
3. **No reference + control on one H3 pass** (B): §17.5 route 1 is not available as written; route 2 stands.
4. **Frame lattice** (§17.6, §19.1): H3 lengths ≥ 107 frames (4.46 s at 24 fps, `:577`, `:581`) and 17n+5
   (`:581-583`); a shot shorter than 107 frames still renders 107 (inference: trimmed at the join). Control windows
   ≤ 362 (`:546`); Ref2VA/FL2VA windows 124-481 (`:719`, `:796`). A `V-U` previz reference is capped at 362 frames and
   given whole to every window (`:757`, `:111`), so a shot longer than one window needs its own previz slice per window
   (inference).
5. **Canvas aspect for 4:3** (§18.1): H3 block 32 (`:584-585`); the Hub's H3 "4:3" tiers are 640×480 (exact) and
   736×544 (1.353, not 4:3) (`hub upstream.facts.json:39-45`, `:76-79`). The sketch size 448×336 is exact 4:3 but not
   a multiple of 32 in height (336 = 10.5×32): fine for Qwen/Flux2/Krea2 (÷16), refused-or-floored on HiDream (32) —
   the Hub floors to the model's block (`hub build.py:272-274`). With a layout image, the panel's size follows the
   layout's aspect (`wgp.py:8038-8040`), so a control frame drawn on a 736×544 canvas yields a 1.353 panel, not
   448×336 (inference). One canvas per script (§18.1) should be one of H3's exact-4:3 sizes (640×480) or the
   layout must be drawn at the sketch aspect.
6. **Control output aspect**: H3 control output takes the control video's aspect (`:196`); `V-U` reference videos keep
   the chosen output size (`:111`). Both consistent with §18.1's one canvas.
7. **Previz anchors**: a start/end frame on the control path must match the control video (`:224`), as R48 §7 records.

## D. What only the server can tell
- Which image weights the model folders hold and what the Hub set each loose file up as (Models 1-3,
  the image-edit model files of §A): the Generate pulldown / catalog. Whether Model 2 (a merged checkpoint) loads at all
  (HANDOFF "Not verified" 1).
- Whether a Qwen Edit Plus / Model 1 edit follows a raw stick-figure layout (`V`) together with a plate and three sheets
  — quality, the first Step 12 run on the server; also how long it takes and its VRAM at 448×336 with five pictures.
- Whether the model folders hold Qwen-Image 2.1, Z-Image Control or Flux 2 Klein weights (catalog `status`).
- H3: whether the control module (`MiniMax-H3-Fun-Control-Union-2.0-pruned_rank8_*`) and its FL2VA-pruned base are on
  the disk (blueprint §9.1); whether H3 renders stick figures as bodies and keeps mouths in sync on `V` + `A` (§9.2);
  whether a `V-U` previz holds camera and layout on Ref2VA (§9.4); VRAM and time per 362-frame window on the server's card.

## What could not be read
- Models 1 and 2: not in the engine; their base is decided by the Hub's tensor fit on the
  files, which needs the files.
- The live catalog on the server (which entries are `available`); the contract fixture `tests/fixtures/contract/upstream-18.05/engine.json`
  lists definitions, not the weights.
- Families not read in depth: chrono_edit, kiwi_edit, hunyuan_custom_edit, lucy_edit, ltx2 edit (video editors),
  ideogram4, kandinsky 5/6, prism.
