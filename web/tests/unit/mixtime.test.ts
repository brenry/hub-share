// A mixed script (every shot and event with `measured`, panels included) is drawn in the track's time;
// any other script as it is; the input's planned times are never changed.
import { describe, expect, it } from 'vitest'
import example from '../../../tests/fixtures/script-1.json'
import type { Script } from '../../src/modules/director/api'
import { inMix, mixed } from '../../src/modules/director/mixtime'
import { boxes, lengthMs, panelsOf } from '../../src/modules/director/timeline'

type Raw = { kind: string; id: string; start_ms?: number; end_ms?: number; at_ms?: number; measured?: unknown }

/** The example with a panel in its first shot, every time measured 500 ms later; p8 an instant. */
function mixedExample(): Script {
  const s = structuredClone(example) as unknown as Script
  const first = s.scenes[0]!.shots[0]!.events as unknown as Raw[]
  first.push({ id: 'k1', kind: 'panel', at_ms: 1000, picture: null, stale: false } as Raw)
  for (const shot of s.scenes.flatMap(sc => sc.shots)) {
    shot.measured = { start_ms: shot.start_ms + 500, end_ms: shot.end_ms + 500 }
    for (const ev of shot.events as unknown as Raw[]) {
      ev.measured = ev.kind === 'panel' ? { at_ms: ev.at_ms! + 500 }
        : ev.id === 'p8' ? { start_ms: 17900, end_ms: 17900 } : { start_ms: ev.start_ms! + 500, end_ms: ev.end_ms! + 500 }
    }
  }
  return s
}

describe('mixtime', () => {
  it('a script measured everywhere comes back in its measured times, panels included', () => {
    const got = inMix(mixedExample())
    const at = Object.fromEntries(boxes(got).map(b => [b.id, [b.start, b.end]]))
    expect(at['shot:1.1']).toEqual([500, 9500])
    expect(at['shot:1.3']).toEqual([17500, 24500])
    expect(at.l1).toEqual([4500, 8142])
    expect(at.c4).toEqual([22500, 24000])
    expect(panelsOf(got).map(p => [p.id, p.at])).toEqual([['k1', 1500]])
    expect(lengthMs(got)).toBe(24500)
  })

  it('a pose measured with its start at its end comes back so', () => {
    const p8 = boxes(inMix(mixedExample())).find(b => b.id === 'p8')!
    expect([p8.start, p8.end]).toEqual([17900, 17900])
  })

  it('one event without measured: the script unchanged', () => {
    const s = mixedExample()
    delete (s.scenes[0]!.shots[1]!.events[0] as Raw).measured
    expect(mixed(s)).toBe(false)
    expect(inMix(s)).toBe(s)
    const panelLess = mixedExample()
    delete ((panelLess.scenes[0]!.shots[0]!.events as unknown as Raw[]).find(e => e.kind === 'panel')!).measured
    expect(inMix(panelLess)).toBe(panelLess)
    const shotLess = mixedExample()
    delete shotLess.scenes[0]!.shots[2]!.measured
    expect(inMix(shotLess)).toBe(shotLess)
  })

  it('a version-1 script unchanged', () => {
    const s = { ...mixedExample(), version: 1 as const }
    expect(mixed(s)).toBe(false)
    expect(inMix(s)).toBe(s)
  })

  it('the planned times are not changed in the input', () => {
    const s = mixedExample()
    const before = JSON.stringify(s)
    inMix(s)
    expect(JSON.stringify(s)).toBe(before)
    expect(s.scenes[0]!.shots[0]!.start_ms).toBe(0)
    expect(s.scenes[0]!.shots[0]!.events.find(e => e.id === 'l1')!.start_ms).toBe(4000)
  })
})
