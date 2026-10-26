# R26 — What a supplied ComfyUI workflow shows (MiniMax H3 Seed Hunter v2.51), 2026-10-17

Facts read from a supplied file (`minimaxH3SEEDHUNTERLatent_v251.json`, a ComfyUI workflow from
civitai, author "foxfuressence"). **Nothing here is copied into the Hub.** It is read as evidence of what the
engine accepts; every claim must be re-checked against upstream at the pinned commit before a spec rests on it.
Checked here: the node list and the widget values. Not checked: whether upstream `af2ed29` accepts the same
fields through the Hub's worker (that is the next research step).

## 1. The node set
`MiniMaxH3AddGuide` x3 (widget values -1, 0, 0 — a guide index; one titled "Guide for 1st Pass"),
`MiniMaxH3ReferenceToVideo` x2, `MiniMaxH3SigmaShift` x2 ("Shift" 12/6; "Audio Shifter" 12/3),
`LTXVConcatAVLatent` x2 and `LTXVSeparateAVLatent` x2 (audio and video latents joined and split),
`TrimAudioDuration` x2 (titled "OG Audio (minus Overlap)" and "Audio Overlap"), `VAEEncodeAudio`,
`VAEDecodeAudio` x5, `SaveAudioAdvanced` x3 (flac), `RIFEInterpolation`, a latent upscaler, Pixaroma and rgthree
helpers. Sizes on the two `ReferenceToVideo` nodes: `1344x768, 124 frames, "max"` and `512x512, 124, "match"`.

## 2. The prompt it sends (the shape of the "Dialogue / Audio Genner" node's text; the line itself replaced by a placeholder)
```
subject_definitions:
<Subject 1> is a character who uses <Audio 1> as their speaking voice timbre reference.

summary:
[reference generation + audio reference] A scene of a character <Subject 1> speaking a line of dialogue.

retention_analysis:
<Audio 1>: reference - its vocal timbre guides the vocal delivery of <Subject 1> without copying the original signal.

detailed_description:
[Shot 1] <Subject 1> says: <d>[English] <Line 1></d> [the speaker's] tone is <emotion>.

overall_soundscape:
N/A

non_diegetic_music:
N/A
```

## 3. What that tells the Hub's plan
- **The six fields are real and in use**: `subject_definitions`, `summary`, `retention_analysis`,
  `detailed_description`, `overall_soundscape`, `non_diegetic_music` (R22 documented them; this is a working
  example). `N/A` is an accepted value for the last two.
- **A voice sample is bound to a character inside the prompt**, as `<Audio N>` named in `subject_definitions` and
  again in `retention_analysis`. This is a different route from the Hub's `audio_guide` + `audio_prompt_type`:
  there the sample is a task field, here it is also declared in the text. Which the engine needs, and whether both,
  is the open question for the voice-in-a-clip stage.
- **Two Director needs have their own fields.** Audience sound belongs in `overall_soundscape`; music
  belongs in `non_diegetic_music`. Neither needs to be invented or hardcoded: the engine's own format carries
  them.
- **Dialogue is tagged** `<d>[English] ... </d>` inside `detailed_description`, under a `[Shot N]` heading, with
  the delivery described after the tag ("[the speaker's] tone is <emotion>"). This is the shape a Director compiler would emit.
- **Continuation carries audio explicitly.** Two `TrimAudioDuration` nodes split the previous pass into "OG Audio
  (minus Overlap)" and "Audio Overlap", and the AV latents are concatenated and separated around the pass. The Hub
  today sends no audio on a continue and trims only the source's video tail (`soundtail.py`).
- **Several reference guides per generation** (`MiniMaxH3AddGuide` x3 with an index) is several references
  with an index each. The Hub sends at most three reference pictures through one path and nothing with an
  index.

## 4. What this does not settle
- Whether any of it reaches upstream `af2ed29` the same way: these are third-party ComfyUI nodes, and the Hub does
  not use ComfyUI. The fields in §2 go into a model's text prompt, which the Hub can already send; the node
  behaviour (guides, AV latent concat) may have no equivalent in upstream's own API.
- The author's voice-clone claim in the release notes is not examined here; the node graph above is all that was read.
- Nothing about the kaleidoscope distortion (BACKLOG 24): the workflow re-encodes between passes too.
