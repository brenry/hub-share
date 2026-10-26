# 2. Generate Image

Scope: the server module `hub/modules/generate_image/` (manifest, routes, screen, tools, cast, build, chain, models), the
LoRA module it pairs with (`hub/modules/loras/`), and the web screen `web/src/modules/generate-image/`, with
Stage 6 (continuing a clip), Stage 7 (Omni references) and the Stage 8 lifts into `hub/core`.
Every statement cites the file (and line or function) it can be checked against. Paths below drop the
prefixes `hub/modules/generate_image/` (written `gi/`), `hub/modules/loras/` (written `loras/`) and
`web/src/modules/generate-image/` (written `web/gi/`) when the context is clear.

## 2.0 One-paragraph summary

The Generate screen has two texts. The **prompt box** holds the typed message to the assistant: Enter sends it to the
chat and clears it (`web/gi/compose/PromptBox.tsx:66-74`). The **draft** is the assistant's prompt. The assistant
writes it through the MCP setting `draft` (`gi/screen.py:31`), and it is shown as a two-column page
(`web/gi/chat/Article.tsx`). Generate renders the draft and never the prompt box (`web/gi/useGenerate.ts:17-18,34`;
`web/gi/job.ts:57`). The settings (model, LoRA stacks, aspect, size, count, per-model steps/guidance/seed) are saved
to `draft.json` (`gi/routes.py:28`). The prompt, the draft, the reference boxes and the LoRA selection belong to the
session: they are held in server memory only (`gi/routes.py:27,29,42-43`). A press builds one job payload
(`web/gi/job.ts:buildJob`). The core turns it into a `JobPlan` of N one-image tasks (`gi/build.py:image_job`), and the
worker translates each task for the engine line (`translate` in `hub/worker/adapters/fork.py:45` or `upstream.py:47`, called from `Engine._params`, `hub/worker/wan2gp.py:166-172`).

A model of the engine's catalog may be a **clip model** (`kind` "video"). The same screen, the same bar and the same
six tools then make one clip: the press builds one task (`gi/build.py:clip_job`, `:161-211`), the output lands in the
clips root (part 3) and is listed in the Clips section of Media. A clip placed in box 1 is continued: the same press makes its scene longer
(`gi/chain.py`, §2.10.7). §2.10 collects what changes for a clip model.

---

## 2.1 Screen layout and regions

The root component is `web/gi/GenerateImage.tsx:25-86`. Its doc comment (lines 21-24) describes the plan. The
rendered tree (lines 71-85) is:

```
div.work                                   grid: [minmax(0,1fr) | clamp(25.75rem, 27%, 31rem)]  (GenerateImage.module.css:7)
├── section.main  data-region="compose"     rows: [1fr | auto]                                    (css:11)
│   ├── <Article/>   data-region="draft"    the assistant's draft, two-column pager
│   └── <Dock/>      data-region="dock"     prompt box + status line (job line / seed line)
└── div.side      data-region="side"        rows: [1fr | auto], position: relative               (css:15)
    ├── <Chat/>      data-region="chat"     the assistant's replies
    ├── div.sheetBox data-region="library-sheet"  absolute over the chat, inert when shut       (css:17-20)
    │   └── <LoraLibrary tight/>            model picker, guidance, LoRA list
    └── <Taskbar/>   data-region="bar"      the one-line bar, bottom right
```

### 2.1.1 Draft page — `chat/Article.tsx`

- It reads only `draft.draft` from the store (`Article.tsx:15`).
- The text is split into paragraphs on blank lines (`Article.tsx:69`). An empty draft shows the placeholder "The
  assistant's draft appears here" (`Article.tsx:74`).
- The CSS lays the text out in two columns: `columns: 2; column-fill: auto` (`chat/Article.module.css:13`). The flow
  grows sideways one page at a time. `measure()` computes the page width (window width plus one column gap) and the
  page count (`Article.tsx:26-34`). A page turn applies `translateX(-page*width)` (`Article.tsx:42-44`).
- A wheel gesture turns exactly one page. A gesture ends after `GESTURE_MS = 180` ms without a wheel event
  (`Article.tsx:9,47-62`). When the article has focus, PageUp/PageDown and the arrow keys also turn pages
  (`Article.tsx:63-67`).
- A new draft text resets to page 0 (`Article.tsx:35`).
- The footer appears only when there is text (`Article.tsx:77-82`). It shows `page / pages` when there are more than
  one, and a **Clear** button that runs `edit(d => ({...d, draft: ''}))`. Clear is the only way a window writes the
  draft field (see `gi/routes.py:5`: "a window writes it only to clear it").

### 2.1.2 Prompt box — `compose/PromptBox.tsx`

- It is a `<textarea id="prompt">` laid over a mirror `div`. The mirror tints the trigger words of the active LoRAs
  (`PromptBox.tsx:98-111,117-121`). Trigger words come from `LoraItem.fileTriggers` of the LoRAs on the current stack.
  Ranges come from `compose/triggers.ts:findRanges`, which matches whole phrases case-insensitively on Unicode
  letter/number boundaries and merges overlaps.
- A character count appears past 90% of `PROMPT_MAX = 4000` (`PromptBox.tsx:122`; `types.ts:74`).
- Keys, handled in `sendOnEnter` (`PromptBox.tsx:66-74`), in this order:
  1. While the character tiles are open, `pickerKey` handles the key (lines 30-45).
  2. Tab runs `completeOnTab` (lines 49-62). See §2.5.
  3. Enter with no modifier (and not during IME composition) trims the text. If the text is empty or the chat is
     busy, nothing happens. Otherwise it clears the box (`edit(... prompt: '')`) and calls `say(text)`. If `say`
     fails, the text goes back into the box, but only when the box is still empty (line 73).
  4. Shift+Enter inserts a newline (default behaviour). Ctrl+Enter is bound at screen level by
     `useCtrlEnter(gen.go, visible)` (`GenerateImage.tsx:56`) and renders the draft.
- The box is typed into only. The prompt field is not an MCP setting (`gi/screen.py:6-7`), and
  `tests/engine/test_generate_image.py::test_no_tool_writes_the_owners_prompt_box` asserts that no tool changes it.

### 2.1.3 Reply column — `chat/Chat.tsx`, `chat/assistant.ts`

- The chat store is `chat` (`assistant.ts:15`). `useAssistant()` loads `GET /api/assistant/chat` on every (re)connect
  (`connects` counter) and follows `assistant.chat` bus events (`assistant.ts:18-25`).
- `Chat.tsx:55-58` renders only `assistant` messages (text plus seconds) and `error` messages. Messages of role `user`
  and of any other role render as `null`.
- The head row shows the chat model name and, when there are messages, a **New chat** link (`Chat.tsx:34-37`).
- While the chat is busy, it shows "Waiting for Open WebUI…" with dots (`Chat.tsx:43`).
- Auto-follow: the column follows new messages while the scroll position is within `FOLLOW_PX = 48` of the bottom
  (`Chat.tsx:10,20-24,39`).
- `say(text)` POSTs `{text}` to `/api/assistant/chat`. A failure shows its text in the reference note line through
  `inputs.note` (`assistant.ts:28-36`).
- `newChat()` (`assistant.ts:42-45`) first calls `clearWords()` (§2.2.6). It then waits for `settled()`, so that any
  in-flight draft save lands first, before it sends `DELETE /api/assistant/chat`.

### 2.1.4 The bar — `run/Taskbar.tsx`

The bar is one `<footer data-region="bar">` (`Taskbar.tsx:47-68`). Left to right:

| Element | Source | Notes |
|---|---|---|
| LoRA sheet fold (thumbs icon) | `Taskbar.tsx:48-50` | toggles `library` state in `GenerateImage.tsx:29,82`; `aria-expanded` |
| Reference boxes | `run/Slots.tsx` | always `BOXES = 3` (`Slots.tsx:22`); boxes past `refCap` are struck through (`data-shut`, `:67`); a filled box shows the thumbnail, a badge and a remove button; a clip in box 1 plays there (a muted `<video>`, hover text "Continues <stem>", `:52-58`) and shuts boxes 2 and 3 with "A continued clip takes only box 1" (`shut`, `:89`; `CLIP_ONLY_TEXT`, `blocking.ts:9`); drop accepts Media drags (`MEDIA_DRAG`) or files, and a clip id in a Media drag goes to the hub as a continue instead (`drop`, `:26-34`; §2.10.7; the Grid does not put a clip in that drag, see the gaps); right-click, Shift+F10 or the menu key opens the box's menu (`Menu`, `:93`): "Cut out background" / "Keep background" on an identity box (`cuts`, `:80`; `toggleCutout`, `edits.ts:77-84`; a small mark shows while on, `Run.module.css` `.cut`) and Remove; the model passed is `refModel(model)` (`Taskbar.tsx:52`): a video model itself, else the refs default or the model. A video model's boxes are named by its role: "Start frame", "Last frame", "Identity n" (`video.ts:boxLabel`, `:83-89`; `Slots.tsx:88`) |
| Size (MP) | `run/Canvas.tsx:SizeMenu` (39-50) | options `SIZES = [1,1.5,2,4]` (`job.ts:9`); hover hint shows `width × height` from `canvasOf`. For a video model the options are its offered tiers by name (`tierOptions`, `video.ts:16-17`) and the hint is `clipSize`. With a clip in box 1 the button is greyed (`aria-disabled`) and its hover text is "The clip's size, W×H" (`Greyed`, `Canvas.tsx:26-30`; `SizeMenu`, `:52`) |
| Aspect | `run/Canvas.tsx:AspectMenu` (26-35) | `auto` + 7 ratios (`Canvas.tsx:13`); Auto is drawn as a dashed square. With a start frame in box 1 of a video model, Auto's hover text is the clip size it snaps to (`:29-31`). With a clip in box 1 it is greyed like Size (`:41`) |
| Steps | `run/Canvas.tsx:Steps` (53-67) | only when a model exists; per model via `withAdvanced`; clamps 1..100 |
| Image count | `run/Canvas.tsx:Count` (88-99) | − n +, clamps 1..6. For a video model `one` is set (`Taskbar.tsx:44,56`): it shows 1 with both buttons off, title "One clip" |
| Connection light | `ui/Live` (`Taskbar.tsx:58`) | |
| Instances (monitor) | `Taskbar.tsx:59-62` | only `insideDesktop()` |
| Utilities menu | `Taskbar.tsx:34-42,61-62` | Settings; "Clear the GPU cache" (`gpu.release` bus request); "Seed back to random" (`POST /api/generate-image/seed/random`) |
| Generate | `Taskbar.tsx:65-66` | `onClick={press.go}`; `aria-disabled` when `press.reason` is set; title is the reason or "Generate N images from the draft" (`run/jobs.ts:37`); the label is "Generate clip" for a video model (`jobs.ts:53`) |

`BarMenu` (`run/BarMenu.tsx`) is the shared button-plus-popover listbox used by Size and Aspect.

### 2.1.5 Raised LoRA sheet — `GenerateImage.tsx:79-81`, `library/LoraLibrary.tsx`

- The sheet is `position:absolute` over the reply column and stops above the bar (`bottom: var(--gen-bar-h)`). Shut,
  it is translated down by 100% and has `pointer-events:none` (`GenerateImage.module.css:17-20`). It is also `inert`
  when shut (`GenerateImage.tsx:79`).
- When the sheet rises, focus moves to `[data-region="model-picker"]`. Escape lowers it, unless a popover is open, and
  returns focus to the fold button (`GenerateImage.tsx:58-69`).
- Contents (`LoraLibrary.tsx:87-108`):
  - The head holds the `ModelPicker`, which runs `withModel` on pick. A `Guidance` input sits under it only when
    `model.guidanceKey` is set (line 78). For a video model that lists text encoder variants, a **Text encoder** menu
    sits there too (`Encoder`, `:24-34`, drawn at `:79`; options from `encoderOptions`, `video.ts:64-68`, a variant
    whose file is not in the model folders says "· not found"). It writes `advancedByModel[model].text_encoder`
    (`withAdvanced`, line 31); a clip model has no guidance, an image model no encoder, so the head never holds both.
  - For a model whose reference announces a detail choice (Omni), a **Detail** menu sits under the encoder (`Detail`,
    `LoraLibrary.tsx:37-47`, drawn at `:93`): the engine's choices in its order and by its labels (`detailOptions`,
    `video.ts:82-83`); it writes `advancedByModel[model].detail` (`withAdvanced`) and shows the saved value, else the
    engine's default (`detailOf`, `video.ts:75-80`). A picture model and First / Last have none.
  - The list shows the **saved** rows first: the current model's stack in stack order, each with its strength
    (`SavedRow`). Then comes a rule, then the **other** LoRAs of the folder sorted A–Z by file stem
    (`library/order.ts:others`), each as an `OtherRow`.
  - A stack entry whose file has gone is shown by its id (`gone()`, lines 17-20).
  - Keys: Up/Down move the selection; Space/Enter toggle the LoRA on or off (lines 41-57).
- `SavedRow` (`library/LoraRow.tsx:21-35`) has a strength line along the top (`share()` caps it at 1.0) and a
  `DragNumber` from 0 to 2, step 0.01, whose reset is `defaultStrength`. A × button takes the LoRA off.
- `OtherRow` (`LoraRow.tsx:38-49`): a + button or a double-click puts the LoRA on. A dot marks a "new" file, meaning
  its mtime is less than 14 days old (`order.ts:5,19`).
- Strength edits: `setStrength` updates the stack on every change. On commit, `rememberStrength` saves the strength to
  the LoRA module 500 ms after the last change (`library/LoraLibrary.tsx:64-67`; `loras.ts:25-29`), through
  `PATCH /api/loras/user?id=…`.
- Putting a LoRA on uses `l.strength ?? l.defaultStrength` (the remembered strength, else the file's
  recommended weight, else 1.0) (`LoraLibrary.tsx:102-103`; `loras/routes.py:32-33`).

### 2.1.6 Status line: job line / seed line — `run/Dock.tsx`, `run/Queue.tsx`, `run/Seed.tsx`

- `Dock` (`Dock.tsx:8-17`) holds the `PromptBox`, then a status `div` containing `<Queue fallback={<SeedLine/>}/>`.
- `Queue` (`Queue.tsx:17-71`) uses `queueView` (`run/jobs.ts:12-22`: `running`, `waiting`, `failed`) over the `jobs` store, filtered to
  `tool === 'generate-image'`. It shows, in order:
  - a running job with its text, progress and Cancel (`job.cancel`); a continue job is labelled first, "Continue · +5.1 s ·
    scene 10.2 s" (`continueLabel`, `run/jobs.ts:45-51`, drawn at `Queue.tsx:57`, `data-region="continue"`);
  - the waiting count with Clear (`job.clear` with the lane);
  - the latest terminal job if it failed, with Dismiss (`job.dismiss`);
  - a 4-second "Done · N images in t" after a job finishes (lines 25-42).
  When none of these applies, it renders `fallback` (line 52).
- `SeedLine` (`Seed.tsx:14-40`) takes the newest job of this tool whose `summary.seeds` is non-empty, and the model
  whose id equals `summary.model_id`. If either is missing it renders nothing. It shows each seed as a button.
  Clicking one sets that model's seed to `{mode:'fixed', value}` through `withAdvanced`. The button that equals the
  current fixed seed is `aria-pressed` and styled `seedKept`. "Random" sets `{mode:'random'}` again. The seeds come
  from the job record's summary (built in `gi/build.py:275-280`). Nothing is stored for this line.

### 2.1.7 Settings card — `web/gi/Card.tsx`

The card is registered through `Card(title="Generate Image", order=880, state=routes.card)` (`gi/manifest.py:47`). The
web panel is `web/gi/Card.tsx`, found by the shell's glob (`web/src/shell/registry.ts:9`).

- It holds the default models "Text to image" and "Reference to image", each a `ModelPicker` with "Not set" on top
  (`Card.tsx:21-28,55-58`).
- For the current model it holds Seed (Random/Fixed plus a value) and Guidance, the latter only when the model has a
  guidance key (`Card.tsx:78-92`). For a video model it holds **Seconds** between them (`Card.tsx:86`): a number input
  (`Seconds`, `:30-45`) that shows `secondsOf(video, frames)` with the frame count as hover text and, on blur or Enter,
  stores `toFrames(video, typed)`, the first frame count on the model's lattice that shows at least those seconds
  (`video.ts:35,46-50`), in `advancedByModel[model].frames`. With a clip in box 1 on a model that continues one, the
  field is the seconds the step adds: it stops at the longest step (`stepMax`, `video.ts:113`: the lattice's maximum less
  `overlap − 1` frames) and a label "+N s" beside it (`stepSeconds`, `:116`: `(frames − 1) / fps`, one decimal;
  `data-region="step"`, `Card.tsx:46`). The text encoder and the detail are on the sheet, not on the card.
- It offers "Reset to model defaults" (`resetAdvanced`), shown when `!isDefault(a, model)`. `isDefault` compares steps,
  guidance, seed and frames; the text encoder and the detail do not count, and a reset keeps a chosen encoder and detail
  (`edits.ts:33-49`).
- The server summary line is "Seed N" for a fixed seed, else "Random seed" (`gi/routes.py:115-121`).

---

## 2.2 The draft model

### 2.2.1 Saved vs session fields

`gi/routes.py:25-29`:

```python
DRAFT, DEFAULTS = "draft", "defaults"
SESSION_FIELDS = ("prompt", "draft", "references", "selected")
SAVED_FIELDS = ("model", "lorasByModel", "aspect", "size", "images", "advancedByModel")
_session: dict[Path, dict[str, Any]] = {}
```

- **Saved** fields live in the module doc `draft` (`ctx.doc(DRAFT, {})`), the module's `draft.json`. They are the
  saved customization:
  - `model`;
  - `lorasByModel` (`{modelId: [{id, strength}]}`);
  - `aspect`;
  - `size` (megapixels);
  - `images` (count);
  - `advancedByModel` (`{modelId: {steps, guidance, seed}}`, and for a clip model `frames`, `text_encoder` and, for a
    model that announces one, `detail`).
  Shapes are in `web/gi/types.ts:52-71`.
- **Session** fields live in `_session[ctx.data_dir]`, reached through `session_part(ctx)` (`routes.py:42-43`). They
  are memory only:
  - `prompt` (the prompt box);
  - `draft` (the assistant's text);
  - `references` (`[{id, w, h}]`; a box may also carry `cutout: true`, and box 1 a clip, `{id, w, h, kind: "clip",
    seconds}`);
  - `selected` (the highlighted LoRA id).
- The module also keeps three keys of its own in the same dict. None is in `SESSION_FIELDS`, so `PUT /draft` cannot set
  them:
  - `last_seeds = {"model", "seeds"}`, written by `build.on_submitted` (`gi/build.py:229-235`) when the module hears
    `job.submitted` for one of its image jobs whose `by` is the module's own id or `"screen"`; a job another module
    submits leaves it as it is (`tests/engine/test_generate_seeds.py`). Before the `by` field the builder wrote it
    itself;
  - `last_clip`, the newest clip this screen made, and `clip_models`, the model that made each of the last 50 clips
    (`MEMORY`, `gi/chain.py:36`), written by `chain.on_job_finished` (`:202-219`) when a Generate job ends `done` with
    clips among its outputs (§2.10.7).
- `on_session_ended` drops the whole session dict (`routes.py:46-48`). The session event comes from the core
  (`hub/core/runtime.py:106-109`).
- `settle(ctx)`, called from `start` (`gi/manifest.py:20-23`), rewrites `draft.json` so that it keeps only
  `SAVED_FIELDS` (`routes.py:32-39`). This removes whatever an older hub stored there (a prompt, references).
  `test_an_older_draft_with_a_prompt_is_settled_at_start` pins this behaviour.

### 2.2.2 GET / PUT `/api/generate-image/draft`

- `get_draft` (`routes.py:134-136`) returns `{**saved, **session_part(ctx)}`, so it includes `last_seeds` when a
  render ran in this session.
- `put_draft` (`routes.py:139-151`) is a **merge**:
  1. The body must be a JSON object (`_body`, lines 124-131).
  2. A detail the window sends (`advancedByModel[model].detail`, new or changed) is checked first (`_check_detail`,
     `:154-175`): the model must announce one (`<label> has no detail setting`) and the value must be one of its
     choices (`Detail must be A, B or C for <label>`); the engine's own line (field `engine`) when the catalog cannot be
     read. A value already saved passes unchecked, and the job builder ignores a stale one. Nothing is stored
     before this passes (`tests/engine/test_omni_refs.py::test_put_refuses_a_detail_the_model_does_not_announce`).
  3. Only the keys in `SESSION_FIELDS` are merged into the session dict.
  4. The saved doc is read, filtered to `SAVED_FIELDS`, updated with the body's `SAVED_FIELDS` keys, and replaced.
  5. It publishes `ctx.bus.publish("changed", "draft", {})`.
  6. It returns the whole draft.
  Keys the body does not name keep their stored value, so a window and the tool server do not overwrite each other's
  fields. Unknown keys are dropped silently.
- The body limit is 262,144 bytes (`gi/manifest.py:41`).

### 2.2.3 The `generate-image.draft` event

- `ctx.bus` is a `ModuleBus` that prefixes the lane and type with `<module id>.` (`hub/core/context.py:55-65`). So
  `publish("changed", "draft", {})` goes out as type `generate-image.draft` on lane `generate-image.changed`.
- The module declares `lanes=("changed",)` (`gi/manifest.py:33`). The runtime registers each module lane for the
  roles `("workspace", *mod.screens)` (`hub/core/runtime.py:123-124`). Generate Image declares no `screens`, so only
  `workspace` lines receive it (default lanes: `hub/core/bus.py:104`, `hub/core/messages.py:18-22`).
- The server publishes it from:
  - `put_draft` (`routes.py:150`);
  - `on_chat_cleared` (`routes.py:58`);
  - `random_seed` (`routes.py:187`);
  - `screen.apply` (`screen.py:256`);
  - `chain.continue_clip` (`chain.py:158`), so an open window redraws box 1 with the clip (the clip does not move).
- The web subscribes with `bus.on('generate-image.draft', () => { void loadDraft() })` (`web/gi/draft.ts:94`).

### 2.2.4 Web store and save path — `web/gi/draft.ts`

- The store is `draft` (initial value `EMPTY_DRAFT`, `edits.ts:5-8`), plus `draftReady`.
- `edit(fn)` (`draft.ts:22-33`) applies a pure edit. If `references` changed (by identity), it also applies
  `followDefaults` (§2.6.4). Every key whose value changed identity is added to `changed`, and `save` is scheduled
  `SAVE_MS = 1000` ms after the last edit.
- `save()` (`draft.ts:37-45`):
  1. Returns if `changed` is empty.
  2. If the bus link is not `on`, calls `retry()` and returns.
  3. Otherwise snapshots the keys, clears `changed`, and sends only those fields with `PUT /draft`, chained after the
     previous save (`saving`).
  4. On failure, the keys are added back to `changed` and `retry()` re-arms the 1 s timer.
- **Why the retry exists** (`draft.ts:47-48`): `loadDraft` keeps this window's value for every key still in
  `changed`. A key stranded there would hide every later value the tool server sets for it, so the bar would freeze.
  `web/tests/e2e/generate-freeze.spec.ts` guards this case.
- `loadDraft()` (`draft.ts:67-75`) does `normalizeDraft(await api.draft())`. It then sets the store to the server
  value, except for keys in `changed`, which keep the current local value. It always sets `draftReady = true`.
  `normalizeDraft` (`edits.ts:11-21`) merges over `EMPTY_DRAFT`, coerces `references` to an array, and clamps
  `images` to 1..6.
- `settled()` resolves once every save sent so far has been answered (`draft.ts:55`).
- On `welcome` (each bus connect, `draft.ts:80-90`):
  - **New session** (the session id differs from the last one seen): the timer is cleared, `changed` is emptied, and
    `prompt`, `draft`, `references` and `selected` are reset locally, so nothing of the old session is sent back.
  - **Same session**: unsaved edits are flushed (`save()`).
  - Either way, `loadDraft()` follows.
  `web/tests/e2e/generate.spec.ts` "a reconnect into a new session drops the prompt and the references the window
  kept" covers this.

### 2.2.5 Pure edits — `web/gi/edits.ts`

| Function | Effect |
|---|---|
| `stackOf(d)` | the current model's `lorasByModel` entry or a stable empty list (line 26) |
| `advancedOf(d, m)` | `advancedByModel[m.id]` or `{steps: m.defaults.steps, guidance: m.defaults.guidance, seed:{mode:'random'}}` (28-30) |
| `isDefault` | steps and guidance equal the defaults and the seed is random (32-34) |
| `withAdvanced` / `resetAdvanced` | patch / delete the per-model Advanced entry (36-44) |
| `withModel(d, m)` | sets `model`, clears `selected` (47); the stack and Advanced are per model, so they "come back" |
| `toggleLora` | appends `{id, strength}` and selects it, or removes it (55-59); never touches the prompt |
| `setStrength` | (61-62) |
| `placeRef(d, i, slot)` / `removeRef` | replace or append; removal shifts later boxes left (65-73) |
| `defaultModel` / `followDefaults` | §2.6.4 (76-83) |

### 2.2.6 New chat (`chat.cleared`)

- Server side: `assistant` emits the core event `chat.cleared` (`hub/modules/assistant/chat.py:51`;
  `hub/modules/assistant/routes.py:94`). Generate Image listens (`gi/manifest.py:48`). `on_chat_cleared`
  (`routes.py:51-58`) does the following:
  - If the session holds neither a prompt nor a draft, it does nothing and publishes nothing.
  - Otherwise it sets `prompt` and `draft` to `""` and publishes `generate-image.draft`.
  - References and `selected` are kept, and the disk is not written.
  - `test_new_chat_empties_the_prompt_box_and_the_draft_and_keeps_the_references` pins all of this.
- Web side: `clearWords()` (`draft.ts:60-64`) removes `prompt` and `draft` from `changed` and empties both locally at
  once, so a pending save cannot write the old words back. `newChat()` then waits for `settled()` before it sends the
  DELETE (`assistant.ts:42-45`). `web/tests/e2e/chat.spec.ts` "the chat follows assistant.chat; New chat empties the
  chat, the prompt box and the draft article" covers this.

### 2.2.7 Other draft routes

- `POST /seed/random` (`routes.py:178-188`) is "Seed back to random". If `advancedByModel[model]` exists, its seed is
  set to `{mode:"random"}` and the doc is replaced. It always publishes `generate-image.draft`. The web manifest
  exposes it to Media as `randomSeed` (`web/gi/manifest.ts:9`; used at `web/src/screens/media/Bar.tsx:43-44`).
- `GET/PUT /defaults` (`routes.py:191-214`) is the doc `defaults` with shape `{text, refs}` (null = not set).
  - PUT accepts only those keys.
  - Every non-null value must be the id of a model in `models.present(catalog)`, else the error is
    `No model "<id>" in the model folders`.
  - When the engine cannot list its models, the error is the engine's own line (field `engine`).

---

## 2.3 Rendering: from a press to engine tasks

### 2.3.1 The press — `web/gi/useGenerate.ts`, `web/gi/blocking.ts`

- `useGenerate(d, model)` (`useGenerate.ts:19-37`) computes `reason`:
  - `EMPTY_DRAFT_TEXT = 'The draft is empty'` when `d.draft.trim()` is empty;
  - else `blockingReason({linkOn, engineOffline, model, prompt: d.draft, refCount, uploading, waiting, draft: d})`
    (`useGenerate.ts:26-30`; `draft` carries the boxes and the frames for the continue lines).
  `engineOffline` is true when every engine in presence is `down`. `waiting` counts this tool's queued jobs.
- `go()` toasts the reason if there is one. Otherwise it sends the bus request
  `job.submit {tool:'generate-image', kind:'image', params: buildJob(draft.get(), model)}` and toasts a refusal's text.
- `blockingReason` (`blocking.ts:32-51`; the video branch is `:41-47`) returns the first match of:
  1. `Reconnecting…`
  2. `Engine is offline`
  3. `Choose a model`
  4. `Write a prompt`
  5. `Prompt is too long (n / 4,000)`
  5a. The continue lines, only when the press carries the draft (`clipReason`, `blocking.ts:24-30`, taken at `:39-40`). A
     clip in any box but box 1 gives `A continued clip takes only box 1` (`CLIP_ONLY_TEXT`, `:9`). With a clip in box 1:
     `<label> cannot continue a clip` (the catalog does not say `continues`, `continuesOf`, `video.ts:110`), the same
     only-box-1 line when another box is filled, and `Each step is at most N s` when the Seconds value is over
     `stepMax` (`video.ts:113`). The hub refuses the same lines (§2.10.7).
  6. `Add a reference image` (no refs and the model lacks mode `new`; for a video model, when its references need at
     least one, `refs.min > 0`)
  7. `<label> takes no references` (a video model that takes none)
  8. `Too many references for this model (k of cap)`
  9. `Waiting for the image to upload`
  10. `Queue is full` (`waiting >= QUEUE_MAX = 10`, `types.ts:76`)
- **Media's Generate button** uses `web/gi/queue.ts:12-20`. It reads `GET /draft` and `GET /models` fresh. If the
  draft is empty it returns `The draft is empty`. It checks `blockingReason` with `linkOn: true, engineOffline: false,
  uploading: 0, waiting: 0, draft: d`, then submits `buildJob(d, model)`. The web manifest exposes this as `queue`
  (`web/gi/manifest.ts:8`; `web/src/screens/media/Bar.tsx:15,30`). The core accepts `job.submit` from `workspace` and
  `media` lines (`hub/core/routes.py:49-50`).

### 2.3.2 The payload — `web/gi/job.ts:buildJob(d, model, text = d.draft)`

`job.ts:57-79` builds (the doc comment at `:52-56` names the video rules, the clip in box 1 and the cut-out):

| key | value |
|---|---|
| `tool` | `'generate-image'` |
| `model` | `model.id` |
| `mode` | `jobMode(d)`: `'refs'` when `d.references.length > 0`, else `'new'` (line 21); `'new'` for a video model that takes no references. A continue has a clip in box 1, so `'refs'` |
| `prompt` | `text`, by default the assistant's `draft` |
| `loras` | `stackOf(d)` with strengths rounded to 2 decimals; entries at 0.00 are left out |
| `width`, `height` | `canvasOf(d)`; `clipSize(d, model)` for a video model (`video.ts:96-97`); the clip's own `w` and `h` when box 1 holds a clip (`job.ts:60-61`) |
| `images` | `d.images`; 1 for a video model |
| `steps` | `advancedOf(d, model).steps` |
| `guidance` | `null` when `model.guidanceKey === null`, else `adv.guidance` |
| `seed` | `{mode:'fixed', value}` or `{mode:'random'}` |
| `references` | `d.references.map(r => r.id)`, only when there are references (and, for a video model, only when it takes some); `[clip.id]` alone when box 1 holds a clip (`job.ts:77`) |
| `cutout` | one boolean per reference, in box order (`d.references.map(r => r.cutout === true)`), sent only when the model's boxes are identities, no clip is in box 1 and at least one box is cut out (`job.ts:78`) |
| `frames` | video model only: `framesOf(d, model)` (`video.ts:53-54`) |

The MCP `generate_image` builds the same params on the server (`gi/tools.py:50-78`); §2.4.4 covers the differences.

### 2.3.3 Canvas math

- Web: `canvasSize(ratio, mp)` (`job.ts:13-16`) computes `p = mp*1048576`,
  `width = round16(sqrt(p*ratio))` and `height = round16(sqrt(p/ratio))`, where `round16 = Math.round(x/16)*16`.
- Auto: `autoRatio` uses reference 1's `w/h`, clamped to 0.4..2.5, or 1 with no reference or zero size
  (`job.ts:24-27`). `canvasOf` picks the auto ratio or `RATIOS[aspect]` (`job.ts:29-31`).
- Server mirror: `gi/screen.py:53-77`. `_round16` is `floor(x/16+0.5)*16`. `AUTO_RATIO = (0.4, 2.5)`.
  `MEGAPIXELS = (1, 1.5, 2, 4)`. `ASPECTS` holds the seven ratios. `canvas(aspect, mp, references, model)` uses
  `ASPECTS.get(aspect) or auto_ratio(references)`. For a video model it returns the offered tier's size instead
  (§2.10.4).
- The model's budget (Stage 9 step 5): a catalog entry may carry `budget`, the most pixels its engine takes in one
  task (upstream refuses an API task above it: the definition's `resolution_budget`, else 1920×1088 = 2,088,960; the
  fork publishes none). A canvas above it becomes the largest canvas of that shape within it, each side floored to 16
  (`models.within`, called by `screen.canvas`; web `canvasSize(ratio, mp, budget)`), and the size menu offers only the
  sizes whose nominal pixels (`mp × 1,048,576`) are within it, the smallest always (web `sizesFor`): Klein, Qwen 2.1 and
  Z-Image on upstream offer 1 and 1.5 MP (2 MP at 1:1 would be 1456², 2.12 M); Krea 2 (2048×2048) offers all four,
  its non-square 4 MP canvases shrunk. A size saved for another model still shows on the button; its canvas shrinks.
- Server block rounding: `build.image_job` validates width and height as integers from 256 to 4096 and floors each to
  a multiple of the model's `block` (`width // block * block`, `gi/build.py:247-248`). `block` comes from the engine
  catalog entry. `test_guidance_key_and_block_rounding` pins this.
- `web/tests/unit/job.test.ts` pins the canvas table for each aspect, including "1200 × 800 at 1 MP is 1248 × 832".

### 2.3.4 `build.image_job(params, ctx)` — `gi/build.py:214-226`, `picture_job` `:238-281`

`image_job` finds the model (a model the engine has but the Hub cannot drive, `why_not`, is refused with that line; `Choose
a model` when it is missing or has status `missing`), builds its `ui_model`, checks the `cutout` list (`_cutout`; a true on
a model whose boxes are not identities is refused with `<label> cuts out no backgrounds`, and a mix of on and off on a
model whose engine has one switch for every box, the catalog's `cutout` "all", with `Cut-out is on or off for every box on
<label>`), refuses a clip among the references of a picture model (`<label> cannot continue a clip`, `:224-225`),
and hands over to `clip_job` when the model is a clip model (`:226`); §2.10.5 and §2.10.7 describe that branch. The list
below is the picture path.

The runtime registers it as kind `generate-image.image`, called as `build(params, ctx)`
(`hub/core/runtime.py:127-128`). `JobBook.submit` deep-copies the params, calls the builder, and refuses with "Engine
is offline" when no lane of `plan.lane_kind` exists, or "Queue is full" at `max_waiting` (`hub/core/jobs.py:67-94`).

Checks, in order, each a single `Invalid(field, text)` line:

1. `model`: `models.find(models.cached(), p["model"])`. The cache is the last catalog fetched (`models.py:39-49`), so
   the catalog must have been loaded once (`gi/manifest.py:start` warms it). A missing model, or one with status
   `missing`, gives `Choose a model`.
2. `mode` must be `new` or `refs` (`Choose New or References`) and must be one of `ui_model(...)["modes"]`. Otherwise
   the text is `MODE_TEXT` (`build.py:19`): "{label} needs a reference image" or "{label} can't use reference images".
3. `prompt` (`_prompt`, `:82-88`): a string that is not blank (`Write a prompt`) and at most `MAX_PROMPT = 4000`
   characters (`Prompt is too long (n / 4,000)`).
4. `width` and `height`: integers from 256 to 4096 (`Choose a size`), floored to `block`; above the model's `budget`,
   `<w>×<h> is more than <label> makes (<budget> pixels at most)` (`_within`).
5. `images`: `COUNT = (1, 6)`.
6. `steps`: `None` means `ui.defaults.steps`, else an integer within `STEPS = (1, 100)`. A model whose steps are locked
   (the catalog's `lock_steps`: its definition's `lock_inference_steps`, or the adapter's own lock, Qwen Image 2.1 Turbo
   at 8 on upstream) runs its own steps; another value is `<label> runs <n> steps` (`_steps`, `models.check_steps`),
   and the card refuses it the same way (`screen._advanced`); the web shows the steps with the control off.
7. `guidance`: only if the model has a `guidanceKey`. `None` means `ui.defaults.guidance`, else a number within
   `GUIDANCE = (0, 50)`. Without a guidance key it is ignored.
8. `references` (`_images`, `:49-60`):
   - `new` mode uses `[]` and `video_prompt_type ""`.
   - `refs` mode needs at least one reference, and no more than `ui.refCap`
     (`Too many references for this model (k of cap)`).
   - Each id is resolved with `ctx.files.resolve` to an existing absolute file (`An image is missing; add it again`).
   - The flags are `models.ref_flags(model) or "I"`.
9. `loras` (`_loras`, `:63-79`):
   - A list of at most `MAX_LORAS = 50`.
   - Each strength must be within `STRENGTH = (0, 2)` and is rounded to 2 decimals.
   - Entries at 0 are skipped.
   - The id must resolve with `models.lora_name` (`LoRA "<id>" was not found for this model`).
10. `seed` (`_seeds`, `:31-36`, through the core's `api.seeds` and `api.seed_value`, `hub/core/checks.py:34-50`):
    - `random` draws `secrets.randbelow(SEED_MAX+1)` once per image (`SEED_MAX = 999_999_999`).
    - `fixed` validates `value` and gives `[(first+k) % (SEED_MAX+1) for k in range(count)]`.

The whole numbers and numbers are checked by `api.whole` and `api.number` (`hub/core/checks.py:18-33`), which the module
imports from `hub.core.api`; a bool is never a number and each refusal names its field.

Each task is `base` plus its own `seed` (`build.py:262-281`). `base` holds:

```
model_type, prompt, resolution "WxH", batch_size 1, image_mode 1, multi_prompts_gen_type "FG",
video_prompt_type <flags>, remove_background_images_ref 0,
activated_loras [engine names], loras_multipliers "s1 s2 …" (format :g),
num_inference_steps (when not None), <guidanceKey>: guidance (when set), image_refs [abs paths] (when refs)
```

The `JobPlan` is `JobPlan("image", model["id"], tasks, summary)`. `summary` (`build.py:275-280`) holds:

```
prompt, model (label), model_id, mode, width, height, count, steps, guidance, seeds,
loras: [{id, name (file basename without extension), strength}]
```

The job record publishes the summary (`hub/core/jobs.py:168-183`). The default card title is
`"{n} {noun} · {summary.model}"` unless the summary has a `title` (`jobs.py:173`). The web `SeedLine` reads
`summary.seeds` and `summary.model_id`.

Side effect, not in the builder: the module listens to `job.submitted` and `build.on_submitted` (`:229-235`) writes
`routes.session_part(ctx)["last_seeds"] = {"model": summary["model_id"], "seeds": [...]}` (memory only) for a job of kind
`generate-image.image` whose `by` is `"generate-image"` or `"screen"`. Both the window's press and the MCP `generate_image`
are such jobs, so both set it; a job another module submits does not (`tests/engine/test_generate_seeds.py`).

### 2.3.5 Worker translate — `hub/worker/wan2gp.py`

- `FORCED_CONFIG` lives in `hub/worker/wgpconfig.py:18-20` (the worker re-exports it, `wan2gp.py:24,32`). `seed_config`
  applies it when it writes the engine config (`wgpconfig.py:76`, called at `wan2gp.py:137`), and the worker applies it again at
  runtime (`self.w.server_config.update(FORCED_CONFIG)`, `wan2gp.py:148`). It sets:
  - `image_output_codec "png"`;
  - `metadata_type "none"`;
  - `enhancer_enabled 0`, `enhancer_mode 1`;
  - `enabled_plugins []`;
  - `save_queue_if_crash 0`;
  - `embed_source_images False`;
  - `video_container "mp4"`: a clip is an MP4 whatever the engine config says.
  `DROPPED_CONFIG` (`services`, `llm_engines`, `enabled_plugins`, `installed_remote_plugins`, `wgpconfig.py:17`) and
  every `notification_*` key are not carried over (`:73-75`). The memory profile picked in Settings is the one other value written
  there (`PROFILE_KEYS`, `:24`, `:77-78`; part 5).
- `FORCED_TASK` is laid over every task and lives in each adapter (`hub/worker/adapters/fork.py:24-25`,
  `upstream.py:22-23`; the engine key families are named only there, part 5, 5.2.3): `prompt_enhancer ""`,
  `negative_prompt ""`, `alt_prompt ""` and `output_filename "{date}-{seed}"`. The default file name of the engine
  contains the prompt, which is why the name is forced. `FORCED_VIDEO` (the fork's `audio_prompt_type ""`,
  `MMAudio_setting 0`; upstream's `audio_prompt_type ""`, `postprocess_audio ""`) is laid over a task whose
  `image_mode` is 0, a clip: it keeps the sound its model makes and never gets a soundtrack or a second audio model.
- `translate(task, factory)` is each adapter's own function, and `Engine._params` (`wan2gp.py:166-172`) calls it with
  the model's cached factory settings:
  - `upstream` (`upstream.py:47-50`): `{**task, **FORCED_TASK, **extra}`, where `extra` is `FORCED_VIDEO` for
    `image_mode` 0, else `{}`; `factory` is not used.
  - `fork`, the worker's "legacy" flavour (`fork.py:45-55`): the model's factory defaults go underneath, then the
    task, then `FORCED_TASK` and `extra`. `"FG"` becomes `2`, and `activated_loras` become base names, because the
    fork finds LoRAs by file name in a flat folder.
  - `Engine._params` caches factory settings per model (`wan2gp.py:166-172`).
- Tests:
  - `tests/engine/test_build.py::test_flavour_translation_keeps_the_forced_values`;
  - `tests/engine/test_worker.py::test_one_prompt_plain_file_nothing_added`;
  - `test_loras_by_flavour`, `test_legacy_lora_names_become_file_names`.

### 2.3.6 Reference modes and caps (web)

- **Mode** is never a setting or a field. Mode `refs` is used if and only if there are references (`job.ts:20-21`;
  `types.ts:2`).
- **refCap** comes from `models.ui_model` (§2.6.2). The web uses `refModel(model) ?? model` to decide which model
  references go to: a video model itself, else the refs default when one is set (`modelList.ts:42-43`). This applies in:
  - `Taskbar.tsx:52`;
  - `inputs.ts:81,107,138` (`taker`, `:81` and `:107`);
  - `sockets.ts:52` (`taker`: the video model, else the refs default, else the model).
  A video model keeps its own boxes, so a reference landing in them does not switch the draft to the refs default
  (`followDefaults` returns the draft unchanged when its model is a video model, `edits.ts:94-95`).
- **Sockets**: the server declares `SocketGroup("reference", "Reference", ("image",), 6)` (`gi/manifest.py:34`). The
  web declares `reference_1..reference_{refCap}`, each with a `filled` flag, `primary: 'reference'` when there is any
  socket, and `mode: jobMode(d)` (`delivery.ts:8-13`); a socket's label is `boxLabel(model, i)`, so Media sees "Start
  frame" or "Identity n" for a video model (`delivery.ts:11`). `planDelivery` (`delivery.ts:19-37`):
  - a group send fills free boxes only and refuses the rest with `full`;
  - a specific socket replaces that box (clamped so there is never a gap) and refuses extra items with `one_only`;
  - an unknown socket is refused with `missing`;
  - while box 1 holds a clip, every item is refused with reason `clip` and `A continued clip takes only box 1`
    (`delivery.ts:21`).
  `useSockets` answers each `deliver` with a `bus.receipt` (`sockets.ts:17-44,47-57`). On an identity model a picture
  outside 1:4 to 4:1 is refused with reason `shape` and `<label> takes pictures between 1:4 and 4:1`
  (`fitsBox` in `receive`, `sockets.ts:33`; `shapeNote`, `video.ts:89`).
- **Local files and Media drags** (`inputs.ts`):
  - Accepted types are PNG, JPEG and WebP up to 25 MB (`TYPES`, `MAX_BYTES`, `:17-18`).
  - `dropPlan(target, n, filled, cap)` puts the first item at `min(target, filled)` and the rest in free indexes up to
    `cap` (`:43-50`). Refused extras give the note "N not added: references are full".
  - While box 1 holds a clip, `addFiles` and `addMedia` place nothing and set the note `A continued clip takes only
    box 1` (`clipRefuses`, `:57-62`, taken at `:77` and `:105`).
  - On an identity model a picture whose long side is over four times its short side is not placed: the note is
    `<label> takes pictures between 1:4 and 4:1` (`fitsBox`, `:65-70`; `inShape`, `video.ts:86`; an unknown size
    passes and is left to the server). For a dropped file the size is read before the upload, so a refused file is never
    uploaded (`:88-92`).
  - Uploads go to `POST /api/upload`; Media items are checked with `POST /api/media/check` (`api.ts:24-26`).
  - The `uploading` counter blocks Generate while it is non-zero.
- **Aspect auto** follows reference 1's stored `w/h` (§2.3.3). A reference slot is `{id, w, h}`; the size comes from
  `imageSize()` decoding the image (`inputs.ts:33-38`).

---

## 2.4 MCP surface

The core publishes every module's declarations as tools (`hub/core/features.py:tools_of`, lines 93-98):

- A `Screen` becomes `get_<id>_settings` and `set_<id>_settings`, with the id's `-` replaced by `_` (lines 65-79).
- A `Listing` becomes `list_<name>`.
- An `Action` is published under its own name.

Generate Image declares these in `gi/manifest.py:50-52` from `gi/tools.py:81,89-92`. The resulting tools are, in
order: `get_generate_image_settings`, `set_generate_image_settings`, `list_image_models`, `list_characters`,
`generate_image`. The LoRA module adds `list_loras` (`loras/tools.py:17-18`; `loras/manifest.py:29`).

### 2.4.1 `screen.SETTINGS` — `gi/screen.py:30-45`

| name | kind | bounds / choices | label (`text`) |
|---|---|---|---|
| `draft` | text | `hi=MAX_PROMPT` (4000) | The assistant's draft prompt, shown beside the chat |
| `model` | choice | none (live list) | Id of the image model, as list_image_models lists it |
| `steps` | integer | 1..100 | Steps the model runs |
| `guidance` | number | 0..50 | Guidance scale, for a model that has one |
| `megapixels` | number | choices 1, 1.5, 2, 4 | Megapixels of the picture |
| `aspect` | choice | auto, 1:1, 4:3, 3:4, 3:2, 2:3, 16:9, 9:16 | Shape of the picture; auto is reference 1's shape, else 1:1 |
| `count` | integer | 1..6 | Number of pictures made |
| `seed` | seed | 0..999,999,999 | Seed of the first picture |
| `loras` | loras | strength 0..2 | Active LoRAs of the model: id (as list_loras lists it) and strength |
| `references` | names | `hi=3` | Reference pictures 1-3 by character name, as list_characters lists them, or last_clip alone to continue that clip; [] empties them |

The helper sets that follow from it (`screen.py:46-50`):

- `ADVANCED = ("steps","guidance","seed")`: these are kept per model. A clip's length (`frames`), text encoder
  (`text_encoder`) and reference detail (`detail`) are kept in the same per-model entry, but no setting names them: the
  card and the sheet alone write them, so the tool schema is the one the picture screen had (`screen.py:47-48`;
  `tests/engine/test_omni_refs.py::test_detail_is_no_tool_setting`). The `references` text is the only description that
  changed with Stage 6 (`tests/engine/test_continue_route.py::test_the_settings_text_and_the_six_tools_stay`).
- `SESSION = {"draft","references"}`.
- `SAVED` = every other setting name.

How a kind becomes JSON Schema (`hub/core/features.py:36-62`):

- `text` gives `maxLength`.
- `number`/`integer` give min and max, and `choices` gives `enum`.
- `loras` gives an array of `{id, strength, file(readOnly)}`.
- `names` gives an array with `maxItems` of strings 1-120 characters long.
- `seed` gives a string whose `maxLength` is the digit count of `hi`, with the description suffix ": random, or a
  whole number from 0 to 999999999".

The set schema has `additionalProperties: false` and no `required` (`features.py:75-76`). The registry refuses a
setting with an unknown kind, choices its kind cannot take, a `seed`/`loras` setting without `lo < hi`, or a `names`
setting without `hi >= 1` (`hub/core/registry.py:55-68,104-113`).

### 2.4.2 `get_generate_image_settings` → `screen.view`

`tools.read_settings` (`tools.py:39-42`) calls `screen.view(ctx, cat, pick_model(cat, read(ctx), None))`.

- `screen.read` (`screen.py:108-115`) normalizes the saved doc: an invalid `aspect` becomes `auto`, an invalid `size`
  becomes 1, an invalid `images` becomes 1.
- `pick_model` (`screen.py:128-135`) takes the requested model if it is usable, else the screen's model, else the
  first model of `models.present`. With no usable model it raises `No image model is in the model folders`.

`view()` (`screen.py:164-190`) returns:

| key | source |
|---|---|
| `draft` | session `draft` or `""` |
| `model`, `model_name` | the picked model id and its label |
| `loras` | `stack(screen, model)`: entries above 0, rounded; each `{id, file (id minus the family prefix), strength}` |
| `steps` | `adv.steps or defaults.steps` |
| `guidance` | `adv.guidance` if numeric else the default; `None` when the model has no guidance key |
| `aspect`, `megapixels`, `width`, `height` | `width`/`height` from `canvas(aspect, size, session references, model)`, the same as a press would render; for a clip model the offered tier's size (§2.10.4) |
| `count` | saved `images`; 1 for a clip model (`screen.py:181`) |
| `frames`, `seconds` | clip model only: `clip_frames(screen, model)` and `seconds` rounded to two decimals (`screen.py:184-189`): `frames / fps`, or with a clip in box 1 the seconds the step adds, `(frames − 1) / fps` |
| `width`, `height` (a continue) | the clip's own size, `held.w` and `held.h` (`screen.py:188-189`; `chain.held`, `chain.py:56-60`), not the tier's |
| `seed` | `"random"` or the fixed value as text |
| `last_seeds` | `last_seeds(ctx, model)`: the seeds of the last render **of this model** in this session, else `[]` (`screen.py:193-196`) |
| `references` | `cast.labels(ctx)`: each box's file stem (§2.4.5) |
| `last_clip` | `chain.last_clip(ctx)` (`chain.py:63-65`): the id of the newest clip this screen made in this session, `""` when none (`screen.py:183`) |

### 2.4.3 `set_generate_image_settings` → `screen.apply`

`tools.write_settings` (`tools.py:45-47`) calls `screen.apply(ctx, catalog, changes)` after the core's schema check
(`hub/core/mcp.py:165`, `hub/core/schema.py:check`). The schema check alone produces messages such as
`count must be at most 6`, `megapixels must be one of: 1, 1.5, 2, 4`, `seed must be text`, and
`unknown argument prompt` (`tests/engine/test_generate_image.py:366-392`).

`apply()` rules (`screen.py:235-257`):

1. It picks the model with `pick_model(cat, read(ctx), changes.get("model"))`. If `model` was given and differs from
   the pick, it fails with `No model "<x>" can run; list_image_models names the ones that can`.
2. For `draft`, `_draft()` (`screen.py:223-232`) requires a string of at most 4000 characters, and at least one
   connected bus line with role `workspace` (`ctx.bus.presence()["screens"]["workspace"]`). Otherwise the error is
   `No Generate window is open`.
3. For a clip model, `_clip_refusals` (`screen.py:245-246,260-263`) refuses a `count` other than 1 with
   `<name> makes one clip at a time`, before anything is written.
   For `references`, the same presence check runs (`_draft(ctx, "")`), then `cast.resolve(...)` (the model's pictures
   are its role's, §2.10.2; the id of a clip alone puts that clip in box 1 of a model that continues one, §2.10.7).
4. If any `SAVED` setting is in `changes`, `_save()` runs (`screen.py:266-290`). It validates every value before it
   writes anything:
   - It pins `draft["model"]` to the picked model.
   - `aspect` must be `auto` or a key of `ASPECTS`.
   - `megapixels` must be in `MEGAPIXELS` and is stored as `size`.
   - `count` is stored as `images` (`_whole`); for a clip model it is not stored, the pictures' count stays
     (`screen.py:281-282`).
   - `steps`, `guidance` and `seed` go through `_advanced()` (`screen.py:199-220`). It starts from the model's entry,
     fills in model defaults where the entry is missing (the same shape the web writes), keeps a clip model's `frames`
     on the lattice and drops a `text_encoder` or a `detail` the model no longer lists (`models.drop_stale`,
     `models.py:128-133`; `:206-208`), and then:
     - `steps`: `_whole` within 1..100, or within the model's own `steps_range` when the catalog gives one (`:209`);
     - `guidance`: refused with `<label> has no guidance setting` when the model has none; otherwise rounded to one
       decimal;
     - `seed`: `_seed` accepts `"random"` or a digit string or int from 0 to 999,999,999.
   - `loras`: `_loras` (`screen.py:147-161`) needs a list of at most 50 entries of `{id, strength 0..2}`. Each id must
     resolve with `models.lora_name` (`No LoRA "<id>" in this model's folder`), and no id may appear twice
     (`A LoRA is listed twice`). Strengths are rounded to 2 decimals. The list replaces `lorasByModel[model]`.
   - It finishes with `doc.replace(draft)`.
5. The session `draft` and `references` are written only after `_save` has passed.
6. It always publishes `generate-image.draft`, then returns `view(...)`.

`test_set_settings_writes_advanced_only_when_it_touches_steps_guidance_or_seed` and
`test_set_takes_back_what_get_reported_with_one_value_changed` pin the partial-write behaviour.

### 2.4.4 `generate_image` — `gi/tools.py:50-78`

It takes no arguments (`NO_ARGS`).

1. It fails with `The draft is empty` when the session draft is blank.
2. It picks the model as `get` does (`pick_model(..., None)`).
3. It builds params from the saved screen:
   - `mode` is `"refs" if refs else "new"`;
   - `prompt` is the draft;
   - `loras` is `screen.stack(saved, model)`;
   - `width`/`height` come from `screen.canvas`;
   - `images` is the saved count;
   - `steps` is `adv.get("steps")`, and `None` falls back to the model default in `image_job`;
   - `guidance` is used only with a guidance key and a numeric value;
   - `seed` is fixed or random;
   - `references` lists the ids of the session boxes;
   - `cutout`, when the model's boxes are identities and a session box has its cut-out on: one boolean per box
     (`tools.py:74-75`), as the window's `buildJob`;
   - for a clip model, `images` is 1 and `frames` is `screen.clip_frames(saved, model)` (`tools.py:76-77`). A clip in
     box 1 is a continue: its id is in `references` and `frames` is the step (§2.10.7).
4. It submits `ctx.jobs.submit("image", params)`. `ModuleJobs` turns this into `generate-image.image`, `by` this
   module (`hub/core/context.py:72-78`).
5. It returns `{state}` at once and nothing else: a job never waits on the GPU's memory, so the state is `queued` or,
   as the lane takes it, `running`.

`test_generate_image_renders_the_draft_as_the_generate_button_does` pins that the result equals the web's payload.

### 2.4.5 Listings and characters — `gi/cast.py`

- `list_image_models` (`tools.py:31-36`) returns `{models:[{id, name, size (defaults.resolution or "1024x1024"),
  steps, loaded (id == catalog.resident)}]}` for `models.present(cat)`.
- `list_characters` returns `cast.listing(ctx)`: `[{name, notes?}]` from `ctx.files.characters()`
  (`cast.py:115-117`).
- `list_loras {model}` returns `{loras:[{id, name, triggers, default_strength}]}` (`loras/tools.py:9-14`).
- `cast.label(ref)` is the box id's file stem (`chars/Character 1.png` → `Character 1`; `clips/2026-10-13/101500-123.mp4` →
  `101500-123`) (`cast.py:26-29`).
- `cast.resolve(ctx, model, names)` (`cast.py:74-112`) checks each name in turn:
  - The value must be a list (`references must be a list of names`).
  - A name that is a clip's id (`chain.is_clip`, `chain.py:40-41`) is box 1 of a continue: `chain.box` checks the clip
    against the model and returns `{id, w, h, kind: "clip", seconds}` (`cast.py:93-94`, `chain.py:111-115`).
  - Else, if `ctx.files.character(name)` finds a character (any case), its picture is opened to read `{id, w, h}`
    (`_picture`, `:38-42`). The box keeps its cut-out flag (`cutout: true`) only when the same picture was in a current
    box with the flag on; a picture newly placed has none (`:90-92`).
  - Else, a current box whose label equals the name (casefold) is kept unchanged, with its flag. This is the "hand back
    what get reported" path; a clip among those boxes is checked again (`:95-96`).
  - Else the error is `No character "<name>"; list_characters names them`.
  - A clip among the result must be alone and stays where it is; more
    than one box gives `A continued clip takes only box 1` (`:99-102`).
  - The count may not exceed `min(BOXES=3, refCap)` (`cast.py:103-107`), else the error is `<label> takes no reference
    pictures` or `<label> takes N reference picture(s)`. For a clip model `refCap` is its role's: 1 for a start frame,
    the engine's cap clamped to 3 for identities, 0 when it takes none (§2.10.2).
  - On an identity model each box's picture must be within 1:4 and 4:1, said at set time (`shape`, `:59-62`, taken at
    `:108-111`); a box the window sent without a size is checked at build.
  - `[]` empties the boxes.
- `cast.character_name(ctx, item_id)` (`:45-48`) is the name of the character whose listed picture is `item_id`, else
  None: a Temp upload, a Drive picture or an older file of the Characters folder sharing a stem has none. The job builder
  uses it for an identity's name (§2.10.5). `cast.name_ok` (`:51-56`) refuses a name longer than `models.NAME_MAX` = 120
  and `cast.size` (`:65-71`) reads a picture's size from its header.
- Because the boxes are session state, nothing is written to disk
  (`test_references_by_name_write_nothing_on_disk`).

### 2.4.6 Errors

Tool functions raise `Invalid(field, text)` (`hub/core/api.py:22`). `McpEndpoint.call` returns
`{"content":[{"type":"text","text": e.text}], "isError": true}` for `Invalid`/`Refused`, and "Something went wrong in
the hub" for any other exception (`hub/core/mcp.py:161-170`). Engine failures are reduced to the engine's first line
by `models.reason` (`models.py:52-54`) through `tools._catalog` (`tools.py:23-28`).

### 2.4.7 What no tool can touch

- **The prompt box**: it is not a setting, and `SESSION_FIELDS["prompt"]` is written only by `PUT /draft` from a
  window and by `on_chat_cleared`. The generated set schema has no `prompt` property; passing one gives
  `unknown argument prompt`. Tests: `test_generated_tools_say_what_the_screen_has_and_nothing_about_when`
  (asserts `"prompt" not in props` and that no `push_draft` exists) and `test_no_tool_writes_the_owners_prompt_box`.
- **`selected`** (the LoRA highlight): "The selection is never touched from here" (`screen.py:9`).
- **Default models** (`defaults` doc) and the **weights panel**: only HTTP routes reach them.
- **LoRA remembered strengths** (`loras.json`): only `PATCH /api/loras/user` reaches them.
- No label may contain "when", "only", "if ", "should", "must", "never" or "always". The generated-tools test above
  enforces this (`test_generate_image.py:180-219`).

---

## 2.5 Characters in the Generate screen

- **Route**: `GET /api/generate-image/characters` (`gi/routes.py:217-230`) returns
  `{items:[{name, id, w, h, thumb}]}`. The size is read by opening each image in a thread; unreadable pictures are
  skipped. It never returns the notes. The MCP listing (`cast.listing`) returns names and notes.
- **Tab completion** (`compose/complete.ts`):
  - `characterList()` fetches the route fresh on every Tab (lines 14-15).
  - `matchesAt(text, caret, list)` takes the non-space word before the caret and returns the characters whose names
    start with it (case-insensitive), sorted by `localeCompare` with base sensitivity (lines 22-28).
  - `place()` swaps the word for the name plus one space, reusing a space that is already there, and puts the caret
    after that space (lines 32-36).
- **PromptBox flow**:
  - `completeOnTab` (`PromptBox.tsx:49-62`) ignores a selection range and drops the result if the text changed while
    the list loaded.
  - One match is placed at once (`put`). Several open the `picker` store.
  - In `pickerKey` (lines 30-45):
    - Tab/Shift+Tab and ArrowRight/ArrowLeft move the lit tile, wrapping.
    - Enter (no modifiers) places the lit tile.
    - Escape closes the tiles and stops propagation.
    - A lone modifier key keeps them open.
    - Any other key closes them and is typed.
  - Blur closes the tiles (line 121).
- **Picker** (`compose/Picker.tsx`) draws a `role="listbox"` of tiles with `aria-selected` on the lit one.
  `onMouseDown` prevents the default so the textarea keeps focus.
- **`put()`** (`PromptBox.tsx:18-24`) writes the new prompt with `edit`, restores focus and caret, then calls
  `addCharacter({id, w, h})`.
- **`addCharacter`** (`inputs.ts:132-140`):
  - If the picture is already in a box, that box flashes and nothing is added.
  - With no model the note is "Choose a model first".
  - If `refModel(model).refCap === 0`, the note is "This model takes no reference pictures".
  - Otherwise it runs `addMedia([...], d.references.length, model)`, which fills the first free box or notes "1 not
    added: references are full".
- **MCP side**: the `references` setting takes character names (§2.4.5).
- While box 1 holds a clip, `addCharacter` places nothing: `addMedia` refuses with `A continued clip takes only box 1`
  (§2.3.6).

---

## 2.6 Models

### 2.6.1 Catalog — `gi/models.py`

- `catalog(ctx, rescan=False)` calls `ctx.engine.query("models", rescan=rescan)` and stores the result in the module
  global `_last` (and the module's `Ctx` in `_ctx`, which `video()` reads for the tier setting). `cached()`
  returns `_last` (`models.py:39-49`).
- `start` warms the cache in a background task (`gi/manifest.py:15-26`), and `_panel` refreshes it after each weights
  query (`routes.py:79`).
- `present(cat)` keeps only models whose `status` is `available` or `partial` and that carry no `why_not` (a model the
  engine has but its adapter cannot drive, such as upstream's H3 control and Viggle models), sorted by (family, name,
  id), all lower-cased.
- `find(cat, id)`: the model with that id, else the one whose `was` holds it (the ids a model had on the engine line the
  Hub ran before, from the upstream adapter's facts file, R16 §3.1). `rename.adopt` brings the saved ids over once when a
  catalog of a renaming line first arrives (`models.catalog` calls it): the draft's model, its last picks, the keys of its
  per-model settings and the defaults take the new ids, and the draft records the line (`engine`, a saved field the
  window never writes; an entry the model already has under its new id is kept). Once per move, because upstream gives
  one fork id to another model: the fork's `minimax_h3_ref2va` was the pruned Omni, upstream's is the 33B; after the
  move an id saved is the line's own. Going back to the fork renames nothing but records the line, so the next move
  forward brings the ids saved on the fork over again. `put_draft` reads the saved draft after its awaits, so a move
  made meanwhile is not written over. A clip model is listed like any other model: `list_image_models` and `GET /models`
  carry it with no new field of their own (`ui_model` adds `kind` and `video`, §2.6.2).
- `GET /models` (`routes.py:61-68`) returns `[ui_model(m, caps) for m in present(cat)]`. With `?rescan=1` the engine
  rescans its folders. An engine error gives `503 {"code":"unavailable","text": <first line>}` (lines 71-73).
- Web: `loadModels(rescan)` (`modelList.ts:14-23`) is called with `rescan = true` on the first connection of the page
  (`GenerateImage.tsx:34-36`). It is also called without rescan when the model picker opens
  (`ModelPicker.tsx:38-40`), when a `settings` event arrives (`ModelPicker.tsx:17`), and from the Card. A sequence
  counter (`latest`) drops stale answers.
- If the draft's model is not in the list, the screen switches to the first listed model (`GenerateImage.tsx:39-43`).

### 2.6.2 `ui_model` — `models.py:180-199`

```
{id, label: name, family, kind: "video" | "image", video: <facts> | None,
 modes: modes(model), refCap: ref_cap(model, caps) if takes_refs(model) else 0,
 defaults: {steps: model.steps, guidance: model.guidance if key else None},
 guidanceKey: model.guidance_key, budget: models.budget(model), lockSteps: models.locked_steps(model) is not None}
```

For a picture model that is the whole answer. For a clip model (`video(model)` is not None, §2.10.2) `kind` is "video",
`video` holds the facts with the offered tiers and the clamped references, `modes` is `clip_modes`, `refCap` is the
role's cap, `defaults.steps` is the clip's steps and `guidanceKey` is `None` (`models.py:180-198`).

- `ref_flags` (`models.py:83-88`) returns `"I"` when the model's `ref_choices` contain `"I"`. Otherwise it returns the first
  choice that contains `"I"` (for example `"KI"`), or `None`.
- `modes` (`models.py:91-94`) gives:
  - `new` when `ref_choices` is empty or contains `""`;
  - `refs` when `ref_flags` is not `None`.
- The reference-manifest helpers (`models.py:97-133`) read the clip's catalog facts:
  - `picture_refs(model)` is the facts' `references` when the clip takes pictures (`:97-100`);
  - `identities(model)` is true when that role's `key` is set, which is a model whose boxes are identities (`:103-106`);
  - `in_shape(w, h)` is true when the long side is at most `SHAPE_MAX = 4` times the short side (`:109-112`);
  - `detail_facts(model)` is `{key, choices:[{value, label}], default}` when the model announces a reference detail,
    else None (`:115-119`), and `detail(model, value)` keeps a value the model lists (`:122-125`);
  - `drop_stale(model, adv)` removes a saved `text_encoder` or `detail` the model no longer lists (`:128-133`).

### 2.6.3 `ref_caps` — `models.py:57-80`

- `ref_caps(ctx)` is `ctx.settings.get("ref_caps") or {}`. `ctx.settings` is the module's block in settings.json:
  `modules.generate-image.ref_caps` (`hub/core/runtime.py:119`; a settings edit replaces each module's copy, `hub/core/apply.py:41-42`).
- `ref_cap(model, caps)` uses the longest prefix in `caps` that the model id starts with, else `DEFAULT_REF_CAP = 3`.
  A clip model does not use the table: its cap is the engine's, no more than the bar's boxes (§2.10.2).
- A model the hub set up from a weight file has `base` in its catalog entry. Its cap uses `base` instead of `id`.
  `test_reference_caps_are_the_owners_table_and_a_pointer_takes_its_base_cap` pins this.

### 2.6.4 Default models (text / refs)

- The server stores `{text, refs}` (§2.2.7).
- Web:
  - `defaults` store and `saveDefaults` (`modelList.ts:11,32-39`).
  - `defaultModel(models, defaults, refs)` returns the refs default when `refs > 0`, else the text default, and `null`
    when the default is unset or no longer listed (`edits.ts:89-90`).
  - `followDefaults` switches to that model when one is found. `edit()` applies it only when `references` changed
    (`draft.ts:26`), so a hand-picked model stays until the next reference change.
  - `refModel()` sends dropped references to the refs default.
- Tests: `web/tests/unit/defaults.test.ts`.

### 2.6.5 LoRA names — `models.py:207-230`

`lora_name(model, id)` handles ids of the form `<family folder>/<rel>`. Family folder = basename of
`lora_dirs[0]`. It refuses:

- a model without `loras` or `lora_dirs`;
- a wrong family;
- `\`, NUL, or empty/`.`/`..` path parts;
- a file that is not `.safetensors`/`.sft`;
- a nested path when the model is not `lora_recursive`.

It returns:

- `rel` when the file exists under one of `lora_dirs` without escaping it;
- the **full real path** when the file is found in `lora_extra` (the LoRA folders), because the engine takes
  a full path there;
- `None` otherwise.

### 2.6.6 Pointer models and the weights panel

- Routes (`gi/routes.py:76-112`):
  - `GET /weights` returns `ctx.engine.query("weights")`.
  - `POST /weights/rescan` returns the same with `rescan=True`.
  - `PUT /weights/base {path, base}` (body limit 4096) validates first:
    - `path` must be one of the panel's files;
    - `base` must not itself be a `pointer` model (`That model is itself a file the Hub set up; pick the model it is
      set up like`);
    - `base` must be `""` ("not a model") or one of `bases`.
    It then queries `weights` with `choose=(path, base)`.
  - Each call refreshes `models.catalog`.
- The panel record per file is `{path, name, folder, size_mb, status: known|pointer|unknown, model, base, suggested,
  candidates, chosen}` (`routes.py:86-87`).
- The pointer definitions are written by `hub/core/autoreg.py`. Its module docstring (lines 1-15) says a weight file
  that no definition names is matched by tensor-name Jaccard (`MATCH = 0.9`) and a size ratio (`LOW, HIGH = 0.25,
  1.3`). A `hub_auto` pointer definition (`POINTER_KEYS`, line 35) is then written into the engine's `finetunes/`.
  Weight files are never copied or moved.
- Model files: `GET /model-files` (`?fresh=1` asks again) returns `{models: [{id, name, kind, parts}], files,
  loras}`: every catalog model with parts, and the weight files in the engine's checkpoint folders (its scratch folder
  left out) and the models' LoRA folders, walked off the event loop (`hub/modules/generate_image/modelfiles.py`).
  `PUT /model-files {model, part, path}` takes an existing absolute weight file, or null for the engine's own; a part
  the engine refuses (the definition, a name the family finds by name) is one line (`Invalid("part")`).
  The panel is `web/src/shell/settings/ModelFiles.tsx` (Settings → Model files).
- the bases are every image model (`autoreg.model_kinds`), its official file present or not; the panel lists
  every file and asks for the kind of each one the Hub could not match ("This file is…").
- The web panel is `web/src/shell/settings/ImageModels.tsx` (Settings → Image models). It edits the model folders and
  the LoRA folders through `PATCH /api/settings`, offers Rescan, and has a per-file base picker ("Not a model" or a
  base, with "· suggested"). After each change it reloads the Generate model list and LoRAs (`refreshScreen`,
  lines 30-32).
- Tests:
  - `tests/engine/test_generate_image.py::test_a_model_the_hub_set_up_is_not_a_base`;
  - `tests/engine/test_autoreg.py`;
  - `web/tests/e2e/generate-models.spec.ts`.

---

## 2.7 The LoRA module (`hub/modules/loras/`)

- **Manifest** (`loras/manifest.py:22-30`): id `loras`. Routes:
  - `GET /api/loras?model=`;
  - `PATCH /api/loras/user?id=`;
  - `GET /api/loras/thumb?id=&size=&v=`.
  It listens to `settings.lora_folders` and rescans and reconciles every family (`on_folders`, lines 12-19). It has
  one listing, `loras`.
- **Families** (`scan.py:49-64`): one family per engine LoRA folder. Key = basename of `lora_dirs[0]`; dirs =
  `lora_dirs` plus `lora_extra`, deduplicated; `recursive` = `lora_recursive`.
- **Scan** (`scan.py:113-120`, `_walk` 93-110):
  - Extensions `.safetensors`/`.sft`.
  - Limits `MAX_DEPTH 8` and `MAX_FILES 5000`.
  - Folder symlinks are never followed; a file symlink must resolve inside the folder (`_entry`, 74-90).
  - Hidden directories are skipped.
  - The primary folder wins over linked ones.
  - Sidecar covers are `<stem>.preview.(png|webp|jpg|jpeg)` or `<stem>.(png|webp|jpg|jpeg|gif)` (`SIDECARS`, line 17).
- **Header facts** (`header.py`): it reads the 8-byte length and the JSON header only, capped at 100 MiB (`CAP`,
  line 14); a bad header means "no metadata". `summary()` (lines 54-68) returns:
  - `title` from `modelspec.title`;
  - `triggers` from `modelspec.trigger_phrase` plus `sd.artifact.v1.triggers` (deduplicated, at most 20, 80
    characters each);
  - `weight` from `recommended_weight` when it is within 0..2;
  - `thumb` when `modelspec.thumbnail` is a data URI.
  `scan.info` caches these facts by (size, mtime_ns) (lines 140-148).
- **List item** (`routes.py:36-43`): `{id, name (title or the prettified stem), file, fileTriggers, cover:{url}|null,
  strength (the set one), defaultStrength (weight or 1.0), addedAt (mtime)}`, sorted by name, then id (line 54).
- **Owner strengths** (`userdata.py`):
  - They are stored in doc `loras` as `{version:1, loras:{id:{strength,size,mtime}}}`.
  - `update` accepts exactly `{strength}`: 0..2, rounded to 2 decimals. `null` or `""` forgets it.
  - `reconcile` re-keys an entry when exactly one unknown file in the family has the same size and mtime (a
    rename/move), drops entries without a strength, and writes only when something changed (lines 31-53).
- **Covers** (`covers.py`): the sidecar, else the embedded thumbnail, else `null` (the web draws initials,
  `web/gi/Cover.tsx`). Thumbnails come from the hub's in-memory thumbnail store at sizes 96 and 336 as square WebP,
  served with `Cache-Control: no-store`. Nothing is written beside the LoRA.
- **Tests**: `tests/engine/test_loras.py` (header, scan rule, sort and covers, strength-only storage, rename keeps the
  strength, ambiguous rename, covers in memory, folders never written, one listing,
  `list_loras`); `tests/engine/test_settings_live.py::test_lora_folders_rescan_and_are_never_written`.

---

## 2.8 Tests that pin behaviour

### Python (`pytest`)

| File | Guards |
|---|---|
| `tests/engine/test_generate_image.py` | the manifest's exact routes, lanes, card, jobs, settings, listings, actions and listens (`test_manifest_declares_tab_sockets_routes_and_tools`); `/models` shape and the engine-down line; pointer models are not bases; draft round trip (saved vs session); settle at start; card text; start warms models; generated tool names, schemas and descriptions, with no "when" words, no `prompt`, no `push_draft`; `list_image_models`; `get` reports the draft and `last_seeds`; `set draft` reaches the session and not the disk or the box; a window clears the draft via PUT; `set draft` needs a window; set round trip; Advanced written only for steps/guidance/seed; every bad value is one line and nothing is written or published; handing back what `get` reported; width/height as the bar renders them; no tool writes the box; New chat; route and MCP list the same models; defaults keep present models only; `generate_image` equals the button; references by name (order, auto aspect, hand-back, cap, cap of the model being set, unknown name, needs a window, nothing on disk); `list_characters` and the names route |
| `tests/engine/test_build.py` | `image_job` defaults; references and flags; refusals as one line; seeds per image (fixed `+k`, random in range); guidance key and block rounding; LoRA names and multipliers; flavour translation keeps `FORCED_TASK`; `ui_model`; `ref_caps` and the pointer base cap; failure lines |
| `tests/engine/test_loras.py` | §2.7 |
| `tests/engine/test_video_engine.py` | the catalog lists clip models with their facts and lists none that lack a field; `one_pass` read from the definition; a clip task reaches the engine with the video values forced and a picture task does not; pictures pass through `translate` as given; no model name in core, worker or modules |
| `tests/engine/test_video_screen.py` | the bar sees a clip model; the canvas is the tier the megapixels pick; `view` reports one clip of the card's length; `apply` keeps a clip to count 1 and the length on the lattice; the clip task key by key; LoRAs only when active; one-line refusals; `generate_image` renders one clip with the unchanged tools; the text encoder is the card's, never a tool setting |
| `tests/engine/test_video_refs.py` | each model's pictures from its definition; the bar's cap (the engine's, no more than 3 boxes) and modes; `references` by name for each role and refused in one line; Auto snaps to a start frame's shape; box 1 as `image_start`; identities as the reference list with absolute paths; `generate_image` with the boxes |
| `tests/engine/test_omni_refs.py` | the catalog carries Omni's announced detail; `ui_model` passes it through; a character's box carries its name; the intent is the engine's `identity`, never the role word, and the fake engine accepts every built Omni task and refuses another intent; the card's detail reaches the task key; a stale detail is dropped by the next tool write; `PUT /draft` refuses a detail the model does not announce and keeps one it does; detail is no tool setting; `cutout` sets `remove_background` on identities only, and a tool press carries the session box's flag; a picture outside 1:4–4:1 is refused at build and, on Omni only, at set time; the manifest reaches the engine intact |
| `tests/engine/test_continue_build.py` | the continue task for 124 frames key by key; the longest step and the one over it; the step follows the card and the text encoder; the probe sends the same task; a loose source moves into its group and box 1 follows; nothing moves when a continue is refused; the clip and model refusals; a continued clip takes only box 1; the scene cap; a picture job and a plain clip are as before |
| `tests/engine/test_continue_route.py` | placing a clip fills box 1 and switches the bar; the model that made the clip, then the bar's; the route refusals; `references` takes a clip id on a model that continues; the settings report the clip's size and the step; `last_clip` is the newest clip made; the memory keeps the last 50; the settings text and the six tools stay |
| `tests/engine/test_continue_land.py` | a continued clip lands flat in its day folder and the source never moves |
| `tests/engine/test_continue_catalog.py` | a definition with "V" continues with its overlap; `continuation` reads the definition alone; every step on the lattice is one window; a "V" task makes the source plus n−1 frames at its size; a clip task that returns two files emits only the last; the scene-cap setting; the probe prints one line per step and chains, and refuses a model that cannot continue |
| `tests/engine/test_video_tiers.py` | the offered tiers: the catalog's first two by default, the setting's names checked against the catalog at use, an edit applied at the next use, odd values never crash, the Settings view |
| `tests/engine/test_worker.py` | real worker vs fake engine: plain PNG with nothing added, LoRAs per flavour, legacy names become basenames, nothing written in the engine root |
| `tests/engine/test_with_core.py` | a generate over the bus into Media, end to end |
| `tests/engine/test_settings_live.py` | the model list follows the model folders; LoRA folders rescan |
| `tests/core/test_features.py` | the generic Screen/Listing/Action to tool generation and schema refusals |
| `tests/core/test_assistant_tools.py` | the assistant chat running tools through Open WebUI (the caller side of these tools) |

### Web unit (`web/tests/unit`, vitest)

| File | Guards |
|---|---|
| `job.test.ts` | canvas table per aspect; Auto from reference 1 with clamp; the payload "byte for byte"; renders the draft, never the box; mode from references; model defaults, guidance only with a key, fixed seed |
| `blocking.test.ts` | each reason; 4,000 characters allowed; first reason only |
| `delivery.test.ts` | socket declaration; group/specific/unknown placement; dropped files; model switch keeps stacks; place/remove refs |
| `defaults.test.ts` | the default-model rule and that only reference edits apply it |
| `complete.test.ts` | `matchesAt`, `place` |
| `triggers.test.ts` | `findRanges` |
| `order.test.ts` | LoRA list order, stem, new mark, strength line |
| `misc.test.ts` | `queueView`, `runningText` (among non-Generate checks) |
| `video.test.ts` | the tier a megapixels value picks and its size per aspect; seconds, frames and the lattice; the clip job; the job line "Done · clip"; the text encoder on the sheet and kept by Reset |
| `continue.test.ts` | a model continues when the catalog says so with its overlap, the longest step is max − overlap + 1 frames; box 1 holds a clip only when it says so; the clip's size and refs, the clip id alone, the step's frames; one line each for a model that cannot continue, a filled box 2, a clip past box 1, a step over the longest; a picture sent while box 1 holds a clip is refused; the Continue route's post; Size and Aspect greyed with a clip; box 1 plays the clip and boxes 2–3 are shut; Seconds shows "+5.1 s"; a clip's group, the day and group rows; the job label |
| `omni.test.ts` | the saved detail when the model announces it, else the engine default; the menu keeps the engine order and labels; Reset keeps the sheet's detail; `toggleCutout`; `removeRef` keeps each flag with its picture; the job sends `cutout` for Omni only; the 1:4–4:1 rule; an out-of-shape drop places nothing and sets the note |
| `video-refs.test.ts` | roles name the boxes; the caps (a start frame takes one picture); Generate with or without a frame, Omni needs one identity; the draft stays on a clip model; the job's `references`; Auto from a start frame |

### Web e2e (`web/tests/e2e`, Playwright)

| File | Guards |
|---|---|
| `generate.spec.ts` | generate → queue → done; cancel/clear/failure; Ctrl+Enter once; blocked reason; save 1 s after the last change; reconnect into a new session; tool-server settings land while the prompt is unsaved; the article follows the server and Clear works; LoRAs on/off and strength |
| `generate-press.spec.ts` | the button and Ctrl+Enter send the draft, never the box; empty draft blocks both |
| `generate-freeze.spec.ts` | the stranded-`changed`-key regression |
| `generate-more.spec.ts`, `bar-controls.spec.ts` | Steps, Count, Aspect, the Settings round trip |
| `bar-line.spec.ts` | the bar is one line at 1366×768 and 1920×1080 with worst-case values |
| `seed-guidance.spec.ts` | Guidance on the sheet only (Qwen yes, Flux no, clamp 0..20); the seed line (hidden cases, keep/Random, running hides it); the bar with Qwen on one line |
| `library-sheet.spec.ts` | the sheet rises over the chat without moving it, lines up with the fold, Escape, inert when shut |
| `article.spec.ts` | paging by gesture and keys, resize alignment, placeholder |
| `chat.spec.ts` | Enter/Shift+Enter/Ctrl+Enter; busy; New chat empties chat, box and draft; only replies shown |
| `tab-complete.spec.ts`, `tab-references.spec.ts` | §2.5 |
| `generate-models.spec.ts` | the picker rescans on open; first load rescans; Settings → Image models |
| `generate-video-model.spec.ts` | the Size menu lists the tiers; one clip a press with the count off and no guidance; Seconds in Settings snapped to the lattice; Reset keeps the text encoder |
| `video-continue.spec.ts` | right-click Continue posts the id, the clip stays where it is and selected, box 1 plays it; the bar's Continue shows only while the Stage shows a clip; a picture has no Continue; Settings → Seconds shows the step as "+5.1 s" and stops at the longest step |
| `video-omni.spec.ts` | Omni's Detail under Text encoder and its choice reaching the draft PUT; First / Last has no Detail; an identity box's menu cuts out the background and keeps it again (mark, title, draft, job); the flag travels with its picture; the box menu of First / Last has Remove only; a 1×4.25 picture is not placed and the box says why |
| `video-references.spec.ts` | a start-frame model's box 1 and struck boxes 2–3; Tab fills the Start frame and the draft stays; identity boxes filled by Send; Auto in the hover text and the job; the Text encoder on the sheet, saved per model, absent for a picture model; the sheet fits at 1366×768 |

---

## 2.9 Recipes

### 2.9.1 Add a setting (MCP-visible, saved, rendered)

1. `gi/screen.py`:
   - Add the bound constant and a `Setting(...)` to `SETTINGS`. Use a valid `SettingKind` (`hub/core/api.py:69`),
     with `lo`/`hi` for `seed`/`loras` and `hi` for `names` (`hub/core/registry.py:55-68`). Write the label as a
     plain fact with none of the banned words (§2.4.7).
   - If the value is per model, add the name to `ADVANCED` and handle it in `_advanced()`. If it is session-only, add
     it to `SESSION` and write it in `apply()`.
   - Otherwise validate and store it in `_save()`.
   - Normalize it in `read()` and report it in `view()`.
2. `gi/routes.py`: add the stored key to `SAVED_FIELDS` (or `SESSION_FIELDS`). Without this, `settle` drops it at
   start and `put_draft` ignores it from the web.
3. `gi/build.py`: validate the incoming param, map it into the engine `base` dict, and add it to `summary` if the job
   line or card needs it.
4. `gi/tools.py:generate_image`: pass it in `params` the way the window does.
5. Web:
   - `types.ts`: add it to `Draft` or `Advanced`.
   - `edits.ts`: add it to `EMPTY_DRAFT`, `normalizeDraft`, and `defaultsOf`/`isDefault` if per model.
   - `job.ts`: add it to `JobParams` and `buildJob`.
   - `blocking.ts` if it can block a press.
6. Tests:
   - `tests/engine/test_generate_image.py`: `SETTING_NAMES`, `DESCRIPTIONS`, and the round trip and refusal tables.
   - `tests/engine/test_build.py`.
   - `web/tests/unit/job.test.ts` (the byte-for-byte payload).

### 2.9.2 Add a tool

- **Listing** (`list_<name>`): add `Listing(name, text, args_schema_props, fn, required=...)` to `LISTINGS` in
  `gi/tools.py:89-91`. Use `loras/tools.py` as the model for arguments.
- **Action** (own name): add `Action(name, text, schema, fn)` to `ACTIONS` (`gi/tools.py:92-93`).
- `gi/manifest.py:51-52` already wires both tuples.
- Rules enforced at startup (`hub/core/registry.py:112-119`): the name is unique snake_case; the description is at
  most 200 characters and ends with a period.
- `fn(ctx, args)` returns compact JSON and raises `Invalid(field, one_line)` on bad input.
- Update `NAMES`, `DESCRIPTIONS` and `test_manifest_declares_tab_sockets_routes_and_tools` in
  `tests/engine/test_generate_image.py`.

### 2.9.3 Add a bar control

1. Write the component in `web/gi/run/Canvas.tsx`, following `Count` and `Steps`: read with
   `useStore(draft, …)` and write only through `edit(x => …)` (or `withAdvanced` for per-model values). Saving follows
   automatically: `edit` records the key, and `save` PUTs it after 1 s.
2. Place it inside `<span className={s.controls}>` in `web/gi/run/Taskbar.tsx:51-57`. A per-model control that would
   crowd the bar can go on the sheet head instead, as `Guidance`, `Encoder` and `Detail` do (`library/LoraLibrary.tsx:88-93`).
3. Make sure the server accepts the field (`SAVED_FIELDS`, §2.9.1 step 2). Otherwise it is lost on reload.
4. Styles go in `run/Run.module.css`. Check the one-line rule with `web/tests/e2e/bar-line.spec.ts` (and the Qwen
   case in `seed-guidance.spec.ts`).

## 2.10 Video models on this screen

A model of the engine's catalog whose `kind` is "video" is a clip model. It is picked from the same menu, shown on the
same bar and rendered by the same button and the same tool. This section gathers, in the order a request travels, what
differs for it. Nothing in `hub/core`, `hub/worker` or `hub/modules` names a model: every fact below is read from the
engine's definitions (`tests/engine/test_video_engine.py::test_core_and_worker_name_no_model`,
`test_modules_hold_no_model_named_one_pass_key`).

### 2.10.1 The catalog entry — `hub/worker/catalog.py`, `hub/worker/catalogvideo.py`

The clip facts are read in `catalogvideo.py`, which `catalog.py` imports (`catalog.py:14-17`); the split keeps both files
under the size limit. The worker names no model in either.

- `build` (`catalog.py:133-172`) lists a visible model when it has `image_outputs` (`kind "image"`, `video None`) or when
  `video_facts(model_def, {"video_length": 0})` is not None (`:143-144`). For a clip model the entry gains `kind "video"`,
  `video` (the facts), `video_task` and `steps_range` (`:162-163`), and `loras` is false when the definition sets
  `loras_disabled` (`:164`). `engine_switches(w)` is read once per catalog (`:136`) and passed in (`:162`).
- `video_facts` (`catalogvideo.py:161-190`) returns None when the definition has `image_outputs` or `audio_only`, lacks
  `t2v_class`, runs in another runtime (any true `*_sidecar` flag), lacks `fps`, `frames_minimum`, `frames_steps` or
  `frames_maximum`, has no resolution tiers, or cannot take text alone: "T" must be in `image_prompt_types_allowed`,
  except for a reference-manifest model (`omni_reference`), which needs its references instead (`:170-182`). Its answer
  (`:187-190`): `fps`; `frames {min, step, max, default}` (the factory `video_length` snapped up to the lattice,
  `:184-185`); `steps` (the factory step count); `tiers`; `references`; `one_pass`; `continues` and `overlap`; and the
  text encoder facts.
- `tiers` (`:27-48`) lists each preset in the definition's order with `sizes` per aspect: the aspects the definition names,
  and every other shape of `RATIOS` (`:11`) sized from the preset's pixel budget (`auto_resolution_budgets`), rounded to the
  block, the way the engine sizes an auto canvas.
- `picture_refs` (`:87-104`) gives the pictures the model takes. A reference-manifest model takes **identities**:
  `{role "identity", min 1, max <omni_reference_limits["image"]>, key <the one *_references list its defaults name>}`
  plus `detail` when it announces one, and is not listed when it has no cap or no such list. A model with "S" in
  `image_prompt_types_allowed` takes a **start frame**: `{role "start", min 0, max <2 when "E" is also allowed, else 1>,
  end <"E" is allowed>}` (`:103-104`): with "E" a second picture is the last frame. A model with neither takes no
  pictures (`references None`).
- `reference_detail` (`:107-118`) is `{key, choices:[{value, label}], default}` from the definition's
  `omni_reference_detail_choices` (label, value pairs in the engine's order) and `omni_reference_detail_default`, with
  the task key the one setting ending `_reference_detail`. It is None when any part is missing or the default is not
  one of the values.
- `continuation` (`:121-134`) is the overlap the model continues a clip with, or None. A model continues when "V" is in
  `image_prompt_types_allowed`, it is not a reference-manifest model, and its overlap
  (`sliding_window_defaults["overlap_default"]`, else the settings' `sliding_window_overlap`) is a whole number above 1
  whose `overlap − 1` lies on the frame lattice, with room for the shortest clip (`min + overlap − 1 <= max`). The facts
  carry it as `continues` (a boolean) and `overlap`. One pass of a continue is `frames + overlap − 1` frames and the
  clip grows by `frames − 1` (§2.10.7).
- `one_pass` (`:147-158`) is `{<a *_multi_window key>: False}` or None. The key is the one the model's own settings name; if
  they name none, an engine switch (`engine_switches`, `:137-144`: every keyword parameter of the engine's
  `generate_video` named `*_multi_window` with a yes/no default) whose prefix starts another key of the model's definition
  or settings. So a definition that publishes no such setting still gets the flag from the engine's own signature
  (§2.10.5).
- `encoder_facts` (`:63-84`) lists the text encoder variants the definition publishes (`text_encoders`,
  `text_encoder_names`, `text_encoder_default`) and which of them have every file in the model folders
  (`text_encoders_found`, None when the engine could not tell); `encoder_choice` (`:51-60`) finds the `<key>_default` and
  `<key>_variants` pair. `video_task` (`:193-197`) is `{<the definition's *_text_encoder key>: <its default>}`.
  `steps_range` (`:200-202`) is `[inference_steps_min, inference_steps_max]`.
- `SHAPE = 7` (`catalog.py:21`) is the entry-shape mark. `enginecat.catalog_key` hashes `shape:<SHAPE>` with the engine's
  paths and definition folders (`hub/core/enginecat.py:29-35`), so a catalog cached under an older shape is never served.
  Pinned by `tests/engine/test_video_engine.py::test_catalog_lists_text_to_clip_models_with_their_facts`,
  `test_video_facts_need_every_field`, `test_one_pass_is_read_from_the_settings_first`,
  `test_a_clip_task_carries_the_one_pass_key_from_the_engine_or_the_settings`,
  `test_modules_hold_no_model_named_one_pass_key` and
  `tests/engine/test_video_refs.py::test_the_catalog_names_each_models_pictures_from_its_definition`,
  `test_picture_refs_read_the_definition_alone`; `tests/engine/test_omni_refs.py::test_the_catalog_carries_omnis_announced_detail`;
  `tests/engine/test_continue_catalog.py::test_a_tsev_definition_continues_with_its_overlap`,
  `test_continuation_reads_the_definition_alone`.

### 2.10.2 The model as the bar sees it — `gi/models.py`

- `video(model)` (`models.py:142-150`) returns the facts with the tiers the size menu offers, or None for a picture
  model. The offered tiers are the setting `modules.generate-image.video_tiers` (default 2, `hub/settings.py:37`): a
  count of the catalog's first tier names, or a list of names the catalog reports (`offered_tiers`, `models.py:61-68`;
  a name the catalog lacks is ignored; no usable value gives the model's first `MAX_TIERS = 3`, `:32`). It is read at
  every use from `_ctx.settings`, so an edit applies at the next call. Pinned by `tests/engine/test_video_tiers.py`.
- `picture_refs(model)` (`:97-100`) is the catalog's `references` when its `max` is set. `clip_modes` (`:136-139`) is "new"
  when the model needs no picture (`min` 0 or no references) and "refs" when it takes some. So a start-frame model has
  both modes, the identity model only "refs", a model with no pictures only "new".
- `ui_model` (`:178-196`): `guidanceKey` is `None`; `refCap` is the model's picture `max` **clamped to the bar's boxes**
  (`min(refs["max"], cast.BOXES)`, `:182-184`), so the bar never promises a box it does not draw; the `ref_caps`
  table is not read for a clip model. A start-frame model's cap is 1, or 2 when its definition allows an end frame; an
  identity model's is the engine's cap or 3, whichever is smaller. `defaults.steps` is the clip's `steps`. Pinned by
  `tests/engine/test_video_refs.py::test_the_bar_takes_the_engines_cap_and_the_image_modes`,
  `test_the_cap_is_no_more_than_the_bars_boxes`.
- `frames(facts, value)` (`:153-156`) snaps a length up to the lattice within min..max, and gives the default for a
  value that is not a whole number. `encoder(model, value)` (`:159-163`) keeps a variant the model lists, else None (the
  definition's default). `encoder_key` (`:166-168`) is the task key a variant goes under.

### 2.10.3 Roles of the reference boxes

- A **start-frame** model: box 1 is the clip's first frame. When its definition allows an end frame, box 2 is the last
  frame; a box past the cap is struck through (box 2 on a model without an end, box 3 always). Box 1 is filled like any
  reference: a Media drag or Send, a dropped file, a character picked by Tab (the picture goes in the first free box,
  §2.5), or the `references` setting by character name. With every box empty the clip is text only. A last frame with no
  start frame is refused (`LAST_ALONE`, §2.10.5): the boxes are a dense list, so box 2 is never filled while box 1 is empty.
- An **identity** model: boxes 1 to the cap are identity pictures, in box order; at least one is required. Each
  picture must be within 1:4 and 4:1 (`models.in_shape`; the web refuses a drop outside it and notes `<label> takes
  pictures between 1:4 and 4:1`, `video.ts:86-89`). A box holding a character carries its name to the engine (§2.10.5).
  The box's menu has "Cut out background" or "Keep background" for this role only (`Slots.tsx:81-82`), which sets that
  box's `cutout` flag. The flag stays with its picture when a box is removed.
- A model that continues a clip (§2.10.7) also takes a **clip** in box 1: the box plays the clip, and boxes 2–3 are shut
  with `A continued clip takes only box 1` (`Slots.tsx:89`). It is never an identity model.
- The web names the boxes by role: `boxLabel` (`video.ts:101-107`) gives "Start frame" (box 1), "Last frame" (box 2, only
  when the facts say `end`), "Identity n" (boxes up to `max`), else "Reference n". `refsOf` (`:71`) reads the facts'
  `references`; `Slots` (`run/Slots.tsx:73-96`, a box is open when its index is below `refCap`, `:88`), the sockets Media
  sees (`delivery.ts:11`) and the job use them. `blockingReason` lets a clip press through with no box when `min` is 0 and
  asks for one ("Add a reference image") when it is not (`blocking.ts:41-47`).
- The assistant sets the boxes with the `references` setting, which `cast.resolve` checks against the model's `refCap`
  (`takes 1 reference picture`, `takes 2 reference pictures`, `takes 3 reference pictures`, `takes no reference
  pictures`, `cast.py:103-107`). Pinned by `tests/engine/test_video_refs.py::test_references_by_name_for_each_role` and
  `test_references_refused_in_one_line`; browser: `web/tests/e2e/video-references.spec.ts` (start-frame boxes, Tab fill,
  identity boxes by Send); unit: `web/tests/unit/video-refs.test.ts`.

### 2.10.4 The size, the aspect and the length

- The bar's Size menu holds the offered tiers by name instead of 1, 1.5, 2, 4 MP. Each is stored as the megapixels value
  that picks it: `tierOptions` (`video.ts:16-17`) maps the first three tiers to 1, 2 and 4. `tierIndex` (`:11`) is the
  inverse: 1 or less is the first tier, up to 2 the second, above 2 the third, never past the last offered. The server
  does the same in `tier_size` (`models.py:173-178`, which calls `clipplan.tier_size`) from the setting `megapixels`: 1 picks the first tier, 1.5 and 2
  the second, 4 the third.
- `canvas(aspect, mp, references, model)` (`screen.py:67-77`) returns, for a clip model, `tier_size(facts, aspect,
  ratio, mp)`. A named aspect takes the tier's size for it, or the size nearest its shape when the tier lacks it.
- **Aspect Auto snaps to the tier's shape nearest the start frame.** For a start-frame model with a picture in box 1,
  `ratio` is `auto_ratio(references)` (box 1's width over height, clamped to 0.4..2.5, `screen.py:57-64`) and `tier_size`
  picks the size whose shape is nearest by log ratio (`hub/core/clipplan.py:59`). With no picture, or for an identity model, the
  ratio is 1 and Auto is the tier's squarest size (`screen.py:74-75`). The web mirror is `tierSize(v, mp, aspect, auto)`
  (`video.ts:26-32`) with `autoOf` (`:92-93`) and `clipSize` (`:96-97`), used by the Size menu, the Aspect menu's Auto
  hover text (`Canvas.tsx:38-40`) and `buildJob`. Pinned by
  `tests/engine/test_video_refs.py::test_auto_snaps_to_a_start_frames_shape`.
- The length is frames on the model's lattice. The card's **Seconds** field edits it (§2.1.7); it is stored in
  `advancedByModel[model].frames`. `screen.clip_frames` (`screen.py:80-83`) reads it on the lattice, else the model's
  default; `view` reports `frames` and `seconds` (`:184-189`); `generate_image` and the press send `frames`
  (`tools.py:76-77`, `job.ts:76`). With a clip in box 1 the Size and Aspect menus are greyed and show the clip's size,
  and Seconds is the step: "+N s" is `(frames − 1) / fps` (§2.10.7).
- On a model that announces a reference detail (an identity model) the sheet has a Detail menu, kept per model as
  `advancedByModel[model].detail` and read by `screen.clip_detail` (`screen.py:91-93`). Like the text encoder it is not a
  tool setting (`tests/engine/test_omni_refs.py::test_detail_is_no_tool_setting`).
- The text encoder is chosen on the raised sheet (§2.1.5), kept per model as `advancedByModel[model].text_encoder`, and
  read by `screen.clip_encoder` (`screen.py:86-88`). It is not a tool setting: `SETTINGS` has no such name
  (`tests/engine/test_video_screen.py::test_the_text_encoder_is_the_cards_alone_never_a_tool_setting`).

### 2.10.5 The clip task — `gi/build.py:clip_job`

`image_job` (`build.py:214-226`) finds the model, builds its `ui_model`, checks the `cutout` list (`_cutout`, §2.3.4),
refuses a clip among the references of a picture model (`<label> cannot continue a clip`, `:224-225`), and calls
`clip_job(p, ctx, model, ui)` (`:161-211`) when `ui["video"]` is set, else `picture_job` (`:238-281`, §2.3.4). The seeds
it drew become the session's `last_seeds` when the module hears `job.submitted` (`on_submitted`, `:229-235`, §2.2.1).
Each check in `clip_job` is one `Invalid(field, text)` line, made before submit because the engine's own refusal is one
vague line:

1. The pictures (`_clip_refs`, `:91-111`): `mode` must be "new" or "refs"; a model without "new" among its modes (the
   identity model) with mode "new" or no pictures is refused with "`<label>` needs at least one image reference"
   (`NEEDS_IDENTITY`, `:20`); a mode the model lacks gives `MODE_TEXT`; more pictures than `refCap` gives "Too many
   references for this model (k of cap)"; on a start-frame model an empty box 1 with a picture after it gives "A last
   frame needs a start frame in box 1" (`LAST_ALONE`, `:25`, `:109-110`); each id must resolve to a file ("An image is
   missing; add it again"). When box 1 holds a clip (`chain.source`, `:168`) this step is skipped and the size check
   below is not made: the press is a continue (§2.10.7).
2. The prompt (`_prompt`, 4000 characters at most), the size (`width`, `height` must be one of the offered tiers' sizes,
   "Choose a size the model can make", `:172-173`), the frames (a whole number within the lattice's min and max, snapped
   up, else the card's value, `:174-178`), the steps (within `steps_range`, else `screen.STEPS`, `:179-181`), the LoRAs
   and the seed.

The task (`:199-204`) is, key by key:

```
model_type, image_mode 0, prompt, resolution "WxH",
video_length frames, sliding_window_size frames,        # one window: the whole clip
**one_pass,                                              # the catalog's {<*_multi_window>: False}, when it has one
num_inference_steps, seed, batch_size 1, multi_prompts_gen_type "FG",
image_prompt_type "", video_prompt_type "",
**video_task,                                            # {<*_text_encoder>: default}
**pictures,                                              # see below
<text-encoder key>: the sheet's variant                 # only when the sheet chose one the model lists (:186-188)
<detail key>: the sheet's detail                         # only when the model announces one and the sheet chose it (:189-191)
activated_loras, loras_multipliers                       # only when a LoRA is active (:192-194)
```

`pictures` (`_clip_pictures`, `:144-158`): for a start frame, `START` (`image_prompt_type "S"`, `image_fit_mode "crop"`,
`:24`) plus `image_start` = box 1's absolute path (the picture is cropped to the clip's canvas, so the clip is the size
asked for); with a second box on a model whose facts say `end`, `image_prompt_type "SE"` and `image_end` = box 2's
absolute path, cropped the same way (`:156-157`). For identities, `image_prompt_type ""` and `<references.key>` = one
item per box, in box order, absolute paths (`_identity`, `:128-141`):

```
{type "image", path, image_intent "identity"            # models.IDENTITY, the engine's word; never the Hub's role word
 character_name?,                                        # the box's character (cast.character_name), at most 120 characters
 remove_background true? }                               # only when the box's cut-out flag is on
```

The picture's shape is checked first (`cast.shape`, 1:4 to 4:1), then `character_name` is added when the box is a listed
character (`cast.name_ok` refuses a longer name), then `remove_background` when `cutout[n−1]` is true. `_cutout`
(`:114-125`) reads the job's `cutout` list: one boolean per entry of `references`; a non-list, a longer list or a
non-boolean gives `Cut-out must be on or off for each box`, and a `true` on a model whose boxes are not identities gives
`<label> cuts out no backgrounds`. The worker passes all of these through untouched except for `FORCED_VIDEO` (§2.3.5).

The summary adds `kind "clip"`, `frames`, `seconds` (frames over fps, two decimals), `guidance None`, `count 1`, and
`references` as the boxes' labels (`:205-210`); `mode` is "refs" when pictures were sent. The job's kind stays `image`
(`JobPlan("image", ...)`, `:211`), so the queue, cancel and the job line work as for a picture. The clip's output event
carries `kind "clip"` (part 1, §1.5 and part 3, §3.2.5); the web job line then says "Done · clip in …"
(`run/jobs.ts:39-41`). Pinned by `tests/engine/test_video_screen.py` (`test_a_clip_is_one_task_key_by_key`,
`test_a_clip_refuses_in_one_line`, `test_a_clip_takes_the_cards_text_encoder_else_the_definitions`,
`test_generate_image_renders_one_clip_with_the_unchanged_tools`), `tests/engine/test_video_refs.py`
(`test_a_start_frame_is_box_one_as_image_start`, `test_box_two_is_the_last_frame_on_a_model_that_allows_one`,
`test_identities_are_the_reference_list_in_box_order`, `test_a_clips_pictures_refused_in_one_line`,
`test_generate_image_sends_the_boxes_with_the_unchanged_tools`) and `tests/engine/test_omni_refs.py`
(`test_a_characters_box_carries_its_name`, `test_the_intent_is_the_constant_not_the_role_word`,
`test_cutout_sets_remove_background_on_identities_only`, `test_a_picture_out_of_shape_is_refused_at_build`,
`test_the_manifest_reaches_the_engine_intact`).

### 2.10.6 What a clip model cannot do here

No guidance (`guidanceKey None`, so the sheet shows no Guidance input); no count above 1 (the Count control shows 1 and
is off, `set_generate_image_settings` refuses another value); no negative prompt, no audio choice (the clip keeps the
sound its model makes); no last frame alone; no audio or video references; no image intent other than identity (scene,
style and composition have no control: `models.IMAGE_INTENTS` lists them, `models.py:28`). A picture model cannot take
a clip. A clip in box 1 is a continue, which needs a model that continues one and takes box 1 alone (§2.10.7). The six
tools are unchanged; the tool list and their schemas are those of the picture screen.

### 2.10.7 Continue a clip — `gi/chain.py`

A clip in box 1 of a model that continues one makes the clip longer. The engine decodes the whole source and writes the
source plus the new frames as one file, so the hub sends one task for the new part. The new file lands flat in the day folder as a new clip; the source stays where it is (the group folders are gone). Nothing in this path names
a model: the overlap, the frame lattice and the sizes are the catalog's.

- **Which models.** `chain.overlap(model)` (`chain.py:68-72`) is the catalog's `video.overlap` when `video.continues` is
  true and it is a whole number above 1, else None. A model that takes a reference manifest never continues
  (`continuation`, §2.10.1).
- **Placing a clip in box 1**, two ways: Media's Continue (menu and bar, part 3) and a clip id in a drop on a box call
  `POST /api/generate-image/continue {id}` (`manifest.py:45`, body limit 4096; web `continue.ts:7`); the `references`
  setting with the clip's id reaches the same checks through `cast.resolve` (§2.4.5). The route (`chain.continue_clip`,
  `chain.py:183-199`) does, in this order:
  1. `chain.facts` (`:75-86`): the clip must exist and be a clip (`The clip to continue is gone`) and its facts must read
     (`This clip is not an MP4 the hub can read`).
  2. The engine's catalog; an engine error is `Invalid("engine", first line)`.
  3. `chain.pick` (`:168-180`): the model that made the clip (session memory `clip_models`) if it is present and
     continues, else the bar's model if it continues, else the first present model that continues; none gives
     `No model here can continue a clip` (`NONE_HERE`).
  4. `chain.box` (`:111-115`) checks the clip against that model with `chain.check` (`:89-101`): `<model> cannot continue
     a clip` (`CANNOT`), `This clip is shorter than <overlap> frames` (`SHORT`), `This clip's size is not one the model
     makes` (`SIZE`, the size must be one of the model's tiers' sizes); and the clip's own length must be under the scene
     cap (`SCENE`, `_cap` with `reached`).
  5. It writes the session's `references = [{id, w, h, kind: "clip", seconds}]`, saves the draft with `model` set to the
     picked model, publishes `changed draft`, and returns `{id, model, label}` (`:194-199`).
- **The press.** `build.clip_job` calls `chain.source(ctx, references)` (`:44-53`): a clip must be box 1 and boxes 2–3 must
  be empty, else `A continued clip takes only box 1` (`ONLY_BOX_1`). With a clip it skips `_clip_refs` and the tier-size
  check and hands the checked prompt, frames, steps, seed, text-encoder/detail keys and LoRAs to `chain.plan`
  (`chain.py:139-165`):
  1. `chain.check` again (`CANNOT`, `SHORT`, `SIZE`).
  2. `frames + overlap − 1` may not exceed the engine's largest window (`video.window_max`, upstream's 481; else the
     lattice's maximum, the fork's), else `Each step is at most <x> s` (`STEP_MAX`, `(top − overlap + 1) / fps`). On
     upstream the step is at most the frame maximum (362) first, so a continue's window is at most 379; the adapter
     refuses one above `window_max` in its own line as well (`tasks.STEP_MAX`).
  3. The scene is the clip's seconds plus `(frames − 1) / fps`; above the cap it is refused (`The scene would be <x> s; the
     longest is <cap> s`).
  4. The task, key by key: `model_type`, `image_mode 0`, `prompt`, `resolution` the source's `WxH`, `video_length frames`,
     `sliding_window_size frames + overlap − 1`, `sliding_window_overlap overlap`, the catalog's `one_pass` key,
     `num_inference_steps`, `seed`, `batch_size 1`, `multi_prompts_gen_type "FG"`, `image_prompt_type "V"`,
     `video_source` the source's absolute real path, `keep_frames_video_source ""`, `video_prompt_type ""`, the model's
     `video_task`, then the text-encoder, detail and LoRA keys (`:152-158`).
  5. The summary has `mode "continue"`, `continues` (the source's id), `width`/`height` (the source's), `frames`,
     `seconds` = `(frames − 1) / fps`, `scene_seconds`, and `references` = the source's stem (`:159-163`). The web job
     line reads it as "Continue · +5.1 s · scene 10.2 s" (`continueLabel`, `run/jobs.ts:45-51`).
  6. The plan names no folder: `chain.plan` returns `JobPlan("image", model, (task,), summary)` and `enginecat.land`
     puts the clip in its day folder.
- **The scene cap** is `modules.generate-image.continue_max_seconds`, 10 to 600, default 60 (`hub/settings.py:38`, checked
  at `:205-206`). It is not edited in the UI. The engine decodes the whole source, so it bounds the memory a long scene
  takes. The 60 s default has not been measured on the server.
- **What the worker does with it.** `wan2gp.py:227-231` keeps only the last file of a clip task that returns several (each
  chained file holds the ones before it). The probe (`python -B main.py --root ROOT --state DIR --probe-continue CLIP [--chain K] [--model ID]`, `hub/worker/main.py:7`) runs a continue one step at a time and prints one line per step (part 5).
- **Session memory** (`on_job_finished`, `chain.py:202-219`): a Generate job that ends `done` with clips among its outputs
  sets `last_clip` to the newest and records each clip's model in `clip_models` (the last `MEMORY = 50`, oldest dropped).
  The tool server reports `last_clip` (§2.4.2), so the assistant can set `references` to it and press Generate to
  continue the clip it just made.
- **Pinned by** `tests/engine/test_continue_build.py`, `test_continue_route.py`, `test_continue_land.py` and
  `test_continue_catalog.py`; web `continue.test.ts` and `video-continue.spec.ts` (§2.8).

---

### 2.10.8 Sound, the shot, the plan and the judges

Written from the code as built; none of it has run on the server.

- **A sound with the clip (`gi/clipsound.py`).** The Sound box holds a Sounds item; the press sends it as
  `ClipRequest.sound` (a real path) with `sound_seconds`; the clip's length is the shortest lattice length that holds
  the sound, a shorter sound padded into `<module data>/soundpad/`. The worker's adapter sends it as the kept
  soundtrack (the facts file's letter). Media's right-click "Put in Sound" and the Video box (
  `gi/clipvideo.py`, `ClipRequest.video`) work the same way; a continue takes neither.
- **The shot (`gi/shotcheck.py`, `gi/shotprompt.py`).** `set_generate_image_settings {shot}` (session-held,
  `screen.SESSION`) is checked against `shotcheck.SCHEMA` and compiled into the prompt the engine's syntax wants; the
  clip's length follows its lines. With `plan_before_render` on, a clip job is planned first: the worker
  asks the engine's preflight (`adapters/plan.py`, `enginequery.query("plan")`), the plan goes to the job's notes
  (`Jobs.note`) and the running job's tooltip; a cut inside a window is refused (`cuts_on_plan`).
- **Takes and the judges (`gi/takes.py`, `adapters/judge.py`, `adapters/faces.py`,
  `adapters/mouth.py`).** The worker's `joins.finish` runs after a task lands: a spoken line is transcribed by the
  engine's own Whisper and scored against its words (`judge.words`); a clip with identity pictures gets the face
  judge (InsightFace from the engine's refiner files, named in the facts file; cosine to the character's picture and
  views per frame at 2 a second: `min`, `median`, `first`, `last`, `drift`, `lost_at`, `present`), the frame judge
  (the face box's size and path) and the mouth judge (the engine's mouth measure from the 106 landmarks against the
  engine's `speech_intervals`, 8 frames a second: `lips`, `moving`, `talk`, `rest`); a clip with a kept soundtrack
  and no identity picture gets the mouth judge alone, on the largest face ("The face judge did not run: no
  character in a box" beside it).
  A continue is judged from its new part on (the clip's length and rate by `hub/core/clip.py`). The result travels
  as the task's `judge` → `notes["judged"][task]` → `job.finished`; `gi/chain.on_job_finished` hands it to
  `takes.on_finished` (lines) or `takes.on_clip_finished` (clips), which keep the best take, re-take on the next seed
  under the bars (`speech_takes_max`, `clip_takes_max`; a lost face scores 0), and write one line as
  `notes["verdict"]` and `last_take["verdict"]`: the job's line shows it (`run/Queue.tsx`), Media's Stage shows
  it on the clip or sound the job made (the media role has the jobs lane), the assistant reads it in the
  settings view. Settings: `speech_judge`, `speech_takes`, `speech_takes_max`, `speech_words_bar`, `clip_judge`,
  `clip_face_bar`, `clip_takes_max`, `clip_lips_bar`, `frame_close`, `frame_wide`, `judge_device` (`settingsmods.py`).
  The judges are advice: anything they cannot do is a line ("The face judge did not run: …"), never a fault.
- **The pace (`gi/pace.py`).** A spoken line's planned length uses the voice's measured words a second
  (`speech_pace`, learned from the judge's span, else the file's own speech span), not the engine's constant alone.
- **A bed under the voice (`hub/core/seqshape.py`, `hub/worker/joincmd.py`).** Edit Video's track-2
  items carry `level`, `fade_in`, `fade_out`, `duck`; Save applies `volume`, `afade` and `sidechaincompress` keyed by
  track 1 (`Duck` on the `JoinRequest`, settings `duck_*`); the item's right-click sets them.

## Gaps / unverified

- **Stale comments about a "push" into the prompt box.** `gi/manifest.py:1-2` says the module publishes "the push of
  the assistant's draft into the prompt box". `web/gi/draft.ts:91` ("pushed it into the prompt box") and
  `web/gi/chat/assistant.ts:3` ("the prompt box after a push") say the same. No such tool exists:
  `test_no_tool_writes_the_owners_prompt_box` asserts that `push_draft` is absent.
- **Guidance bounds differ.** The server allows 0..50 (`screen.GUIDANCE`, `build.py`). The web inputs clamp to 0..20
  (`run/Canvas.tsx:84,74`; `Card.tsx:88`). A tool-set guidance above 20 is accepted by the server. How the web input
  displays it was not run.
- **Box count vs `refCap`.** `run/Slots.tsx` always draws 3 boxes and `cast.BOXES = 3`. For a picture model `refCap` may
  be up to 6 (`ref_caps`), and `delivery.ts` and `inputs.ts:dropPlan` use `refCap` as the limit. Whether a 4th–6th
  reference can be placed but not shown was not checked at runtime. A clip model's `refCap` is clamped to the boxes
  (`models.py:183-185`), so for clips the question does not arise.
- **The "No Generate window is open" check** counts any bus line with role `workspace` (`screen.py:230`), not
  specifically a visible Generate tab. Whether every `workspace` line is a Generate window was not traced.
- **`last_seeds` reaches the web store.** `GET /draft` returns it (spread of the session dict), and
  `normalizeDraft` carries unknown keys through into the `draft` store. It is not typed in `Draft`. It is not sent
  back, because `put_draft` filters to `SESSION_FIELDS`. The UI reads seeds from the job summary instead.
- **`random_seed`** publishes `generate-image.draft` even when it changed nothing (no Advanced entry for the model).
- The e2e and unit descriptions here come from test titles and file headers, not from a run.
- **A clip cannot be dragged from the Grid onto a box.** `Slots.drop` continues a clip whose id is in the `MEDIA_DRAG`
  payload (`Slots.tsx:26-34`), but `Grid.onDrag` leaves clips out of that payload (`Grid.tsx:81-88`), so a drag from the
  Grid carries a clip only as `text/uri-list`. Continue is reached from the Media menu and bar, and from the `references`
  setting. No other element sets `MEDIA_DRAG`: the Tree's rows drag folders with `FOLDER_DRAG` (`Tree.tsx:96`).
- **The scene cap of 60 s is a guess.** No clip over a few seconds was continued on a real engine, so what a long source
  costs in memory is unmeasured (part 5, §5.4).
- **The clip path has run only against the fake engine.** The catalog facts (§2.10.1) are read from definitions that
  `tests/engine/fake_engine/` imitates; Stage 0's measurements of a real clip are not written down.
  Whether the real engine accepts `image_start` with `image_fit_mode "crop"` and a manifest list of absolute paths as
  built here is pinned by the fake only.
- **The two owner settings for clips live outside this module.** The memory profile for video models
  (`engine.profile_video`) and the sizes the size menu offers (`modules.generate-image.video_tiers`) are edited on Settings →
  Image engine (`web/src/shell/settings/CoreList.tsx:91-108`; helpers in `coreSettings.ts:1-16`), through `PATCH
  /api/settings` and `settings_edit.ui_patch` (`hub/settings_edit.py:11-14`); part 1, 5.2. A change to the sizes reaches the
  bar at its next use (§2.10.2); a change to the video profile takes effect at the next clip job (part 1, 1.5).
- The engine catalog fields used here (`block`, `ref_choices`, `guidance_key`, `defaults`, `lora_dirs`, `lora_extra`,
  `lora_recursive`, `status`, `base`) were taken from their use sites; their producer is `hub/worker/catalog.py:45-63`
  (`describe`). The clip fields (`kind`, `video`, `video_task`, `steps_range`) were read in the producer (§2.10.1).
- `hub/core/autoreg.py` was read only at its docstring and constants; the matching code was not traced.
