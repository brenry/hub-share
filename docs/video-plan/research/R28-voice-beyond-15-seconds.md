# R28 — Voice consistency beyond a 15-second sample: what is documented, 2026-10-17

Written from web sources fetched on 2026-10-17 and the engine source at upstream
`af2ed29`. Facts only. The aim: the project's limits pushed as close to a premium service tier as
possible.

## 1. The ceiling in the engine
H3's speech route uses at most 15 s of a reference: `H3_DIALOGUE_MAX_REFERENCE_SECONDS = 15.0`
(upstream `models/minimax_h3/dialogue.py:20`), and `_prepare_audio_references` cuts the combined references to 15 s,
split evenly across samples (`pipeline.py:546-565`). A longer or better recording cannot raise the voice past what
15 s of conditioning gives. Within the ceiling, the sample's quality is the only lever: one voice, no music, no
crowd, a close microphone, steady delivery.

## 2. The premium tier, as one vendor states it
ElevenLabs, of its two tiers ([blog](https://elevenlabs.io/blog/instant-vs-professional-voice-cloning)):
"Instant and Professional Voice Cloning share the same underlying technology but differ in terms of training
depth." Instant "infers your voice from a small sample in real time" from "around a minute of voice data".
Professional "fine-tunes a dedicated model for hours on audio", needing about 30 minutes at least and improving up
to about 3 hours. The Hub's 15-second sample is the instant tier; the professional tier is training.

## 3. Voice LoRAs on H3: possible, not established
- H3 is trained on video and audio together; a LoRA trainer notes "clips with usable audio can teach corresponding
  sound behavior" and warns: "Do not promise speech, voice identity, or sound quality that your dataset and
  evaluation have not demonstrated" ([LoraAI](https://loraai.me/minimax-h3-lora-training), undated).
- One documented voice experiment ([Virse](https://www.virse.ai/blog/minimax-h3-guide), 2026-09-23, modified
  2026-10-06): "35 images, 26 WAV files, and one video clip"; after epoch 40 "the workflow switched toward
  audio-only training to strengthen voice characteristics." The author: "an individual training experiment rather
  than a universal recipe." No consistency results are reported. The same page advises a LoRA "when a recurring
  style, identity, motion, or voice cannot be reproduced reliably through references alone."
- A survey of H3 LoRAs ([ArtRealm](https://artrealmai.com/article/best-minimax-h3-loras-by-type), 2026-09-06) lists
  none for voice or speaker identity.
- One source says H3 "can't be fine-tuned" because "the model is closed" ([wan27](https://wan27.org/blog/minimax-h3-lora),
  2026-09-07). That is the hosted API model; the server runs open weights locally, for which LoRAs exist (R26 lists
  three). It does not apply here.

## 4. Open, for the next research step
- Whether the speech route (`minimax_h3_tts_ref2va_pruned`) loads a LoRA at all, and which weights an audio LoRA
  would touch: read in a clone at `af2ed29` (the route passes `loras_slists`/`loras_selected`,
  `dialogue.py:415-416`, so the plumbing exists; whether an audio-trained LoRA changes the voice is untested).
- What a training set needs for a voice (minutes of clean speech; transcripts or not); which local trainer supports
  H3 audio (ai-toolkit is named for H3 by RunComfy; its audio support for H3 is not documented in what was read).
- How to measure consistency without listening by ear: a speaker-embedding similarity between lines, the same way
  R27's author validates by transcription.
