# R48 — How the Director's script and its audio are built: what was proven, what is wrong, with citations

Status: live. Source: an
engineer session's five build-and-prove tests (2026-10-18; sandbox with no GPU and no weights), every engine claim
checked here against upstream WanGP `af2ed29` (`/tmp/upstream`). Labels: PROVEN (the engineer ran it; checked here),
ENGINE (read in upstream source), DO NOT (an error the engineer made; corrected here), OPEN (needs the weights).
Specs written from PLAN.md cite this note by section; a build session reads the section its spec names.

## 1. The script format (the timeline)
- One script = scenes → shots → events. Event kinds: `line` (speaker, words, language, emotion, pace), `cue`
  (kind: effect | music | reaction; words describing the sound), `pose` (character, pose). Every event has
  `start_ms` and `end_ms`; a cue or pose may also anchor to a line (starts at its start or end).
- Prior art for the shape: OpenClap segments (`startTimeInMs`, `endTimeInMs`, `track`, `category`, `entityId`,
  `sceneId`, `prompt`; github.com/jbilcke-hf/openclap-format `DRAFT.md` §3.5.1); HocusPocus's storyboard panel record
  (role, framing, characters, dialogue, SFX, duration, camera, `videoAction`); R21 §2 ShotPlan.
- Characters are referenced by their Characters-folder name; every character keeps a fixed left-to-right place for
  the whole scene ("one world, many views"), so position cannot disagree across a cut. PROVEN (engineer test 3).

## 2. The Director writing it live over MCP
- PROVEN (engineer test 2: a real MCP client drove a 30 s, two-character session with three planted mistakes): the
  script is written one event per tool call; each call is checked on arrival; a refused call leaves the script
  untouched and answers `{problem, fix}` with structured hints (`suggested_end_ms`, `valid_speakers`), so a slip is
  one corrected call. Tools that worked: open a scene/segment, add line, add cue, add pose, move event, remove event,
  read the script, close. The check that catches most: a line too long for its window, by word count against the
  speaking rate (`pace`).
- Also refuse on arrival: a speaker not in the cast; an event past its scene's end; two lines overlapping (one speaker
  at a time, E6); a pose change on a character during the character's own line (ENGINE: face pose competes with speech,
  `minimax_h3_handler.py:230`, `:239`).
- The Hub already has an MCP server Open WebUI uses (`hub/core/mcp.py`, tools only); the script tools are added
  there. DO NOT use stdio (Open WebUI's native MCP is Streamable HTTP).
- The Hub's planner today checks a whole plan at the end and refuses up to three times; event-at-a-
  time is the lesson that replaces that for scripts. Nothing is refused for its words.
- OPEN: whether the configured model corrects itself from a `{problem, fix}` reply (the engineer's session was scripted).

## 3. Timing
- A line's length = its words at the pace setting (`hub/modules/generate_image/pace.py`; the engine's own 2.6 words/s
  when unset) plus the turn pause (ENGINE: `H3_DIALOGUE_PAUSE_SECONDS = 0.18`, `models/minimax_h3/dialogue.py:22`).
- Moving or lengthening an event pushes every later event on its row back by the overrun; nothing overlaps on a row.
  PROVEN in engineer test 4 (a line forced 1.8x long pushed all later events back by exactly the overrun).
- Estimates are replaced by measured times after the audio renders (§6).

## 4. Pose keyframes (stick figures)
- ENGINE: the pose drawing is the engine's own: `draw_pose` (`preprocessing/dwpose/pose.py:29`), `draw_bodypose`,
  `draw_handpose`, `draw_facepose` (`preprocessing/dwpose/util.py:71`, `:115`, `:143`). Body 18 points; hands always
  drawn (`pose.py:297`, `:519`); face 68 landmarks (`pose.py:375-377`). Strokes are fixed pixels: limbs 4 px
  (`util.py:76`), joints 4 px (`:110`), so draw at the final size, never scale a drawing.
- PROVEN (engineer test 1): seven named poses on the 18-point body (stand, sit, walk_step, turn, point, arms_raised,
  hand_to_face); eased interpolation between keyframes at the clip's fps; the mouth moves only inside its
  character's lines; figures kept apart (minimum gap measured).
- DO NOT: drop the hands; draw a 4-dot mouth (not what the ControlNet was trained on); draw labels, text or boxes on
  any frame that will be sent to the engine (HocusPocus's rule: lettering never in a conditioning frame).
- For the script screen, poses are drawn in the browser only; no render.

## 5. The MiniMax audio script
- ENGINE: the audio model's speech format is one turn per `Speaker N:` block, with language, emotion, pace and acting
  directions in square brackets, not spoken: `Speaker 1:` / `[English, warm and quiet] You found the right place.`
  (`models/minimax_h3/prompt_enhancer.py:123-125`, `H3_AUDIO_DEEPY_PROMPT_INFOS`).
- ENGINE: voice samples map to speakers 1 to 3; each at least 2 s; above 15 s combined, split evenly
  (`minimax_h3_handler.py:417`). The voice-clone model is `minimax_h3_tts_ref2va_pruned` (`defaults/`).
- ENGINE: `duration_seconds` CAPS the audio (`minimax_h3_handler.py:417`). DO NOT set it to the line's planned
  window: a long line is cut off. Set it above the expected length and measure.
- A non-speech cue is not a `Speaker` block; it goes to a sound model (§6).

## 6. Rendering the audio track
- ENGINE + PROVEN (engineer test 4, 40 s, three characters, on placeholder voices): one generation per event, not
  one combined script. The engine's dialogue mode splits into turns itself (`dialogue.py:41`) and paces them with a
  fixed 0.18 s pause that cannot follow an authored timeline, and has no syntax for cues or music.
- Order: generate each line (its own `Speaker 1:` block, the speaker's sample as `audio_guide`); measure each clip;
  push later events back by any overrun; then place everything at its time.
- Cues go to the dedicated models the engine ships, not to H3 (DO NOT route foley or music through H3):
  `stable_audio3_small_sfx` (impacts, whooshes, ambience, transitions, foley), `stable_audio3_small` (music),
  `minimax_music3` (songs), ACE-Step (`defaults/`). OPEN: which of these weights the model folders hold; a cue whose model is absent
  is refused in one line at render, never silently dropped.
- Mix with the engine's own mixer: `replace_audio` (`shared/deepy/engine.py:4982`) → `remux_media`
  (`shared/deepy/video_tools.py:540`): clips at offsets, per-clip gain and fades, one loudness pass, a true-peak
  limiter, ducking driven by detected speech (`:680-700`). The Hub's own join already places track-2 items with
  fades and ducking; the spec decides which of the two mixes, with its reason.
- Each line is judged by the Hub's words judge and taken again under the bar.

## 7. For the picture component (not in PLAN.md's steps; recorded so nothing is re-derived)
- Control path: MiniMax H3 ControlNet-Union, control window 362 frames (`minimax_h3_handler.py:546`; 481 is the
  non-control maximum, `:719`, `:796`); legal lengths: at least 107, then steps of 17 from offset 5 (`:581-583`); the
  engine trims other lengths DOWN (`shared/utils/frame_scheduler.py:23`), so pad UP; reference videos 17n+5
  (`models/minimax_h3/pipeline.py:632-633`); window overlap 18 (`:1258`, `constants.py:8`); each window gets its own
  control slice (`:655`); output takes the control video's aspect ratio (`:239`), so every shot is drawn on one canvas
  size; `[Shot N] At MM:SS.mmm` valid on the control path (`:542`); window commands `[/duration]`, `[/overlap]`,
  `[/new_shot]` (`frame_scheduler.py:100-130`; `/new_shot` only on T-capable models, `:128`, `wgp.py:2964`).
- Guide letter `V` ("Use Control Video as is", `:549-550`). DO NOT use `PV`: `P` runs the person detector on video
  that is already stick figures (`wgp.py:4893`, `preprocessing/processors.py:31`).
- Kept soundtrack: audio `A` keeps `audio_guide` as the soundtrack; the prompt asks for "speaking with natural lip
  movements synchronized" and never names the track (`:230`); speech across a window join is re-made by
  `audio_overlap_repair_seconds` (`shared/utils/audio_video.py:108-114`).
- Storyboard (engineer test 5): entry panel per shot, exit panel only when a pose category changes; continuity from
  what was rendered, not what was authored; animatic from panels before any render; anchors (`image_start`,
  `image_end`) must match the control video (`:239`) and the control model was trained without anchors (`:224`);
  a stick-figure anchor is for previz only.
- OPEN (the weights): the ControlNet module is not on the server's disk; whether H3 renders stick figures; mouths in sync
  while a pose holds; `[/new_shot]` on the control path.

## 8. The scene context and the sketch storyboard (the design)
The design: each character's costume and elements are set from the start; a sketch storyboard is the key, a
low-resolution pencil sketch per shot, each finished and checked before the next step; keyframes are markers, with
tweened animation between them; the Director keeps the timestamps of camera changes, audio cues and everything that
serves the renders; no pre-rendered frame-to-video segments; and, once the audio file is made, a quality check against
the Director's notes and the sketches' layout. The
reason for it: with each shot its own render from one reference picture, nothing carries a set or a costume from one
shot to the next.
- **The context, before any line.** Each cast member's look and costume, written once and locked (what to keep, what to
  ignore; HocusPocus: `SeriesCharacter` with `appearance`, `identityLock`, `wardrobeVariants`,
  `ui/src/features/series/types.ts:65-85`; its character-sheet rule "Name clothing, materials, colors, body, face and
  props … Always say what to ignore (background, floor, lighting, other people …)",
  `app/services/character_sheet.py:44-50`). The set: its description, its elements and props, and each character's
  home position (HocusPocus `SeriesLocation.layout2d.homes`, x in %, and a background plate, `types.ts:87-97`;
  `SeriesProp`, `:100-110`). Nothing appears in a shot that is not in the set or the cast's costume unless an event
  adds it; a costume changes only by an event.
- **Keyframes, tweened.** Poses are keyframes at line starts and ends, at cuts, and wherever the narration moves
  someone; everything between is eased interpolation (§4), not authored per frame.
- **Sketch panels, as the Director writes.** A low-resolution pencil-sketch panel for each keyframe that changes the
  picture: each shot's start, and each pose-category change inside a shot (engineer test 5's entry/exit rule, §7).
  Drawn from the context (set, places, costumes), the shot's camera and the poses at that time. Queued as the script is
  written, one after another, each finished before the next (the previous nail, §8); never video. A sketch is a record of
  the intended frame for the later checks and renders, not a conditioning frame (no labels in anything sent to the
  engine, §4).
- **Checks against the record.** After the audio renders, its measured events are compared with the script's (each
  line heard, each cue present, at its time), and later the picture with the sketches.
