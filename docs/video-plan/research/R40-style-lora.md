# R40 — A production-style LoRA for H3: the set, the cameras, the audience, with the character from a picture, 2026-10-17

Research note (no spec, no code). The question: train a LoRA on clips of one existing multi-camera production so that H3 clips keep
that production's camera coverage (crane and pan over the audience, seated two-shots, handheld push-ins), its lighting, set and
real-looking audience, while a character picture given to Ref2VA still decides who is on stage. R29 and R31 (voice LoRAs:
the loader, key formats, the trainers' audio rules, time and VRAM in general) are not repeated; this note cites them.

Read here: upstream WanGP `af2ed29` (2026-10-12, the pinned engine, read-only clone); Fizgig `6449224` (2026-10-17);
musubi-tuner `f8a1b03` (docs 2026-09-27); ai-toolkit `9a1828f` (2026-10-17). Web items are from 2026-08-18 onward unless
marked; each says whether the page was fetched or only its search summary read. Facts only; §8 lists what is not known.

## 0. The one sentence per trainer
- **musubi-tuner** names the recipe outright: "Video: style, motion, general concept" trains T2VA on the FL2VA base from a
  `video_directory`, with the adapter or the guidance loss (docs/minimax_h3.md:142). Nothing on captions for style.
- **Fizgig** ships a "MiniMax H3 Style (LoRA 8)" preset: the Fast preset minus the clips' sharp-face stills, "style is
  about the look, not the face" (docs/MINIMAX_H3.md:38), and one captioning rule for style sets (docs/CLI.md:226).
- **ai-toolkit** has H3 (`minimax_h3`, `minimax_h3_ref2va`) but no H3 example config, no H3 doc, and no style guidance in
  the repo at `9a1828f` (grep of `config/examples`, `docs`, `README.md`).
- No trainer documents a *production* or *set* LoRA; "style" in all three means a visual look. The composition-and-coverage
  goal here is inferred from their motion/concept rows and block findings (§1.4), not stated by any of them.

## 1. The training set, per trainer

### 1.1 What a clip must be
| | musubi-tuner | Fizgig | ai-toolkit |
|---|---|---|---|
| Frame rate | 24 fps; sources normalised from their timestamps (minimax_h3.md:84) | exactly 24 fps, refused otherwise (MINIMAX_H3.md:147) | dataset `fps` default 24 (`toolkit/config_modules.py:1082`) |
| Frame count | `17n+5`; released range 5–15 s = 124…345 frames; `--allow_experimental_duration` lifts the range check only (:86) | 5, 22, 39, 56, 73, 90, 107 or 124 (:148; `src/fizgig/minimax/clip.py:23`): all *below* the released 5 s minimum except 124 | `num_frames` snapped down to `17n+5` with a warning (`minimax_h3.py:629-636`) |
| Cutting a longer file | `frame_extraction` head / chunk / slide / uniform, `target_frames`, `max_frames` (docs/dataset_config.md:268-276); example `target_frames=[124]`, `head` (minimax_h3.md:222-223) | the clip file *is* the sample; Gizmo cuts (below) | `shrink_video_to_frames` (default true) spreads `num_frames` evenly over the whole file, so a longer file is time-compressed (`config_modules.py:1075-1077`; `toolkit/dataloader_mixins.py:645-648`); off, a random start at `fps` (:1078-1082) |
| Size | multiples of 32; example buckets `[768,1344]` (minimax_h3.md:85, :212-216) | multiples of 32 (:149); trains at Target Megapixels, 0.25 MP default (:74); clips are cut at native size and resized at training time (:154) | bucket divisibility from the model (`minimax_h3.py:225`); no H3 figure |
| Audio | optional; stereo 32 kHz; sidecar, embedded, then silence (:87, :226) | 32 kHz stereo or none; `_mute` suffix keeps the picture and drops the sound (:150, :128) | `do_audio` on the dataset (`config_modules.py:1108`) |
| Caption | `clip.txt` (:226) | `.txt` beside the clip, "like a photo" (:118) | folder captions as for images |

Cost, Fizgig's measurement: a 22-frame clip is ~7× a still per step, 124 frames ~37× (MINIMAX_H3.md:156). Its table for
a **32 GB** card: up to 56 frames at up to 0.5 MP; 73–90 frames at 0.5 MP; 107–124 frames at 0.25 MP (:158-162).

### 1.2 One shot per clip
- Fizgig's Gizmo **Auto-chop** runs ffmpeg's `scene` filter on frames shrunk to 320 px wide, a score above the threshold is
  a cut, and clips are planned *between* cuts "so no clip ever straddles one — a clip that crosses a cut trains the cut as
  if it were motion" (`src/gizmo/gizmo.py:1182-1203`). Thresholds: Normal 0.30, "More cuts — fast-cut or handheld" 0.22,
  "Fewer cuts — slow or static" 0.40 (:1187-1191). A scene shorter than one clip is dropped, not padded; "Several clips
  from long scenes" packs a long scene back to back (:1226-1240, :4773-4784). Each segment is offered as a thumbnail from
  its middle frame to keep or skip (:122, :4984). A review grid stops at 400 segments (:1192).
- Dissolves and wipes: nothing in Gizmo handles them; a slow dissolve produces "micro-scenes" that the length filter drops
  (:1229-1230).
- musubi-tuner and ai-toolkit have no scene detection; a file is cut by frame arithmetic only (table above). musubi's
  `chunk` extraction splits one file into consecutive `target_frames` pieces regardless of cuts (dataset_config.md:307).
- No trainer says whether a multi-shot clip (a cut inside the 5 s) is good or bad for a *coverage* LoRA; H3's own prompt
  grammar expects cuts inside one window (`[Shot N] At MM:SS.mmm`, R22 §A.2), and a training clip with a cut is the only
  way to teach one. Not tested by anyone found.

### 1.3 Captions: composition, not identity
- **Fizgig's style rule** (docs/CLI.md:226): "caption the contents and never the style itself … say nothing about medium,
  brushwork, texture, colour grade or lighting. Then the trigger word is the only thing every caption has in common …
  Lighting is the one people get wrong: caption it and the style only fires under the lighting it saw. Describe
  generously." Its Style captioner instruction is one line, "Describe the image with zero references to the image
  style, just the factual contents of what is depicted" (`src/fizgig/krea2/caption_text.py:105-107`); the comment above
  it reports that a four-rule instruction leaked style words less often but trained worse, and that the one-liner's
  captions were ~2.4× richer (~70 words) (:86-99). The captioner is Qwen3-VL-4B (TRAINING.md:16). Clips are captioned
  by the same tab; a Whisper button appends `saying "…"` (MINIMAX_H3.md:136).
- Read against this goal: Fizgig's rule puts *lighting* on the "never caption" side so that the look fires everywhere;
  for a production whose lighting *is* part of what should fire, the same rule says to leave it out of the captions. The rule
  says nothing about camera moves; a camera move named in every caption would, by the same logic, bind to the words
  rather than to the trigger. No source tests this on video.
- **Trigger word.** Fizgig prepends the trigger (CLI.md:217-221; mode 2 "trigger + description" recommended). With LoRA
  Isolation a "style or look" subject "keeps its trigger as written … DOP drops the trigger from the trigger-free
  caption, so the look only appears when it's called" (docs/LORA_ISOLATION.md:61); on H3, Isolation trains from photos
  only, clips and voice are left out (:88; RELEASE_NOTES_v8.4.0.md:38). musubi names a trigger word only as the
  alternative to teacher matching (minimax_h3.md:143). ai-toolkit: its MiniMax caption prompt writes speech as
  `<d>[Language] …</d>` with `(S1)` IDs (R31 §1); no style prompt.
- **Keeping the production's on-screen people out.** musubi's identity recipes go the other way (teach identity while the caption omits it,
  :119-121). For the opposite, the only mechanism in a trainer is Fizgig's DOP/Isolation, photos only on H3. musubi's
  teacher-matching docs give the one engine-level fact: "The identity-decision band was measured at base sigma 0.6-0.75
  … color/style decisions start around 0.73, so style and identity overlap — the band gate alone cannot separate them"
  (docs/minimax_h3_advanced.md:92); and `--h3_teacher_loss_dc_weight` below 1 "stops the dataset's palette from being
  learned as a style shift … keep 1.0 when the dataset's palette is part of what should be learned (style LoRA)" (:103;
  minimax_h3.md:272). These are teacher-matching knobs; under the adapter or guidance-loss recipes there is no such gate.
- Fizgig's timestep help: "0-400 is the clean end (style, texture, fine detail), 600-1000 the noisy end (composition,
  layout, pose)" (RELEASE_NOTES_v8.0.5.md:4); on H3 its Training Structure "Likeness and Style" puts 60 % of steps on
  nearly-clean images (MINIMAX_H3.md:101; CLI.md:472) — the clean end, by its own help the *opposite* end from
  composition. "Model default, movement" is 8 % (CLI.md:472). Which structure a coverage LoRA wants is not measured.

### 1.4 Which blocks, which base, which adapter
- Fizgig: Default trains blocks 20-49 ("styles train faster and better on it", MINIMAX_H3.md:44); More Blocks 6-49 "for
  training a motion concept, since it reaches more of the model; whether Default is enough there too needs more
  testing" (:46); blocks 0-5 "deform anatomy and pull the dataset's colour into every render" (:50, :106). Its Ostris
  adapter "on a video-only style run … learned the look about three times faster" (:63). adamw "worth trying" for a
  style set (:56). Rank 8 presets; rank 16 "for larger datasets and longer trains" (:36-37).
- musubi: style row = FL2VA base, `--task t2va`, adapter or guidance loss (:142); default targets the four block
  linears (:400); teacher matching warns that unrestricted teaching near pure noise "overwrites the base model's
  composition prior with the dataset mean" (advanced :92) — the thing a coverage LoRA *wants* to move.
- ai-toolkit: `partition` `fl2va_pruned` default, `ref2va`, `ref2va_pruned` (R31 §2); LoRA target is the whole
  transformer class (`minimax_h3.py:199`), which Linears that resolves to was not traced here; training adapter loaded
  frozen as an "assistant" LoRA (:278-378).
- Base for the goal here: the Hub's character route is Ref2VA (R32). musubi trains Ref2VA only from a JSONL with
  per-record `references` (:235-251; "Video datasets take Ref2VA references from JSONL only", :674); ai-toolkit's
  ref2va class takes image references per item (`minimax_h3.py:1099-1122`); Fizgig's Training Base "Reference (ref2va)"
  exists for reference distillation (R31 §2). A production LoRA trained on FL2VA and loaded on Ref2VA: §2.3.

### 1.5 How many clips
Not stated by any trainer for video (R31 §1 found the same). Fizgig: "Clips cost far more per step than stills, so start
with a handful" (MINIMAX_H3.md:142). Web reports: §3.

## 2. A video LoRA and an identity picture together in Ref2VA at af2ed29
### 2.1 Where the LoRA goes
- One LoRA folder for every H3 model type, `get_lora_dir` → `"minimax_h3"` (`models/minimax_h3/minimax_h3_handler.py:482-483`).
- `wgp.py:7330-7357` parses the multipliers, resolves the files and calls `offload.load_loras_into_model` on
  `get_trans_lora()` = the transformer (`pipeline.py:448-449`) through `preprocess_loras` (`transformer.py:597-674`):
  kohya `lora_unet_blocks_N_attn_*` (:606-608), Diffusers names (:610-631), and q/k/v merged into `qkv_proj` (:656-673).
  Key formats per trainer: R31 §2. AdaLN adapters are converted by the *loaded* model's table (`lora_affine.py:95-97`:
  `architecture = _architecture(model_type)`, `ref2va` for all three Ref2VA types, :19-21).
- Inside the sequence, reference images are VAE latents packed as condition rows between the text and the target
  (`pipeline.py:604-612`; `components/packing.py:211-236`: text, keyframes, references, audio, target). The LoRA'd
  linears (`attn.qkv_proj`, `out_proj`, `mlp.fc1/fc2`) run on every row (R29 §2), so a LoRA changes how the reference
  rows are read as much as how the target is drawn. No code compares, orders or gates `activated_loras` against
  `image_refs`; nothing in the handler mentions both.

### 2.2 Strength and phases
- Ref2VA (not PDD) runs two guidance phases and two LoRA multiplier phases (`minimax_h3_handler.py:586`, `:589`):
  phase 1 denoises at half size (`pipeline.py:865-871`, scale `:39`), phase 2 refines after the latent upscale for
  `sampling_steps2` steps (default 3, `:753`; `:1432`, `:1459-1461`).
- A multiplier `1` applies in both phases; `a;b` sets them apart; a comma list ramps over steps
  (`shared/utils/loras_mutipliers.py:59-66`, `:89-97`). The engine itself adds the Turbo LoRA with `0;1`, phase 2 only
  (`pipeline.py:444-446`); the file is the FL2V turbo (`H3_TURBO_LORA_KEY`, `pipeline.py:46`; handler `:35-36`, set on
  every H3 model def `:683`); the Ref2V turbo file (`:37-38`) is used only by the face refiner
  (`postprocessing/h3_face_refiner/wgp_bridge.py:194-206`). A user-chosen turbo strength in phase 2 zeroes the engine's
  (`pipeline.py:892-898`).
- The audio refinement extra phase runs with every LoRA switched off and restores them after (`pipeline.py:1669-1678`).
- The speech route takes no LoRA in the Hub (R29 §1); the image route and the clip route pass them.

### 2.3 Trained on FL2VA, loaded on Ref2VA
- The FL2VA and Ref2VA transformers are different checkpoints (musubi: "Ref2VA uses the Ref2VA transformer", :65; the
  pruned files differ, R31). The loader does not check which base a LoRA was trained on; the AdaLN conversion uses the
  loaded base's table (§2.1). Upstream reads filename-marked **hybrid FL2VA/Ref2VA** checkpoints
  (`hybrid_fl2va_ref2va_bN-M`, `minimax_h3_main.py:35-50`) and converts a LoRA's AdaLN adapters per block to whichever
  half the block belongs to (`lora_affine.py:140-150`, `transformer.py:645-647`) — evidence that the two bases are
  treated as different, not that an FL2VA LoRA is wrong on Ref2VA. Whether a production LoRA trained on FL2VA keeps its
  effect on Ref2VA is not reported anywhere found (R29 §5 asked the same for voice).
- Shape for shape, one class serves both: `MiniMaxH3Model` has no Ref2VA-only module (`transformer.py:683-745`; the
  reference packing is used whenever `payload["refs"]` is present, `:773-774`), so an FL2VA-trained LoRA's keys fit
  the Ref2VA transformer exactly; only the weights under them differ. Whether the learned deltas carry over is the
  open question, not whether the file loads.
- Fizgig's Circlestone adapter "one file serves both the fl2va and ref2va bases"; Ostris's comes as separate fl2va
  and ref2va files (MINIMAX_H3.md:62-63); musubi lists an Ostris Ref2VA adapter, rank 16 (:179).

### 2.4 What the Hub sends today
`clip()` builds one task with `image_refs` (`hub/worker/adapters/tasks.py:154-161`) and `activated_loras` /
`loras_multipliers` (`:183`, `:76-77`) side by side; strengths go as plain numbers (`f"{s:g}"`), so no `a;b` phase
syntax and no ramps; up to 50 LoRAs (`hub/modules/generate_image/screen.py:27`). The folder the Hub lists for every
H3 model is `get_lora_dir`'s key under the LoRA root, `<LoRA folder>/minimax_h3` (`hub/worker/catalog.py:109-127`;
handler `:482-483`), plus the adapter's linked folders (`:129-134`); one listing serves FL2VA, Ref2VA and the speech
model. Reference *videos* (`video_guide`)
are not sent by the Hub (no such key in `tasks.py`), although the engine's Ref2VA takes up to three "for appearance,
motion or camera" (`minimax_h3_handler.py:111`) — a LoRA-free way to hand H3 a production's camera and set that is outside
this note's question and untested here.

## 3. Time and VRAM: what was reported (training; inference numbers in R31 and the matsuo notes)
Web access from this container: only github.com pages could be fetched; the rest are search summaries. Within 60 days
(2026-08-18 on) unless marked.
| Report | Card | What ran | Figures |
|---|---|---|---|
| Inline Studio v1.2.64 (GitHub discussion, **fetched**, 2026-08-07, 11 days outside the window) | RTX PRO 4500 Blackwell **32 GB** | 167 pixel-art clips, 1 s (24 f), 512 px, 500 steps; rank not stated | clips **3.01 s/step, 20.9 GB** peak; stills 0.72 s/step, 20.49 GB; "a 500-step clip run is roughly 27 minutes … plus about 7 minutes to load"; caching 173 clips ~20 min; clips "about 4× per step and almost nothing extra in VRAM" |
| Cseti CrossView-Warp (comfyui-wiki 2026-09-22, summary) | RTX PRO 6000 Blackwell (96 GB) | musubi-tuner, Ref2VA base, 512×512, **73 frames**, rank/alpha 32, adamw8bit 1e-4, INT8 ConvRot, batch 1, 6 000 steps (released 3 500); 719 Blender scenes rendered across camera offsets | **~20.35 s/step, 33 h 55 min** |
| pablodawson 360-Orbit (alphasignal, summary) | A100 80 GB | ai-toolkit, FL2VA, rank 16, 3 000 steps, 28 Gaussian-splat orbit renders | **~10.5 h** (~12.6 s/step by division) |
| musubi Discussion #1061 (**fetched**, 2026-08-16, two days outside the window) | "48 GB" (card not named; a 3090 is named for prep) | Ref2VA pruned INT8, 768×1344, 73 frames, rank 16, `--blocks_to_swap 40` | **~123 s per optimizer step**; 20 GB card: swap 50, 1-step smoke test only |
| Fizgig #73 (**fetched**, 2026-08-14) | 5090, int8 base, swap 19 forced | H3 LoRA step, clip size not stated | classic swap 5.51 s/step → H2D streaming **0.86 s/step**, +0.42 GiB |
| ai-toolkit #1050 (**fetched**, 2026-09-18, open) | **RTX 5090 32 GB**, Windows | `minimax_h3_ref2va`, `ref2va_pruned`, int8 convrot + nvfp4 TE, rank 16, 41 frames, 608×1088, layer offloading 0.5–0.75 | VRAM fills to ~31.9 GiB then a clean hang (triton); without triton OOM at load (dequant to ~40 GB) |
| musubi #1123 (**fetched**, 2026-09-18, open, same reporter) | **RTX 5090 32 GB**, Windows | Ref2VA pruned INT8, 608×1088, **124 frames**, rank 16, GL 4.0, `--video_only`, no swap | ~32.1 of 32.6 GiB then a first-step hang; `--blocks_to_swap 48` failed fast; inference on the same weights 11.7 s/step at 544×960×124 |
| ai-toolkit #1017 (**fetched**, closed 2026-09-22) | RTX 5090, 96 GB RAM | H3, convrot8 + nvfp4 TE, rank 16, 1-frame stills at 256 | RAM "spikes to 120GB+"; the error was a Triton path misconfiguration, fixed |
| ai-toolkit #1071 (**fetched**, 2026-10-02) | RTX 5090 | 39-frame clips at 512 | ~20 min stalls per load stage; a second user: ~1 h of CPU dequantisation before training |
| fal guide (summary, updated 2026-08-10) | cloud | 10–200 clips, "best 50–200"; rank 16, LR 2e-4, default 2 000 steps; "best people-realism adapter came from a 5,000-step slow-cook run at learning rate 1e-4" | billed 0.005 $/step |
| OmniChar guide (summary, undated) | L40S / RTX PRO 4500 / L4 | still 0.63 / 0.72 / 1.81 s per step at 512; a 1 s clip 3.26 s/step on the Blackwell | matches the Inline Studio figures (same tool family) |
| alisson-anjos gist, "ref2va aligned video guides (IC-LoRA style v2v) for ai-toolkit" (GitHub gist, **fetched** at heartbeat 1, last active 2026-09-20; patch against ai-toolkit `be99518`) | one GPU, not named | `minimax_h3_ref2va` with `align_video_refs` / `control_latent_only`; paired clips (target, aligned guide video, identity images); 73 frames, 512×288, rank **128**, batch 1, gradient checkpointing; 300 pairs for the timing, 1 000 for the LoRA | **53.1 s/it** default, 45.3 s/it with `control_latent_only`; embed cache 84 MB per sample (~105 GB for 1 250 pairs) vs ~0.9 MB with the flag; VRAM not reported |

- Fizgig's own ceilings for a 32 GB card are in §1.1; its Fast preset reaches likeness "in a few hundred steps" at rank 8
  (MINIMAX_H3.md:36). No Fizgig user report on a 5090 with clip sizes and step times was found in its issues or
  discussions (issue list fetched 2026-10-17; discussion #183 is unrelated).
- **No report of a 5090 finishing a multi-second-clip H3 LoRA run was found.** The two 32 GB reports that name frame
  counts above 1 s either hang at the first step or OOM (both open, both the same reporter, Windows, torch 2.14+cu130);
  the one 32 GB run that finished used 1 s clips at 512 px. A B200 (180 GB) OOMed on a Ref2VA *video-reference* item at
  1792×768×124 (musubi #1029 comment, 2026-09-15, fetched); image references trained.
- Rank and steps people used: 8 (Fizgig presets), 16 (fal default; 360-Orbit; #1050/#1123), 32 (CrossView); steps
  500 (Inline), 2 000 (fal default), 3 000 (Orbit), 3 500 of 6 000 (CrossView), 5 000 (fal realism).

## 4. How people measure that a style LoRA worked
- **Same seed, with and without.** fal's guide: paired renders, "same prompt, same seed: base model on the left, the
  trained realism adapter on the right"; strength 1.0 intended, 0.6–0.8 lighter (summary). LTX docs: hold seed, prompt,
  resolution and frame count; sweep 0.5–1.0; test one LoRA alone; disable it to see whether an artefact is the base's
  (summary). Fizgig's Repair Studio does exactly this on H3 — two 22-frame clips "side by side … looping in lockstep",
  a pinned first/last frame so "what you compare is the LoRA's effect, not the shot the seed happened to pick", and a
  library of renders with banks of five blocks switched off to see which blocks carry which feature
  (MINIMAX_H3.md:200-208); under Reference mode the same with up to two reference pictures (:210).
- **Where in the steps a thing settles.** musubi's `--trajectory_dir` decodes each step's clean estimate to an MP4 so
  one can see "at which step composition, palette, and identity settle" (minimax_h3_advanced.md:253); its logs split
  the teacher residual into a DC (palette) and an AC (structure) part (:86). Fizgig's Training Run Visualiser scrubs a
  run epoch by epoch (TRAINING.md:10).
- **Identity kept out / kept in, by number.** ArcFace cosine against the subject's mean face: same person ≥ ~0.45,
  strangers 0.0–0.2 (Fizgig LORA_ISOLATION.md:11, image model); the matsuo H3 notes (GitHub, fetched, 2026-08-14 →
  09-14) use 0.28 as the same-person line and a prompt-only control at 0.13, and report a 4-step LoRA lowering
  reference identity 0.669 → 0.613 (n = 3) — the one H3 measurement found of a LoRA changing how far a *reference*
  identity is kept. For a production LoRA the same score, run on the referenced character, is the test that the picture
  still wins; no one has published it.
- **Camera and shot.** Classifiers exist (CameraBench cam-motion VLMs, yes/no per motion primitive; ShotVL's eight
  dimensions, §5) but no source was found applying them to a LoRA's output; CameraBench's own scope is understanding
  existing video. The one style metric in a paper: generate from shared prompts, embed the first frames, compare
  style embeddings across pairs (arXiv 2605.01929, summary). Nothing H3- or Wan-specific.
- **Loss.** musubi: "There is no universal absolute flow-matching loss target" (Discussion #1061, fetched); its
  teacher-matching logs are the one per-step readout tied to meaning (cos / norm ratio / DC vs AC, advanced :84-86).

## 5. From a folder of 15-minute recordings to clips: what exists (web, mostly summaries)
Only github.com could be fetched from this container; huggingface.co, fal.ai, arxiv.org, civitai.com, reddit, note.com,
scenedetect.com were refused (proxy 403 / DNS). "fetched" = page read; "summary" = search-result text only.
- **Cut detection.** PySceneDetect 0.7.2 (2026-10-11, fetched): `ContentDetector(threshold=27.0, min_scene_len=15)`,
  `detect-adaptive` ratio 3.0 (summary of its API docs); `ThresholdDetector` for fades to black/white; nothing on
  dissolves. TransNetV2 (fetched README) has two heads, `single_frame_pred` for hard cuts and `all_frame_pred` for
  gradual transitions; the CineTrans paper (arXiv 2508.11484, summary) ran PySceneDetect first, then TransNetV2, and
  reports TransNetV2 "can handle gradual transitions more effectively". ffmpeg `scdet` threshold default 10, "good
  values 8–14" (summary). Fizgig's Gizmo uses ffmpeg's `scene` score at 0.30 / 0.22 / 0.40 (§1.2). LTX-2's trainer
  ships `split_scenes.py` over PySceneDetect with `--filter-shorter-than 2s`, `--min-scene-length`, `--max-scenes`
  (fetched, `packages/ltx-trainer/scripts/split_scenes.py`). No threshold report for older broadcast dissolves or wipes
  was found in any LoRA context.
- **Labelling shots and camera moves automatically** (for captions): ShotBench / ShotVL-7B-v1.1 (2025-09-12, fetched
  GitHub) scores eight dimensions — shot size, framing, camera angle, lens size, lighting type, lighting condition,
  composition, camera movement — evaluation code only, no labelling script. CameraBench (fetched GitHub) releases
  Qwen2.5-VL cam-motion checkpoints that answer yes/no per motion primitive or write "Describe the camera motion in
  this video", sampled at 8 fps. SkyCaptioner-V1 (fetched README, 2025-04) emits shot type, angle, position, camera
  motion, environment, lighting as fields. None was found used in an H3 or Wan LoRA pipeline.
- **Captioners and prompts.** LTX-2's `captioning.py` (fetched) defaults to Qwen3-Omni-30B-A3B at 2 fps and asks, per
  shot, for "the shot type and framing (extreme wide / wide / medium / medium close-up / close-up / extreme close-up)
  and any camera motion", "the environment's materials, textures, lighting, and colors", and all audio with dialogue
  quoted — the inverse of Fizgig's style rule (§1.3): everything named. fal's H3 trainer guide (summary, undated):
  10–200 clips, "best 50–200", one paragraph per clip "covering subject, action, setting, lighting, camera"; a
  `split_input_into_scenes` option (30 s default) with a warning to pre-split for precise captions.
- **De-identification by caption** (describe the on-screen people generically so the LoRA does not keep their faces): no source
  found that documents or measures it. The nearest facts: Fizgig's rule that "what you describe, the model can separate
  out; what you leave silent gets baked into the trigger" (CLI.md:219) and its style finding that a word in some
  captions but not others "teaches the model that some of these images have a property the others lack"
  (`caption_text.py:95-97`); and musubi's note that constant appearance is learned unless the teacher carries it
  (minimax_h3.md:121). One Wan thread (summary, anecdotal) claims the opposite tactic, a *detailed* face description,
  keeps the face out of the LoRA. Untested on H3.
- **Interlace, telecine, 4:3.** No LoRA guide covers it. General sources (summaries): `bwdif` over `yadif` for edges;
  film-origin 29.97 material wants inverse telecine (`fieldmatch,decimate` or `pullup`) to 23.976, not a resample;
  video-origin 59.94i has no 24p original. All three trainers want 24 fps (musubi normalises from timestamps, Fizgig
  refuses, §1.1). 4:3 needs no crop: musubi and Fizgig bucket any 32-multiple size (minimax_h3.md:85; CLI.md:181-191).
  Pillarbox/letterbox decisions for training: no report.

## 6. The production as a world: set, period look, 3D from footage (web, summaries unless marked)
- **Style apart from identity in video LoRAs.** Disco-LoRA (arXiv 2606.26668, June 2026, Wan 2.1 1.3B, summary):
  separate content / style / motion LoRAs, rank 32, "iterative dual-LoRA training with complementary prompting and
  time-aware masking", a z-score regulariser because content-LoRA weights are large and dominate style when merged;
  ~10 min to train a style LoRA; no code found. Older and labelled so: VideoMage (CVPR 2025) names "appearance
  leakage", a motion LoRA absorbing the subject's look; Customize-A-Video (ECCV 2024) adds an "appearance absorber".
  Image-side block findings (B-LoRA 2024; SplitFlux 2511.15258; Abstract-LoRA 2609.13239): style and content live in
  different blocks. **Not found:** a block map of Wan 2.x or H3 for look vs identity beyond Fizgig's 20-49 / 6-49 / 0-5
  (§1.4) and musubi's sigma bands (§1.3).
- **Period and broadcast-look LoRAs on H3** (HF/Civitai, summaries, dates not shown): `vh5tape` (KennethFal): worn-tape
  look, trigger `vh5tape` then a "damage tier" then the scene, strength 1.0 (0.7–0.9 softer); "Neon VHS Dreams"
  (Civitai 2987989) 0.85–0.95, no trigger; `y2kdigicam` (Civitai 2987922) at 0.8. Wan 2.2 "VHS television style
  80s/90s/2000s" (Civitai 2034788, 2025-10, older). LTX-2.3: CRT-terminal; "Golden Boy 90s anime" (493 clips, 67k
  steps). Datasets are not stated in any snippet. **Every period LoRA found is a tape/lens artefact look; none is a set,
  a lighting rig, an audience or multi-camera coverage.** No LoRA for a multi-camera production's set, audience or multi-camera
  coverage for H3, Wan or LTX was found.
- **Camera-behaviour LoRAs on Ref2VA with identity from the picture** — the pattern of this question, on HF (summaries):
  Cseti `MiniMax-H3_Ref2VA-LoRA-CrossView-Warp_v1`, pablodawson "360-Orbit", matlod "turnaround": each teaches a view
  or camera behaviour while the reference image supplies the subject. No bleed data reported. akatz-ai
  `MiniMax-H3-Character-Swap-LoRA` (Ref2V): V1 "loses the reference identity or returns to the source appearance",
  V1.5 retains more; mitigation is prompt text. note.com (PIYO) states LoRA "bleed" between persons as the reason for
  RefMod (R32). No measured report of a *set* LoRA's on-screen person overriding a referenced character.
- **Wan 2.2 practice** (vendor blogs, summaries, unverified): style on the low-noise expert, motion on the high-noise;
  20–60 regularisation clips of the class, 20–40 % non-portrait shots for backgrounds; "anything constant across all
  training clips becomes part of the trigger". Stack small single-purpose LoRAs (identity ~0.6 + look ~0.3) rather
  than one. The engine's per-phase multiplier syntax (§2.2) is the H3 equivalent of the per-expert strengths.
- **A set as 3D from broadcast footage.** HY-World 2.0 / WorldMirror 2.0 (Tencent, 2026-04-16, ICML 2026, summary):
  feed-forward video → depth, cameras, point cloud, 3DGS, ~12–24 GB VRAM. Marble (World Labs, summary): photos or a
  short video of a real location → 3D world, exports splats/meshes/camera-path renders. Vizrt (2026-10 blog): splats
  for virtual-production sets, demo. **Not found:** any reconstruction from *edited multi-shot broadcast* (cuts, zooms,
  moving people), or renders of such a set fed back as Ref2VA references. H3 itself takes a reference video "for
  appearance, motion or camera" (§2.4) and a depth control video that "keeps the scene layout, camera movement and
  object placement while the prompt restyles everything" (`minimax_h3_handler.py:201`, the FL2VA ControlNet-Union
  model); neither is LoRA training and neither is wired in the Hub.
- **Shot-grammar vocabulary** (trade sources, summaries; no academic paper on multi-camera shot grammar found):
  three cameras — wide master, a single of the lead speaker, a single of the other speaker — a fourth or a jib/crane
  for opening and bumper sweeps over the audience; a two-shot shifting to over-the-shoulder; audience cutaways used to
  cover edits; a fixed seating layout; all cameras on one side of the line (lacastlestudios, videomaker, rondexter).
  Zettl, *Television Production Handbook* (editions to 2015) is the standard text; its pages on this production type
  were not reached. Handheld push-in on a seated speaker is not a named convention in any source found. The caption vocabulary that exists in
  tools is LTX-2's shot-size list and ShotBench's eight dimensions (§5).

## 7. TV-style clips on H3: what their makers say they trained (web, summaries)
- **A continuous generated stream of TV-style segments** runs on fal's **H3 Max Director**, a proprietary autoregressive variant "with up to
  two minutes of context" that chains 39-frame carried segments and "expands each new direction against the prompts
  that came before it" (fal, latent.space, mindstudio; summaries). No LoRA and no training set is named anywhere; the
  set's persistence is attributed to context and prompt history, with drift reported as reduced, not removed. It is
  not the open H3 that the Hub runs.
- Two YouTube uploads of H3 clips in the style of a TV programme describe no training.
- No maker of a clip imitating a multi-camera production on H3 or Wan was found stating a dataset (two searches,
  2026-10-17).
- The nearest stated dataset: `vh5tape` (HF, summary) was trained on a small hand-curated set of four-second clips of
  period broadcast material (several programme types, commercials, news and station sign-offs; paraphrase) — for the *tape*
  look, with a "damage tier" word in the prompt; clip count not given. fal's Realism People LoRA: 176 live-action
  clips, slow-motion "detected and retimed", "normalized to 24 fps and structured scene captions", trigger `r34l1sm`
  (summaries). The two camera LoRAs (§3) trained on *renders* (Blender scenes; splat orbits), not footage.
- Rights: a third-party trainer page tells users to "use original or permitted footage and confirm the intended
  training rights" (summary). Not a finding; recorded because every TV-sourced set meets it.

## 8. Not known (named)
1. Whether an H3 LoRA trained on one production's clips moves camera coverage, set and audience while a Ref2VA picture still
   sets the person. No published run; the engine has no gate between the two (§2.1), and the one measurement of a
   LoRA against a reference identity is a *speed* LoRA (0.669 → 0.613, §4).
2. Whether to train on FL2VA (musubi's style row, Fizgig's default) or on Ref2VA (the Hub's route) for a LoRA used on
   Ref2VA; no cross-base report (§2.3).
3. Captions: whether Fizgig's "never the lighting" rule, written for a *look* on still images, holds when the lighting
   and the camera are the thing to learn; whether naming the on-screen people generically keeps them out; no video test of
   either (§1.3, §5).
4. Clip length for coverage: 1 s clips (the one finished 32 GB run) cannot hold a crane move or a push-in; 5 s clips
   (124 frames) at 32 GB have no finished report (§3). Fizgig caps 107–124 frames at 0.25 MP on 32 GB (§1.1).
5. How many clips; whether one shot per clip or a clip with a cut inside teaches cuts (§1.2).
6. Time on a 32 GB card: no completed multi-second-clip run reported on any 32 GB card; the two 32 GB attempts
   hang or OOM (§3). Fizgig's own ceilings are documented, its measured 5090 steps are at swap 19 without clip size.
7. Strength: 0.8–1.0 for the camera LoRAs, 0.6–0.8 "lighter" per fal; nothing for a set LoRA with references; the
   engine's phase syntax (`a;b`) is not sent by the Hub (§2.2, §2.4).
8. Whether the Hub's LoRA folder listing sees a trainer's file by name on Ref2VA (the listing is by name; no H3 LoRA has
   been loaded in WanGP from any of the three trainers by anyone here, R31 §5).
9. Any set reconstructed from edited broadcast footage; any such render used as a Ref2VA reference (§6).
10. What the generated stream's set persistence rests on beyond context length; whether its base is open (§7).

Sources (web; none fetched unless marked): [Inline Studio v1.2.64](https://github.com/orgs/inlineresearch/discussions/31) (fetched),
[musubi #1061](https://github.com/kohya-ss/musubi-tuner/discussions/1061) (fetched), [musubi #1029](https://github.com/kohya-ss/musubi-tuner/issues/1029) (fetched),
[musubi #1123](https://github.com/kohya-ss/musubi-tuner/issues/1123) (fetched), [ai-toolkit #1050](https://github.com/ostris/ai-toolkit/issues/1050) (fetched),
[ai-toolkit #1017](https://github.com/ostris/ai-toolkit/issues/1017) (fetched), [ai-toolkit #1071](https://github.com/ostris/ai-toolkit/issues/1071) (fetched),
[Fizgig #73](https://github.com/shootthesound/Fizgig/issues/73) (fetched), [matsuo-koya/minimax-h3-notes](https://github.com/matsuo-koya/minimax-h3-notes) (fetched),
[MiniMax-H3 #17](https://github.com/MiniMax-AI/MiniMax-H3/issues/17) (fetched), [MiniMaxH3Mod #33](https://github.com/Luisacaotica/ComfyUI-MiniMaxH3Mod/issues/33) (fetched),
[LTX-2 captioning.py](https://github.com/Lightricks/LTX-2/blob/main/packages/ltx-trainer/src/ltx_trainer/captioning.py) (fetched),
[LTX-2 split_scenes.py](https://github.com/Lightricks/LTX-2/blob/main/packages/ltx-trainer/scripts/split_scenes.py) (fetched),
[PySceneDetect](https://github.com/Breakthrough/PySceneDetect) (fetched), [TransNetV2](https://github.com/soCzech/TransNetV2) (fetched),
[ShotBench](https://github.com/Vchitect/ShotBench) (fetched), [CameraBench](https://github.com/sy77777en/CameraBench) (fetched),
[fal H3 LoRA guide](https://fal.ai/learn/devs/how-to-train-a-lora-for-minimax-h3), [fal Realism People LoRA](https://huggingface.co/fal/MiniMax-H3-Realism-People-LoRA),
[vh5tape](https://huggingface.co/KennethFal/vh5tape-vhs-lora-minimax-h3), [Cseti CrossView-Warp](https://huggingface.co/Cseti/MiniMax-H3_Ref2VA-LoRA-CrossView-Warp_v1),
[comfyui-wiki CrossView](https://comfyui-wiki.com/en/news/2026-09-22-h3-crossview-warp), [360-Orbit (alphasignal)](https://alphasignal.ai/news/pablo-dawson-s-minimax-h3-lora-spins-a-full-360-orbit-from-one-photo),
[akatz Character-Swap](https://huggingface.co/akatz-ai/MiniMax-H3-Character-Swap-LoRA), [Disco-LoRA](https://arxiv.org/abs/2606.26668),
[arXiv 2605.01929](https://arxiv.org/pdf/2605.01929), [HY-World 2.0](https://github.com/Tencent-Hunyuan/HY-World-2.0), [Marble](https://www.worldlabs.ai/blog/marble-world-model),
[H3 Max Director](https://fal.ai/h3-max-director), [latent.space on fal.live](https://www.latent.space/p/ainews-fals-h3-max-live-breaks-the),
[OmniChar guide](https://www.omnichar.org/lora-training/minimax-h3), LA Castle Studios blog, a studio production guide (lacastlestudios.com, blog).
