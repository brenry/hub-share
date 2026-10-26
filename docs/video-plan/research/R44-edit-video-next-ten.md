# R44 — Edit Video's next ten features: three browser editors and what the Hub's data has, 2026-10-17

Research note. Builds on R34 (cited "R34 §n", not repeated). Hub read:
`hub/modules/sequence/`, `hub/core/{seqshape,sequences}.py`, `hub/worker/joincmd.py`, `web/src/modules/sequence/`.
The three editors are R34 §5's, read in the shallow clones R34 made under `/tmp/r34/` (reused, commits checked):
FableCut `a963fa5` (2026-10-17, MIT), ai-video-editor `669b1f7` (2026-10-17, MIT), Kimu (`trykimu/videoeditor`)
`6a30d43` (2026-09-10, AGPL-3.0 or commercial, `LICENSE.md:1-11`). Read, not run. No web fetch was made. Facts only.

The ten: roll trim, slip, slide, transitions, audio levels, markers, undo/redo (asked), and three from R34 §3's
"lacks" rows: **ripple delete** (R34 §3 "track 1: ripple only; track 2: lift only"; R34 §4 names it in the Adobe help
set and the union of core operations), **linked A/V and J/L cuts** (R34 §3 "a track-1 clip's sound cannot be
detached"; J/L cuts need the unlink, R34 §2), **track mute/solo/lock** (R34 §3 "track volume, mute, solo: lacks").

## 1. Feature × editor
| Feature | FableCut | ai-video-editor | Kimu |
|---|---|---|---|
| Roll | `rollEdit` edit-ops.js:810 | `rollVisualBoundary` src/lib/fineEdit.js:63 | not found |
| Slip | `slipClip` edit-ops.js:830 | `slipVisualSegment` fineEdit.js:32 (video only) | not found |
| Slide | `slideClip` edit-ops.js:852 | `slideVisualSegment` fineEdit.js:98 (middle clips only) | not found |
| Transitions | per-clip `transitionIn/Out`, 16 types, canvas | per-segment `transition`, 8 types, canvas | between clip ids, Remotion |
| Clip volume | `props.volume` 0-2, `props.gain` dB | `volume` 0-4, `muted` | `volume` 0-1, `muted` |
| Fades / volume keyframes | fade curves; `keyframes.volume` | `fadeIn`/`fadeOut`; no volume keyframes found | volume lane typed, not rendered |
| Markers | `{t, label?}`, M | `{id, type, time, endTime?, notes, color}`, M | not found |
| Undo/redo | JSON snapshots, 100 | past/current/future, 50 | timeline clones, 100 |
| Ripple delete | `rippleDelete` edit-ops.js:352 | main lane gapless; timed lanes via ripple toggle | no (delete leaves gap) |
| Linked A/V, J/L | `linkGroup`, unlink Ctrl+L; no J/L op | `sourceAudioLinked`, per-clip offsets | not found |
| Track mute/solo/lock | disabled, solo, locked, untargeted | per-lane visibility and locks | `muted` toggle, not rendered; no lock |

### Roll, slip, slide
- **FableCut.** Data: clip `start`, `in`, `duration` in seconds (`app.js:523`). Each op takes a `delta`, clamps it and
  returns it, or a refusal string (`edit-ops.js:774-870`); roll moves left tail and right head (`trimGroupTail`,
  `trimGroupHead(..., true)`, `:748-767`); slip changes `in` only, for every linked partner (`:830-850`); slide
  moves `start` and its neighbours' tail/head (`:852-870`). Tools V/B/R/Y/U (`EDIT_TOOLS`, `app.js:3936-3942`),
  drag in `startTrimToolGesture` (`app.js:3975`). Preview and export read the same document; nothing extra.
- **ai-video-editor.** Main visual lane is an ordered gapless list; fields `duration`, `sourceStart`,
  `sourceDuration`, `playbackRate` (`fineEdit.js:5-19`). Roll at boundary *i*: previous `duration` +d, next
  `duration` −d and `sourceStart` +d (`:63-91`). Slide changes only the two neighbours, the slid clip's fields stay,
  its position follows from the list (`:98-127`). Slip moves `sourceStart` (`:32-45`). Drag
  (`src/components/Timeline.jsx:429-430`); roll by a keyboard step at a selected edit point (`Timeline.jsx:1244`).
- **Kimu.** No roll, slip or slide: no such names in `app/hooks/useTimeline.ts` or `app/components/timeline/`.

### Transitions
- **FableCut.** `transitionIn`/`transitionOut` `{type, duration, curve?}` on a clip (`serializeClip`, `app.js:1543`);
  types in `TRANSITIONS` (`app.js:86-88`). Drawn per frame by `evalProps` → `applyTransition` (`app.js:8350-8358`,
  `:8387`) as offsets, opacity or wipe on the clip in the canvas compositor; the clips overlap on the timeline.
  `crossfadeCut` extends both clips into spare media and sets audio `fade` "power" plus video `fade`
  (`edit-ops.js:920-950`). Export draws the same frames in the browser, ffmpeg encodes them (`README.md:311-319`).
- **ai-video-editor.** `segment.transition {id, duration}` (default 0.5 s, min 0.1) at a segment's end
  (`src/lib/offlineVideoExport.js:276-282`); ids in `src/config/editor.js:276-286`. Preview: a CSS layer with
  `--transition-progress` (`src/components/PreviewStage.jsx:822`). WebCodecs export: `renderCompositionAt` draws the
  next segment from its start during the last `duration` of the outgoing one (`offlineVideoExport.js:252`, `:276-334`)
  via `drawPreviewFrame` (`src/lib/media.js:1167`, `:1285-1293`). The headless ffmpeg plan `buildFfmpegRenderPlan`
  refuses transitions (`src/lib/projectRenderPlan.js:39`, `:73`) — that is R34 §5's "unsupported" path.
- **Kimu.** `Transition {presentation fade|wipe|clockWipe|slide|flip|iris, timing spring|linear, durationInFrames,
  leftScrubberId, rightScrubberId}` in `track.transitions` (`app/components/timeline/types.ts:20-28`, `:83`); clips
  keep `left_/right_transition_id`. Added by `handleAddTransitionToTrack` (`useTimeline.ts:833`). Preview and render
  are one Remotion composition: `TransitionSeries.Transition` between `Sequence`s
  (`app/video-compositions/VideoPlayer.tsx:240-293`); render `renderMedia` of `TimelineComposition`
  (`app/videorender/videorender.ts:2`, `:69`).

### Audio levels
- **FableCut.** `props.volume` (default 1, `app.js:48`; max 2, `VOL_MAX` `:3459`), clip gain `props.gain` dB before
  volume (`:54`, `clipGainDb` `:175`), track `gain`/`pan` (`trackGainDb` `:180`), master gain (`:182`). `volume` is
  in `ANIMATABLE` (`:82`): keyframes `{t, v, ease}` read by `volumeAtLocal` (`:3481-3482`). Fade shapes power/
  linear/exp (`audioFadeGain`, `:8366-8372`). One Web Audio graph for preview (AudioContext) and export
  (OfflineAudioContext, `renderAudioMix` `:13848`, `:13861`) — "what plays is what renders" (`:6340-6347`).
- **ai-video-editor.** Audio segment `volume` 0-4 (0 when `muted`), `fadeIn`, `fadeOut` seconds
  (`makeAudioInput`, `src/lib/audioExport.js:10-24`); one envelope for preview and export
  (`scheduleAudioEnvelope` `:30`, `mixOfflineAudio` `:73`). Gain handle −60 to +12 dB on the clip
  (`src/components/TimelineGain.jsx:5-11`); fade sliders 0-3 s (`VoicePanel.jsx:1059-1060`). The ffmpeg plan writes
  `volume=<v>` per segment (`projectRenderPlan.js:65-68`). No volume keyframes found.
- **Kimu.** Scrubber `volume` 0-1, `muted` (`types.ts:70-72`) → Remotion `volume` callback (`VideoPlayer.tsx:164`,
  `:181`). `"volume"` is a keyframe property (`types.ts:140`; `v2/KeyframeLanes.tsx:12`), but `getTimelineData`
  passes no keyframes to the composition (`useTimeline.ts:147-184`) and no file under `app/video-compositions/`
  reads them.

### Markers
- **FableCut.** `project.markers [{t, label?}]` (`app.js:524`); M adds or removes at the playhead, also while
  playing (`toggleMarker`, `:4521-4530`); Shift+M next/previous (`goToMarker`); snap target (R34 §5); in undo
  snapshots (`:2240`).
- **ai-video-editor.** `{id, type marker|chapter|range|note, time, endTime (range), notes, color}`
  (`src/lib/timelineMarkers.js:1-2`, `:21-45`); absolute seconds, never moved by a ripple (`:15-19`); M key
  (`src/hooks/useTimelineMarkers.js:51`). Not in any export.
- **Kimu.** None found.

### Undo/redo
- **FableCut.** `undoSnapshot` = JSON of clips, markers, comps; `pushUndo` caps 100 and clears redo
  (`app.js:2238-2269`). Drag gestures push the pointer-down clips array. Track state is not in the snapshot.
- **ai-video-editor.** `pushEditorHistory` limit 50 (`src/lib/editorHistoryCore.ts:17-28`); snapshot of project
  content (`createSnapshot`, `src/hooks/useEditorHistory.js:18`); Ctrl/Cmd+Z (`:377`).
- **Kimu.** Session-only stacks of `structuredClone(timeline)`, 100 (`useTimeline.ts:35-73`); Ctrl+Z,
  Ctrl+Shift+Z (`app/routes/home.tsx:457-463`).

### Ripple delete
- **FableCut.** `rippleDelete` removes clips with linked partners, merges the removed ranges per targeted unlocked
  track and pulls later clips left (`edit-ops.js:352-422`); `rippleDeleteSelected` (`app.js:2872`). Lift/extract
  over a range: `liftRange` (`edit-ops.js:871`).
- **ai-video-editor.** Main visuals are gapless, so removing one closes the gap; with the `rippleEditing` toggle
  (`Timeline.jsx:2921-2931`) `applyTimelineRipple` shifts timed audio/caption clips after the edit point, skipping
  locked lanes (`src/lib/timelineRipple.js:19-40`; caller `src/App.jsx:323`).
- **Kimu.** `handleDeleteScrubber` removes the clip and its transitions, no shift (`useTimeline.ts:339`); ripple only
  on Alt + right-edge resize (`handleRippleEdit`, `:1490-1493`).

### Linked A/V and J/L cuts
- **FableCut.** `linkGroup` (or legacy `linkedId`) ties picture and stems; `unlinked: true` blocks re-pairing
  (`edit-ops.js:174-196`); every trim, slip, slide, delete acts on `withLinked`. Ctrl/Cmd+L toggles
  (`toggleLinkSelected`, `app.js:2312`). J/K/L are shuttle keys (`app.js:15266`); no J/L-cut op — unlink, then trim
  one partner.
- **ai-video-editor.** The video's own audio is a "source" lane: `sourceAudioOffset`, `sourceAudioDisabled` per video
  segment, `sourceAudioLinked` on the project (`src/lib/sourceAudioSync.js:37-47`, `:73`, `:101`;
  `browserEditPlan.js:477`). No J/L-cut op found.
- **Kimu.** None: a video scrubber's sound plays from the same Remotion `<Video>`.

### Track mute/solo/lock
- **FableCut.** Project lists `disabledTracks` (hidden from preview and export), `lockedTracks`, `untargetedTracks`
  (`app.js:527-529`); solo = `soloId` plus a saved `disabledTracks` (`:573-574`, `toggleTrackSolo` `:687`);
  `toggleTrackEnabled` `:700`, `toggleTrackLocked` `:710`; ops refuse locked clips (`edit-ops.js:164-169`).
- **ai-video-editor.** Per-lane booleans `trackVisibility` and `trackLocks` for image, overlay, caption, sticker,
  source, audio, music (`src/lib/projectTrackState.js:1-31`); export reads visibility
  (`src/lib/editorComposition.js:21-25`, `:96`).
- **Kimu.** `TrackState.muted` toggled by `handleToggleTrackMute` (`useTimeline.ts:1553-1558`); `getTimelineData`
  skips `hidden` tracks (`:151`) but does not read `muted`. No lock.

## 2. What the Hub has to build on, per feature
Common base: the file is `{"version": 2, "revision", "tracks": [[…], […]]}` with exactly those keys
(`hub/core/seqshape.py:20`, `:60`) and two bare lists (`:63`); an item is exactly `{clip|sound, in, out}` plus `at` on
track 2 (`keys_of`, `:35-36`; `_item_ok` `:43`); a save refuses any other key (`hub/core/sequences.py:125-126`, `ONLY`
`:33`). So every field named "absent" below is refused by today's shape. Save: one PUT `{name, revision, tracks}`,
compare-and-swap (`sequences.py:149-163`; `hub/modules/sequence/routes.py:104`); the browser queues edits in one
chain, each drawn from the last answer (`web/src/modules/sequence/load.ts:105-125`); an older revision never covers
a newer one (`load.ts:57-62`). Keys: one `keydown` handler, ignoring any event with Ctrl, Meta or Alt
(`Sequence.tsx:91-115`, `:93`). Item units: clip frames, sound ms (`seq.ts:6-14`); items of track 1 may differ in
rate (encode path sets each to the canvas rate, `hub/worker/joincmd.py:105-107`).

- **Roll.** Track 1 is back to back (`seq.ts:19-25`), so a roll is item *i* `out` +d and item *i+1* `in` +d — both
  fields exist; one PUT can carry both (`edit`, `load.ts:107`). `trimIn`/`trimOut` clamp one item each
  (`seq.ts:115-124`). Edge drag is per item (`Track.tsx:87-109`). Absent: nothing in the shape; d must be
  converted to each item's own unit.
- **Slip.** `in` and `out` both shifted within `0..frames` (`sequences.py:133-137`). Absent: nothing in the shape.
- **Slide.** On track 1 the same as ai-video-editor's gapless form: previous `out` +d, next `in` +d; the item's own
  fields stay (`seq.ts:19-25`). On track 2 a move already sets `at`, overlap is pushed after the hit item
  (`seq.ts:162-175`). Absent: nothing in the shape.
- **Transitions.** Absent: any transition field on an item, a joint or a track. Join: the copy path is the concat
  demuxer (`joincmd.py:185-188`); the encode path joins with `concat=n=…` (`joincmd.py:116`), hard cuts; no `xfade`,
  `acrossfade` or `afade` in the file. Preview shows one of two `<video>` players at a time, swapped at `out`
  (`Player.tsx:14-16`, `show` `:52-60`). Transitions would be one more filter per gap;
  BACKLOG item 15 (`docs/BACKLOG.md:53`).
- **Audio levels.** Absent: per-item volume, fade or keyframe; per-track gain. Join mixes track 2 at equal levels,
  `amix … normalize=0` or `volume=<n>` (`joincmd.py:139-149`); track 1's sound is `atrim` + `aresample` only
  (`_sound`, `:90-93`). Preview: track 2 and track-1 sounds through hidden `<audio>` with no `volume` set
  (`Sounds.tsx:71-75`); track-1 clip sound from the `<video>` players. No waveform (`Track.tsx:124-126`).
- **Markers.** Absent: a markers key at file level (`seqshape.py:20`). Snapping only to the item's own unit
  (`seq.ts:109-111`). The playhead store is `transport` (`Sequence.tsx:12`).
- **Undo/redo.** Absent: any history, client or server. Each edit already sends whole tracks (`api.ts:19-20`), so a
  restored snapshot is an ordinary PUT drawn from the current revision; the server bumps `revision` and tells every
  window (`routes.py:28-29`, `:110`). Ctrl/Cmd+Z never reaches the handler today (`Sequence.tsx:93`). A refused
  PUT reloads (`load.ts:119`).
- **Ripple delete.** Track 1: Delete removes and the rest close up (`Sequence.tsx:62`, `swap` `:21-24`). Track 2:
  Delete leaves a gap. Track-2 `at` is absolute ms (`seq.ts:4`), so no track-1 edit moves track 2. Absent: nothing
  in the shape; there is no op shifting track 2.
- **Linked A/V, J/L cuts.** A track-1 clip's sound is its own `[k:a]` in the join (`joincmd.py:111-112`) and plays
  from its `<video>`; a clip on track 2 gives its sound only (`join.py:10-11`). Absent: a link/unlink flag, separate
  sound in/out for a clip, any sound offset.
- **Track mute/solo/lock.** Absent: a per-track object; tracks are bare lists (`seqshape.py:63`, `value_of`
  `:70-71`). Join skips nothing but soundless track-2 clips and items past the end (`join.py:43-49`).

## 3. Not known
- Whether the server's ffmpeg build has `xfade` and `acrossfade`; the worker probes only
  `amix normalize` today (`joincmd.py:176-177`).
- Whether FableCut's, ai-video-editor's and Kimu's ops run as read (none run here).
- Whether Kimu's track mute or volume keyframes are applied somewhere not found by name search.
- How a roll or slide between two track-1 clips of different rates rounds in the Hub (no code exists).
- How Edit Video behaves on the server (R34 §6).

## Sources
- R34 (`docs/video-plan/research/R34-editor-against-a-pro-timeline.md`), §2-§5.
- https://github.com/ronak-create/FableCut `a963fa5`; https://github.com/MartinDelophy/ai-video-editor `669b1f7`;
  https://github.com/trykimu/videoeditor `6a30d43`.
- Hub: the files cited above.
