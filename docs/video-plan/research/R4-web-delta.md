# R4 — Web delta for Generate Video (MiniMax H3)

Scope: the browser side only (`web/src`, `web/tests`). It takes the blueprint
`docs/architecture/parts/08-video-blueprint.md` §4 (and the web parts of §2.8, §2.9, §2.12), checks it against the
code, and turns it into an exact plan. Where the code disagrees with the blueprint, the code wins and the
correction is marked **Correction**.

Read for this note: all of `web/src/modules/generate-image/**`, `shell/Workspace.tsx`, `shell/TopBar.tsx`,
`shell/registry.ts`, `shell/settings/*`, `screens/media/*`, `lib/*`, the `ui/*` used by Generate, `styles/tokens.css`,
`web/tests/unit/*` and `web/tests/e2e/{helpers.ts,fixtures/*}`.

The rules this plan has to keep (`web/tests/unit/guards.test.ts`):

- Every src and test file is ≤250 lines (`:22-25`). This counts test files and fixtures too.
- No `overflow: hidden`; only `[data-scroll]` scrolls (`:27-32`).
- px only for 1px hairlines; no px font sizes; no inline `fontSize` (`:40-53`).
- Banned copy (`:55-61`), e.g. "detected", "generations appear here".
- No `console.`, no `localStorage`/`sessionStorage`, no absolute URLs (`:63-69`).
- A module imports only react, `ui/`, `lib/` and its own folder (`:71-81`).

The constraint for this work: Generate Image must not be contaminated. Anything both screens use is
**lifted** into `web/src/lib` (logic) or `web/src/ui` (components). Generate Image then imports it from there in the
same commit, and its tests stay green. Nothing is imported across modules, and nothing is copied.

---

## 0. Findings the blueprint missed (read first)

These come from how the Workspace mounts tabs, and each one is a bug the moment a second Generate tab exists.

1. **Both tool panels stay mounted.** `Workspace.tsx:43-50` renders every tab's panel and only sets `hidden` on the
   ones not shown. So Generate Image and Generate Video run their effects at the same time.
2. **The socket declaration is last-writer-wins.** `bus.declare` stores one `lastSockets` per window
   (`lib/bus.ts:206-209`) and re-sends it on every welcome (`:121`). Generate Image declares from an effect with no
   visibility gate (`generate-image/sockets.ts:46-52`). With two panels, whichever effect ran last owns Media's Send,
   whatever tab is on screen. **Fix:** the lifted `useSockets` takes `visible`, declares only while visible, and
   re-declares when its tab becomes visible.
3. **Every panel hears every `deliver`.** `useBusEvent('deliver', …)` (`sockets.ts:53-55`) never checks `del.tool`.
   A delivery meant for Generate Video would also be placed in Generate Image's boxes, and both would send a receipt.
   **Fix:** the lifted handler ignores a delivery whose `tool` is not its own.
4. **Global DOM queries in Generate Image.** The sheet's focus and Escape handling use
   `document.querySelector('[data-region="model-picker"]' / '[data-region="library-toggle"]')`
   (`GenerateImage.tsx:61,65`). With two panels these find the first match in the DOM, which may be in the hidden
   tab. **Fix:** the lifted layout scopes the queries to its own panel through a ref.
5. **Duplicate element id.** The prompt textarea has `id="prompt"` (`compose/PromptBox.tsx:119`). Seven e2e specs
   use `#prompt`. **Fix:** the lifted PromptBox takes an `id` prop. Generate Image keeps `prompt`; Generate Video uses
   `video-prompt`.
6. **Media's Generate button picks the first module that has `queue`** (`screens/media/Bar.tsx:14`). With two
   modules, Media would always queue Generate Image. **Fix:** pick the focused tool (`focus.tool` from `lib/live`) when
   it has `queue`, and fall back to the first one. With no focus (as in the current e2e) the behaviour is unchanged.
7. **New chat clears only Generate Image's words on the client.** The server's `chat.cleared` reaches every module
   (blueprint §3.6). But `newChat()` calls only Generate Image's `clearWords`/`settled` (`chat/assistant.ts:42-45`).
   **Fix:** the lifted assistant keeps a list of registered clearers. Each draft store registers itself.
8. **There is one conversation.** The chat store is per window and the server has one chat. The lifted Chat column
   therefore shows the same conversation in both tabs. This is intended (the assistant routes "clip" vs "picture"
   requests, blueprint §5.2), and it is visible on screen.
9. **The lib/ui → modules direction is not guarded.** The guard checks only `src/modules/` imports. After the lift,
   nothing stops `lib/` or `ui/` from importing a module back. **Add** a guard: `src/lib` and `src/ui` never import
   from `src/modules`, `src/screens` or `src/shell`.

---

## 1. Lift list

`L` numbers are lifts. Each lift is one commit: create the shared file, switch Generate Image to it, delete the old
code, and keep `npm test` + `npm run e2e` green.

**Rules for every lift:**
- `data-region`, aria labels, titles and visible text stay exactly as they are, so the 30 e2e specs pass unchanged.
- CSS custom properties (`--gen-bar-h`, `--gen-edge`, `--gen-bar-ctl`, `--gen-bar-fs`) keep their names. They move
  into the lifted layout's CSS and are inherited by the lifted pieces.

### 1.1 Table

| # | From (generate-image) | To | Parameters (what becomes an argument) | Generate Image files changed |
|---|---|---|---|---|
| L1 | `api.ts`: `upload`, `check`, `itemThumb`, `itemPath` | `lib/items.ts` (~20) | none. These are **core** routes (`/api/upload`, `/api/media/check`, `/thumbs/…`), and module api files should not have held them | `api.ts` (32→18), `inputs.ts`, `sockets.ts` |
| L2 | `compose/triggers.ts` | `lib/phrases.ts` (24) | none (pure) | `compose/PromptBox.tsx` |
| L3 | `compose/complete.ts` (`Character`, `characterList`, `matchesAt`, `place`) | `lib/characters.ts` (~35) | URL becomes core `GET /api/characters` (blueprint §3.7). The `picker` store does **not** move (see L11) | deleted |
| L4 | `run/jobs.ts` (`queueView`, `runningText`, `doneText`) | `lib/queueView.ts` (~55) | `queueView(all, tool)`, `doneText(n, seconds, noun)`, `runningText(j, {noun})`. Adds a decode phase (§2.4). `lastSeeds(all, tool)` is lifted from `run/Seed.tsx:18-20` | `run/jobs.ts` keeps only `generateLabel` (moved into `run/Taskbar.tsx`; file deleted) |
| L5 | `blocking.ts` generic lines + `useGenerate.ts` hook body | `lib/press.ts` (~60) | `pressHead({linkOn, engineOffline, hasModel, prompt, max})` returns link, engine, "Choose a model", "Write a prompt", too long. `pressTail({uploading, waiting, queueMax, waitText})`. `usePressState(tool, uploading)` returns `{linkOn, engineOffline, waiting}`. `submit(tool, kind, params)` toasts a refusal. `EMPTY_DRAFT_TEXT` | `blocking.ts` (31→~20, keeps the modes/refCap lines in the same order), `useGenerate.ts` (37→~20), `queue.ts` |
| L6 | `draft.ts` | `lib/draftStore.ts` (~100) | `createDraftStore<D>({ load, save, event, empty, normalize, sessionKeys, follow? })` returns `{ draft, ready, edit, settled, clearWords, load }`. `event` is `'generate-image.draft'` or `'generate-video.draft'`. `sessionKeys` is the set reset on a new session (image: prompt, draft, references, selected). `follow` is image's "references changed → followDefaults" hook. It registers its `clearWords`/`settled` with L7 | `draft.ts` (94→~25: config + re-exports `draft`, `draftReady`, `edit`, `loadDraft`, `settled`, `clearWords` under the same names, so `defaults.test.ts`, `Card.tsx` and `shell/settings/ImageModels.tsx` are untouched) |
| L7 | `chat/assistant.ts` | `lib/assistant.ts` (~60) | `useAssistant()` is fed once per window (a module-level guard, so two panels make one GET). `say(text)` returns `Promise<string \| null>` (the error text) instead of writing into Generate Image's `note`. `onNewChat({clearWords, settled})` registers a clearer. `newChat()` clears all, waits for all `settled()`, then DELETEs. Its error goes to `toast` | `chat/assistant.ts` deleted |
| L8 | `chat/Chat.tsx` + `Chat.module.css` | `ui/Chat.tsx` (59), `ui/Chat.module.css` (26) | none: it reads `lib/assistant` | deleted |
| L9 | `chat/Article.tsx` + `Article.module.css` | `ui/Pager.tsx` (~85), `ui/Pager.module.css` (26) | `{ text, onClear, empty? }`. It stops reading the draft store | deleted. `chat/` folder gone |
| L10 | `run/BarMenu.tsx` + its classes (`.barBtn .square .menuPop .menu .option .optionOn`) | `ui/BarMenu.tsx` (38), `ui/BarMenu.module.css` (~12) | unchanged API (blueprint W1 is right) | `run/Canvas.tsx`. **Correction:** `Run.module.css:53` `.option > .ar { width: 1rem }` is a cross-class selector that stops matching once `.option` lives in another CSS module. Replace it with a class on the shape itself (`.arOpt`) |
| L11 | `compose/PromptBox.tsx`, `compose/Picker.tsx`, prompt and picker rules of `Compose.module.css` | `ui/PromptBox.tsx` (~125), `ui/Picker.tsx` (~25), `ui/PromptBox.module.css` (~30) | `{ id, value, onChange, max, words, busy, onSend: (t) => Promise<boolean>, onCharacter: (c) => void }`. Tab completion, the Enter/Shift+Enter/Escape handling and the tint mirror move whole. The picker becomes component state (`useState`), so two boxes never share tiles. **Correction to blueprint §4.2:** PromptBox *can* be lifted whole. The LoRA tint is only a `words` list (video passes `[]`). A separate video `Compose.tsx` would copy about 80% of it | `compose/PromptBox.tsx`, `Picker.tsx` deleted. A new `run/Prompt.tsx` (~25) binds draft.prompt, the LoRA trigger words, `say`, `note` and `addCharacter` |
| L12 | `compose/ModelPicker.tsx` + `.model .menu* .option` rules; `Card.tsx`'s `DefaultPicker` + `NOT_SET` + `Card.module.css .pick` | `ui/ModelPicker.tsx` (~75), `ui/ModelPicker.module.css` (~20) | generic `<M extends {id,label,family}>`. `onOpen?` replaces the hard `loadModels()`, and `onSettings?` replaces the `useBusEvent('settings', …loadLoras)`. `none?: string` adds the "Not set" row with its empty-family heading hidden (from `Card.module.css:4-6`) | `compose/` folder gone; `Card.tsx` (72→~60); `library/LoraLibrary.tsx` import |
| L13 | `run/Slots.tsx` (the `Slot` markup, BOXES=3, note line) + slot rules `Run.module.css:57-74`; `inputs.ts` generic parts (`dropPlan`, `imageSize`, the `uploading/flashing/slotNote` stores, `note`, `flash`) | `ui/RefBoxes.tsx` (~60), `ui/RefBoxes.module.css` (~20); `lib/refs.ts` (~55): `createRefState()` returns `{uploading, flashing, slotNote, note, flash}`, plus pure `dropPlan`, `imageSize`, type `Slot` | RefBoxes: `{ refs: {id}[], cap, label(i) => string, emptyTitle(i), state, onDrop(e, i), onRemove(i) }`. **Correction to blueprint W2:** the note line and the flash state must move with the boxes. Each module needs its own state instance (factory), because both bars are mounted | `run/Slots.tsx` (56→~25), `inputs.ts` (119→~65), `delivery.test.ts` imports `dropPlan` from `lib/refs` |
| L14 | `delivery.ts` (`declaration`, `planDelivery`) + `sockets.ts` (`receive`, `useSockets`) | `lib/sockets.ts` (~95) | `useSockets({ tool, visible, filled, cap, mode, place(index, slot), flash })`. Declares only while `visible` (finding 2). Drops a `deliver` for another tool (finding 3). Refuses an item whose `kind` is not `image` before `/api/media/check` | `delivery.ts`, `sockets.ts` deleted. `GenerateImage.tsx` calls it with `visible` (~6 lines). `delivery.test.ts` → imports `lib/sockets` |
| L15 | `run/Queue.tsx` + queue rules `Run.module.css:76-88` | `ui/JobLine.tsx` (~75), `ui/JobLine.module.css` (~16) | `{ tool, noun: 'image' \| 'clip', fallback }` | `run/Queue.tsx` deleted |
| L16 | `run/Seed.tsx` markup + `.seed*` rules | `ui/SeedLine.tsx` (~30) (styles in `JobLine.module.css`) | `{ seeds, kept, onKeep, onRandom }`. The module computes `seeds` with `lastSeeds(jobs, TOOL)` (L4) and `kept` from its own draft | `run/Seed.tsx` (40→~20) |
| L17 | `run/Canvas.tsx` `Steps` and `Guidance` markup (number + two arrows) + `.steps .number .arrows` | `ui/Nudge.tsx` (~30), `ui/Nudge.module.css` (~12) | `{ label, value, min, max, step, nudge, more, fewer, region, onChange }`. Keeps `aria-label`s "More steps", "Fewer steps", "More guidance", "Less guidance" and `data-region` "steps", "guidance" | `run/Canvas.tsx` (85→~60). `Count` stays in Generate Image (video has no count) |
| L18 | `run/Taskbar.tsx` right half (Live, instances menu, utilities fold-up, Generate button) + `.bar .controls .barIcon .go .liveFlat` | `ui/RunBar.tsx` (~60), `ui/RunBar.module.css` (~25) | `{ fold: {open, tip, region, onToggle}, controls: ReactNode, press: {reason, go}, goLabel, randomSeed: () => Promise<unknown> }` | `run/Taskbar.tsx` (68→~30) |
| L19 | `GenerateImage.tsx` layout + `GenerateImage.module.css` + `run/Dock.tsx` + the sheet focus/Escape effect | `ui/Workbench.tsx` (~65), `ui/Workbench.module.css` (~25) | `{ page, prompt, status, side, sheet, sheetOpen, onSheet, bar }`. It renders `.work/.main/.side/.sheetBox`, the dock grid (prompt box over one status line) and the sheet. Focus and Escape are scoped to its own root (finding 4). The sheet's first-focus target is `[data-sheet-first]`, not `model-picker` | `GenerateImage.tsx` (86→~60), `GenerateImage.module.css` and `run/Dock.tsx` deleted |

Not lifted (stays in Generate Image only): the LoRA sheet (`library/*`, `loras.ts`, `Cover.tsx`), `edits.ts`,
`job.ts`, `modelList.ts` (image defaults policy), `run/Canvas.tsx` (`AspectMenu`, `SizeMenu`, `Count`), `blocking.ts`'s
mode/refCap lines, `queue.ts`, `Card.tsx`.
- **LoRA sheet?** No. H3 turbo LoRAs are out of the primitive (blueprint §1.5). If they come later, the LoRA list is
  lifted then, not now (no zombie).

`hasPhrase` (`triggers.ts:23`) is used only by `triggers.test.ts`. When L2 moves the file, drop it and its test
line, or keep it in `lib/phrases.ts` with the test. Pick one; do not carry an unused export silently.

### 1.2 Line budgets after the lifts

There are no source files near 250 today (the largest in scope is `lib/bus.ts` at 233, and it is untouched). The
budget pressure is in tests:

| File | Now | After | Action |
|---|---|---|---|
| `tests/e2e/fixtures/api.ts` | 208 | 211 | One line routes `/api/generate-video/*` to a new `fixtures/video.ts`. One field `video: VideoState` in `ApiState`. The characters route is renamed to `/api/characters` |
| `tests/e2e/fixtures/controller.ts` | 129 | ~150 | `tools` option, video `job.submit`, focus label and `deliver.tool` from the declaring tool (§5.2) |
| `tests/e2e/fixtures/data.ts` | 53 | ~95 | `VIDEO_MODELS`, `videoSummary`, clip items |
| `tests/e2e/settings.spec.ts` | 249 | 249 | Do not touch. The video card spec goes in its own file |
| `tests/e2e/seed-guidance.spec.ts` | 234 | 234 | Unchanged (the Nudge labels are kept) |
| `tests/e2e/tab-complete.spec.ts` | 224 | 224 | One URL string changes (`/api/generate-image/characters` → `/api/characters`) |
| `screens/media/Media.tsx` | 149 | ~162 | Clip switch, clip-aware menu, Space |
| `screens/media/Grid.tsx` | 113 | ~122 | Clip tile |
| `tests/unit/misc.test.ts` | 88 | ~95 | `queueView(all, 'generate-image')`, `doneText(…, 'image')` |

### 1.3 Unit tests that move

- `complete.test.ts` → imports `lib/characters`.
- `triggers.test.ts` → imports `lib/phrases`.
- `misc.test.ts` → `queueView`, `runningText`, `doneText` from `lib/queueView`. `generateLabel` is imported from
  `modules/generate-image/run/Taskbar` (or that one test line moves into the image module's own test).
- `delivery.test.ts` → `declaration`, `planDelivery` from `lib/sockets`, and `dropPlan` from `lib/refs`. Its
  `Draft`/`Model` fixtures stay image-typed and become the arguments of the generic functions.
- `blocking.test.ts`, `defaults.test.ts`, `job.test.ts`, `order.test.ts`: unchanged. They keep importing Generate
  Image's own modules, which keep their exports.

---

## 2. The Generate Video screen

### 2.1 Files (`web/src/modules/generate-video/`)

| File | ≈Lines | Role |
|---|---|---|
| `manifest.ts` | 10 | `id: 'generate-video'`, `label: 'Generate Video'`, `order: 20`, `load`, `queue`, `randomSeed` |
| `types.ts` | 45 | `VideoModel`, `Draft`, `Advanced`, `Aspect`, `TOOL = 'generate-video'`, `PROMPT_MAX = 4000`, `QUEUE_MAX = 10` |
| `api.ts` | 20 | `/api/generate-video/{models,draft,seed/random,defaults}` |
| `edits.ts` | 55 | `EMPTY_DRAFT`, `normalizeDraft`, `advancedOf`, `withAdvanced`, `resetAdvanced`, `withModel`, `placeRef`/`removeRef`, `withLength`, `followDefaults` |
| `length.ts` | 30 | Pure: the model's legal lengths come from the server; `snap(seconds, model)` (up, clamped to the model's range); `label(frames, fps)` |
| `draft.ts` | 25 | `createDraftStore` config (L6), event `generate-video.draft` |
| `modelList.ts` | 35 | Model list + `{text, refs}` defaults (video's own policy, same shape as image's) |
| `job.ts` | 40 | Pure: the payload of one press |
| `blocking.ts` | 20 | `pressHead` + video lines (reference cap, "takes no references") + `pressTail` |
| `useGenerate.ts` | 20 | `usePressState` + `submit(TOOL, 'video', buildJob(...))` |
| `queue.ts` | 20 | Media's Generate (manifest `queue`) |
| `inputs.ts` | 50 | `createRefState()`; Media tiles/files into the boxes; `addCharacter` |
| `GenerateVideo.tsx` | 65 | `Workbench` with Pager, PromptBox, JobLine/SeedLine, Chat, model sheet, `VideoBar` |
| `run/VideoBar.tsx` | 45 | `RunBar` with the controls below |
| `run/Controls.tsx` | 80 | `ResolutionMenu`, `AspectMenu`, `Length`, `Steps` |
| `run/ModelSheet.tsx` | 45 | The raised sheet: `ModelPicker` and the model's facts |
| `run/Seed.tsx` | 20 | `SeedLine` bound to this draft |
| `Card.tsx` | 80 | Settings card (§4.4) |
| `Card.module.css`, `GenerateVideo.module.css` | ≤10 each | Only what is not in the lifted CSS |

None of these imports `modules/generate-image`. Each one uses `lib/`, `ui/` and its own folder only.

### 2.2 Layout (the same plan as Generate Image, through `ui/Workbench`)

- **Left (`compose`):**
  - `Pager` with the assistant's draft (`d.draft`, Clear → `edit(d => ({...d, draft: ''}))`).
  - Under it, the `PromptBox` (id `video-prompt`, `words=[]`, Tab completion puts the character's picture in the
    first open reference box).
  - Under that, one status line level with the bar: `JobLine tool="generate-video" noun="clip"`, with `SeedLine` as
    the fallback.
- **Right (`side`):**
  - The same `Chat` (finding 8), the raised sheet holding `ModelSheet`, and the one-line `VideoBar` in the bottom
    right corner.
- Ctrl+Enter → `useCtrlEnter(gen.go, visible)`.
- Sockets → `useSockets({tool: TOOL, visible, …})`.

### 2.3 The bar, left to right

1. **Fold** (`data-region="model-toggle"`; tip "Raise the model" / "Lower the model"). It raises `ModelSheet`:
   - the `ModelPicker`, grouped by family, listing only the models the server offers;
   - then four plain facts from the model entry, as `t-meta` lines:
     - "References: first frame" or "References: identity, up to 3";
     - "Length 5.2–14.4 s";
     - "Steps 4–8";
     - "With sound".
2. **Reference boxes** (`RefBoxes`): always 3 boxes, struck through past `model.refCap`. The box title names what
   the picture does: `Reference 1 · first frame` on FL2VA, `Reference 1 · identity` on Omni. Pictures only: a dragged
   clip is refused with the note "Pictures only".
3. **Resolution** (`BarMenu`): the model's offered tiers (`480p`, `540p`, `720p` by default). The button shows
   `540p`. The hover hint is the size, e.g. `960 × 544`, read from the model's tier table for the current aspect.
4. **Aspect** (`BarMenu`): `16:9, 9:16, 1:1, 4:3, 3:4, 21:9`, the keys of the tier table. No `Auto` in the primitive
   (Open decision 3).
5. **Length** (`run/Controls.tsx` `Length`; `data-region="length"`):
   - It shows the snapped seconds to one decimal (`5.2 s`), with the same two small arrows as Steps (`ui/Nudge` in a
     text mode, or a sibling of it).
   - The arrows step through the model's legal lengths only. The aria labels are "Longer clip" / "Shorter clip".
   - Hover text: `124 frames · 24 fps`.
   - Typing is not offered: the lattice is coarse (14 values), so stepping is enough.
6. **Steps** (`ui/Nudge`): per model, bounded by the model's `steps.min/max` (fused: 4–8), defaults from the model.
7. **No count.** One clip per press (blueprint §3.3). Reasons:
   - a clip takes minutes on the single engine lane;
   - the queue cap already limits pressing again;
   - Media follows each landing.

   The Generate label is "Generate clip".
8. The `RunBar`'s right half, unchanged: Live, instances (inside HocusPocus Desktop), the utilities fold-up (Settings,
   Clear the GPU cache, Seed back to random → `/api/generate-video/seed/random`), and Generate.

**Seed** is not a bar control. As on Generate Image it lives:
- on the status line (`SeedLine`: click the last clip's seed to keep it, "Random" to let it go);
- in the Settings card (Random/Fixed + value).

This matches the task brief's "seed" without adding a bar field. Open decision 5 covers putting it in the bar anyway.

### 2.4 The job line for a clip (`lib/queueView.runningText` with `noun: 'clip'`)

| Phase | Left (bold) | Right (`t-meta`) | Progress line |
|---|---|---|---|
| no progress yet | `Starting` | — | indeterminate |
| `phase` matches `/load/i` | `p.text` or `Loading model` (H3 load is tens of GB: minutes) | — | indeterminate |
| steps running | `Rendering clip` | `step 7 of 20 · 35% · about 3 min` | `pct/100` |
| `phase` matches `/decod\|vae\|audio\|mux\|sav/i` | `Decoding` | — | indeterminate |
| done (4 s) | `Done · clip in 6 min` | | |
| waiting / held / failed / cancel | unchanged from Generate Image | | |

- For images, the steps row keeps today's text, `Generating k of N` and `p% · about t`, so `misc.test.ts` keeps
  passing.
- The decode row exists because the blueprint (§2.13) says steps stop at the end of denoising while VAE decode,
  audio and mux carry no steps. Without it the line would sit at "100%" for a long time.
- The phase strings the worker sends for H3 are **Unverified** (see the end).

### 2.5 Where the finished clip appears, and the preview decision

- A finished clip appears in **Media**:
  - the controller publishes `generation` with `kind: "video"` (blueprint §2.9);
  - Media prepends it and, unless 2+ tiles are selected, brings it up on the Stage (`selection.follow`).
  - The job line says `Done · clip in 6 min`.
- **Decision: no clip preview on the Generate screen.** Recommended over a small player on the job line:
  1. The job line is one row of `--gen-bar-h` (1.625rem). A player there is a thumbnail with controls too small to
     use. The blueprint's `ClipPreview` "above the bar" would cover the reply column.
  2. The rule is that Generate makes and Media shows. A second viewer is a second system to keep in step
     (sizes, codec errors, sound, keyboard).
  3. The clip has sound. A player in the workspace would compete with Media's, often on the other monitor.
  4. Media already brings the new clip up by itself, and it is usually open on its own monitor.
  5. It saves ~50 lines and an e2e surface.
- **Correction:** drop `run/ClipPreview.tsx` from blueprint §4.3. If a cue is asked for later on the Generate
  screen, the `Done · clip` text can become a link that focuses Media (`window.open('/media', …)` reuses the named
  window). That is a few lines, not a player.

---

## 3. Media changes for clips (`web/src/screens/media/*`; Media is a screen, so these files may share freely)

### 3.1 Types (`lib/protocol.ts`, `screens/media/media.ts`)

- `GenerationItem.thumb: string | null`, plus `seconds?: number`. `kind` is already a string (`protocol.ts:51-54`).
- `DraggedMedia` gains `kind?: 'image' | 'video'`. Missing means `image`, so old payloads still work.
- `JobSummary` gains `seconds?: number; frames?: number`. **Correction to blueprint §3.4:** the video summary must
  also carry `model_id`, `seeds: [seed]`, `loras: []` and `count: 1`, so `lastSeeds` (L4) and the job line work
  unchanged. The blueprint's summary has only `seed`.
- `MediaItem` gains `kind: 'image' | 'video'` and `seconds: number | null`.
  - A server item without `kind` is normalized to `image` in `loadTemp`, `loadMore`, `loadFolder` and
    `loadCharacters` (one `norm()` helper).
  - `fromGeneration` maps `g.kind` and `g.seconds`.

### 3.2 Stage and the new Clip view

- **Lift `fit` inside Media.** New `screens/media/fit.ts` (~12 lines, pure):
  `fit(W, H, w, h) → {s, x, y}`, i.e. `s = min(W/w, H/h)`, centred.
  - `Stage.tsx:28-39` calls it. No behaviour change, and the `fit.spec.ts` e2e stays green.
- **New `screens/media/Clip.tsx`** (~75 lines), mounted with `key={current.url}`:
  - `<video controls playsInline preload="metadata" src={url}>`. No autoplay, no loop, not muted: play starts on the
    play press. The blueprint's `loop` is dropped. **Correction:** a looping clip with sound repeats its audio and fights
    the "panel never moves" calm.
  - **Fit uses the item's `w`/`h` from the media list**, not the video's natural size. The tile and the box are laid
    out before (or without) a decode. This matters for e2e (§5.3) and for a codec that does not play.
  - **Fit area.** The Stage runs under the right column (`Media.module.css:7-8`). A full-width clip would put its
    native controls (volume, full screen, the right end of the timeline) under the thumbnails.
    - The Clip therefore fits into the board's width minus the column while the thumbnails are up. It measures
      `[data-region="side"]`'s left edge at each resize, the way `Edges.at` measures the counter.
    - With the thumbnails folded it uses the whole board, like an image.
  - No zoom and no pan. It gets no `data-wheel="stage"`, so `lib/lock.ts` keeps blocking Ctrl+wheel and Ctrl+0
    there.
  - The `shadow` and `outline` of `.stageImg` go on the video box (shared class).
  - Edge zones: not on a clip. The native timeline sits along the bottom and clicks belong to the player. The bar's
    previous/next still step.
  - `onError` shows one line on the Stage: `This clip's codec doesn't play here` (blueprint §8). The line is neutral
    and not banned.
- **`Media.tsx`:**
  - `current.kind === 'video' ? <Clip …/> : <Stage …/>` at `:133`.
  - **Keyboard:** Space toggles play/pause when the current item is a clip and focus is not in a field
    (`video.paused ? play() : pause()`). The arrows, Home/End, Enter, Del, F and Escape keep their Media meanings,
    because the window listener prevents the native seek.
  - Add to Characters is `off: 'Pictures only'` when any chosen item is a clip.
  - Favorite, move and delete work unchanged: they act on ids.

### 3.3 Grid tile

- **Decision: `<video muted playsInline preload="metadata" src={url + '#t=0.1'}>` now, server poster later**
  (blueprint §2.8). The browser draws the frame from the file, and nothing new is stored.
  - Grid is windowed (`gridMath.windowRange`, visible rows ±3 overscan), so about 20–30 tiles mount at once. Each
    makes one Range request.
  - Risk: Chromium allows 6 connections per host on HTTP/1.1, so a page of clips can delay thumbnails and API calls
    while metadata loads. If that shows, the blueprint's later memory-only WebP poster (worker → `ThumbStore`) is the
    fix, and the tile then switches back to `<img src={thumb}>` when `thumb` is non-null. Both branches are one
    ternary in `Grid.tsx`.
- The tile also gets:
  - a length badge (`5.2 s`, `num`, bottom right, styled like `.favMark`);
  - a small play glyph? No. The badge is enough.
- `draggable`: the payload carries `kind` (`Grid.tsx:81`).

### 3.4 Selection and send rules

- `send.ts` `sendState(linkOn, focus, presence, n, kinds)`: when no chosen item's kind is in the target sockets'
  `accepts`, the state is disabled with the reason `A clip cannot go in a reference box`. With a mix of pictures and
  clips, the label counts only the pictures, and the clips are refused by the tool's receipt.
- `useSend` and `Media.tsx` pass the chosen items' kinds.
- **Defence in depth**, already present server-side: delivery is refused by `accepts`
  (`hub/core/delivery.py:108`, blueprint §2.12), and `/api/media/check` accepts images only (`files.existing_image`,
  `hub/core/fileroutes.py:91-99`). The lifted `useSockets` (L14) also refuses non-image items before calling `check`.
- **Later:** a video reference socket (Omni `minimax_h3_references` type video, blueprint §1.2) would declare
  `accepts: ['video']`, and the same rules let a clip in. Nothing to build now.
- **Characters are unaffected.**
  - The server lists pictures only. `Characters.tsx` does not change.
  - A clip dropped on the Characters heading is refused early with the toast `Pictures only`. This is the
    `Tree.tsx` drop path: one check on the dragged `kind`.

### 3.5 Media's bar (finding 6)

`Bar.tsx`: `const tool = modules.find(m => m.id === focus?.tool && m.queue) ?? modules.find(m => m.queue)`. Both
`generate` and `Seed back to random` follow it, and the button title stays `tool.label`. `media-bar.spec.ts` passes
unchanged, because the FakeHub's focus is null until a workspace declares.

---

## 4. Draft and API shape

### 4.1 The draft (`modules/generate-video/types.ts`)

```ts
export type Aspect = '16:9' | '9:16' | '1:1' | '4:3' | '3:4' | '21:9'
export type Seed = { mode: 'random' } | { mode: 'fixed'; value: number }
export type Advanced = { steps: number; seed: Seed }
export type Draft = {
  model: string | null                       // disk
  seconds: number                            // disk; always a snapped value (frames / fps)
  resolution: string                         // disk; tier id, e.g. '540p'
  aspect: Aspect                             // disk
  advancedByModel: Record<string, Advanced>  // disk; steps and seed per model
  prompt: string                             // session: the prompt box
  draft: string                              // session: the assistant's draft, the text Generate renders
  references: Slot[]                         // session: {id, w, h} from lib/refs
}
```

- **Correction:** no `selected`. In Generate Image it is the selected LoRA row; with no LoRAs it would be dead.
- **`last_seeds`** is not a draft field. As in Generate Image, the web reads the last job's `summary.seeds` from the
  live jobs (`lastSeeds(jobs, TOOL)`). The server's `view()` exposes `last_seeds` to the assistant only.
- **Session reset** on a new session (L6 `sessionKeys`): `prompt`, `draft`, `references`.

### 4.2 The model entry (`GET /api/generate-video/models`)

```ts
export type VideoModel = {
  id: string; label: string; family: string               // 'H3 First / Last', 'H3 Omni'
  refCap: number                                          // 1 for FL2VA, 3 for Omni (boxes), 0 if none
  referencesAs: 'first frame' | 'identity' | null
  fps: number                                             // 24
  lengths: { frames: number; seconds: number }[]          // the legal one-pass lengths, ascending
  tiers: { id: string; sizes: Record<Aspect, [number, number]> }[]   // only the offered tiers
  steps: { min: number; max: number; default: number }
  sound: boolean
}
```

**Correction to blueprint §4.3 (`job.ts` "lattice snapping, which mirrors screen.py"):** the web must not encode
`17n+5`. The server sends the list of legal lengths and the tier sizes, and the web only picks from them. One source
of truth: Python's catalog. `length.ts` then reduces to:
- `snap(seconds, model)`: the first entry with `seconds ≥` the asked value, else the last;
- `frameHint(entry, fps)`.

### 4.3 Routes (mirrored from Generate Image; `api.ts`)

| Route | Body / answer | Image equivalent |
|---|---|---|
| `GET /api/generate-video/models[?rescan=1]` | `VideoModel[]` | `/api/generate-image/models` |
| `GET /api/generate-video/draft` | the merged draft (disk + session) | same |
| `PUT /api/generate-video/draft` | changed fields only (merge-PUT, L6) | same |
| `POST /api/generate-video/seed/random` | `{ok}`. **Correction:** missing from blueprint §3.2. Needed by `manifest.randomSeed`, the bar's utilities and Media's bar (§3.5) | same |
| `GET/PUT /api/generate-video/defaults` | `{ text: string \| null, refs: string \| null, tiers: string[] }`. `tiers` is the `tiers_offered` setting (Open decision 4) | `{text, refs}` |
| `GET /api/characters` | `{items: Character[]}` (core, blueprint §3.7) | replaces `/api/generate-image/characters` |
| `POST /api/media/check`, `POST /api/upload`, `/thumbs/…` | unchanged core routes (L1) | same |

**Job submit:** `bus.request('job.submit', { tool: 'generate-video', kind: 'video', params })`.
- The bare kind `video` resolves to `generate-video.video` (blueprint §2.10).
- `params` from `job.ts` `buildJob(d, model)`:

```ts
{ tool: 'generate-video', model, prompt: d.draft, frames, resolution: d.resolution, aspect: d.aspect,
  steps, seed: {mode:'random'} | {mode:'fixed', value}, references?: string[] }
```

- `frames` (an integer from `lengths`) is sent rather than `seconds`, so there is no float to round twice. The
  server checks that it is on the model's list. Width and height are **not** sent; the server derives them from
  tier + aspect.
- **Correction:** Generate Image sends width/height because it computes the canvas itself. Video does not own a
  tier table, so it should not send one.

### 4.4 Bus event

- The server publishes on lane `generate-video.changed` with type `draft` (prefixed by `ctx.bus.publish`,
  `hub/core/context.py:64-65`). The web listens to **`generate-video.draft`**, like `generate-image.draft`
  (`draft.ts:94`, publisher `generate_image/routes.py:58,148,161`).
- **Correction to blueprint §2.15:** "publishes its own `generate-video.changed`" names the lane. The event the
  windows hear is `generate-video.draft`.

### 4.5 Settings card (`modules/generate-video/Card.tsx`)

`shell/registry.ts:9` picks the card up by folder name. It shows only when `/api/cards` lists `generate-video`
(`Settings.tsx:19`), so no shell change is needed.

The card shows:
- **Default models:**
  - "Text to clip" and "Picture to clip" (`ModelPicker` with `none="Not set"`, L12);
  - when references change, the draft follows them, as in Generate Image (`followDefaults`).
- **Resolutions offered:**
  - a `Switch` per tier the catalog knows (480p, 540p, 720p, 768p, 1080p), saved to `/defaults.tiers`;
  - the bar lists only these;
  - a tier turned off while selected falls back to the first offered.
- **Per current model** (title = model label):
  - Seed (`Segmented` Random/Fixed + number);
  - Steps (`ui/Nudge`, the model's bounds);
  - "Reset to model defaults" when they differ.

  This is "defaults per model": the model's own default steps come from the catalog, and the override set on screen is
  kept per model in `advancedByModel` on disk.
- Like `shell/settings/ImageModels.tsx`, it does **not** list weight files. Video weights are not managed in the
  Hub (blueprint §3.2).
- Do not repeat `ImageModels.tsx:4-6`'s pattern of the shell importing module internals.

---

## 5. Tests

### 5.1 Unit (vitest, `web/tests/unit/`)

New files, each well under 250 lines:

- `draftStore.test.ts` (L6):
  - only changed keys are PUT;
  - a failed save retries and never strands a key;
  - `clearWords` drops unsaved prompt/draft;
  - a new session resets `sessionKeys` only;
  - a bus event reloads every field except unsaved ones.

  It uses a fake `load`/`save` and `createBus` with a fake socket, as `bus.test.ts` does.
- `assistant.test.ts` (L7): `newChat` calls every registered clearer and waits for every `settled` before the DELETE.
- `sockets.test.ts` (L14):
  - a hidden tool does not declare;
  - becoming visible declares;
  - a `deliver` for another tool is ignored;
  - a `video` item is refused with "Pictures only".
- `video.test.ts` (generate-video pure parts):
  - `snap` (5 → 5.17/124, 5.17 → 124, 14.4 → 345, 30 → 345, 0 → 124);
  - `buildJob` exact payload, without and with references, fixed seed;
  - `blockingReason` order (link, engine, model, empty, too long, references on a model with `refCap` 0, too many,
    uploading, queue);
  - `withModel` keeps per-model advanced;
  - `normalizeDraft` of `null` / an old shape.
- `media-clip.test.ts`:
  - `fit()`;
  - `norm()` (missing kind → image);
  - `fromGeneration` for a video;
  - `sendState` with kinds (clip only → disabled with the clip line; mixed → counts pictures).
- `queueView.test.ts`, or extend `misc.test.ts`:
  - `runningText` decode phase → indeterminate "Decoding";
  - steps with `noun: 'clip'` → "Rendering clip" and "step s of S";
  - `doneText(1, 360, 'clip')` → `Done · clip in 6 min`;
  - `lastSeeds` per tool.
- `guards.test.ts`: add the lib/ui direction guard (finding 9).

### 5.2 Fixtures to extend (`web/tests/e2e/fixtures/`)

- **`controller.ts` (FakeHub):**
  - Constructor `tools?: ToolInfo[]`, defaulting to today's single Generate Image, so the 30 existing specs see no
    video tab. `Workspace.tsx:18` hides modules the welcome does not list.
  - `focus.label` from the declaring tool, not the literal `'Generate Image'` (`:100`).
  - `deliver.tool` and `delivery.tool/toolLabel` from `focus.tool` (`:119,124`).
  - `job.submit` with `d.kind === 'video'`:
    - title `Clip · 5.2 s · H3 First / Last — Pruned`;
    - summary `videoSummary(model, seed, frames)`;
    - `tool: 'generate-video'`, `kind: 'video'`.
  - A `progress(id, phase, step, steps, pct)` helper to walk a job through load → steps → decode → done.
  - `generation(item)` to broadcast a landing to `media`.
- **`data.ts`:**
  - `VIDEO_MODELS`: `minimax_h3` (FL2VA, refCap 1, lengths 124…345, tiers 480/540/720, steps 1–100 default 20)
    and `minimax_h3_ref2va_fused_turbo` (Omni, refCap 3, steps 4–8 default 4);
  - `videoJob()`, `videoSummary()`;
  - `clipItems(n)`: FakeItem gains `kind` and `seconds`, ids `.mp4`, `thumb: null`.
- **New `video.ts`:** `/api/generate-video/{models,draft,defaults,seed/random}` with a `VideoState` in `ApiState`.
  The DELETE chat route also broadcasts `generate-video.draft` and empties `st.video.draft`'s prompt/draft.
- **`api.ts`:**
  - the `/(files|thumbs)/` route serves a `.mp4` id from `fixtures/clip.ts`;
  - `/api/characters` replaces `/api/generate-image/characters`.
- **New `clip.ts`:** a tiny base64 clip, a few frames generated once with ffmpeg (present on the dev box at
  `/usr/bin/ffmpeg`).
  - Playwright's bundled Chromium is believed to lack H.264/AAC (Unverified), so the fixture is VP8/WebM served
    with `video/webm` under the `.mp4` id. The layout assertions do not depend on it, because Clip fits by the
    item's `w`/`h` (§3.2).
  - A second route answers garbage bytes for the codec-error spec.
- **`helpers.ts`:** `openVideo(page, …)` builds a FakeHub with both tools and clicks the Generate Video tab.
  Locators in video specs are scoped to `#panel-generate-video`, because the hidden image panel's regions are still
  in the DOM.

### 5.3 Browser specs to write (Playwright; titles)

**`video-screen.spec.ts`**
- `Generate Video is its own tab after Generate Image, only when the hub lists it`
- `the video screen keeps the plan: page, prompt box, job line, reply column, one-line bar; nothing scrolls`
  (`rootScroll` = `ZERO`, `unnamedScrollers` = [])
- `the bar holds the model fold, three reference boxes, resolution, aspect, length and steps; no image count`
- `length steps along the model's lengths; the frame count is the hover text`
- `resolution names its size in the hover text; aspect changes it`
- `the model sheet rises over the replies, lists only video models and states what references do`
- `edits save after a second and follow generate-video.draft from the tool server`

**`video-press.spec.ts`**
- `Generate sends one video job: the draft, frames, tier, aspect, steps, seed`
- `Ctrl+Enter renders only the visible tab's draft`
- `Generate is blocked with an empty draft, no model, or more references than the model takes`
- `the job line walks loading, rendering with step and percent, decoding, then Done · clip`
- `the last clip's seed can be kept and let go`
- `Media's Seed back to random and Generate follow the focused tab`

**`video-tabs.spec.ts`** (the isolation specs)
- `switching tabs moves the socket declaration to the visible tool`
- `a delivery for Generate Video never lands in Generate Image's boxes`
- `New chat empties both tabs' prompt boxes and drafts`
- `the chat column shows the same conversation in both tabs`
- `Generate Image's payload is unchanged with Generate Video present`
  (the same `toEqual` as `generate.spec.ts:28-30`)
- `Escape lowers only the visible tab's sheet and gives focus back to its own fold`

**`video-settings.spec.ts`**
- `the Generate Video card sets the default models, the resolutions offered, and seed and steps per model`

**`media-clips.spec.ts`**
- `a clip tile is a video with its length, never an img`
- `a clip on the Stage has controls and fits left of the thumbnails, the whole board when they fold`
- `Space plays and pauses a clip; the arrows still step`
- `a clip cannot be sent to a reference box; Add to Characters is off for a clip`
- `a new clip lands at the top and comes up on the Stage, paused`
- `a clip that cannot play says so on the Stage`
- `Ctrl+wheel over a clip does not zoom the page or the clip`

**Existing specs:** unchanged, except the one URL in `tab-complete.spec.ts`.

`margins.spec.ts`, `scale.spec.ts` and `narrow.spec.ts` should also get a `@video` twin later, run with `openVideo`.
They are optional for the primitive.

---

## 6. Ordered task list

`S-…` are server prerequisites from the blueprint, done by the server-side plan.

| # | Task | Depends on | Files | Done when |
|---|---|---|---|---|
| W1 | Guard: lib/ui never import modules/screens/shell | — | `tests/unit/guards.test.ts` | the new test passes on today's tree |
| W2 | L1 core item helpers | — | `lib/items.ts`; image `api.ts`, `inputs.ts`, `sockets.ts` | tsc, unit, e2e green; `rg "api/media/check\|api/upload" src/modules` finds nothing |
| W3 | L2 + L3 phrases and characters (core URL) | S-characters (`GET /api/characters`) | `lib/phrases.ts`, `lib/characters.ts`; `compose/PromptBox.tsx`; fixture `api.ts`; `tab-complete.spec.ts` URL; `complete.test.ts`, `triggers.test.ts` | unit + `tab-complete`/`tab-references` specs green |
| W4 | L4 + L15 + L16 queue view, job line, seed line | — | `lib/queueView.ts`, `ui/JobLine.*`, `ui/SeedLine.tsx`; image `run/Queue.tsx`, `run/Seed.tsx`, `run/jobs.ts`, `Run.module.css`; `misc.test.ts` | `bar-line`, `generate*`, `seed-guidance` specs green; decode/clip unit cases pass |
| W5 | L5 press helpers | W4 | `lib/press.ts`; image `blocking.ts`, `useGenerate.ts`, `queue.ts` | `blocking.test.ts` unchanged and green; `generate-press`, `media-bar` green |
| W6 | L6 draft store factory | — | `lib/draftStore.ts`; image `draft.ts`; `draftStore.test.ts` | `defaults.test.ts` and `generate-freeze.spec.ts` green; new unit green |
| W7 | L7 + L8 + L9 assistant, chat, pager | W6 | `lib/assistant.ts`, `ui/Chat.*`, `ui/Pager.*`; image `GenerateImage.tsx`, `chat/` deleted, `compose/PromptBox.tsx` (`say`) | `chat`, `article` specs green; `assistant.test.ts` green |
| W8 | L10 + L17 + L18 bar menu, nudge, run bar | — | `ui/BarMenu.*`, `ui/Nudge.*`, `ui/RunBar.*`; image `run/BarMenu.tsx` deleted, `run/Canvas.tsx`, `run/Taskbar.tsx`, `Run.module.css` (`.arOpt`) | `bar-controls`, `bar-line`, `seed-guidance`, `lock` specs green; Run.module.css holds only aspect/count rules |
| W9 | L13 + L14 reference boxes, ref state, sockets with `visible` | W2 | `lib/refs.ts`, `lib/sockets.ts`, `ui/RefBoxes.*`; image `inputs.ts`, `run/Slots.tsx`, `GenerateImage.tsx`, `delivery.ts`/`sockets.ts` deleted; `delivery.test.ts`; `sockets.test.ts` | `tab-references`, `media`, `shot*` specs green; hidden-tab and foreign-tool unit cases pass |
| W10 | L11 + L12 prompt box, picker, model picker | W3, W7 | `ui/PromptBox.*`, `ui/Picker.tsx`, `ui/ModelPicker.*`; image `run/Prompt.tsx` (new), `compose/` deleted, `Card.tsx`, `library/LoraLibrary.tsx` | `tab-complete`, `generate-models`, `library-sheet`, `settings` specs green |
| W11 | L19 workbench layout | W7–W10 | `ui/Workbench.*`; image `GenerateImage.tsx`, `GenerateImage.module.css` and `run/Dock.tsx` deleted | `margins`, `narrow`, `scale`, `library-sheet` specs green; `regionRects` unchanged |
| W12 | Media follows the focused tool | — | `screens/media/Bar.tsx` | `media-bar.spec.ts` green |
| W13 | Protocol + media item kinds | S-kinds (server sends `kind`, `seconds`, `thumb: null`) | `lib/protocol.ts`, `screens/media/media.ts` | tsc; `media*` specs green; `norm` unit |
| W14 | Media clips: fit, Clip, tile, send rules, Space, Characters off | W13 | `screens/media/{fit.ts,Clip.tsx,Stage.tsx,Grid.tsx,Media.tsx,send.ts,useSend.ts,Tree.tsx,Media.module.css}`; fixtures `clip.ts`, `data.ts`, `api.ts` | `media-clips.spec.ts` green; `fit.spec.ts` unchanged and green |
| W15 | Video module skeleton: manifest, types, api, edits, length, draft, modelList, layout, bar without Generate, model sheet | W4–W11; S-video routes (`/models`, `/draft`, `/defaults`, `/seed/random`) | `modules/generate-video/*` (§2.1); fixtures `video.ts`, `controller.ts` `tools` option, `helpers.ts` `openVideo` | `video-screen.spec.ts` green; existing 30 specs unchanged |
| W16 | Video press: job, blocking, useGenerate, queue, Generate, Ctrl+Enter, job line `clip` | W15; S-build (`generate-video.video` job kind) | `job.ts`, `blocking.ts`, `useGenerate.ts`, `queue.ts`, `run/VideoBar.tsx`; FakeHub video `job.submit`/progress | `video-press.spec.ts` green; `video.test.ts` green |
| W17 | Video references: boxes with model caps, Media send/drag, Tab → first frame/identity | W9, W16; S-cast (blueprint Stage 4) | `inputs.ts`, `GenerateVideo.tsx` (`useSockets`) | `video-tabs.spec.ts` green |
| W18 | Video Settings card | W15; S-defaults (`tiers`) | `Card.tsx`; fixture `api.ts` CARDS entry, `video.ts` | `video-settings.spec.ts` green |
| W19 | Sweep | all | — | `rg` finds no second copy of any lifted function. No file >250. `npm test`, `npm run e2e`, `npm run build` green. The build's dist has no external URL |

How this maps onto the blueprint's stages:
- W1–W12 are Stage 1 (lifts, no new tab). W13–W14 can land in Stage 1 as soon as the server sends `kind`.
- W15 and W18 are Stage 2.
- W16 is Stage 3.
- W17 is Stage 4.

### Leaving room for a later "Image | Video" switch (not built)

The "Generate Image" tab label is a placeholder, and a switch may later sit at the top of the bar.
This plan leaves room for it without building any of it:
- Each Generate screen stays one self-contained component taking `visible` (`ToolProps`), with:
  - its sockets gated on `visible` (W9);
  - Ctrl+Enter gated on `visible`;
  - its DOM queries scoped (W11).

  A parent that shows one of two such screens therefore needs no change inside them.
- The switch would most naturally be a `Segmented` in `TopBar` grouping modules that share a future manifest key
  (e.g. `group: 'generate'`), or a row at the top of the Workbench's side column. That column's grid
  (`minmax(0,1fr) auto`) would gain one `auto` row above the chat.
- Neither key nor row is added now (no zombie). The Workbench keeps its slots as props, so adding a `head` slot later
  is one prop.
- Both manifests keep their own `id`. The server tab labels and orders (10, 20) stay the source of truth, so merging
  tabs later is a TopBar change only.

---

## Open decisions

1. **Clip preview on the Generate screen.** Recommended: none (§2.5). The alternative is a 1-line "Done · clip"
   link that brings up Media.
2. **Media tile poster.** Recommended: `<video preload="metadata">` now, the server WebP poster only if many clips
   prove slow (§3.3).
3. **Aspect `Auto`** for FL2VA first-frame jobs (use reference 1's shape, as Generate Image does). Off in the
   primitive. It needs the server to snap an arbitrary ratio to the nearest tier aspect.
4. **Where `tiers_offered` is edited.** In the card through `/defaults.tiers` (proposed), or only in `settings.json`
   (blueprint §3.3), in which case the card shows it read-only.
5. **Seed in the bar** (as the task brief lists) vs on the status line and in the card (as Generate Image does).
   Proposed: same as image, for one behaviour across tabs.
6. **One conversation for both tabs** (finding 8). Proposed: keep it. The assistant routes by the chat message's words.
7. **`hasPhrase`**: delete it with its test line, or keep it tested in `lib/phrases.ts` (§1.1).
8. **Mixed send** (pictures and clips selected): place the pictures and refuse the clips (proposed), or refuse the
   whole send.
9. **The fold's region name** for the video sheet: `model-toggle` (proposed), or reuse `library-toggle`.
10. **Server job params**: `frames` (proposed) vs `seconds`, and no width/height (§4.3). These must be agreed with the
    server-side builder before W16.

## Unverified

- The `phase` strings the worker forwards during an H3 job (load, denoise, VAE decode, audio, mux). §2.4's regexes
  are guesses until a Stage 0 run is logged by the job line's own `progress` objects (no new logging).
- That Playwright's bundled Chromium cannot decode H.264/AAC (and so needs a WebM fixture), and that a `.mp4` id
  served as `video/webm` is accepted by `<video>`.
- That `preload="metadata"` plus `#t=0.1` draws a frame in the tile in the desk's browser (HocusPocus Desktop's
  engine), and how 20–30 tile requests behave on HTTP/1.1.
- That native `<video>` controls stay usable at the Media window's sizes and with `lib/lock.ts`'s Ctrl+wheel and Ctrl
  +/- block (the lock calls `preventDefault` on the window; the player's own keys may differ by engine).
- That the controller's focus label comes from the module title (FakeHub hard-codes it; the real code was not read
  here).
- That a second `useAssistant()` subscriber and a second `bus.on('welcome')` draft loader add no visible request
  burst on reconnect beyond one extra `GET /api/generate-video/draft`.
- That no e2e spec acts in the moment between page load and the first welcome, when both panels are briefly mounted
  (`Workspace.tsx:18` shows all modules until `tools` arrives). If a strict-locator flake shows, the Workspace can
  wait for `tools` before mounting panels.
- Line counts after the lifts are estimates from the current files. Each lift's commit is checked by the 250-line
  guard.
