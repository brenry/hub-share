// The Storyboard in the track's time, pure. After a mix every version-2 shot and event carries
// `measured` (`{start_ms, end_ms}`, a panel's `{at_ms}`); the file keeps the plan. All or nothing: one
// shot or event without it and the script is drawn in its planned times, so two clocks are never drawn together.
import type { Script, Span } from './api'

type AnyEv = { kind: string; start_ms?: number; end_ms?: number; at_ms?: number; measured?: Partial<Span> & { at_ms?: number } }

const num = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v)

function measuredOk(ev: AnyEv): boolean {
  const m = ev.measured
  if (!m || typeof m !== 'object') return false
  return ev.kind === 'panel' ? num(m.at_ms) : num(m.start_ms) && num(m.end_ms)
}

/** True when the script is version 2 and every shot and every event (panels included) carries `measured`. */
export function mixed(script: Script): boolean {
  if (script.version !== 2) return false
  const shots = script.scenes.flatMap(scene => scene.shots)
  return shots.length > 0 && shots.every(shot => {
    const m = shot.measured
    return m !== undefined && num(m.start_ms) && num(m.end_ms) && (shot.events as unknown as AnyEv[]).every(measuredOk)
  })
}

/** A copy of a mixed script with each shot's and event's times its measured ones (a panel's `at_ms`); any other
 *  script as it is. Each box keeps its own measured time, never clamped into its shot; an instant stays an instant. */
export function inMix(script: Script): Script {
  if (!mixed(script)) return script
  return {
    ...script,
    scenes: script.scenes.map(scene => ({
      ...scene,
      shots: scene.shots.map(shot => ({
        ...shot, start_ms: shot.measured!.start_ms, end_ms: shot.measured!.end_ms,
        events: (shot.events as unknown as AnyEv[]).map(ev => (ev.kind === 'panel'
          ? { ...ev, at_ms: ev.measured!.at_ms }
          : { ...ev, start_ms: ev.measured!.start_ms, end_ms: ev.measured!.end_ms })) as unknown as typeof shot.events,
      })),
    })),
  }
}
