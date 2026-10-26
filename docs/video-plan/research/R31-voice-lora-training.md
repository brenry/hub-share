# R31 — Training a voice LoRA for H3's speech model on the recordings: what is documented, 2026-10-17

Research note following R29 (which it does not repeat). Engine: upstream WanGP `af2ed29` (read-only clone). Trainers
read in shallow clones under `/tmp/r31`: Fizgig `bf8b0be` (2026-10-17; R29 read `d63ca56`), musubi-tuner `f8a1b03`
(2026-09-27, as R29), ai-toolkit `9a1828f` (2026-10-17; R29 read `dcebc74`), SimpleTuner `0b4d3b1` (2026-10-17, new
here). Metric packages: SpeechBrain `c024127` (2026-10-14), WeSpeaker `9fecd6c` (2026-09-22), Resemblyzer `15d828e`
(2023-10-12, its last commit). Web: no page could be fetched from this container (DNS failure, then the proxy refused
note.com, comfyui-wiki.com, omnichar.org); web items below are cited from search-result summaries and are marked so.
Community sources only from 2026-08-18 onward. Facts only.

## 1. The training set, per trainer
- **Fizgig.** Audio-only items: yes (MINIMAX_H3.md:164-174). Length: exactly 0.917, 1.625, 2.333, 3.042, 3.750,
  4.458 or 5.167 s, ±25 ms (:171; `minimax/audio.py:44-46`). Any rate/channels, decoded to 32 kHz stereo
  (`audio.py:36-38`). Caption: a `.txt` beside each file or it does not train (:173). Amount: "ten minutes of reading
  is a usable dataset" (:126).
- **musubi-tuner.** No audio-only item: every item is a video, 5-15 s, 17n+5 frames at 24 fps (minimax_h3.md:84-86);
  audio stereo 32 000 Hz (:87); caption `clip.txt` (:226). Amount: not stated.
- **ai-toolkit.** No audio-only item: a folder of audio files is read only by audio models
  (`toolkit/data_loader.py:479-488`) and H3 is a video model. Video `num_frames`; audio can be stretched to fit
  (`toolkit/config_modules.py:1109`); resampled to 32 kHz (`minimax_h3.py:714-716`). Amount: not stated.
- **SimpleTuner.** Audio-only items: `dataset_type: "audio"` (quickstart MINIMAX_H3.md:74-76). Audio trimmed to 15 s
  (`models/minimaxh3/model.py:1284-1303`); duration buckets, 3 s default (DATALOADER.md:187-190); audio VAE at
  32 000 Hz (`modular_pipeline.py:729`). Captions and amount: not stated for H3.
- Fizgig's cutting tool is Gizmo (`src/gizmo/gizmo.py`). Exports are wav, 32 kHz stereo, exactly `latents × 800`
  samples, caption `.txt` beside each (`gizmo.py:84-96`, `:2990-2996`). Two routes:
  - An existing recording (any audio, or a video's soundtrack): segments are marked by hand on the waveform, a grid
    length is picked per segment (MINIMAX_H3.md:124, :178). No automatic silence-based splitting of a long file was
    found in Gizmo.
  - The 🎙 Record route: prompts sentences "across every length and five tonal flavours" (:178); each take is trimmed
    to its speech by an amplitude envelope with 0.15 s / 0.2 s margins (`gizmo.py:269-290`), then widened to the
    smallest grid slot that holds it using the room tone around it (`:294-302`). A take longer than the biggest slot
    is kept in full for cutting in the editor (`:305-308`).
- Captions (Fizgig): describe the voice, trigger word first ("a man speaking calmly, low pitch, unhurried"); the
  Transcribe button appends the spoken words (MINIMAX_H3.md:178). The transcriber is `openai/whisper-base`, run
  locally from a cached snapshot (`scripts/transcribe_clip.py:19`, `:31-35`; `scripts/fetch_models.py:193`). The doc
  does not say whether transcribed words are required; only the caption file is.
- musubi-tuner: no transcript rule; the released prompt format writes dialogue as `<d>[Language] ...</d>` (:67).
  A trigger word is named only as the alternative to teacher matching for identity (:143).
- ai-toolkit: the UI captioner runs Qwen3-Omni-30B (`ui/src/helpers/captionOptions.ts:192-194`) with a MiniMax T2VA
  prompt that writes speech verbatim as `<d>[Language] ...</d>` with `(S1)` speaker IDs (`:39-44`).
- Fizgig refuses digital silence (MINIMAX_H3.md:172). musubi allows ≤200 ms missing audio per window (:89).

## 2. Running each trainer locally
- **Fizgig.** Linux/NVIDIA: `python install_fizgig.py`, then `./launch_fizgig.sh` (docs/INSTALL.md:125-128); Python
  3.10-3.13, driver 550+ on Linux (:14, :17). Headless: `src/fizgig/families/train.py --family minimax` with model
  paths as flags (docs/CLI.md:443-462). Voice-relevant options: `audio_blocks=20-49` (Default mode, CLI.md:456);
  `audio_weight=W`, "raise it if a voice isn't being learned" (:473); `lownoise_pct=60` = Likeness and Style, the
  structure the doc names for voices (:469; MINIMAX_H3.md:180). An audio-only item trains with video weight 0, so its
  loss is the audio term alone (`minimax/driver.py:434-439`; `minimax/common.py:1018-1021`).
  Base: Training Base "Reference (ref2va)" = `--dit` on `minimax_h3_ref2va_pruned_int8_convrot.safetensors`
  (`families/minimax.py:54-58`, `:198-209`; CLI.md:89); default is fl2va (`minimax.py:55`). Needs the audio VAE.
- **musubi-tuner.** Three steps: `minimax_h3_cache_latents.py` (with `--audio_vae`, always required, :347),
  `minimax_h3_cache_text_encoder_outputs.py`, then `accelerate launch ... minimax_h3_train_network.py` (:380-398) plus
  one loss method (adapter, guidance loss or teacher matching, :113-121). Audio: `--audio_loss_weight` (default 1.0);
  `--video_only` turns it off (:490). The reference teacher learns "identity and voice from video" and copies each
  clip's audio (:456). Ref2VA needs per-record references, ≥1 image or video (:91). Pruned
  int8 Ref2VA file listed (:56).
- **ai-toolkit.** `python run.py <config>`; H3 is not in the UI's model list at this commit (grep of `ui/src` finds
  only the caption prompts). Arch `minimax_h3` / `minimax_h3_ref2va` (`minimax_h3.py:178`, `:1122`); partition
  `ref2va_pruned` selectable (`:26-27`); the ref2va class takes image references only (`:1108`). Audio needs
  `do_audio` on a video dataset (`:814-823`); weight `audio_loss_multiplier` (`config_modules.py:618`).
- **SimpleTuner** (found by search, not in R29). Config JSON, `model_family: "minimaxh3"` (quickstart :17-30). Starting
  configs are fl2va int8 presets for 24 GB (RamTorch), 32, 48, 80 GB (:9-13). Flavour `ref2va` exists
  (`model.py:133`); no example combines it with audio-only. In audio-only mode the default LoRA targets are attention
  plus `audio_proj_in`/`audio_proj_out` (`model.py:167-174`; DATALOADER.md:181-185), the audio-only weights R29 §2
  found no other trainer naming.

Output keys against WanGP's loader (by reading only; none loaded in WanGP):
- Fizgig: kohya `lora_unet_blocks_N_attn_*/_mlp_*` (`networks/lora.py:1314`; targets `minimax/common.py:53-54`).
  WanGP's `preprocess_loras` rewrites this prefix (upstream `models/minimax_h3/transformer.py:606-608`).
- musubi-tuner: `lora_unet_*` (`networks/lora_minimax_h3.py:15`, `:65`); same WanGP path.
- ai-toolkit: `diffusion_model.` + checkpoint keys (`minimax_h3.py:1094-1096`); the prefix is stripped by upstream
  `mmgp/offload.py:2028-2039`.
- SimpleTuner: default Diffusers format (`training/lora_format.py:17-28`), keys prefixed `transformer.` or, for
  ref2va, `transformer_ref.` (`modular_pipeline.py:451`, `:771`). WanGP's Diffusers renaming runs only on unprefixed
  keys (`transformer.py:599-602`); mmgp strips `transformer.` after it (`offload.py:2018-2039`); `transformer_ref.`
  is not stripped. `--lora_format comfyui` writes `diffusion_model.` native fused keys (`modular_pipeline.py:332-338`).

## 3. Time and VRAM
- Fizgig, documented: Auto picks base and block swap from free VRAM: ~30 GB int8 no swap; ~22 GB int8 ~14 blocks
  streamed; ~15 GB int8 ~36 blocks; ≤12 GB 4-bit (MINIMAX_H3.md:13-18). Smallest card for H3: 16 GB (README.md:71).
  Fast preset: rank 8, 50 epochs, "reaches likeness in a few hundred steps" (MINIMAX_H3.md:36). Per-step cost of a
  voice item: not stated (a 22-frame clip is ~7× a still, :156).
- musubi-tuner, documented: example run `--blocks_to_swap 48 --gradient_checkpointing` (:389-390); swap up to 48 of 50,
  `--block_swap_h2d_only` faster (:507-508); pruned int8 transformer ~21 GB, text encoder NVFP4 ~15 GB (:505-510).
  Measured: classic swap 12.7 s/it vs ~4 s/it with `--block_swap_h2d_only` on int8, GPU not named
  (docs/minimax_h3_advanced.md:181). No minutes or hours for a run.
- ai-toolkit: no H3 VRAM or time figure in the repo.
- SimpleTuner: VRAM-tier presets only (above); no times.
- Web, within 60 days (summaries; pages not fetched):
  - comfyui-wiki "Fizgig v5 Full Fine-Tuning" (URL dated 2026-08-30): voice listed trainable at 16 GB; measured H3
    peaks 8.8-12.3 GB on a 16 GB card.
  - YouTube "MiniMax H3 - Voice & Likeness single Lora training with Audio files, Videos and Stills" (search gave
    "about 59 days ago", ~2026-08-19): no numbers in the summary.
- Found but outside the window or undated, not used for numbers: musubi-tuner Discussion #1061 (mid-August, 123 s
  per optimizer step on 48 GB); SECourses Musubi presets (Patreon, date not shown); note.com RTX 4070 reports (date not
  shown, page refused).
- No report of a voice-only H3 run's time or VRAM was found.

## 4. Measuring that the voice matches (R29 §4, made concrete)
- SpeechBrain ECAPA (`speechbrain/spkrec-ecapa-voxceleb`, RVCBench's verifier): `SpeakerRecognition`
  `.verify_files(a, b)`; 16 kHz input; returns the cosine score and a decision `score > 0.25` by default
  (`speechbrain/inference/speaker.py:61-99`, `:101-133`).
- WeSpeaker: `wespeaker --task similarity --audio_file a.wav --audio_file2 b.wav`; resampled to 16 kHz, VAD on by
  default (docs/python_package.md:22, :49-50); prints `(cos+1)/2`, range 0-1 (`wespeaker/cli/speaker.py:180-191`).
- Resemblyzer: `VoiceEncoder().embed_utterance(preprocess_wav(f))`; 16 kHz (`resemblyzer/hparams.py:9`); 256-dim
  embedding, similarity = dot product (README.md:47-52; demo01_similarity.py:43-47).
- WeSpeaker can load CAM++ (`--campplus`, `campplus_cn_common_200k`) and a w2v-BERT2 model (python_package.md:39, :45).
- The engine's CAM++ takes an 80-bin Kaldi fbank of 16 kHz audio, mean-normalised, and gives a 192-dim vector
  (upstream `models/TTS/index_tts2/infer_v2.py:271`, `:529-536`); it is used as conditioning, not as a score.
- Words: the speech route loads Whisper medium (upstream `models/minimax_h3/dialogue.py:204-207`); Fizgig ships
  Whisper base (above).
- Thresholds: no fixed "same voice" bar. WeSpeaker's 0-1 score is a rescaled cosine, so it is not on SpeechBrain's
  scale. arXiv 2609.27230 (September 2026; summary only): under the Seed-TTS protocol same-speaker
  pairs score about 0.7.
- Built-in evaluation in the trainers: none computes a speaker score. Fizgig renders previews with sound
  (MINIMAX_H3.md:76, :134); its likeness score is ArcFace on faces only (`web/gallery_likeness.py:1-4`). musubi writes
  muxed MP4 samples (:546) and warns adapter-run samples show the de-distilled model (:561). ai-toolkit saves previews
  as MP4 with audio (`minimax_h3.py:134-145`). SimpleTuner validation renders audio in audio-only runs (quickstart :64).

## 5. Not known
- Whether any trainer's voice LoRA changes the voice on WanGP's speech route; no file from any trainer was loaded.
- Whether SimpleTuner's default-format H3 LoRA loads in WanGP at all (by reading, its keys miss the renaming).
- Whether the engine's `campplus_cn_common.bin` is the same weights as WeSpeaker's `campplus_cn_common_200k`.
- Time and VRAM of a voice-only run on any trainer; dataset size for musubi-tuner, ai-toolkit, SimpleTuner.
- Whether transcribed words in captions are needed for a voice LoRA; no trainer says.
- Any similarity score for an H3 voice LoRA.

Sources (web): [Fizgig](https://github.com/shootthesound/Fizgig),
[musubi-tuner docs/minimax_h3.md](https://github.com/kohya-ss/musubi-tuner/blob/main/docs/minimax_h3.md),
[ai-toolkit](https://github.com/ostris/ai-toolkit),
[SimpleTuner MINIMAX_H3](https://github.com/bghira/SimpleTuner/blob/main/documentation/quickstart/MINIMAX_H3.md),
[SpeechBrain](https://github.com/speechbrain/speechbrain), [WeSpeaker](https://github.com/wenet-e2e/wespeaker),
[Resemblyzer](https://github.com/resemble-ai/Resemblyzer),
[comfyui-wiki Fizgig v5](https://comfyui-wiki.com/en/news/2026-08-30-fizgig-v5-full-finetuning) (not fetched),
[YouTube voice & likeness](https://www.youtube.com/watch?v=lVqSgsPpF0c) (not fetched),
[arXiv 2609.27230](https://arxiv.org/pdf/2609.27230) (not fetched),
[musubi Discussion #1061](https://github.com/kohya-ss/musubi-tuner/discussions/1061) (outside window).
