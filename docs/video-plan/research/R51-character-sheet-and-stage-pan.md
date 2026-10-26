# R51: the character sheet and the stage pan, from an H3 ComfyUI workflow

Research note, 2026-10-20. Facts only, each with its source; inference is marked **[inference]**. Serves blueprint
§13 (Casting), §14 (the stage), §16 (the house), §17 (control), §18 (format) and PLAN.md Steps 10-12.

## 0. Sources and what could be read

Repository: `https://huggingface.co/PoopMan333/H3_Character_Sheet_Generator` (13 commits, 1 contributor, latest
commit "Update README.md" ccc9d41; tree listing read 2026-10-20). Root files: `.gitattributes` (2.72 kB),
`H3_CharSheetMaker_4_Panel_(Faster).json` (45 kB), `H3_CharSheetMaker_6_Panel.json` (49.3 kB), `README.md`
(7.89 kB); folders `B prompts/`, `early_version/` (`H3_CharSheet_Maker.json`, 40.5 kB), `examples/` (12 files:
sheets as PNG, `[Character 2] A2R - Spin Video.mp4`). Note: the README names the 4-panel file
`H3_CharSheetMaker_4_Panel__Faster_.json`, but the repo holds `H3_CharSheetMaker_4_Panel_(Faster).json`.

| Source (URL) | How read | Status |
|---|---|---|
| U1 repo page `…/H3_Character_Sheet_Generator` | WebFetch | **Summarized** by the fetcher (it refused a verbatim copy) |
| U2 `…/tree/main`, `…/tree/main/B%20prompts`, `…/tree/main/examples`, `…/tree/main/early_version` | WebFetch | Listings read (names, sizes, links) |
| U3 `…/blob/main/README.md` | WebFetch, keyword lines | **Verbatim lines**; lines over 125 characters excerpted with "…" by the fetcher |
| U4 `…/raw/main/B%20prompts/Standard%20Orbit%20-%206%20panel.txt` | WebFetch, sentence by sentence, long sentences in ≤100-character segments | **Verbatim**, reassembled from quoted segments; paragraph breaks known, line breaks inside a paragraph not certain |
| U5 `…/raw/main/B%20prompts/Standard%20Orbit%20-%204%20panel.txt` | WebFetch, sentence by sentence | **Verbatim**, reassembled |
| U6 `…/blob/main/H3_CharSheetMaker_4_Panel_(Faster).json` and `…/raw/main/H3_CharSheetMaker_4_Panel_(Faster).json` | WebFetch | Node table **summarized** by the fetcher (ids, types, titles, widget values given as values); prompt strings and notes **verbatim** in ≤100-character segments with `\n` shown |
| U7 `…/H3_CharSheetMaker_6_Panel.json` | WebFetch on `/blob/main/`, `/resolve/main/`, `/resolve/main/…?download=true` | **NOT READ**: each returned "There was an error while fetching"; `/raw/main/` was refused (not in the fetcher's allowed set) |
| `B prompts/Anime2Real - 4 panel.txt`, `Anime2Real - 6 panel.txt`, `early_version/H3_CharSheet_Maker.json` | — | Not read (not needed for R51) |
| `examples/*.png`, `[Character 2] A2R - Spin Video.mp4` | WebFetch | **NOT READ**: refused (not in the fetcher's allowed set). No sheet image was seen. |
| Direct download (`curl`) of any huggingface.co URL | Bash | **Blocked**: the session's egress proxy refuses huggingface.co (403) |

Caveat for every "verbatim" below: the text passed through WebFetch's model, which returned it as quotes. It was not
byte-compared with the files. The 6-panel workflow's node values (frame indices, size, steps, LoRA) are therefore
**unknown**; everything given for "the workflow's settings" is from the 4-panel JSON unless said otherwise.

## 1. The prompts

### 1.1 The A prompt (the per-picture keep/ignore lines)

README (U3), section "Writing the A Prompt", verbatim example:

```
<Picture 1> - keep the photo style. Use the bald head, facial hair, physique.
<Picture 2> - keep only the black outfit. Remove the hair, remove accessories.
<Picture 3> - use the shield. It is attached to the man's back.
```

Rules from the README (U3) and the README copy embedded in the 4-panel JSON (node 142 MarkdownNote,
"README — H3 Character Sheet Maker"), verbatim lines:
- "2. **Fill in `Input Text (Prompt)`** — one line per image saying what to take and what to ignore." (node 142)
- "1. **Load your references.** Any mix of photos, drawings or anime art." / "The first one sets the style." (node 142)
- "wardrobe drifts. "Black high-collared coat with silver buckles" sticks. "The coat from Picture 2"" (U3, one wrapped
  line; the sentence around it was not quoted in full)
- "**Give it a back view if you have one.** With only front-facing references" / "the entire back of your" /
  "character is invented." (node 142)
- "stages: run once to get a clean front view, then feed *that* render back in as" / "`<Picture 1>` and build the sheet
  from it." / "A purpose-made reference beats a pile of contradictory ones." (node 142)

The A prompt actually saved in the 4-panel workflow (U6, node 138 `PrimitiveStringMultiline`, title
"Input Text (Prompt)", `widgets_values[0]`), verbatim (`\n` are newlines). It does **not** use the README's
one-line-per-picture form; it uses two labelled fields:

The saved prompt is now empty: node 138 holds `""` in `widgets_values[0]` and `widgets_values_named.value`.

How A and B become one prompt (U6): node 236 `StringConcatenate` ("Combine Strings"), `string_a` ← node 138 (A),
`string_b` ← node 239 (B), `delimiter` "" (empty); its output feeds node 136's `prompt`. So the model's prompt is A
followed directly by B (A ends in `\n`).

### 1.2 The B prompt, 6-panel (the orbit instruction)

File `B prompts/Standard Orbit - 6 panel.txt` (U4), verbatim, reassembled from the quoted sentences and segments.
Blank lines are the file's paragraph breaks; the README says this B prompt is fixed ("The six grab points are locked
to the beat timings in the fixed prompt.", node 142). Whether the 6-panel JSON's own B node holds exactly this text
was not read (U7).

```
[STYLE]
The output is matches the style of <Picture 1>. Sharp detail on eyes and face. The style never changes and never drifts between shots. No shadows.

[STAGING]
Solid light grey seamless backdrop, one flat uniform tone edge to edge, with no gradient, no vignette, no texture and no floor line. Nothing else is in frame. the subject casts no shadow onto the backdrop and no contact shadow on the ground beneath it, and it does not sit in its own shadow. Soft form shading on the subject itself is fine and should read its shape. Long telephoto lens, near-orthographic.

The character holds one relaxed A-pose throughout: arms hanging slightly away from the body, palms toward the thighs, feet shoulder-width apart, head level, calm neutral expression, eyes open and looking forward. The subject is completely frozen, as rigid and motionless as a statue. Only the camera moves. Hair, fabric, cloaks, skirts, sleeves, straps, ribbons, chains, tassels, fur and feathers are all locked solid: every strand and every fold sits in exactly the same position in every frame. There is no wind, no breeze, no air movement, no breathing, no settling, no sway, no secondary motion of any kind. Orientation, surfaces and lighting are identical in every shot, and the subject stays the same size in frame.

[0-3 seconds] tight full shot of the subject. The camera makes one smooth fixed-speed orbit right around it, a full 360 degrees: starting square on the front, passing the left side a quarter of the way round, directly behind at halfway, the right side three quarters of the way round, and returning to the front. The subject does not move at all. Ends back on the front view at 3 seconds.

[3-4 seconds] Camera snaps into a fast push-in on the character's face. Locked-off head and shoulders close-up, face square to camera, eyes into the lens. Ends on a sharp front-on face.

[4-5 seconds] camera whip-pans and rotates to a orthogonal angle. Locked-off head and shoulders close-up, head turned to a three-quarter angle, eyes still forward. Ends on a clean three-quarter face.

[CAMERA] One constant-speed orbit in beat 1, then locked off and static. The camera is the only thing in the scene that moves at any point. No zoom, no push in, no dolly, no tilt, no roll, no handheld shake, no motion blur, no dissolves.
[AUDIO] Silence. No music, no room tone, no voices.
```

### 1.3 The B prompt, 4-panel

Saved in the 4-panel workflow (U6, node 239 `PrimitiveStringMultiline`, title "Prompt for orbiting - (Keep Picture
1's Style)", mode 0), verbatim with its exact newlines:

```
[STYLE]
The output is matches the style of <Picture 1>. Sharp detail on eyes and face. The style never changes and never drifts between shots. No shadows.


[STAGING]
Solid light grey seamless backdrop, one flat uniform tone edge to edge, with no gradient, no vignette, no texture and no floor line. Nothing else is in frame. the subject casts no shadow onto the backdrop and no contact shadow on the ground beneath it, and it does not sit in its own shadow. Soft form shading on the subject itself is fine and should read its shape. Long telephoto lens, near-orthographic.

The character holds one relaxed A-pose throughout: arms hanging slightly away from the body, palms toward the thighs, feet shoulder-width apart, head level, calm neutral expression, eyes open and looking forward.
The subject is completely frozen, as rigid and motionless as a statue. Only the camera moves. There is no wind, no breeze, no air movement, no breathing, no settling, no sway, no secondary motion of any kind. Orientation, surfaces and lighting are identical in every shot, and the subject stays the same size in frame.

[0-2 seconds] tight full shot of the subject. The camera makes one smooth fixed-speed orbit to the left around it, sweeping 180 degrees: starting square on the back, passing the left side a third of the way through this move, and ending square on the front at 2 seconds. The subject does not move at all. Ends on the back view at 2 seconds.

[2-3 seconds] Camera whip-pans front and snaps into a fast push-in on the character's upper body. Locked-off head and shoulders close-up, face square to camera, eyes into the lens. Ends on a sharp front-on face at 3 seconds.

[CAMERA] One constant-speed 180-degree orbit in beat 1, then a hard whip-pan back to front and a push-in for beat 2. No zoom, no dolly, no tilt, no roll, no handheld shake, no motion blur, no dissolves beyond the one whip-pan cut.
[AUDIO] Silence. No music, no room tone, no voices.
```

Differences between the sources:
- The file `Standard Orbit - 4 panel.txt` (U5) has one more sentence after "Only the camera moves.": "Hair, fabric,
  cloaks, skirts, sleeves, straps, ribbons, chains, tassels, fur and feathers are all locked solid: every strand and
  every fold sits in exactly the same position in every frame." Node 239 does not have it.
- The 4-panel text says both "ending square on the front at 2 seconds" and "Ends on the back view at 2 seconds." It is
  quoted as it stands.
- Neither B prompt is a cut-free orbit from start to end. The 6-panel one has a "fast push-in" at 3 s and a
  "whip-pans" at 4 s. The 4-panel one allows "the one whip-pan cut". "No hard cuts" (README) refers to the orbit beat.
- Node 252 (title "Prompt for orbiting - (Anime to Real)") is a second B prompt, bypassed (mode 4). It was not read
  verbatim.
- README (U3): "The B prompt says **"neutral A pose"** — delete that bit if you want a specific pose"; "**Works on
  objects and props too.** You'll want to tweak the B prompt, mainly swapping the face" (line cut there by the fetcher).

## 2. Generation settings (4-panel JSON, U6; the 6-panel JSON was not read)

| Setting | Value | Source (U6 node / field, or README line) |
|---|---|---|
| Diffusion model | `minimax_h3_ref2va_pruned_int8_convrot.safetensors`, weight_dtype `default` | node 127 `UNETLoader` |
| Text encoder | `qwen3vl_32b_minimax_h3_int8_convrot.safetensors`, type `minimax`, device `default` | node 128 `CLIPLoader` |
| Video VAE | `minimax_h3_video_vae_int8_convrot.safetensors` | node 119 `VAELoader` |
| Audio VAE | `minimax_h3_audio_vae_fp32.safetensors` | node 120 `VAELoader` |
| Model folders (README) | `models/diffusion_models/`, `models/text_encoders/`, `models/vae/`, `models/loras/` | U3 Models table |
| Model Links note | names other files (`minimax_h3_video_vae_fp16.safetensors`, `qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors`) than the loaders use | node 117 (**fetcher's summary**, not verbatim) |
| Generation node | `MiniMaxH3ReferenceToVideo`: prompt ← node 236; width `768`, height `1344` (widgets, overridden by links); length `73` (no link); ref_image_size `max` | node 136 |
| Size | `ResolutionSelector` "IMAGE SIZE (pick ratio + megapixels)": `"9:16 (Portrait Widescreen)"`, `0.4`, `32`; outputs width → node 136 slot 11, height → slot 12 | node 115 |
| Size table | 16:9 rows only, multiple 32: 0.2 → 608 x 352; 0.3 → 736 x 416; **0.4 → 864 x 480**; 0.5 → 960 x 544; 0.6 → 1056 x 608; 0.7 → 1152 x 640; 0.8 → 1216 x 672; 0.9 → 1280 x 736; 0.98 → 1344 x 768; 1.0 → 1376 x 768; 1.2 → 1504 x 832; 1.5 → 1664 x 928; 1.8 → 1824 x 1024; 2.0 → 1920 x 1088 | node 140 MarkdownNote, verbatim rows |
| Resulting canvas | 9:16 at 0.4 MP: **480 x 864 [inference]**, the table's 0.4 row transposed; the selector's output was not read | — |
| Frames | 4-panel: `73` (node 136 length). 6-panel: 124 (README: "You're generating 124 frames to use 6."; node 142: "**Duration — leave at 5.** That's 124 frames.") | node 136; U3; node 142 |
| Legal lengths (author's words) | "Valid lengths are `17n + 5`: 5, 22, 39, 56, 73, 90," / "107, 124. Anything else rounds up." | node 142, verbatim |
| Speed limit (author's words) | "Go much shorter and the spin outruns the model — it smears past about 5° per frame." | node 142, verbatim |
| fps | `24` (bit depth `8`, `sRGB`); `audio` input unlinked | node 130 `CreateVideo` |
| Sampler | `euler` | node 123 `KSamplerSelect` |
| Scheduler, steps, denoise | `linear_quadratic`, `8`, `1` | node 124 `BasicScheduler` |
| Steps note | "IF YOU ARE using the latest speed ups from 26 Aug." / "8 Steps - Latest Scheduler with Turbo LORA" / "20-25 Steps - WITHOUT any speed ups" | node 964 Note "<<<< STEPS", verbatim |
| CFG / guidance | none: `BasicGuider` (model + positive conditioning only; no CFG widget) | node 126 |
| Negative prompt | none: no negative conditioning is wired; node 136 outputs `positive` → 126 and `LATENT` → 125 | nodes 125, 126, 136 links |
| Seed | `1039518910366181`, control `randomize` | node 129 `RandomNoise` |
| Sampling node | `SamplerCustomAdvanced`: noise ← 129, guider ← 126, sampler ← 123, sigmas ← 124, latent_image ← 136 slot 1; output → `VAEDecode` 122 | node 125 |
| Turbo LoRA | `minimax_h3_ref2v_turbo_4step_v0.1_comfyui_bf16.safetensors`, strength `1` | node 956 `LoraLoaderModelOnly` "5. Turbo LoRA", inside subgraph "Speed Ups ( Updated 26 Aug 2026)" |
| Sigma shift | shift_video `8`, shift_audio `3` | node 958 `MiniMaxH3SigmaShift` |
| Other speed patches (active) | `H3SLAAttention` sparsity_ratio 0.9, block_size "64", min_seq_len 4096, dense_last_steps 1, protect_audio true, enabled true, dense_steps "0", dense_backend comfy_kitchen, disable_fp16_accum true, stabilize_motion true, reference_protection false (959); `MiniMaxLowVRAMAttention` 4 (960); `ModelPatchTorchSettings` false (953); `MiniMaxChunkFeedForward` 2 / 4096 (954). `H3AdaLNLoRAFix` `port` bypassed (957). | subgraph nodes (fetcher's table) |
| Speed-stack note | "## Speed stack — matched to PlagueKind MiniMax-H3 V6"; "Sampler outside this subgraph: euler + **simple** + 8 steps (was beta). [PlagueKind] explicitly avoids EasyCache — it costs visible quality."; "Requires: ComfyUI-PlagueKind-Nodes, ComfyUI-KJNodes." | node 955, verbatim |
| Outputs | `SaveImage` "SAVE CHARACTER SHEET" prefix `charsheet/SHEET` (218); `SaveVideo` prefix `charsheet/SHEET`, auto/auto/auto (92); `SaveImage` "Save ALL frames (pick from the best if you wish)" prefix `charsheet/frames/f`, **bypassed** (141) | nodes 218, 92, 141 |

Contradictions inside the source, as found:
- The scheduler is `linear_quadratic` (node 124), but node 955 says "euler + **simple**".
- The embedded README says of the speed-up nodes: "Deliberately left out." / "Add them if you like." (node 142). The
  file holds an active speed-up subgraph dated 26 Aug 2026, so that text predates it.
- The README says the third-party nodes are KJNodes and rgthree (U3). Node 955 requires PlagueKind Nodes and KJNodes.
- README (U3): "**Speed-ups cost you something.** Turbo LoRAs and caching do make it faster, but prompt adherence and"
  (line cut there); "detail — the text encoder especially, that's where prompt adherence lives."; "- **More steps** =
  slightly better quality, if you're willing to wait"; "**Quality is limited.** It's a video model, it's better at
  video than stills. Crank the resolution and steps if" (cut).

Arithmetic (this note's): 124 frames at 24 fps is 5.17 s, and 73 frames is 3.04 s. The 6-panel orbit turns 360° in 3 s
(72 frames), which is 5.0° per frame, exactly the author's smear limit. The 4-panel orbit turns 180° in 2 s
(48 frames), 3.75° per frame.

## 3. Which frames become which panel, and the sheet

### 3.1 4-panel (read: U6, subgraph "Image Stitching", group "Character Sheet Assembly")

| Node | Title (verbatim) | `ImageFromBatch` batch_index, length | Time at 24 fps |
|---|---|---|---|
| 200 | "1 front (orbit 0%)" | `2`, `1` | 0.08 s |
| 201 | "2 left side (orbit 25%)" | `24`, `1` | 1.00 s |
| 203 | "4 right side (orbit 75%)" | `45`, `1` | 1.88 s |
| 204 | "5 face front (beat 2)" | `68`, `1` | 2.83 s |

The subgraph input is VAEDecode 122's IMAGE (via subgraph node 238). Its output goes to SaveImage 218.

Stitching (verbatim settings):

| Node | Title | image1 / image2 | direction, match_image_size, spacing_width, spacing_color |
|---|---|---|---|
| 210 | "Row 1: 1+2" | 200 / 201 | `right`, `true`, `6`, `black` |
| 213 | "Row 2: 4+5" | 203 / 204 | `right`, `true`, `6`, `black` |
| 216 | "Stack rows" | 210 / 213 | `up`, `true`, `6`, `black` |

So the 4-panel sheet is 2 x 2 with 6 px black gutters. **[inference]** In ComfyUI's `ImageStitch`, direction is where
image2 goes relative to image1, so `up` puts row 2 (203|204) above row 1 (200|201). This was not checked against an
example image.

How the indices relate to the 4-panel prompt **[inference]**: the node titles and numbering (1, 2, 4, 5) are the
6-panel's labels. Against node 239's timing (back at 0 s, a 180° orbit to the front at 2 s = frame 48, then the face
beat over frames 48-72), index 2 falls on the back view, 24 at the orbit's midpoint (a side), 45 near the front
(about 169°), and 68 on the face close-up. The README says how the indices were chosen and what to do when they are
wrong: "Frame timings shift between runs. If a panel looks off, turn on the "save all frames" output, find" / "a
better frame number and plug it into the subgraph. Re-stitching is cached, so it's instant" (U3).

### 3.2 6-panel (indices NOT read; U7 failed)

Views and layout, from the README copy in node 142 (verbatim):

| # | View | Source |
|---|---|---|
| 1 | Front | orbit 0% |
| 2 | Left side | orbit 25% |
| 3 | Back | orbit 50% |
| 4 | Right side | orbit 75% |
| 5 | Face, front | beat 2 |
| 6 | Face, three-quarter | beat 3 |

"Laid out 3 wide × 2 tall with thin black gutters." "**Retiming.** The six grab points are locked to the beat timings
in the fixed prompt." "If you change those times or the duration, open the subgraph and move the frame indexes" / "to
match, or the grabs will land mid-transition." README table (U3): "`H3_CharSheetMaker_6_Panel.json` | Front, both
sides, back, plus two face shots".

**[inference]** Indices implied by the 6-panel B prompt at 24 fps over 124 frames (0-123). The orbit runs over
frames 0-72: front about 2 (the 4-panel file starts at 2), left side 18, back 36, right side 54. The front face
(3-4 s, frames 72-96) settles near 90-95. The three-quarter face (4-5 s, frames 96-120) settles near 114-119. These
are a starting point to check against the 6-panel JSON, not its values.

Sheet size **[inference]**: each panel is the clip's canvas, assumed 480 x 864. The 4-panel sheet would then be
2·480+6 = 966 px wide and 2·864+6 = 1734 px tall. The 6-panel sheet would be 3·480+2·6 = 1452 px wide and 1734 px
tall, if it uses the same 6 px spacing. No sheet's real size was read.

**Conflict with the blueprint.** §13.1 names the angles "front 0°, right 90°, back 180°, left 270°". The workflow's
table puts the *left* side at 25% and the *right* side at 75%, as its B prompt says ("passing the left side a
quarter of the way round"). Which side a frame shows follows the B prompt's words, and the model's obedience to them.
The run on the server decides it.

## 4. How references are wired (4-panel, U6)

- Node 136 `MiniMaxH3ReferenceToVideo` inputs:
  - `ref_images.ref_image_0` ← LoadImage 137 (`example.png`, active)
  - `ref_image_1` ← LoadImage 251 (`Picture 2.jfif`, active)
  - `ref_image_2` ← LoadImage 253 (same file, **bypassed**, mode 4)
  - `ref_image_3`, `ref_video_0`, `ref_video_audio_0`, `ref_audio_0` are shown but unconnected
  - `clip` ← 128, `vae` ← 119, `audio_vae` ← 120
- The fetcher reports that only ref_image_0 to ref_image_3 are present, with no 4-9.
  **[inference]** The node grows a new slot as each one is connected. The README says "Turn up to **9 reference
  images** into a clean six-view character sheet" / "in a single generation." (node 142).
- Order: `ref_image_0` is `<Picture 1>`. The A prompt numbers from `<Picture 1>` (node 138), and the B prompt's
  style comes from `<Picture 1>` (node 239). README: "The first one sets the style." (node 142).
- `ref_image_size` is `max` (node 136).

## 5. Mapping to the Hub

Paths below are relative to the repository root. The fixture is the
capture of upstream 18.05: `tests/fixtures/contract/upstream-18.05/engine.json`, entry
`minimax_h3_ref2va_pruned` at :3237.

| Workflow setting | Hub today (file:line) | Has / lacks |
|---|---|---|
| Ref2VA model | `minimax_h3_ref2va_pruned` ("MiniMax H3 Ref2VA Pruned 20B") and `minimax_h3_ref2va_pruned_pdd` (8-step) in the catalog (fixture :3237; `hub/worker/adapters/upstream.facts.json:190-192`); picked in Generate's pulldown (CLAUDE.md) | Has. The ComfyUI `int8_convrot` files are ComfyUI's packaging. The Hub runs the engine's own weights; int8 or bf16 is the engine's server config `transformer_quantization` (R16 §3.1) |
| Text encoder | Card's encoder or the model's default (`build.py:195`; `tasks.py:180-190`) | Has (choice among the engine's variants) |
| Up to 9 references, box order | Engine cap 9 (`upstream.facts.json:192`; fixture :3274 `max 9`); sent as `image_refs` in box order with letter "I" (`tasks.py:162`; `upstream.py:205-214`) | Engine has it. **The UI lacks it**: `cast.BOXES = 3` (`modules/generate_image/cast.py:21`) caps the cap at 3 (`models.py:234-235`), so a headshot plus 8 bits cannot be sent from Generate |
| Picture shape | Each identity 1:4 to 4:1 (`cast.py:51-53`) | Has |
| `ref_image_size max` | No `image_refs_relative_size` is sent anywhere under `hub/` (grep), so the engine's default 100 applies (R16 §3.2: 50-400, default 100) | **Lacks** a way to ask for "max" detail |
| A + B prompt | The prompt is sent as typed, at most 4000 characters (`screen.py:28`; `build.py:86-88`). `multi_prompts_gen_type "FG"` is sent (`tasks.py:244`), which R16 §3.4 says a multi-paragraph prompt needs | Has. 2.4 kB of B plus the A lines fits. The Director's shot prompts already use `subject_definitions` / `retention_analysis` (`shotprompt.py:4-10`), the same labels as node 138 |
| Size 9:16, 0.4 MP | H3 tiers include 480p 9:16 = 480x864, 3:4 = 480x640, 4:3 = 640x480 (`upstream.facts.json:19-29`); a clip size must be a tier size (`build.py:178-179`); tiers offered per the `video_tiers` setting (`models.py:189-197`) | Has 480x864 if the 480p tier is offered |
| 124 frames | `124 = 17·7 + 5`. Lattice min 107, step 17, max 362, default 124 (fixture :3262-3267); `snap_frames` (`core/clipplan.py:36-42`) | **Has: legal as is.** It is also the Ref2VA default |
| 73 frames | `73 = 17·4 + 5`. Legal in ComfyUI ("Valid lengths … 5, 22, 39, 56, 73", node 142), but **below the Hub/upstream minimum 107** (R16 §3.3: "17k + 5 with k ≥ 6"; R48 §7: "at least 107"); `snap_frames` raises it to 107 (`clipplan.py:42`) | **Not available.** A Hub 4-panel orbit is at least 107 frames (4.46 s). Node 239's 2 s / 3 s beats would need retiming to it, or the indices re-picked. Blueprint §16.2 and PLAN Step 10.2b ("73 frames") do not hold on the Hub's engine |
| One window | Window sent = `max(frames, window_min)` (`tasks.py:243`); window_min 124, window_max 481 (fixture, same entry); R48 §7: 362 is the control window, 481 the non-control maximum | **Fits.** 124 runs as one window of 124. 107 runs in a window of 124. Both are ≤ 362 and ≤ 481. No continue, no join |
| fps 24 | fps 24 (fixture :3262) | Same |
| Steps 8 (turbo) / 20-25 | Default 20 for pruned (fixture :3257), set per press (`build.py:133-139`, `:189-191`); PDD variant locked at 8 (fixture `lock_steps: true`) | Has |
| Sampler euler, scheduler linear_quadratic | No `sample_solver` or scheduler key is sent (grep under `hub/`); R16 §3.4: solvers euler / res_multistep / ralston_2s, PDD forces euler | Lacks a choice; the engine's default applies |
| Sigma shift 8 / 3 | Nothing sent for upstream; only the fork adapter sends `flow_shift` (`worker/adapters/fork.py:77`) | Lacks. Whether the engine exposes an H3 shift was not checked |
| CFG none | Clip guidance is None (`build.py:212`; `models.py:232`); R16 §3.4: `guidance_scale` default 1.0, not sent | Same |
| Negative prompt none | Forced `negative_prompt ""` (`upstream.py:56`) | Same |
| Seed randomize | Random or fixed, 0 to 999,999,999 (`build.py:41-46`, `:193`; `screen.py:26`) | Has; "again" = a new seed |
| Turbo LoRA | Clip LoRAs sent as `activated_loras` / `loras_multipliers` (`build.py:192`; `tasks.py:75-77`, `:190`); catalog `loras: true` for Ref2VA pruned (fixture :3241) | Route has it. Whether the ComfyUI-format file `…_comfyui_bf16.safetensors` loads in the engine is **not known** |
| Speed stack (SLA, low-VRAM attention, chunk FF, AdaLN fix) | ComfyUI custom nodes | No Hub equivalent; not checked whether the engine has its own |
| Sound | Workflow: video saved without audio (node 130 `audio` unlinked), B prompt "[AUDIO] Silence.". Hub: H3 makes its joint sound (`upstream.py:58` `FORCED_VIDEO`; R16 §3.4) | The orbit MP4 carries the model's sound; harmless for a sheet |
| Frame extraction | Only the judges' ffmpeg decode: raw BGR scaled to `WIDTH = 640` (`worker/adapters/faces.py:34`, `:42-52`) | **Lacks** a full-size PNG of frame N from a clip |
| Stitching | None in the Hub | Not needed by §13.2, which stores separate PNGs (`sheet/{front,right,back,left,face-1,face-2}.png`). Showing the sheet is the screen's layout |
| Reference video (for §14.5) | `V-U`, at least 2 s, first 15 s kept (`worker/adapters/refvideo.py:7`, `:23`, `:35-45`) | Has. A 124- to 192-frame pan (5.2-8 s) is within it |

## 6. The stage pan by analogy (blueprint §14) **[inference throughout: the assistant's, not the workflow's]**

The workflow's method: one picture sets the style (`<Picture 1>`). A fixed B prompt freezes everything but the camera
("The subject is completely frozen…", "Only the camera moves."). The camera follows timed beats, and each grab sits
where a beat "Ends on" a clean view. Speed stays at or under about 5° per frame. A set has no "subject" to orbit, so
the analogy keeps the freeze, the timed beats and the holds, and swaps the orbit for the camera moves §14.1 names.

One difference from the blueprint's words: §14.1 asks for "a slow pan from stage left to stage right". A pan turns
the camera on one spot, so it shows one viewpoint at different angles. Zettl's left, centre and right camera
*positions* (§11.5) are three places. To get them in one clip, the camera has to truck or arc between them. The
proposal arcs. Which one is a planner's call.

Proposed A prompt (one line per picture, as the README teaches):

```
<Picture 1> - the stage. Keep the set, the furniture, the colours and the lighting exactly. Remove all people.
```

Proposed B prompt, 175 frames (17·10+5, 7.29 s at 24 fps; one window, ≤ 362):

```
[STYLE]
The output matches the style of <Picture 1>. The style never changes and never drifts between shots.

[SET]
The stage set shown in <Picture 1>, empty: no people anywhere, on the stage or in the audience seats. Every piece of furniture, prop, light and wall stays exactly where <Picture 1> shows it; nothing is added, removed or moved. The set is completely frozen. Only the camera moves. Lighting is identical in every shot. No flicker, no moving lights, no screens changing.

[0-1 seconds] Locked-off wide establishing shot from the centre of the audience, the whole stage in frame. Ends on the wide.
[1-2 seconds] The camera arcs smoothly to the camera-left position, aimed at stage centre, medium-wide. Ends locked off on the left view.
[2-3 seconds] The camera arcs smoothly to the centre position, medium-wide. Ends locked off on the centre view.
[3-4 seconds] The camera arcs smoothly to the camera-right position, medium-wide. Ends locked off on the right view.
[4-6 seconds] The camera pans smoothly at constant speed through 180 degrees on its pedestal, from the stage to the audience seats.
[6-7 seconds] Locked-off wide of the empty audience seats. Ends on the seats.

[CAMERA] Smooth constant-speed moves joined by holds. No cuts, no whip-pans, no zoom, no tilt, no roll, no handheld shake, no motion blur, no dissolves.
[AUDIO] Silence. No music, no room tone, no voices.
```

Proposed plate indices (24 fps, 175 frames, indices 0-174): each one taken late in its hold, so it does not land
mid-transition (README "Retiming"):

| Plate | Beat | Frame index |
|---|---|---|
| `wide` | 0-1 s | 20 |
| `left` | 1-2 s | 44 |
| `centre` | 2-3 s | 68 |
| `right` | 3-4 s | 92 |
| `audience` | 6-7 s | 166 |

The 180° turn over 48 frames is 3.75° per frame, the same rate as the 4-panel orbit. The README's warning applies:
"Frame timings shift between runs". The Hub should keep every frame of the pan, which it does by keeping the MP4
(§14.2), and let an index be re-picked on screen.

For `audience: "seen"` (§16.1), the house plates `{wide, left, right, row}` would come from a second pan by the same
method. It would run from the house wide to house-left and house-right, then a slow push-in to two or three rows
(`row`), from the era words of `house: {era, dress, hair, size}` in place of "empty". A third beat on the first pan
would push it past one window's comfortable length. That is untested.

## 7. What only the run on the server can decide

1. Time per orbit on the server's GPU: 124 frames at 480x864 (or the script's aspect) at 20 steps, and at 8 steps with a turbo LoRA or
   the PDD variant, as the Hub drives it (no ComfyUI speed stack).
2. Quantization: the engine's `transformer_quantization` and text-encoder quantization (int8 or bf16). The workflow
   ran int8 ComfyUI files throughout. Whether the Wan2GP weights of the model folders are the same is not known.
3. Quality on the installed engine without the workflow's sigma shift (8/3), its `linear_quadratic` scheduler and its SLA patch:
   whether the orbit holds identity and the "statue" freeze.
4. Whether the ComfyUI turbo LoRA file loads in the engine at all, and what it costs in prompt adherence (the README
   says speed-ups do).
5. The real frame indices of the runs on the server, for both sheets and the pan: "Frame timings shift between runs" (U3).
6. Whether a 107-frame retimed 4-panel orbit gives a usable extra's sheet, since 73 is not available on the Hub's
   engine.
7. Whether the engine's default reference detail (100) is enough, or the workflow's `max` is needed.
8. Which side a "25%" frame shows on the configured model (left, per the B prompt, against §13.1's "right 90°").
9. The sheet's aspect: the workflow uses 9:16 portrait for a standing figure, while §18 makes the script 4:3. The
   tiers offer 3:4 (480x640) and 4:3 (640x480). Whether a sheet's aspect follows the script is a planner's call.
10. Whether one picture of the stage holds a 180° set and a turn onto the house in one pan (§15.5 already lists it).
11. VRAM with 9 references at 124-192 frames.
12. Licence: the README notes that the MiniMax H3 community licence restricts some regions and covers outputs as well
    as weights (U1, **summarized**). It is the Hub's own use (§15.5).

## Addendum 2026-10-20: three workflow files (read in full, not estimated)
Three workflow files were attached; they are kept beside this note in `R51-workflows/`
(`H3_CharSheetMaker_6_Panel_10Sept.json` is the "Updated 10 Sept" version). From the 6-panel file, verbatim:
- Generation: `MiniMaxH3ReferenceToVideo` (node 136) `["", 768, 1344, 124, "max"]`: 768×1344 (portrait 9:16, 1 MP from
  `ResolutionSelector` node 115 `["9:16 (Portrait Widescreen)", 1, 32]`), **124 frames**, reference size `max`.
- Sampling: `KSamplerSelect` euler (123); `BasicScheduler` `["beta", 8, 1]` (124): beta, 8 steps, denoise 1;
  `BasicGuider` (no CFG, 126); `RandomNoise` randomize (129); turbo LoRA `minimax_h3_turbo_v4_step600_ema.safetensors`
  at 1 (5883); note 962: "8 Steps - Latest Scheduler with Turbo LORA · 20-25 Steps - WITHOUT any speed ups".
- **The six views (`ImageFromBatch`, frame index)**: front (orbit 0 %) **2** (node 200); left side (orbit 25 %) **21**
  (201); back (orbit 50 %) **42** (202); right side (orbit 75 %) **63** (203); face front (beat 2) **84** (204);
  face 3/4 (beat 3) **113** (205). Stitched 3 × 2 with 6 px black gutters (`ImageStitch` 210-216).
  Corrects the estimates above (§3) and blueprint §13.1's angles: these indices are the ones to use.
- The orbit B prompt (node 239, "Keep Picture 1's Style") and the A prompt (node 138, the general-purpose one of
  10 Sept) verbatim:
```text
=== node 239 Prompt for orbiting - (Keep Picture 1's Style)
[STYLE]
The output is matches the style of <Picture 1>. Sharp detail on eyes and face. The style never changes and never drifts between shots. No shadows.


[STAGING]
Solid light grey seamless backdrop, one flat uniform tone edge to edge, with no gradient, no vignette, no texture and no floor line. Nothing else is in frame. the subject casts no shadow onto the backdrop and no contact shadow on the ground beneath it, and it does not sit in its own shadow. Soft form shading on the subject itself is fine and should read its shape. Long telephoto lens, near-orthographic.

The character holds one relaxed A-pose throughout: arms hanging slightly away from the body, palms toward the thighs, feet shoulder-width apart, head level, calm neutral expression, eyes open and looking forward.
The subject is completely frozen, as rigid and motionless as a statue. Only the camera moves. There is no wind, no breeze, no air movement, no breathing, no settling, no sway, no secondary motion of any kind. Orientation, surfaces and lighting are identical in every shot, and the subject stays the same size in frame.

[0-3 seconds] tight full shot of the subject. The camera makes one smooth fixed-speed orbit right around it, a full 360 degrees: starting square on the front, passing the left side a quarter of the way round, directly behind at halfway, the right side three quarters of the way round, and returning to the front. The subject does not move at all. Ends back on the front view at 3 seconds.

[3-4 seconds] Camera snaps into a fast push-in on the character's face. Locked-off head and shoulders close-up, face square to camera, eyes into the lens. Ends on a sharp front-on face.

[4-5 seconds] camera whip-pans and rotates to a orthogonal angle. Locked-off head and shoulders close-up, head turned to a three-quarter angle, eyes still forward. Ends on a clean three-quarter face.

[CAMERA] One constant-speed orbit in beat 1, then locked off and static. The camera is the only thing in the scene that moves at any point. No zoom, no push in, no dolly, no tilt, no roll, no handheld shake, no motion blur, no dissolves.
[AUDIO] Silence. No music, no room tone, no voices.



=== node 138 Input Text (Prompt)
<Subject 1> is the character shown in <Picture 1>. 

Take from <Picture 1> the character's identity: face shape and features, eye colour, hair colour, length and style, complete outfit including footwear, and any distinctive markings, tattoos, jewellery, or accessories that are part of who they are. 

Do not carry over anything the character is holding in <Picture 1>. 

Do not carry over their pose in <Picture 1>. 

Do not carry over the background or setting of <Picture 1>.

```
