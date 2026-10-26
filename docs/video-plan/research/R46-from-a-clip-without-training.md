# R46 — A production's cameras and set handed to H3 as video, without training: what the engine has at af2ed29, 2026-10-17

Companion to R40 (a production-style LoRA). Read at: upstream WanGP `af2ed29`, Fizgig `6449224`, musubi-tuner
`f8a1b03`, ai-toolkit `9a1828f`. The question here: before or beside a LoRA, which engine inputs take a clip of the
production itself — its crane over the audience, its seated two-shot, its set and light — and what each one does to the output.
Facts only; nothing here was run. §5 lists what is not known.

## 1. Four inputs that take a video, and what each is for (engine text and code)
| Input | Models | What the engine says it does | Where it goes |
|---|---|---|---|
| **Reference Video** (`V-U`, `V+-U`, `V+*-U`: one to three) | Ref2VA | "for appearance, motion or camera" (`minimax_h3_handler.py:111`); "reuse subjects, appearance, or motion without changing the selected output resolution"; "contextual material, not a guaranteed frame-exact continuation constraint" (:120, :153) | VAE latents packed as condition rows in the sequence, like a reference image (`pipeline.py:628-650`; `components/packing.py:226-228`) |
| **Excerpts** (`V1-U`) | Ref2VA | up to three moments of one longer video, each 3 s unless `/duration`, ≥ 2 s, ≤ 15 s in all; "name them `<Video 1>` to `<Video 3>` in order" (:150-158; `excerpts.py:5-9`, `:36-56`) | the same path; the file is decoded by the pipeline (`pipeline.py:535-544`, `:1006-1007`) |
| **In-Context Guide** (`VU`) | FL2VA and Ref2VA | "H3 receives the control video's unchanged frames as `<Video 1>` … for LoRAs trained on FL2VA to transform a source video … Without such a LoRA, FL2VA is not trained to follow `VU`" (:87); on Ref2VA "it behaves like a Reference Video that follows the control video section by section" (:154) | split per sliding window; each window gets its own section (:91, :111) |
| **Denoise Control Video** (`GV`) | FL2VA and Ref2VA | video-to-video edit by denoising strength and mask; "does not supply the video as a motion/appearance reference" (:155; :111) | the source becomes the starting latents (`pipeline.py:1066-1070`) |
| **ControlNet-Union** (`PV` pose, `DV` depth, `EV` canny, `SV` shapes, `CV` gray, `V` as-is, `MV` inpaint) | `minimax_h3_control`, `_pruned` | "A control video drives the structure and motion … the text prompt defines its content, style and sound. The output takes the control video's aspect ratio"; depth "keeps the scene layout, camera movement and object placement while the prompt restyles everything" (:196, :201); strength `control_net_weight` 0–2 (:239) | a separate branch, a second file beside FL2VA (`defaults/minimax_h3_control.json:7-12`, bf16 and int8 files) |

- A reference video is **given whole to every sliding window** (:111); a control video is cut per window (:91). R32 §1
  found the same for reference images.
- The Ref2VA UI retired its own depth/pose/edge transfers in favour of the ControlNet-Union model (`:744-746`, commented out).

## 2. What a reference video becomes
- **Length.** First 15 s = 362 frames at 24 fps (`excerpts.py:9`; handler `:757`); two videos 7.3 s each, three 4.5 s
  (`:115`; `reference_video_frame_limit`, `excerpts.py:21-23`); frames must be `17n+5` after preprocessing
  (`pipeline.py:632-633`); each video ≥ 2 s (handler `:1000`). Over the budget, each keeps its first share and the UI
  says so (`:1012-1015`).
- **Size.** `reference_video_max_size` (768, 1344) (handler `:758`); resized to the output size (`pipeline.py:1025`,
  `_resize_video`), unlike images, which keep their own aspect at a pixel budget (R32 §1).
- **Two views of it.** The VAE latent (`pipeline.py:634-635`, under `control_video_encoding()`), and a Qwen3-VL
  presentation of frames sampled every `fps/2` frames, 2 per second, with timestamps (`:640-646`): the text encoder
  *sees* the clip at 2 fps, the transformer attends to all its latent frames.
- **Sound.** With `K`, the reference video's own track becomes an audio reference trimmed to the video's length
  (`pipeline.py:1020-1024`); with `KS` it is kept as the output soundtrack (handler `:113`). Without `K` the reference
  is "visual-only" — musubi uses the same words for a training reference with `"audio_path": null` (minimax_h3.md:251).
- **Prompt.** `<Video N>` is "a whole-video role"; a retained label is written in `retention_analysis` with a mode
  (`fully_preserved`, `partially_preserved`, `attribute_transfer`, `weak_reference`) (R22 §A.3). Which mode fits "take
  the camera and the set, not the people" is not stated by the engine; no example in `prompt_enhancer.py` uses a
  reference video for a set (grep `Video 1` → the character-swap and motion-transfer examples only).

## 3. Reference images and reference videos together
- Counts: 9 images + 3 videos + 3 audio, 12 files (handler `:985-988`, `:115`; `pipeline.py:1058-1063`). The order in
  the sequence: keyframes, then references in the order given (`packing.py:232-236`); the prompt numbers pictures and
  videos independently (R22 §A.3).
- Nothing in the engine assigns a reference to a role; roles come from the prompt (`:120`: "Images can guide identity,
  appearance, or scene content; video can guide content, appearance, and motion"). The engine's own stated use of the
  pair is "motion transfer to image-reference characters" (`:111`, `:576`).
- Found reports (R40 §6, summaries): background from reference *photos* pulling into the scene (MiniMaxH3Mod #33,
  2026-10-05, fetched, unanswered); no report of a reference *video*'s set competing with a referenced person's identity,
  in either direction.

## 4. What the trainers do with reference videos (for a LoRA that expects one)
- **musubi-tuner.** A Ref2VA record lists `references` of type `video` with an optional `audio_path`; `null` makes it
  "visual-only (motion or composition)" (minimax_h3.md:235-251); reference videos 2–15 s, ≤ 3 per record (:91). The
  reference teacher (`ref`) is the recipe that learns "identity and voice from video" with the clip itself as the
  teacher's privileged condition (:119, :143, :257). Memory: the reference teacher "carries the full reference video
  and audio tokens, so its teacher step is slower and needs more memory" (:514); a B200 (180 GB) OOMed on a
  1792×768×124 video-reference item (issue #1029, 2026-09-15, fetched).
- **ai-toolkit.** The Ref2VA class's docstring says "Image references only for now" (`minimax_h3.py:1104`), but the code
  packs reference videos from `control_video_paths_list` as multi-frame blocks after the image references
  (`:1413-1468`), with "the dataset's temporal treatment": real-time pacing from frame 0 at 24 fps, tail trimmed,
  snapped to `17n+5`, capped at the sample's frame count, area-matched to the target
  (`src/ref_video_cache.py:27-38`, `:166-206`; `minimax_h3.py:1320-1336`). Noise-augmented like keyframes (`:1457-1460`).
  A community patch (alisson-anjos gist, fetched at R40 heartbeat 1, last active 2026-09-20) adds `align_video_refs`, which
  puts a control video "on the target's rotary clock and spatial grid" as a frame-aligned v2v guide, and
  `control_latent_only`, which keeps it out of the VLM presentation; paired-clip datasets (target, guide, identity images),
  73 frames; its own examples are edits and a head swap, not camera or set transfer (figures in R40 §3).
- **Fizgig.** No reference-video training. Its RefMod (no training; a file the ComfyUI MiniMaxH3Mod nodes load) can
  take a clip "as motion (every latent frame of the clip, the pack's video reference, for a dance or a camera move)"
  with a token cap that thins near-duplicate frames (docs/REFMOD_HOWDOI.md:71-72); and two "style" presets "make a look
  rather than a person" (MINIMAX_H3.md:190). WanGP does not load RefMod files (R32).

## 5. What the Hub sends, and does not
- The Hub's clip task carries `image_refs` and LoRAs (R40 §2.4). It sends **no `video_guide`**, no `video_prompt_type`
  with `V`, no `custom_settings` for excerpts (`hub/worker/adapters/tasks.py`, no such keys); so none of §1's inputs is
  reachable from the Hub today. `minimax_h3_control` and `_pruned` are in the Hub's facts as models
  (`hub/worker/adapters/upstream.facts.json`, `models`), without a control-video key.
- The engine's `window_plan` from `wangp_validate` (R22 §B.1) would show how a reference video and the windows line up;
  not exercised here.

## 6. Not known
1. Whether a 15 s reference video of the production makes H3 reproduce its coverage and set with a different person from a
   picture; the engine's words ("appearance, motion or camera") are the only claim, and no run or report was found.
2. Which `retention_analysis` mode and wording give "set and camera from `<Video 1>`, person from `<Picture 1>`".
3. Whether excerpts (three 3–5 s shots: the crane, the two-shot, the push-in) work better than one 15 s stretch; untested
   anywhere found.
4. VRAM of a 362-frame reference on the server's 32 GB card at the Hub's sizes: not measured; musubi's note on reference
   teacher memory and the B200 OOM are training-side.
5. Whether the depth ControlNet-Union, fed a production clip, keeps "camera movement and object placement" of a
   crane shot while a prompt names a different person; no report.
