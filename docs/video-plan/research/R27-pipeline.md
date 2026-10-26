# R27 — A working 8.5-minute automated pipeline, read from its author's own account, 2026-10-17

A Reddit thread by its author (`teachersecret`) describes a fully automated pipeline that
produced an 8.5-minute scripted video with several speakers from one prompt, locally, on a 4090, in a few hours. **Everything here is that
author's claim, not a verified fact.** It is filed because it is the only end-to-end account of the thing the Hub
is to do. Nothing is copied; nothing
here authorises a build.

## 1. The pipeline, as the author confirmed it
A commenter (`multikertwigo`) set it out and the author answered "Yeah, you got the idea":
1. One prompt as input; the LLM writes the script.
2. From the script: character sheets (text-to-image) **and voice references**.
3. The voice API generates the audio for the **whole** film up front.
4. That audio is split into 5-10 s clips.
5. The LLM works out the camera for each clip.
6. Each audio chunk goes to **H3 Ref2VA** with the scene in H3's prompt format **and the actor references**.
7. Validation; on failure, the same clip is generated again with a different seed.
8. The clips are stitched.

## 2. The two techniques worth taking
- **Audio first, at full steps; video after, at low steps.** The author: "Gen the audio first (use my fastapi at 50
  steps). I do this because most turbo LoRAs ruin sound. I then generate the video from that audio, which at these
  settings (1344x768, 3 steps turbo tao LoRA or 4 step DMAD) is quite fast." This is the Hub's
  order, audio first and the video following it, used for 8.5 minutes, with a
  concrete reason: speed LoRAs damage sound but not picture, so the two passes want different settings.
- **Validate by transcribing what was generated.** The author transcribes each generated clip and compares the
  words, rejecting a bad generation without anyone looking at it ("it's basically instantly able to tell you if the
  video gen came out good or not without even looking, and it can reject flawed generations automatically"). This
  is cheap, automatic and needs no vision model. It is the shape Director's validator (R21 part 3) should take for
  the clip stage. Its limit is stated too: audio-only validation passes a clip whose *picture* is wrong — the
  author's own film has a character speaking in another character's voice, which the check did not catch.

## 3. What it confirms for the Hub
- **References go in on every clip.** Step 6 sends the actor references with each chunk, through Ref2VA. The Hub
  does neither on a continue (BACKLOG 24): it only offers FL2VA and carries the
  face through 18 frames of the last output.
- **Character sheets instead of LoRAs.** Step 2 makes the actors as pictures, not LoRAs — the Hub's position
  exactly (no character LoRAs; a character is a few views and a headshot). Direction D3.
- **Segmentation is the pipeline's job, not an input's.** Step 4 cuts the audio into 5-10 s pieces and each piece
  becomes one clip. The requirement: a queue of about 15-second pieces does the segmentation and continuation
  automatically. Direction D4.
- **A re-shoot loop is part of the design**, not a failure of it: a rejected clip is simply generated again on a new
  seed (step 7). The Hub has no such loop.

## 4. What it also shows about the limits
A commenter (`f5alcon`) catalogued roughly a hundred continuity faults across the 8.5 minutes: characters and faces
changing between shots, objects appearing and teleporting, rooms not matching, accents changing mid-scene, a line
spoken by the wrong character. The author does not dispute them ("tons wrong... it's straight auto and wasn't
looking at images, was validating on audio"). Two things follow for this project:
- Automatic continuity at this length is **not** solved by anyone; it is not to be expected from Director's
  first cut. The author's own framing is "previz": generate fast and rough, then re-shoot the bad clips.
- The author's stated next step is better references, including reference images shot at
  the right camera angle, and a library of camera-move references.

## 5. Not checked here
Nothing in this note was run or read as code. The author's tools (a voice API, a "factory" harness, a transcription
repo) are third-party and unexamined; the model the author used for the writing is a 26B local model. Whether upstream
`af2ed29` through the Hub's worker behaves as the author's ComfyUI-based stack does is unknown and is the research step for
D3 and D4 (see also R26, the supplied workflow).
