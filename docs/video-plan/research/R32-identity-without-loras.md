# R32 — Keeping the same characters across shots without LoRAs: engine, ComfyUI, community, 2026-10-17

Research note for BACKLOG 25. Engine: upstream WanGP `af2ed29`, read in a clone. ComfyUI core
`ce1e922` (2026-10-17, shallow; file history of `comfy_extras/nodes_minimax_h3.py` not read). RefMod repos, shallow:
ComfyUI-MiniMaxH3Mod `517e8c4` (2026-10-15), MiniMaxH3Mod-for-WanGP `d7d1e69` (2026-10-17), Refmod-Fork `c370627`
(2026-10-16); ComfyUI-H3-Continuum `7e14fde` (2026-10-16). Web pages outside GitHub could not be fetched from this
container (DNS/proxy refused: note.com, ai-muninn.com, virse.ai, astorie.ai, huggingface.co, docs.comfy.org); those
items are cited from search-result summaries. The ComfyUI workflow file R26 describes is not in this repo; R26 is the only record.
Facts only.

## 1. What Ref2VA takes per window at af2ed29
- **Count.** At most 9 reference images, injected frames not counted (`minimax_h3_handler.py:985-986`, `:115`,
  `:124`); 3 videos, 3 audio clips, 12 files in all (`:987-988`, `:1059-1067`). The pipeline raises again inside
  each call: "at most 12 references: 9 images, 3 videos, and 3 audio clips" (`pipeline.py:1062-1063`). The cap is
  per job and per window, not per character: nothing in the engine groups pictures by character.
- **Audio needs pictures.** Audio references may not outnumber image + video references
  (`minimax_h3_handler.py:1062-1064`; `pipeline.py:1058-1061`). Each audio reference ≥ 2 s; above 15 s combined each is
  cut to an equal share (`pipeline.py:546-563`; handler `:126`).
- **Modes.** `image_ref_choices`: none, `KI` (first picture is the main subject and sets the output size), `I`
  (references, chosen size kept), `FI` (first pictures injected at `frames_positions`, the rest references)
  (`minimax_h3_handler.py:724-732`).
- **Size, crop, background (wgp).** On window 1 only, `wgp.py:8054-8108` prepares the references once: with
  `fit_into_canvas_image_refs: 0` (`minimax_h3_handler.py:736`) each picture is scaled to the output's pixel budget,
  aspect kept, rounded to the block size, no crop (`shared/utils/utils.py:724-728`); with `K` the first picture is
  resized to the canvas (`:704-710`). The server's crop-fit setting crops only background/injected pictures
  (`wgp.py:8064-8073`). Background removal is off by default (`minimax_h3_handler.py:169`, `:1256`); when on, `rembg`
  cuts each non-background picture onto white (`utils.py:729-735`; colour `wgp.py:8091`).
- **Size (pipeline).** Each picture is resized again to `width × height × image_refs_relative_size/100` pixels, aspect
  kept, sides rounded to 32 (`pipeline.py:593-602`, `:337-346`); the slider runs 50–400 % (`minimax_h3_handler.py:738`).
  Small pictures are scaled up. No 1:4–4:1 aspect rule was found in `models/minimax_h3/` at af2ed29.
- **Encoding, two paths per picture.** (a) the video VAE encodes it as one frame; its rows join the condition rows,
  mixed with noise at `VISUAL_COND_TIMESTEP` (`pipeline.py:604-612`, `:735-742`). (b) the frame is shown to the
  Qwen3-VL text encoder as `<Picture N>: ` + vision tokens, before the prompt text (`text_encoder.py:124-154`).
- **Placement.** In the packed sequence: text, keyframe rows (start/end/continued/injected and history), keyframe
  audio, then the references in order; each image reference gets its own RoPE time step after the text and its own
  spatial grid; the target follows (`components/packing.py:211-246`, `:268-270`).
- **Order and labels.** Presentation order per window: keyframes first (continued or start frame, end image,
  injected frames by time), then reference images (`pipeline.py:965-996`); counters per type
  (`text_encoder.py:126-143`). Infos: "Per window, pictures are numbered: start or continued frame (`<Picture 1>`), end
  image, that window's injected frames by time, then references" (`minimax_h3_handler.py:109`, `:179`).
- **Tags.** The label is `<Picture N>`, not `<Image N>`; `<Audio N>`, `<Video N>` (`text_encoder.py:138-143`). The
  engine never parses tags in the prompt: binding is prompt text, e.g. `<Subject 1> is the violinist from <Picture 1>`
  (`prompt_enhancer.py:109`, `:161`, `:193`). An audio reference gets the label text only; audio never enters Qwen
  (`text_encoder.py:140-141`); its latent rows are placed with the references (`packing.py:247-252`).
- **Pairs.** No image+audio pair object exists. A reference video's own soundtrack is the only paired form
  (`video_audio`, `pipeline.py:628-651`). A picture and a voice are bound only by prompt wording, as in R26 §2.
- **Two-phase.** Phase 2 re-encodes the same pictures at the full output size (`pipeline.py:1433-1448`). The audio
  refinement extra phase injects no references (`minimax_h3_handler.py:279`).

## 2. On a continue / sliding windows
- **Pictures re-injected every window.** `src_ref_images` is set once on window 1 (`wgp.py:8077`, `:8097`) and passed
  to every `generate` call (`wgp.py:8252`); `audio_guide` likewise (`:8300`). Each call adds them again
  (`pipeline.py:991-996`, `:1029-1045`). Changelog: "Ref2VA preserves its selected reference memories across every
  Sliding Window" (`docs/CHANGELOG.md:83`, v12.45). The WanGP RefMod port read the same lines (README §13).
- **What carries the previous window.** Overlap `prefix_frames_count` (Ref2VA default 18, step 17, 1–120,
  `minimax_h3_handler.py:719-720`): all overlap frames but the last go in as VAE "history" rows, the last as a "first"
  keyframe image (`pipeline.py:808-822`, `:940-944`); the overlap audio as history + first audio anchors (`:969-986`).
- **Numbering shifts on a continue.** The continued frame is presented as `<Picture 1>`, so the reference pictures
  become `<Picture 2…>` in windows 2+ (`pipeline.py:944` before `:995-996`; `prompt_enhancer.py:54`, `:120`).
- **Appearance loss, engine's words.** `pipeline.py:812-813`: "ControlNet continuation keeps the overlap on the
  target timeline, both as fixed video latents and as visible pixels in its inpainting input. Native H3 history
  alone loses that appearance constraint." The comment sits on the ControlNet branch; FL2VA and Ref2VA take the
  native path (`:814-822`).
- **The Hub today.** Generate has 3 boxes (`hub/modules/generate_image/cast.py:19`), capped to them
  (`models.py:233`); the engine cap 9 is mirrored from the facts file (`hub/worker/adapters/upstream.facts.json:184`,
  `:190`). Identities go as `image_refs` with letters `I`, one cut-out switch for all
  (`hub/worker/adapters/tasks.py:158-163`; `upstream.py:205-214`), no names (`upstream.py:213`), no
  `image_refs_relative_size` (default 100 %). An identity model never continues: `continues` false
  (`hub/worker/catalogvideo.py:230-231`), a continue on it refused `NO_CONTINUE`, and a continued clip takes no other
  picture, `SOURCE_ALONE` (`tasks.py:40-41`, `:124-128`). No `<Picture`/`<Subject` string exists under `hub/`. The
  Hub's 1:4–4:1 rule (`cast.py:49-51`) cites the fork (R6 §4.3), not upstream. Sending the pictures with the clip
  is not built.
- **Post-process route in the engine.** H3 Face Refiner (v18, `docs/CHANGELOG.md:7`): tracks up to 5 faces and
  re-renders them with Ref2VA pruned, optional face reference pictures matched by InsightFace
  (`postprocessing/h3_face_refiner/wgp_bridge.py:139`, `:258`, `:293-299`), windows ≤ 362 frames, overlap 18
  (`runtime.py:17-20`). The Hub does not call it.

## 3. The workflow's ComfyUI nodes (ComfyUI core, not a custom pack)
Both live in `comfy_extras/nodes_minimax_h3.py` (ComfyUI `ce1e922`). `MiniMaxH3AddGuide` came in Comfy-Org/ComfyUI
PR #15439 by drozbay, merged 2026-08-13: "only allows keyframe guides at the first and last frame" before it.

- **`MiniMaxH3AddGuide`** (`:166-240`). Inputs: positive, latent, optional vae, audio_vae, image, audio, and
  `frame_idx` −9999..9999, negative counted from the end (`:177-185`). Anchors an image, a 17k+5-frame clip or an
  audio at that frame of the target (`:202-235`); the image is centre-cropped to the canvas (`:222`). Output:
  `minimax_keyframes`, one more per chained node (`:237-239`), placed at `frame_idx` on the shared time axis
  (`comfy/ldm/minimax/model.py:373-377`). It has no clip input: the guide is not shown to the text encoder.
- **`MiniMaxH3ReferenceToVideo`** (`:243-364`). Inputs: clip, prompt, size, length, `ref_image_size` `match`/`max`,
  ≤ 9 images, ≤ 3 videos with optional soundtracks, ≤ 3 audio (`:260-284`). `match` scales down only, to the output
  area; `max` caps the short edge at 2048, never up (`:301-308`). Builds the Qwen presentation `<Picture i>`,
  `<Video k>`, `<Audio j>`, images first (`:245-251`, `:360`; `comfy/text_encoders/minimax.py:7-12`) and the
  reference latents `minimax_refs` (`:363`).
- **R26's values.** AddGuide has one widget, `frame_idx`; R26 lists −1, 0, 0: last frame and frame 0. What was wired
  into each (image, clip or audio) is not recorded.
- **WanGP equivalents at af2ed29.** ReferenceToVideo ↔ Ref2VA `image_refs`/video/audio references (same labels and
  limits). AddGuide ↔ start/end image, `FI` injected frames at `frames_positions` (anchor `frame`,
  `pipeline.py:906-917`, `:955-956`) and the continuation history; WanGP shows those keyframes to Qwen as
  `<Picture N>`, AddGuide does not. Not found in WanGP: a user input that anchors a clip or an audio at an arbitrary
  frame (its audio anchors are only the continuation's `history`/`first`, `pipeline.py:983-986`); a `max` (2048 px)
  mode — 400 % of a 1344×768 output gives 2688×1536 for a 16:9 picture.
- **"RefMod" is a published tool name.** Luisa's ComfyUI-MiniMaxH3Mod: "no-training reference mods": a reference's
  VAE latent saved as `.safetensors`, reloaded at a strength through H3's native reference-token path; "It does not
  train H3 weights" (README:90-105). `training` mode pools the latent (fewer tokens, detail lost); `encode` keeps it
  (README:170-171). Its own words: "identity, clothing, background and composition can still mix" (:104-105);
  "There is no validated optimum image count" (:298). Ported to WanGP as a plugin (g3n3rativ3, `plugin_info.json`
  date 2026-08-19; up to 9 image + 2 video mods, README:24-35). Forked by jedsdead: "picture mods keep the same
  `<Picture N>` on every sliding window instead of shifting by one behind the carried-over frame" (README:110-112).
  The port monkeypatches `MiniMaxH3Pipeline` in memory (`patches.py:596-925`) and fails safe if the pipeline changed
  (README:973-977). Not run here against af2ed29.

## 4. What people do now (after 2026-08-18)
- **~2026-09-06** (date from a later post's listing), ai-muninn, two characters in one Ref2VA shot: 2 reference
  pictures, 243 frames, 1344×768, 437 s on an RTX 5090, n=1; "a <Subject 1> label carries no identity, so restate
  the full appearance in every shot or the model invents a person".
- **2026-09-07**, comfyui-wiki news: H3 RefMods, files of ~1–1.6 MB loaded like a LoRA in ComfyUI.
- **2026-09-12, updated 2026-10-11**, CivitAI (via civarchive): RefMods workflows & tutorial v1.0; no identity
  result in the summary.
- **Date not established**, note.com sepiablue (かみもと), "best combination of 3 reference images": 5 prepared
  pictures (multi-angle face sheet, three-view full body, upper body, two outfits), patterns A–D, fixed seed; the
  conclusion could not be read. Same author, RTX 4070: one small three-view sheet instead of 3 pictures saved
  ~12–13 s; one large combined picture did not.
- **2026-10-16 (HEAD)**, ComfyUI-H3-Continuum README:179-190, :244-245: Reference Images in slots 1–9, `All chunks`
  or `Per chunk`; `@R1` tags because "the actual `<Picture N>` may change by chunk"; "exact identity, motion, lip
  sync and frame-by-frame reproduction are not guaranteed"; "A subject may persist through video continuity after
  its assignment ends".
- **Undated in the summaries**: rundiffusion, leadde, virse guides: character sheets (front, three-quarter,
  profile, full body); one role per reference.
- Other H3 long-take packs seen in search, not read: ComfyUI-H3-Continuum-Plus (xmarre; masked continuation of the
  previous latent tail), ComfyUI-H3-LongTake (mark9009), ComfyUI_MiniMax_H3_Extender (tritant; "Choose Ref" takes a
  frame of the source video as an identity reference).
- Wan 2.x Phantom, Lynx, Stand-In, MAGREF, VACE refs, HuMo: no community report dated after 2026-08-18 was found.
  Results returned were the 2025 papers (Lynx table: facexlib resemblance Phantom 0.664, MAGREF 0.575, Stand-In
  0.611, short clips) and pages dated July 2026 or older.
- No measured identity score across continued H3 windows was found, from any source.

## 5. Not known
- Whether R26's mention of RefMods means the RefMod plugin (§3) or several reference pictures per generation.
- What the workflow's three AddGuide nodes carried, and whether the character's identity held in that workflow over several passes.
- Whether re-sent pictures (§2) hold identity over 3+ continued windows on the server; not yet tested.
- Whether a headshot + four views beats fewer pictures: no measured comparison found (sepiablue's result unread).
- Whether `image_refs_relative_size` above 100 % improves identity on H3; only the changelog's "favors fidelity".
- Whether the RefMod WanGP plugin loads on af2ed29.

Sources (web): [ComfyUI PR #15439](https://github.com/Comfy-Org/ComfyUI/pull/15439),
[ComfyUI-MiniMaxH3Mod](https://github.com/Luisacaotica/ComfyUI-MiniMaxH3Mod),
[MiniMaxH3Mod-for-WanGP](https://github.com/g3n3rativ3/MiniMaxH3Mod-for-WanGP),
[Refmod-Fork](https://github.com/jedsdead/Refmod-Fork),
[ComfyUI-H3-Continuum](https://github.com/ukr8b3g-cmyk/ComfyUI-H3-Continuum),
[ai-muninn two characters](https://ai-muninn.com/en/blog/minimax-h3-ref2va-two-characters),
[comfyui-wiki RefMods](https://comfyui-wiki.com/en/news/2026-09-07-minimax-h3-refmods),
[civarchive RefMods pack](https://civarchive.com/models/2932888?modelVersionId=3319580),
[sepiablue 3 references](https://note.com/sepiablue/n/nc752c844266c),
[sepiablue 3 into 1](https://note.com/sepiablue/n/na4e7729363b4),
[rundiffusion H3 prompt guide](https://www.rundiffusion.com/minimax-h3-prompt-guide),
[Lynx](https://byteaigc.github.io/Lynx/).
