# BLUEPRINT — the Director, from narration to the rendered scene

A blueprint that tells how everything is going to work, no generalization, no guessing.
Every spec written from `PLAN.md` is written from the stage of this file `PLAN.md` names, with
R48 beside it; a build session reads the same. Facts cite the Hub (`hub/…`), upstream WanGP `af2ed29`
(`upstream …`), Maestro `0678b44` (`M:…`), HocusPocus `41a7127` (`HP:…`). What is not known is in §9 and nowhere
else; nothing in §1-§8 is a guess.

## 0. The shape
Four stages, fed to the architect one at a time through `PLAN.md`; a stage's steps are specs in order, each built,
reviewed, installed and run before the next. Every stage only adds: `Clip:`, `Scene:`, `Redo shot`, Generate and
every existing press keep their prompts, tests and behaviour.

| Stage | What the screen does at its end | Renders |
|---|---|---|
| A | Narrate a story; the Hub writes a locked, timed, sketched script and renders its audio track | audio, sketch pictures |
| B | Render the script as a stick-figure animatic: control video + the track, through H3 ControlNet | previz video |
| C | Render the script with the cast's characters on the context's set, every shot a view of one world, to the track | the scene |
| D | Redo a shot, a line or a panel by saying so; the script is the one source of every render | the same |

The pipeline, as data: narration → **script** (one JSON file, §2) → **audio track** (one WAV, §3.9) → **control video**
(one MP4 of stick figures, §4.2) → **shots** (clips, §4.3 / §5.2) → **the scene** (one MP4, §4.4). Each arrow reads only
the file before it. The script is a file of the Scripts folder; the rest are the Hub's jobs.

## 1. Fixed facts the blueprint stands on
Engine (`upstream`):
- Speech: one turn per `Speaker N:` block, `[language, emotion, pace, directions]` not spoken
  (`models/minimax_h3/prompt_enhancer.py:123-125`); samples map to speakers 1-3, each ≥ 2 s, 15 s split evenly above
  that; `duration_seconds` is a cap (`minimax_h3_handler.py:417`); dialogue mode splits into turns itself with a fixed
  0.18 s pause (`models/minimax_h3/dialogue.py:22`, `:41`); the voice-clone model `minimax_h3_tts_ref2va_pruned`.
- Sound models shipped: `stable_audio3_small_sfx`, `stable_audio3_small`, `stable_audio3_medium`, `minimax_music3`,
  ACE-Step (`defaults/`). The H3 audio model also makes "speech, ambience, Foley, or music from the prompt alone"
  (the Hub's `upstream.facts.json` `speech.sounds`).
- Kept soundtrack: letters with `S` (Ref2VA `AS`) keep `audio_guide` as the clip's sound and the video follows it
  (`minimax_h3_handler.py:113`, `:769-779`); the prompt asks "speaking with natural lip movements synchronized" and
  never names the track (`:230`); a supplied track replaces generated audio window by window
  (`shared/utils/audio_video.py:75`); speech across a join is re-made (`:108-114`).
- Voice reference: `A`/`AB`/`ABD` = `audio_guide`s whose timbre is reused; `<Audio N>` in the prompt
  (`text_encoder.py:139-140`); the sample is a reference block, not on the timeline (`pipeline.py:653-659`,
  `:735-742`); its own example: "without copying its original words or background noise" (`prompt_enhancer.py:226`).
- Control path (ControlNet-Union, `defaults/minimax_h3_control_pruned.json` = base `minimax_h3_fl2va_pruned` + one
  rank-8 module): `video_guide` + `video_prompt_type` letters `"",PV,DV,EV,SV,CV,V,MV` (`:549-550`), `V` = control
  video as is; `audio_prompt_type` `A` keeps `audio_guide` as the soundtrack on this path (`:239`); window 362
  frames (`:546`); legal lengths ≥ 107, then 17n+5 (`:581-583`), other lengths trimmed down
  (`shared/utils/frame_scheduler.py:23`); overlap 18 (`:1258`, `constants.py:8`); each window its own control slice
  (`:655`); output in the control video's aspect (`:239`); `[Shot N] At MM:SS.mmm` valid (`:542`); window commands
  `[/duration=Xs] [/overlap=Nf] [/new_shot]` (`frame_scheduler.py:100-130`; `/new_shot` needs `T` in
  `image_prompt_types_allowed`, `:128`, `wgp.py:2964`); anchors `image_start`/`image_end` "should match the control
  video" (`:239`), the control model trained without them (`:224`).
- Pose drawing: `draw_pose` (`preprocessing/dwpose/pose.py:29`), body/hand/face (`util.py:71`, `:115`, `:143`); 18 body
  points, hands always (`pose.py:297`, `:519`), 68 face points (`:375-377`); limbs 4 px, joints 4 px (`util.py:76`,
  `:110`).
- Ref2VA identity: up to 9 pictures (`:985-986`); the six-field prompt (`subject_definitions`, `summary`,
  `retention_analysis`, `detailed_description`, `overall_soundscape`, `non_diegetic_music`, `:284`), `<Subject N>` from
  `<Picture N>`; one reference video `V-U`, whole, to every window, 2-15 s (`:740`, `:757`, `:1000-1004`).

Hub (`hub/`):
- Engine requests the worker already speaks (`hub/worker/enginerequests.py`): `PictureRequest`, `ClipRequest`
  (`sound`/`sound_seconds` kept track; `video`/`video_seconds` reference video; `voices`;
  `judge`, `speaker`, `words` for the judges), `SpeechRequest` (`sample`, `turn_seconds`, `pace`, `judge`,
  `join_seconds`), `VoiceRequest` (SeedVC), `SoundRequest` (`model` marked `sounds`, `seconds` exact), `JoinRequest`
  (`items` track 1, `audio` track 2 `JoinSound` with `at_ms`, `level`, fades, `duck`; `out_kind` "mp4" or "wav";
  `Duck`). The kept-sound clip length is the lattice length covering the sound (`clipsound.frames`); a shorter sound
  is padded to cover (`_covering`).
- Jobs: `JobPlan` (`tasks`, `inputs`, `prepare`, `finish`, `takes`, `judge`; `hub/core/api.py:100-111`); a job that
  plans itself at start (`prepare`); per-take judging and re-takes inside the job within
  `scene_takes_max` / `scene_retake_minutes` (`judgeshot.ShotJudge`, `presstakes.plan`); judges: face,
  mouth, words (Whisper, recall; unscripted seconds), framing. The scene join with
  placed reactions and ducking (`audience.place`, `.sounds`; `JoinRequest.audio`).
- MCP: the core publishes each module's `screen`, `listings` and `actions` as tools (`hub/core/api.py:115-117`,
  `hub/core/mcp.py`); Open WebUI calls them; the planner's asks go through `chat.ask` to the model in Settings →
  Assistant with `response_format` held.
- Scripts: `hub/modules/director/` with `scriptshape.read`, `scripts.listing/one/rename/delete`,
  routes `/scripts`, `/script`, `/rename`, `/delete`; files under `scripts/` (a root in `OWN`); the Scripts tab
  (`web/src/modules/director/`, `Timeline.tsx`, `Figure.tsx` + `poses.ts` with the seven poses, `Bar.tsx`). Format
  version 1: `{version, scenes: [{title, cast, shots: [{id, camera, start_ms, end_ms, events: [...]}]}]}`, events
  `line` / `cue` / `pose` with `start_ms`, `end_ms`, optional `anchor: {line, at}`.
- Characters: `<Name>.png` with `<Name>.wav` sample and `Voice` words (`ctx.files.characters()`,
  `character_sample`); a voiced speaker is `<Audio N>` (`shotprompt._audio`).
- Rules: files under `hub/` ≤ 300 lines; engine keys only in `hub/worker/adapters/`; worker stdlib only; nothing of a
  prompt, chat or job on disk; no model or file name hardcoded; the model is picked in Generate's pulldown.

## 2. The script file, version 2 (Stage A step 2 raises version 1 to this; every later stage reads it)
Amended, field by field, by §11.3 (a shot's `kind`, a cutaway's `during`), §12 (`takes`, `mix`), §13 (a cast member's
`sheet`, `variant`), §14 and §16 (the set record, `audience`, the house, a cast member's `place`), §18 (`format`, a
`super` event). A spec reads those sections with this one.
```
{"version": 2,
 "context": {
   "cast": [{"name": str,                      # a Characters-folder name; its picture and sample are its references
             "look": str,                      # what to keep: body, face, hair, in concrete words (HP character-sheet rule)
             "costume": str,                   # clothing, materials, colours; one costume per script unless an event changes it
             "ignore": str,                    # what in the picture is not the character (its background, props)
             "home": int}],                    # 0-100, left to right on the set; fixed for the script (one world)
   "set": {"name": str, "description": str,   # the stage: floor, walls, furniture, lights, in concrete words
           "elements": [str],                  # the things that may appear; nothing else does
           "props": [{"name": str, "owner": str|null, "description": str}],
           "plate": str|null},                 # a picture of the empty set (a Hub picture id), drawn in Stage C step 1
   "style": str},                              # one line: the look of every render
 "scenes": [{"title": str, "cast": [str],      # cast names, a subset of context.cast
   "shots": [{"id": str, "camera": {"framing": str, "move": str, "on": [str]},   # on: who is in frame, by name
              "start_ms": int, "end_ms": int,
              "events": [
                {"id", "kind": "line", "start_ms", "end_ms", "speaker", "words", "language", "emotion", "pace",
                 "measured": {"start_ms", "end_ms"}|null},          # written back by the audio render (A.9)
                {"id", "kind": "cue", "start_ms", "end_ms", "cue": "effect"|"music"|"reaction", "words",
                 "model": str|null, "anchor"?},                     # model: the catalog id that rendered it (A.9)
                {"id", "kind": "pose", "start_ms", "end_ms", "character", "pose": str|{joints}, "anchor"?},
                {"id", "kind": "panel", "at_ms", "picture": str|null, "stale": bool}]}]}],  # A.6 sketches
 "lock": {"locked": bool, "at": str|null},
 "renders": {"track": str|null, "control": str|null, "scene": str|null}}   # Hub ids of the latest outputs
```
Rules the file carries: an event's `speaker`/`character`/`owner` is a context cast name; a `cue` of kind `reaction` is
the audience (the Hub's placed sound, never a prompt word, E4); `pose` as a name is one of the seven (`poses.ts`), as
joints the 18 body + 2×21 hand + 68 face points of §1; `panel.at_ms` is a shot's `start_ms` or a pose-category change.
Times are ms; a shot's `end_ms` = the last of its events' ends. Version 1 files are read as version 2 with an empty
context (A.2's rule), never rewritten unless saved.

## 3. Stage A — the script and its audio track (PLAN.md steps 1-9; R48 §1-§6, §8)
A.1 (built) the format v1 and the Scripts screen.

A.2 the context: the fields of §2 `context`; screen: a Context panel above the timeline (cast cards with picture, look,
costume, home; the set's description, elements, props; the style line). `give_example` ships a context. Refusals on
read: a cast name not in Characters; `home` outside 0-100; an event naming a name not in the context.

A.3 the Director writes it live. Tools on the Hub's MCP server (`Action`s of the director module; each answers the
script's state in ≤ 6 lines and refuses with `{problem, fix, hints}`, the script untouched):
`script_start {name, story}` (a new script from a story: the context is written first by the model, cast from Characters
only), `context_set {cast?, set?, style?}`, `scene_add {title, cast}`, `shot_add {scene, camera, after?}`,
`line_add {shot, speaker, words, language?, emotion?, pace?}`, `cue_add {shot, cue, words, anchor?}`,
`pose_add {shot, character, pose, anchor?|start_ms}`, `event_move {id, start_ms}`, `event_change {id, fields}`,
`event_remove {id}`, `script_read {name?}`, `script_lock`/`script_unlock` (A.7). Refusals on arrival (R48 §2): speaker
not in the scene's cast; words over the shot's window at the pace (word count × 1/pace + 0.18 s); two lines overlapping
on any row (one speaker at a time); a pose change on a character inside the character's own line; an event past its scene's end;
a prop or element not in the context. `Script: <story>` in the Open WebUI block hands the chat to `script_start`, and the
block says every later message in that chat is a tool call on the same script. The screen follows by the Hub's bus
(`director.script.changed`), no reload. The planner asks for the context with `response_format` held (the context route).

A.4 timing: a line's `end_ms` = `start_ms` + words/pace×1000 + 180; a shot's events are laid in authored order per
row; an overrun pushes later events on its row and the shot's end; `start_ms` is authored or anchored
(`anchor.at` start|end of a line); the screen shows total length. A `Scene:`-style cap: the script's total ≤
`scene.MOST_SECONDS` × scenes (60 s per scene), refused with the amount over.

A.5 poses, tweened: a keyframe per character at each line start and end (its speaker), at each shot start, and
wherever `pose_add` says; between keyframes eased interpolation (`poses.ts` already draws the seven; interpolation
is the same joints lerped with ease-in-out); each character drawn at its `home` x on a fixed canvas (the clip model's
size, from Generate's pulldown at draw time, else 16:9); no render.

A.6 sketch panels: for each `panel` event, one picture job on the picture model picked in Generate (a
`PictureRequest`, prompt = `style` + the set's description + each in-frame character's look and costume + the shot's
framing + each character's pose name at `at_ms`, "pencil sketch, low detail, monochrome"; no names, no text; size
the model's smallest), queued by the director module as the script changes, one job at a time (the core's lane runs
them in order); a panel whose shot's context, camera or poses change is marked `stale` and redrawn after the current
one. Shown on the timeline at `at_ms`. These pictures live in the Hub's Temp like every picture; the script holds
their ids. A panel is a record for the checks and for Stage C's anchors, never a control frame.

A.7 the lock: `script_lock` refuses with one line per gap: context incomplete (a cast member without look, costume or
home; a set without description); a line without speaker sample (`character_sample`), words, language, emotion or
pace; an untimed event; a shot without camera framing or length; a speaker without a pose at a line's start and end;
a panel not drawn or stale. Locked: every tool but `script_read` and `script_unlock` refuses "locked"; the screen's
Rename/Delete stay.

A.8 the audio script view: beside the timeline, per line the exact `Speaker 1:\n[language, emotion, pace] words`
block the Hub will send (one speaker per generation, so always `Speaker 1`), per cue its request (model, seconds,
prompt), at their times. Pure text from the script; nothing renders.

A.9 the audio track, `Track` button on a locked script (one job, the director module's `jobs`): tasks in order:
one `SpeechRequest` per line (`prompt` = that block, `sample` = the speaker's `<Name>.wav`, `seconds` = planned
length × 2 rounded up (a cap, §1), `judge` True, `turn_seconds` as the speech route sets it, `pace` from the setting), one
`SoundRequest` per cue (`model` = the first catalog model marked `sounds` whose kind fits: effect → `*_sfx`, music →
`stable_audio3_*`/`minimax_music3`, reaction → the kept audience file when present else the sfx model;
`seconds` = the cue's length; a cue whose model is absent fails the job in one line naming it), then one
`JoinRequest` with `out_kind` "wav": `items` = the lines in order as track-1 sounds (`sound` True) each at its
measured length, with a 180 ms gap, lines pushed back by overrun in order (A.4's rule, applied to measured lengths);
`audio` = the cues as `JoinSound` at their (pushed) `at_ms`, music `duck` True, level and fades at the audience mix's
defaults. Each line judged by the words judge and re-taken under the bar (a scene's takes; `presstakes`). `finish`
writes `measured` into each line, `model` into each cue, `renders.track`, and files the WAV in Sounds named for the
script; then the check: for each line, heard ≥ the bar and inside its measured window; for each cue, a task landed;
every mismatch one line on the server's card. Nothing of a prompt on disk: the script holds the words (the file).

## 4. Stage B — the stick-figure animatic (previz) through the control path
B.1 the control video: from a locked script with a track, one MP4 at the clip model's size and fps, length = the
track's length rounded UP to the legal lattice (≥107, 17n+5) with the last frame held; every character drawn by the
engine's own pose code (the worker imports `preprocessing.dwpose.util` from the engine checkout, as the DWPose
adapter did: the Hub's worker calls upstream code only through `hub/worker/adapters/`), tweened as A.5, hands and
68-point face always, mouth open/closed cycling only inside its character's measured line windows, no text or
boxes; shots drawn on one fixed canvas, each shot a view: framing scales and offsets the whole world (never crops a
drawing: redraw at scale, §1 fixed strokes). Filed in Clips as the script's control video; `renders.control`.

B.2 the previz render: one `ClipRequest` per generation window on the control model (its catalog entry; `video` =
the control video, letters `V` joined to `video_prompt_type` by a new adapter twin of `refvideo.py` for the control
path: `video_guide` + `V`, never `PV`; `sound` = the track with letters `A` (this path's kept-soundtrack letter, §1),
`sound_seconds`; `frames` = the window's legal length; prompt = the shot list for that window in FL2VA form
(`[Shot 1]` … `[Shot N] At MM:SS.mmm` at the script's cut times inside the window, each shot's framing and action
from the script, "stick figures on a plain stage", lip-sync wording per `:230`, no track named); windows of ≤ 362
frames split at cut times with `[/duration]`/`[/overlap=18f]` where a window must end mid-shot). The pruned
ControlNet module and its base must be on the server's disk (§9.1); the Hub refuses in one line naming the missing file.

B.3 join: the windows joined with the track as the sound (`JoinRequest`, `items` the windows trimmed by the 18-frame
overlap as the engine's own joiner does, `audio` empty: the track is already in each window's sound; or `items` with
`audio` False and the track as one track-2 item at 0 ms, level 1, no duck: the spec decides, with the reason that
window-edge speech repair (§1) favours the first). Judged per window: mouth judge against the track's line windows
(the mouth opens only inside them), framing judge against each shot's framing; re-takes as for a scene's shots.

B.4 check against the sketches: each panel's `at_ms` frame of the previz is compared with its sketch by the face/pose
judge's layout (who is in frame, where, scale); mismatches listed. Previz filed as `renders.scene` of kind previz.

## 5. Stage C — the scene with the cast's characters, every shot a view of one world
C1 the set plate: one picture job from the context's set description and style (no people), kept as `context.plate`
and shown in the Context panel; a picture dropped on it replaces it. Character references: each cast
member's picture (and its views, `cast.with_views`) as today.

C2 shots: one `ClipRequest` per shot on the Ref2VA model picked in Generate, kept-sound route: `sound` = the
track's slice for the shot (cut by the Hub at the shot's `start_ms`-`end_ms`, padded to the lattice as `clipsound`
does), `sound_seconds`; letters `AS`; references = the set plate as `<Picture 1>` (the set first, so every shot shares
it), then each in-frame character's pictures; `voices` empty (the track carries the voices); prompt in the six fields:
`subject_definitions` from the context's look + costume per in-frame character and "the stage from <Picture 1>",
`retention_analysis` each `fully_preserved`, `detailed_description` = style, the set's description, each character at
the character's home position (left/centre/right from `home`), the shot's framing and move, the poses at the shot's keyframes as
actions, the lip-sync wording, the frame held on the speaker, no audience faces while anyone speaks (the scene
guard, kept), `overall_soundscape` the room sentence, `non_diegetic_music` N/A. A shot longer than
one pass is split at a sentence end of its measured lines into more shots of the same camera (A.4's seconds are
measured now). Judged as a scene's shots (face, mouth against the slice, words against the slice's lines, framing,
unscripted speech), re-taken under the bar; C's reference video option: the previz window as `video` (`V-U`, 2-15 s)
for the camera and the layout when the spec finds it holds on the server (§9.4).

C3 join: shots in order, the whole track as track 1's sound replacing each clip's own (`JoinItem.audio` False on
the clips, the track as the one sound item), the audience's reactions already in the track (A.9); `renders.scene`;
filed in Clips named for the script.

C4 check: each panel's frame of the scene against its sketch (layout), each line's window against the mouth judge
(the speaker's mouth moves, no one else's), the costume judge: the face judge's picture similarity per character
across all shots (a character whose similarity to its own first shot drops under the bar is listed, "costume or
identity drifted in shot k"). Mismatches on the card, one line each, never a silent pass.

## 6. Stage D — redo by saying so
`Redo shot k`, `Redo line <id>`, `Redo panel <id>` on a locked script: the one task again from the script (the
script is the source; nothing is re-planned), its outputs replaced in the track / control / scene by re-running the
joins (A.9, B.3) from the kept parts; the existing `Redo shot` is left as it is for `Scene:`.

## 7. Open WebUI's side
The block (`docs/video-plan/system-prompt-video-paragraph.md`) gains, per stage, only the hand-over lines: `Script:`
→ `script_start` and "every later message in this chat is one of the script tools on that script"; `Track`, `Previz`,
`Film`, `Redo …` → the matching actions. The planning model is asked only for the context and for turning narration
into tool calls; it never writes a render prompt (the Hub compiles every prompt).

## 8. Order of feeding (what PLAN.md names, when)
Stage A steps 1-9 (now). Then B.1-B.4 as one PLAN.md component, gated on §9.1 (the ControlNet
module installed, or Stage B is skipped to C). Then C1-C4. Then D. A stage's PLAN.md text names this file's section and R48's
sections; each spec cites both.

## 9. Not known (recorded; not to be solved while a stage is being fed)
1. Whether the ControlNet module (`minimax_h3_control_pruned`'s rank-8 file) is on the server's disk, and whether the pruned base
   takes it.
2. Whether H3 renders a stick figure as a stick figure on the control path, and keeps mouths in sync while a pose holds.
3. Whether `[/new_shot]` is accepted on the control path (`T` in the control model's allowed types).
4. Whether a previz window as a reference video (`V-U`) holds the camera and layout on a Ref2VA render.
5. Which sound-model weights the model folders hold (`stable_audio3_*`, `minimax_music3`, ACE-Step).
6. Whether the planning model corrects itself from `{problem, fix}` refusals.
7. The speaking-rate setting that matches the voices (the measurement has not been run).
8. The 360° / panoramic stage plate: whether a plate picture alone holds the set across shots, or a
   reference video of the empty set (`V-U`) is needed; decided by C2's runs.

## 10. Later: casting before the script, and sketches as guidance (not in PLAN.md)
What the code does not yet do. Not to be built
until PLAN.md names it; nothing here changes Stage A. The rule: an item enters PLAN.md only after
it is fully researched, solved and proved on the server the way R48's engineer findings were; until then it is
stepped around.
1. **What the code does today.**
   - The context's look and costume are written by the Open WebUI model from each cast member's name alone; it never
     sees the character's picture, so the costume and the style are the model's, not the picture's.
   - Each sketch is its own picture job (random seed, no reference, no LoRA; `sketch_plan`,
     `hub/modules/generate_image/tools.py`), so nothing carries from one panel to the next.
   - No staging: the prompt lists who is in frame at the character's home place and the camera as free text ("Wide Shot"), so
     the model lines everyone up side by side, not in a staged shot.
   - Each sketch is 1328×752 (1 MP at 16:9, `screen.MEGAPIXELS`, `screen.py:24`) at the model's full steps: as slow
     as a finished picture, against a script written as it is narrated in the chat.
2. **Sketches are guidance only.** Their job is to hold the set, props, costumes and placement steady across shots
   for the later renders; the Storyboard shows them as thumbnails. A sketch is small, black-and-white line art, fast. The Hub's
   1 MP floor is its own menu; the size code takes any multiple of 16 (`models.within`, `models.py:96-102`).
   Not known: whether the picture model draws a usable sketch at 480p (848×480, 0.41 MP) or 320p (576×320,
   0.18 MP); one test render per size on the picked model decides it.
3. **Casting before the script.** A character is captured from all angles in the costume chosen for the story: an
   orbital, bullet-time clip of the character, its stills turned into four poses and a headshot. That set, not one
   supplied picture and not the context's invented text, is the character's reference for the sketches and for
   Stage C. A costume change is part of casting, before the script, and is meant to be played with, like character
   customisation in a game.
4. **Film staging, not a line-up.** Where each person stands relative to the camera (blocking) is decided per shot;
   Step 7's camera object (framing, move, who is in frame) does not cover it.
5. The panoramic stage plate stays §9 item 8.
6. **Cutting, not long takes.** Edited shots, quick cuts of about 2 s: a close-up on the eyes as the look turns
   away, an exit out of frame, over-the-shoulder shots that follow the speaker. Today nothing asks for it: a shot is 1 to 15.08 s
   (`layout.SHOT_MIN_MS`, `SHOT_MAX_MS`) and the Director picks the cuts. Neither this blueprint nor R48 has rules for cut rhythm, inserts, reaction shots or over-the-shoulder
   coverage. Each shot is one clip render in Stage C, so many short shots mean many renders, all of one set
   and one costume from changing angles: the consistency item 2's sketches exist to hold. No sketch needs to be
   shown; it serves the renders, not the screen.
   A production-style LoRA from clips of an existing production is R40: it would teach how a shot of that
   production looks and moves (coverage, lighting, set, audience), not when to cut: trainers cut training clips between cuts
   (Fizgig Gizmo, R40 §1.2), and whether a clip with a cut inside teaches cutting is not known (R40 §8 item 5). The
   cut rhythm stays a script decision, the Director's.
7. **Levels and the audience, by ear.** Before Step 9's track is called done: each line is
   measured for loudness and brought to one level per scene, the check of 9c listing any line or cue off it; the
   audience is a bed that swells, overlaps and decays under the cut, not reactions that start and stop, with depth
   (a binaural feel). What exists: the engine's mix tool has gain, fades, one loudness pass
   (`normalize_lufs`), a true-peak limiter and speech-driven ducking (`shared/deepy/video_tools.py:540-544`,
   `:680-700`; R48 §6 lines 75-77, R42 §3); the Hub's Edit Video Save adds track 2 at equal levels with no volume,
   fade or pan field (`hub/worker/joincmd.py:30`; R42 lines 77-82). Not known: how an audience bed is built
   and placed (R42 §8 asks whether it masks the line); a research note before Step 9b's spec, possibly the dataset
   of item 6. The library's Holman (`docs/library/README.md`: chs. 2, 7, 10-12) is the reference for that note.

8. **Music: its own layer, three kinds** (down the line, after Step 19). (a) **Source music**:
   music heard inside the scene, placed on the set like any
   sound, coloured by its source and room, louder or softer as the camera moves to or from it. (b) **Score**: music
   over the scene that no one in it hears, with its fades in
   and out. (c) **A supplied song** (an audio file given as input): kept as given, on its own layer, never levelled,
   limited or ducked by the master's pass unless a chat message asks for it; and a scene may be **led by the song** (a music video,
   a singing number): the picture rendered to the audio, the video carried by the audio. Binaural and spatial
   placement (item 7, the board's Later strip) applies to all three. A redo never touches the song: a line found wrong
   is taken again alone and the track re-mixed around it (§12.1, §12.5), the song one untouched clip on its lane. Not known yet, a research note before any
   spec: which engine models render picture driven by a supplied song and how long a piece they take; how source
   music is coloured (Holman, the library); how the master's loudness rules treat a layer marked untouched.

## 11. The Director's education: the law in the Hub, not in a prompt
The question: how do the books in `docs/library/` make the Director think and work like a traditionally
trained director, without relying on an Open WebUI prompt? The answer is Maestro's: **the rules live in the Hub's
code and the model only proposes.** The Hub already does this for timing (a line that overruns is refused with the fix,
A.4): the books become the same kind of law. Six decisions.

### 11.1 The Director is three departments, not one model
Writing, staging and switching are three jobs. The Director is split the same way, each
department with its own written law and its own kind of enforcement:
| Department | Does | Law | Done by |
|---|---|---|---|
| **Writer** | the exchange: who says what to whom, in what order, in each one's own voice | McKee *Dialogue* (R49 §5, §7.5): a line is an action on the other; beats build; no narrated exposition; a voice per role | the Open WebUI model, through the script tools; **graded** by the Hub (11.4) |
| **Stager** | where each person is and faces, per scene | Katz chs. 9-11 (R49 §7.1): the two-, three-, many-player positions and their camera sets; the context's `home`; the stage line | **code**, from the cast and set; the model may choose among the named positions, never invent one |
| **Switcher** | the shots: when the picture cuts and to what | Zettl ch. 10 (switching principles), Stasheff & Bretz (R49 §2.7-2.9), Murch (R49 §7.2), Bordwell and the multi-camera series study (R49 §3) | **code**: the Hub cuts the exchange by rule (11.3); the model may override a shot, and the override is checked |
The model is best at lines and worst at structural rhythm kept consistent over a scene; code is the reverse. Today
the model does all three by instruction; that stays as the interim and the fallback.

### 11.2 The rulebook: every rule is data with a source, a tier and a test
`hub/modules/director/rulebook.json` ships with the Hub (it is code). One record per rule:
`{id, name, statement, source: {book, pages | "R49 §n.n"}, scope: context|scene|shot|line|exchange, tier: check|grade|
advise, params: {name: {value, source, measured: null|{...}}}, fix: "<the one line sent back>"}`.
- **check**: deterministic, in code, run inside the tool write after timing (`edit.settle`, `timing.check`); a failure is
  the ordinary refusal `{problem, fix, hints}` plus `rule: {id, source}`. The Director learns by correction, as R48 §2.
- **grade**: needs judgement; the Hub asks its own model (`assistant.chat.ask(messages, schema)`, the context's and the
  clip judge's path) with a rubric built from the rule's statement and the scene; the answer is held to a schema of
  per-rule verdicts `{rule, pass, line|shot, why}`; a failed verdict is a refusal to the Director naming the rule and
  the line. The Director never sees the rubric, only verdicts, as with the words judge today.
- **advise**: a hint only (the tool answer carries it), never a refusal.
A contract test asserts: every rule has a source, a tier, and a test that fails when the rule is removed. The docs copy
`RULEBOOK-director.md` (under `docs/video-plan/`) is generated from the JSON by a tool (never hand-edited), so the generated file reads as
the law in prose and the Hub enforces the same file. R49 §7.6 ("what the books do not answer") is the list of rules
that stay `advise` until a source or a measurement arrives.

### 11.3 The switcher: the Hub cuts the exchange by rule
The Writer writes lines, cues and who is addressed; the Switcher turns a scene's exchange into shots, mechanically,
the way a live multi-camera production is switched by convention:
1. a scene opens on the **establishing** shot (R49 §1.4; Zettl: the wide), everyone on stage in frame;
2. a **new speaker** is cut to as the speaker begins ("just as [the speaker] begins to reply", Stasheff & Bretz, R49 §2.7; Zettl p. 273;
   R50 SW-2, C-1, C-2: `cut_late_ms` 0 until measured): the speaker's single or the speaker's side of the
   OTS pair (R49 §2.9), the framing from the staging (11.5);
3. a **reaction** of the one spoken to is cut in, used sparingly, cut a second early (R49 §2.8), when a line runs past
   `params.reaction_after_ms` or carries a provocation (a `grade` rule marks the line);
4. a run of short lines holds the **two-shot** instead of ping-pong singles (Katz p. 182 ("CUs tend to break up the
   scene"), the TV "quick limit to fast cutting", R49 §3.4);
5. an **entrance** returns to the wide; a **reveal** lands on a close-up of the one it lands on, then that one's
   reaction (Grindstaff p. 250, Zettl pp. 274-275; R50 SW-9, SW-10, C-7);
6. an **audience cue** (applause, laughter) may cut to the audience, back on the speaker (Zettl; R49 §4);
7. shot lengths are held between `params.shot_min_ms` and `params.shot_max_hold_ms`, and a scene's average is
   checked against the format's measured range (R49 §3: 2.8-4.0 s for multi-camera series; the production's own number
   is **not known** and is the first measurement, 11.6).
The switcher's output is ordinary shots in the script (A.3's `shot_add`), each with the camera object (§2: `framing`,
`move`, `on`) and a new `kind`: `establishing | single | two_shot | ots | reaction | insert | audience | wide`. The
Director may add or change a shot by hand; the hand shot is checked against the same rules (a cut that lands mid-word,
a reaction with nobody speaking, a single of someone not on stage: refused with the rule). The switcher runs when a
scene is marked done (`scene_change`), and again on every later write to that scene, so the cut always
matches the exchange as it stands. Its lane is deterministic: the same exchange always cuts the same way (a seeded
tie-break), so the sketches and the lock stay stable.
**Data model (amends §2):** the picture is cut independently of the sound rows. A `reaction`, `insert` or `audience`
shot is a **cutaway**: it lies inside a line's time and the line's sound continues over it (the L-cut of R49 §2.5).
Today an event belongs to one shot and must lie inside it (A.3, A.4); the amendment: a line belongs to the shot it
starts in, and a cutaway shot carries `during: <line id>`; timing's "no overlap on a row" is unchanged (rows are
sound; shots are picture); A.9's track is built from the line rows alone, so audio is untouched by the switcher.

### 11.4 The writing judge: McKee as a grader
After a scene is marked done, the Hub grades the exchange (tier `grade`) against McKee's six tasks (R49 §7.5), each a
numbered rule with its page: a line that is no action on the other (`WR-1`); exposition narrated instead of carried
(`WR-3`); two cast members with one voice (`WR-4`); a beat that does not turn (`WR-2`). Deterministic proxies run as
`check` before the ask and cost nothing: a line whose words are a substring of the story (narration copied); the
lead speaker silent through the lead speaker's own exchange; one speaker holding more than `params.max_run_lines` in a row;
a scene off its named length. The grade is one ask per scene (not per line), with the schema held by the
backend as for the context; three asks at most, as the context's.

### 11.5 Staging: Katz's positions, then the stage line
A scene's staging is one of Katz's named patterns chosen from its cast count (two players: Position One facing /
Two shoulder-to-shoulder / Three at 90°, pp. 173-194; three players: ch. 10; four or more: ch. 11), each pattern
carrying its camera set (master, the OTS pair, the singles) with the framing heights of fig. 6.1 (p. 122). The context's
`home` (0-100, left to right) places each person; the stage line is drawn from the lead speaker's position; every shot the
switcher makes keeps each person's screen side (the 180-degree rule, Katz; R49 §1.5), and a hand shot that flips a side
without a neutral shot between is refused with the rule. The stager carries one named preset,
`three_camera`: a lead speaker standing or at a table, the others seated, audience in front, Zettl's three-camera plan
(cams left, centre, right; ch. 15) — its figure numbers filled in when R49 gains Zettl's section. **The sketches follow
the staging, not the shot list:** a panel is drawn per camera set-up (a three-camera set-up has three plates plus the
close-ups), and a shot's panel is its set-up's plate with the poses at that time. That is what keeps the furniture, the
set and the costumes where they were between shots (§10.1), and it cuts the sketch count
from one per shot to one per set-up.

### 11.6 Numbers from evidence: the measurement tool
Every numeric `param` in the rulebook names its source and holds `measured: null`. A read-only tool
(`tools/measure_cuts.py`, the Gizmo method of R40 §1.2: ffmpeg scene detection at 320 px wide) takes one real recording
file given as input, finds its cuts, and reports: shot-length distribution, cuts per minute, the fraction of shots
under 2 s, reaction-cut and audience-cut frequency (the last two by hand labels on a sample). The measured
values are written into the rulebook with the file's name and date as the source. This is the dataset
idea in its right place: not a LoRA for writing (R40 teaches a shot's look, not when to cut), but numbers for the
switcher. Until measured, the parameters are R49 §3's published figures, marked so.

### 11.7 What stays in Open WebUI
One sentence: write with the script tools and follow the Hub's refusals. The procedure (context → cast and staging →
the exchange → scene done → the switcher's cut → the lock) is taught by the tools' answers (`script_start` answers
with the next step; `scene_add` with its staging pattern and camera set; `scene_change {done}` with the cut it made and
any grade refusals), never by the block. A different model, or a bare one, meets the same law.

### 11.8 Order and proof
Audio first: these are PLAN.md Steps 13-16, after 9d and after casting, the stage and the
records (Steps 10-12, §13-§15), because A.9's track is built from the
line rows and the switcher does not touch them. Each step is proved as R48's engineer findings were: the rulebook's
contract test; a fixture exchange cut by the switcher into the expected pattern, asserted shot by
shot; property tests (no shot under the floor, a speaker change cut within `params.cut_late_ms`, no screen side flipped
without a neutral); the grade's schema held by the configured backend in the planner harness; and the run on the server.
Not known (recorded, not solved here): the production's shot-length figure (11.6); whether the configured model grades McKee's
rules reliably (the harness's readout decides); how a cutaway renders in Stage C (one clip per shot stands; a cutaway
is a clip of its own with the line's sound kept).

## 12. The track is a mix, not a render (amends A.8, A.9)
The design: no single 90-second generation of everything. Lines are spoken one at a time, each judged,
measured and levelled; a cough is trimmed, not re-rendered; a second speaker may start while the first is still
sounding; music and the audience sit on their own layers; trimming never re-renders; one line's change re-renders one
take; the whole piece plays on the timeline, changes are asked for in the chat, and the Director suggests its own.
Everything below stands on what exists: one generation per event (R48 §6, proven), the words judge (Whisper on the
worker, `hub/worker/adapters/judge.py`, heard %, first miss, extra speech), and the Hub's own ffmpeg
join with per-item level, fades and sidechain ducking (`hub/worker/joincmd.py`). Seven decisions.

### 12.1 Takes: every sound is its own file, kept
A **take** is one generation of one event: a line (its own `Speaker 1:` block, its speaker's sample, `duration_seconds`
above the planned length, R48 §5) or a cue (its kind's sound model, R48 §6). Takes are WAVs in Sounds, the files, named
`<script>/<event id>-<n>.wav`. The script records each take: `"takes": {<event id>: {"file", "hash", "tries",
"measured": {"speech_start_ms", "speech_end_ms", "lufs", "true_peak_dbtp"}, "judge": {"heard", "first_miss_ms",
"extra_speech", "verdict": "ok"|"flagged", "why"}}}`. `hash` is the event's fields that make its sound (speaker,
words, language, emotion, pace; a cue's words and kind): a take whose hash no longer matches its event is **stale**
and is the only thing `Track` renders again. Nothing else is ever re-generated by a trim, a move, a level or a fade.

### 12.2 Every take is judged, measured and levelled before it is placed
On arrival, in the worker, without a model ask:
1. **Heard**: the words judge against the line's words (as today); `extra_speech` when speech is heard outside the
   words; under the bar → another take, up to `params.takes_max` (3), then flagged on the timeline.
2. **Boundaries**: the speech's real start and end inside the take (silence gate, the judge's word timestamps):
   `speech_start_ms`/`speech_end_ms`. Lead and tail silence or stray sound are outside the clip's in/out by default: a
   garbled first second is cut, not re-rendered, when the words after it are heard whole.
3. **Level**: integrated loudness and true peak of the speech (ffmpeg `ebur128`); the take's clip gain is set so its
   speech sits at the scene's **dialogue anchor** (`params.dialogue_lufs`); a take whose peak would clip after the
   gain, or whose loudness is more than `params.level_tolerance_db` off before gain, is flagged "level".
4. A cue take: boundaries and level only; a `reaction` take (applause, laughter) also measured for its natural decay,
   so it is never cut dead (§10 item 7).
The rulebook (§11.2) carries the numbers with their source: `dialogue_lufs` and `true_peak_dbtp` from the broadcast
loudness standards (EBU R 128 / ATSC A/85; the spec cites the documents' text), `level_tolerance_db`, `takes_max`,
the ducking depth/attack/release (R42 §3's engine defaults as the first values). Holman (library) is the reference
for intelligibility, overlaps and crowd (chs. 2, 7, 11, 12).

### 12.3 Lanes: the mix is the timeline's rows
The mix is a set of **lanes**, one per row the timeline already draws: a dialogue lane **per speaker**, a `reaction`
lane (the audience), an `effect` lane, a `music` lane and a `room` lane (the set's own tone, under everything, from one
ambience take). Two speakers may overlap because they are on different lanes (an interruption, McKee's beat that turns,
is written as two lines whose times overlap; timing's "no overlap on a row" holds per speaker). Each lane holds
**clips**: `{take, at_ms, in_ms, out_ms, gain_db, fade_in_ms, fade_out_ms}`; a lane has its own `gain_db` and, for
`reaction`, `effect` and `music`, a `duck` under the dialogue lanes (a 10 dB volume envelope from the placed dialogue
clips; R54 measured the join's `sidechaincompress` at 2.4 dB; the room is never ducked). The
script stores it as `"mix": {"lanes": [...], "target": {"lufs", "true_peak_dbtp", "source"}}`. Clips are
**non-destructive**: `in_ms`/`out_ms` trim the take; nothing is written to the take file, ever.

### 12.4 Placement: measured sound, not planned slots
When takes are judged, the Hub places clips from the measured speech, not from the plan: a line's clip starts at its
planned time, its sound trimmed to its measured boundaries; the next line of the same shot starts at the previous
line's measured end plus the turn pause (A.4), unless the Director wrote it to overlap; every later event is pushed
by the overrun (A.9 as before); the planned times in the script are replaced by the measured ones (`measured` on the
line, 9c) and the timeline moves with them. A cue anchored to a line's end follows the measured end. Dead air longer
than `params.dead_air_ms` between lines of one exchange is flagged (advise), never silently filled.

### 12.5 The mixer: the Hub's ffmpeg graph, in seconds
The track is rendered by the Hub's own join command (`joincmd.py`), extended from two tracks to lanes: each clip
`atrim` to its in/out, `afade` at its ends, `volume` by its gain, `adelay` to its place; lanes summed; the reaction,
effect and music lanes ducked by the dialogue's envelope; the measured gain to the target and a true-peak limiter last
(R54: one `loudnorm` pass missed −1 dBTP; the engine's own mixer uses `loudnorm`, R48 §6; the Hub's is chosen so the mix never depends on the fork, R9). A
re-mix takes seconds, so **every change of a clip, lane or level re-mixes at once** and the timeline's Play (9d) plays
the new mix from the playhead. The track WAV is `Sounds/<script>.wav`; the stems (one WAV per lane) are written beside
it when a chat message asks, for the editor. The mix is checked after render as 9c says, by the judge on the whole track:
each line heard at its time, each cue present, the integrated loudness at the target.

### 12.6 The Director's ear: checks and suggestions on the mix
Rulebook rules of scope `mix`, from Holman and the standards, run on the measured mix: a line whose speech is more than
`params.mask_db` below the bed under it (masking, Holman ch. 2); two lines overlapping where neither was written as an
interruption; a reaction cut dead before its decay; a music cue under no ducking; dead air (12.4); the track off its
loudness target. Each is a `check` (refused at the lock of the track) or an `advise` (a suggestion line in `Track`'s
answer: "shot 3: Character 2's line sits 9 dB under the applause; lower the reaction lane or move the cue"). In the Script
chat, after `Track`, the chat message's words become mix tools: `take_change {id, gain_db | in_ms | out_ms | redo}`,
`lane_change {lane, gain_db | duck}`, `clip_move {id, at_ms}`; each re-mixes; only `redo` generates. This is how the
Director works from the chat message about what is heard: the message names what it hears, the Director changes the mix or redoes one take, and
says what it would change itself.

### 12.7 The timeline shows the sound
Each line and cue box shows its take state: none / rendering / ok / flagged (why) and its measured length against the
planned one; a trimmed clip shows its in/out; the lanes' levels are the rows' levels; the sketch row (6b) and the stage
(Step 5) run with Play. Binaural and spatial placement (§10.7) come later as a per-clip `pan`/position on the same
clip record: the lane model is built to take it without re-shaping.

### 12.8 Proof
The mixer is pure (a request in, an ffmpeg command out, as `joincmd.py`), so it is tested without rendering; the
judge and the measurement run in the planner/worker harness on fixture takes (a take with a garbled first second, a
take 6 dB hot, a cough in a gap, an overlap); the runs on the server are each step's §7. Not known: whether `ebur128`'s
speech-gated loudness matches the ear on the voices (the run on the server decides the anchor); the sound models the model folders hold for cues
(R48 §6, unchanged).

## 13. Casting: the character sheet is the identity
The design: a headshot in, a 360° turnaround out, costumes tried on it, one approved; after that the
Director *knows* the character (age, build, face, costume) and never invents the character. A published ComfyUI workflow did this on H3 and held (the H3 character-sheet
generator on huggingface.co; R51): a MiniMax H3 **Ref2VA**
generation from up to 9 reference pictures, an "A prompt" with one line per picture saying what to keep and what to
ignore (`<Picture N> - keep …. Remove …`), a "B prompt" for a slow orbit with no cuts ("stands like a statue"), 124 frames
(6-panel: front, both sides, back, two face shots) or 73 (4-panel), the frames stitched into a sheet; "faces carry
across on their own but wardrobe drifts", so clothing is described in words; "if you don't rule things out by name,
backgrounds and the wrong person's hair sneak through". The Hub already has every part: a Ref2VA clip with
`<Picture N>` boxes in box order (R16 §4 rule 8; the clip route), the 17n+5 frame rule (124 = 17×7+5), ffmpeg frame
extraction, and R48 §8's context fields `look / costume / ignore`, which are this workflow's A-prompt lines. The
expressions sheet is not used (no stills are made). Decisions:
1. **A Casting tab** (module `casting`, tab "Casting"), beside Storyboard. A character is cast from the pictures of the character: a
   headshot and up to 8 more "bits" (a costume from one picture, a hat from another), each with its keep/ignore line
   (the A prompt, typed or chosen), and the character's facts that no picture carries: age, build, voice (the character's sample, V1). "Cast"
   makes **one orbit clip** on a Ref2VA video model picked in Generate (picked there and nowhere
   else, never changed by the Hub; the Director finds the model, not a field: the pulldown's model
   when Ref2VA, else the last Ref2VA pick, else the only one, else one refusal line), 124 frames, the B prompt fixed by the Hub (a slow
   full turn, neutral stance, flat light, plain backdrop), the A prompt from the character's lines in the workflow's own form
   (`subject_definitions:` / `retention_analysis:`, the labels the Hub's shot prompts already use). The Hub extracts the
   six views at the frames the workflow uses (R51: front, left, back, right, front face, three-quarter face; the indices
   from the 6-panel workflow file, not guessed) at full size and shows the **sheet** (3 × 2).
   Per R51: the Hub's Generate takes 3 reference boxes (`cast.BOXES`, `cast.py:21`) while the
   engine takes up to 9 (the workflow's README): casting needs up to 9 boxes on this route; the reference detail
   `max` (`image_refs_relative_size`) is not sent today; frame extraction at full size is new (the judges' decode is
   scaled to 640 wide). Approve, ask again (new seed) or change a line; nothing is a character until approved.
2. **The sheet is the identity.** Approved, it is written beside the character's picture in Characters:
   `Characters/<Name>/sheet/{front,right,back,left,face-1,face-2}.png`, the orbit MP4 beside them, and
   `Characters/<Name>/casting.json`: `{facts: {age, build, …}, keep: [...], ignore: [...], variants: {...}}` — files
   in the Characters folder, never a log (CLAUDE.md). The context's cast entry (§2) gains `sheet: true` and `variant: <name>`.
3. **Costumes are variants of one identity.** A costume change is a second orbit whose references are the approved
   sheet's face frames (keep: face, hair, age, build) plus a costume picture or words (keep: the outfit): a named
   variant `Character 2/<variant>`, its own sheet, approved the same way. A script's context names the variant; the Director
   may change which variant a scene wears, never what the character is.
4. **The context stops inventing.** `script_start`'s ask no longer writes `look`, `costume` or `ignore` for a cast
   member with a sheet: the Hub copies them from `casting.json` and the variant; the model is told the facts and asked
   only for `home`, the set and the style. A cast member without a sheet is cast as today (the fallback), and the context
   card says "no sheet: cast in Casting" (one line, a fact, not an explanation).
5. **Every picture of the character comes from the sheet** (§15): sketches, Stage B stills and Stage C renders put the character's sheet
   frames in the boxes with the character's keep/ignore lines, the frame chosen by the side the character shows the camera (the stager's
   screen side, §11.5: a character on screen left showing the right side gets `right.png`).
6. Nothing locks the character in: a sheet can be recast, a variant added, a fact edited; a script's context that names a variant
   deleted from the folder is listed with that problem (A.1's rule), never broken.

## 14. The stage: a locked set with a live audience
The design: a stage, a 180° set, built once, locked like a character, changed only
by asking (add, move, remove), with the audience in it; nothing on it appears or wanders between shots.
1. **A Stage tab** (module `stage`, tab "Stage"). A set is built like a character: from a picture of the stage
   (or a described one), the Hub makes **one slow pan clip** of the empty set on the picked Ref2VA model (B prompt:
   an empty stage, no people, a slow pan from stage left to stage right, then the reverse onto the audience seats;
   no cuts), and extracts the **plates**: the wide (establishing), Zettl's three camera positions (left, centre,
   right; §11.5's `three_camera` preset), and the reverse (the audience). Approve, ask again, or say a change.
2. **The set record**: `Sets/<Name>/plates/{wide,left,centre,right,audience}.png`, the pan MP4, and `set.json`:
   `{description, elements: [...], props: [{name, place, owner?}], camera_plan: "three_camera", audience: true}`.
   The context's `set` (§2) names a set record (`"set": {"name", "plate": ...}` already exists; it gains `plates` and
   `camera_plan`), and its `elements`/`props` are copied from the record: the Director never invents a prop; a prop
   not in the set is refused with the fix ("add it to the set in Stage, or ask: add a table stage left").
3. **Changes by asking**: in the Script chat or the Stage tab, "add a bench stage left", "remove the table", "move the
   table to centre": the Hub makes a new pan with the current plates as references and the change as the A/B prompt
   ("keep everything; add a bench at stage left"), extracts new plates, shows old against new; approved, the record
   changes and every panel of every script on that set is marked stale (6b) and redrawn. A rejected change leaves the
   set as it was. The set is **locked** between changes: nothing in a sketch or render comes from outside its record.
4. **The audience is part of the set**: the reverse plate and the `audience: true` flag; the switcher's `audience`
   shots (§11.3) and the reaction lane (§12.3) exist only when the set has one; a set without an audience refuses an
   audience cue with the fix.
5. §9 item 8 (whether a plate alone holds the set across shots, or a reference video of the empty set is needed) is
   answered by this design in both directions: the pan clip *is* the reference video, kept; the plates are its frames.
   The run on the server on Stage C decides which the renders need.

## 15. Consistency along the timeline: one source for every picture
The sketch under each shot stays the same set, the same people, the same costume, from the first panel to the last,
because every picture is built from the same approved records, never from words the model made up:
1. **A panel's request** = the shot's camera plate from the set record (by the shot's set-up, §11.5) in `<Picture 1>`,
   then each in-frame character's sheet frame for the side the character shows (§13.5) in the next boxes, each with its
   keep/ignore lines, then the poses at that time (R48 §4) and the shot's `framing`; the prompt words name only what
   the records hold (R48 §8). A picture model that takes no references (`ref_caps`) gets the records'
   words only, and the card says so in one line. Panels are drawn per camera set-up where the staging exists
   (§11.5) and per shot before it.
2. **Stale is defined**: a panel is stale when its shot's plate, any in-frame sheet or variant, the poses at its time
   or its camera changed (6b's rule, widened to the records), and only then; a redraw never changes a panel whose
   inputs are the same (the seed is kept in the panel record), so the storyboard does not drift between redraws.
3. **The same boxes feed Stage B and C**: the previz stills and the Ref2VA clips take the plate and the sheet frames
   in the same box order with the same lines, so the sketch, the previz and the render are three drawings of one
   source. R46 (a production from a clip without training) and R40 (a production-style LoRA) are then additions on top of a
   locked set and cast, not substitutes for them.
4. **Locked means locked**: a script's lock (A.7) refuses while a cast member has no sheet or the set has no plates
   (one line each), so a locked script can only be drawn from records; a script may still run unlocked with
   the fallbacks, for play.
5b. **The sketch is drawn over the stick figures**, so the sketch and the stage view show one composition.
   A panel's composition is the shot's **control frame at the panel's time** (§17.1: the stager's places, the poses,
   the camera's framing and move, drawn on the script's canvas): that frame goes in the first box as the layout to
   follow ("the people stand where the figures stand, in those poses, at this framing"), then the plate, then the
   sheets. The sketch, the stage view and the video's control are one composition drawn three times. Until the
   stager (Step 14) exists, the control frame is the flat stage view (Step 5's) at the shot's framing; a picture model
   that cannot follow a pose picture gets the plate and sheets only, and the card says so in one line. The stage view
   in the Storyboard tab shows the shot's camera framing, not the flat test line-up, once the stager exists.
5. Not known (recorded): whether a 124-frame orbit holds on the picked model and quantization and how long it takes
   on the server's GPU (the first cast on the server decides); whether a one-picture stage pan holds a 180° set (the first set on the server decides; the
   fallback is more of the pictures of the stage as references); whether the picture model takes references for
   sketches (`ref_caps` says; else words). The MiniMax H3 community licence covers outputs, as the workflow's README
   notes; the Hub's own use.

## 16. The house: the audience as set and as cast
The design: an audience that is believable and consistent (hair and clothes true to the set's `era` field, the same
people throughout), optional and peripheral (a production may never show it, or live in it: a cast member standing
among the seats with the camera turned round on its pedestal, a cut to one face when a line lands, a cast
member in a seat spoken to), the set's own 180° as the world and the house as the
other 180° that a shot may turn to. What the manuals say: a seated audience is warmed up and coached
to react, and its reaction shots are taped and inserted (Grindstaff pp. 128-130; the warm-up, pp. 123-124); the
reaction shot is used sparingly and cut a second early (R49 §2.8); the reverse onto an audience needs its own camera
or a cutaway to cross the line (Zettl ch. 10, remote example p. 469; ch. 16); an audience on camera is a production's
own choice, and its monitors go off when someone in it is on camera (Zettl, ch. 13). Decisions:
1. **The house is the set's second half.** A set record (§14) carries `audience: "none" | "heard" | "seen"`.
   `none`: no audience in picture or sound. `heard`: the reaction lane (§12.3) is allowed, no house
   in picture (laughter and applause only). `seen`: the house exists in picture: its plates are made with
   the set's pan (§14.1: the reverse onto the seats) and stored as `Sets/<Name>/house/{wide, left, right, row}.png`,
   `row` a medium plate of two or three rows for reaction cut-ins. The stage's 180° is the default world; a house
   plate is drawn only when a rule or the Director turns to it. That is what "peripheral" means here.
2. **The crowd is a plate; the faces are cast.** The mass of the audience is the house plates: made once from the
   set's words for the era (`house: {era, dress, hair, size}` in `set.json`, the keep/ignore lines
   for the pan), approved, changed only by asking ("make them older", "fill the back rows"), the same people in every
   shot because every house shot is drawn from the same plates (§15). A face that is seen close is never the plate's:
   a **featured member** is cast in Casting (§13) with a 4-panel sheet (the cheaper orbit at 107 frames: the workflow's
   73 is legal in ComfyUI but under the Hub engine's 107-frame minimum, R51, `clipplan.py`), as an extra:
   `Characters/<Name>/casting.json` `{role: "audience", seat: {side, row}}`. A reaction cut-in is always a featured
   member's single on the `row` plate (the member's sheet frame in the box, the plate behind), so the emotion that "brings the
   moment home" is on a face that exists. A set with `seen` names at least two featured members, or reaction cut-ins
   stay on the `row` plate at medium distance (no face close enough to drift).
3. **A cast member in a seat.** The context's `home` (0-100 across the stage) becomes a **place**:
   `{where: "stage", x}` or `{where: "house", side, row}`. A cast member with a sheet may sit in the house; the member's
   lines are allowed from the seat; the member's single is drawn on the `row` plate.
4. **A cast member among the audience.** A blocking event, `move {character, to: place}` (A.3 gains it; the stager
   keeps it), puts a cast member in the house for a stretch; while the member is there the switcher (§11.3) uses the **reverse
   set-up**: the camera turned on its pedestal from the stage to the house, the member at a seat with rows behind
   (`member_in_house` shot kind: the `wide` or `row` house plate, the member's sheet frame, the one the member faces). Crossing
   to the reverse and back is bridged as Zettl says: a cutaway or a neutral shot between, never a straight flip
   (the 180-degree rule, §11.5; a hand shot that flips without one is refused).
5. **Audience shot kinds for the switcher** (§11.3 gains them): `audience_wide` (the house wide, on an applause or
   entrance cue), `audience_reaction` (a featured member's single or the `row` plate, cut in a second before a line
   lands and held `params.reaction_hold_ms`), `member_in_house`, `member_single`. When they fire: on a `reaction` cue,
   on a line the writing grade marks as a provocation or a reveal (§11.4: a `grade` rule `WR-5`, Grindstaff), on a `move` into the house; never on a set with `audience: none`; on `heard`, the sound fires
   and no picture does. All of it is law in the rulebook with its page.
6. **Sound follows the picture.** The reaction lane's takes (§12.3) are placed under the audience cue as before; a
   house shot does not change the sound, so `heard` and `seen` share one audio design.
7. **Lighting is later**: Zettl chs. 5-6 are the source; the set record carries a `lighting`
   field for it; nothing is built from it now.
8. Not known (recorded): whether a house plate of fifty people holds between redraws (the plate is reused as a
   picture, so it holds by construction in sketches; in Stage C's renders the run on the server decides); whether a 107-frame orbit
   gives a usable 4-panel sheet on the picked model (the first extra on the server decides).

## 17. The control: the plan becomes motion, one take per shot (amends §4-§5)
The design: everything is decided before a single frame renders; the
stick figures are the Director's only guarantee that the camera and the bodies do what the storyboard says; one
render per shot, never a continuous eight minutes; re-renders only for the model's own failures, never for planning.
§4 (the control video, the previz) and §5 (the shots) already hold the engine facts (R48 §7: ControlNet-Union, 362-frame
control windows, 17n+5, letter `V` never `PV`, kept sound `A`, overlap 18). What follows closes the gaps between them.
1. **The control video is the law of motion, per shot.** B.1 stands, made per shot rather than per track: each shot's
   control clip is drawn from the script alone: the stager's places (§11.5, §16.3), the pose keyframes tweened (A.5),
   hands and the 68-point face, on the shot's camera set-up. **The camera is in the control**: the shot's `framing`
   sets the world's scale and offset; its `move` (push-in, pan, the pedestal turn to the house, §16.4) is an eased
   transform of the whole world across the shot's frames (never a crop: redrawn at scale, §1), with the rulebook's
   limits on speed (Katz chs. 17-19 as the source). The model is told where every body and the frame edge are on
   every frame; there is no camera left to improvise.
2. **The mouth follows the real audio.** The take exists before the render (§12): the control's mouth openness per
   frame is the smoothed envelope of that speaker's take (RMS over the frame's window, scaled to the face's mouth
   points), zero outside the speaker's measured line windows. The kept soundtrack asks for lip sync (R48 §7); the control
   agrees with it frame by frame instead of fighting it. No one else's mouth moves (C4's mouth judge, kept).
3. **Emotion is drawn, not hoped for.** A line's `emotion` (A.1's field, in the `Speaker` block) selects a face preset
   (brows, eyes, head: a small set in `poses.ts`, R48 §4's fixed strokes) held through the line and eased at its
   edges; a beat the writing grade marks as a turn (§11.4) gets an `advise` to the Director to set a gesture keyframe
   there (a pose from the seven, or joints). Realism comes from the sheet (identity), the plate (set), the control
   (motion) and the take (voice) agreeing; the prompt words add nothing those records do not already say.
4. **One take per shot, by construction.** A shot's render takes: the plate for its set-up (`<Picture 1>`), the
   in-frame sheet frames for the sides shown, the shot's control clip (`V`), the mix slice for the shot (`A`, from the
   track: lines, cues and the bed, already levelled), the prompt from the records, and a seed kept in the shot record.
   The same inputs give the same clip; a re-render happens only when a judge (face identity against the sheet, the
   mouth against the take's windows, framing against the control, words against the slice, unscripted speech) finds
   the model's own failure, up to the rulebook's `takes_max`, then flagged with why. Nothing is re-rendered for a
   planning change, because planning is locked (A.7: the lock refuses until the sheet, the plates, the track and every
   shot's control clip exist).
5. **Two routes, one of them proven first.** Whether the Ref2VA model (identity from references) takes the control
   video and the kept sound in one pass is not known (§9.1, §9.4): the ControlNet module is not on the server's disk, and its
   base may not be Ref2VA. So: **route 1** (one pass: references + control + sound on one model) is tried first in the
   engineer's harness and in the first Stage C run on the server; **route 2** (two passes) is the fallback, already the
   previz window rendered on the control model from the stick figures and the sound (B.2), then the shot on the
   Ref2VA model with the previz window as the reference video (`V-U`, 2-15 s) for camera and layout, the sheet frames
   for identity, the slice for sound. Both keep every decision of 1-4; route 2 costs one render more per shot.
6. **Never an eight-minute render.** A shot is the render unit and is at most one control window (362 frames,
   15.08 s; A.4's cap exists for this reason); a cutaway is a shot of its own; an eight-minute script is about 150
   jobs queued one at a time, each within VRAM, each resumable after a restart (the job book), each filed in Clips;
   C3's join assembles them with the whole track as the one sound. A failed shot blocks nothing but itself.
7. **The animatic is the dailies.** Before any Stage C render, the previz (B.2-B.4: stick figures with the real
   track, judged against the sketches) plays on the timeline (9d); the whole plan is watched moving with its sound for
   the cost of the previz alone, and what to change is said in the chat (the mix tools, a pose, a cut); every change
   re-draws the control clips (seconds) and re-renders only the previz windows it touched. Stage C starts on a render press
   ("Render"), never on its own.
8. **The judges' bars are law** (§11.2): face similarity to the sheet, mouth-in-window, framing match, words heard,
   are rulebook params with their source and their first values from the engineer's measurements (the judges'
   current bars), tuned by the runs on the server; a "flagged with why" always names the bar and the number.
9. Not known (recorded, decided by the runs on the server): route 1 (5); whether the control model renders a stick-figure world as
   real bodies on the weights (R48 §7 OPEN); the face preset count that reads as emotion at 540p; the envelope-to-mouth
   scale that the mouth judge passes.

## 18. Format: one aspect for everything, the era's picture, and the supers
1. **One aspect per script.** A set record (§14) carries the
   `format` it was built in (`{aspect: "4:3"|"16:9", height: 540|720|...}`, from the Generate pick when the set is
   made); the script takes it from its set, and every picture of the script follows it: the plates, the sheets' use,
   the sketches (the sketch size is "the smallest size Generate offers at the script's aspect": 576×320 at
   16:9, 448×336 at 4:3, multiples of 16), the control canvas (§17.1, one canvas), the renders (R48 §7: the output takes
   the control video's aspect), the join. A shot never changes aspect; a set rebuilt in another format is a new record.
2. **The era's picture is a style, applied last.** A period broadcast look (the softness, the video gamma, the aspect) is
   the set record's `style` line for the renders and, later, a post pass at the join (an ffmpeg filter chain the
   approved by eye: R46 and R40 are the additions on top, §15.3); never a prompt word that a model may ignore,
   never a LoRA before there is a measured reason (§10's rule).
3. **Supers are the Hub's, never the model's.** A production may name its cast on screen (a lower third: "CHARACTER 2 · Super 1").
   A `super` event (`{kind: "super", at_ms, end_ms, lines: [str, str]}`, written by the Director from the
   context's names and the story, or typed) is overlaid by the Hub at the join (ffmpeg `drawtext`, a lower-third
   preset per set record: font, band, position, the era's look), on the timeline as its own row, and never put into a
   render's prompt (R48 §8's rule: no text drawn by a model). The lock needs nothing of it; it is the one element the
   model never touches.
4. Known risk, recorded: whether the Open WebUI model carries a twenty-line exchange with a dozen tool calls per
   scene and the grade's schema (§11.4) reliably; the design moves structure (staging, cutting) into code for this
   reason, leaving the model the lines.


## 19. The storyboard is the picture track: a professional board, not panels hung on the dialogue (amends §2, §11.3, §15, §17.1)
The design: sketches must not be locked to the dialogue's time stamps. The camera changes while someone
keeps talking (a cut to a prop as it moves); a storyboard is scene and camera management, the dialogue runs under
it. Today a shot *contains* its lines (A.3, A.4), a panel is drawn at a shot's start and at a pose change (A.6), and
the Director writes shots around lines: the board is a by-product of the dialogue rows. Katz says what a board is:
"a description of the physical environment … and of the spatial quality of a sequence (staging, camera angle, lens and
the movement of any elements)", conveying "the shot flow", with "descriptions below each panel" of action, transition
and camera, and the dialogue written beside the panels it accompanies (R49 §7.4.2, Katz pp. 28, 37, 44-45, 64-65);
"Reading a storyboard is a matter of editing with your eyes" (p. 189). Six decisions.

### 19.1 Two tracks: the picture track and the sound rows
The script (version 3; version 2 read as 3) has a **picture track** of shots and the **rows** of lines, cues and poses,
each with **absolute** times. A line never belongs to a shot; a shot never contains an event. A shot is
`{id, start_ms, end_ms, setup, framing, on, move, action, beats: [{at_ms, text}], seed, panels: [...]}` on its own
track; cut points fall anywhere, inside a line included (the L-cut, R49 §2.5: the sound runs on). A shot is at least
`SHOT_MIN_MS`; it has no upper bound on the board (a 30 s wide is one shot); the renderer, not the board, splits a long
shot into windows of ≤ 362 frames at render (§17.6, C2's rule, invisible on the board). Timing's rules on the rows
stay (no overlap on a row, the line's length from its words, the turn pause, the push by an overrun, no dead air the
Director made); its rules that tied events to shots go ("inside its shot", "a shot's end is its last event's end",
`LAST_POSE_MS`). Shot-relative times become a way of *naming* a time, not of storing one: `{shot: n, at}` and
`{speaker, nth, at: start|end|word n}` (the listing's references) resolve to absolute ms. §11.3's `during` is no longer
needed. Migration: a version-2 file's shot-relative offsets become absolute on first read; nothing else changes in it.
The audio track (§12) is built from the rows alone and is untouched; nothing built on it may rely on a line lying inside
a shot.

### 19.2 Camera setups come from a floor plan (Katz's method, Zettl's plan)
The set record (§14) carries a **floor plan**: a top-down plan in metres with the footprint of every element and prop,
the audience area, and the named **camera positions** of its plan (`three_camera`: Zettl's cameras 1-3 and the
reverse, §11.5; each with its height and default lens). The stager (§11.5, Step 14) places each person on the plan
(`x, y, facing`) by Katz's patterns. A **setup** is `{camera, lens, aim}`; the Hub **projects** the plan through it
(a simple perspective: each person a box of that person's height, props as boxes) and gets the **frame layout**: who is in
frame, where across the frame, at what scale, which side each shows (each one's facing against the camera's direction), and
who is in front of whom. A framing asked for by name ("close shot on Character 2 from camera 2") is solved into the lens and
aim that put Character 2's head and shoulders at Katz's framing height (fig. 6.1, p. 122). That one projection is the stage
view in the Storyboard tab (no more flat line-up), the control frame's figure placement (§17.1), and the sketch's layout
(§15.5b): three views of one geometry. The book's composition rules become checks on the layout (R50 ST rules: the
180° line drawn on the plan, matched pairs at one lens and distance, headroom and lead room, "only camera positions
within the established semicircle", Katz p. 130, R50 ST-3).

### 19.3 A panel is a shot's composition at a moment, never a line's
Panels are drawn at: a shot's start; each **beat** the Director names in the shot (`beat_add {shot, at, text}`: "Prop 1
falls", "Character 2 picks up Prop 2"); the end of a camera move (Katz's frame-within-a-frame, p. 42: a push-in is
two panels); a pose-category change that the layout makes visible (A.6's rule, kept). A beat's `at` may be a word in a
line (`{speaker, nth, word: 7}`): the planned word time from the words and the pace, the measured word timestamp once
the take exists (§12.2's judge gives them): "cut to Prop 1 as the speaker says word 7". The panel's picture: the setup's plate
(the set pan's frame at that camera position and lens, §14.1) as the background, the control frame of that moment as
the layout, the in-frame sheet frames for the sides shown (§13.5), and for an insert the **prop's own picture** (each
prop in the set record gains one: a full-size crop of the plate, or one approved close-up generated from the plate
region and the set's style, kept with the record), words from the records only, the seed kept (§15.2). The caption
under the panel is the board's language: `1.3 · cam 2 · CU Character 2 · push-in · Prop 1 falls`.

### 19.4 Who cuts, and what is checked
The Director writes shots freely on the picture track (`shot_add {setup, from, to}` with references, `shot_change`,
`beat_add`), including a cut in the middle of a line; the switcher (§11.3, Step 15) proposes the coverage and
rewrites nothing the Director placed by hand; the rulebook checks every cut on the board (R50 SW rules: the cut on a
new speaker as the speaker begins, a reaction used sparingly, no near-identical cut, no jump from extreme long to extreme close,
the line crossed only with a cutaway or a neutral; and the layout rules of 19.2). A line whose speaker is not in frame
is legal (an OTS on the listener, an insert, a reaction) and the control's mouth for the listener is simply not drawn (§17.2);
the mouth judge checks only speakers in frame (§17.4).

### 19.5 The Storyboard screen reads like a board
The picture track is the top row: the panels with their captions, cuts marked; the rows of lines, cues and poses run
under it with absolute times, a line box spanning every cut it crosses; the stage shows the projected frame of the
shot under the playhead; Play runs it with the sound (9d) and, as Katz's flip-book (p. 43), a panel-strip mode holds
each panel for its shot's length. Shift + wheel scales the tab with the rest of the Hub (7b).

### 19.6 Consistency of the small things
Every background is a frame of one pan (one generation per set), every face a frame of one orbit, every prop one
kept picture, every layout one geometry, every panel one kept seed; a panel is redrawn only when one of those inputs
changed (§15.2). A sketch continuity check (advise, not a refusal: sketches are guidance) compares each panel with its
plate (background) and its sheets (identity) by the face and layout judges and lists drifts on the card ("panel 1.3:
Prop 1 moved; Character 2's costume changed"), so a drift is seen on the board, long before a render.

### 19.7 Order
Step 11b (the picture track, the floor plan, setups and projection, beats and prop pictures) after Step 11 (the
stage gives the floor plan) and before Step 12; Steps 12, 14, 15 and 17 build on it as amended below. Nothing before
Step 8 changes; 9a-9d are told only that no mix rule may rely on a line lying inside a shot. Not known (recorded):
whether the picture model follows a layout picture (a pose image) together with a plate and sheets in one job (the
`ref_caps` and the first Step 12 run on the server decide; a model that takes only words gets the records' words and the layout as
words, "Character 2 screen right, close, facing left"); whether a simple box projection reads well enough for the stage
view (the Step 11b run on the server decides).

## 20. What the engine can do, read in its code (R52; amends §15, §17, §18, §19)
R52 read upstream af2ed29 for every claim below (`docs/video-plan/research/R52-engine-references-and-control.md`).
1. **Route 1 does not exist; route 2 is the design.** The H3 ControlNet model is the FL2VA base, loaded without
   reference mode (`minimax_h3_handler.py:528-530`, `:1129`), and the pipeline refuses any reference picture without
   the Ref2VA checkpoint ("Image, video, and audio references require the Ref2VA checkpoint", `pipeline.py:967-968`);
   Ref2VA has no control (`:744-746`). So §17.5 is decided: each shot is **two passes**: (a) the previz window on the
   control model from the stick figures with the mix slice as kept sound (`V` + `A`; 17n+5 frames, ≥ 107, windows
   ≤ 362), (b) the shot on Ref2VA with that previz as the reference video (`V-U`, ≥ 2 s, only its first 362 frames kept
   and the whole of it sent to every window, `:757`, `:111`), the plate and the sheet frames as pictures (≤ 9 pictures,
   ≤ 12 files, `:985-986`, `:1065-1067`), and the slice as kept sound (`AS`). §17.4's "one take per shot" is per pass:
   the previz is judged against the control, the shot against the previz, the sheets and the slice. The previz is
   already Step 17's dailies, so the second pass costs nothing the plan did not already pay for in time to decide.
2. **Sketch panels: the layout is the guide, not a picture box.** Only the Qwen-Image Edit Plus family (2509/2511) and
   Qwen-Image 2.1 take a raw layout image (`image_guide`, letter `V`, "Qwen Raw Format") together with separate
   reference pictures in one job (`qwen_handler.py:101-107`, `qwen_main.py:231-232`; `qwen21_handler.py:130`,
   `qwen21/pipeline.py:220-224`, ≤ 10 pictures with the guide); the engine puts the guide first. So a panel's request
   is: `image_guide` = the layout (Step 11b's projection drawn as stick figures), `video_prompt_type` `V` + `KI`, and
   `image_refs` = [the setup's plate, the in-frame sheet frames, a prop's picture for an insert]; never `PV` (the pose
   detector must not run on stick figures). In the prompt the layout is Picture 1, the plate Picture 2, the sheets
   from Picture 3. Other picture models: Krea 2 edit takes the layout and ≤ 2 references (layout + plate + one sheet);
   Z-Image Turbo, Flux 2 Klein: no layout with references: the panel gets the layout composited onto the plate as one
   reference, or the layout as words, and the card says which in one line. The Hub sends no `image_guide` and never
   `KI` today, and caps references at 3 (`tasks.py:86-109`, `models.py:28`): Step 12 adds all three on the sketch
   route only.
3. **4:3 sizes must be exact multiples of 32.** H3 sides divide by 32; the Hub's 540p "4:3" is 736 × 544 (1.353, not
   4:3); 640 × 480 is exact; a panel takes the layout picture's aspect (`wgp.py:8038-8040`). So §18's canvas is
   **640 × 480** for 4:3 renders and the control, and the sketch at 4:3 is **512 × 384** (§18.1's 448 × 336 is not a
   multiple of 32 in height); 16:9 stays as it is.
4. What only the server can tell: which model each of the picture-model files is set up as; whether an
   edit model follows a raw stick-figure layout with a plate and sheets, and its time and VRAM with five pictures;
   whether the ControlNet module and its base are on the server's disk; whether a `V-U` previz holds camera and layout.

## 21. The Hub reads the chat message's words: `script_say`
A chat model calling the script tools can fail in four ways the tools cannot see: the wrong tool for a change
(`shot_add` for a request to change a shot's framing), the request paraphrased, a number misread, and a report of a
change not made. The project already solved this
once: `Clip:` hands the chat message's words to the Hub unchanged (`direct_clip {request: "<the chat message's words, exactly as written>"}`)
and the Hub plans with its own schema-held ask. The Script chat does the same:
1. After `script_start`, every message in a Script chat is one call: `script_say {words: "<the chat message's words,
   exactly as written>"}`, and nothing else; the chat model replies with the Hub's answer line, never its own summary.
2. The Hub asks its model (Settings → Assistant, the context's path, `assistant.chat.ask(messages, schema)`) with the
   script's numbered listing (`nth · speaker · first words`, shots by number with their framing) and a schema of
   **operations**: `add_lines`, `change_line {ref, words}`, `remove {ref}`, `move {ref, at}`, `change_shot {ref:
   {shot: n}, framing, on, move}`, `add_shot`, `set_length {seconds}`, `beat_add` (Step 11b), each with the listing's
   references; the backend holds the schema.
3. Checks in code before anything is applied, refused back to the ask with the line (as the context's three asks):
   - words quoted or given after "to:" in the chat message appear **verbatim** in the operation (a paraphrase is refused);
   - a number written in the chat message (30 seconds, shot 2, the second line) appears unchanged in the operation;
   - "change", "make", "turn" never resolve to an add (an add needs "add", "more", "another", or narration);
   - the operations then run through the ordinary tools and their refusals.
4. The answer line is the Hub's, built from what was applied ("changed shot 2 (s2): close-up on Character 2"), and the chat
   model is told to show it as written: no report the Hub did not make.
5. The direct tools stay for the model's own drafting turn and for a model configured to drive them; the
   block's Scripts paragraph shrinks to the one-call rule.
Not known: whether the configured model holds the operation schema on the first ask (the planner harness's readout; three asks
as the context).
