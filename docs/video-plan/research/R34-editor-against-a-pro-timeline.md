# R34 — Edit Video against a professional timeline: what the Hub has, what Resolve and Premiere define, 2026-10-17

Research note. Hub read: the
code under `web/src/modules/sequence/`, `hub/core/{sequences,seqshape}.py`, `hub/worker/joincmd.py`. Browser editors
read in shallow clones under `/tmp/r34/` (commits and dates in §5). Every web page fetch failed from this container
(`getaddrinfo ENOTFOUND` for helpx.adobe.com, blackmagicdesign.com and others; curl through the proxy: 403), so
every vendor fact below is **search-summary-only** (marked [s]); the summary named the page it came from. Official
docs need not be within 60 days; the version each covers is stated where the summary gave one. Facts only.


> Correction (R41–R45): ai-video-editor's in-browser export does draw transitions; R44.

## 1. What Edit Video has today
- **Tracks.** Exactly two, always drawn, none added or removed: the file shape refuses any other count
  (`hub/core/seqshape.py:63`; `{"version": 2, "revision", "tracks": [[…], […]]}`, `:3-7`). Up to 200 items per
  track (`hub/settings.py:46`, `:223`).
- **Track 1** plays back to back, no gaps (`web/src/modules/sequence/seq.ts:19-25`), clips or sounds but not both
  (`hub/core/sequences.py:161`). **Track 2** holds items placed at `at` ms; a drop or move that would overlap is
  put right after the item it hits (`seq.ts:159-175`). A clip on track 2 gives its sound only.
- **Clip/item model.** `{clip|sound, in, out[, at]}`: frames of a clip, ms of a sound (counted as `fps` 1000),
  `out` exclusive (`seq.ts:6-14`; `seqshape.py:9-10`, `:87-88`). Non-destructive: only Save writes a file.
- **Trim.** Edge strips on each tile, dragged with the pointer, one PUT on release (`Track.tsx:87-109`,
  `:128-131`); In/Out drag-numbers in the bar (`Bar.tsx:44-63`); I/O keys at the playhead
  (`Sequence.tsx:70-78`, `:108`). On track 1 later tiles close up (the effect of a ripple trim, no mode); on
  track 2 the left edge moves `at` with `in` (`seq.ts:115-120`). No roll, slip or slide operation exists.
- **Split.** S or the tile menu "Split at playhead" cuts the *selected* item only, at the playhead
  (`Sequence.tsx:63-69`, `:109`; `seq.ts:131-136`; `Strip.tsx:68`). No all-tracks cut.
- **Delete.** Delete key or menu removes the item from the sequence (`Sequence.tsx:62`, `:107`); on track 1 this
  closes the gap (back-to-back model); on track 2 it leaves a gap.
- **Ordering.** Track 1: drag a tile into a gap (`Track.tsx:60-63`; `seq.ts:86-103`). Track 2: drag sideways to a
  new `at` (`Track.tsx:64-66`). Drop from Media or an own mp3/wav at the pointer time (`Track.tsx:70-84`).
- **Snapping.** Only to the item's own unit: one frame of a clip, 10 ms of a sound (`seq.ts:109-111`). No snap to
  other edges, the playhead or markers.
- **Transitions.** None. Backlog item 15 lists them as designed in Stage 11, not built (`docs/BACKLOG.md:53`).
- **Audio.** Track 1 clip sound stays with its picture (no unlink). Mix at Save: each track-2 item `atrim`,
  48 kHz stereo, `adelay`, then `amix … normalize=0` (or `volume=K`) at equal levels
  (`hub/worker/joincmd.py:139-149`).
  No per-item or per-track volume, pan, fade or keyframe; no mute/solo; no waveform (a sound tile shows an icon,
  `Track.tsx:124-126`).
- **Markers.** None in the file or the UI (the file holds ids, order, in/out and `at` only, `sequences.py:33`).
- **Undo.** None. Every edit is a compare-and-swap PUT on `revision` (`web/src/modules/sequence/load.ts:105-125`;
  `hub/core/sequences.py:149-163`); no history is kept.
- **Navigation.** Space, Left/Right one frame (track 1), Home/End (`Sequence.tsx:100-106`); zoom 1×/2×/4× =
  1.5/3/6 rem per second (`seq.ts:77`; `Strip.tsx:14`). No J/K/L shuttle.
- **Preview.** Two `<video>` players swapped at each cut (`Player.tsx:13-15`); sounds through hidden `<audio>`
  elements re-seeked when off by >0.25 s (`Sounds.tsx:9-10`, `:32-42`): "a preview, not sample-exact".
- **Export.** Save queues `sequence.join` on the engine lane; ffmpeg in the worker: stream copy when every item is
  whole and alike and track 2 is empty, else libx264 CRF 18 `medium` + AAC 192k on the first clip's canvas,
  letterboxed (`joincmd.py:174-197`, `:96-118`); WAV 16-bit 48 kHz stereo when track 1 holds no clip
  (`joincmd.py:160-171`). Video over video is "later" (`docs/BACKLOG.md:154-155`).

## 2. Resolve and Premiere timeline models [s]
Resolve: current is **21.1** (released 2026-09-08/09, IBC; 21.1.1 by early October added "trim editor improvements for
audio clips") — RedShark, SVG News, Phoronix summaries. Premiere: current **26.5.2** (September 2026; release notes
updated 2026-10-12) — Adobe release-notes summary. The help pages below are Adobe's current "premiere/desktop" set.

- **Tracks.** Resolve: video and audio tracks added freely (no manual text reached). Premiere: any number of
  video/audio tracks, "limited only by system resources"; audio track types Standard, Mono, Adaptive, 5.1; up to
  32 channels.
- **Trims.** Resolve: Trim Edit mode (T) does ripple, roll, slip or slide by where the pointer sits on the clip;
  Dynamic Trim (W) trims with J/K/L during playback; Cut page: slip, roll and an A/B trimmer in the viewer.
  Premiere: Ripple Edit B, Rolling Edit N, Slip Y, Slide U; Ctrl/Cmd-click with Ripple gives Rolling.
- **Razor.** Resolve: Blade Edit mode (B) cuts the clip under the pointer, linked partners too when Linked
  Selection is on; blade at playhead Ctrl+B or Ctrl+\ (sources disagree). Premiere: Razor C; Add Edit Ctrl/Cmd+K,
  Add Edit to All Tracks Ctrl/Cmd+Shift+K; Alt/Opt-click cuts only the audio or video of a linked clip.
- **Delete.** Resolve: ripple delete Shift+Backspace; Backspace lifts (leaves a gap). Premiere: not in the summaries.
- **Snapping.** Resolve: N (Edit and Fairlight pages). Premiere: S, "Snap in Timeline".
- **Transitions.** Resolve: Effects Library; audio crossfades +3/0/−3 dB; Alt+right-click a cut for a 0 dB
  crossfade. Premiere: Apply Video Transition Ctrl/Cmd+D, Audio Transition Ctrl/Cmd+Shift+D; on-clip transition
  handles (26.0); Shape Dissolve (26.3).
- **Audio levels.** Resolve: volume line in the clip, Alt-click for a keyframe, Inspector Clip Volume keyframe,
  fade handles at clip edges. Premiere: rubber band and Pen-tool keyframes; clip keyframes vs track keyframes;
  Audio Clip Mixer writes keyframes from faders; Global Mute (26.2).
- **Markers.** Both: M at the playhead. Premiere 26.2 adds a Sequence Index panel.
- **Linked A/V.** Resolve: Linked Selection toggle (chain icon); blade and trim act on linked partners. Premiere:
  linked clips move and trim as one; Clip > Unlink; Link Ctrl/Cmd+L; Linked Selection toggle.
- **J/L cuts.** Premiere: own help page; turn Linked Selection off and drag the audio or video edge on its own.
  Resolve: not found in the summaries.
- **Undo.** Resolve: Ctrl/Cmd+Z, Ctrl/Cmd+Shift+Z (cheat sheets); a history window not confirmed. Premiere: up to
  32 recent changes; History panel steps through states.

- Resolve rows come from third-party tutorials and forum quotes of the manual; the Blackmagic manual itself was not
  reached by search or fetch. Premiere rows come from helpx.adobe.com pages named in the summaries.

## 3. Feature × Resolve × Premiere × Hub
| Feature | Resolve | Premiere | Hub Edit Video |
|---|---|---|---|
| Add/remove tracks | has | has | lacks (two fixed) |
| Separate video and audio tracks | has | has | lacks (a track holds clips or sounds; track 2 audio only) |
| Overwrite / insert on a track | has | has | insert only on track 1; place on track 2 |
| Trim an edge by drag | has | has | has (edges, I/O keys, In/Out fields) |
| Ripple trim | has (mode) | has (B) | has as a side effect on track 1; track 2 does not follow |
| Roll, slip, slide | has | has | lacks |
| Razor at pointer / across all tracks | has | has | lacks |
| Split at playhead | has | has (Add Edit) | has (selected item only) |
| Ripple delete / lift | has / has | has / has | track 1: ripple only; track 2: lift only |
| Reorder by drag | has | has | has (track 1) |
| Snapping to edges/playhead/markers | has | has | lacks (frame/10 ms quantise only) |
| Video transitions | has | has | lacks |
| Audio crossfade / fades | has | has | lacks |
| Clip volume, keyframes | has | has | lacks (equal-level mix) |
| Track volume, mute, solo; waveforms | has | has | lacks |
| Markers | has | has | lacks |
| Linked A/V, unlink | has | has | lacks (a track-1 clip's sound cannot be detached) |
| J/L cuts | not found [s] | has | lacks |
| Undo / redo | has | has (32 steps) | lacks |
| J/K/L shuttle | has | has | lacks (Space, frame step, Home/End) |
| Zoom | continuous | continuous | three steps |
| Export | render page / export, many codecs | Export, many codecs | one MP4 (copy or x264) or one WAV |

## 4. The ten most-used operations in a cut
- No source found that **ranks** editing operations by use. Searches for keyboard-usage studies, editor surveys
  and telemetry returned none; the nearest is an informal 2013 Creative COW thread asking FCP X editors for daily
  shortcuts, with no tally [s].
- What sources **name as core**, unranked [s]:
  - Resolve shortcut sheets: in/out marking, J/K/L playback, edit-mode switches, blade, frame nudging.
  - Clipchamp and Adobe Firefly video editor help: undo, copy/paste, split, play/pause, seek.
  - Adobe "trimming" tutorials and Larry Jordan: regular trim, ripple, roll; slip and slide as the further pair.
  - Adobe help set: razor/add edit, ripple delete, snapping, markers, linked selection, J/L cuts, default transition.
- The union of these lists, in no order: play/shuttle (J/K/L), mark in/out, split/razor, trim, ripple trim,
  ripple delete, roll, slip/slide, move/reorder, snap, undo, add transition/crossfade, set audio level, marker.

## 5. Browser timeline editors with commits in the last 60 days
| Repo | Last commit | License | Stack |
|---|---|---|---|
| ronak-create/FableCut | `a963fa5` 2026-10-17 | MIT | plain JS, DOM rows, canvas compositor, Node + ffmpeg |
| MartinDelophy/ai-video-editor | `669b1f7` 2026-10-17 | MIT | React (JSX), WebCodecs export via mediabunny |
| trykimu/videoeditor ("Kimu") | `6a30d43` 2026-09-10 | AGPL-3.0 dual | React Router, Remotion player, server render |
| OpenCut-app/OpenCut | `e668010` 2026-09-24 | MIT | rewrite in progress (Rust core); no timeline code yet |

- Outside the window (default-branch HEAD): opencut-classic `cf5e79e` 2026-05-17; freecut `4d62e80` 2026-08-07;
  twick `3044c23` 2026-05-07; designcombo/react-video-editor `9a8c529` 2026-06-29; react-timeline-editor
  `4148f4a` 2026-01-25; omniclip `cbe581a` 2025-08-07. OpenChatCut (`72ddb33`, 2026-10-15, AGPL) is Electron.
- **FableCut.** Data: one `project.json`; clips `{id, mediaId, kind, track, start, in, duration, name, props}`,
  tracks `[{id, kind, gain?, pan?}]`, default V3…V1 + A1…A4, `markers [{t, label?}]` (`app.js:523-532`, `:14-16`).
  Ops in one DOM-free module shared with its MCP server: split, ripple delete, close gap, lift/extract,
  insert/overwrite, ripple/roll/slip/slide, crossfades (`edit-ops.js:1-8`); each trim takes a `delta`, returns
  the clamped delta or a refusal string, and the drag restores a start-of-drag snapshot before each call
  (`edit-ops.js:699-708`); ripple `:770-774`, roll `:807-810`, slip `:827-830`, slide `:849-853`. Linked A/V
  via `linkGroup` (`edit-ops.js:173-187`). Snap targets clips, playhead, markers, in/out, frames
  (`app.js:473`, `snapInfo` `:3852`). Undo: JSON snapshots of clips+markers, 100 deep (`app.js:2238-2262`).
  Audio: per-clip `volume`, preview through AudioContext and export through OfflineAudioContext (`app.js:6347`).
  Export: browser renders frames, server ffmpeg encodes JPEG frames, or WebCodecs H.264 muxed by the server, or
  MediaRecorder fallback (`README.md:309-320`; `server.js:294`). Each clip is a DOM `div` (`app.js:3353`).
- **ai-video-editor.** Data: a gapless "main visual" sequence plus timed lanes for audio/captions — the same split as
  the Hub's track 1 / track 2; ripple shifts timed clips after an edit point and excludes main visuals because they
  are "already a gapless sequence" (`src/lib/timelineRipple.js:19-26`). Snap points: timeline ends, playhead,
  markers (point and range), clip edges (`src/lib/timelineSnap.js:14-31`). Undo: past/current/future, limit 50
  (`src/lib/editorHistoryCore.ts:1-26`). Clip gain in dB on the timeline (`src/components/TimelineGain.jsx:7-10`).
  Export: WebCodecs `VideoEncoder` + mediabunny (`src/lib/offlineVideoExport.js:16`, `:378`), audio through
  OfflineAudioContext (`src/lib/audioExport.js:111`); transitions are listed as unsupported for that path
  (`src/lib/projectRenderPlan.js:39`).
- **Kimu.** Data: tracks `{id, scrubbers[], transitions[], muted?}`; a clip ("scrubber") stores `left`/`width` in
  pixels, `y` track index, `trimBefore`/`trimAfter` in frames, `volume`, `muted`, keyframes
  (`app/components/timeline/types.ts:50-87`); a transition sits between two clip ids with a duration in frames
  (`types.ts:20-28`), rendered by Remotion `TransitionSeries` (`app/video-compositions/VideoPlayer.tsx:3`,
  `:256`). Ripple only with Alt on a right-edge resize, same track (`app/hooks/useTimeline.ts:1490-1493`). Snap to
  clip edges, playhead, grid with a zoom-scaled pixel threshold (`app/hooks/useSnapPoints.ts:4`, `:17-38`). Undo:
  session-only stacks of whole-timeline clones, 100 deep (`useTimeline.ts:35-50`). Render: `@remotion/renderer`
  `renderMedia` on a Node server with a BullMQ queue (`app/videorender/videorender.ts:1-18`).
- Common to the three: one JSON document of tracks and clips (times in seconds or frames; Kimu in pixels), undo
  as whole-document snapshots capped at 50-100, snap to clip edges and the playhead; FableCut and ai-video-editor
  also snap to markers.

## 6. Not known
- The Resolve 21 manual's own text for trims, linking, audio and undo (no page reached; rows rest on tutorials).
- Any ranked usage frequency of editing operations (no study found).
- How Edit Video behaves on the server (not yet run there).
- Whether FableCut's or Kimu's ops behave as their comments say (read, not run).

Repos: https://github.com/ronak-create/FableCut, https://github.com/MartinDelophy/ai-video-editor,
https://github.com/trykimu/videoeditor, https://github.com/OpenCut-app/OpenCut.

Sources (web, all search-summary-only): [Resolve 21.1, RedShark](https://www.redsharknews.com/davinci-resolve-21.1-new-features-release),
[SVG News 2026-09-09](https://www.sportsvideo.org/2026/09/09/ibc-2026-blackmagic-design-releases-davinci-resolve-21-1/),
[Phoronix](https://phoronix.com/news/DaVinci-Resolve-21.1), [Resolve Cut page](https://www.blackmagicdesign.com/products/davinciresolve/cut/),
[Resolve forum: blade/linking](https://forum.blackmagicdesign.com/viewtopic.php?f=21&t=80127),
[Videomaker: Resolve trim](https://www.videomaker.com/how-to/editing/editing-technique/how-to-use-the-trim-tool-in-blackmagic-davinci-resolve/),
[DaVinci Resolve Club: fades](https://davinciresolveclub.com/fade-audio-davinci-resolve/),
[Premiere release notes](https://helpx.adobe.com/premiere-pro/kb/fixed-issues.html),
[ripple](https://helpx.adobe.com/premiere/desktop/edit-projects/trim-clips/perform-ripple-edits.html),
[rolling](https://helpx.adobe.com/premiere/desktop/edit-projects/trim-clips/perform-rolling-edits.html),
[slip](https://helpx.adobe.com/premiere/desktop/edit-projects/trim-clips/perform-slip-edits.html),
[link A/V](https://helpx.adobe.com/premiere/desktop/add-audio-effects/basic-audio-editing/link-audio-and-video-clips.html),
[J and L cuts](https://helpx.adobe.com/uk/premiere-pro/using/perform-j-and-l-cuts.html),
[shortcuts](https://helpx.adobe.com/premiere/desktop/get-started/keyboard-shortcuts/default-keyboard-shortcuts.html),
[History panel](https://helpx.adobe.com/premiere-pro/using/correcting-mistakes.html),
[audio track types](https://helpx.adobe.com/au/premiere-pro/using/overview-audio-audio-mixer.html),
[add tracks](https://helpx.adobe.com/premiere/desktop/edit-projects/change-clip-sequence/add-tracks.html),
[Creative COW shortcut survey](https://creativecow.net/forums/thread/simple-keyboard-shortcut-survey/),
[Clipchamp shortcuts](https://support.microsoft.com/en-us/clipchamp/keyboard-shortcuts-for-clipchamp).
