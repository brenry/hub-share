# R39 — The smallest run that tests a Fizgig voice LoRA on H3's speech route: what is documented, 2026-10-17

Research note following R29 and R31 (not repeated; cited as "R29 §n", "R31 §n"). Engine: upstream WanGP `af2ed29`
(2026-10-12), read-only clone at `/tmp/upstream`. Trainer and metric read in shallow clones under `/tmp/r39`: Fizgig
`6449224` (2026-10-17 18:28; R31 read `bf8b0be`), SpeechBrain `c024127` (2026-10-14, version 1.1.2, as R31). Hub at
the working tree of 2026-10-17. Two
searches found no source on a Fizgig voice LoRA or on WanGP with an H3 voice LoRA; search-summary items are
marked. Facts only.

## 1. The set
- Item lengths Fizgig accepts: 0.917, 1.625, 2.333, 3.042, 3.750, 4.458, 5.167 s, ±25 ms (Fizgig
  `docs/MINIMAX_H3.md:171`; `src/fizgig/minimax/audio.py:14`). They are the 17n+5 clip grid at 24 fps without the
  5-frame slot (`audio.py:42-43`, :17-20); the tolerance is one 800-sample hop (`audio.py:45-47`), checked against
  32 kHz (`audio.py:65-71`). Formats `.wav .mp3 .flac .m4a`, any rate or channels; digital silence refused
  (doc :170-172).
- Item count: the doc gives no minimum; "ten minutes of reading is a usable dataset" (doc :126). Arithmetic only: ten
  minutes at the longest slot (5.167 s) is about 116 items; at mixed lengths, more.
- Tools: Gizmo (`launch_gizmo.sh`, Linux twin of `Launch Gizmo.bat`; or the Image Prep tab, doc :118). Voice tab:
  - From a recording: open audio or a video's soundtrack, mark segments, pick a length, caption, export
    (doc :124, :178).
  - 🎙 Record: prompted sentences "across every length and five tonal flavours", a delivery style rolled per take
    (doc :178); each take trimmed to its speech with 0.15 s / 0.2 s margins (`src/gizmo/gizmo.py:269`, :338-339);
    capture is 32 kHz (`gizmo.py:130`), written `pcm_s16le` wav (`gizmo.py:369-370`). Slot fitting: R31 §1.
- Caption file: a `.txt` beside each item, else it "silently won't train" (doc :173). Content: the voice, not a picture
  ("a man speaking calmly, low pitch, unhurried"), trigger word first (doc :178); Gizmo's card: "describe only the
  sound — tone, pace, accent, mood … Transcribe appends the spoken words, which helps the voice bind"
  (`gizmo.py:3033-3035`). Assembled as `<trigger>, <caption>` (`gizmo.py:4194-4199`); Transcribe writes
  `saying "…"` (`gizmo.py:4191`). The trigger word is remembered between sessions (`gizmo.py:3041-3044`).
- Transcriber: `openai/whisper-base`, local snapshot first (`gizmo.py:691-704`); language from Gizmo's settings,
  "Auto detect" by default (`gizmo.py:653`, :684). The Captions tab's script defaults to English when none is saved
  (`src/fizgig/scripts/transcribe_clip.py:48-56`).
- Where: Gizmo's voice save folder (`voice_out_dir`, persisted, `gizmo.py:3192-3193`); that folder is the training
  folder. Photos, clips and voice may share one folder (doc :118, :130); a voice-only folder is allowed (doc :166).

## 2. Fizgig settings for a voice-only run on Ref2VA (pruned)
| Setting | Documented value | Source (`src/fizgig/families/minimax.py`, docs) |
|---|---|---|
| Base | Training Base "Reference (ref2va)" = `--dit` on "DiT (reference)" (Preferences) | `minimax.py:54-58`, :199 |
| Base file | `minimax_h3_ref2va_pruned_int8_convrot.safetensors` (~21 GB) | `docs/CLI.md:89`; doc :91 |
| Audio VAE | required for voice files (~605 MB, own Preferences row) | doc :138, :174 |
| Structure | "Likeness and Style" (`lownoise_pct=60`), the default; "set … for voices" | doc :101, :180; CLI.md:472 |
| Training mode | Default: photos, clips, voice on blocks 20-49 (`audio_blocks=20-49`) | `minimax.py:79-80`; CLI :471 |
| Other blocks | "voice core `38-48`" via Blocks to Train, only with Training mode Off | doc :106; `minimax.py:132` |
| Preset Fast | rank/alpha 8, 50 epochs, automagic3 from 1e-6, 0.25 MP, EMA 0.98 | `minimax.py:24-38`, :44; doc :36 |
| Preset (rank 16) | rank 16, 60 epochs, same otherwise | `minimax.py:45`; doc :37 |
| CLI example | rank 8, `adamw8bit`, lr 2e-4, 50 epochs (differs from the GUI preset) | CLI.md:447-465 |
| Adapter | Circlestone default, one file both bases; Ostris ref2va file when Base is ref2va | doc :62-63; `:13` |
| Audio weight | `audio_weight=W`, CLI only, "for clips that carry sound" | CLI.md:476 |
- Batch is one item a step (CLI.md:192), so steps per epoch = item count. Fast "reaches likeness in a few hundred
  steps" (doc :36); no step count is given for a voice.
- Start, GUI: Base Model "MiniMax H3", then Start-tab folder, Captions, Samples, Training (doc :11). Headless: two cache
  stages (`cache.py --family minimax --stage latents … --aux audio_vae=…`, then `--stage text`), then
  `train.py --family minimax` (CLI.md:154-156, :447-465). Settings are read at launch (doc :114).
- Output: GUI default folder `output_loras` inside Fizgig (`src/fizgig/web/server.py:54`, :205). Headless:
  `<output_dir>/<output_name>.safetensors`, epochs as `<name>-NNNNNN.safetensors` (CLI.md:266). Previews: `.mp4` with
  the generated sound as `.wav` beside it, in `<output_dir>/sample/` (CLI.md:581, :585). Previews run on the training
  model, not on WanGP's speech route.
- Time/VRAM: R31 §3 (Auto plan by free VRAM; no voice-only run time anywhere). New, search summary only: a CivitAI
  guide (September 2026) gives 15-20 min for 30 images at 1 MP on an RTX 5090, images only, no voice.
- Targets: `blocks.N.attn.*`, `blocks.N.mlp.*`, refiner only if ticked (`minimax/common.py:53-54`;
  `minimax/driver.py:90-91`); saved as kohya `lora_unet_<module>` (`common.py:1222`). A comment says the pruned
  AdaLN projection is "INCLUDED" (`common.py:42-52`); the doc says nothing a LoRA learns lives there on the pruned
  file (doc :95). Whether a saved file carries `adaln_proj` keys was not established here.

## 3. The file in WanGP
- Folder: the H3 handler returns key `"minimax_h3"` (`models/minimax_h3/minimax_h3_handler.py:482-483`); WanGP
  resolves it as `--lora-config` JSON entry for that key, else `<root>/minimax_h3` (`wgp.py:2586-2605`;
  `shared/lora_paths.py:21-26`), root = `--loras`, else config `loras_root`, else `loras` (`wgp.py:2574-2584`;
  `shared/cli_args.py:35-36`). The resolver creates the folder if missing (`lora_paths.py:25`). `--lora-config`
  maps a key to any directory, relative paths read from the JSON's folder (`lora_paths.py:9-16`).
- Listing: every `*.safetensors`/`*.sft` under the folder, recursive (`wgp.py:3933`). Absolute names load as they are
  (`wgp.py:3836-3837`).
- Task keys: `activated_loras` (list of names) and `loras_multipliers` (string) (`wgp.py:1182-1183`, :10601-10613).
  UI: "LoRAs Multipliers (1.0 by default) separated by Space chars or CR" (`wgp.py:12809`); a value may be a
  comma list, one per step (`shared/utils/loras_mutipliers.py:60-67`). The speech model has one multiplier phase
  (`minimax_h3_handler.py:397`).
- Loading: `wgp.py:7330-7357` → `offload.load_loras_into_model` with the transformer's `preprocess_loras` (R29 §1).
  Kohya keys: `lora_unet_blocks_N_attn_*`/`_mlp_*` → `blocks.N.attn.*`/`.mlp.*` (`transformer.py:605-608`).
  AdaLN conversion acts on keys containing `.adaln_proj.linear.` (`lora_affine.py:104-106`), table `ref2va` for
  this route (`lora_affine.py:21`).
- By reading only: a kohya key `lora_unet_blocks_N_adaln_proj_linear` (the name Fizgig itself reads AdaLN rows by,
  `common.py:1224-1226`) would become `blocks.N_adaln_proj_linear` (only the first `blocks_` is rewritten,
  `transformer.py:607-608`), match neither the conversion nor a module, and mmgp fails a file with unmatched module
  keys ("likely … for a different model", `mmgp/offload.py:2134-2136`, :2274-2276); WanGP then raises
  "Error while loading Loras" (`wgp.py:7354-7357`).

## 4. The Hub today, and WanGP's own UI
- Refusal: `NO_LORAS = "{} takes no LoRAs"` (`hub/modules/generate_image/speech.py:19`), raised when any LoRA has a
  strength above 0 (`speech.py:22-25`, :49-50); the plan's summary has `"loras": []` (`speech.py:62`).
- Upstream of that: the catalog gives every speech model `"loras": False` (`hub/worker/catalog.py:209`), so no owner
  LoRA folder is attached (`hub/core/enginecat.py:78-79`) and no LoRA name resolves
  (`hub/modules/generate_image/models.py:266`). The speech task carries no LoRA keys
  (`hub/worker/adapters/tasks.py:251-276`).
- Other routes: `build.py:76-91` checks each `{id, strength}` (0-2, `screen.py:25`; 0 dropped) through
  `models.lora_name` (`models.py:259-284`): engine folder first, then `<owner LoRA folder>/<family key>`
  (`enginecat.py:75-82`) as a full path. `tasks.py:75-77` writes `activated_loras` and `loras_multipliers` (space
  joined); `adapters/fork.py:63` reduces names to basenames. Owner folders: Settings → LoRA folders
  (`hub/core/apply.py:19-23`).
- WanGP's own UI: the LoRAs tab shows for an audio-only model when `enabled_audio_lora` is set
  (`wgp.py:12797`), which this model sets (`minimax_h3_handler.py:396`). The model is listed as
  "TTS MiniMax H3 Voice Clone 20B" (`defaults/minimax_h3_tts_ref2va_pruned.json`). Its sample is `audio_guide` with
  `audio_prompt_type` "A", 32 kHz stereo out, each sample ≥2 s (`minimax_h3_handler.py:417`). Route defaults: 20
  steps, guidance 1.0, flow shift 12, euler, attention sparsity 1.3, skip-steps start 25 % ×0.08, duration 15 s
  (`minimax_h3_handler.py:1219-1233`). The engine is installed by `install/install-engine.sh` at `af2ed29`
  (`:14`), a folder with `wgp.py` (`install/install-hub.sh:47`).

## 5. The A/B and its measures
- Fixed across runs, per the task keys: `prompt` (script `Speaker 1:` + line, as the Hub writes it,
  `tasks.py:262-267`), `seed`, `audio_guide` + `audio_prompt_type` "A" (`tasks.py:271-273`), `duration_seconds`.
  Varied: `activated_loras` empty vs the file, `loras_multipliers` per strength. A dialogue job applies the same
  LoRAs to every turn (R29 §1).
- ECAPA check (SpeechBrain 1.1.2, package `speechbrain`):
  `from speechbrain.inference.speaker import SpeakerRecognition`;
  `SpeakerRecognition.from_hparams(source="speechbrain/spkrec-ecapa-voxceleb", savedir=…)`
  (`speechbrain/inference/speaker.py:22`, :34-41); `verify_files(path_x, path_y)` → `(score, decision)`
  (`speaker.py:101-133`).
  - Input: `load_audio` resamples to the normalizer's rate and mixes to mono (`inference/interfaces.py:346-360`);
    default `AudioNormalizer(sample_rate=16000, mix="avg-to-mono")` (`dataio/preprocess.py:42`). So H3's 32 kHz
    stereo `.wav` goes in as it is. The model card's own hparams could not be fetched (huggingface.co refused).
  - Score: cosine similarity of the two embeddings (`speaker.py:59`, :96-98); decision `score > threshold`,
    threshold 0.25 by default (`speaker.py:62`, :99). No fixed "same voice" bar for this use: R29 §4, R31 §4.
  - Comparison targets named by the task: each output vs the recordings. Which recordings (training items
    or held-out takes) no source prescribes.
- Words: Fizgig's `transcribe_clip.py <file>` prints `{"text": …}` (`transcribe_clip.py:1-3`, :97-101), whisper-base
  at 16 kHz (:19, :85). The engine's Whisper medium is used for turn trimming (R29 §4). No word-error tool or bar is
  documented in WanGP, Fizgig or the Hub.

## 6. Not known
- Whether a Fizgig voice-only LoRA changes the voice on WanGP's speech route at any strength (R29 §5, R31 §5).
- Whether a saved Fizgig H3 file carries `adaln_proj` keys; if so, whether WanGP loads it (by reading, §3: no).
- Whether a ref2va-base run with audio-only items is supported as documented; the doc names ref2va for the r2v
  workflow and for distillation, not for voice.
- Whether the trigger word must appear in the speech route's prompt, and where (the `[…]` direction or the line).
- Smallest set and step count that would show an effect; Fizgig gives only "ten minutes" and "a few hundred steps".
- Run time and VRAM of a voice-only run (R31 §3), on the server's card.
- The `spkrec-ecapa-voxceleb` hparams (rate, normalizer) as published; whether the step-skip cache defaults on this
  route change output between runs with the same seed.
- What ECAPA score change, if any, separates "LoRA changed the voice" from seed noise; no source states one.

Sources (web): [Fizgig](https://github.com/shootthesound/Fizgig),
[SpeechBrain](https://github.com/speechbrain/speechbrain),
[spkrec-ecapa-voxceleb](https://huggingface.co/speechbrain/spkrec-ecapa-voxceleb) (not fetched),
[CivitAI article 35846](https://civitai.com/articles/35846) (search summary only, September 2026),
[comfyui-wiki Turbo LoRA](https://comfyui-wiki.com/fr/news/2026-08-06-minimax-h3-turbo-lora) (search summary only,
2026-08-06, outside the 60-day window, not used for facts).
