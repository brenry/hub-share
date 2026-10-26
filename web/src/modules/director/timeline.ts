// The timeline's rows and boxes, pure. Rows top to bottom: the ruler, the shots, one row of lines per
// character, the cues, one row of poses per character. Characters in order of first appearance in the scenes' casts;
// where they stand is the stage's (`tween.ts`, the context's homes). Times are milliseconds from the script's start.
import type { Job } from '../../lib/protocol'
import type { Ev, Panel, Script, Shot, Take } from './api'

/** The fewest rem a second gets (40 px at a 20 px root); a script longer than the window then scrolls
 *  sideways. */
export const MIN_REM_PER_S = 2

export type Row =
  | { key: 'ruler'; kind: 'ruler'; head: '' }
  | { key: 'shots'; kind: 'shots'; head: 'Shots' }
  | { key: 'panels'; kind: 'panels'; head: 'Sketches' }
  | { key: string; kind: 'lines'; head: string; who: string }
  | { key: 'cues'; kind: 'cues'; head: 'Cues' }
  | { key: string; kind: 'poses'; head: string; who: string }

const fold = (name: string) => name.toLocaleLowerCase()

/** Every character once, as first written, in order of first appearance in the casts. */
export function characters(script: Script): string[] {
  const seen = new Map<string, string>()
  for (const scene of script.scenes) for (const name of scene.cast) if (!seen.has(fold(name))) seen.set(fold(name), name)
  return [...seen.values()]
}

export function rows(script: Script): Row[] {
  const who = characters(script)
  return [
    { key: 'ruler', kind: 'ruler', head: '' },
    { key: 'shots', kind: 'shots', head: 'Shots' },
    ...who.map((w): Row => ({ key: `line:${fold(w)}`, kind: 'lines', head: w, who: w })),
    { key: 'cues', kind: 'cues', head: 'Cues' },
    ...who.map((w): Row => ({ key: `pose:${fold(w)}`, kind: 'poses', head: `${w} pose`, who: w })),
  ]
}

/** The Sketches row, drawn right under Shots only when the script has a panel. */
export const SKETCHES: Row = { key: 'panels', kind: 'panels', head: 'Sketches' }

/** A sketch panel on the Sketches row: its time, picture, stale mark and its shot's `<scene>.<shot>` label. */
export type Sketch = { id: string; at: number; picture: string | null; stale: boolean; shot: string }

/** The script's panels, in script order (shot by shot, by time), read before `drawable`. */
export function panelsOf(script: Script): Sketch[] {
  return script.scenes.flatMap((scene, i) => scene.shots.flatMap((shot, k) => (shot.events as unknown as Panel[])
    .filter(ev => ev.kind === 'panel')
    .sort((a, b) => a.at_ms - b.at_ms || a.id.localeCompare(b.id))
    .map(p => ({ id: p.id, at: p.at_ms, picture: p.picture ?? null, stale: Boolean(p.stale), shot: `${i + 1}.${k + 1}` }))))
}

/** A panel's state in words: `drawn`, `stale` or `not drawn`. */
export const sketchState = (p: Sketch): string => (p.picture === null ? 'not drawn' : p.stale ? 'stale' : 'drawn')

/** A panel as a box: selected like any box, the playhead at its time. */
export const sketchBox = (p: Sketch): Box => ({ id: p.id, row: 'panels', start: p.at, end: p.at, text: '', ev: null, shot: p.shot, panel: p })

/** The script with only line, cue and pose events: a sketch panel is drawn on its own row. */
export function drawable(script: Script): Script {
  const kinds = new Set<string>(['line', 'cue', 'pose'])
  return { ...script, scenes: script.scenes.map(scene => ({ ...scene, shots: scene.shots.map(shot => ({ ...shot, events: shot.events.filter(ev => kinds.has((ev as { kind: string }).kind)) })) })) }
}

/** The row an event is drawn on. */
export const rowOf = (ev: Ev): string =>
  ev.kind === 'line' ? `line:${fold(ev.speaker)}` : ev.kind === 'pose' ? `pose:${fold(ev.character)}` : 'cues'

/** The script's length: the latest end of any shot, 0 with none, as the server's `scriptshape.length_ms`. */
export const lengthMs = (script: Script): number =>
  Math.max(0, ...script.scenes.flatMap(scene => scene.shots.map(shot => shot.end_ms)))

/** Pixels per second: the whole script fits `width` when that gives at least MIN_REM_PER_S at the root's `rem` pixels,
 *  else that least. */
export function scale(ms: number, width: number, rem: number): number {
  const least = MIN_REM_PER_S * rem
  if (ms <= 0 || width <= 0) return least
  return Math.max(least, width / (ms / 1000))
}

export const x = (ms: number, pxPerS: number): number => (ms / 1000) * pxPerS

/** A shot's camera in words: the text, or framing, `, <move>`, ` · on <names>` (`on nobody`); '' none. */
export function cameraText(shot: Shot): string {
  const c = shot.camera
  if (c === undefined || typeof c === 'string') return c ?? ''
  const on = c.on === undefined ? '' : ` · on ${c.on.length ? c.on.join(', ') : 'nobody'}`
  return `${c.framing ?? ''}${c.move ? `, ${c.move}` : ''}${on}`
}

export type Box = { id: string; row: string; start: number; end: number; text: string; ev: Ev | null; shot: string; panel?: Sketch }

/** A shot box's words: `<scene>.<shot>`, its camera words, then ` · <its action>`. */
export function shotText(label: string, shot: Shot): string {
  const head = cameraText(shot) ? `${label} ${cameraText(shot)}` : label
  return shot.action ? `${head} · ${shot.action}` : head
}

/** Every shot and event as a box on its row; a shot's id is `<scene>.<shot>`, its text `shotText`. */
export function boxes(script: Script): Box[] {
  const out: Box[] = []
  script.scenes.forEach((scene, i) => scene.shots.forEach((shot, k) => {
    const label = `${i + 1}.${k + 1}`
    out.push({ id: `shot:${label}`, row: 'shots', start: shot.start_ms, end: shot.end_ms, text: shotText(label, shot), ev: null, shot: label })
    for (const ev of shot.events) {
      const text = ev.kind === 'pose' ? ev.pose : ev.words
      out.push({ id: ev.id, row: rowOf(ev), start: ev.start_ms, end: ev.end_ms, text, ev, shot: label })
    }
  }))
  return out
}

/** Seconds with one decimal: 7642 -> "7.6". */
export const secs = (ms: number): string => (ms / 1000).toFixed(1)

/** A box's fields in one line, for the bar. */
export function describe(b: Box, script: Script): string {
  const span = `${secs(b.start)}–${secs(b.end)} s`
  const ev = b.ev
  if (b.panel) return [`Sketch ${b.id}`, `shot ${b.shot}`, `${secs(b.start)} s`, sketchState(b.panel)].join(' · ')
  if (!ev) {
    const [i, k] = b.shot.split('.').map(Number)
    const shot = script.scenes[i! - 1]?.shots[k! - 1]
    const camera = shot ? cameraText(shot) : ''
    return ['Shot ' + b.shot, camera, shot?.action, span].filter(Boolean).join(' · ')
  }
  if (ev.kind === 'line') {
    const pace = ev.pace === undefined ? undefined : `${ev.pace} words/s`
    return [ev.speaker, `“${ev.words}”`, ev.language, ev.emotion, pace, span].filter(Boolean).join(' · ')
  }
  if (ev.kind === 'cue') return [`Cue ${ev.cue}`, ev.words, span].join(' · ')
  return [ev.character, ev.pose, span].join(' · ')
}

const num = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v)
/** One decimal with its sign, the minus as U+2212: 0.4 -> "+0.4", -23.4 -> "−23.4". */
const signed = (v: number, plus: boolean): string => `${v < 0 ? '−' : plus ? '+' : ''}${Math.abs(v).toFixed(1)}`

/** A line's or cue's take's measured length: its speech's end less its start, in ms; null when not measured. */
export function measuredMs(take: Take): number | null {
  const m = take.measured
  return m && num(m.speech_start_ms) && num(m.speech_end_ms) ? m.speech_end_ms - m.speech_start_ms : null
}

/** A take's line for the bar: its state, file's name, measured of planned length, heard, loudness and
 *  gain, each only when known; a flagged or failed take's why after. `none`, `stale · <file>` and `rendering` alone.
 *  A failed take names a file only when one landed (`failed · <why>`). */
export function takeLine(take: Take, plannedMs: number): string {
  if (take.state === 'none' || take.state === 'rendering') return take.state
  if (take.state === 'stale') return `stale · ${take.file}`
  const ms = measuredMs(take)
  const heard = take.judge?.heard
  const lufs = take.measured?.lufs
  const gain = take.measured?.gain_db
  const parts = [
    take.state, take.file ? take.file.split('/').pop() ?? take.file : null,
    ms === null ? null : `${secs(ms)} s of ${secs(plannedMs)} s`,
    num(heard) ? `heard ${Math.round(heard * 100)} %` : null,
    num(lufs) ? `${signed(lufs, false)} LUFS` : null,
    num(gain) ? `gain ${signed(gain, true)} dB` : null,
  ]
  const why = take.state === 'flagged' || take.state === 'failed' ? take.why ?? take.judge?.why : null
  return [...parts, why || null].filter(Boolean).join(' · ')
}

/** The take player's gain: the take's measured `gain_db` as a factor, 1 (0 dB, as the mix places a clip
 *  whose gain is null) when it is not a finite number. */
export function gainOf(take: Take): number {
  const g = take.measured?.gain_db
  return num(g) ? 10 ** (g / 20) : 1
}

/** Track's job as the bar shows it: queued at its place, or running with its takes done of all, the
 *  bar's value (null: indeterminate), the step being spoken and its box's id (`room` has none). */
export type TrackProgress =
  | { queued: number | null }
  | { done: number; count: number; value: number | null; step: string | null; id: string | null }

/** The queue's card of Track's job -> its progress; null when there is no card or the job has ended. `done` counts
 *  the tasks before the running one (a passed-over re-take counted done). */
export function trackProgress(job: Job | null | undefined): TrackProgress | null {
  if (!job) return null
  if (job.state === 'queued') return { queued: job.position }
  if (job.state !== 'running') return null
  const names = job.summary?.step_names ?? []
  const p = job.progress
  if (!p) return { done: 0, count: names.length, value: null, step: null, id: null }
  const done = Math.max(0, p.index - 1)
  const step = names[p.index - 1] ?? null
  const id = step === null ? null : step.split(' · take ')[0]!
  const value = p.count > 0 ? (done + (num(p.pct) ? p.pct : 0) / 100) / p.count : null
  return { done, count: p.count, value, step, id: id === 'room' ? null : id }
}

/** The progress in words: `queued (<place>)`, or `<done> of <all> takes · <step>`. */
export function progressText(p: TrackProgress): string {
  if ('queued' in p) return p.queued === null ? 'queued' : `queued (${p.queued})`
  return [`${p.done} of ${p.count} takes`, p.step].filter(Boolean).join(' · ')
}

/** Render's job as the bar shows it (as Track's): queued at its place, or running with its steps done of
 *  all, the bar's value and the step's name; null when there is no card or the job has ended. */
export function cutProgress(job: Job | null | undefined): TrackProgress | null {
  if (!job) return null
  if (job.state === 'queued') return { queued: job.position }
  if (job.state !== 'running') return null
  const p = job.progress
  if (!p) return { done: 0, count: job.summary?.step_names?.length ?? 0, value: null, step: null, id: null }
  const done = Math.max(0, p.index - 1)
  const value = p.count > 0 ? (done + (num(p.pct) ? p.pct : 0) / 100) / p.count : null
  return { done, count: p.count, value, step: job.summary?.step_names?.[p.index - 1] ?? (p.text || null), id: null }
}

/** Render's progress in words: `queued (<place>)`, or `<done> of <all> · <step>`. */
export const cutText = (p: TrackProgress): string =>
  'queued' in p ? progressText(p) : [`${p.done} of ${p.count}`, p.step].filter(Boolean).join(' · ')

/** The video's named length (a scene's named seconds from its first shot), else its run: the longer of the two. */
export function namedMs(script: Script): number {
  const run = lengthMs(script)
  const last = script.scenes[script.scenes.length - 1]
  if (!last || last.seconds === undefined) return run
  return Math.max(run, (last.shots[0]?.start_ms ?? 0) + last.seconds * 1000)
}
