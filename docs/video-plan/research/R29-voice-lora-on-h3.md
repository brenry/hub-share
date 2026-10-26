# R29 — A voice LoRA on H3's speech route: what the engine and the trainers document, 2026-10-17

Research note for V, R28 §4. Engine: upstream WanGP `af2ed29`, read in a clone. Trainers read in shallow
clones: ai-toolkit `dcebc74` (2026-10-16), musubi-tuner `f8a1b03` (docs/minimax_h3.md last changed 2026-09-27),
Fizgig `d63ca56` (docs/MINIMAX_H3.md last changed 2026-10-17). Web sources dated within 60 days. arXiv pages could not
be fetched from this container (proxy refused); the two arXiv items below are cited from search-result summaries of
their abstracts. Facts only.

## 1. Does the speech route load a LoRA
- Yes, by the engine's code path. The model def sets `"enabled_audio_lora": True` (upstream
  `models/minimax_h3/minimax_h3_handler.py:396`), which shows the LoRAs tab for an audio-only model
  (`wgp.py:12797`). LoRAs come from the folder shared by every H3 model: `get_lora_dir` returns `"minimax_h3"`
  (`minimax_h3_handler.py:482-483`).
- At generation `wgp.py:7330-7357` loads the selected LoRAs into `wan_model.get_trans_lora()`, which for H3 is the
  transformer (`models/minimax_h3/pipeline.py:448-449`), through the transformer's `preprocess_loras`
  (`wgp.py:3694-3700`; `models/minimax_h3/transformer.py:598-674`).
- The speech model type is in the AdaLN LoRA conversion table, mapped to `ref2va` (`models/minimax_h3/lora_affine.py:21`);
  a type not in it raises (`lora_affine.py:37-41`). The route reuses the pruned Ref2VA checkpoint
  (`defaults/minimax_h3_tts_ref2va_pruned.json`, URLs `MiniMax-H3-Ref2VA-pruned_rank8_*`), so the matching training base
  is Ref2VA (pruned).
- A dialogue runs one `pipeline.generate` per speaker turn, each with the same `loras_slists`/`loras_selected`
  (`models/minimax_h3/dialogue.py:399-420`); each call activates them for its steps (`pipeline.py:873-878`, `:900`).
  The route runs one guidance phase (`minimax_h3_handler.py:1224`), so no automatic Turbo LoRA is added
  (`pipeline.py:444-445`).
- Key formats accepted: `lora_unet_blocks_N_attn_*`/`_mlp_*` (`transformer.py:606-608`) and diffusers names, including
  `audio_proj_in.` → `audio_patch_proj.` and `audio_proj_out.` → `final_layer.audio_out.` (`transformer.py:611-631`).
- The Hub refuses LoRAs on the speech route today: `NO_LORAS` (`hub/modules/generate_image/speech.py:18`, `:48-49`).
- Not tested anywhere: whether an audio-trained LoRA changes the voice this route produces.

## 2. Through which weights an audio LoRA acts
- H3 is single-stream: text, video and audio rows are packed into one sequence through the same 50 `DiTBlock`s
  (`transformer.py:716-719`). Every block's `attn.qkv_proj`, `attn.out_proj` (`:249`, `:252`), `mlp.fc1`, `mlp.fc2`
  (`:188-189`) act on audio rows as on video rows.
- Per-modality weights: the AdaLN projection outputs three modalities (`AdalnProj`, `modalities=3`,
  `transformer.py:389-395`); a row's shift/scale/gate is picked by `timestep_row*3 + tag`, tags video 0, text 1,
  audio 2 (`models/minimax_h3/components/packing.py:16-18`; `transformer.py:68`). Audio-only weights: `audio_patch_proj`
  (`transformer.py:700`) and `final_layer.audio_out` (`:543`).
- The route denoises a hidden 32×32 video with the audio (`pipeline.py:794-797`; model description in the defaults file).
- Trainers' default targets are the block linears only: musubi-tuner `attn.qkv_proj`, `attn.out_proj`, `mlp.fc1`,
  `mlp.fc2` in the 50 main blocks (docs/minimax_h3.md:400); Fizgig writes `lora_unet_blocks_0..49_*` (attn qkv/out +
  mlp fc1/fc2) and token-refiner blocks (`src/fizgig/repair_studio/h3_blocks.py:6-8`). Neither names
  `audio_patch_proj` or `audio_out` as a target.
- musubi-tuner: "Because H3 is single-stream, a video-only LoRA modifies the weights the audio path uses too"
  (docs/minimax_h3.md:490).
- Fizgig names blocks `38-48` the "voice core" among its measured recipes; its Default trains blocks `20-49`
  (docs/MINIMAX_H3.md:106, :44).

## 3. Local trainers that document H3 audio, and what a voice dataset needs
| | Fizgig | musubi-tuner | ai-toolkit |
|---|---|---|---|
| H3 audio training | yes: "photos, video clips, sound, voice" (README.md:71) | T2VA, FL2VA, Ref2VA with audio (docs/minimax_h3.md) | joint audio "when the dataset provides it" (`extensions_built_in/diffusion_models/minimax_h3/minimax_h3.py:3-4`) |
| Voice alone (no video) | yes: "Training on a voice alone" (docs/MINIMAX_H3.md:164-174) | no audio-only mode described | audio trains only on video batches with `do_audio` (`minimax_h3.py:814-823`; `toolkit/config_modules.py:1108`) |
| Bases | fl2va and ref2va (MINIMAX_H3.md:63, :210) | Ref2VA among the tasks | `fl2va`, `fl2va_pruned` (default), `ref2va`, `ref2va_pruned` (`minimax_h3.py:26-27`) |
| Format | `.wav .mp3 .flac .m4a`, any rate or channels (MINIMAX_H3.md:170) | stereo 32 000 Hz; same-stem sidecar, then embedded audio, then silence (:87, :226); JSONL `audio_path` wins (:245) | resampled to 32 kHz (`minimax_h3.py:714-716`) |
| Item length | exactly 0.917, 1.625, 2.333, 3.042, 3.750, 4.458 or 5.167 s ±25 ms (MINIMAX_H3.md:171) | 5 to 15 s, frames 17n+5 at 24 fps (:86); reference videos 2 to 15 s, ≤3 audio-bearing refs (:91) | 17n+5 frame grid |
| Captions / transcripts | `.txt` beside each file, else it "silently won't train" (:173); caption the voice, trigger word first; Whisper "Transcribe" appends the words (:178); clips get `saying "…"` (:136) | no transcript requirement stated; dialogue is written `<d>[Language] ...</d>` (:67) | not documented |
| How much | "ten minutes of reading is a usable dataset" (:126) | not stated | not stated |
| Audio weight | Training Structure "Likeness and Style" for voices (:180) | `--audio_loss_weight` (default 1.0), `--video_only` (:490); "ref" teacher learns "identity and voice from video" (:143, :456) | `audio_loss_multiplier` (`toolkit/config_modules.py:618`) |
| Needs | the audio VAE (~605 MB) (:138, :174) | — | audio VAE file (`minimax_h3.py:121`) |

- Fizgig output "loads straight into ComfyUI's H3 workflows" (docs/MINIMAX_H3.md:5). Its key prefix
  `lora_unet_blocks_` is one WanGP's preprocessor rewrites (`transformer.py:606-608`); loading one in WanGP is untested.
- No published voice-consistency result for an H3 voice LoRA was found (searches 2026-10-17; R28 §3 lists the one
  documented experiment, Virse, which reports none).

## 4. Measuring voice consistency between lines
- The method in current voice-cloning papers: embed each clip with a speaker-verification model and take the cosine
  similarity. Seed-TTS-eval's SIM uses WavLM-large fine-tuned for speaker verification
  ([seed-tts-eval](https://github.com/BytedanceSpeech/seed-tts-eval)). RVCBench (arXiv 2602.00443, latest version dated
  2026-10-01 per its listing) uses SpeechBrain's ECAPA-TDNN verifier and reports acceptance rates. arXiv 2608.15690
  (2026-08-16, voice cloning added to a text-to-audio-video model) reports speaker-encoder cosine similarity across three
  verifiers: ECAPA-TDNN, WavLM-SV, Resemblyzer.
- Local tools: SpeechBrain ECAPA and WeSpeaker are Apache-2.0 backends of LocalAI's voice verification, which returns a
  distance and a threshold ([LocalAI](https://localai.io/features/voice-recognition/index.html), page undated);
  WeSpeaker's model card documents a two-file `similarity` task
  ([wespeaker-ecapa-tdnn512-LM](https://huggingface.co/Wespeaker/wespeaker-ecapa-tdnn512-LM)).
- No source gives a standard threshold for "same voice"; papers compare scores between systems, not against a fixed bar.
- Already in the engine folder: a CAM++ speaker encoder (`campplus_cn_common.bin`, 192-dim embedding) loaded by
  IndexTTS2 (`models/TTS/index_tts2/infer_v2.py:264-274`) and SeedVC (`postprocessing/seedvc_processor/assets.py:9`),
  as conditioning, not as a metric; and the Whisper model the speech route loads for boundary trimming
  (`minimax_h3_handler.py:1139-1140`; `dialogue.py:204`), the transcription check R27 uses.
- Inside one dialogue job, a speaker with no reference gets the last 15 s of that speaker's first generated turn as the reference
  for that speaker's later turns (`dialogue.py:346-348`, `:427`). Separate jobs share only the sample given.

## 5. Not known
- Whether an audio-trained LoRA changes H3's voice on this route, and by how much at what strength.
- Whether a LoRA trained on fl2va acts the same on the Ref2VA-pruned checkpoint the route uses.
- Any similarity score for H3 lines, with or without a LoRA.

Sources (web): [musubi-tuner docs/minimax_h3.md](https://github.com/kohya-ss/musubi-tuner/blob/main/docs/minimax_h3.md),
[ai-toolkit](https://github.com/ostris/ai-toolkit), [Fizgig](https://github.com/shootthesound/Fizgig),
[seed-tts-eval](https://github.com/BytedanceSpeech/seed-tts-eval), [RVCBench](https://arxiv.org/abs/2602.00443),
[arXiv 2608.15690](https://arxiv.org/abs/2608.15690), [LocalAI voice recognition](https://localai.io/features/voice-recognition/index.html),
[WeSpeaker model](https://huggingface.co/Wespeaker/wespeaker-ecapa-tdnn512-LM).
