# R5 — Generate Video: the assistant (MCP) contract, the risks, the stages

Scope: how a new module **Generate Video** (MiniMax H3) appears to the assistant so that it behaves exactly as
Generate Image does today; what can go wrong, each with the code fact behind it; and the staged plan with the tests
that prove each stage. Read-only research: nothing in `hub/`, `web/` or `tests/` was changed.

Conventions: **Fact** cites a file and line in this tree, the engine (`hp:` = the `app/` folder
of a HocusPocus source copy) or the desktop client (`hpd:` = the `hp-desktop` source tree). **Proposed** is a
choice left open; nothing Proposed exists. **Measured** was run here, read-only.

Builds on `docs/architecture/parts/04-assistant-mcp.md` (§4.4–§4.5) and `parts/08-video-blueprint.md` (§3, §5–§8).
Where this note disagrees with the blueprint it says so and why.

---

## 1. The video tool set as the model sees it

### 1.1 The rules every tool must pass (Fact)

- Generated, never hand-written: a `Screen` gives `get_<id>_settings` / `set_<id>_settings`, a `Listing`
  `list_<name>`, an `Action` its own name (`hub/core/features.py:1-6,65-98`); `generate-video` →
  `get_generate_video_settings` (`features.py:66`). Descriptions: `Settings of the {title} screen: {names}.` and
  `Set settings of … Returns the settings after.`, names in declaration order (`features.py:77-79`).
- Registry (`hub/core/registry.py:114-119`): names snake_case and **unique across all modules**; descriptions
  non-empty, ≤200 characters, ending with a period. One duplicate fails the whole registry pass.
- Banned-word scan (`tests/engine/test_generate_image.py:205-208`): every tool and property description, any depth,
  lower-cased, must not contain the substrings `when`, `only`, `if `, `should`, `must`, `never`, `always` (so
  `whenever` and `commonly` fail too). Labels are "a short factual label … never an instruction"
  (`hub/core/api.py:73-79`); listing and action texts "one factual line, ending with a period" (`api.py:100,110`).
- The check treats `null` for a known optional key as left out and `15.0` as 15 (`hub/core/schema.py:38-39,63-64`). A `seed` is published as a string with `: random, or a whole number from lo to hi` appended
  (`features.py:54-57`); a `names` setting is an array of ≤`hi` strings of 1–120 characters (`features.py:51-53`).

### 1.2 The tools after Generate Video (Proposed; 10 in all)

Unchanged: `get_generate_image_settings`, `set_generate_image_settings`, `list_image_models`, `generate_image`
(Generate Image), `list_loras` (LoRAs), and `list_characters` — same name, text, schema and result, now declared by
**Media** (§1.7). New: `get_generate_video_settings`, `set_generate_video_settings`, `list_video_models`,
`generate_video`.

Order in `tools/list` follows module discovery order then each module's screen, listings, actions
(`features.py:93-98`, `hub/core/runtime.py:118-119`). The test that pins today's six names and order is
`tests/core/test_mcp.py::test_the_shipped_modules_publish_six_generated_tools_and_a_set_changes_the_screen`; it
becomes "ten" and lists the new order.

### 1.3 `set_generate_video_settings`: every setting and its label (Proposed)

Labels follow the Generate Image style (`hub/modules/generate_image/screen.py:31-44`): a noun phrase, no period, no
verb of command.

| Setting | Kind | Bounds / choices | Lives | Label text (verbatim) |
|---|---|---|---|---|
| `draft` | text | `hi` = `MAX_PROMPT` (6000, see §2.5) | session | "The assistant's draft prompt for the clip, shown beside the chat" |
| `model` | choice (live) | checked in `write` against `list_video_models` | disk | "Id of the video model, as list_video_models lists it" |
| `seconds` | number | `lo=1`, `hi=15`; `write` rounds **up** to the model's frame grid and refuses past its one-pass maximum | disk | "Length of the clip in seconds, rounded up to the model's frame grid" |
| `resolution` | choice (live) | the model's offered tiers (`480p`, `540p`, `720p` by default) | disk | "Resolution tier of the clip, as list_video_models lists it" |
| `aspect` | choice | `16:9`, `9:16`, `1:1`, `4:3`, `3:4`, `21:9` | disk | "Shape of the clip" |
| `steps` | integer | `lo=1`, `hi=100`; the model's own range checked in `write` | disk, per model | "Steps the model runs" |
| `seed` | seed | `lo=0`, `hi=999999999` | disk, per model | "Seed of the clip" (published: "Seed of the clip: random, or a whole number from 0 to 999999999") |
| `sound` | choice | `keep`, `cut` (only if path B of §4.9 is taken) | disk | "Sound track of the clip: keep, or cut from the file" |
| `references` | names | `hi=3` | session | "Reference pictures 1-3 by character name, as list_characters lists them; [] empties them" |

Notes:
- `references` keeps the Generate Image text **verbatim** (`screen.py:42-43`), so one sentence in the system
  prompt covers both screens. What a box *means* (first frame or identity) is reported by get, not by the label
  (§1.4), because it depends on the model and a label is static.
- No `guidance` (H3 declares `guidance_max_phases: 0`, blueprint §1.2), no `loras` (fused entries disable them,
  `hp:defaults/minimax_h3_fused_turbo.json:25`; turbo LoRAs are not local), no `count` (one clip per press).
- `resolution` is a live choice, not an enum: an enum is fixed at import and would advertise `1080p` to the model
  before it is turned on in Settings.
- The presence rule is the same as Generate Image: `draft` and `references` are refused with
  "No Generate window is open" while no workspace screen is connected (`screen.py:195-205,216-219`;
  `hub/core/bus.py:77-85` counts lines per role). See Open decision D4 for a per-tab variant.

Resulting descriptions (Measured, built with the real `features.tools_of` and checked with the real
`registry.validate` beside the shipped modules: "registry ok", banned words: none):

- `get_generate_video_settings` (113 chars): "Settings of the Generate Video screen: draft, model, seconds,
  resolution, aspect, steps, seed, sound, references."
- `set_generate_video_settings` (145 chars): "Set settings of the Generate Video screen: draft, model, seconds,
  resolution, aspect, steps, seed, sound, references. Returns the settings after."
- `list_video_models` (94 chars): "Video models that can run, with their lengths, resolution tiers, frame rate and
  default steps."
- `generate_video` (83 chars): "Render the draft as a clip with the screen's settings, as the Generate button does."
  Without `sound`, the core drops it from both screen descriptions.

### 1.4 What `get_generate_video_settings` returns (Proposed `view()`)

Same rules as the image `view()` (`screen.py:147-168`): the draft first, plain values, the seed as text, `last_seeds`,
and the values a press would render. Example:

```json
{"draft": "integrated_multimodal_description: [Shot 1] ...", "model": "minimax_h3_fused_turbo",
 "model_name": "H3 Fused 4-Step — Frames (Experimental)", "seconds": 8.0, "frames": 192, "fps": 24,
 "resolution": "540p", "aspect": "16:9", "width": 960, "height": 544, "steps": 4, "seed": "random",
 "last_seeds": [], "sound": "keep", "references": ["Character 1"], "references_as": "first frame"}
```

- `seconds` is the exact length on the grid (192 frames / 24 fps = 8.00), so "8 seconds" comes back as 8.0 and
  "6 seconds" as 6.58 (158 frames). Grid: `17*n+5`, 124–345 frames, 24 fps (`hp:models/minimax_h3/
  minimax_h3_handler.py:56-64,1740-1746`).
- `references_as` is `"first frame"` for a First/Last (FL2VA) model and `"identity"` for an Omni (Ref2VA) model.
  It is a value, not an instruction; the system prompt says what to do with it (§2.6).
- Read-only keys (`model_name`, `frames`, `fps`, `width`, `height`, `last_seeds`, `references_as`) are not in the
  set schema. When a model hands back the whole get result, Open WebUI drops the keys the schema does not name and
  passes the rest (`tests/engine/test_generate_image.py:388-403`); the video copy of that test does the same.

### 1.5 `list_video_models` (Proposed)

Fields asked for: id, name, tier, seconds range, fps, steps, loaded. Proposed shape, one entry per model that can
run (offered by the module setting and `available`, never `partial`; blueprint §1.7):

```json
{"models": [
  {"id": "minimax_h3_fused_turbo", "name": "H3 Fused 4-Step — Frames (Experimental)",
   "tiers": ["480p", "540p", "720p"], "seconds": {"min": 5.17, "max": 14.38}, "fps": 24,
   "steps": {"default": 4, "min": 4, "max": 8}, "references": 1, "references_as": "first frame", "loaded": false},
  {"id": "minimax_h3_ref2va", "name": "H3 Omni — Pruned", "tiers": ["480p", "540p", "720p"],
   "seconds": {"min": 5.17, "max": 14.38}, "fps": 24, "steps": {"default": 20, "min": 1, "max": 100},
   "references": 3, "references_as": "identity", "loaded": true}]}
```

- `name` is the engine's own (`hp:defaults/*.json:3`); a request's "turbo" maps to a name containing "4-Step"
  (§2.4). `loaded` is `id == catalog.resident`, as `list_image_models` does (`generate_image/tools.py:33-38`).
- `references` is the box cap the module will accept (FL2VA: 1 first frame in the primitive; Omni: up to 3 boxes,
  the engine allows 9 images, `hp:models/minimax_h3/reference_manifest.py:15-18`).

### 1.6 `generate_video` (Proposed)

No arguments, exactly as `generate_image` (`generate_image/tools.py:50-78`): the session's draft ("The draft is
empty" when blank), the saved settings and the session's boxes go to `ctx.jobs.submit("video", params)`; it answers
at once `{"state": "queued"}`, plus `"held"` when the VRAM plan holds it (`hub/core/jobs.py:146-150`). It never waits.

### 1.7 `list_characters`: who owns it (Proposed resolution)

Fact: it is declared by Generate Image (`generate_image/tools.py:83-93`) and reads only core data
(`ctx.files.characters()`, `generate_image/cast.py:65-67`, `api.py:220`). A second declaration in Generate Video would
fail the registry (`registry.py:115-116`), and a module may not import another (`tests/core/test_rules.py:57-64`).

Options: **A** stay in Generate Image (video's `references` label then names a tool that is gone whenever Generate
Image is disabled, `registry.py:3`); **B** move to Media, which owns the Characters folder and its routes
(`hub/modules/media/manifest.py:21-25`) — a `Listing` needs no screen, neither generate module imports the other;
**C** core publishes it (core publishes no tools today, `runtime.py:118-119`; a new path for one listing).

Recommendation: **B**. Same name, same text ("Characters by name, with the notes on each, from the Characters
folder."), same `{characters: [{name, notes?}]}` result, so the system prompt and the model see no change. Done in
Stage 1, before Generate Video exists, with the image tests unchanged except the module that declares it. (Agrees
with blueprint §3.7.)

---

## 2. The system-prompt contract (the Open WebUI side)

### 2.1 What the Hub does and does not do (Fact)

The Hub adds no system message or prefix: `wire()` sends `{role, content}` and the saved `output` items only
(`hub/modules/assistant/chat.py:157-168`); tool texts never say when to call (`features.py:4-6`). *When* to draft,
revise and render is the system prompt in Open WebUI (`generate_image/tools.py:9-10`). §2.2–§2.8 are the text.

### 2.2 Routing a request to video or to image

Both screens' tools are always listed; the model chooses by the words. Video: clip, video, animation, shot,
"animate", "make it move", seconds, 540p/720p, turbo. Image: picture, image, photo, still, portrait, megapixels,
count. "A clip of <character> …" is video with the character in `references`; "animate it" right after a picture
is video from that picture; anything unclear gets one short question: picture or clip.

### 2.3 First message drafts, later messages revise and render — for clips

Same rhythm as pictures (`04-assistant-mcp.md` §4.5.2): the first message of an idea writes the draft only
(`set_generate_video_settings {draft, references}`); a later one revises it and calls `generate_video`; a
setting-only message sets that key alone. A clip costs minutes and blocks the one queue (§4.3), so draft-first
matters more for clips than for pictures.

### 2.4 Setting-only messages (Proposed mapping, text in §2.8)

"8 seconds" → `{seconds: 8}` (comes back 8.0; "6 s" comes back 6.58); "540p" → `{resolution}`; "vertical" /
"square" / "wide" → `{aspect: "9:16" | "1:1" | "16:9"}`; "turbo" → `{model}` whose name has "4-Step"; "full quality" →
the Pruned or Full id; "keep the seed" → `{seed: "<from last_seeds>"}`; "new seed" → `{seed: "random"}`; "silent" →
`{sound: "cut"}` (path B only).

### 2.5 The H3 draft shape (Fact from the engine; Proposed use)

What reaches H3 is the draft, unchanged: the worker forces no enhancer and no rewriting (`hub/worker/wan2gp.py:33-45`),
and the module sends it as `prompt`. So the assistant must write H3's own dialect. From the engine:

- **Fields, FL2VA (text-only or first frame):** exactly `integrated_multimodal_description:`,
  `overall_soundscape:`, `non_diegetic_music:` in this order (`hp:models/minimax_h3/prompt_enhancer.py:4-33,89-92`,
  `hp:services/h3_prompt_policy.py:11-15`). `[Shot 1]` opens the timeline with no timestamp; a later cut is
  `[Shot N] At MM:SS.mmm, …` (`prompt_enhancer.py:22-24,94`). One continuous shot is preferred for short clips.
- **First frame:** the first line must be `For the target video, at 0.00 seconds into the target video, <Picture 1>
  (from [Shot 1]) is fully referenced.` then a blank line (`prompt_enhancer.py:120`,
  `hp:services/director/minimax_h3_prompting.py:20-23`).
- **Fields, Ref2VA (Omni):** `subject_definitions:`, `summary:`, `retention_analysis:`, `detailed_description:`,
  `overall_soundscape:`, `non_diegetic_music:` (`prompt_enhancer.py:36-63`, `h3_prompt_policy.py:16-23`).
  `<Subject N> is … from <Picture N>.`; summary starts `[reference generation]`; retention lines use
  `fully_preserved` etc. The encoder itself prefixes each reference image as `<Picture N>: <vision tokens>` in box
  order (`hp:models/minimax_h3/conditioner.py:204-208`), so the draft only names `<Picture 1..3>`.
- **What to describe:** subjects, setting, light, a causally continuous action path from onset to result, camera
  movement as type, amplitude and speed (`prompt_enhancer.py:94-96,122`).
- **Dialogue:** only words inside `<d>[Language] …</d>` are spoken; text outside is never spoken; the speaker is
  named before the tag (`prompt_enhancer.py:27,96,100,106`). Budget ≈ 2.1 words per second of clip
  (`hp:services/director/h3_dialogue.py:652-656`), i.e. ~10 words in a 5.17 s clip. For the primitive: no dialogue
  unless asked.
- **Sound:** H3 always renders a stereo track (`"returns_audio": True`, `minimax_h3_handler.py:1801`). The
  engine's own Director writes `overall_soundscape: N/A` and `non_diegetic_music: N/A` for a silent intent
  (`h3_dialogue.py:8-10`, "never describe sound… stay N/A") because described sounds become audible events.
- **Lines the engine eats:** every prompt goes through `prompt_parser.process_template` on submit
  (`hp:wgp.py:799`, reached via `shared/api.py:482` → `wgp.validate_task` `wgp.py:10145-10158`): a line starting
  with `#` is **dropped** and a line starting with `!` is read as a **macro** (`hp:shared/utils/prompt_parser.py:50-54`).
  A Markdown heading or "!important" in the draft silently vanishes or errors. The newlines themselves are safe:
  H3 declares `single_block_prompt: True` (`minimax_h3_handler.py:1753`, `wgp.py:812-821`).
- **Length:** no tokenizer cut (`conditioner.py:193-198` has no `max_length`), but text is part of H3's packed
  sequence (`minimax_h3_handler.py:49-55`). MiniMax recommends 350–500 English words for a Ref2VA
  `detailed_description` (`prompt_enhancer.py:73,144`); with five more sections that is ~3,000–4,500 characters, over the
  image module's 4,000 (`screen.py:30`). Hence `MAX_PROMPT` 6000 for video (Open decision D2).

### 2.6 Characters into reference boxes; what a box means

- Characters are found with `list_characters` and set by name: `{references: ["Character 1", "Character 2"]}`, any case, boxes 1–3 in
  order; a box handed back as get reported it is kept (`generate_image/cast.py:42-62`). The video `cast.py` keeps
  this behaviour and only its cap differs.
- **First/Last (FL2VA) model:** box 1 is the **first frame**. A character sheet used as a first frame makes the clip
  open on the sheet's pose and background. So "a clip of <character> doing X" wants an **Omni** model; "animate this
  picture" wants a **First/Last** model with that picture in box 1. The module reports `references_as`; it does not
  switch models by itself (the Hub decides nothing, §2.1). The system prompt carries the rule (§2.8).
- **Omni (Ref2VA) model:** boxes are identities; each named character gets `<Subject N> is <name> from <Picture N>`
  with its notes as appearance background (notes come only from `list_characters`).
- Image → clip: Media sends a Temp picture to the Generate Video reference box (Stage 4); get then
  reports that box by its file stem (`cast.py:26-29`), and the assistant keeps it by handing the label back.

### 2.7 Keep-seed

`last_seeds` lists the seed the last clip of the current model used (memory only); `{seed: "<that number>"}` fixes
it; "random" lets it go — the image contract unchanged (`screen.py:147-172`).

### 2.8 The paragraph for the Open WebUI system prompt (ready to paste)

Placed after the system prompt's existing picture rules. No names, paths or personal data. About 330 words (~450 tokens).

```text
CLIPS. Requests for a clip, video, animation, shot, or anything that moves use the Generate Video tools
(get_generate_video_settings, set_generate_video_settings, list_video_models, generate_video). Requests for a
picture, image, photo or still use the Generate Image tools. "Animate it" after a picture means a clip of that
picture. If it is unclear whether the chat message asks for a picture or a clip, ask one short question.

Same rhythm as pictures: the first message about a new clip idea writes the draft only (set draft, and references
if characters are named) and does not render. Later messages about that idea revise the draft and then call
generate_video. A message that only changes a setting sets that one setting and nothing else: "8 seconds" ->
seconds; "540p"/"720p" -> resolution; "vertical"/"square"/"wide" -> aspect 9:16/1:1/16:9; "turbo" -> the model
whose name says 4-Step; "keep the seed" -> seed set to the number in last_seeds; "new seed" -> seed random.

Characters: find them with list_characters and put the named ones in references, in order of appearance. Use their
notes as appearance background. A clip of a character uses a model whose references_as is identity (Omni). A clip
that starts from a given picture uses a model whose references_as is first frame, with that picture in reference 1.

Write the draft in English (dialogue keeps its own language), plain text, no Markdown, and no line that starts
with # or !. Fit the action to the clip's seconds; prefer one continuous shot.
First-frame or text-only models: exactly three fields, each on its own line:
integrated_multimodal_description: [Shot 1] subjects, place, light, the action from start to finish, the camera
move (type, size, speed).
overall_soundscape: N/A
non_diegetic_music: N/A
With a first frame, the very first line is: For the target video, at 0.00 seconds into the target video,
<Picture 1> (from [Shot 1]) is fully referenced.  -- then one blank line.
Identity (Omni) models: six fields: subject_definitions (<Subject 1> is NAME from <Picture 1>.), summary
([reference generation] ...), retention_analysis (<Subject 1> (appears in [Shot 1]): fully_preserved - ...),
detailed_description ([Shot 1] ...), overall_soundscape: N/A, non_diegetic_music: N/A.
Speech only when the chat message asks for it: the speaker, then <d>[English] the exact words</d>, about 2 words per second.
```

The `N/A` sound fields are the primitive's choice (silent intent, §4.9). If ambience is wanted, the two
`N/A` lines become "a short description of the ambience and physical sounds" and "N/A unless the chat message asks for music".

---

## 3. Context budget

### 3.1 Facts

- Only the last `keep` exchanges are kept (default 6, 1–20; `hub/modules/assistant/turns.py:19,39-49`).
- In every exchange before the newest, each **tool result** is cut to its first line, 120 characters
  (`turns.py:51-80`). The **tool calls go whole**, arguments included (`turns.py:9-11`): a `set {draft}` call keeps
  its full draft in history for all `keep` exchanges.
- Every completion carries `params.num_ctx` = "Context length", default 8192, 0 = Open WebUI/Ollama decide
  (`hub/modules/assistant/settings.py:18,71-73`). Past it the model's input is cut silently (Ollama's 4096
  default overflowed after about six turns).
- Open WebUI sends the tool list on every turn. Measured here with the real `registry.discover()` +
  `features.tools_of()`: today's six tools are **2,864 characters** of JSON (set image settings alone 1,792). The
  four video tools as proposed: **2,098 characters**. Together ≈ 4,960 characters.

### 3.2 Estimate per exchange (≈4 characters per token for English and JSON; Estimate)

| Part | Image today | Video (FL2VA draft) | Video (Ref2VA draft) |
|---|---|---|---|
| Tool list, every turn | ~720 t | ~1,240 t (both screens) | ~1,240 t |
| Owner's system prompt | ~600 t (unknown, not in repo) | +~450 t (§2.8) | +~450 t |
| Draft text (typical) | 60–160 t | 250–450 t | 750–1,100 t |
| Older exchange: message + `set {draft}` call (whole) + cut result + reply | 150–300 t | 350–600 t | 850–1,250 t |
| Newest exchange: call + full result (echoes the draft again + ~100 t of settings) | 300–500 t | 650–1,100 t | 1,650–2,400 t |
| **Total at keep=6** | **≈ 2.4–3.3k** | **≈ 4.7–6.8k** | **≈ 8.3–12.4k** |

### 3.3 Verdict and proposals

- Image-only fits 8192 with room. FL2VA clips fit at keep=6. **Ref2VA clips overflow 8192** by exchange 4–6, and the
  overflow is silent.
- **Proposed (assistant module, not video-specific): lean also trims older call arguments.** In exchanges before the
  newest, each `function_call` item's `arguments` JSON is re-serialised with every string value over 120 characters
  replaced by its `brief()` form; keys, call ids and the tool name stay, so the model still sees that it set a draft.
  The newest exchange stays whole, and every `set` result echoes the full current draft, so the model always has
  the draft it is revising. Effect: an older Ref2VA exchange drops from ~1,000 t to ~200 t; total ≈ 4.5–5.5k.
  Test: `tests/core/test_assistant_lean.py::test_lean_cuts_long_strings_in_older_call_arguments` (valid JSON after,
  short strings untouched, newest exchange untouched, the kept message unchanged). Unverified: that Open WebUI 0.11.4
  passes a re-serialised `arguments` string through `convert_output_to_messages` unchanged (U5).
- No other video-specific trim: `view()` keeps the image shape. Owner advice (a setting, no code): Context length
  16384 for Omni drafts if Ollama's GPU has room; `keep` 4 for long clip sessions.

---

## 4. Risks and mitigations

Each: the code fact, then the mitigation (Proposed unless marked Fact).

### 4.1 VRAM

- Fact: H3 reserves 10 GB of working VRAM on top of streamed weights, whatever the card (`hp:…/minimax_h3_handler.py:
  49-55`); its memory curves are calibrated on a 24 GB 4090 at 345 frames 1280x704 (`:546-551`).
- Fact: the Hub learns VRAM peaks **per model and GPU only**: key `"{model}|{uuid}"`, last three values, max
  (`hub/core/vram.py:64-72`). A 480p 5 s clip teaches a peak that a 720p 14 s clip exceeds.
- Fact: the engine picks a smaller pass (sliding windows) by VRAM unless the window equals the clip; a request whose
  window covers the whole clip sets `sliding_window_memory_override` (`minimax_h3_handler.py:1236-1262`). The
  blueprint's `sliding_window_size = video_length` therefore buys "one pass, exact length" at the price of "no
  automatic shrink": an over-large request OOMs instead of splitting.
- Mitigation: `tiers_offered` default 480p/540p/720p (blueprint §1.3); Stage 0 measures peak VRAM at 540p×5 s and
  720p×14 s on the server's engine GPU; the job card's "run anyway" stays the card's override
  (`hub/core/jobs.py:139-144`). Later, and only if Stage 0 shows the spread: learn by `(model, frames×w×h bucket)` in
  `vram.py` — a core change with its own tests, out of the primitive.

### 4.2 Time per clip vs the 10-minute limit and the Hub's timeouts

- Fact: the Hub waits at most **600 s** for Open WebUI's whole tool loop (`hub/modules/assistant/link.py:17,166`);
  `generate_video`, like `generate_image`, only submits (`generate_image/tools.py:74-78`): the render is outside it.
- Fact: **no per-task timeout** in the Hub: `EngineLane._task` waits for events until `task_done` or worker exit
  (`hub/core/engine.py:146-176`). Timeouts that exist: worker start 600 s (`hub/core/supervisor.py:108,171`), 3
  crashes in 600 s (`supervisor.py:26-28`), chat delete 30 s (`link.py:18`), VRAM hold re-check 15 s (`line.py:19`).
- Risk: a model that "waits for the clip" by calling get repeatedly inside one turn can run into the 600 s limit
  and the turn ends with an error line. Mitigation: no status tool in the primitive; the system prompt says nothing
  about waiting; the job card shows progress.

### 4.3 One queue shared with images

- Fact: one FIFO per lane, head-of-line blocking by design (`hub/core/dispatch.py:1`); one engine lane; jobs go to a
  lane already holding the model, else the shortest queue (`jobs.py:81-84`); `queue.max_waiting` 10
  (`hub/settings.py:29`), "Queue is full" beyond (`jobs.py:85`).
- Risk: image, clip, image, clip unloads and loads H3 (21 GB fused checkpoint, `hp:defaults/
  minimax_h3_fused_turbo.json:41`, plus the Qwen3-VL text encoder) every switch. A queued image waits behind a
  multi-minute clip.
- Mitigation: documented behaviour; `held` text is returned by both actions and shown on the server's card; the job
  can be cancelled. No reordering (it would break the FIFO contract and its tests).

### 4.4 Blocked downloads, missing companion files, progress stalls

- Fact: the worker blocks outbound sockets and DNS (`hub/worker/netguard.py:27-45`); H3 needs the transformer, video
  VAE, audio VAE and text encoder (`hp:defaults/minimax_h3_fused_turbo.json:13,42-47`). Mitigation: video lists
  `available` models only (images accept `partial`, `generate_image/models.py:82-85`); Stage 0 inventories files.
- Fact: progress is step/steps, never backwards (`hub/core/enginecat.py:70-77`); VAE decode, audio decode and mux
  carry no steps (blueprint §2.13); no watchdog (§4.2). Mitigation: phase text ("decoding"); one pass only; cancel
  between events (`engine.py:89-95`). Whether a cancel interrupts VAE decode is U7.

### 4.5 Output size and `land`

- Fact: `land` runs `clean.strip`, which opens the file with Pillow; an `.mp4` raises, the file is **deleted** and the
  job fails "The engine wrote a picture the hub could not read" (`hub/core/enginecat.py:104-114`,
  `hub/core/clean.py:27-33`). `/files/<item>` serves `existing_image` only, so a clip would 404
  (`hub/core/fileroutes.py:59-64`, `hub/core/files.py:104-108`).
- Fact: the engine writes `<name>_tmp.mp4` beside the output and removes it; leftovers are swept after each task
  (`hp:wgp.py:9416-9455`, `enginecat.py:95-101`).
- Size: x264 quality 8, yuv420p (`hp:shared/utils/audio_video.py:625-628`) — a few MB at 540p×5 s, tens of MB at
  720p×14 s (Estimate; Stage 0 measures). Temp has no quota.
- Mitigation: Stage 1 `land` by kind (blueprint §2.4–§2.5): a clip is checked and cleaned by the stdlib `clip.py`,
  never by Pillow.

### 4.6 Codec and container the engine config writes

- Fact: `video_container` default `mp4`, `video_output_codec` default `libx264_8` (`hp:wgp.py:3485-3486`). The
  engine's config on the server may say `libx265_*` (HEVC) or `libx264_lossless` (yuv444p, or FFV1 in MKV)
  (`audio_video.py:625-640`). No `+faststart`: the `moov` box is written at the end (no `movflags` anywhere in
  `audio_video.py` or `wgp.py`), so a player needs a Range read of the file's tail before it can start.
- Risk: HEVC and 4:4:4 H.264 do not decode in every Chromium build; MKV does not play in `<video>`.
- Mitigation: force `video_container: "mp4"` in the worker (blueprint §2.6); Stage 0 records the codec actually
  written; Open decision D3: also force `video_output_codec: "libx264_8"`, or show "This clip's codec doesn't play
  here" on the `<video>` error.

### 4.7 HTTP Range for seeking (Measured)

- Fact: the installed Starlette here is 1.6.0 (the lock pins 1.7.0, `requirements/controller.lock:20`). Its
  `FileResponse` parses `Range` and answers 206/416 (`starlette/responses.py:362-407`).
- Measured (scratch script, a 5,000-byte file served by `FileResponse` with `no-store`): `Range: bytes=0-99` →
  `206 bytes 0-99/5000`, 100 bytes; `bytes=4990-` → `206 bytes 4990-4999/5000`; `bytes=9000-` → `416 bytes */5000`.
- Fact: the Guard only appends headers to `http.response.start` (`hub/core/guard.py:197-208`), so 206 and
  `content-range` pass through. CSP has no `media-src`, so `default-src 'self'` applies: `/files/…` plays, a
  `blob:` URL would not (`guard.py:30-31`). `x-content-type-options: nosniff` means the served type must be
  `video/mp4`.
- Mitigation: Stage 1 test through the real `/files` route on the pinned 1.7.0 (§5, Stage 1).

### 4.8 The desktop client playing video

- Fact: HocusPocus Desktop is Electron 44.7.0 (`hpd:package.json:20`), built only as a **Linux AppImage**
  (`hpd:package.json:14,52-55`); no Windows target exists in this source (U9). Its only switch is
  `host-resolver-rules` (`hpd:src/main/main.ts:20`); pages are sandboxed (`hpd:src/main/session.ts:47-56`); requests
  outside the network are cancelled (`hpd:src/main/privacy.ts:42-47`), `/files` is not. No `autoplayPolicy`.
- Expectation (Unverified, U8): Electron's bundled FFmpeg decodes H.264 and AAC, so no flag is needed for
  `libx264_8` + AAC; HEVC would need platform decoders. Stage 3 checks `video.canPlayType('video/mp4;
  codecs="avc1.640028, mp4a.40.2"')` inside the client and plays one clip with seek.

### 4.9 Audio is always in H3's output — keep or strip

- Fact: H3 renders picture and sound jointly and always returns audio (`minimax_h3_handler.py:1801`); wgp muxes it
  as AAC with `-c:v copy` (`hp:wgp.py:9415-9452`). The compute is spent either way.
- **Path A — keep (primitive default):** the file has its sound; Media plays it with controls. The draft writes both
  sound fields as `N/A` (the engine's own silent policy, `h3_dialogue.py:8-10`) so H3 is not asked for sounds. No
  code beyond playback.
- **Path B — cut:** a `sound` setting (`keep`/`cut`). The cut happens in the **worker**, which already runs inside
  the engine's environment where `imageio_ffmpeg` exists (blueprint Stage 0 item 6): after `task_done` and before
  the `output` event, remux `-an -c:v copy` into the outbox. The controller keeps "no ffmpeg" (blueprint §2.15).
  A stdlib cut in `clip.py` (drop the audio `trak`) would leave the AAC bytes in `mdat`; rejected. A UI-only
  `muted` attribute leaves sound in the file; rejected for "primitive video".
- Open decision D1.

### 4.10 Assistant-side risks

- Two screens' tools in one list: a small model may call `set_generate_image_settings` for a clip. Mitigation: §2.2
  routing text; distinct draft labels ("…for the clip…"); the Stage 2 acceptance includes three routing prompts.
- A draft in Markdown or with `#` headings loses lines silently (§2.5). Mitigation: the paragraph forbids it;
  Open decision D5: the module refuses a draft line starting with `#` or `!` with one plain line.
- `chat.cleared` must empty the video draft too: Generate Video `listens` to it as Generate Image does
  (`generate_image/manifest.py:47`, `assistant/chat.py:51`).

---

## 5. Stage plan

Every stage: tests first, the suite green, then one package. Paths below are generic: `<engine-root>` is the
HocusPocus `app` folder, `<data>` the Hub's data folder, `<engine-python>` the engine's interpreter.

### Stage 0 — verify on the server (read-only; no Hub change)

Checks, one short command each, nothing written:
1. `ls <engine-root>/defaults | grep -E '^minimax_h3'` — the definitions present.
2. Per folder in `engine.model_folders`: `find <folder> -maxdepth 3 -iname '*h3*' -printf '%s\t%p\n'` —
   transformer, video VAE, audio VAE, text encoder present (against `required_model_assets` in the definition).
3. `nvidia-smi --query-gpu=index,name,memory.total,memory.used --format=csv` and `free -g` — the engine's card, RAM.
4. `<engine-python> -c "import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())"` — the encoder (path B).
5. `grep -E '"(video_output_codec|video_container|audio_output_codec)"' <engine config>` — what it writes.
6. **One clip is run in HocusPocus's own UI**: `minimax_h3_fused_turbo` (or `minimax_h3`), 540p 16:9, 124
   frames, default steps, text only, a prompt in the §2.8 three-field shape. The seconds taken and peak VRAM are noted
   (`nvidia-smi` in a second terminal, or the engine's own readout). Then on the produced file:
   `ffprobe -v error -show_entries format=format_name,duration,size:stream=codec_name,profile,pix_fmt,width,height,
   r_frame_rate,channels -of compact <clip>` and `strings -n 6 <clip> | grep -i -E 'lavf|x264|seed|prompt' | head`.
7. Same clip at 720p, 14.38 s if time allows (the VRAM spread for §4.1).

Done when: one clip played; codec, profile, pixel format, container, fps, audio and size recorded; every needed file
local; seconds per clip and peak VRAM written into this note's §4. A failed check stops the plan and is recorded.
Accepted when: the clip has been watched and the numbers are written down.

### Stage 1 — core lifts (no new tab; Generate Image unchanged in behaviour)

Work: `list_characters` moves to Media (§1.7); media kinds in `api.py`; `clip.py` (stdlib check + metadata strip);
`land` by kind; `/files` serves video with its type; Media lists clips; the assistant `lean` arguments trim (§3.3);
`video_container` forced in the worker.

Tests that prove it:
- `tests/core/test_mcp.py::test_the_shipped_modules_publish_six_generated_tools…` — still six, `list_characters` now
  from Media, same text and schema; the conformance test (`tests/core/test_mcp_conformance.py`) unchanged.
- `tests/engine/test_generate_image.py` — every existing test passes unchanged except the declaring module of
  `list_characters` in `test_generated_tools_say_what_the_screen_has_and_nothing_about_when`.
- New `tests/engine/test_media.py::test_list_characters_is_published_by_media`.
- New `tests/core/test_files.py::test_a_clip_is_served_with_range` — `GET /files/<clip>` with `Range: bytes=0-99`
  → 206, `content-range`, `video/mp4`, `no-store`; `bytes=<size>-` → 416; on Starlette 1.7.0.
- New `tests/core/test_clip.py` — a real tiny MP4 fixture: accepted; `udta`/encoder text removed; a non-MP4 refused;
  a file Pillow cannot read is no longer deleted as "a picture".
- New `tests/engine/test_engine_lane.py::test_an_mp4_output_lands_as_a_clip` with the fake worker emitting an MP4.
- New `tests/core/test_assistant_lean.py::test_lean_cuts_long_strings_in_older_call_arguments`.
- `tests/core/test_rules.py` — line limits, module imports, no HTTP clients: unchanged and green.

Done when: all green; a hand-placed MP4 in Temp shows, plays and seeks in Media and can be deleted; Generate Image
behaves as before. Owner accepts: drops one clip into Temp, plays and deletes it in Media; makes one picture as
before.

### Stage 2 — module skeleton, settings, MCP visible in Open WebUI (nothing renders)

Work: `hub/modules/generate_video/{manifest,models,screen,routes,tools,cast}.py`, the tab with draft panel and bar.

Tests (`tests/engine/test_generate_video.py`, each mirroring an image test by name):
- `test_manifest_declares_tab_sockets_routes_and_tools`; registry accepts it beside the shipped modules.
- `test_generated_tools_say_what_the_screen_has_and_nothing_about_when` — the exact schemas of §1.3 and the
  banned-word scan, copied from the image test.
- `test_list_video_models` — §1.5 shape from a fake catalog; `partial` models absent; `loaded` correct.
- `test_seconds_round_up_to_the_frame_grid` — 5→5.17/124, 6→6.58/158, 8→8.0/192, 14.4→14.38/345, 15→refused
  with one line naming the maximum.
- `test_resolution_and_aspect_give_the_models_size` — 540p 16:9 → 960x544; 720p 9:16 → 704x1280; 1080p refused
  while not offered.
- `test_steps_outside_the_models_range_are_refused`; `test_set_draft_needs_a_generate_window`;
  `test_references_need_an_open_generate_window`; `test_new_chat_empties_the_video_draft`;
  `test_no_tool_writes_the_owners_prompt_box`; `test_set_takes_back_what_get_reported_with_one_value_changed`.
- `tests/core/test_mcp.py` — ten tools, in order; a `set_generate_video_settings {draft}` over `/mcp` with a window
  open lands in the video panel and touches neither the image draft nor any file.

Done when: all green; in a fake-engine run the tab shows the models and `set_generate_video_settings` from
`tests/core/mcp_driver.py` redraws an open window. Owner accepts in Open WebUI (tool server refreshed): the ten
tools listed; "a clip of a red fox running through snow" writes the draft in the Generate Video panel and nothing
renders; "8 seconds" moves the bar to 8.00 s; "turbo" picks the 4-Step model; "a picture of a red fox" writes the
**image** draft.

### Stage 3 — render path, Media landing, playback

Work: `build.py`, the `generate_video` action, the Generate button, Media's clip view and tile.

Tests:
- `test_plan_sends_every_value_explicitly` — the exact task dict (`image_mode: 0`, `video_length`,
  `sliding_window_size`, `resolution`, `num_inference_steps`, `seed`, `prompt` unchanged) and summary title.
- `test_generate_video_renders_the_draft_as_the_generate_button_does`; `test_an_empty_draft_is_refused`;
  `test_a_held_job_says_why` (`held` text).
- Fake worker emitting an MP4: the job finishes, Media gets a `generation` of kind video, the clip is listed;
  cancel during a clip; queue full shared with images.
- Web e2e: a clip plays on the Stage, seeks (the page receives a 206), and the Grid tile has no `<img>`.
- Mutation check: break `land`'s kind switch and the snap-up rounding; the new tests must fail.

Done when: on the server, text → clip from the button and from `generate_video` lands in Media and plays with seek
in the desktop client; `strings` finds no prompt and no encoder text; the next image job runs after the H3 unload.
Owner accepts: two clips (button and assistant), one image after them, all three in Media.

### Stage 4 — references and characters (Ref2VA), image → clip (FL2VA)

Tests: names resolve through `Files.character`; the cap is the model's (FL2VA 1, Omni 3); a box handed back as
reported is kept; `references_as` in `view()` and `list_video_models`; the task carries absolute paths only;
FL2VA → `image_prompt_type "S"` + `image_start`; Omni → `minimax_h3_references [{type: image, path,
image_intent: identity, character_name}]` (`hp:models/minimax_h3/reference_manifest.py:24,84-87`).

Done when: "a clip of <character> walking through rain" with an Omni model gives a recognisable character; a Temp
picture sent from Media becomes the first frame of an FL2VA clip. Both are judged by eye.

### Stage 5 — later, each its own design note first

Dialogue (`<d>` lines, budget), sound kept with ambience, sound cut (path B) if not done earlier, audio
references (`voice | drive | style`), sliding windows past 14.38 s with progress folded, turbo LoRAs if local,
Director-like chaining (several clips in sequence) — the last stays outside the Hub's tools unless a chat message asks.

---

## 6. How the work proceeds

1. **One stage at a time.** Nothing of the next stage starts until the current one is accepted.
2. **A written plan before code:** the files it changes, what it writes and where, what it leaves alone; the stage starts once it is accepted.
3. **Tests first.** The stage's tests are written and shown failing before the code that makes them pass. Each new
   test is mutation-checked: the code it guards is broken on purpose and the test goes red.
4. **No package until the stage's suite is green** — server, web unit and browser tests, counts in the change record.
5. **No blaming the model without reading the code path.** "It says it did it but nothing changed": first read what
   the Hub sent and received (both causes were the Hub's), only then the model or the prompt.
6. **Measurement for the screen.** Layout and playback are proven by browser tests that measure (sizes, positions,
   a 206 for seeking, `canPlayType`), not by a screenshot.
7. **Nothing fetched, logged or left in a file.** Stage 0 confirms the files are local; Stage 3 checks with `strings`.
8. **Short diagnosis:** one short read-only command at a time on the server, never a long log.
9. **You decide** every Open decision below; the default is written beside it.

---

## Open decisions

- **D1 Sound:** path A (keep the track, sound fields `N/A`) or path B (`sound` setting, cut in the worker).
  Default A for the primitive.
- **D2 Draft cap:** `MAX_PROMPT` 6000 for video (Omni drafts run 3,000–4,500 characters) or 4000 as images.
- **D3 Codec:** force `video_output_codec: libx264_8` in the worker, or keep the engine config and show a
  plain line when a clip cannot play.
- **D4 Presence:** refuse a video draft with no workspace window (same as images, any tab), or only when no window
  shows the Generate Video tab (needs a core lift: `bus.presence()` adding counts by `line.tool`,
  `hub/core/bus.py:255-261`).
- **D5 Lines the engine eats:** refuse a draft line starting with `#` or `!`, or leave it to the system prompt.
- **D6 Read-only keys in set:** Open WebUI drops them; another MCP client sending them gets "unknown
  argument". Accept and ignore them in the core schema check (both screens), or leave as is.
- **D7 Character on an FL2VA model:** the box is a first frame (current proposal), or refuse a character name on an
  FL2VA model with "This model takes a first frame, not a character".
- **D8 Lean trim of call arguments** (§3.3): in the assistant module now (Stage 1), or only if Omni clips overflow.
- **D9 `list_characters` owner:** Media (recommended), Generate Image, or core.

## Unverified

- U1 Seconds per clip and peak VRAM on the server's engine GPU (Stage 0).
- U2 The codec, profile, pixel format and audio actually written by the engine config; whether `Lavf` /
  x264 SEI text is in the file (Stage 0).
- U3 That `sliding_window_size = video_length` with the override gives exactly one pass on this fork, and what an
  over-large request does (OOM vs refusal) (`minimax_h3_handler.py:1236-1262`).
- U4 That Starlette **1.7.0** (the pinned version) answers Range as 1.6.0 does here (Stage 1 test).
- U5 That Open WebUI 0.11.4 accepts re-serialised `function_call.arguments` with shortened strings and hands them to
  Ollama unchanged (§3.3).
- U6 The token figures in §3.2 (estimates at ~4 characters per token; the system prompt is not in the repo).
- U7 Whether a cancel interrupts H3's VAE decode. U8 That Electron 44's bundled FFmpeg plays H.264 High + AAC in MP4
  without flags, and how it treats HEVC. U9 Whether a Windows build of the client exists (this source: Linux only).
- U10 That `<Picture N>` numbering in the encoder follows the order of `minimax_h3_references` as the module sends
  the boxes (`conditioner.py:204-208` enumerates the images it is given).
- U11 How Open WebUI prefixes tool names to the model (the fake uses `hub_<name>`, `tests/fakes/openwebui.py:146`).
