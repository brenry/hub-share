# R8 — A storyboard for short films: what HocusPocus does, and a minimal Hub module

Status: research, 2026-10-14. No code changed. Sources: the HocusPocus fork (`hp:` = a HocusPocus source copy)
and the Hub. Every design choice in §3–§5 is *Proposed*. No model is named; "the start-frame model"
and "the identity model" are the two clip roles the Hub already knows (`hub/modules/generate_image/build.py:121-130`).

## 1. What HocusPocus's Comic Book and Director do today

**Two front doors, one plan.** The Comic editor has a mode switch, comic or storyboard (`hp:ui/src/features/comics/
ComicEditorPanel.tsx:1517-1545`), and the Director chat embeds the same panel (`hp:ui/src/components/Sidebar/
DirectorChat.tsx:18-19`). In storyboard mode a "page" is one shot with one panel (`hp:app/_launch_runtime.py:32196-32205`).

**Data shapes.**
- The project is one browser-built JSON, `ComicProject` (`hp:ui/src/features/comics/types.ts:131-178`): pages of
  positioned elements (panel, image, text, `:47-124`), assets by id, characters with reference asset ids (`:27-41`), and
  a `director` block holding the request, the plan, completed panel ids and the image jobs per panel (`:155-177`).
- A planned shot is `ComicPlanPanel` (`types.ts:201-246`): `imagePrompt` (the frozen first frame), `characters` (ids in
  visual priority), `framing`, `continuityNotes`, `videoPrompt` (motion after the first frame), `videoAction`,
  `durationSeconds`, `cameraMove` (none, push-in, pull-out, pan-left, pan-right), `videoEndFrame` (auto, none,
  next-panel), seed, renderer and fit, plus `videoOverrideFields`, the list of locked fields (`:183-197`).
- The request, `ComicDirectorRequest` (`types.ts:316-360`), carries the premise, `productionMode`, the storyboard
  aspect and quality, the shot count (`pageCount`), style, world context, forbidden elements and the characters.
- The film-shot contract sent to the backend is documented with an example (`hp:docs/COMIC_VIDEO_ADAPTATION.md:36-56`):
  `shot_id`, `source_panel_ids`, `action`, `camera`, `motion_level`, `duration_seconds`, `fit_mode`, `seed`, `end_beat`.
- Behind it, the Director's generic `ShotPlan` (`hp:app/services/director/schema.py:262-305`) has `duration_sec`,
  `camera_plan` (`:191-197`), `image_strategy` (reference_edit, reference_inspired, fresh_generation, none, `:258`),
  `continuity_strategy`, `video_prompt` and `image_prompt`.

**The flow.**
1. Plan. `POST /api/v1/director/comic/plan/start` runs a background LLM job (`hp:app/_launch_runtime.py:33225-33280`).
   In storyboard mode the rules ask for exactly one clean first frame per shot at a fixed canvas (832x448 or 1280x704,
   portrait swapped, `:32206-32240`), an `imagePrompt` that freezes the instant before the action, a `videoPrompt` of
   one continuous chronological shot under 180 words, 2–10 seconds, a camera move from the five, and no lettering
   (`:32411-32434`).
2. Place. The browser turns the plan into pages, one panel per page, with the video canvas as the page size
   (`ComicEditorPanel.tsx:1195-1290`, canvas at `:1249-1256`). Generated hints are not locks (`:1202-1206`).
3. Draw. The browser builds each panel's image prompt with style, world and character identity locks and the shot's
   continuity notes (`hp:ui/src/features/comics/generateArtwork.ts:69-93`; storyboard frame lock `:79-82`), picks one
   reference picture, that of the first listed character who has one (`:7-25`), and submits the image job itself,
   remembering the job id per panel so a dropped request resumes (`:300-360`, `:130-139`).
4. Film. The browser captures every panel from the canvas without lettering, uploads each as a PNG and assembles the
   shot list (`hp:ui/src/features/comics/ComicWorkflowPanels.tsx:1178-1300`; lettering off at `:1299`; seed from the
   panel id hash at `:1270-1274`). It starts the `comic_movie` pipeline with `provided_clip_image_paths`, one start
   picture per shot, and `comic_adapt_to_film: false` for a storyboard, so shots stay one to one (`:1369-1383`;
   `hp:docs/COMIC_VIDEO_ADAPTATION.md:32-34`). The planner can split a long shot and repeats its picture
   (`hp:app/services/director_comic_film.py:76-101`). The backend fits each picture to the clip canvas and keeps durable
   copies (`hp:app/services/director_pipeline.py:8151-8185`), then renders image-to-video per shot and joins with hard
   cuts (`COMIC_VIDEO_ADAPTATION.md:23-27`).
5. A separate animatic route makes a slideshow video of the lettered panels with ffmpeg (`hp:app/routers/comics.py:
   721-811`).

**UI-only versus engine.**

| Lives in the browser only | Lives in the backend |
|---|---|
| The project, pages, elements, assets and locks (`types.ts`) | Saving the JSON as `<time>_<title>.comic.json` plus a preview PNG (`comics.py:440-450,559-584`) |
| Placement of the plan on pages, canvas size per mode (`ComicEditorPanel.tsx:1195-1290`) | Writing the plan with an LLM, storyboard rules included (`_launch_runtime.py:32190-32480`) |
| Image prompt assembly, the choice of reference, submitting each image job (`generateArtwork.ts`) | The image jobs themselves |
| Capturing panels as pictures, building `comic_shots` (`ComicWorkflowPanels.tsx:1178-1300`) | The `comic_movie` pipeline: fit, render, check, join (`director_pipeline.py:7580-7584,8151-8185`) |
| Override bookkeeping (`types.ts:183-197`) | Planners and the shot schema (`director/planners/comic_movie.py:591`, `director/schema.py`) |

**What the Hub should take and leave.** Take the cell contract (first frame + motion text + seconds + camera + cast)
and the one-to-one rule for storyboards. Leave the canvas editor, the LLM planner (the assistant writes the
text), fusion and splitting, the fit modes, the deterministic renderers and the joining step. The main lesson: in
HocusPocus the shot list exists only in the browser, and pictures reach video only by a browser capture and upload.
In the Hub the record must be files on the server, so the assistant can read and drive it through tools.

## 2. A storyboard as cell guidance, in Hub terms

A cell is: a picture, the clip text (the draft the clip is rendered from), seconds, a camera note, and a cast (character
names). The cells play in order; one cell makes one clip; the clips seen in order are the film.

What the cell picture does depends on the clip model's role, which the Hub already reads from the catalog
(`hub/modules/generate_image/models.py:77-82`, used at `build.py:121-130`):
- On the start-frame model, the cell picture is box 1: the clip opens on it (`build.py:21-24,127-128`).
- On the identity model, the cast's character pictures are the identities, boxes 1 to N (`build.py:129-130`); the cell
  picture is then only the sketch of the shot, not sent.

Continuity from cell to cell, from strongest to weakest, and what the Hub can do today:

| Continuity | How | Today |
|---|---|---|
| Same people | Every cell picture is drawn with the cast's character pictures as references, and every clip text restates who is there and what they wear | Yes: Generate Image takes character references by name (`hub/modules/generate_image/cast.py:40-63`) |
| Same place and light | Each clip text is self-contained and restates place and light, as the HocusPocus planner requires (`hp:app/services/director/planners/short_film.py:5622-5628`) | Yes, by the system prompt (§4) |
| Cut on the next picture | Clip N ends on cell N+1's picture (HocusPocus `videoEndFrame: next-panel`, `types.ts:239`) | No: the engine takes an end frame but the Hub sends none |
| Continue the shot | Clip N+1 starts from clip N's last frame (`continuity_strategy: extend_previous`, `short_film.py:5627`) | No: needs a frame read from a clip, and the controller has no ffmpeg (`docs/architecture/parts/08-video-blueprint.md:404-413`) |

The workflow, step by step:
1. A chat message gives the assistant a synopsis. It calls `list_characters`, then makes a storyboard and writes cells one by one:
   each cell's picture drawn (or taken from a Character or from the newest picture), its clip text, seconds, camera.
2. Media shows the cells, in the Drive folder of that storyboard: pictures in order, text with each.
3. A chat message asks to fix cell 3 or to swap cells 4 and 5; the assistant rewrites or moves that cell.
4. A chat message asks to render all cells or cells 2 and 5; one clip per cell is queued on the existing clip path.
5. The clips appear on `/clips` in a group named after the storyboard, in cell order, and play one after another.

## 3. A minimal, modular design

### 3.1 The record: a folder of numbered pictures, not a JSON file

A storyboard is a Drive folder, `<storyboards folder>/<name>/`, whose pictures are its cells in name order (`01.png`,
`02.png`…). Each cell's text is held in the one PNG text field the Hub already writes for Characters
(`hub/core/characters.py:9-13,30-32,150-171`). The field holds a few header lines, a blank line, then the clip text:

```
seconds: 5
camera: slow push-in
cast: <name>, <name>
                                 (blank line)
<the clip text, exactly as it will be rendered>
```

Why the folder wins over one JSON file:
- The file is the record (`characters.py:7`); a JSON would be a second record about pictures, which the Hub refuses
  everywhere else (`hub/modules/media/library.py:6`). Ids inside a JSON go stale the moment a picture is moved or renamed
  in Media; a folder cannot point at the wrong picture.
- It is on screen today: Media already lists a Drive folder's pictures sorted by name (`hub/core/drive.py:75-90`).
  A JSON file would be invisible there and would need a new editor.
- Deleting, copying or renaming a cell is a plain file operation; nothing else needs to agree.
- Against it: every cell needs a picture (a text-only cell cannot exist), and it widens the one exception to "a
  picture is its pixels" (`docs/architecture/00-overview.md:65-67`) from the Characters folder to the storyboards
  folder. Both are acceptable: a storyboard cell *is* a picture, and the text is the typed text, not
  provenance. The widening is a decision of the chat and must be recorded with an enforcing test (§5, S1).

Limits stay settings (`00-overview.md:76-77`): `cell_text_max` (default 4000, the clip prompt cap at
`hub/modules/generate_image/screen.py:28`) and `max_cells` (default 24).

### 3.2 The module: `hub/modules/storyboard/`, declarations only

No tab and no routes in the first stages. The core generates every tool from the declarations
(`hub/core/api.py:88-112`, `hub/core/features.py:93-98`); nothing new is wired.

| Declaration | MCP tool | What it does |
|---|---|---|
| `Screen` settings | `get_storyboard_settings`, `set_storyboard_settings` | `storyboard` (the open one, a name checked against the folder), `model` (clip model id), `picture_model` (image model id), `aspect`, `megapixels` (tier, as Generate Image maps it), `steps`, `seed` ("random" or a number; cell k uses seed + k − 1) |
| `Listing("storyboards")` | `list_storyboards` | Storyboards by name, with the number of cells |
| `Listing("storyboard_cells", {storyboard})` | `list_storyboard_cells` | Each cell: number, seconds, camera, cast, text, and its newest clip on `/clips` if any |
| `Action("put_cell")` | `put_cell` | Make or replace cell N of a storyboard: picture from a character name or "newest" (the newest Temp picture), and/or new text; a new storyboard is made by its first cell |
| `Action("draw_cell")` | `draw_cell` | Queue one picture with the picture model, the given picture prompt and the cast as references; when it lands it becomes cell N (its text kept) |
| `Action("move_cell")` | `move_cell` | Move cell N to position M; the files are renumbered |
| `Action("render_storyboard")` | `render_storyboard` | Queue one clip per cell, all cells or the listed ones, in order |

Descriptions are factual labels, ≤200 characters, with no "always/never" (`00-overview.md:72-73`). Tool names are
unique across modules (`hub/core/registry.py:115-116`); `list_characters` stays Generate Image's (`tools.py:87-93`).

### 3.3 Rendering through the existing clip path

The module never builds an engine task. `ctx.jobs.submit` already accepts another module's kind by its dotted name
(`hub/core/context.py:71-78`; kinds registered as `<module>.<kind>` at `hub/core/runtime.py:123-124`). So
`render_storyboard` submits `generate-image.image` with the same params a Generate press sends
(`hub/modules/generate_image/tools.py:52-80`): `model`, `mode: "refs"`, `references` (the cell picture's Drive id on
the start-frame model; the cast's `chars/` ids on the identity model), `prompt` (the cell's clip text), `width` and
`height` (the tier size), `frames` (seconds snapped to the model's lattice), `steps`, `seed`, `loras: []`. The clip job
builder checks every value and refuses in one line (`build.py:133-173`), so the storyboard repeats no check.

- One queue, one lane, the same hold texts and job line; the job's `tool` is `generate-image` (`hub/core/jobs.py:86`),
  so the Generate window shows storyboard clips like its own.
- A drip, not a flood: the module submits the next cell only when the previous job finishes, listening to
  `job.finished`, which carries the outputs (`jobs.py:160-168`). This keeps the shared queue's `max_waiting`
  (`jobs.py:84-85`) free for the pictures. The job-to-cell map is memory only and goes with the session.
- On `job.finished` the module files the clip under `clips/<day>/<storyboard>/<NN>.mp4` (a redo becomes `NN-2.mp4`).
- If Generate Image is disabled, the submit fails with "Unknown job kind" (`jobs.py:71-73`) and the action says so.

### 3.4 The `/clips` page as a sequence

Clips may already sit in a group under their day (`hub/core/files.py:199-222`). Two small web changes: in clips mode a
group is sorted by name (cell order) instead of newest first (`hub/modules/media/library.py:104`), and the clip Stage
gets "play in order", which starts the next clip of the group when one ends. No joined file: joining needs ffmpeg in
the controller, which the blueprint rules out (`08-video-blueprint.md:404-413`).

### 3.5 What stays out

An LLM planner in the Hub (the Hub adds no instructions, `00-overview.md:72-73`), fusion or splitting of cells, fit
modes, deterministic renderers, the end frame and last-frame continuation (later, §5 S5), a storyboard tab, and any
record kept about a clip.

## 4. The Open WebUI paragraph (to paste after the clip paragraph)

```text
STORYBOARDS. A storyboard is a numbered list of cells in a Drive folder; each cell is one picture and the text of one
clip. When the chat message gives a synopsis and asks for a storyboard, a short film or a shot list: call
list_characters, then plan 4 to 12 cells and reply with the plan in one line per cell (what is seen, seconds, camera).
Write nothing until a chat message agrees. Then, for each cell in order: draw_cell with a picture prompt that freezes the first instant of the shot,
before anything moves, naming the cast from list_characters; then put_cell with the cell's text. The text starts
with three lines, "seconds: N", "camera: <a few words>", "cast: <names>", then a blank line, then the clip draft in
the shape the clip paragraph gives for the clip model set in get_storyboard_settings. Each clip draft stands alone:
restate the place, the light, every person and what they wear; describe only what moves after the first frame;
fit the action to the seconds; one continuous shot, no cuts. Use the same wording for a person in every cell.
"Use <character> as cell N" -> put_cell with that name. "Use the newest picture" -> put_cell with "newest".
"Change cell N" -> list_storyboard_cells, then put_cell with the new text only. "Swap N and M" or "move N to M" ->
move_cell. "Render it" -> render_storyboard; "render cell N" -> render_storyboard with that cell only. Say it is
queued and that the clips appear on the Clips page in the storyboard's group, in order. Never render unless a chat
message asks for it.
```

What each line rests on: the cell text format (§3.1), the clip draft shapes already in
`docs/video-plan/system-prompt-video-paragraph.md`, self-contained prompts (`short_film.py:5622-5628`), and the frozen
first instant (`hp:app/_launch_runtime.py:32413-32417`).

## 5. Staged plan

### Core lifts (each moves code; the old owner switches in the same commit, so nothing is copied)

| Lift | From | To | Who uses it |
|---|---|---|---|
| L1 PNG text field: read and write the one `Description` field pixel for pixel | `hub/core/characters.py:138-171` | `hub/core/pngtext.py`; `Files.picture_text(id)` and `Files.picture_text_set(id, text)` in `api.Files`, allowed only in `chars/` and the storyboards folder | Characters, Storyboard |
| L2 Put a picture into a Drive folder under a name, metadata cut, replacing | `characters.put` (`characters.py:69-94`) | `hub/core/drive.py` `put_named`; `Files.drive_put(folder, name, id)` | Characters (its folder), Storyboard |
| L3 Clip facts from the catalog: role, tier size, frames on the lattice, seconds | `generate_image/models.py:77-130`, `screen.py:66-82` | `hub/core/clipfacts.py`, reached as `ctx.engine.clip(model_id)` returning `{role, fps, frames, tiers, ref_cap}` and `size(aspect, megapixels)`, `frames(seconds)` | Generate Image, Storyboard |
| L4 Plain-value checks (whole number, number, seed) | `generate_image/build.py:27-45`, `screen.py:132-146` | pure functions in `hub/core/api.py`, as blueprint §3.7 proposes (`08-video-blueprint.md:537`) | both |
| L5 File a clip under a group with a name | `Files.regroup` keeps the time name (`files.py:199-222`) | `regroup(ids, group, stem=None)` | Storyboard; Media unchanged |
| L6 The newest Temp picture | Media's own listing (`library.py:104`) | `Files.newest("out")` | Storyboard |
| Fix | `clip_job` writes Generate's `last_seeds` (`build.py:172`) | write it in the press (`tools.py:52-80`) only | so a storyboard render does not change the Generate screen's seed line |

Not lifted: the job builder itself (used through the dotted kind), the box policy and the screen bounds (each
module's own policy, `08-video-blueprint.md:542-543`).

### Stages

**S0 — owner decisions (no code).** Approve widening the PNG text exception to the storyboards folder; the folder
setting's default; the drip; "play in order" without a joined file. Done when recorded in part 7's decisions.

**S1 — lifts L1, L2, L4, L6 (no new tool).** Characters move onto `pngtext` and `drive_put`. Done when every existing
test passes unchanged and new tests pin: text kept pixel for pixel; a text field written outside `chars/` and the
storyboards folder is refused; `clean.strip` still cuts the field from a Temp copy; `newest("out")` with an empty Temp.
Extend `tests/core/test_rules.py` with a check that no module calls PIL's PNG text writer.

**S2 — the module skeleton: settings, listings, `put_cell`, `move_cell`.** Done when the six new tools appear in Open
WebUI with no wiring change; tests: a cell made from a character name, from "newest", text over `cell_text_max`
refused in one line, `max_cells` refused, header lines parsed and an unknown header refused, numbering after a move,
a picture dropped into the folder by hand listed as a cell, a storyboard name that leaves the Drive refused.

**S3 — lifts L3, L5, the fix; `render_storyboard`.** Generate Image moves onto `ctx.engine.clip`. Done when a
three-cell storyboard renders three clips one after another on the start-frame model and they land as
`clips/<day>/<name>/01.mp4…03.mp4`. Tests with the fake engine: the submitted params pass `build.image_job`
unchanged; seconds snap to the lattice; the identity model sends the cast, not the cell picture; one waiting job at a
time; a failed cell stops the drip and says which cell; Generate's `last_seeds` untouched.

**S4 — `draw_cell` and the `/clips` sequence.** Done when one
conversation goes from a synopsis to a played sequence. Tests: the drawn picture becomes cell N with its text kept; a group sorted by name in clips mode; "play
in order" advances on `ended` (browser test); the 250-line web limit holds.

**S5 — later, each with a one-page note first.** The end frame (cell N+1's picture as clip N's last frame; the engine
takes one, `docs/architecture/parts/05-engine-lineage.md:564`), a joined file, last-frame continuation, a storyboard
tab with a cell strip.

## Gaps / unverified

- That `ctx.engine.query("models")` returns the video facts in the shape L3 needs was read from code, not run.
- Whether the Media Drive view shows a cell's text is not checked; S2 may need a read-only text line under the Stage.
- Clips rendered across midnight would split one storyboard over two day folders; filing by the render's start day
  needs L5 to take the day too.
- The per-cell seed (seed + k − 1) mirrors Generate's count rule (`build.py:39-45`), not HocusPocus's shot-id hash.
