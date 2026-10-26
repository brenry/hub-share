# R42 — Audience reactions for a production with an audience: H3's soundscape, local audio models, the Hub's mix, 2026-10-17

Research note on a separate audience bed. Engine: upstream
WanGP `af2ed29` (commit date 2026-10-12), read in a clone at `/tmp/upstream`: `defaults/`, `models/minimax_h3/`,
`models/TTS/stable_audio3_handler.py`, `models/ltx2/`, `postprocessing/{audio_processors.py,mmaudio,prismaudio,
custom_soundtrack}`, `shared/utils/audio_video.py`, `shared/deepy/video_tools.py`, `wgp.py`. Builds on R35 (§2: H3 has no form for applause or laughter; §3: with a kept soundtrack the engine makes
sound only after the track); those are not repeated. Shallow clones in `/tmp/r42/` for last-commit dates.
Web: huggingface.co, runware.ai, morphic.com, fal.ai and krea.ai were refused by the proxy (DNS); GitHub issue
search was refused (GraphQL and `search/issues` closed; Wan2GP's issues API not enabled). Web items
are search-result summaries unless marked fetched; none was fetched. Facts only.

## 1. What H3's soundscape text produces for an audience
- Upstream at `af2ed29`: no H3 file carries applause, cheering, boos, a crowd or a seated audience. Grep of
  `defaults/`, `models/minimax_h3/`, `shared/` for `applau|audience|crowd|laugh|cheer|boo|clap` and one TV-genre word, H3 hits only:
  - laughter of the person in shot, `overall_soundscape`: "…distant seagulls, and [the person's] soft laughter."
    (`defaults/minimax_h3_control.json:14`, same text `defaults/minimax_h3_control_pruned.json:14`), and in the
    description: "looks straight into the lens and laughs with carefree joy" (same lines).
  - "audience" only as the listener of score: "non_diegetic_music: Audience-only score, or N/A."
    (`models/minimax_h3/prompt_enhancer.py:114`; also `:64`, `:258`, `:296`, R35 §1).
  - "crowded" as a visual adjective (`prompt_enhancer.py:236`).
- Non-H3 defaults with a reaction word, verbatim:
  - Ovi: "The crowd roars in response, fists in the air." (`defaults/ovi.json:16`; `ovi_1_1.json:16`,
    `ovi_fastwan.json:12`, `ovi_1_1_fastwan.json:14`) — the only shipped crowd reaction.
  - JoyAI Echo: "bows to the empty seats, and says, \"Ladies and gentlemen, please applaud responsibly…\""
    (`defaults/joyai_echo.json:11`) — applause as spoken words, no applause sound.
  - DramaBox: "[the speaker] claps [the speaker's] hands together loudly"; "[The speaker] lets out a short, dismissive laugh"
    (`defaults/dramabox_audio.json:11`); Scenema "[Almost laughing, incredulous]" (`defaults/scenema_audio.json:11`);
    OmniVoice `[laughter]` (`defaults/omnivoice.json:10`). All a speaker's own sound.
- Web, 2026-08-18 onward: no report, issue or example was found that shows what H3 renders for "applause",
  "crowd laughs", "boos" or a seated audience. What was found (search summaries, dates not obtained unless given):
  - Runware's H3 "Sound and voice" guide: sound is directed by a sound clause at the end of the prompt, a sound named
    next to its action lands in time with it; an example has a cheering crowd as background. Not fetched.
  - minimaxh3.studio sample prompt: "the massive roar of the crowd after the goal" (third-party site).
  - A Hugging Face H3 discussion (#47 or #76, date not obtained) writes `non_diegetic_music` as a light, upbeat
    piano track in a TV-comedy style (paraphrase).
  - Krea's H3 guide: an example with "no added music, applause, or spoken words" (the R35 §5 negative line).
  - H3 release date: 2026-07-31 per Renderforest (search summary).
- No source compares H3's applause or laughter with a recorded one; no example pairs an audience with dialogue.

## 2. Local audio generators: in WanGP `af2ed29`, and outside it
| Model / processor | What it makes | Inputs | Length | Defined at |
|---|---|---|---|---|
| Stable Audio 3 Small SFX | "impacts, whooshes, ambience, transitions, foley…" | text; `AE` edit, `AI` inpaint (start/end s), `AC` continue a source audio | 1–120 s, 44.1 kHz stereo | `defaults/stable_audio3_small_sfx.json:5`; `stable_audio3_handler.py:29-35`, `:64-65`, `:173` |
| Stable Audio 3 Medium | "longer music, cinematic beds, evolving textures… mixed music/SFX" | same modes; needs Flash Attention 2 | 1–380 s | `defaults/stable_audio3_medium.json:5`; `:64-65` |
| Stable Audio 3 Small Music | instrumentals, loops | same modes | 1–120 s | `defaults/stable_audio3_small.json:5` |
| H3 audio generator (speech route) | "speech, ambience, Foley, or music from the prompt alone"; up to 3 `<Audio N>` refs | text, refs ≥ 2 s, 15 s shared | total ≤ 300 s (`dialogue.py:19`); a segment above 15 s "experimental"; 32 kHz stereo | `minimax_h3_handler.py:289-297` |
| MMAudio (post-process) | "Generate and remux a soundtrack that follows the video's visual content" | the video + prompt + negative prompt | the video's length (≥ 1 s) | `postprocessing/mmaudio/audio_processor.py:21-35`, `:84-86`; modes `mmaudio/__init__.py:1-9` |
| PrismAudio (post-process) | "a prompt-guided soundtrack for the video" | video + prompt | the video's length | `postprocessing/prismaudio/audio_processor.py:65-74` |
| LTX-2 `2` | "Generate Audio based on Control Video and Text Prompt" | control video + prompt | the clip | `models/ltx2/ltx2_handler.py:661-666`; `infos.py:173` |
| Joint AV (Ovi, Prism `<sfx>`, K6 `<AUDCAP>`) | sound made with the picture | prompt | the clip | `defaults/ovi.json:16`, `prism.json:17`, `k6_pro_distill.json:12` |
- None of these is a crowd or laughter model by its description; none has an audience example in its defaults.
- The soundtrack post-processes replace sound, they do not mix: `generate_soundtrack` writes a WAV
  (`wgp.py:6321-6340`, `:8730-8747`), then `combine_video_with_audio_tracks` maps only `0:v` from the video plus the
  new track(s) (`shared/utils/audio_video.py:657-693`, `-map 0:v` at `:675`), so the clip's own sound is dropped.
- HunyuanVideo-Foley, ThinkSound, AudioX are not in WanGP at `af2ed29` (grep of `.py`, `defaults/`).
- Upstream mixing (Deepy assistant): `remux_media(... mode="mix", gains_db, offsets_s, fade_in_s, fade_out_s,
  ducking, normalize_lufs)` (`shared/deepy/video_tools.py:540-544`); per-file `volume=…dB`, `adelay`, `afade`
  (`:744-757`); ducking lowers named tracks under the speech intervals of named files, `depth_db` 1–40 (default 10),
  `attack_s` 0.2, `release_s` 0.6 (`:680-697`); `amix … normalize=0` "Files add at their own levels" (`:763-764`); a
  -2 dBTP limiter (`:771-772`). Exposed as Deepy's `replace_audio` (`shared/deepy/engine.py:4982`). File last changed
  2026-10-12. A `multitrack` mode keeps each source as its own stream (`:715-731`).
- Outside WanGP, last commit of the default branch (shallow clones, 2026-10-17): MMAudio `974010a` 2026-02-23;
  HunyuanVideo-Foley `df7b005` 2025-09-29; ThinkSound `4e2cfd5` 2026-03-24 ("Release PrismAudio"); AudioX `3bdfb70`
  2026-03-10; stable-audio-tools `3241adb` 2026-05-26. None active in the last 60 days. Upstream WanGP itself:
  `stable_audio3_handler.py` last changed 2026-10-11, `postprocessing/prismaudio` and `mmaudio` 2026-10-10.
- A separate audience bed mixed under kept dialogue: no dated source (2026-08-18 on) describing this workflow was
  found. Found, undated or out of window (search summaries): Resolve guides put dialogue and music on separate tracks
  and duck music from the dialogue track (davinciresolveclub.com); imgix's "audio mark duck" keys a sidechain
  compressor on the speech track; ComfyUI nodes that mix with per-track volume (core "Audio Adjust Volume" in dB,
  TKNodes Audio Merge/Fuse, DJZ Combine Audio Tracks, Yvann Audio Remixer), none found doing automatic ducking; stock
  laughter/applause libraries (Uppbeat, Artlist, Storyblocks, Sound-Ideas) and ElevenLabs' hosted applause
  generator. A 2023 generated TV-comedy stream used an automatic laugh track that "fired at inappropriate times"
  (minimaxir.com, 2024-08).

## 3. How the Hub mixes sound today
- Edit Video's Save: track 2's sounds trimmed, set to 48 kHz stereo (`SOUND_FORMAT`, `hub/worker/joincmd.py:30`;
  `_sound`, `:90-93`), delayed to `at_ms` by `adelay` and mixed under track 1 by
  `amix=inputs=n:duration=first:dropout_transition=0:normalize=0`, else `…,volume=n` (`joincmd.py:139-149`; doc
  `:17-19`). Equal levels; the file keeps track 1's length.
- A track-2 item carries `path, at_ms, in, out, fps` only (`joincmd.py:7`; `hub/modules/sequence/join.py:9`): no
  volume, fade, pan or ducking field. R34 §1 lists the same lacks.
- `normalize` support is asked of ffmpeg once per worker (`hub/worker/join.py:98-103`, `:131`).
- Generate sends a clip's own sound only: `FORCED_VIDEO = {"audio_prompt_type": "", "postprocess_audio": ""}`
  (`hub/worker/adapters/upstream.py:58`; fork: `MMAudio_setting: 0`, `fork.py:34`). The Hub drives H3 and
  viggle_animate (`upstream.facts.json` `models`) and the H3 speech route (`hub/modules/generate_image/speech.py`);
  no Stable Audio, MMAudio or PrismAudio path.
- A continue refuses a sound in the Sound box: "A continued clip takes no sound"
  (`hub/modules/generate_image/clipsound.py:25`, `:44`).

## 4. Continuity across a continued clip
- The Hub's continue is one window of `frames + overlap - 1` from `video_source` (`hub/worker/adapters/tasks.py:
  217-227`); H3 Ref2VA overlap default 18 frames at 24 fps, step 17 (`minimax_h3_handler.py:719-720`, `:365`).
- Audio carried: window 1 of a continue slices the source clip's first audio track under the overlap
  (`wgp.py:7910-7914`); later windows take the previous window's generated audio from the overlap start
  (`wgp.py:8496-8499`, read at `:7908-7909`). H3 sets `audio_window_alignment` and `audio_overlap_repair_ms` 25
  (`minimax_h3_handler.py:650-651`; repair `wgp.py:7918-7923`).
- In the pipeline the overlap waveform is encoded; all but the last frame's latents enter as `"history"`, the
  boundary as `"first"` (`models/minimax_h3/pipeline.py:969-985`); the output keeps the source's history audio
  in front (`:1724-1730`). "H3 native continuation regenerates only the last overlap frame's audio"
  (`pipeline.py:825`; Hub `soundtail.py:1-16`). So the model hears about 0.7 s of the previous crowd, not more.
- Soundscape text per window: each window takes `prompts[window_no]`, else the last prompt (`wgp.py:7816`); in "W"
  / "PW" modes each line or paragraph is a new window's prompt (`shared/utils/prompt_parser.py:29`, `:76`). The Hub
  sends `multi_prompts_gen_type: "FG"` and one prompt per continue (`tasks.py:226`). Nothing in the engine copies
  one window's `overall_soundscape` into the next.
- Whether repeating the same soundscape words keeps an audience the same (size, room, laugh character): no source
  found. The Hub's speech route keeps a voice by a reference cut from the first turn (R29 §4, `dialogue.py:346-348`);
  no equivalent exists for ambience.

## Not known
- What H3 renders for "applause", "the audience laughs", "boos", "cheering" in `overall_soundscape`, with or
  without dialogue in the same clip: no upstream example, no dated report, not tested here.
- Whether an audience written in the soundscape competes with or masks the `<d>` line (level, intelligibility).
- Whether Stable Audio 3 Small SFX or the H3 audio generator makes a usable laugh or applause bed: no example, no
  report; neither description names an audience.
- Whether the 0.7 s of history audio plus the same words keeps a crowd consistent across a continue.
- Any dated (2026-08-18 on) account of people mixing an audience bed under a kept dialogue track, and with which
  tool: none found; GitHub issues and the refused hosts could not be searched.
- The content of the Runware, Morphic, fal.ai and Krea H3 guides beyond their search summaries.

## Sources
- Upstream WanGP `af2ed29` (2026-10-12): `defaults/{minimax_h3_control,minimax_h3_control_pruned,ovi,ovi_1_1,
  ovi_fastwan,ovi_1_1_fastwan,joyai_echo,dramabox_audio,scenema_audio,omnivoice,prism,k6_pro_distill,
  stable_audio3_small_sfx,stable_audio3_small,stable_audio3_medium}.json`; `models/minimax_h3/{prompt_enhancer,
  minimax_h3_handler,pipeline,dialogue}.py`; `models/TTS/stable_audio3_handler.py`; `models/ltx2/{ltx2_handler,
  infos}.py`; `postprocessing/{audio_processors.py,mmaudio/,prismaudio/audio_processor.py,custom_soundtrack/}`;
  `shared/utils/{audio_video,prompt_parser}.py`; `shared/deepy/{video_tools,engine}.py`; `wgp.py`.
- Hub: `hub/worker/joincmd.py`, `hub/worker/join.py`, `hub/modules/sequence/join.py`,
  `hub/worker/adapters/{upstream,fork,tasks,soundtail}.py`, `upstream.facts.json`,
  `hub/modules/generate_image/clipsound.py`. Prior notes: R29, R34, R35.
- Shallow clones `/tmp/r42/`: https://github.com/hkchengrex/MMAudio, https://github.com/Tencent-Hunyuan/HunyuanVideo-Foley,
  https://github.com/FunAudioLLM/ThinkSound, https://github.com/ZeyueT/AudioX,
  https://github.com/Stability-AI/stable-audio-tools (FunAudioLLM/PrismAudio: clone refused, auth prompt).
- Search summaries only (fetch refused): https://runware.ai/docs/models/minimax-h3/guides/sound-and-voice,
  https://minimaxh3.studio/, https://huggingface.co/MiniMaxAI/MiniMax-H3/discussions/47,
  https://huggingface.co/MiniMaxAI/MiniMax-H3/discussions/76,
  https://www.krea.ai/blog/minimax-h3-what-s-new-benefits-and-6-prompts-to-try-in-2026,
  https://fal.ai/learn/devs/minimax-h3-prompting-guide, https://morphic.com/resources/how-to/minimax-h3-guide,
  https://www.renderforest.com/minimax-h3, https://docs.imgix.com/apis/video/audio/audio-mark-duck,
  https://davinciresolveclub.com/davinci-resolve-audio-ducking.md,
  https://www.runcomfy.com/comfyui-nodes/ComfyUI/audio-adjust-volume, https://comfy.icu/node/TKAudioFuse,
  https://comfy.icu/node/CombineAudio, minimaxir.com (2024-08 post on that stream).
