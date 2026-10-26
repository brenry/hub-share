# 6. The web client frame, style system, build, tests and release

Scope: the React/Vite client under `web/`, how it is built and served, how the three test suites work, how a release zip is made and installed, and the repo rules with the test that enforces each. Facts are from the tree at commit 7834eb2. Numbers were measured on 2026-10-13 (section 6.14).

Naming used below: "server" is the Starlette process (`hub/`); "the desk" is the machine that runs HocusPocus Desktop; "the server machine" is the machine that runs the Hub. The code itself contains no address of either machine; test fixtures use placeholder addresses.

---

## 6.1 Layout of `web/`

| Path | Role |
|---|---|
| `web/package.json` | scripts and pinned dependencies (no `^` or `~`; `web/.npmrc` sets `save-exact=true` and `engine-strict=true`; `engines.node >= 22.12`) |
| `web/vite.config.ts` | Vite 8 config: React plugin, build flags, dev proxy, vitest include |
| `web/tsconfig.json` | strict TypeScript 7, `noEmit` |
| `web/index.html` | one `<div id="root">` and `<script type="module" src="/src/main.tsx">`; title `Hub` |
| `web/src/main.tsx` | entry: styles, screen choice, bus start, error policy, render |
| `web/src/shell/` | the window frame, the top bar, the connection cover, the Settings page, the module registry |
| `web/src/screens/` | `media/` (the Media window) and `pair/` (the pairing page) |
| `web/src/modules/` | one folder per tool or Settings card: `generate-image/` (tab and Settings card), `network/` (card only), `assistant/` (card only) |
| `web/src/lib/` | store, bus, http, protocol types, formatting, keys, toast, desktop detection, lock |
| `web/src/ui/` | shared widgets, each with a `.module.css` |
| `web/src/styles/` | `tokens.css` (colours) and `base.css` (layers, sizes, reset, lock) |
| `web/tests/unit/` | vitest, node environment |
| `web/tests/e2e/` | Playwright against a fake hub; `fixtures/` holds the fakes |
| `web/tests/full/` | full-stack Playwright: the real controller process (`stack.ts`, `prepare.py`, `stack.spec.ts`) |
| `web/shots/` | PNGs written by the `@shot` specs (review pictures, not assertions) |
| `web/dist/` | build output (generated, served by the server, shipped in the zip) |

Dependencies are only `react` and `react-dom` (both 19.3.0). Everything else is a dev dependency: Vite 8.3.3, `@vitejs/plugin-react` 6.1.1, TypeScript 7.0.2, vitest 5.0.3, `@playwright/test` 1.56.1, and type packages (`web/package.json`). There is no ESLint, Prettier, router library, state library, CSS framework or component library. `web/` has no ESLint config and `package.json` has no `lint` script; the one place an ESLint comment appears is `// eslint-disable-line react-hooks/exhaustive-deps` in `src/screens/media/Media.tsx`, which has no effect without ESLint (see Gaps).

## 6.2 Screens and routing

There is no client-side router. `src/main.tsx` holds a table keyed by path (`main.tsx:14-20`):

| Path | Screen module | Bus role | `data-screen` on `<html>` |
|---|---|---|---|
| `/` | `shell/Workspace` | `workspace` | `workspace` |
| `/media` | `screens/media/Media` | `media` | `media` |
| `/pair` | `screens/pair/Pair` | none (`null`) | `pair` |

How it resolves (`main.tsx:22-29`):

1. `path = location.pathname` with trailing slashes stripped, or `/`.
2. `[role, load] = screens[path] ?? screens['/']`. Any unknown path renders the Workspace. This includes `/screen/1` to `/screen/9`, which the server serves as shell pages (`hub/core/web.py:64`, `web_routes`) but which the client has no entry for; they behave as `/` and open a `workspace` bus line.
3. If `role` is not null: `feed(bus)` (wire the bus into the live stores) then `bus.start(role, label)`, where `label` is the optional `?label=` query parameter (`main.tsx:24-27`). `/pair` never opens the bus.
4. `document.documentElement.dataset.screen = role ?? 'pair'` selects the palette (section 6.5).
5. The screen is code-split: `lazy(load)` inside `<Suspense fallback={null}>`, inside `<StrictMode>`.

Server side, the three shell paths and the assets are routed in `hub/core/web.py`: `GET /`, `/media`, `/screen/{n:int}` with auth kind `public`, `GET /pair` and `GET /assets/{path}` with auth kind `pair`, `POST /api/pair`. `index.html` is sent with `cache-control: no-store`; `/assets/*` with `public, max-age=31536000, immutable` (hashed file names). If `web/dist/index.html` is absent the server answers the text "Hub is running. Its interface is not installed." (`web.py:20,34-35`).

Page-level error policy (`main.tsx:32-34`): React is created with `onUncaughtError` showing the toast "Something went wrong on this page", and the other two handlers empty; `unhandledrejection` is `preventDefault`ed. Nothing is written to the console (guard, 6.12).

`installLock()` (`src/lib/lock.ts`) runs once per page: it consumes Ctrl+wheel and Ctrl `+ - 0` so the page can never be zoomed, except inside an element with `data-wheel="stage"` (the Media Stage), which zooms its own image and owns Ctrl+0.

### /pair

`screens/pair/Pair.tsx` reads `#c=<code>&next=<path>` from the URL fragment (`pair.ts` `readFragment`), clears the fragment with `history.replaceState`, and posts `{code}` to `POST /api/pair`. On success it shows "Paired" and `location.replace(next)`. `next` is accepted only if it resolves to the same origin (`pair.ts` `localPath`), else `/`. Failure texts come from `PAIR_TEXT`; HTTP 429 maps to "Too many attempts", other 4xx to "This link is not valid or was already used". A module-level `started` flag stops React StrictMode's double effect from redeeming the one-time code twice.

### /media

`screens/media/Media.tsx` is a full screen on its own `Frame` without a top bar (`Frame` with no `bar` prop): the Stage on the left, a right column with the bar, the thumbnail grid and a folder tree that rolls out over the Stage. Its stores are in `screens/media/media.ts` (section 6.4). It is not a tab and cannot open Settings; Settings opens only from the Generate bar.

### / (the Workspace)

`shell/Workspace.tsx` (`export default function Workspace`, line 16) is the shell for tools plus Settings.

- Tabs. `modules` (from `shell/registry.ts`) is every `src/modules/*/manifest.ts` default export, sorted by `order` (`registry.ts:4`, `import.meta.glob(..., {eager: true})`). Today there is one manifest, `generate-image` (`id: 'generate-image'`, `label: 'Generate Image'`, `order: 10`). Tabs shown are the manifests whose `id` also appears in the controller's `welcome.tools` list (`Workspace.tsx:17-18`); before the first welcome (`tools` is null) all manifests show.
- Cards. `registry.ts:9` globs `src/modules/*/Card.tsx` into `cardPanels`, keyed by the folder name. Settings shows only the cards that the server also lists at `GET /api/cards` (`Settings.tsx:16-19`). So adding a tool tab or a Settings card on the client is: add a folder with `manifest.ts` and/or `Card.tsx`; deleting the folder removes it (`lib/module.ts` comment).
- Active tab and Settings state. `active` is `useState` in Workspace, starting at `modules[0].id`. Settings open or closed is not local state but the store `lib/settingsOpen.ts` (`createStore(false)`), because the open tool's bar sets it: the Generate bar's fold-up item "Settings" runs `settingsOpen.set(true)` (`modules/generate-image/run/Taskbar.tsx`). Clicking a tab does `setActive(id); setSettings(false)` (`Workspace.tsx:32`).
- Panels. Every tab's panel is rendered once and kept mounted; hidden ones use the `hidden` attribute (`Workspace.tsx:45-47`, `visible = !settings && m.id === active`). Each panel gets `visible` as a prop (`ToolProps`). Panels are `lazy(m.load)` created once with `useMemo`.
- Focus report. While a tab is active the Workspace calls `bus.focus(active)` and repeats it on every window `focus` event (`Workspace.tsx:24-30`). The controller uses this to know which tool Media should deliver pictures to. `bus.ts` remembers `lastFocus` and `lastSockets` and re-sends both after a reconnect's `welcome`.
- Foot. The Workspace passes a `foot` to `Frame` only when Settings is open, or when there are no tabs at all (`bare`). The foot is `<span grow/> <Live/> <close button>`; the close button is the lit sliders icon (`data-region="settings-close"`) and toggles `settingsOpen`. When a tool is showing, the tool's own bar (`footer data-region="bar"`) is the bottom row and Workspace adds no foot.
- Settings. `shell/settings/Settings.tsx` shows the standard list (`CoreList.tsx`: Storage, Image engine with the memory profiles and the video sizes, Image models, Hardware, About with Version and Restart) in a `Scroll` named `settings`, with the cards in a `Dock` pinned below (three columns). Clicking a card replaces the list with that card's lazy panel and a crumb "Settings > Title". `CoreList` talks to `GET/PATCH /api/settings` and `POST /api/settings/restart`; it reloads on the bus message `settings`.

### The Frame

`shell/Frame.tsx` is used by both the Workspace and Media. It is a grid of `.app` > (`.frame` = optional `header[data-region="topbar"]` + `.body`) and an optional `footer[data-region="foot"]`, plus `ConnectionCover` and `Toasts`.

- `.frame` gets `inert` whenever the cover is not `none`, and `data-dim` (opacity .35) when the cover is `off`. The foot is outside `.frame`, so the Live box in it stays clickable while the cover is up (`Frame.tsx` comment; `Frame.module.css`: foot `z-index: 11`, cover `z-index: 10`).
- `.body > *` all use `grid-area: 1 / 1`, so panels stack in one cell and only the visible one displays.
- `ConnectionCover.tsx` `useCover()` reads `bus.link`: `off` and `unpaired` show at once; `cut` or `connecting` show only after a 1.5 s grace (`GRACE_MS`, `ConnectionCover.tsx:8`). Texts: "Server offline — reconnecting…", "Switched off" with a "Check now" button (calls `bus.nudge()`), and "Not paired" with the command `hub pair --name <device>`.
- `TopBar.tsx` draws only tabs: `role="tablist"`, roving tabindex, ArrowLeft/Right/Home/End. The active tab has a `--rule` thick underline in `--accent`. There are no status readouts in the bar; the connection light is `ui/Live` and lives in the tool bars and the foot.

## 6.3 The `ui/` widgets and `lib/` modules

`src/ui/` (each file has its own `.module.css` where it needs one; every module CSS wraps its rules in `@layer ui` or `@layer screen`):

- `cx.ts`: `cx(...parts)` joins truthy class names. Two lines.
- `Scroll.tsx`: `<Scroll name="...">` renders `<div data-scroll="name">`. The comment says it is "the only way to get a scrolling box. Everything else clips." The CSS side is `[data-scroll] { overflow: auto; ... }` in `base.css`, and the guard allows no other rule to set `overflow: auto|scroll` (6.12).
- `Button.tsx`: variants `default | ghost | danger`, `small`, optional `icon`; 2rem high (`--ctl-h`), small 1.5rem (`--ctl-h-sm`); icon-only buttons need an `aria-label`.
- `Icon.tsx`: a `PATHS` table of inline SVG paths on a 16 grid, stroke 1.5, 32 names (`gear`, `down`, `right`, `left`, `x`, `plus`, `minus`, `folder`, `term`, `net`, `layers`, `chat`, `monitor`, `copy`, `refresh`, `link`, `pen`, `trash`, `lock`, `send`, `run`, `back`, `spark`, `up`, `star`, `treeOut`, `treeIn`, `thumbsUp`, `thumbsDown`, `chip`, `sliders`, `reseed`; counted from the table). Size is `var(--icon)` or `var(--icon-sm)`.
- `Menu.tsx`: a portal right-click or fold-up menu (`createPortal` to `document.body`, `role="menu"`). Items are `{label, icon, key, danger, off, run, sub}` or `{sep: true}`. `off` keeps an item visible but disabled, with the reason as its `title`. `sub` folds a second list out to the left. `row` draws items as a row of icons. Arrow keys move focus between enabled items (Up and Down, or Left and Right in a `row` menu), ArrowRight on an item with `sub` moves into the folded list and ArrowLeft returns (`Menu.tsx:36-47`); the first enabled item takes focus when the menu opens (`Menu.tsx:32`); `media-bar.spec.ts` covers it. It positions itself from `MenuAt {x, y, up}`; Escape, a click elsewhere, any scroll, a resize or window blur closes it. Menu z-index is 30 (`Menu.module.css`).
- `Progress.tsx`: `<Progress value={0..1 | null} label>`; moves by `transform: scaleX` only; `null` is indeterminate.
- `Live.tsx` and `Live.module.css`: the connection light box. Reads `bus.link` and `controllerBlip` (`lib/blips.ts`). When linked it says "Live"; one click arms ("Restart?" for 3 s), a second click within 3 s posts `POST /api/settings/restart` and toasts "Restarting the Hub". When the link is not on, one click calls `bus.nudge()` to reconnect now.
- Others: `StatusDot` (kinds `ok warn cut err idle`), `Toasts`, `Field`, `Select`, `Switch`, `Segmented`, `Stepper`, `DragNumber`, `Popover`, `Sheet` (`Section`, `Row`, `Plate`, `Tag`, `Empty` used by Settings), `PathField` and `CopyField`.

`src/lib/`:

| File | Purpose |
|---|---|
| `store.ts` | `createStore`, `useStore` (6.4) |
| `bus.ts` | `createBus(env)` and the singleton `bus`: the one WebSocket to `/bus` per window (6.4) |
| `live.ts` | stores mirroring controller state, and `feed(bus)` |
| `useBus.ts` | `useBusEvent(type, fn)` (subscribe for the component's lifetime, latest `fn` via a ref), `useLinkState()` |
| `http.ts` | `getJSON`, `sendJSON`, `sendBlob`, `HttpError(status, text, field)`, `errorText`, `q()` query builder; same-origin, `credentials: 'same-origin'`; the server's `{text, field}` body becomes the error line |
| `protocol.ts` | TypeScript types of the bus: `Envelope`, `Welcome`, `Job`, `JobState`, `Presence`, `Focus`, `Declaration`, `Deliver`, `Delivery`, `ChatView`, `BusError`, `MEDIA_DRAG` |
| `format.ts` | plain-English numbers: `gb`, `count`, `plural`, `about`, `clock`, `ago` |
| `keys.ts` | `isTypingTarget`, `useCtrlEnter` |
| `toast.ts` | store of at most 3 toasts, each leaves after `ms` (default 4000) |
| `desktop.ts` | HocusPocus Desktop detection (6.11) |
| `lock.ts`, `reveal.ts` | zoom lock; `focusInScroller` (focus without letting the browser scroll the page, then scroll the nearest `[data-scroll]`) |
| `module.ts` | `ModuleManifest`, `ToolProps`, `CardProps`, `CardInfo` |
| `blips.ts`, `copy.ts`, `settingsOpen.ts` | connection-light text; copy-or-select helper; Settings open flag |

## 6.4 State model

### createStore and useStore (`lib/store.ts`, 31 lines)

`createStore<T>(initial)` returns `{get, set, subscribe}`. `set` takes a value or an updater function; it does nothing if the new value is `Object.is`-equal to the old one; otherwise it stores it and calls every subscriber (a copy of the set, so a subscriber may unsubscribe while being called). `useStore(store, pick)` is `useSyncExternalStore` over `pick(store.get())`. The comment says `pick` must return a primitive or an existing reference, never a fresh object, or React would re-render forever. Updates are always by replacing values (new `Map`, new array), never by mutating.

### Where each store lives

| Store | File | Fed by |
|---|---|---|
| `bus.link` (`state`, `since`, `nextTry`, `version`) | `lib/bus.ts:39` | the WebSocket's lifecycle and `welcome` |
| `presence`, `jobs` (a `Map<id, Job>`), `focus`, `tools`, `connects` | `lib/live.ts:6-11` | bus messages via `feed(bus)` |
| `toasts` | `lib/toast.ts` | `toast()` calls |
| `settingsOpen` | `lib/settingsOpen.ts` | the Generate bar's fold-up, the Workspace foot, tab clicks |
| `temp`, `drive`, `favFolders`, `characters`, `view`, `naming` | `screens/media/media.ts:28-38` | HTTP (`/api/media/...`), bus events `generation` and `media.changed` |
| `draft`, `draftReady` | `modules/generate-image/draft.ts:11-12` | `GET/PUT /api/generate-image/draft`, bus `welcome` and `generate-image.draft` |
| `modelList`, `defaults` | `modules/generate-image/modelList.ts:10-11` | HTTP |
| `loras` | `modules/generate-image/loras.ts:6` | HTTP |
| `chat` | `modules/generate-image/chat/assistant.ts:15` | `assistant.chat` bus event, `GET /api/assistant/chat` |
| `uploading`, `flashing`, `slotNote` | `modules/generate-image/inputs.ts:13-15` | local UI actions |
| `picker` | `modules/generate-image/compose/complete.ts:18` | local UI (tab-complete popup) |

Component-local UI state (the active tab, menus, selections in Media, Settings view) uses plain `useState`.

### Bus to store flow

`lib/bus.ts` (`createBus(env)`; the `env` argument injects `open`, `url`, `reload`, `onWake`, `random`, `now`, which is what lets `tests/unit/bus.test.ts` run it without a browser) holds the whole protocol client:

1. `start(role, label)` connects to `ws(s)://<host>/bus`, and on open sends `hello {proto: 1, role, screen, label, subs: null}`. `screen` is a random id `scr_XXXXXXXX`.
2. A `welcome` message carries `boot`, `version`, `session`, `limits`, `tools`, `presence`, `focus`, `jobs`. On the first welcome the bus stores `boot`; if a later welcome has a different `boot` the controller restarted with new code, so the page calls `fetch('/', {cache: 'reload'})` then `location.reload()` (`bus.ts` `handle`, `env.reload`). Otherwise `link` becomes `on`, and the bus re-sends `focus` and `sockets` and flushes up to 20 queued delivery receipts (`RECEIPT_MAX`).
3. The watchdog: 10 s to connect (`CONNECT_TIMEOUT`), then `limits.silence_s` (default 60 s, min 5 s) of silence kills the socket and starts reconnecting.
4. Reconnect schedule: close code 4003 = `unpaired` (stop, no retry); 4000 or a prior `going_off: shutdown` = `off` (retry at 2, 5, 10 s, then 30 s); 4013 = `slow` (30 s); 4009 = fresh screen id and immediate retry; anything else = `cut` (500, 1000, 2000, 4000, 8000 ms with 0.8-1.2 jitter; after 10 minutes of cut, 30 s). Window `online`, `focus` and `visibilitychange` call `nudge()`, which reconnects at once if cut or off.
5. Messages: `reply` or `error` with `re` matching a pending `request(t, d)` id resolve or reject that promise; `beat` is ignored; everything else is dispatched by type name to listeners registered with `bus.on(type, fn)`. All pending requests reject with `{code: 'unavailable', text: 'Connection lost'}` when the socket closes.
6. `feed(bus)` (`lib/live.ts:13`, called once from `main.tsx` for the two bus screens) registers: `welcome` sets `presence`, `focus`, `tools`, replaces `jobs` with the welcome's list and increments `connects`; `presence` and `focus` replace; `job` upserts into a new `Map`; `job.gone` removes. The comment states the rule: stores hold current state fed only by the bus, "never deltas to replay".
7. Screens refetch their HTTP lists when `connects` changes (Media does so in an effect on `connects`, `Media.tsx:59-60`) so a reconnect or a restarted controller always reloads from the server.
8. Module code subscribes with `useBusEvent` or `bus.on` and updates its own store (for example `draft.ts` listens to `welcome` and `generate-image.draft`, `assistant.ts` to `assistant.chat`, `Media.tsx` to `generation`, `media.changed`, `delivery`).

Sending: `bus.send(t, d, id?)` (fire and forget; returns false if the socket is not open), `bus.request` (promise), `bus.focus(tool)`, `bus.declare(decl)` (the tool's sockets, i.e. the reference boxes Media can deliver into), `bus.receipt(re, d)`.

The server's HTTP API is used for reads and for edits to saved state; the bus carries presence, focus, jobs, deliveries and "something changed" notices. The server remembers nothing about the page between sessions (`docs/20-BUILD-SPEC.md` section 6), and the client holds no persistence of its own.

### No localStorage, no console

`grep` of `src/` finds no `localStorage`, `sessionStorage` or `console.`, and the guard test fails the build if one appears (6.12). There are no cookies set by the client; the pairing cookie is `HttpOnly` and set by the server (`hub/core/web.py` `set_cookie`). The draft survives only in the server's memory for the session; "Nothing remembered" is a product rule (`docs/20-BUILD-SPEC.md` section 6).

## 6.5 Design language and tokens

The look is quiet: small grey text, dark flat panels with a 1px hairline, one accent colour (cyan), 2px radii, no shadows except on floating menus and sheets, and short copy ("labels first", `docs/20-BUILD-SPEC.md` section 8). The reference is HocusPocus Media (`tokens.css` comment on "Studio": "taken from the HocusPocus Media monitor (`.hp-studio`, cyan-400) and lifted one step from black"; "Lights are cyan too (no green)").

### Colours (`src/styles/tokens.css`, 74 lines)

`:root` defines a "Slate" palette (blue-grey), the default. The block `html[data-screen='media'], html[data-screen='workspace']` (`tokens.css:46-74`) overrides it with the "Studio" palette:

| Token | Studio value | Slate value (default and `/pair`) |
|---|---|---|
| `--seam` (page behind everything) | `#121316` | `#1C2225` |
| `--chrome` (bars) | `#17191d` | `#293134` |
| `--well` (text fields) | `#121316` | `#22292D` |
| `--panel` (page) | `#17191d` | `#272F32` |
| `--panel-2` | `#1b1d21` | `#2D3538` |
| `--raise` (rows, controls) | `#22252a` | `#363D40` |
| `--raise-hover` | `#2a2d33` | `#3D4447` |
| `--select` | `#272a2e` | `#3D4346` |
| `--line` | `#25282c` | `#353C3F` |
| `--line-strong` | `#34383e` | `#4A5053` |
| `--stage` (Media image backdrop) | `#0d0e10` | `#121415` |
| `--text-1` / `-2` / `-3` / `-dis` | `#e6e7e8` / `#a5a7aa` / `#85888c` / `#5f6368` | `#E6E8E8` / `#BFC4C5` / `#8E9497` / `#666C6F` |
| `--accent` / `--accent-hover` / `--accent-ink` | `#00d3f2` / `#53eafd` / `#051316` | `#8A9D90` / `#98AB9E` / `#1B201D` |
| `--ok`, `--new` | `#00d3f2` (cyan too) | `#79D28D`, `#8BA293` |
| `--warn` | `#fbbf24` | `#C9A06B` |
| `--err` | `#fca5a5` | `#C97A7A` |
| `--accent-soft` / `--accent-line` | `rgba(0, 211, 242, .15)` / `rgba(0, 211, 242, .7)` | `rgba(138,157,144,.16)` / `rgba(138,157,144,.6)` |

Shared in `:root` regardless of palette: `color-scheme: dark`, `--edge-light` (`inset 0 1px 0 rgba(255,255,255,.07)`), `--edge-light-soft`, `--side-shade-l/r`. The colour rule is in the file header: "Every screen and module reads these; nothing defines its own colours." Colour is kept for the primary action, the connection light, states and the new-file dot.

(The `/pair` page therefore has the grey-green Slate accent `#8A9D90`, not cyan. That comes from the selectors in `tokens.css`; whether it is intended is not stated anywhere.)

### Sizes (`src/styles/base.css`, 86 lines)

- Layer order is declared first: `@layer base, ui, screen;` (`base.css:77`). `main.tsx` imports `tokens.css` then `base.css` before any module CSS so that this declaration wins. Base rules are in `@layer base`, widgets in `@layer ui`, screens and modules in `@layer screen`; later layers beat earlier ones, so a screen can override a widget without specificity fights.
- One root font size: `--ui-base: clamp(15px, 10.25px + min(0.5375vw, 0.9556vh), 30px)` times `--ui-scale` (`base.css:88-90`). Fitted so 1366x768 gives 17.6px, 1920x1080 20.6px, 2000x1130 21px, 2560x1440 24px (comment values). `--ui-scale: 1` everywhere except `html[data-screen='media'] { --ui-scale: .68 }`, so Media reads at about 14px. Every other size in the code is `rem`, so the whole UI scales together. The string is duplicated in `guards.test.ts` (`ROOT_SIZE`) so changing it needs a matching test edit.
- Type scale (all rem): `--fs-cap` 0.875, `--lh-cap` 1.25; `--fs-ctl` .86 (small controls on a tool's bottom row); `--fs-body` 1, `--lh-body` 1.5; `--fs-lead` 1.125, `--lh-lead` 1.625; `--fs-title` 1.25; `--fs-head` 1.5, `--lh-head` 2. Font stack: system UI (`-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif`); there are no web fonts. Text-role classes: `.t-label` (cap, 600, uppercase, +.05em), `.t-meta`, `.t-cap`, `.t-head`, `.num` (tabular), `.ell` (ellipsis), `.visually-hidden`.
- Spacing scale `--sp-1` .25rem, `--sp-2` .5, `--sp-3` .75, `--sp-4` 1, `--sp-5` 1.25, `--sp-6` 1.5, `--sp-7` 2, `--sp-8` 2.5, `--sp-9` 3 (`base.css:103-104`).
- Controls and shape: `--ctl-h` 2rem, `--ctl-h-sm` 1.5rem, `--bar-h` 2.5rem, `--icon` 1rem, `--icon-sm` .875rem, `--dot` .5rem, `--ring` .1875rem, `--rule` .125rem. Radii `--r-1`, `--r-2`, `--r-3`, `--r-pill` are all .125rem (the four names exist, the values are the same, so every corner is 2 rem-eighths, about 2px at 16px root). Derived: `--hi`, `--shade`, `--accent-edge` via `color-mix`.
- `--gen-edge` is not a global token. It is defined in `modules/generate-image/GenerateImage.module.css:6` on the `.work` box as `var(--sp-3)` (.75rem) and is "the one inner margin": reply column to card to text, the draft's corner, the head. The same file defines `--gen-bar-h: 1.625rem`, `--gen-bar-ctl: 1rem`, `--gen-bar-fs: var(--fs-ctl)`. `margins.spec.ts` pins these against measurements.
- Resets (`base.css:117-147`): `box-sizing: border-box; margin: 0; padding: 0`; buttons and inputs have no chrome; lists have no markers; `:focus-visible` draws a `--rule` outline in `--accent`; `prefers-reduced-motion` turns animations and transitions off.

### The lock (no page scroll)

`base.css:120-127`: `html`, `body` and `#root` are `overflow: clip` at 100% height with `overscroll-behavior: none`; `[data-scroll] { overflow: auto; overscroll-behavior: contain; min-height: 0 }` is the only scroller, with a .375rem WebKit scrollbar and no arrow buttons. `.app` in `Frame.module.css` is `overflow: clip` too. The rule is "no box but a named scroller can ever scroll". Layouts are CSS grids with `minmax(0, 1fr)` rows and `min-height: 0` children so content shrinks instead of pushing the page. `overflow: hidden` is banned because it still allows programmatic scrolling (`clip` does not); the guard enforces this.

## 6.6 Build pipeline

Commands (`web/package.json` scripts; run in `web/`):

| Command | What it runs |
|---|---|
| `npm run dev` | `vite` (dev server with HMR). Proxy in `vite.config.ts` sends `/api`, `/files`, `/thumbs` to `http://127.0.0.1:42010` and `/bus` as WebSocket to `ws://127.0.0.1:42010` |
| `npm run build` | `tsc --noEmit && vite build` into `web/dist/` |
| `npm run preview` | `vite preview --host 127.0.0.1 --port 4173 --strictPort` |
| `npm test` | `vitest run` |
| `npm run e2e` | `playwright test` (config `playwright.config.ts`) |
| `npm run full` | `playwright test -c playwright.full.config.ts` |
| `npm run shots` | `SHOTS=1 playwright test --grep @shots` |

Build details (`vite.config.ts`): `assetsInlineLimit: 0` (no data-URI inlining, so the "no external requests" scan and the CSP-friendly output stay simple), `sourcemap: false`, `modulePreload: {polyfill: false}`. Output: `index.html` plus hashed `assets/*.js|css`, with chunks per lazy screen and per shared widget (the 2026-10-13 zip lists 43 files under `web/dist`, for example `Workspace-*.js`, `Media-*.js`, `GenerateImage-*.js`, `Pair-*.js`, `react-*.js`, `index-*.js`). `tsc` runs with `noEmit`, so only vite emits.

TypeScript flags (`tsconfig.json`): target ES2023, `strict`, `noUncheckedIndexedAccess`, `exactOptionalPropertyTypes`, `noImplicitOverride`, `noFallthroughCasesInSwitch`, `noUnusedLocals`, `noUnusedParameters`, `verbatimModuleSyntax`, `erasableSyntaxOnly`, `isolatedModules`, `jsx: react-jsx`. It compiles `src`, `tests`, and the three config files together, so tests are type-checked too.

How the server serves it: `hub/core/runtime.py:57` `DIST = Path(__file__).resolve().parents[2] / "web" / "dist"`. `Core.__init__` takes `dist: Path = DIST` and `core.app()` passes it to `web_routes(gate, devices, dist)` (`runtime.py:134`); `hub/core/web.py` serves `dist/index.html` for `/`, `/media`, `/pair`, `/screen/{1..9}` and files below `dist/assets` for `/assets/*` (path-traversal-checked with `realpath` and `commonpath`). There is no static-file mount, no SPA fallback for other paths (an unknown path is a Starlette 404 or the guard's refusal), and no server-side build step: the server has no Node dependency at run time. Tests pass a different `dist` through `start_hub(..., dist=...)` (`tests/core/harness.py`).

Line limits applied during the build (not by tooling in `vite`, but by `npm test`): see 6.12.

### The shared preview-server convention

`npm run preview` is always `127.0.0.1:4173` with `--strictPort`, so a second copy fails to start instead of picking another port. `playwright.config.ts` sets `use.baseURL = 'http://127.0.0.1:4173'` and `webServer: { command: 'npm run preview', url: 'http://127.0.0.1:4173', reuseExistingServer: true }`. The consequence for parallel runs is: if something already listens on 4173 (an earlier preview or another agent's), Playwright reuses it and serves whatever `web/dist` that process was started over; if not, Playwright starts one and stops it when the run ends. The preview serves the built `web/dist`, so e2e results reflect the last `npm run build`, not the current source. `connection.spec.ts:81` asserts that every request goes to `http://127.0.0.1:4173/` or `ws://127.0.0.1:4173/`. Playwright also runs `workers: 1`, `timeout: 60_000`, 1920x1080 Chromium, and excludes tests tagged `@shot` or `@shots` unless `SHOTS` is set (`playwright.config.ts`). I did not find a written rule for how several agents coordinate; the only mechanism is the shared fixed port plus `reuseExistingServer`. To run against a different build you must stop the process on 4173 yourself (do not use `pkill -f`).

## 6.7 Test architecture: overview

| Suite | Tool | Where | Needs |
|---|---|---|---|
| Server | pytest + pytest-asyncio | `tests/core`, `tests/engine` | `.venv` only; no GPU, no network |
| Web unit | vitest (node env) | `web/tests/unit/*.test.ts` | Node |
| Web e2e | Playwright Chromium | `web/tests/e2e/*.spec.ts` | built `web/dist`, a Chromium |
| Full stack | Playwright, real `python -m hub serve` | `web/tests/full/` | `npm run build`, `.venv`, a system Python as the fake engine's Python (`HUB_TEST_ENGINE_PYTHON`, default `/usr/bin/python3`) |
| Static rules | pytest and vitest | `tests/core/test_rules.py`, `tests/engine/test_rules.py`, `web/tests/unit/guards.test.ts` | |

`docs/20-BUILD-SPEC.md` section 9 defines "done": `pytest -q` and `ruff check hub tests` clean; in `web/`: `tsc --noEmit`, unit tests, browser tests, `npm run build`. Browser tests run in the development copy only; nothing of Playwright ships.

## 6.8 Server tests

Config (`pyproject.toml`): `testpaths = ["tests"]`, `pythonpath = ["."]`, `addopts = "-q --import-mode=importlib"`, `asyncio_mode = "auto"`, function-scoped event loops, and `filterwarnings = ["error::PIL.Image.DecompressionBombWarning"]` (the controller turns Pillow's warning into an error at import, and pytest resets filters per test, so it is repeated here). Because `-q` is already in `addopts`, plain `pytest -q` prints no summary line; use `pytest -v` or `-rA` to see counts.

`tests/conftest.py`: one autouse fixture deleting `HUB_DATA` from the environment so no test inherits a data folder.

Layout:
- `tests/core/` (546 tests collected): the controller. Bus, guard/pairing, jobs, session, VRAM, settings, store/devices, MCP (including `mcp_driver.py` and a conformance test), the assistant module (chat, tools, purge, cleanup, lean, link), characters, drive, files, clean, netlock, CLI, process, plan, registry, rules.
- `tests/engine/` (477 tests collected): the image engine side. Worker protocol and process (`test_worker.py`, `test_supervisor.py`), lane (`test_engine_lane.py`), Generate Image module, LoRAs, Media, autoreg (pointer files), the build of job params, and `test_with_core.py`. `tests/engine/fake_engine/` is a stand-in Wan2GP tree (`wgp.py`, `fake_engine.json`, `defaults/`, `shared/`); `helpers.py` has `make_engine_root(base, flavour)`.
- `tests/fakes/`: `fake_probes.py` (scripted NVML readings; `FakeProbes` has the same surface as `hub.core.probes.Probes`, counts reads, and `set_procs` sets the per-process MB that used/free follow), `fake_worker.py` (a stdlib-only worker that speaks `hub/worker/protocol.py` and writes a real PNG per task; modes `fatal`, `exit-on-start`, `crash-on-run`, `ignore-stop`, `slow`, `report-env`), `screen.py` (`Screen`: one simulated bus line over a real WebSocket, plus raw `http()` and handshake helpers), `openwebui.py`.
- `tests/core/fake_lane.py`: `FakeLane`, a scripted `JobLane` that "loads" a model by adding MB to `FakeProbes` and writes tiny PNGs.
- `tests/fixtures/`: two catalog JSON files.

### `start_hub` (`tests/core/harness.py`, 109 lines)

`async start_hub(data, *, lanes=(), modules="own", probes=None, timing=FAST, settings=None, dist=None, ping_s=None) -> Hub` runs the real controller inside the test's event loop:

1. Copies `DEFAULTS` from `hub.settings`, forces `server.bind = ["127.0.0.1"]`, deep-merges the `settings` override, validates and saves them to `data`.
2. `bind(["127.0.0.1"], 0)` opens a socket on an OS-chosen free port.
3. Builds `Core(data, s, probes, port=..., timing=FAST, [dist=...])`, adds the given lanes as engines, loads modules: `"own"` = the network and assistant modules, `"discover"` = real registry discovery, or a list of `Module` objects.
4. Makes a `HubServer` (uvicorn) from `config(core.app())`, `await core.start()`, serves in a task and waits up to 2 s for `server.started`.

It returns a `Hub` dataclass: `core`, `server`, `task`, `port`, `data`, `probes`; `origin`; `pair(name, addr)` (mints and redeems a code directly, returns the cookie value `<id>.<secret>`); `http(method, path, cookie, json_body, headers, body, origin=True)` (adds the cookie and an `Origin` header on non-GET, which the guard requires); `screen(cookie, role, screen, label)` (opens a bus line and sends `hello`); `close()`. `FAST = Timing(hello_s=1.0, beat_s=25.0, deliver_s=0.5, session_grace_s=0.4)` shrinks the session grace (15 s in production) so "the session ends" tests are quick. So server tests talk to the real Starlette app through real sockets; only the GPU, the worker and the outside services are faked.

### FakeOpenWebUI (`tests/fakes/openwebui.py`, 192 lines)

A `ThreadingHTTPServer` on 127.0.0.1 that records every request in `requests` and answers the paths the assistant module uses: model list, tool-server config (`/api/v1/configs/tool_servers`), chat list/create/delete (`/api/v1/chats/...`), and completions. Knobs: `reply`, `status`, `raw`, `models`, `servers`, `output` (tool-call output), `content`, `error`, `stream_as` (`"null"` or `"sse"`), `making` (delay before chat creation answers), `titles`, `delete_status` and `delete_detail`. Helpers `calls`, `settled`, `until`, `tool_hub` (starts a hub wired to the fake). Used by `test_assistant_chat.py`, `test_assistant_tools.py`, `test_assistant_purge.py`, `test_assistant_cleanup.py`, `test_assistant_lean.py`. Hub code reaches Open WebUI only on loopback (`docs/20-BUILD-SPEC.md` section 5), so the fake needs no network access.

## 6.9 Web unit tests (vitest)

`vite.config.ts` sets `test: { environment: 'node', include: ['tests/unit/**/*.test.ts'] }`. No DOM environment is configured, so unit tests cover pure logic and the bus (which takes an injected socket). Files (19): `blocking`, `bus` (the reconnect state machine with a fake socket and clock), `clips` (the Clips section: where a new file lands, the listings asked, the tree's order, `/clips` opening on the section, Fit), `complete` (tab-completion of LoRA/trigger words), `continue` (continue a clip: the model facts, the step's length, the job, the refusals, the greyed menus and clip box, the Seconds row, the Clips group rows), `core-settings` (`shell/settings/coreSettings`: profile, tier lock and toggle), `defaults`, `delivery`, `desktop` (user-agent parsing), `guards` (6.12), `job`, `misc`, `omni` (the detail menu, each identity box's cut-out, the 1:4 to 4:1 shape pre-check), `order`, `selection` (Media selection logic), `send`, `triggers`, `video` (the size menu's tiers, seconds and frames, the job line) and `video-refs` (a video model's reference boxes). Result at this commit: 19 files, 143 tests, all pass.

## 6.10 Web e2e: Playwright against a fake hub

Playwright runs the built client in Chromium. There is no server at all: everything the page asks for is intercepted in the browser.

### How a spec starts (`tests/e2e/helpers.ts`, `open`)

```
open(page, path, hub = new FakeHub(), st = apiState()):
  await hub.attach(page)        // page.routeWebSocket(/\/bus$/, ...)
  st.broadcast = (t,d) => hub.broadcast(t, d, 'workspace')
  await mockApi(page, st)       // page.route(/\/api\//, ...), page.route(/\/(files|thumbs)\//, ...)
  await page.goto(path)         // served by `vite preview` on :4173
```

`process.env.MUTATION` injects a style tag after load (used to check that a spec fails when CSS is broken). Other helpers: `settle` (two animation frames), `rootScroll` (the eight scroll values that must be 0), `unnamedScrollers` (elements that scroll or clip with range but lack `data-scroll`), `regionRects` (bounding boxes of every `data-region` and `data-scroll`), `openSettings` (click `[data-region="utilities"]`, then the "Settings" menu item).

### HTTP: `fixtures/api.ts` (208 lines)

`mockApi` registers `page.route` handlers:
- `/files/...` and `/thumbs/...` are answered with a generated PNG (`fixtures/png.ts`, size from `?w=&h=`, default 1680x944 for files and 264x148 for thumbnails, colours from a hash of the path via `tint`).
- Every `/api/...` call is pushed to `st.calls` (`{method, path, body}`), so specs assert what the UI sent. Then a chain of `if (p === ...)` returns canned JSON: models, weights, draft (a `PUT` merges into `st.draft`), defaults, LoRAs, upload, media (delegated to `fixtures/media.ts` `mediaRoute`: Temp with groups, the Drive tree, favorite folders, characters, move, delete), settings (`PATCH` validated like the controller: a path containing "missing" is refused with `{code:'invalid', field, text}` and status 400), cards, network, assistant, Open WebUI models and tool servers, `/api/pair`, chat. Unknown paths return 404 `{text: 'Not found'}`.
- `ApiState` is the mutable fake database per test: `draft`, `loras`, `media`, `drive`, `chars`, `calls`, `uploads`, `settings`, `chat`, `owuiModels`, `weights`, `owuiKeep`, `owuiContext`, `mcpKey`, and `broadcast` (so a route can notify windows, e.g. `DELETE /api/assistant/chat` empties the draft and broadcasts `generate-image.draft`).
- Fixture constants give a deployment's shape with placeholder values: a Drive path, an engine folder, a device named `Desk` at a placeholder LAN address, and the server at a placeholder address on port 42010.

### The bus: `fixtures/controller.ts` (`FakeHub`, 129 lines)

`FakeHub.attach(page)` calls `page.routeWebSocket(/\/bus$/, ...)`. State: `boot`, `session`, `lines` (connected pages with role and screen), `got` (every message the client sent, in order), `jobs` (Map), `focus`, `engines`, switches `refuse`, `ghostWorkspaces`, `answerDeliveries`. Behaviour:
- On `hello` it registers the line and replies `welcome` (proto 1, the `boot`, version `0.1.0`, `limits`, one tool `generate-image` with tab order 10, `presence`, `focus`, current `jobs`), then broadcasts `presence`.
- `sockets` sets `focus` and broadcasts it to Media lines.
- `job.submit` replies `{job, state: 'queued', position: 1}` and creates a job (`j_00000001`...) with a summary carrying seeds; `setJob` broadcasts `job` to workspace lines. `job.cancel` replies and broadcasts `job.gone`.
- `send` (Media to Generate) finds the workspace line that has focus and sends it a `deliver` message; the client's `received` receipt is turned into a `delivery` message back to Media. `answerDeliveries = false` simulates no answer; with no focus it returns `delivery {status:'failed', reason:'no_tool'}`.
- `gpu.release` replies `{ok: true}`.
- Test controls: `setJob`, `dropJob`, `chat(view)` (an `assistant.chat` event), `broadcast`, `closeAll(code)` (close every socket with a given close code, e.g. 4000 for off, 4001 for new boot, 4003 for unpaired), `sent(type)`.
- `refuse = true` closes new sockets at once, which with `closeAll` drives the connection-cover specs. Changing `hub.boot` and closing with 4001 drives the "new boot reloads the page" spec.

`fixtures/data.ts` has deterministic data: three `MODELS`, `makeLoras(n)`, `job(id, patch)`, `summary(...)`, `mediaItems(n)`. `fixtures/mediaPage.ts` `twoWindows()` opens a Generate window and a Media window on the same `FakeHub` and `ApiState`, so delivery between them is testable.

### What the specs check

223 tests run in 32 spec files. `tests/e2e` holds 36 `*.spec.ts` files plus `fit.ts` and `helpers.ts`; the other 4 spec files contain only `@shot`-tagged tests, which the config excludes. Groups: Generate (`generate*.spec.ts`, `bar-*.spec.ts`, `library-sheet`, `chat`, `article`, `tab-complete`, `tab-references`, `seed-guidance`), Media (`media*.spec.ts`, `characters*.spec.ts`), Settings and cards (`settings.spec.ts`), connection (`connection.spec.ts`: short drop shows nothing, longer cut shows the cover and recovers, switched-off, unpaired stops retrying, new boot reloads, pairing page, no foreign requests), and layout. The layout specs are the design tests:
- `lock.spec.ts`: at 1366x768, 1920x1080, 2560x1440 and 3840x2160, for each of generate, generate-loras, settings, network, assistant, media and pair, the page never scrolls (the `rootScroll` values are zero), no unnamed scroller exists, and "full lists" keep scroll range.
- `scale.spec.ts` and `fit.ts`/`fit.spec.ts`/`narrow.spec.ts`/`bar-line.spec.ts`: root size matches `expectedRoot`, Media is at `MEDIA_SCALE`, nothing overlaps or escapes its column, text that clips has an ellipsis, the bottom bar stays on one line at 1366 wide with the widest values.
- `margins.spec.ts`: the measured gaps on Generate (`--gen-edge`, `--sp-4`, `--fs-ctl`, `--text-3`).
- `shot.spec.ts`, `shots.spec.ts`, `shots-v2.spec.ts`: screenshot specs tagged `@shot`/`@shots`, skipped unless `SHOTS` is set; they write PNGs under `web/shots/` or `SHOT_DIR` (the default is a folder outside the repo set in the spec file).

### Full stack (`web/tests/full`)

`stack.ts` `Stack` creates a temp dir, runs `tests/engine/helpers.make_engine_root` through `prepare.py` for a fake Wan2GP root, calls `python -m hub init`, then `hub serve` on a free port with a minimal environment (`PATH`, `HOME` in the temp dir, `LANG`), pairs with `hub pair`, and `stack.spec.ts` drives a Generate window and a Media window through the real controller, real worker and built UI. It refuses to start without `web/dist/index.html` ("run npm run build first"). It is separate from the 223-test run (`npm run full`); I did not run it (6.14).

## 6.11 HocusPocus Desktop (the desk client)

The `hp-desktop` source tree is a separate project (not part of the Hub repo, not in the Hub zip): an Electron 44.7.0 / TypeScript 5.9.3 app, version 1.2.1, built as a Linux AppImage with electron-builder (`package.json`: `"build": "tsc -p tsconfig.json && node scripts/copy-static.mjs"`, `"dist": "... electron-builder --linux AppImage"`; `release/` has the 1.1.0, 1.2.0 and 1.2.1 AppImages). Its own `KNOWLEDGE.md` describes it as "a private desktop client that shows HocusPocus web pages ("instances") in clean windows: no browser tabs, no address bar, one window per monitor if you want".

What matters to the Hub, all verified in `hp-desktop/src`:
- Instances. An instance is a saved name, address, monitor, full-screen flag, zoom and an optional `tag` (1-9 unique; the form offers None and 1-6; `src/shared/types.ts`). Saved in `~/.config/HocusPocus Desktop/instances.json` (`KNOWLEDGE.md` section 7). The Hub does not create instances; they are added by hand (`README-INSTALL.md` section 2: one for `/`, one for `/media`, each with a monitor).
- Pairing. Instance pages run in the persistent session `persist:hocuspocus`, so the `HttpOnly` cookie from `/pair` is kept and shared by all windows ("All Desktop windows share the one pairing", README). The cookie's life is `COOKIE_AGE = 34_560_000` s (400 days, `hub/core/web.py:19`).
- User agent. `controller.ts` `tagUserAgent()` appends ` HocusPocusDesktop/<version>` and, when instances carry tags, ` tags=2,3` (ascending) to the session's user agent and every open page's; it is refreshed when instances change. Nothing else about the server is in it.
- `insideDesktop` (`web/src/lib/desktop.ts`): true when `navigator.userAgent` matches `/HocusPocusDesktop\//`. `desktopTags()` parses `tags=` (digits and commas, ascending, ignores malformed). Tested in `tests/unit/desktop.test.ts`.
- `launchTargets()`: returns one entry `{label: String(n), url: 'hpd:instance/n'}` for each tag, or if none is tagged, a single `{label: 'Hub', url: location.origin + '/'}`.
- Use in the pages: both the Generate bar (`modules/generate-image/run/Taskbar.tsx`) and the Media bar (`screens/media/Bar.tsx`) show a monitor button (`data-region="launch"`) only when `insideDesktop()`. Its menu items call `window.open(url, '_blank', 'noopener')`.
- What the client does with `window.open`. `controller.ts` `popup()`: a URL with protocol `hpd:` and path `instance/<1-9>` opens the instance with that tag in a new window (focus if shown), using its own monitor and full-screen setting; if no instance has that tag nothing happens. Otherwise an address equal to a saved instance's address opens as that instance; any other address on the network opens a plain window; anything outside the network opens in the system browser, only if it follows a real click or key within 5 s.
- Network lock. The client blocks requests outside private ranges (`netpolicy.ts`, `privacy.ts`, `resolver.ts`), which matches the Hub's own no-outbound rule.
- It has its own tests: `npm test` runs `node --test dist/test/*.test.js` (`src/test/logic.test.ts`); `e2e/run.mjs` runs on a virtual X desktop. The Hub's suites do not run them.

Where the desk gets the Hub: the instance address is `http://<server address>:42010/` (and `/media`), after the first open of the one-time pairing link `http://<server address>:42010/pair#c=<code>` (README-INSTALL.md section 2). The first instance address contains the code; the README says to change it to the plain address afterwards "so the used code isn't kept". Nothing of the Hub is installed on the desk. (`hp-desktop/KNOWLEDGE.md` gives its own HocusPocus server on the server's address, port 42002; that is the engine's web UI, a different program from the Hub on 42010.)

## 6.12 Repo rules, and what enforces each

| # | Rule | Enforced by | Notes |
|---|---|---|---|
| 1 | Python files at most 300 lines | `tests/core/test_rules.py` `test_files_stay_small_and_typed` (`len(read_text().splitlines()) > 300`) | applies to `hub/**/*.py` only. `tests/`, `tools/`, `install/` are not measured; the largest test file is 672 lines (`tests/engine/test_generate_image.py`). Largest `hub/` file is `hub/core/engine.py`, 297 |
| 2 | Python files typed, `from __future__ import annotations` | same test (files over 3 lines must contain the import) | the full-hint rule itself is not machine-checked |
| 3 | TS, TSX, CSS and all `web/tests/**/*.ts` at most 250 lines | `guards.test.ts` "every source and test file is at most 250 lines" | measured as `split('\n').length`, which counts the empty piece after a final newline, so the effective limit is 249 lines as `wc -l` reports them. The largest files at this commit are 249 (`tests/e2e/settings.spec.ts`). `.py` in `web/tests/full/` is not measured |
| 4 | Ruff, line length 120, rules E F W I B UP, py313 | `pyproject.toml` `[tool.ruff]`; run by hand: `.venv/bin/ruff check hub tests` | no test or CI runs it; `docs/20-BUILD-SPEC.md` section 9 makes it part of "done". `web`, `wheels`, `.venv` are excluded. `tools/` and `install/helpers.py` are included by default. Passed at this commit |
| 5 | No `px` except 1px hairlines (and 0px) | `guards.test.ts` "every size is in rem" (regex over every CSS line, with the root clamp removed) | |
| 6 | No `px` font sizes, no inline `fontSize` | `guards.test.ts` "the root size is the one fluid clamp..." | it also requires the exact `--ui-base` clamp string in `base.css` |
| 7 | No `overflow: hidden`; only `[data-scroll]` may be `overflow: auto/scroll` | `guards.test.ts` "overflow: hidden is banned; only [data-scroll] scrolls" | expects exactly one `auto/scroll` rule, in `base.css`, with selector `[data-scroll]` |
| 8 | `html`, `body`, `#root`, `.app` use `overflow: clip` | `guards.test.ts` "html, body, #root and .app clip" | |
| 9 | No `console.*`, no `localStorage`/`sessionStorage`, no `http(s)://` in source | `guards.test.ts` "no console, no storage, no absolute URLs in source" | the one exception is the string `http://127.0.0.1:3000` (the Open WebUI address placeholder in the Assistant card). Applies to `src/**/*.ts(x)`, not to tests or CSS |
| 10 | The built client makes no external requests | `guards.test.ts` "the build makes no external requests" (scans `dist/*.js,css,html` for `http(s)://`; allows `https://react.dev/errors`, `http://www.w3.org/`; `index.html` may not load `src`/`href` from `//`) and `connection.spec.ts` (every browser request goes to `127.0.0.1:4173`) | the unit check silently passes when `web/dist` does not exist |
| 11 | Web modules import only `react`, `ui/`, `lib/` and their own folder (and `.css`) | `guards.test.ts` "modules import only react, ui/, lib/ and their own folder" | `screens/` and `shell/` are not restricted (Media imports `shell/registry`, `shell/Frame`) |
| 12 | Python modules import only `hub.core.api` | `tests/core/test_rules.py` `test_modules_import_only_the_api` (allows `hub.core.api`, the module's own package, and the bare name `hub.core`) and the stricter `tests/engine/test_rules.py` `test_modules_reach_core_only_through_the_api` (only `hub.core.api`, but only for the generate_image, loras and media modules) | |
| 13 | Core never imports modules | `test_core_never_imports_modules` | covers `hub/*.py` and `hub/core/*.py` |
| 14 | No HTTP clients; no `requests`/`httpx`/`aiohttp`/`urllib.request`/`http.client`/`smtplib`/websocket clients | `test_no_http_client_imports` (`BANNED`) | the Open WebUI link uses raw asyncio sockets (`docs/20-BUILD-SPEC.md` section 5) |
| 15 | No outbound network at run time (no telemetry, no fetching) | runtime audit hook `hub/core/netlock.py` in the controller, `hub/worker/netguard.py` in the worker; `tests/core/test_netlock.py` (outbound TCP, DNS, UDP blocked; loopback and Unix sockets allowed; the CLI installs the hook first) and worker tests in `tests/engine/test_worker.py` | the hook is enforcement; the import ban is the static half |
| 16 | No logs (no `logging`, no `print` outside the two allowed stdout lines and stderr failure lines) | `tests/engine/test_rules.py` `test_no_content_filters_and_no_logging`: no `logging` import and no `print(` | only for the worker, `engine.py`, `supervisor.py`, `autoreg.py` and the generate_image, loras and media modules. `hub/__main__.py` prints CLI output by design. No test covers the other `hub/` files; I found no `import logging` anywhere under `hub/` by search |
| 17 | No content filters (a list of filter words: safety, censor, content_filter, moderat and others) in engine code | same engine test; the web side has `guards.test.ts` "no banned copy" with filter-word regexes such as `/safety/i` | |
| 18 | The worker is standard-library only | `test_worker_is_stdlib_only` | |
| 19 | No literal secrets in source | `test_no_literal_secrets` (32+ char hex or mixed-case base64-like string constants) | |
| 20 | The installed controller venv equals the hash-pinned lock exactly | `test_installed_packages_match_the_lock_exactly` (skipped if the lock is absent; `HUB_VENV` checks another venv) | |
| 21 | No explanatory sentences, safety text or directive hints in UI copy | `guards.test.ts` "no banned copy" (a list of 16 regexes, e.g. `/nothing is logged/i`, `/never downloads/i`, `/detected/i`, `/safety/i`, `/generations appear here/i`) | a deny-list of phrases that were removed, not a style checker |
| 22 | Release zip under 28 MB, wheels match the lock | `tools/release.py` (`LIMIT_BYTES`, `verify_wheels`) | at release time, not in pytest |
| 23 | No dead code, no commented-out code, no TODO stubs; one source of truth per fact | none (review only) | stated in `docs/20-BUILD-SPEC.md` section 7 |
| 24 | Colours only from tokens; no px sizes; sizes from `--sp-*` | partly: rule 5 and 6 for px; nothing checks that colours come from tokens (some CSS uses `rgba(0,0,0,.45)` for shadows) | |
| 25 | Page never scrolls; no unnamed scroller | `web/tests/e2e/lock.spec.ts`, `scale.spec.ts`, `fit.spec.ts` (needs the browser) | complements rules 7-8 |

## 6.13 Release and install

### `tools/release.py`

Run from the repo root with `python tools/release.py [zip|wheels|lock]` (default `zip`).

- `zip`: calls `verify_wheels()`; if that fails it calls `fetch_wheels()` (download, then verify); then `build_zip()`.
- `wheels`: download wheels for the shipped lock for CPython 3.13 and 3.14 using `pip download --require-hashes --only-binary=:all:` with the manylinux platform tags 2_28 down to 2_5, 2014, 2010 and 1, into `wheels/`, then verify.
- `lock`: for each of `controller` and `dev`, resolves with `uv pip compile --generate-hashes` for both Pythons on `x86_64-manylinux_2_28`, requires the same pinned versions on 3.13 and 3.14, downloads the wheels for both, and rewrites `requirements/<name>.lock` listing only the hashes of the wheels that exist (so the lock and the wheel folder agree). Top-level requirements: controller = starlette, uvicorn, websockets, nvidia-ml-py, pillow; dev = pytest, pytest-asyncio, ruff (`TOP_LEVEL`). Only `controller` is shipped (`SHIPPED`).
- `verify_wheels`: every file in `wheels/` must be a `.whl` whose SHA-256 is in the controller lock; and an offline `pip download --no-index --find-links wheels --require-hashes` of the lock must succeed for each Python.

The zip (`build_zip`) is `dist/hub-release-YYYY-MM-DD-HHMM.zip`, written to a `.partial` file, deflate level 9, every entry under a top folder with the same name, dates set to today at 00:00, modes 0755 for executables and 0644 otherwise, and refused if 28 MiB or larger (`LIMIT_BYTES = 28 * 1024 * 1024`). Contents:

- Trees `hub`, `web/dist`, `install`, `deploy`, skipping any path part named `__pycache__`, `tests` or `node_modules`, any dot-part, `*.pyc`/`*.pyo`, `test_*.py`, `*_test.py`, `conftest.py`, and symlinks (`wanted`).
- All `wheels/*.whl`.
- `README-INSTALL.md` and `requirements/controller.lock`.
- It requires `web/dist/index.html` to exist ("Not ready to release, missing: ..."). It does not run the build; building `web/` first is the caller's job.

It does not contain: `pyproject.toml`, `tests/`, `tools/`, `docs/`, `web/src`, `web/node_modules`, `web/tests`, `dev.lock`. The newest zip in `dist/` at this commit (`hub-release-2026-10-13-0458.zip`) holds 145 files, 15.8 MB uncompressed, 15.1 MB zipped: 37 files in `hub/core`, 33 in `hub/modules`, 8 in `hub/worker`, 5 in `hub/`, 43 in `web/dist`, 12 wheels (the cp313 and cp314 builds of pillow and websockets, and the pure-Python ones: anyio, click, h11, idna, nvidia_ml_py, starlette, typing_extensions, uvicorn), 4 in `install/`, `deploy/hub.service`, `README-INSTALL.md`, `requirements/controller.lock`. `dist/` also holds 47 other zips of this and previous names (`hub-web-*`, `hub-stream-*`, `hub-node-*`, ...).

### `install/install-hub.sh` (159 lines) on the server machine

Run as the normal user, not root, from the unzipped folder: `unzip -q hub-release-<stamp>.zip && bash hub-release-<stamp>/install/install-hub.sh` (`README-INSTALL.md` section 1). Options: `--prefix DIR`, `--bind IP`, `--engine-root DIR`, `--engine-python FILE`, `--lora-folder DIR` (repeatable), `--python FILE`, `--no-firewall`, `--yes`. Steps in order:

1. Checks (`install-hub.sh:36-56`): not root; systemd and a reachable user manager (`need_user`); a system Python 3.13 or 3.14 with `venv` and `ensurepip` (`find_python`); `hub/__main__.py`, `web/dist/index.html`, `requirements/controller.lock`, `deploy/hub.service` present in the zip; the prefix path matches `^/[A-Za-z0-9._/+-]+$`; none of `venv hub web install data` exists in the prefix unless an earlier `.installed` file is there (`check_target`); the engine root (default `<prefix>/engine/app`, the Hub's own engine) has `wgp.py` and the engine Python is executable and starts, or, with no engine there and none given, the first settings name none and the end says to run `install-engine.sh`; the prefix is not inside the engine folder; LoRA folders exist (default: the real `<engine root>/loras` if it is a directory); the LAN address is found with `install/helpers.py lan` (the default-route interface, skipping `lo docker podman virbr br- veth cni flannel tailscale tun tap wg vnet zt` names; `--bind` must be one of the machine's addresses).
2. Defaults: `PREFIX` is the install prefix (at this commit a fixed default in `install-hub.sh`), engine root `$PREFIX/engine/app`, engine Python `$PREFIX/engine/env/bin/python`, data `$PREFIX/data`, launcher `~/.local/bin/hub`. No other program's folder is named.
3. Opens the record `$PREFIX/.installed` (every directory, file, service enable, linger and firewall rule it makes is appended, so `uninstall.sh` can reverse exactly those, newest first), creates `$PREFIX/.stage` for scratch and for the earlier versions it moves aside, and stops a running `hub.service` (remembering whether it was active).
4. Builds the venv `$PREFIX/venv` with `python -m venv`, then `pip install --no-index --find-links <zip>/wheels --require-hashes --only-binary=:all: -r requirements/controller.lock`, then uninstalls pip from it, and writes `hub-app.pth` containing `$PREFIX` so `import hub` works without installing the package. The venv is rebuilt only if the lock's SHA-256 or the Python minor version changed (`$venv/.hub-lock`). Nothing is downloaded.
5. Replaces `$PREFIX/hub`, `$PREFIX/web` (only `web/dist` is copied in) and `$PREFIX/install` with the zip's copies (copy excludes `__pycache__`, `*.pyc`, `tests`, `.pytest_cache`); the earlier versions are kept in `.stage` until the run succeeds.
6. If `$DATA/settings.json` exists it keeps it ("Keeping your settings and images"); otherwise runs `hub init --data $DATA --bind <LAN IP> [--engine-root ... --engine-python ...] --lora-folder ...`, which writes the first settings (bind = LAN IP + 127.0.0.1; port defaults to 42010, `hub/settings.py:21`; a linked `ckpts` is listed by the folder it links to).
7. Writes the `hub` launcher script `~/.local/bin/hub` (`HUB_DATA=<data> exec <prefix>/venv/bin/python -I -m hub "$@"`), unless a file by that name exists that is not in the record, in which case it prints the long form of the command instead.
8. Installs `~/.config/systemd/user/hub.service` from `deploy/hub.service` with `@PREFIX@` and `@DATA@` filled in: `ExecStart=@PREFIX@/venv/bin/python -I -m hub serve --data @DATA@`, `Restart=on-failure`, `RestartSec=5`, `StartLimitIntervalSec=0` (keeps retrying if the drive mounts late), `KillMode=control-group`, `TimeoutStopSec=30`, `UMask=0077`, `WantedBy=default.target`. It is a systemd user unit; it refuses to replace a unit it did not make.
9. Turns on lingering (`loginctl enable-linger`) if off, so the unit starts at boot without a login; if that fails it warns and prints the command to run with `sudo`. Enables the unit, checks the port is free, `systemctl --user start hub.service`, waits up to 30 s for the port to listen, and fails with "journalctl --user -u hub -n 20" if it does not.
10. Firewall (only when `firewall-cmd` exists, firewalld is running, and `--no-firewall` was not given): finds the zone of the LAN interface and, after asking once (default yes; asks for the `sudo` password), adds two rich rules, runtime and permanent: priority -20 accept TCP on the port from the LAN subnet, priority -19 reject TCP on the port from anywhere else. Each rule is recorded so it can be removed. Without a terminal and without `--yes` the answer is no. The README says the port rules should be re-created by running the installer again after a port change.
11. `finish_run`, then prints the pairing link made by `hub pair --name Desk` (valid once, within 10 minutes) with the HocusPocus Desktop steps.

`install/install-engine.sh` (Stage 10) makes upstream WanGP the Hub's own engine inside the prefix and `uninstall.sh --engine [--purge]` undoes it; part 5, 5.6.3.

On any error after the record is opened, `on_exit` rolls back: it undoes this run's changes in reverse and restores moved-aside directories, restarts a service that was running. `install/uninstall.sh [--prefix DIR] [--purge]` undoes the record (including asking for `sudo` to remove the firewall rules); it keeps `data/` unless `--purge`, and never removes the `auto_*.json` pointer files the running Hub writes into the engine's `finetunes` folder (README).

### Where things are on the server machine, and what an update never touches

| What | Path |
|---|---|
| Program | `<prefix>/{hub, web/dist, venv, install}` |
| Installer record | `<prefix>/.installed` |
| Data (settings, devices and pairing, Temp pictures in `data/outputs`) | `<prefix>/data` |
| Service and launcher | `~/.config/systemd/user/hub.service`, `~/.local/bin/hub` |
| Port and bind | 42010 on the LAN IP and 127.0.0.1 (`hub network show` / `set`) |
| Engine (read only, never started by the Hub's installer) | the engine's folder, wherever it was installed |

Re-running the installer from a newer zip replaces `hub/`, `web/`, `install/` and (if the lock or Python changed) `venv/`. It does not touch `data/` or anything in it (owner settings in `settings.json`, the Temp images, the paired devices), it does not touch the engine, the LoRA or model files, the Drive and Characters folders, or HocusPocus's service. The first start after an update erases what older versions kept about pictures (`README-INSTALL.md` "Update or repair"; code in `hub/core/files.py`). The desk's pairing is unaffected, since the device record is in `data/`; the cookie is still valid. The desk installs nothing: it opens `http://<server address>:42010/` and `/media` in HocusPocus Desktop.

CLI after install (`hub/__main__.py` `EPILOG`): `hub serve`, `init`, `pair --name`, `network show|set [--bind] [--port]|reset`, `restart` (also Settings > About > Restart and the Live box double-click post `POST /api/settings/restart`, routed at `hub/core/routes.py:34`, which calls `restart_service` in `hub/core/runtime.py`; the CLI `hub restart` is `_restart` in `hub/__main__.py`, running `systemctl --user restart hub.service` only if the unit is active).

## 6.14 The checks

| Check | Command |
|---|---|
| Server | `.venv/bin/python -m pytest` |
| Ruff | `.venv/bin/ruff check hub tests tools` |
| TypeScript | `npx tsc --noEmit` in `web/` |
| Web unit | `npx vitest run` |
| Web e2e | `npx playwright test` (files whose only tests are tagged `@shot` are excluded by `grepInvert`) |
| Full stack | `npm run full` |

Playwright takes its browsers from `PLAYWRIGHT_BROWSERS_PATH` when it is set. `npm run build` rewrites `web/dist`. The
suites' current counts are in `HANDOFF.md`.

## Gaps / unverified

- `docs/20-BUILD-SPEC.md` and several code comments cite `12-CONTROLLER`, `15-FEATURES`, `16-FRONTEND` documents; none of them is in `docs/` of this tree, so those section references (e.g. `bus.ts:1`, `helpers.ts:1`, `guards.test.ts:1`) cannot be followed.
- The ESLint comment in `Media.tsx` implies an ESLint setup; none exists in `web/` (no config, no dev dependency, no script). Whether linting is run elsewhere is unknown.
- `base.css` says colours come from `tokens.css` "(generated)". No generator is in the repo; `tokens.css` header says it came from the approved layout mockup `generate-layout-mockup-v14`, which is not in the repo.
- Slate vs Studio: only `/pair` still uses the Slate palette; nothing states whether that is deliberate.
- Unknown paths such as `/screen/3` are served by the server and fall through to the Workspace in `main.tsx`; the server's `/screen/{n}` route and `Presence.screens.aux` suggest a feature (numbered auxiliary screens) that the client does not implement. Not verified against the controller's bus code, which is outside this section.
- The "parallel agents share the preview server on 4173" convention is derived from the config (`--strictPort`, `reuseExistingServer: true`), not from a written rule. No document states it.
- `tests/full` (full stack) and the HocusPocus Desktop tests were not run. The hp-desktop description relies on reading its source and `KNOWLEDGE.md`, not on running it.
- The installer, the uninstaller, `tools/release.py wheels` and `lock` need `sudo`, systemd or the network; the installer behaviour above is from reading `install/*.sh`. What the server holds (the version installed, firewall rules, lingering) is not readable from the repository.
- `tools/release.py lock` writes `dev.lock` too, but `dev.lock` is not used by any script in the repo (the dev venv is not installed from it by anything in the repo).
- `ruff` is not part of `pytest` and no CI exists in the tree (no `.github`, no Makefile); every "clean before reporting" rule rests on whoever runs the commands.
- The guard for the 250-line limit measures `split('\n').length`, so a file's real limit is 249 lines; the 300-line Python guard uses `splitlines()`, so 300 is allowed. This asymmetry is as the code reads, not a documented decision.
- Dev-server pairing: whether `npm run dev` (proxy to 42010) works against a real hub from the dev machine depends on the guard's address rules (`hub/core/guard.py`); no test exercises it.
