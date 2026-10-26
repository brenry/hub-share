# R30 — Joins in a spoken line made of several turns: what is documented, 2026-10-17

Written for BACKLOG item 29 from the engine source at upstream WanGP `af2ed29` (cloned read-only
to a scratch folder, commit dated 2026-10-12) and web sources found on 2026-10-17. Facts only; no decision, no spec.
The question: joined turns can carry slight traces of audience sounds and sharp cut-offs; the requirement is
one natural piece with no abrupt cut.

## 1. Where the sound inside a turn comes from

**What the Hub sends.** One `Speaker 1:` block per group of whole sentences, every block the same speaker, that speaker's
sample as prompt letter `A` (`hub/worker/adapters/tasks.py:226-241`). No direction words are added when a sample is
given (`:227`). One seed for the job (`:237`).

**What the engine does with that, per turn.**
- The sample is read, resampled to 32 kHz stereo and cut to 15 s; nothing else: no denoise, no filter, no level
  change (upstream `models/minimax_h3/pipeline.py:510-526`, `:546-565`; `dialogue.py:372-374`).
- The same sample conditions every turn of Speaker 1 (`dialogue.py:387`, `:401-404`). A turn's own output becomes the
  speaker's reference only when no sample was given (`dialogue.py:427`, `setdefault`; `:346-348`).
- Each turn gets its own seed, `base + index × 1000` (`dialogue.py:170`), and is a separate engine pass of its own
  length (`:399-420`).
- The prompt the engine writes for each turn (`dialogue.py:175-201`) asks for the sample's identity only: "its words,
  timing, and background noise are not copied" (`:179`), "Generate one clean isolated dialogue turn" (`:192`), a
  "minimal neutral close-microphone studio shot" (`:196`), and as soundscape "Clean close-microphone speech, subtle
  natural breaths, **quiet neutral room tone**, no overlapping voices, and no unrelated sounds" (`:198`). So every
  turn is asked to generate a room tone of its own; nothing ties one turn's room tone to the next.
- The engine's own help text: with no reference the preset makes "speech, ambience, Foley, or music from the prompt
  alone"; with one, `<Audio 1>` is described as "the voice, delivery, music, or sound characteristics to retain"
  (`minimax_h3_handler.py:292-294`). The model itself is audiovisual: "H3 still jointly denoises a tiny 32x32 video
  internally" (`:290`, `pipeline.py:794-797`).

**What the code cannot show.** Whether the model obeys "background noise … not copied" is a property of the model's
weights, not of the code. Whether the Character 1 sample contains audience sound is not known here (the file is on the
server).

**Outside sources on a reference's background reaching the output.**
- A report on the H3 model's Hugging Face page (discussion #64, `huggingface.co/MiniMaxAI/MiniMax-H3/discussions/64`)
  that the reference audio is passed through as well as the voice copied, and garbled reference audio appears in
  "non speaking moments"; a suggested workaround was to describe the ambience in the prompt. Found by search, about
  70 days old by the search engine's dating (older than this note's 60-day window); the page itself could not be
  opened from here (network policy), so the wording is the search summary's, not checked.
- A Maestro pull request on H3 voice (`github.com/Blizaine/Maestro/pull/173`, opened 2026-10-06, open): H3 "speaks
  cloned voices faster than that and filled the unused seconds before the script with invented speech"; "Not the
  reference audio: I swapped reference clips and tried one versus two references, and neither changed it." It
  changes the duration plan to "words / 3 + 0.6 s". This is about surplus speech, not background, but it bears on
  §2's trimming: a planned length longer than the speech leaves seconds the model fills.

## 2. What in the engine can carry sound across a join

### 2.1 The speech route (the one the Hub's joined turns use)
- Turns are planned with `_natural_duration`: words / 2.6 + 0.18 s per `.!?;:` + 1.4 s, between 4 and 45 s
  (`dialogue.py:17-18`, `:23`, `:148-151`).
- After all turns are made, Whisper finds the expected words in each (`dialogue.py:432-439`, `:301-343`). The cut
  after the last word: only if surplus follows or more than 0.5 s remains (`:332`); then 0.14 s after the last word
  (`:24`, `:333-336`), moved later to the first 10 ms window whose RMS is under 0.012 (`:25`, `:288-298`) within 0.5 s
  (`:335-338`), else hard at the 0.14 s point (`:338`). The cut before the first word mirrors this (`:324-329`).
  No fade is applied at either cut.
- 0.012 RMS on a ±1 scale is about −38 dBFS (20·log10 0.012). A background at or above that level has no "quiet"
  window, so the cut lands hard at word end + 0.14 s inside the background.
- The join: a block of zeros of 0.18 s (`dialogue.py:22`, `:440`) between turns, `torch.cat` (`:441-442`). No fade,
  no overlap, no level match.
- Options a caller can set: none of these. `H3_DIALOGUE_PAUSE_SECONDS`, `BOUNDARY_PADDING_SECONDS` and
  `SILENCE_THRESHOLD` are module constants (`dialogue.py:15-25`); `generate_dialogue` takes no argument for them
  (`:351-355`). The audio-only preset has `"sliding_window": False` (`minimax_h3_handler.py:358`), and
  `generate_dialogue` passes no `input_video` / `prefix_frames_count` to a turn (`dialogue.py:399-420`), so the
  continuation path below (`pipeline.py:808-809`) is never taken: a turn hears nothing of the turn before it.

### 2.2 How the video models carry sound across a sliding window
- **Conditioning, not fading.** The next window is conditioned on the previous window's audio over the overlap
  frames: `pre_audio_guide` is the last `next_overlap_frames` of the generated audio (`wgp.py:8496-8499`), passed as
  `input_waveform` (`wgp.py:7908-7910`); the pipeline encodes it and adds it as `"history"` and `"first"` audio
  conditions (`pipeline.py:969-986`). The model so continues the same sound.
- **`audio_overlap_repair_ms`.** Per model: H3 25 ms ("one audio latent, plus the measured waveform shortfall",
  `minimax_h3_handler.py:651`), LTX-2 80 ms (`models/ltx2/ltx2_handler.py:558`), Ovi 20 ms
  (`models/wan/ovi_handler.py:52`). `audio_overlap_repair_seconds` = that value + any shortfall of the overlap audio
  (`shared/utils/audio_video.py:108-114`); conditioning stops that much before the overlap's end
  (`wgp.py:7923`, `pipeline.py:979-984`, `:1054-1056`), so the model regenerates the last 25 ms itself.
- **The splice.** `append_sliding_window_audio` keeps the old track up to `committed − repair_samples` and appends the
  new window's audio from there (`shared/utils/audio_video.py:74-105`, called at `wgp.py:8575-8580`): a plain
  `np.concatenate`, no crossfade. Smoothness comes from the new audio having been generated to continue the old.
- **`sound_join` (Hub).** `sound_join: 1` for the four H3 clip models in `hub/worker/adapters/upstream.facts.json`
  (`:173-189`), the Hub's mirror of "only the last overlap frame's" sound being made again; a source whose sound
  ends earlier is refused (`pipeline.py:824-825`).

## 3. What other people do at a join (sources)

Window: dated 2026-08-18 or later. Sources outside it are marked.

- **Silence of a set length, by kind of break.** `halacha_audio_pipeline` PR #6 (opened 2026-09-30, merged
  2026-10-01, `github.com/yedidyatob/halacha_audio_pipeline/pull/6`): without a pause the stitched chunks give an
  abrupt cut; it adds `tts.chunk_gap_paragraph_ms` (default 700) and `tts.chunk_gap_sentence_ms` (default 300).
- **A separate ambience bed under the voices.** `ConversationalLanguageLearning` PR #60 (opened 2026-10-08, merged
  2026-10-11, `github.com/Pechst1/ConversationalLanguageLearning/pull/60`): a procedural bed per place, "RMS 0.018
  for a room up to 0.055 for the market", "The bed drops −12 dB (×0.2512) in 0.12 s while a line plays and comes back
  up over 0.6 s", "Fade in 2.5 s, fade out 1.2 s". The author calls the levels first-pass, not yet checked by ear.
- **Drift between independently made chunks.** Qwen3-TTS discussion #220, reply of 2026-08-10
  (`github.com/QwenLM/Qwen3-TTS/discussions/220`; eight days outside the window): "each chunk is generated
  independently, and then the resulting audio is stitched back together"; "the narrator's baseline cadence,
  prosody, and emotional delivery drift between chunks … even though the same voice, instructions, and seed are
  being used"; asks for "some form of continuation mode, narrator state, or style reference". No fix given.
- **Outside the window, for completeness (not current):** voicebox issue #363 (2026-03-27) proposes "a small
  crossfade (e.g., 50ms)" between chunks and, in a reply of 2026-06-20, 250–400 ms between sentences and 600–900 ms
  between paragraphs; TTS-Audio-Suite's newest release is v5.6.0 of 25 July (no chunk-join change listed); a March
  2026 paper (arXiv 2603.06444) uses the previous chunk's audio as the acoustic prompt for the next; MagpieTTS-LF
  (arXiv 2606.18485, June 2026) carries model state across sentence chunks. Room-tone fill practice (lay a matched
  room tone under the gap and crossfade both ends; match the noise floor before lengthening fades; do not loop one
  short piece) appears in post-production guides found by search (soundforgepro.com, soundfreakstudios.com), whose
  dates could not be read: the pages did not open from here.
- **Not found:** a source in the window that measures which join (silence, crossfade, room tone, bed) listeners
  hear as seamless, or a crossfade length for generated speech.

## 4. Not known
- Whether the "audience" heard in the take is in the sample, generated from the prompt's "room tone", or the model's
  own; that needs the sample and the turns heard apart (the server).
- Whether H3's speech route would accept the previous turn's audio as continuation (the video route's history
  conditioning, §2.2) for an audio-only pass: the code never tries it (`minimax_h3_handler.py:358`,
  `dialogue.py:399-420`), and no source was found.
- The background level of a typical H3 turn, i.e. whether the −38 dBFS quiet test (§2.1) usually finds a quiet
  window: not measured.
- Sources that could not be opened from this container (network policy): dev.to, huggingface.co, arunbaby.com,
  atlascloud.ai, minimax.io, soundforgepro.com, soundfreakstudios.com.
