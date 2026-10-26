// The timeline's hand edits as the Hub's `/edit` ops, pure. Times are the drawn script's milliseconds; an
// op's `start_ms` counts from the start of the shot it lands in.
import type { EditOp, Script, Shot } from './api'
import { characters, type Box } from './timeline'

export type Placed = { scene: number; label: string; id: string; shot: Shot }

/** Every shot in script order with its scene's number, its `<scene>.<shot>` label and its id (the label when the
 *  file has none yet). */
export function shotList(script: Script): Placed[] {
  return script.scenes.flatMap((scene, i) => scene.shots.map((shot, k) => ({
    scene: i + 1, label: `${i + 1}.${k + 1}`, id: shot.id ?? `${i + 1}.${k + 1}`, shot,
  })))
}

/** The shot at `ms`: the one whose span holds it, else the last that starts before it, else the first; null with none. */
export function shotAt(script: Script, ms: number): Placed | null {
  const all = shotList(script)
  return all.find(p => p.shot.start_ms <= ms && ms < p.shot.end_ms)
    ?? [...all].reverse().find(p => p.shot.start_ms <= ms) ?? all[0] ?? null
}

/** A box's shot: the shot box's own, an event's the one it is in. */
export const shotOfBox = (script: Script, b: Box): Placed | null => shotList(script).find(p => p.label === b.shot) ?? null

/** The id an op names for a box: an event's id, a shot's id. */
export const idOf = (script: Script, b: Box): string | null => (b.ev ? b.ev.id : b.panel ? null : shotOfBox(script, b)?.id ?? null)

/** A box dropped with its start at `ms`: `move` to that time in the shot it lands in, naming that shot when it is not
 *  the box's own; a shot box dropped on another shot names it (its place), else carries the script time. Null for a
 *  sketch or a box that did not move. */
export function moveOf(script: Script, b: Box, ms: number): EditOp | null {
  const id = idOf(script, b)
  const own = shotOfBox(script, b)
  const start = Math.max(0, Math.round(ms))
  if (id === null || own === null || start === Math.round(b.start)) return null
  const into = b.ev ? shotAt(script, start) ?? own
    : shotList(script).find(p => p.id !== own.id && p.shot.start_ms <= start && start < p.shot.end_ms) ?? own
  if (!b.ev && into.id === own.id) return { op: 'move', id, start_ms: start }
  const at = Math.max(0, start - into.shot.start_ms)
  return into.id === own.id ? { op: 'move', id, start_ms: at } : { op: 'move', id, start_ms: at, shot: into.id }
}

/** The speakers a new line may have: the context's cast, else the characters of the scenes' casts. */
export function speakers(script: Script): string[] {
  const cast = script.context?.cast.map(m => m.name) ?? []
  return cast.length ? cast : characters(script)
}

/** Where an add at `ms` goes: its shot's id and the time from its start; null with no shot. */
export function addAt(script: Script, ms: number): { shot: string; start_ms: number; scene: number } | null {
  const p = shotAt(script, ms)
  return p ? { shot: p.id, start_ms: Math.max(0, Math.round(ms - p.shot.start_ms)), scene: p.scene } : null
}
