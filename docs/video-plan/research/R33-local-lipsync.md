# R33 — Local audio-driven lipsync: what the engine ships and what runs beside it, 2026-10-17

Research note for D3b (one line + one picture → one lipsynced clip), in case H3's lipsync is weak.
Engine: upstream WanGP `af2ed29` (2026-10-12), read in a clone; every `defaults/*.json` (261 files) was checked for an
audio input. Model repos read in shallow clones (README, LICENSE): InfiniteTalk `50aa0a9` (2026-05-22), LongCat-Video
`6b3f4b8` (2026-05-27), LatentSync `a229c39` (2025-06-20), MuseTalk `0a89dec` (2025-09-26), EchoMimic v3 `7e89489`
(2026-03-18), StableAvatar `3862518` (2026-09-25), Sonic `c1bd2d1` (2026-01-08), OmniAvatar `1536bf3` (2025-08-06),
HuMo `845f447` (2026-01-26), daVinci-MagiHuman `209209b` (2026-04-11), Wan2.2 `1ea34ff` (2026-09-21). Web pages other
than github.com could not be fetched from this container (DNS failure / proxy 403 for arxiv.org, huggingface.co,
reddit.com, virse.ai, instavar.com, fuser.studio, atlascloud.ai, comfy.icu); items marked *(search summary)* are cited
from search-result summaries, not read. Facts only.

## 1. What WanGP `af2ed29` ships that takes speech and drives a face or body
| Def (`defaults/`) | Base | Inputs | Spk | Length / windows | Res. |
|---|---|---|---|---|---|
| `multitalk`, `multitalk_720p` | Wan2.1 i2v 14B + Multitalk | image + audio | 1-2 | windows, 25 fps | 480p/720p |
| `i2v_2_2_multitalk` (hidden) | Wan2.2 i2v + Multitalk | image + audio | 1-2 | windows | — |
| `vace_multitalk_14B` | VACE FusioniX + Multitalk | control/refs + audio | 1-2 | 81 frames | 832×480 |
| `infinitetalk`, `_multi` | Wan2.1 i2v + InfiniteTalk | image(s) or video + audio | 1 / 2 | win 81, ovl 9 | 480p |
| `fantasy` | Wan2.1 i2v + Fantasy Speaking | image + audio | 1 | ovl 1, 23 fps | 1280×720 |
| `hunyuan_avatar` | HunyuanVideo 13B Avatar | ref image + audio | 1 | 128-frame segments | 720p |
| `hunyuan_custom_audio` | HunyuanVideo Custom | ref image + audio | 1 | up to 10 s | — |
| `longcat_avatar`, `_multi` | LongCat-Video 13.6B Avatar | image + audio | 1 / 2 | win 93, ovl 13, 16 fps | — |
| `longcat_avatar_v1_5` | LongCat Avatar 1.5, 8 steps | image + audio | 1-2 | win 93, ovl 13, 25 fps | — |
| `magi_human*` (4 defs) | daVinci-MagiHuman 15B | image + opt. audio | 1 | win 25-251, 25 fps | 448×256; SR 1080p |
| `ltx2_*` (19B, 22B) | LTX-2 2.0/2.3/2.5 | soundtrack `A`, ctrl audio `K` | 1 | e.g. 241 frames | e.g. 1280×704 |
| `minimax_h3_fl2va*`, `_ref2va*` | H3 33B / pruned 20B | refs + kept track | prompt | win 124-481, 24 fps | — |

Citations, per model:
- Multitalk class = `multitalk`, `vace_multitalk_14B`, `i2v_2_2_multitalk`, `infinitetalk`
  (upstream `models/wan/wan_handler.py:53-54`); they take audio and return it (`:281-285`); fps 25, fantasy 23
  (`:333-336`); audio guidance scale for fantasy and the class (`:966-967`, default 4 at `:1433-1434`).
- Speaker choices in the UI: "One Person Speaking Only", "Two speakers, Auto Separation", "in a Row", "in Parallel"
  (upstream `wgp.py:12410-12425`, labels `:12413-12419`); a second `audio_guide2` (`:12460`); speaker boxes
  "Left:Right or a BBox" (`:12478-12479`); "Ignore Background Music (for better LipSync)" (`:12475`).
  `one_speaker_only` / `multi_speakers_only` in `defaults/infinitetalk.json:13`, `infinitetalk_multi.json:13`,
  `longcat_avatar.json:6`, `longcat_avatar_multi.json:6`.
- InfiniteTalk dubbing: "Sparse Video to Video, one Image will by extracted from Video for each new Sliding Window" and
  "Video to Video, amount of motion transferred depends on Denoising Strength" (`wan_handler.py:638-645`); defaults
  window 81, overlap 9 (`:1255-1265`); def text "Sliding Window size must be 81 frames"
  (`defaults/infinitetalk.json:12`).
  Changelog: "this feature can be used for Video Dubbing … a *Sparse Video to Video*" (`docs/CHANGELOG.md:1238`).
- Multitalk defaults: discard last 4 frames per window, `audio_prompt_type` `A` (`wan_handler.py:1245-1253`).
  Fantasy: overlap 1, `A` (`:1238-1243`); "works not only on people but also on objects" (`docs/CHANGELOG.md:1535`).
- Hunyuan Avatar: "processing 128 frames segment at a time … max 3 segments recommended as the quality will get worse"
  (`defaults/hunyuan_avatar.json:6`); fps 25, no sliding window (`models/hyvideo/hunyuan_handler.py:60-81`); defaults
  129 frames, `KI` (`:318-327`). Engine note: "just 10 GB of VRAM … up to 15s" (`docs/CHANGELOG.md:1504`).
  Custom Audio: "video length can be anything up to 10s" (`defaults/hunyuan_custom_audio.json:6`).
- LongCat Avatar: audio sources `A`, `XA`, `CAB`, `PAB`, speaker locations (`models/longcat/longcat_handler.py:70-95`);
  v1.5 distill-only 8 steps, Whisper-large-v3 encoder, DMD LoRA (`:100-110`); defaults window 93/overlap 13
  (`:202-213`). v1.0 "very slow. It needs 40+ steps" (`docs/CHANGELOG.md:849`); 1.5 "fast (8 steps distilled)"
  (`:346`, release 2026-05-22).
- Magi Human: "Driving Audio", choice "Generate Video based on Soundtrack and Text Prompt", window slicing
  (`models/magi_human/magi_human_handler.py:57-90`); "Best results will be obtained at 256p"
  (`defaults/magi_human.json:5`). Engine note: "VRAM hungry (targets RTX 5090+) … 101 frames at 1080p requires 'only'
  16 GB"; the author asks the Discord whether to keep it (`docs/CHANGELOG.md:472-476`).
- LTX-2: audio choices `A` "Generate Video based on Soundtrack and Text Prompt", `K` control video + its audio track,
  `A1OF` reference voice ID-LoRA (not on 2.5); `one_speaker_only` (`models/ltx2/ltx2_handler.py:656-690`). Engine note:
  forcing a soundtrack "works like *Multitalk* / *Avatar* except … any kind of sound" (`docs/CHANGELOG.md:841`);
  "as low as 10 GB of VRAM" (`:839`); Modality Guidance "should improve audio / video (lipsync...)" (`:704`).
- Not a driver: JoyAI-Echo (`defaults/joyai_echo*.json`) takes no `audio_guide`; a control video's audio only fills
  its memory (`ltx2_handler.py:617-648`). Ovi (`defaults/ovi*.json`) generates speech from `<S>…<E>` text; its handler
  sets no audio input (`models/wan/ovi_handler.py:50-59`).
- Postprocessing: **H3 Face Refiner** re-denoises tracked face crops with pruned Ref2VA, passing each window the
  clip's own audio slice (`postprocessing/h3_face_refiner/runtime.py:16-22`, `:226`); default prompt "Restore natural,
  sharp, temporally stable eyes, mouth, teeth" (`wgp_bridge.py:17`); up to five faces (`docs/CHANGELOG.md:7`).
  SeedVC replaces voices after generation (`docs/CHANGELOG.md:330`); it does not move the mouth.
- Absent at `af2ed29`: Wan2.2-S2V, HuMo, OmniAvatar, LatentSync, MuseTalk, Sonic, EchoMimic, StableAvatar, LTX LipDub.
  No def file, and `grep -ri` over `*.py`/`*.json`/`*.md` for `s2v`, `humo`, `omniavatar`, `latentsync`, `musetalk`,
  `lipdub`, `wav2lip` finds no model code.
- VRAM per profile: the engine states no per-model figure for Multitalk/InfiniteTalk beyond "greatly reduced the VRAM
  requirements" (`docs/CHANGELOG.md:1227`).

### How H3 itself conditions on a supplied soundtrack
- FL2VA audio sources: `A` "Generate Video based on Soundtrack and Text Prompt (Soundtrack Kept)", `K` control video's
  track, `2` generate audio for a control video (upstream `models/minimax_h3/minimax_h3_handler.py:820-831`). Ref2VA
  adds `AS` / `KS` for the same (`:770`, `:778-779`); plain `A` on Ref2VA is a voice *reference* (`:773`).
- In the pipeline, `S` means "the audio is the soundtrack: condition on it rather than reference it"
  (`models/minimax_h3/pipeline.py:1019`). The waveform is encoded (`:1046-1056`) and copied into the start of the
  audio latent (`:1136-1138`); the sampler updates only the tail past it (`:1242`, `:1264`). Video is denoised
  jointly against that fixed audio in the one single-stream transformer (R29 §2).
- Prompt rule, in the engine's own text: "identify the character and explicitly request `speaking with natural lip
  movements synchronized` … without mentioning a supplied audio track. No transcript is required; exact lip sync is
  not guaranteed" (`minimax_h3_handler.py:66`, same at `:100`, `:140`); a kept soundtrack gets no `<Audio N>` label
  (`:140`). With a pose guide, "a still mouth or a lowered face can compete with speaking motion" (`:230`).
- Audio Refinement Extra Phase keeps the video latent and re-noises audio at 0.5; "preserves fine lip motion"
  (`:275`). Hub side: R25 §1 contradiction 5 notes the Hub's soundtrack templates lack the lip-sync wording.

## 2. Local lipsync models outside WanGP
| Model | Kind | License | VRAM (repo text) | WanGP |
|---|---|---|---|---|
| InfiniteTalk (2025-08-19) | picture → talk; sparse-frame dubbing | Apache-2.0 | "very low" via Wan2GP | yes |
| LongCat-Video-Avatar 1.5 (2026-05-21) | picture/continuation, 1-2 streams | MIT | INT8 option, no figure | yes |
| daVinci-MagiHuman | picture (+text or audio) → head | Apache-2.0 | H100 timings only | yes |
| LatentSync 1.6 (2025-06-11) | dubbing, mouth inpaint, 512² face | Apache-2.0 | ≥18 GB (1.5: 8 GB) | no |
| MuseTalk 1.5 (2025-03-28) | dubbing, real-time, 256² face | MIT (code) | 4 GB laptop, ~5 min/8 s | no |
| Wan2.2-S2V-14B (2025-08-26) | picture → speech video, 480/720p | Apache-2.0 | "at least 80GB", offload | no |
| HuMo 17B / 1.7B | text+image+audio, 480/720p | Apache-2.0 | 1.7B: 480p 8 min on 32 GB | no |
| OmniAvatar 14B / 1.3B | picture → talk, 480p | Apache-2.0 | 14B: 36 GB, or 8 GB slow | no |
| EchoMimic v3 Flash (2026-01-22) | picture → talk, ≤768² | Apache-2.0 | 12 GB | no |
| StableAvatar (Wan2.1 1.3B) | picture → infinite-length avatar | MIT | not stated | no |
| Sonic (CVPR 2025) | portrait animation | CC BY-NC-SA 4.0 | not stated | no |
| LTX-2.3 IC-LoRA LipDub (summary) | dubbing from video + new text | LTX-2 community | ~16 GB (3rd party) | no |

- Sources, in order: InfiniteTalk README.md:22, :35-36, :42-43, :51, :67; LongCat-Video README.md:49, :169-171, :261;
  daVinci-MagiHuman README.md:19, :30, :88-94; LatentSync README.md:14, :108-111; MuseTalk README.md:39, :336, :523,
  :540; Wan2.2 README.md:39, :201, :259; HuMo README.md:27, :69, :86; OmniAvatar README.md:77, :98-103;
  echomimic_v3 README.md:51-55, :202; StableAvatar README.md:72, :97; Sonic README.md:14, :30.
- LongCat 1.5 replaces Wav2Vec2 with Whisper-Large "for more accurate lip synchronization" (LongCat-Video
  README.md:49). Its technical report (arXiv 2605.26486) says the base model keeps "a noticeable advantage in overall
  human-likeness and lip synchronization" over the accelerated one *(search summary)*; WanGP ships only the distilled.
- InfiniteTalk V2V "mimics the original video's camera movement, though not identically" (README.md:190).
- MuseTalk lists its own limits: 256×256 face region, suggests GFPGAN for more (README.md:523-524).
- LipDub: mask-free; regenerates lips and audio for new dialogue text; validated in English, French, Spanish, German,
  Russian; from paper JUST-DUB-IT, arXiv 2601.22143 *(search summary of docs.ltx.video; page not fetched)*.

## 3. Quality reports after 2026-08-18
- **2026-09-11**, GitHub issue #28 on ComfyUI-MiniMaxH3-Director (read): Ref2VA with a WAV and three references, prompt
  "lip syncs to the audio input" — "didn't make the [@ref] character perform lip syncing"; it worked after "manually
  mentioning <audio 1> in the prompts". No reply; closed by the author the same day.
- **Late Aug – mid Sep 2026** *(search summary)*: a community int8 Ref2VA merge on Hugging Face (Asirus) reports one
  test, a reference image plus a 10 s singing track, with "synchronized mouth movement / lip-sync"; labelled
  experimental. A ComfyUI node "MiniMax H3 • LipSync Latent Setup" swaps in encoded audio and advises audio denoise 0
  to keep timing (undated).
- **About 2026-10-06** *(search summary; virse.ai not fetchable)*: Virse "MiniMax H3 Reddit Review" lists, among user
  questions, "deformation during image-plus-audio lip-sync", eye flicker, face softness, pixelated distant characters.
  Leadde's H3 Reddit review (updated Aug 2026, day not known) lists softer distant faces and high VRAM; no lipsync
  figure.
- **2026-09-25**: StableAvatar accepted at NeurIPS 2026 (README.md:72); no new weights in that entry.
- **Sept 2026**, ComplexSync (arXiv 2609.29225) *(search summary)*: authors' own comparison against LatentSync,
  MuseTalk, DINet, Ditto, KeySync, OmniSync; says MuseTalk produces "significant visual artifacts", LatentSync "often
  fail[s] to achieve accurate lip shapes". Self-reported; no released code found in the summary.
- **2026-10-06**, PVSync (arXiv 2610.09223) *(search summary)*: a lip-sync scorer; on clips from 13 talking-head
  models its ranking agrees with human raters at Spearman 0.83 vs 0.34 for LSE-C (SyncNet). Which 13 models, and
  their ranks, not available without the paper.
- No Reddit r/StableDiffusion or r/comfyui thread dated after 2026-08-18 comparing lipsync models was found by search;
  reddit.com cannot be fetched here. No dated Discord summary found. No head-to-head of H3 against InfiniteTalk,
  LongCat or LTX-2 lipsync found.
- Older, outside the window, for context only: Instavar (May 2026) keeps LatentSync 1.6 as its local dubbing default
  and calls InfiniteTalk a heavier, different category *(search summary)*.

## 4. Not known
- How H3's kept-soundtrack lipsync scores against InfiniteTalk / LongCat 1.5 / LTX-2 on the same line and picture.
- Which models people use most for lipsync now: no dated community count or poll was found.
- The 13 models and ranks in PVSync; whether it includes H3.
- LongCat 1.5 and Magi Human output resolution limits in WanGP beyond the def defaults; VRAM for each WanGP talking
  model at the settings.
- Whether `<Audio N>` in a Ref2VA prompt (issue #28's workaround) changes lipsync or only voice timbre on the engine.
- LipDub's release date and VRAM from an official page.

Sources (web): [InfiniteTalk](https://github.com/MeiGen-AI/InfiniteTalk),
[LongCat-Video](https://github.com/meituan-longcat/LongCat-Video),
[LatentSync](https://github.com/bytedance/LatentSync),
[MuseTalk](https://github.com/TMElyralab/MuseTalk), [Wan2.2](https://github.com/Wan-Video/Wan2.2),
[HuMo](https://github.com/Phantom-video/HuMo), [OmniAvatar](https://github.com/Omni-Avatar/OmniAvatar),
[EchoMimic v3](https://github.com/antgroup/echomimic_v3), [StableAvatar](https://github.com/Francis-Rings/StableAvatar),
[Sonic](https://github.com/jixiaozhong/Sonic), [daVinci-MagiHuman](https://github.com/GAIR-NLP/daVinci-MagiHuman),
[H3-Director issue #28](https://github.com/seesee75-commits/ComfyUI-MiniMaxH3-Director/issues/28),
[LTX LipDub docs](https://docs.ltx.video/open-source-model/advanced-workflows/lip-dub-beta),
[Asirus H3 merge](https://huggingface.co/Asirus/minimax_h3_ref2va_pruned_int8_convrot_taomate_8_step),
[Virse H3 review](https://www.virse.ai/blog/minimax-h3-reddit-review),
[Leadde H3 review](https://leadde.ai/blog/mini-max-h3-reddit-review),
[ComplexSync](https://arxiv.org/abs/2609.29225), [PVSync](https://arxiv.org/abs/2610.09223),
[LongCat Avatar 1.5 report](https://arxiv.org/abs/2605.26486),
[Instavar](https://instavar.com/research/ai-video/open-source-lip-sync-models).
