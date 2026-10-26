# R35 — Director's cue layer in the engine's own syntax: sound, music, camera and cuts in H3, 2026-10-17

Research note on cues (audience reactions, music) written in the engine's own cue syntax, not invented
tags, audio first. Engine: upstream WanGP `af2ed29` (commit date 2026-10-12), read in a clone at `/tmp/upstream`:
`models/minimax_h3/` (`prompt_enhancer.py`, `minimax_h3_handler.py`, `pipeline.py`, `dialogue.py`, `transformer.py`,
`components/packing.py`), `wgp.py`, `shared/utils/prompt_parser.py`, the H3 files in `defaults/` and
`shared/deepy/settings/`. Hub at `main` as of today. Builds on R21 §1.1 and R22 §A/§B (field names, `<scenetrans>`,
`<cutoff>`, lip-sync wording), R24 (speech route) and R30 (joins); those are not repeated. MiniMax's own guides on
Hugging Face, and most web pages, could not be fetched from this container (DNS/proxy refused); web items below are
search-result summaries unless marked fetched. Facts only.

## 1. The fields that carry cues, and how they reach the model
| Family | Fields, in order | Defined at |
|---|---|---|
| FL2VA (T2VA, frames, control, VDN) | `integrated_multimodal_description`, `overall_soundscape`, `non_diegetic_music` | `prompt_enhancer.py:252` (rule), `:25-28` (agent form), `:44-46` (doc form) |
| Ref2VA, speech route's compiled prompt | `subject_definitions`, `summary`, `retention_analysis`, `detailed_description`, `overall_soundscape`, `non_diegetic_music` | `:284` (rule), `:108-114`, `:138-156` |
- Ref2VA has six sections, not six fields of cue: the cue-bearing ones are `detailed_description` (timeline, camera,
  cuts, speech) and the two sound fields; the other three bind references (R22 §B).
- No code parses the fields. The prompt string is appended whole after the media labels and tokenized
  (`text_encoder.py:124-155`, `add_text(prompt)` at `:154`); there is no `max_length` or truncation in
  `text_encoder.py`. The field names are text the model reads, nothing more (R22 §0.1, R23).
- The one code that reads a field name: the `PW` boundary check treats a window that starts with
  `overall_soundscape:` or `non_diegetic_music:` as a stray split of a structured prompt
  (`shared/utils/prompt_parser.py:68-70`), i.e. a blank line before a sound field breaks a window.
- Field content rules, verbatim:
  - FL2VA: "overall_soundscape is one compact paragraph covering ambience, physical action sounds, and non-verbal
    human sounds; do not repeat dialogue or singing. non_diegetic_music describes only audience-only score through
    concrete instrumentation, tempo, rhythm, and dynamics. Write `non_diegetic_music: N/A` when no score is
    requested." (`prompt_enhancer.py:258`)
  - Ref2VA: "overall_soundscape summarizes ambience, physical sounds, and non-verbal human sounds. non_diegetic_music
    covers only audience-only score. Cite an `<Audio N>` in the section where its copy/reference role is audible."
    (`:296`)
  - The Ref2VA agent form says otherwise for voices: "overall_soundscape: Ambience, physical sounds and voices."
    (`:113`). Two shipped defaults name the speech inside the soundscape: "the astronomer's synchronized voice"
    (`defaults/minimax_h3_fl2va.json:11`), "the synchronized spoken line" (`defaults/minimax_h3_ref2va.json:11`).
- Limits stated upstream: one paragraph for the soundscape (`:258`); Ref2VA `detailed_description` "roughly 350-500
  English words" (`:292`). No sentence or token cap on either sound field. The 1-4 / 1-3 sentence limits seen on the
  web (§5) are not in the engine.

## 2. Each cue type: upstream's own form
| Cue | Field | Upstream wording (verbatim) | Where |
|---|---|---|---|
| Audience reaction (laughter, applause) | — | **No form.** No H3 rule, example or default mentions applause, cheering, an audience or a laugh track. | grep of `models/minimax_h3`, `defaults/minimax_h3_*`, `shared/deepy/settings`, `docs/` |
| Laughter by a person in shot | `overall_soundscape` (as "non-verbal human sounds") | "Gentle waves rolling onto the sand, a light sea breeze, distant seagulls, and [the person's] soft laughter." | `defaults/minimax_h3_control.json:14` (only H3 instance) |
| Music bed, score (audience-only) | `non_diegetic_music` | "A sparse, gentle marimba motif at a slow tempo, fading under the final close-up." | `prompt_enhancer.py:93` |
| | | "Low sustained cellos with a restrained frame-drum pulse, opening into a single bright horn note in the final shot." | `:101` |
| | | "A tense electronic pulse with dry percussion, synchronized to the acceleration and drift." | `:218` |
| | | "A breezy acoustic guitar summer groove." | `defaults/minimax_h3_control.json:14` |
| Music in the scene (radio, performer) | `overall_soundscape` | "faint radio music from inside the car" ; "close natural violin performance" | `defaults/minimax_h3_vdn.json:24`; `prompt_enhancer.py:200` |
| No music | `non_diegetic_music` | "`non_diegetic_music: N/A`" | `:258` |
| Sound effect | `overall_soundscape` | "Steady rain on canvas and metal, bicycle-chain clicks, wet tires hissing over stone, distant traffic, and the courier's breath settling after the stop." | `:83` |
| | | "Delicate metal clicks, tweezers touching the bench, the restored watch beginning to tick, soft room tone, and a quiet satisfied exhale." | `:237` |
| Timed effect | `overall_soundscape` (a time word, no timestamp) | "a distant roll of thunder near the end" ; "three clean receiver tones, a brass switch clicking … and a short stereo transmission pulse" | `defaults/minimax_h3_vdn.json:24`; `defaults/minimax_h3_fl2va.json:11` |
| Camera move | description field | "Describe camera movement naturally as type, meaningful amplitude, and speed." | `prompt_enhancer.py:256` |
| | | "The camera tracks beside [the courier] at wheel height, then rises smoothly into a medium close-up" | `:82` |
| | | "the camera makes a slow clockwise arc from medium shot to close-up" | `:91` |
| | | "The camera makes a slow semicircle around [the violinist], widening as the mist parts" | `:199` |
| Cut inside a clip | description field | "A later hard cut begins `[Shot N] At MM:SS.mmm, ...` using a strictly increasing time within the requested duration. Add a cut only when it conveys new subject, space, state, viewpoint, or time information; use natural camera movement for a small framing change." | `:254` |
| | | "[Shot 2] At 00:04.000, cut to a wide aerial view as the fox descends into a pine valley" | `:99` |
| Cut between windows | window command | "`[/new_shot]`: carry no frames from the previous window, creating a hard cut. This is the same as `[/overlap=0]`." | `:14` |
- Placement rule for all sound: "Put exact dialogue inside `<d>[Language] ...</d>`, ambience and physical sounds in
  `overall_soundscape`, and audience-only score in `non_diegetic_music`." (`:174`)
- No timestamp form exists for a sound or music event. Timestamps belong to `[Shot N] At MM:SS.mmm` only (`:254`);
  every timed sound in upstream's examples is placed by words ("near the end", "in the final shot", "fading under the
  final close-up") or by the visible event in the description it accompanies.
- "Do not add dialogue, narration, music, cuts, or story events that conflict with […] request." (`:258`)
- Not H3: other engines' defaults carry their own cue tags — Prism `<sfx>…</sfx>` (`defaults/prism.json:17`),
  OmniVoice `[laughter]` (`defaults/omnivoice.json:10`), Ovi "The crowd roars in response" (`defaults/ovi.json:16`).
  None of these appears in an H3 file.

## 3. A kept soundtrack and generated sound
- Mode letters: FL2VA `A` = `audio_guide` kept, `K` = control video's track kept (`minimax_h3_handler.py:821-826`);
  Ref2VA `AS`, `KS` (`:769-781`). `"S" in audio_prompt_type` sets `soundtrack` (`pipeline.py:1019`); a kept track is
  then not added as an `<Audio N>` reference (`:1029`).
- How the track enters denoising: the window's slice of the waveform (`pipeline.py:1046-1051`) is encoded and
  copied into the **first** `target_audio_condition_latents` tokens of the target audio latent (`:1136-1138`); those
  tokens get the condition timestep `AUDIO_COND_TIMESTEP = 1.0` (`transformer.py:52`; `components/packing.py:323-327`).
  Each step updates only `audio[..., target_audio_condition_latents:]`, the tail after the track (`pipeline.py:1242`,
  `:1264`, `:1403`).
- So the engine generates audio **after** the kept track, never on top of it: a track that covers the window leaves
  no tail. Upstream says the same: "If the soundtrack covers the whole video, WanGP uses the original audio in the
  final file. If it ends early, H3 generates the remaining sound." (`minimax_h3_handler.py:96`; also `:66`).
- Output: when the input audio fills the window and the track is kept, the generated audio is dropped
  (`wgp.py:7916`, `:8445-8447`); otherwise the generated audio is appended after the existing track
  (`keep_existing=…`, `wgp.py:8576`). In the paths read, no step mixes generated sound into a kept track.
- Audio Refinement Extra Phase is switched off with a soundtrack (`pipeline.py:1643-1644`; "FL2VA hides this option
  when an input soundtrack controls the result", `minimax_h3_handler.py:279`).
- Prompt rules in soundtrack mode: lip-sync wording in the description field, no transcript, no mention of the track,
  no `<Audio N>` (`prompt_enhancer.py:34`, `:116`, `:68-74`, `:176-182`; R22 §A, §B). Upstream gives **no** rule for
  `overall_soundscape` or `non_diegetic_music` in soundtrack mode. Its one soundtrack template writes them as
  "overall_soundscape: The supplied soundtrack.\nnon_diegetic_music: N/A" (`shared/deepy/settings/gen_video_with_speech/
  MiniMax H3 Ref2VA Pruned Turbo Lightx2v 8 Steps With Sound.json:9`, `audio_prompt_type` `AS` at `:11`) — which
  names the supplied track, against the "without mentioning a supplied audio track" rule (`prompt_enhancer.py:180`).
- The Hub's lip sentence inserts into `detailed_description` / `integrated_multimodal_description` and
  knows both sound fields only as section headers (`hub/worker/adapters/lipsync.py:15-18`).

## 4. The speech route and cues
- Script grammar: `Speaker N:` or `Speaker N{k=v,…}:` header (`dialogue.py:44`); every `[ … ]` in the body is a
  direction (`:45`), collected from anywhere in the turn and joined with "; " (`:126-128`, `:141`); the spoken text is
  the body with all brackets removed (`:129`). A bracket in mid-line (e.g. `[laughs]`) is therefore not kept at its
  position: it becomes part of the turn's voice direction.
- Each turn compiles to a fixed six-section prompt (`dialogue.py:175-201`) whose sound fields are fixed text:
  "Clean close-microphone speech, subtle natural breaths, quiet neutral room tone, no overlapping voices, and no
  unrelated sounds." and `N/A` (`:197-200`). No user cue reaches either sound field.
- Whisper trims sound before the first and after the last expected word of each turn (`dialogue.py:301-343`); turns are
  joined with 0.18 s of silence (`:22`, `:441-443`). A laugh or reaction outside the words is in the trimmed region.
- Upstream's own speech-writing prompts forbid cues unless asked: "Do not add another speaker, narration outside the
  spoken monologue, sound effects, music, or visual directions unless explicitly requested." (`prompt_enhancer.py:356`);
  "Do not add narration, sound effects, music, overlapping speech, or visual directions unless explicitly requested."
  (`:375`). Neither says where a requested effect would go.
- Non-script audio on the same model uses the six sections instead: "For non-script sound generation, describe the
  sound and its evolution in H3's six sections … use N/A for an unneeded music score." (`prompt_enhancer.py:131`);
  "**No reference:** generate speech, ambience, Foley, or music from the prompt alone." (`minimax_h3_handler.py:292`).
  A prompt with any `Speaker N:` header goes to the script path instead (`pipeline.py:760`).
- Inside `<d>[Language] ...</d>` upstream defines only spoken or sung words (`prompt_enhancer.py:256`); no non-speech
  token for use inside `<d>` is defined. `(S1,S2)` compound IDs are Maestro's, not the engine's (R22 §D).

## 5. Web, 2026-08-18 onward
- No MiniMax page, GitHub issue or node README dated in the window was reached that gives a form for applause,
  laughter or a crowd reaction in H3. MiniMax's guides `VIDEO_PROMPT_WRITING_GUIDE_base_en.md` / `_ref_en.md`, which
  upstream adapts (`prompt_enhancer.py:104`, `:245`), could not be fetched (huggingface.co refused by the proxy).
- "MiniMax H3 Director: Timeline Storyboard Editor for ComfyUI", comfyui-wiki news dated 2026-08-18 (by its URL):
  shots placed on a timeline track compile to timestamped shots; an audio item becomes a reference or the muxed
  soundtrack. Search-summary only.
- Third-party H3 prompt guides (aireiter.com, hackernoon.com, lumalabs.ai, domoai.app; dates not obtained): soundscape
  "1–4 sentences, one paragraph, no dialogue", music "1–3 sentences, or N/A"; laughter listed as a non-verbal human
  sound for the soundscape; music from a radio or performer belongs in the timeline field, not the music field; one
  example has the negative line "no added music, applause, or spoken words". Search-summary only; the sentence limits
  are not in the engine (§1).
- Outside the window, for reference: ComfyUI issue #15283 (opened 2026-08-04, closed 2026-08-05, fetched) reports
  distorted H3 audio, "more frequent in loud scenes like explosions, impacts, and crowds"; replies attribute it to
  ancestral/SDE samplers, not to prompts.

## Not known
- How H3 renders an audience reaction (applause, a laugh track) written in `overall_soundscape`: no upstream
  example, no test here, nothing found on the web in the window.
- Whether H3 places a sound at a time written in words ("at the end", "after the line"); upstream only shows such
  wording, it does not measure it.
- What the model does with `overall_soundscape` / `non_diegetic_music` when a soundtrack covers the window: the tokens
  are encoded and attended to, but the audio they would describe is never generated (§3). Whether they still steer
  the picture is not known.
- What MiniMax's own guides say about cues beyond what upstream adapted: not readable from here.
- Whether the Ref2VA agent form's "voices" in `overall_soundscape` (`:113`) or the rule "non-verbal" (`:296`) is the
  intended one.

## Sources
- Upstream WanGP `af2ed29` (2026-10-12): `models/minimax_h3/prompt_enhancer.py`, `minimax_h3_handler.py`,
  `pipeline.py`, `dialogue.py`, `transformer.py`, `text_encoder.py`, `components/packing.py`; `wgp.py`;
  `shared/utils/prompt_parser.py`; `defaults/minimax_h3_{fl2va,ref2va,control,vdn}.json`, `defaults/{prism,omnivoice,
  ovi}.json`; `shared/deepy/settings/gen_video_with_speech/MiniMax H3 *.json`.
- Hub: `hub/worker/adapters/lipsync.py`. Prior notes: R21, R22, R23, R24, R30.
- https://github.com/Comfy-Org/ComfyUI/issues/15283 (fetched; 2026-08-04, outside the window).
- https://comfyui-wiki.com/en/news/2026-08-18-minimax-h3-director (search summary only).
- https://aireiter.com/blog/minimax-h3-prompt-guide,
  https://hackernoon.com/minimax-h3-prompt-guide-how-to-write-better-hailuo-30-video-prompts,
  https://lumalabs.ai/learning-center/articles/minimax-h3-prompt-guide (search summaries only; fetch refused).
- https://huggingface.co/MiniMaxAI/MiniMax-H3/blob/main/docs/VIDEO_PROMPT_WRITING_GUIDE_base_en.md (not reachable).
