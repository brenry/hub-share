# Desktop client: build instructions

A desktop client opens the Hub's web pages as windows, one per monitor, and remembers where each one goes. It is a
separate program; nothing of the Hub runs inside it. These instructions are complete enough to build one from
nothing with Electron, or to strip an existing Electron app down to one.

## Base
- **From nothing (shortest):** a new Electron app in TypeScript, packaged with electron-builder. Steps below.
- **From ComfyUI's desktop app:** <https://github.com/Comfy-Org/Comfy-Desktop> (Electron, Vue 3, TypeScript,
  electron-vite, electron-builder; Linux `.deb` and AppImage; Node 22+, pnpm 10+ via `corepack enable`; source in
  `src/main`, `src/preload`, `src/renderer/src`). Keep its window and packaging code; remove the parts that install
  and run ComfyUI; add the behaviour below. Its licence is AGPL-3.0-or-later, so a client derived from it is too.
  (The older <https://github.com/Comfy-Org/desktop> is archived and points to the one above.)

## The Hub's pages
| Address | Window |
|---|---|
| `http://<server>:42010/` | Workspace: the tabs Generate Image, Edit Video, Storyboard, Casting, Stage, and Settings |
| `http://<server>:42010/media` | Media: Temp, Drive, Characters, Sounds |
| `http://<server>:42010/clips` | Media, opened on Clips |
| `http://<server>:42010/pair#c=<code>` | Pairing, opened once (`hub pair --name <device>` on the server prints it) |

`?label=<text>` on a page address names that window to the Hub (`web/src/main.tsx`). Any number of windows may open
the same address.

## Build from nothing
1. `npm init -y`; `npm i -D electron electron-builder typescript`; a `tsconfig.json` compiling `src/` to `dist/`.
   `package.json`: `"main": "dist/main.js"`, scripts `"build": "tsc"`, `"start": "tsc && electron ."`,
   `"dist": "tsc && electron-builder --linux AppImage"`.
2. `src/config.ts`: read and write `instances.json` under `app.getPath('userData')`. One record per window:
   `{ id, name, url, display, fullscreen, zoom, tag }`. `display` is the index into `screen.getAllDisplays()`;
   `zoom` a number (1 = 100 %); `tag` an integer 1-9, unique, or `null`.
3. `src/main.ts`, at `app.whenReady()`:
   - **One session for every window:** `const ses = session.fromPartition('persist:hub')`, passed as
     `webPreferences.session` to each `BrowserWindow`. Pairing sets an `HttpOnly` cookie on `/pair`; one shared
     session means one pairing serves every window. The cookie lasts 400 days (`hub/core/web.py`).
   - **The client's mark:** `ses.setUserAgent(ses.getUserAgent() + ' <TOKEN>/<version>' + tags)`, where `<TOKEN>` is
     the name the Hub's pages look for (the `TAG` pattern in `web/src/lib/desktop.ts`) and `tags` is
     ` tags=<n>,<n>` with the instances' tags ascending, or `''` when none has one. Set it again whenever the
     instances change. Changing `<TOKEN>` means changing the same pattern in `desktop.ts`.
   - **One window per instance:** `new BrowserWindow({ x, y, width, height, fullscreen, webPreferences: { session:
     ses, contextIsolation: true } })`, with `x, y, width, height` from `screen.getAllDisplays()[display].bounds`;
     `win.loadURL(url)`; `win.webContents.setZoomFactor(zoom)`.
   - **The monitor button's links:** `win.webContents.setWindowOpenHandler(({ url }) => ...)` on every window. For
     `hpd:instance/<n>`: show and focus the window of the instance with tag `<n>`, opening it on its display if it is
     closed; do nothing for an unknown tag. For an address equal to a saved instance's `url`: the same, for that
     instance. Return `{ action: 'deny' }` in both cases. Any other address on the server: `{ action: 'allow' }`.
   - **Network lock:** `ses.webRequest.onBeforeRequest((d, cb) => cb({ cancel: !isPrivate(d.url) }))`, where
     `isPrivate` passes the server's address, `localhost`, `127.0.0.1` and the private ranges (10/8, 172.16/12,
     192.168/16). The Hub's pages make no outbound requests.
4. **The instance list:** one more `BrowserWindow` loading a local `src/ui/index.html` (with its own `style.css`):
   a table of the instances, a form to add or edit one (name, address, display, full screen, zoom, tag), and Open.
   It talks to the main process through a preload script (`contextBridge.exposeInMainWorld`) and `ipcMain.handle`
   for `list`, `save`, `remove`, `open`. Its look is entirely the client's own CSS.
5. `npm run dist` writes the AppImage under `dist/`. Run it with `--no-sandbox` on systems that need it.

## What the Hub does across windows
Moving media between windows needs nothing from the client. Each page keeps one WebSocket to the Hub
(`hub/core/bus.py`: presence, focus, socket declarations). Media's right-click menu ("Put in …", "Replace …", "Add as
reference"; `web/src/screens/media/send.ts`) sends to whichever Workspace tool is focused, in any window, on any
monitor. The client only keeps the windows open and paired.

## Layout
One instance per window. Any number of windows on any number of monitors; the Workspace may be open more than once,
each window on a different tab.

## Styling
The Hub's pages carry their own styles (`web/src/styles/`); the client does not restyle them. The client styles its
own instance list.

## Checks
- A Workspace window inside the client shows the monitor button in the Generate bar; the same address in a plain
  browser does not.
- With instances tagged 1 and 2, the button lists 1 and 2; choosing 2 opens or focuses instance 2 on its display.
- Pairing in one window, then opening a second window on `/media`, needs no second pairing.
- From Media, "Put in …" on a picture fills the box of the Workspace tool focused on another monitor.
- A request to an address outside the private ranges is cancelled.
