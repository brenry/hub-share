// Pure: what the queue area shows for this tool.
import { about, plural } from '../../../lib/format'
import type { Job } from '../../../lib/protocol'
import { TOOL } from '../types'

type QueueView = {
  running: Job | null
  waiting: Job[]
  failed: Job | null
}

export function queueView(all: Iterable<Job>): QueueView {
  const mine = [...all].filter(j => j.tool === TOOL).sort((a, b) => a.created - b.created)
  const waiting = mine.filter(j => j.state === 'queued')
  const terminal = mine.filter(j => j.state === 'failed' || j.state === 'done' || j.state === 'cancelled')
  const last = terminal[terminal.length - 1] ?? null
  return {
    running: mine.find(j => j.state === 'running') ?? null,
    waiting,
    failed: last?.state === 'failed' ? last : null,
  }
}

/** A scene's step, every one the first included: "Shot 2 · Speaker 1 · 7.3 s" as "Shot 2 of 5 · Speaker 1 · 7.3 s". */
const sceneStep = (name: string, shots: number): string => name.replace(/^Shot (\d+)/, `Shot $1 of ${shots}`)

/** A step of a re-take ("Render · take 2"): shown before the engine's own status, so the take is seen. */
const takeStep = (name: string | undefined): string => (name?.includes(' · take ') ? name : '')

const isLoading = (j: Job): boolean => j.progress !== null && /load/i.test(j.progress.phase)

/** "Generating k of N" and "p% · about t" for a running job. */
export function runningText(j: Job): { left: string; right: string; value: number | null } {
  const p = j.progress
  if (!p) return { left: 'Starting', right: '', value: null }
  if (isLoading(j)) return { left: p.text || 'Loading model', right: '', value: null }
  if (p.phase === 'checking') return { left: p.text || 'Checking the take…', right: '', value: null }   // the judges
  if (p.phase === 'planning') return { left: p.text || 'Planning', right: '', value: null }   // the Director
  const eta = p.eta_s === null ? 'estimating…' : about(p.eta_s)
  const steps = j.summary?.step_names                          // a job of named steps: the render, then its re-takes
  const left = j.summary?.mode === 'scene' ? sceneStep(steps?.[p.index - 1] ?? '', j.summary.shots ?? 0)   // a scene: one step per shot
    : steps ? (p.index > 1 ? takeStep(steps[p.index - 1]) || p.text || steps[p.index - 1] || '' : 'Generating')
    : `Generating ${p.index} of ${p.count}`
  return { left, right: `${Math.round(p.pct)}% · ${eta}`, value: p.pct / 100 }
}

const took = (seconds: number): string => (seconds < 60 ? `${Math.max(1, Math.round(seconds))} s` : `${Math.round(seconds / 60)} min`)

export const doneText = (images: number, seconds: number): string => `Done · ${plural(images, 'image')} in ${took(seconds)}`

/** The short line for a job that just finished `seconds` after it started: a clip or a line says so. */
export const doneLine = (j: Job, seconds: number): string =>
  (j.summary?.kind === 'clip' ? `Done · clip in ${took(seconds)}` : j.summary?.kind === 'sound' ? `Done · line in ${took(seconds)}`
    : doneText(j.outputs.length || j.progress?.count || 1, seconds))

const tenth = (n: number): string => String(Math.round(n * 10) / 10)

/** The newest finished line's verdict from the words judge (the job's `notes.verdict`), or null. */
export function verdictOf(jobs: Iterable<Job>, tool: string): string | null {
  let best: Job | null = null
  for (const j of jobs) {
    if (j.tool !== tool || j.state !== 'done' || typeof j.notes?.verdict !== 'string') continue
    if (!best || j.created > best.created) best = j
  }
  return best ? String(best.notes!.verdict) : null
}

/** The windows the engine planned for a clip job (the job's `notes.plan.windows`): "3 windows: 5.2 s,
 *  5.2 s, 4.5 s"; null when the job has no plan. */
export function planLine(j: Job): string | null {
  const plan = j.notes?.plan as { windows?: { seconds?: number }[] } | undefined
  const windows = Array.isArray(plan?.windows) ? plan!.windows!.filter(w => typeof w?.seconds === 'number') : []
  if (!windows.length) return null
  return `${windows.length} ${windows.length === 1 ? 'window' : 'windows'}: ${windows.map(w => `${tenth(w.seconds!)} s`).join(', ')}`
}

/** A continue job's label, "Continue · +5.1 s · scene 10.2 s"; null for any other job. */
export function continueLabel(j: Job): string | null {
  const m = j.summary
  if (m?.mode !== 'continue') return null
  const scene = m.scene_seconds === undefined ? '' : ` · scene ${tenth(m.scene_seconds)} s`
  return `Continue · +${tenth(m.seconds ?? 0)} s${scene}`
}

export const generateLabel = (n: number, clip = false, line = false): string =>
  (line ? 'Generate line' : clip ? 'Generate clip' : n === 1 ? 'Generate image' : `Generate ${n} images`)
