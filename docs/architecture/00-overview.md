# The Hub — Architect's Guide

> **Status 2026-10-17:** the engine is upstream WanGP 18.05 at `<prefix>/engine/app`, not the HocusPocus fork named below; the invariants in §0.3 stand; the “not built” list is of 2026-10-14. State: `HANDOFF.md`. The decisions that hold are in `PLAN.md` and `docs/video-plan/BLUEPRINT-director.md`.

This guide is the blueprint for anyone — a person or another session — who has to understand, extend or
rebuild the Hub without having lived through its construction. It is written from the code at this commit;
every statement in parts 1–6 cites a file and, where it matters, a line. Part 8 records the video work (what is built, the
roadmap through Stage 11, and the earlier full-module design kept as a dated reference) and marks every design choice not yet built as *Proposed*. Nothing here is a wish; where a fact could not be
confirmed from code it is listed under *Gaps / unverified* at the end of each part.

## 0.1 What the Hub is, in one paragraph

A single Python process (Starlette, uvicorn, port 42010) on the server machine drives one generation engine
— the Wan2GP engine as carried by the HocusPocus fork (WanGP 10.9875, a Maestro descendant) — through a
worker process it owns, and serves one React client (the Workspace at `/`, the Media window at `/media`,
pairing at `/pair`) to the desk's client and to any browser on the LAN. Three
feature modules sit on a small core: **Generate Image** (the draft, the bar, the LoRA sheet, the render),
**Media** (Temp, the Drive, the Characters, and the Clips section), and the **Assistant** (the chat box that talks to
Open WebUI, and the MCP tool server through which Open WebUI's model drives the screens). The core owns the
engine, the files, the bus, the jobs, the settings, pairing and the MCP endpoint; modules declare what they
have (routes, a tab, a card, a screen's settings, listings, actions) and the core publishes it. A fourth module,
**Storyboard**, is declarations only and is switched off by default (`modules_disabled`, part 4, 4.9). A fifth, **Sequence** (the Edit Video tab: sequences of clips, played and joined into one clip; Stage 11).

## 0.2 The map

```
hub/
  __main__.py, server.py            process entry, uvicorn
  settings.py, settings_edit.py, pathrules.py   the settings on disk, the Settings screen's edits, path rules
  core/                              owns everything shared — never imports a module
    api.py        Ctx, Module, Setting, Screen, Listing, Action, Files protocol, Invalid, JobPlan
    registry.py   validates module declarations; features.py generates the MCP tools from them
    runtime.py    Core: wires services, loads modules, settles settings
    bus.py/line.py  websocket lanes, presence, sessions (15 s grace)
    jobs.py       lanes, submit (`job.submitted.by`), progress rate, terminal cleanup
    engine.py, enginecat.py   the worker's owner; outputs landing (a clip lands flat in its day)
    enginelane.py LaneMemory: the worker is released before a model switch and after every clip
    plan.py, vram.py   the run-or-release decision and the learned peaks
    files.py, drive.py, characters.py, clean.py, thumbs.py   roots out/drive/chars/clips; metadata strip; in-memory thumbs
    named.py, temp.py   named pictures and the one PNG text field's folders; Temp regroup (Favorites), file_clip, newest_temp
    checks.py, clipplan.py   plain-value checks shared by modules; a clip's plan
    clip.py, pngtext.py   MP4 tag blanking and facts at landing; the one PNG text field (character and cell notes)
    enginequery.py        the catalog and engine queries split out of engine.py
    mcp.py        the MCP endpoint (JSON-RPC subset) for Open WebUI
    fileroutes.py, routes.py, web.py   /files, /thumbs, /api/upload, /api/media/check, /api/settings, /api/cards, dist
    devices.py    pairing
  worker/                            the engine process: wan2gp.py (the session loop), wgpconfig.py (forced config),
                                     catalog.py + catalogvideo.py (the catalog, image and video entries), engineapi.py (the
                                     Hub-side types and the Adapter protocol), adapters/ (fork, upstream: the only files
                                     that name an engine key family), enginedump.py (--dump-engine), probe.py
                                     (--probe-continue), protocol, netguard
  modules/
    generate_image/   screen.py (settings), routes.py (draft), build.py (JobPlan), chain.py (Continue), tools.py, cast.py, models.py
    storyboard/       declarations only, off by default: screen.py, cells.py, render.py (eight tools)
    loras/            the LoRA folders, strengths, list_loras
    media/            routes.py, library.py, favorites.py
    assistant/        chat.py, link.py, remote.py, turns.py, settings.py, routes.py
    network/          the Network card
web/src/
  lib/     bus, live stores, store, http, protocol, desktop, keys, toast
  ui/      Menu, Scroll, Button, Icon, Progress, Live
  shell/   Workspace, Frame, settings screens
  modules/generate-image/   chat/ compose/ run/ library/ + draft.ts, job.ts, inputs.ts, …
  modules/assistant/, modules/network/
  screens/media/, screens/pair/
```

Parts: **01** the core · **02** Generate Image · **03** Media · **04** the Assistant and MCP · **05** the engine,
the worker and the lineage (Maestro → HocusPocus → Hub) · **06** the web frame, build, tests, release ·
**07** external programs and the rebuild order · **08** video: what was built, the roadmap, the parked full module.

## 0.3 The invariants (what every change must keep)

1. **Modules import only `hub.core.api` and their own package; the core never imports a module.** Enforced by
   `tests/core/test_rules.py`. Anything two modules need is lifted into the core, never copied.
2. **A picture is its pixels.** Every output and upload is rewritten without metadata (`hub/core/clean.py`);
   the engine is forced to write none (`hub/worker/wgpconfig.py:18-20` FORCED_CONFIG; FORCED_TASK in the adapters, `hub/worker/adapters/fork.py:24`, `upstream.py:22`). The one exception is
   two fields, notes and voice, Characters only: the notes on a character (PNG `Description`) and the words
   for the character's voice (PNG `Voice`) in the Characters folder (part 3); a storyboard cell's text may use the
   `Description` field once `paths.storyboards` is set (part 8). A sound is its sound: every engine WAV
   keeps only `fmt `, `fact` and `data` (`hub/core/sound.py`).
3. **Nothing of a session is remembered.** Prompt box, draft, references, chat, last seeds: memory only, gone
   15 s after the last window leaves. On disk: the settings (`settings.json`, `draft.json`,
   `openwebui.json`, defaults, devices), Temp pictures, and the sequence files (`<data>/clips/sequences/<name>.json`:
   clip ids, order and in and out points only, Stage 11), nothing else. No logs anywhere.
4. **The Hub fetches nothing.** The worker runs offline (`netguard.py`); a missing weight fails the job.
5. **The prompt box is typed into only.** No tool reads or writes it. Generate (button, Ctrl+Enter, the
   `generate_image` tool) renders the assistant's draft, never the box.
6. **The Hub adds no instructions to the model.** What the assistant does on a message is the Open
   WebUI system prompt's; tool descriptions are labels (≤200 chars, end with a period, no "always/never").
7. **Settings, not constants, for anything that may be set differently** (keep, context, model folders, paths,
   reference caps…); registry refuses a bound-less seed/loras/names setting.
8. **Size rules:** Python ≤300 lines/file, ts/tsx/css/tests ≤250; no `px` but 1px; no `overflow:hidden`; no
   console/localStorage/absolute URLs (`web/tests/unit/guards.test.ts`); ruff line 120 (config only).
9. **One package at the end, tested in full first** (server, unit, browser); the install line is run on the server.

## 0.4 How the three components meet without a spiderweb

| Need | Where it is shared | Who uses it |
|---|---|---|
| Pictures, ids, thumbnails | `hub/core/files.py` (`out/`, `drive/`, `chars/`) | Media (the pictures' own view), Generate Image (references by id), the assistant (characters by name) |
| Characters | `hub/core/characters.py` behind `Files` | Media edits them; Generate Image reads names/pictures for Tab and `references`; the assistant lists them |
| Jobs and outputs | `hub/core/jobs.py`, `enginecat.land` → the `generation` lane | Generate Image submits; Media shows; the job line shows; the storyboard module submits through the same call |
| Settings changes | `ctx.bus.publish("changed", …)` lanes | every open window redraws |
| Tools for the model | `features.tools_of` from each module's Screen/Listings/Actions | `hub/core/mcp.py` serves them; the assistant module only carries the chat |
| Cross-module events | `ctx.emit` / `listens` (e.g. `chat.cleared`) | the assistant emits; Generate Image listens |

Generate Image and Media never import each other; they meet only in the core. The assistant module knows
nothing of either: it carries a conversation to Open WebUI and back; the tools Open WebUI calls are served by
the core from the modules' own declarations.

## 0.5 Audit findings at this commit (from writing the guide)

Found while reading the code for parts 1–8. Verified by the compiler (V) or reported by a section's author
and not independently re-run (R). None blocks use; they are listed so the next session does not rediscover them.

| # | Finding | Where | Status |
|---|---|---|---|
| 1 | Settings → Assistant showed the MCP key empty and "New key" discarded the key the server returned (the view never carries the key by design, `test_cards.py:109`). | `web/src/modules/assistant/Card.tsx` | **Fixed** (V): the made key is kept on screen until the page reloads; the e2e fake no longer returns a key in the view. |
| 2 | `/api/media/delete` and `/api/media/move` accept `chars/` ids (`is_media`), though the error text says "Only Temp and Drive images"; a delete through the generic route erases one file, not every file of that name. | `hub/modules/media/routes.py:_ids`, `library.is_media` | V — behaviour as described; harmless; the tree's own Delete character is the intended path. |
| 3 | Stale comments still describe the removed "push" of the draft into the prompt box. | `hub/modules/generate_image/manifest.py:1-2`, `web/…/draft.ts:91`, `web/…/chat/assistant.ts:3`, `assistant/routes.py:1`, `assistant/chat.py:13` | R — text only. |
| 4 | `web/tests/full/stack.spec.ts` (not in the regular run) still expects `push_draft` and reads `mcp_key` from the view. | `web/tests/full/stack.spec.ts:88-95` | R — stale; `tests/full` is not run by the suite. |
| 5 | Guidance bounds differ: server 0–50 (`screen.GUIDANCE`), web inputs clamp 0–20. | `run/Canvas.tsx`, `Card.tsx` | R — a model's guidance above 20 cannot be set from the screen; the assistant can. |
| 6 | `Slots.tsx` always draws 3 boxes (`BOXES`, `run/Slots.tsx:22`). Moot for clip models: the server clamps their `references.max` and `refCap` to `cast.BOXES` (`hub/modules/generate_image/models.py:184-186`). Still true for a picture model whose table cap is above 3: `refCap` comes from the table (`ref_cap`, `models.py:75-81`; the default table lists `qwen_image_21` at 6, `hub/settings.py:40`), is not clamped, and `dropPlan` honours it, so a 4th to 6th reference could be placed but not shown. | `run/Slots.tsx:22`, `inputs.ts` | R — not seen at runtime; whether such a model is in the catalog was not checked. |
| 7 | `fit.spec.ts:28` expects `[data-region="actions"]` which nothing sets. | `web/tests/e2e/fit.spec.ts` | R — the spec passes; the locator is unused. |
| 9 | `/mcp` is protected by the Host allow-list, the access switch and the key only (no cookie/pairing). | `hub/core/mcp.py` | V — by design (Open WebUI in Docker is not a paired screen); documented in part 4. |
| 10 | `gpu.release` is used: Media's and Generate's bars send it. | `web/src/screens/media/Bar.tsx`, `web/src/modules/generate-image/run/Taskbar.tsx` | V |
| 11 | `web/src/shell/settings/ImageModels.tsx` imports Generate Image internals — a coupling a new module must not repeat. | `shell/settings/ImageModels.tsx:4-6` | R |
| 12 | Ruff is configured but no test or CI runs it; the 250-line web limit counts `split('\n')`, so the effective limit is 249. | `pyproject.toml`, `guards.test.ts` | V |
| 13 | The engine's catalog kept only models with `image_outputs`, so no video model reached the Hub. | `hub/worker/catalog.py:123-164`, `hub/worker/catalogvideo.py:196-235` | **Fixed in the Stage 0 to 4 work** (V by reading the code): `build` now also lists the native video models, each entry with `kind` "video", the `video` facts and `video_task`; `SHAPE = 7` (`catalog.py:21`) keys the controller's cache. Not yet run against the real engine (part 8, R9). |
| 14 | A clip is meant to be continued by dragging it onto a reference box. `Slots.tsx` has a drop branch for a clip id (`drop`, `:25-34`), but the Grid leaves clips out of the `MEDIA_DRAG` payload (`web/src/screens/media/Grid.tsx:84-85`), so that branch is not reached from the Grid; a clip reaches Continue from the right-click menu, the bar's button, or `references`. | `Grid.tsx`; `run/Slots.tsx` | V — read from both files; not traced in a browser. |

## 0.6 Video, in one screen

Video is not a module. Clip models are catalog entries of kind "video" on the Generate Image screen: the same bar,
draft, Generate button and six tools; there is no new tab, module or tool, and the job kind is still `image`. A clip lands
in its own root (`<data>/clips`, ids `clips/<day>/<time>.mp4`, flat by day, a continued clip too) after `hub/core/clip.py` blanks its tags. It is listed in the Clips section of the Media
window (the path `/clips` opens the same window on that section) and served with Range requests by `/files`.
Built and in the tree:
- Stages 0 to 4: the catalog reads the video models (`SHAPE = 7`); the bar shows frames, Seconds, size tiers by shape and
  the text encoder; a start picture, a last frame or identity pictures go in the reference boxes; the worker forces the
  video container; a memory profile can differ for clips (`engine.profile_video`); the engine's one-pass switch is read
  from its signature.
- Stage 6, Continue: a clip in box 1 makes the scene longer through the engine's "V" route; the new clip lands flat
  beside the source, which stays; `last_clip` tells the assistant the newest clip (part 2, 2.10; part 3, 3.7.11).
- Stage 7, Omni: a name, a detail choice and a cut-out per identity box (part 2, 2.10).
- Stage 8, partly: the core lifts (`named`, `temp`, `checks`, `clipplan`, the `Files` additions) and the storyboard
  module with its eight tools, off by default (`modules_disabled`, part 4, 4.9). Its web part is not built.
- Stage 9, steps 1 to 5: `--dump-engine`, `engineapi.py` and the `fork` and `upstream` adapters, the only files that name
  an engine key family or build an engine task; the wire (`PROTO = 2`) carries the Hub's requests; the upstream adapter
  drives H3 on upstream's own terms, held against the capture of upstream 18.05 (part 5, 5.6).
- The GPU rule: a job runs, or releases the worker's model first; the worker is released before a model switch and
  after every clip, so each clip runs in a fresh worker. Nothing names, lists or counts another program on the card
  (part 1, 3.7).

Not built: the Stage 9 debts (part 5, 5.6.2), the storyboard web part (its decisions are taken; joins by
ffmpeg in the engine's worker and never in the controller, and the sequence, are decided; V0 makes the Hub's engine
upstream WanGP and V1a to V1d settle voice), and Stage 10's last step, the run on the server of the engine installer and of
upstream's page (the engine must not depend on the HocusPocus/Maestro install, part 5, 5.1.4; its installer, the hold
on the weights and upstream's pre-check are built, 5.6.3), and Stage 11, the sequence (an Edit Video tab). The full design for a separate Generate Video module (own tab, core lifts, new
tools) is parked, kept in part 8 as a dated reference. The main risks, in order: VRAM and RAM on the engine host, blocked
downloads failing a missing companion file at load, progress that stalls during decode, a continue that re-encodes
everything before it, and the engine fork's private surface (R9).

## 0.7 How to read this guide for a task

- **"Where does X live?"** — the table at the end of part 1 (§1.7), then the part for the component.
- **"Add a setting / a tool / a bar control to Generate Image"** — part 2 §2.9.
- **"Add a tree section / a menu item / a root to Media"** — part 3 §3.7.
- **"Expose a new module to the assistant"** — part 4 §4.8 (what the registry refuses, description rules).
- **"Why is it like this?"** — `docs/video-plan/BLUEPRINT-director.md` and `PLAN.md` (decisions and their reasons), then the C.<n> entry cited.
- **"What do the rules rule out?"** — §0.3 above and `CLAUDE.md`, with part 1 §6 for the enforcing test of each rule.
- **"Video: what exists"** — part 8 §8.A, then part 2 §2.10 (the screen, Continue, Omni), part 3 §3.7.11 (the Clips section), part 5 (the worker, the adapters §5.6). **"The storyboard module"** — part 4 §4.9. **"What next"** — part 8 §8.B.
