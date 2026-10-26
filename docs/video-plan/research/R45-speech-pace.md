# R45 — The speech engine's pace: every figure, how a line's length is set, what can be measured, 2026-10-17

Research note. Engine: upstream WanGP `af2ed29` (commit dated 2026-10-12), read in a clone.
Maestro read in a shallow clone in `/tmp/r45/maestro`: `main` at `31d7396` (2026-10-05), and PR #173's head fetched
with `git fetch origin pull/173/head`: `8e6042a` (2026-10-06, "Plan H3 voice passes at 3 words per second"). The PR's
open/merged state was not checked here (the GitHub API refused this repo); R30 recorded it as open. Syllable
packages read from their wheels: pyphen 0.18.1, syllables 1.1.5, textstat 0.7.13. ffmpeg 6.1.1 run locally.
Web: no source dated 2026-08-18 or later was found that gives a speaking rate; ffmpeg.org and voxbooster.com did not
resolve from this container. Facts only.

## 1. Every pace figure, and what it is used for
Rates converted: 2.1 w/s = 126 wpm; 2.2 = 132; 2.6 = 156; 2.8 = 168; 3.0 = 180; 0.22 s/syllable = 4.55 syll/s.

| Where | Figure | Used for |
|---|---|---|
| upstream `models/minimax_h3/dialogue.py:23` | `H3_DIALOGUE_WORDS_PER_SECOND = 2.6` | a turn's planned length (`:148-151`) |
| `dialogue.py:150` | 0.18 s per `.!?;:` in the turn's text | added to the planned length |
| `dialogue.py:151` | + 1.4 s per turn | added to the planned length |
| `dialogue.py:17-18` | turn held between 4.0 and 45.0 s | floor and cap of a planned turn |
| `dialogue.py:19` | 300 s | cap of the whole assembled line |
| `dialogue.py:22` | 0.18 s of zeros | pause inserted between turns (`:440-442`) |
| `dialogue.py:24-25` | 0.14 s pad; RMS 0.012 "quiet" | Whisper trim around the expected words (`:324-338`) |
| `dialogue.py:284-285` | a word lasting ≤ 0.5 + 0.15 s × its letters, probability ≥ 0.35 | a "reliable" boundary word for the trim |
| `hub/worker/adapters/turns.py:19-22` | 2.6, 0.18, 1.4, 4.0 (mirrors of the above) | `planned()` (`:38-41`) and grouping (`blocks`, `:61-73`) |
| `hub/settings.py:44`, `:217` | `speech_turn_seconds` 5.0, 4.0–45.0 | a line planned above it is split into turns (`tasks.py:261-262`) |
| `docs/video-plan/system-prompt-video-paragraph.md:76` | "About 2.6 words per second" | the Open WebUI block, speech drafts |
| same file `:68` | "about 2 words per second of the clip" | the same block, video drafts |
| Maestro `app/services/dialogue_timing.py:6-7` (`31d7396`) | 2.8 default, 3.0 max w/s | Maestro's dialogue pace and admission cap |
| Maestro `voice_audio.py:122-127` (PR head `8e6042a`) | words / 3 + 0.6 s, at least 5 s (`:13`) | a speech pass's planned length |
| Maestro `voice_audio.py` before `8e6042a` | words / 2.8 + 0.12 s per punctuation + 1.4 s | the same, replaced |
| Maestro `voice_audio.py:178-179`, `:194` | refuse > 3 w/s of the chosen duration; minimum words / 3 per segment | admission |
| HocusPocus, per R21 §2 (unverified, R23/R25) | 0.22 s per syllable; 2.1 w/s budget | its clip length and word budget |
| upstream `models/ltx2/scenema_audio.py:70`, `:450` | 2.2 w/s fallback, + 0.3 s per sentence | Scenema sentence length when Kokoro is absent |
| `scenema_audio.py:68`, `:546-549` | Kokoro's own synthesis length × pace 1.5; fallback (words / 2.2 + 0.5) × pace | Scenema total length; Kokoro measured at 24 000 Hz (`:410-425`) |
| upstream `models/ltx2/dramabox_audio.py:137-160` | 14 chars/s (×0.6 under 40 chars, ×0.8 under 80), + 0.3 s per `.!?`, + 2.0 s, at least 3 s | DramaBox segment length; × `duration_multiplier` 1.1 (`ltx_audio_tts_handler.py:45`, `dramabox_audio.py:263`) |
| upstream `models/TTS/index_tts2/utils/text_utils.py:31-40` | syllables (textstat) ÷ 5.5 to ÷ 3 syll/s; × 0.8517 for Chinese | `get_text_tts_dur`; no caller found in the clone |
| `models/TTS/index_tts2/pipeline.py:35-37`, `:404-408` | 29.67 sound tokens per text token; at least 10 s | IndexTTS2 per-segment token budget |
| `models/TTS/omnivoice/utils/duration.py:40-60`, `:208-248` | per-character weights (Latin 1.0 "~40-50ms", space 0.2, punctuation 0.5, digit 3.5), scaled by the reference's text/duration | OmniVoice length when none is given; without a reference, "Nice to meet you." = 25 tokens (`modeling_omnivoice.py:910-922`) |
| `models/TTS/chatterbox/tts.py:249` | `max_new_tokens=1000` | a token cap; no length from text |
| `models/TTS/ace_step_handler.py:160` | "roughly 6-10 syllables per line" | lyric-writing guidance |

- `hub/modules/assistant/turns.py` holds no pace figure: it counts kept chat exchanges (`KEEP` 6, `CUT` 120 chars,
  `:19-20`). No other pace figure was found under `hub/` (grep for words per, per word, wps, syllab, per second).
- Upstream video speech: no words-per-second figure (R22 §"Words per second"); the 2.6 is the audio route's only.
- Maestro's commit message for `8e6042a`: "H3 speaks cloned voices faster than that and filled the unused seconds
  before the script with invented speech, so Whisper could not trim the lead-in. A 30-word script planned at 13.1 s
  came out as gibberish; the same request at 10 s was clean." One reported run; no measured rate given.
- Kugelaudio and Qwen3 `tokens_per_second` (`kugelaudio/pipeline.py:214-219`, `qwen3/pipeline.py:178-199`) are codec
  rates that turn a seconds cap into tokens, not text-to-time estimates.

## 2. How a line's length is set today
**Speech route (engine).**
- The Hub always writes `Speaker 1:` (`hub/worker/adapters/tasks.py:51`, `:265`, `:267`), so the engine takes its
  dialogue path: `pipeline.generate` → `generate_dialogue` for an audio-only model with a dialogue prompt (upstream
  `pipeline.py:760-768`).
- `duration_seconds` the Hub sends is the model's slider maximum (`hub/modules/generate_image/speech.py:54`, from
  `catalogspeech.py:38`; upstream slider 4…300, `minimax_h3_handler.py:368-372`; checked `:874-880`). In the engine
  it is only a cap: turn lengths are `min(natural, remaining)` (`dialogue.py:159-169`, `:375-386`), the joined
  output is cut at it (`:443-444`).
- Each turn's length is planned from its text: `words / 2.6 + 0.18 × stops + 1.4`, held 4…45 s
  (`dialogue.py:148-151`; words counted by `_normalize_words`, `:220-222`, brackets removed, `:129`).
  The pass then makes `round(seconds × 24)` frames (`pipeline.py:794-795`; fps 24, `minimax_h3_handler.py:365`),
  rounded up to 17n+5 (`pipeline.py:798`; `shared/utils/frame_scheduler.py:16-20`): up to 16 frames (0.67 s) longer
  than planned.
- After generation, Whisper (medium, `dialogue.py:204-217`) aligns the expected words and trims surplus before the
  first and after the last word, only when at least half the words match (`:301-343`, `:309`), keeping 0.14 s pads
  (`:24`). The line's final length is the trimmed turns plus 0.18 s per join (`:440-445`), reported back as
  `duration_seconds` (`:449`). So the output length follows the speech actually produced, not the plan, whenever the
  trim fires.
- **Hub side:** a line whose `planned()` is above `speech_turn_seconds` (default 5.0) goes as groups of whole
  sentences, each planned ≤ the target (`tasks.py:261-266`; `turns.py:61-73`). With the default, a group with one stop
  holds at most (5.0 − 1.4 − 0.18) × 2.6 ≈ 8.9 words (arithmetic). A group planned under 4 s is still made 4 s
  long by the engine (`dialogue.py:151`); the Hub joins a last group under 4 s to the one before (`turns.py:71-72`).
- Not built: a 0.10 s crossfade in place of each 0.18 s join would shorten the line by the overlap per join.

**A clip driven by a sound.** The clip's frames are the shortest model lattice length that holds the whole
sound: `ceil(seconds × fps)`, raised to `min + k·step` (`hub/modules/generate_image/clipsound.py:61-67`; called at
`:54`); a sound shorter than that is padded with silence (`hub/core/sound.py` `pad`, via `_covering`,
`clipsound.py:58`); a sound above the largest window is refused (`:55-57`). The worker floors the same seconds to
the same lattice (`hub/worker/adapters/tasks.py:195-205`). The sound's length is read unrounded
(`sound_exact`, `clipsound.py:50`).

## 3. What defines and measures pace
**What docs hold.**
- No spoken line run on the server is recorded with its text, word count or number of turns (BACKLOG 27, 29).
- For scale only (arithmetic): 14 s of speech is 36.4 words at 2.6 w/s, 42 at 3.0, 30.8 at 2.2.

**Quantities.**
- Words (the engine counts letters/digits runs with apostrophes, `dialogue.py:220-222`); syllables; characters;
  stops (`.!?;:`, the engine's 0.18 s each); number of turns (the engine's 1.4 s each).
- Speaking rate counts total time; articulation rate excludes silent pauses. The same Switchboard conversations give
  193 wpm (words / total time), 236 wpm (excluding silent pauses), 164 wpm (per-speaker turn time) (LDC Interspeech
  2006 paper, search-summary only).
- Speech duration excluding silence, and the pauses themselves (count, lengths), including the engine's 0.18 s joins
  and 0.14 s pads, which are part of the file as played.

**Local tools and how each reports.**
- **Whisper (engine's).** openai-whisper `==20250625` (upstream `requirements.txt:37`), medium checkpoint loaded by
  `shared/deepy/transcription.py:83-94` for the speech route (`minimax_h3_handler.py:1139-1141`). Called with
  `word_timestamps=True`, it returns `segments[].words[]` each with `word`, `start`, `end`, `probability`
  (`dialogue.py:272-279`). Whisper medium is in the Hub's pre-check list
  (`hub/worker/adapters/upstream.facts.json:225`).
  The Hub's worker is stdlib-only (CLAUDE.md) and has no Whisper call of its own.
- **ffmpeg `silencedetect`.** Options (ffmpeg 6.1.1, `-h filter=silencedetect`): `noise`/`n` (default 0.001, also
  given in dB), `duration`/`d` minimum silence (default 2 s), `mono`/`m` per channel (default false). It prints to
  the log `silence_start: <s>` and `silence_end: <s> | silence_duration: <s>` (run here on a test tone).
- **textstat 0.7.13** `syllable_count(text)`: CMU dictionary stress digits per word, else pyphen hyphenation points
  + 1 (`backend/counts/_count_syllables.py:10-34`); MIT. Upstream IndexTTS2 imports it (`text_utils.py:3`); it is not
  in upstream `requirements.txt` (grep).
- **pyphen 0.18.1**: hyphenation; `positions(word)` and `inserted(word)` (`pyphen/__init__.py:157`, `:272`); syllable
  count is a derived use, not its stated purpose ("Pure Python module to hyphenate text"); GPL/LGPL/MPL.
- **syllables 1.1.5** `estimate(word)`: one English word → estimated syllables (`syllables/__init__.py:184`); GPLv3.

## 4. Published speaking-rate figures
- **In window (2026-08-18 on):** none found that measures English conversational or TTS speaking rate.
- A page "Speech Rate Statistics (2026)" (voxbooster.com) gives 130–150 wpm and 4.4 syllables/s for conversational
  English, attributed to the Journal of Phonetics: search-summary only; the page did not resolve, its exact date and
  study are not known.
- Older, search-summary only: 300 syllables/minute (≈ 5 syll/s) for native English conversation (D. Jones, via a
  Lund University record); 4–6 syll/s typical for West Germanic conversation, mean syllable ≈ 200 ms (MPG paper);
  5.2–7.8 syll/s for L1 read speech across languages (Bradlow, Interspeech 2019); Switchboard figures in §3.
- Recent TTS papers found treat rate as a control input (words / utterance duration offset by the training mean;
  phonemes per speech length) or control it per token (VoXtream2, arXiv, March 2026; MAGIC-TTS, April 2026): outside
  the window and giving no reference rate (search-summary only).
- What the repo already uses: 2.6 w/s (engine), 2.8/3.0 w/s (Maestro), 2.1 w/s and 0.22 s/syllable (HocusPocus via R21).
  R23 lists speech pace as "not an engine fact … measured on the [GPU]"; R25: "no measurement exists".

## 5. How the first cut sets a clip's length from its lines
- The clip's seconds are set from its lines, or from the Sound box when a sound is held; with neither, the Seconds
  setting stands (`hub/modules/generate_image/shotcheck.py:7-11`).
- A shot is refused before GPU work when its lines need more seconds than one clip holds (`OVER`, `LONG`,
  `shotcheck.py:42-43`).
- The estimate of a line is the speech engine's own (words / 2.6 + 0.18 per stop + 1.4 s, `turns.planned`), the best
  figure in the repo; how long H3 takes to say a line is not known.
- Length: `turns.planned()` over all lines, summed, plus `LEAD_SECONDS` = 1.0 s (`need`, `shotcheck.py:44`,
  `:159-161`), up to the model's lattice; above the one-pass maximum, refused. Each `planned()` includes the 1.4 s
  turn allowance (`turns.py:21`, `:41`), so n lines carry n × 1.4 s + 1.0 s beyond words and stops.
- The 2.6 figure is the audio route's; upstream gives no rate for speech inside a video clip (R22).

## 6. Not known
- The words, syllables and speech-only duration of the 14 s and 20 s lines run on the server: not recorded. An 18.6 s line is
  not mentioned anywhere in the repo.
- H3's actual pace on the speech route, with or without a voice sample; whether it differs from 2.6 w/s, and whether
  Maestro's "faster than that" for cloned voices holds on the server: no measurement exists.
- H3's pace when speaking inside a video clip (Ref2VA/FL2VA): no engine figure, no measurement.
- How often the Whisper trim fires on the turns, so how far the output length departs from the plan.
- PR #173's state today (merged or open).
- OmniVoice's tokenizer frame rate (not read), so its weights in seconds.
- A published conversational or TTS rate dated in the window.

## Sources
Repo: `hub/worker/adapters/turns.py`, `hub/worker/adapters/tasks.py`, `hub/modules/generate_image/speech.py`,
`hub/modules/generate_image/clipsound.py`, `hub/settings.py`, `hub/modules/assistant/turns.py`,
`hub/modules/generate_image/shotcheck.py`; BACKLOG 27, 29; R21, R22, R23, R25, R30; `docs/video-plan/system-prompt-video-paragraph.md`. Engine: upstream
`af2ed29` files cited above. Clones: Maestro `31d7396`, PR #173 head `8e6042a`
([PR #173](https://github.com/Blizaine/Maestro/pull/173)); wheels pyphen 0.18.1, syllables 1.1.5, textstat 0.7.13.
Web (search-summary only, none opened):
[VoxBooster speech rate statistics 2026](https://voxbooster.com/blog/speech-rate-statistics-2026/),
[LDC Interspeech 2006](https://www.ldc.upenn.edu/sites/default/files/interspeech2006-towards-integrated-understanding.pdf),
[Lund record](https://lup.lub.lu.se/record/529462),
[MPG speech rate paper](https://pure.mpg.de/rest/items/item_2256527/component/file_2291716/content),
[Bradlow Interspeech 2019](https://www.isca-archive.org/interspeech_2019/bradlow19b_interspeech.pdf),
[arXiv 2206.14165](https://arxiv.org/pdf/2206.14165), [MAGIC-TTS](https://www.alphaxiv.org/abs/2604.21164.md),
[arXiv 2603.13518](https://arxiv.org/pdf/2603.13518).
