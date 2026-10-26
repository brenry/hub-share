# Hub

**A film studio in a box, on your own hardware.** Narrate a story to an assistant; the Hub turns it into a script, a
storyboard, a sound track and rendered clips, on a local video engine, with every creative decision left to the
person at the keyboard. No Guard Rails. Nothing leaves the network. Nothing is logged.

> Private, in active development. Shared for review and public research, not published.

## The engine

The Hub drives one engine: upstream [WanGP](https://github.com/deepbeepmeep/Wan2GP), pinned at commit `af2ed29`
(v18.05) and installed as the Hub's own copy. The engine's facts (model keys, frame counts, reference slots, prompt
syntax) live in one place, `hub/worker/adapters/upstream.facts.json`, read against a contract test. Change the engine,
change one file.

Also totally sweet. Your LLM can take ComfyUI's Desktop App opensource on github (which is windows only but easily ported for linux use its nothing but a Chromium Electron). Docs in this project explain pipelining for Multi-Monitor usage. You can use 2-3 monitors if you want. Media on one monitor, video time line editor on another, and Image Creation on a 3rd. Its all very open ended on what you want to do. Contextual Right Click can send media from one monitor into project on another. You define the instances.

Build instructions for a client: `docs/architecture/desktop-client.md`.

What the engine family offers, and what the Hub already uses:

| Model path | What it does | In the Hub |
|---|---|---|
| **MiniMax H3** text-to-video | A clip from a six-field prompt (`subject_definitions`, `summary`, `retention_analysis`, `detailed_description`, `overall_soundscape`, `non_diegetic_music`), with speech and sound generated in the same pass | Every shot; pasted community prompts are imported one shot per time range |
| **H3 Ref2VA** (reference-to-video-and-audio) | Up to 9 pictures as `<Picture N>`, 3 videos, 3 sounds; characters and places held by reference, no training | Character sheets, costumes, sets, voiced clips in one render, continuing clips |
| **H3 FL2VA** (first-and-last frame) | A clip bridged between two frames | The base of the control path (below) |
| **H3 TTS Ref2VA** | A spoken line in a referenced voice | Dialogue takes, measured and re-taken under a quality bar |
| **H3 Control** (ControlNet-Union) | A clip that follows a control video: pose, layout, camera | **In progress**: the previz path |
| **Image models and LoRAs** | Any image model in the model folders; image and video LoRAs picked by name | Generate, sketches, Casting views |

The worker that talks to the engine is standard-library Python, runs in its own scope (a memory kill takes the engine,
never the Hub), and is watched by a VRAM manager that queues jobs rather than crashing them.

## The pipeline

```
narration ──▶ script ──▶ sketches ──▶ sound track ──▶ clips ──▶ cut
 (chat)      (JSON)     (pencil     (every line      (one per   (joined,
                         panels)    and cue, mixed)   shot)      editable)
```

- **Storyboard.** The Director (any assistant model through Open WebUI, over the Hub's MCP tool server) writes the
  script as the story is told: scenes, shots, lines with speaker and delivery, sound cues, poses, each timed in
  milliseconds. The screen shows the timeline, the shot list, the clips, and the **context cards**: style, set, and one
  card per cast member (look, costume, what to ignore, where they stand). Every field is typed by hand; an empty
  field sends nothing.
- **Sketches.** A pencil panel for every shot and pose change, drawn by the picture model from the context cards
  alone, redrawn when the shot changes.
- **Track and Mix.** Every line rendered as its own take on the speech model, judged for words (Whisper), measured,
  levelled to -23 LUFS, re-taken under the bar; cues and room tone rendered on the sound model; all of it mixed by one
  map onto lanes, with the audience, effects and music 10 dB under speech and the room never ducked.
- **Clips.** Each shot rendered on a Ref2VA model with its cast's pictures (or the shot's own pictures) and its slice of
  the track; a render of one shot rejoins the full video. Face, mouth and frame judges score every take.
- **Casting.** A character sheet from reference pictures: one orbit on a video model, six still views, costumes as
  separate pieces, an audience member with a side and a row. No trait is assumed.
- **Stage.** A set from one picture of a location: a pan render and five plates (wide, left, centre, right, audience).
- **Edit Video.** Tracks, trims, splits, export to MP4 or WAV.

## The control path (what is being built next)

The design in `docs/video-plan/BLUEPRINT-director.md`, Stage B:

1. The locked script and its track become a **stick-figure animatic**: a control video at the clip model's size and
   fps, every character at its place and pose, every cut where the script cuts.
2. The animatic drives **H3 Control** (ControlNet-Union on the FL2VA base): a previz render that holds camera,
   layout and timing before any costly render.
3. The previz is checked against the sketches shot by shot by the pose judge; mismatches are listed, not hidden.
4. The previz window then serves as the **reference video** for the final Ref2VA render, so sketch, previz and render
   are three drawings of one shot.

Status: the engine facts for the control models are filed (`minimax_h3_control`, `minimax_h3_control_pruned`), the
research is done (R48 §7, R52), the adapter is specified; the build is gated on the ControlNet module being present in
the model folders, and the Hub refuses in one line naming the missing file rather than guessing.

## The library: how the craft gets into the code

`docs/library/` holds the reference books the project reasons from. They are not decoration: every design decision
about cutting, staging, dialogue, sound or studio practice is made by a **Research session** that reads the relevant
chapter and files a note under `docs/video-plan/research/` (`R1` to `R49` so far), **cited by page**, stating facts and
taking no decision. The design cites the note; the code cites the design. Nothing in the pipeline is "how it seemed"; it is
traceable to a page.

| Book | What it feeds |
|---|---|
| Katz, *Film Directing Shot by Shot* (1991) | Storyboards; framing heights; the cut on the look; staging two, three, four or more players; pans, cranes, tracking |
| Murch, *In the Blink of an Eye* (2001) | Where and why to cut: the Rule of Six; cutting where a viewer would blink |
| McKee, *Dialogue* (2016) | Every line as an action on the other; beats of action and reaction; exposition carried in the lines |
| Holman, *Sound for Film and Television* (2010) | Intelligibility; dialogue overlaps; mixing conventions; the multi-camera dialogue edit |
| Zettl, *Television Production Handbook* (1976) | The multi-camera studio: switching as instantaneous editing; directing on the air; lighting; set design; talent |
| Grindstaff, *The Money Shot* (2002) | How a daytime studio interview program is built: segments, the audience's warm-up and reactions, the control room |

`docs/library/README.md` says what each book is good for and which pages; `WANTED.md` lists the one book that would
fill each remaining gap. A new book is filed as `Author-Year-Short-Title.pdf` with a line in the README, and from then
on research sessions can cite it.

## Rules the code is held to

- **Nothing between the prompt and the engine.** No hidden prompt text, no default traits, no invented lengths or counts,
  no random values, no refusal, no lock. What is typed is what is sent.
- **Model files stay where they are.** Models are read from the folders set in Settings; nothing is copied, moved,
  renamed or downloaded. No model or file name is hardcoded outside the facts file.
- **No logs, no data.** Nothing of a prompt, chat or job is written to disk; no metadata beside a picture; no sample
  data ships.
- **Nothing is "fixed" until it ran on the target machine.** Every build reports what ran where.

A vocabulary test (`tests/core/test_vocabulary.py`, scanner `tools/vocabulary.py`) refuses gendered pronouns, private
names, addresses and paths anywhere in the tree.

## Layout

```
hub/core/       jobs, bus, VRAM manager, routes, MCP tool server
hub/modules/    one package per screen: director, casting, stage, generate_image, media, sequence, …
hub/worker/     engine worker (stdlib only); adapters/ holds every engine key and the facts file
web/src/        React 19 + TypeScript client (Vite); one module per screen
install/        installer, engine installer (pins the engine commit), uninstaller
tools/          release packer, update script, vocabulary scanner, session setup
tests/          pytest: core, engine, worker, install; Vitest and Playwright under web/tests
docs/           architecture (how the code works), video-plan (design and 50 research notes), library
```

## Development

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --require-hashes -r requirements/controller.lock -r requirements/dev.lock
cd web && npm ci && cd ..

.venv/bin/ruff check hub tests tools
.venv/bin/python -m pytest                                  # ~8 min
cd web && npm run build && npx vitest run && npx playwright test
.venv/bin/python tools/release.py                           # dist/hub-release-<date-time>.zip
```

Python 3.13+, Node 22. A release installs on the server with `install/install-hub.sh` (`README-INSTALL.md`).

## Where to start

- **How the code works:** `docs/architecture/00-overview.md`, then the part for the component (core, Generate Image,
  Media, assistant and MCP, engine lineage, web build and release, video).
- **What was learned about the engine and the craft:** `docs/video-plan/research/` (R1 to R53), each note a set of facts
  cited to an engine source line or a book page. Start with R22 (the H3 prompt format), R48 (the Director's build
  knowledge) and R52 (references and control).
- **Where it is going:** `docs/video-plan/BLUEPRINT-director.md`, the design the research feeds.
- **How the assistant is instructed:** `docs/video-plan/system-prompt-video-paragraph.md`.

## License

Its for research. Do what you want. Have your LLM check Docs full of logs.
Works under `docs/library/` remain the
property of their authors and publishers and are held for private reference only.
