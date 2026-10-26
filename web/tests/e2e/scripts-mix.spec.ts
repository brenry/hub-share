// The Storyboard tab, a mixed script (every shot and event with `measured`) is drawn in the track's time,
// its length the track's; `/script`'s `track` shows its words and a player on the bar; cue boxes show their takes.
import { readFileSync } from 'node:fs'
import { expect, test, type Page, type Route } from '@playwright/test'
import type { ToolInfo } from '../../src/lib/protocol'
import { FakeHub } from './fixtures/controller'
import { SEQUENCE_TOOL, mockSequence, seqState } from './fixtures/sequence'
import { open } from './helpers'

const example: unknown = JSON.parse(readFileSync(new URL('../../../tests/fixtures/script-1.json', import.meta.url), 'utf8'))
const DIRECTOR_TOOL: ToolInfo = { id: 'director', title: 'Storyboard', tab: { label: 'Storyboard', order: 30 }, sockets: [] }
const LOCK = { locked: true, at: '2026-10-20T09:15:02+02:00' }
const URL_ = '/files/sounds/Script 1.wav?t=1760951702'
const NOTE = 'room tone left out: no room take'
const REDO = 'c2: its take Script 1/c2-1.wav has no measured sound: redo it (delete it from Sounds, then call script_track)'

const json = (route: Route, body: unknown) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) })

type Raw = { id: string; kind: string; start_ms?: number; end_ms?: number; at_ms?: number; measured?: unknown }
type Shot = { start_ms: number; end_ms: number; measured?: unknown; events: Raw[] }
/** A long first take: every time from 4 s on is 1.5 s later in the track; l3 starts before its shot's measured start
 *  (a line across a cut); p8 lies in a flat stretch (start equal to end). A panel k1 at 5 s in the first shot. */
const pushed = (t: number) => (t < 4000 ? t : t + 1500)
function mixed(): unknown {
  const s = structuredClone(example) as { scenes: { shots: Shot[] }[] }
  s.scenes[0]!.shots[0]!.events.push({ id: 'k1', kind: 'panel', at_ms: 5000, picture: null, stale: false } as Raw)
  for (const shot of s.scenes.flatMap(sc => sc.shots)) {
    shot.measured = { start_ms: pushed(shot.start_ms), end_ms: pushed(shot.end_ms) }
    for (const ev of shot.events) {
      ev.measured = ev.kind === 'panel' ? { at_ms: pushed(ev.at_ms!) }
        : ev.id === 'l3' ? { start_ms: 18000, end_ms: 22500 }
          : ev.id === 'p8' ? { start_ms: 18500, end_ms: 18500 }
            : { start_ms: pushed(ev.start_ms!), end_ms: pushed(ev.end_ms!) }
    }
  }
  return s
}

type State = { script: unknown; track: unknown; takes: Record<string, unknown> }
const take = (id: string, state: string) => ({ state, file: `Script 1/${id}-1.wav`, url: `/files/sounds/Script 1/${id}-1.wav`, why: state === 'flagged' ? 'too quiet' : null })
const audioOf = (takes: Record<string, unknown>) => ['c1', 'c2', 'l1', 'l2', 'c3', 'l3', 'c4'].map(id => ({
  id, kind: id[0] === 'c' ? 'cue' : 'line', shot: '1.1', start_ms: 0, end_ms: 1000, who: 'x', text: 'x: words', problem: null,
  sample: null, seconds: 8, hash: '3f9c0a1b77e2d415', take: takes[id] ?? { state: 'none', file: `Script 1/${id}-1.wav` },
}))

async function scripts(page: Page, st: State): Promise<FakeHub> {
  await page.setViewportSize({ width: 1600, height: 900 })
  await page.route(/\/api\/director\//, route => {
    const p = new URL(route.request().url()).pathname.replace('/api/director', '')
    if (p === '/scripts') return json(route, { scripts: [{ name: 'Script 1', seconds: 24, scenes: 1, shots: 3, lines: 3, changed: 1, problem: null }] })
    if (p === '/script') {
      return json(route, { name: 'Script 1', seconds: 24, problem: null, script: { ...(st.script as object), lock: LOCK }, pictures: {},
        unpictured: [], audio: audioOf(st.takes), track: st.track })
    }
    return json(route, {})
  })
  await mockSequence(page, seqState())
  const base = new FakeHub()
  const hub = new FakeHub({ tools: [...base.tools, SEQUENCE_TOOL, DIRECTOR_TOOL] })
  await open(page, '/', hub)
  await page.getByRole('tab', { name: 'Storyboard' }).click()
  await expect(page.locator('[data-region="timeline"]')).toBeVisible()
  return hub
}
let rev = 1
const changed = (hub: FakeHub) => hub.broadcast('director.changed', { name: 'Script 1', revision: ++rev }, 'workspace')

const state = (over: Partial<State> = {}): State => ({ script: mixed(), track: null, takes: {}, ...over })
const box = (page: Page, id: string) => page.locator(`[data-region="timeline"] [data-box="${id}"]`)
const trackLine = (page: Page) => page.locator('[data-region="track"]')

/** A box's left and right on the timeline in ms, from the ruler's left and the scale. */
async function place(page: Page, id: string): Promise<[number, number]> {
  const ruler = (await page.locator('[data-region="ruler"]').boundingBox())!
  const pps = Number(await page.locator('[data-region="timeline"]').getAttribute('data-pps'))
  const b = (await box(page, id).boundingBox())!
  return [((b.x - ruler.x) / pps) * 1000, ((b.x + b.width - ruler.x) / pps) * 1000]
}
const near = (got: [number, number], want: [number, number]) => {
  expect(Math.abs(got[0] - want[0])).toBeLessThan(60)
  expect(Math.abs(got[1] - want[1])).toBeLessThan(60)
}

test('a mixed script draws its boxes at their measured places and the bar has the track length', async ({ page }) => {
  await scripts(page, state())
  near(await place(page, 'l1'), [5500, 9142])
  near(await place(page, 'c2'), [2500, 3900])
  near(await place(page, 'p3'), [5500, 9142])
  near(await place(page, 'shot:1.2'), [10500, 18500])
  const k1 = await place(page, 'k1')
  expect(Math.abs(k1[0] - 6500)).toBeLessThan(60)
  await expect(page.locator('[data-region="script-length"]')).toHaveText('25.5 s')
})

test('the same script without one measured draws the plan', async ({ page }) => {
  const s = mixed() as { scenes: { shots: Shot[] }[] }
  delete s.scenes[0]!.shots[1]!.events[0]!.measured
  await scripts(page, state({ script: s }))
  near(await place(page, 'l1'), [4000, 7642])
  near(await place(page, 'shot:1.2'), [9000, 17000])
  await expect(page.locator('[data-region="script-length"]')).toHaveText('24.0 s')
})

test('a line measured outside its shot is drawn at its own time; a pose of no hold shows its figure there', async ({ page }) => {
  await scripts(page, state())
  near(await place(page, 'l3'), [18000, 22500])
  near(await place(page, 'shot:1.3'), [18500, 25500])
  const p8 = await place(page, 'p8')
  expect(Math.abs(p8[0] - 18500)).toBeLessThan(60)
  const figure = box(page, 'p8').locator('svg')
  await expect(figure).toBeVisible()
  const ruler = (await page.locator('[data-region="ruler"]').boundingBox())!
  const pps = Number(await page.locator('[data-region="timeline"]').getAttribute('data-pps'))
  expect(Math.abs(((await figure.boundingBox())!.x - ruler.x) / pps * 1000 - 18500)).toBeLessThan(60)
})

test('a current track shows its length and a player of its url', async ({ page }) => {
  await scripts(page, state({ track: { state: 'current', file: 'Script 1.wav', url: URL_, length_ms: 25500 } }))
  await expect(trackLine(page)).toHaveText('Track · 25.5 s')
  await expect(trackLine(page)).toHaveAttribute('data-state', 'current')
  await expect(page.locator('[data-region="track-play"]')).toHaveAttribute('src', URL_)
  const btn = (await page.locator('[data-region="script-track"]').boundingBox())!
  expect((await trackLine(page).boundingBox())!.x).toBeGreaterThan(btn.x)
})

test('mixing, stale and failed show their words; a note follows them', async ({ page }) => {
  const st = state({ track: { state: 'mixing' } })
  const hub = await scripts(page, st)
  await expect(trackLine(page)).toHaveText('Track · mixing')
  await expect(page.locator('[data-region="track-play"]')).toHaveCount(0)
  st.track = { state: 'stale', file: 'Script 1.wav', url: URL_, length_ms: 25500, note: NOTE }
  changed(hub)
  await expect(trackLine(page)).toHaveText(`Track · stale · 25.5 s · ${NOTE}`)
  await expect(page.locator('[data-region="track-play"]')).toHaveAttribute('src', URL_)
  st.track = { state: 'failed', why: 'the mix job failed' }
  changed(hub)
  await expect(trackLine(page)).toHaveText('Track · failed · the mix job failed')
})

test("failed with a take's redo line shows it whole", async ({ page }) => {
  await scripts(page, state({ track: { state: 'failed', why: REDO } }))
  await expect(trackLine(page)).toHaveAttribute('title', `Track · failed · ${REDO}`)
  await expect(trackLine(page)).toHaveText(`Track · failed · ${REDO}`)
})

test('none and null show no track line', async ({ page }) => {
  const st = state({ track: { state: 'none' } })
  const hub = await scripts(page, st)
  await expect(page.locator('[data-region="script-track"]')).toBeVisible()
  await expect(trackLine(page)).toHaveCount(0)
  st.track = { state: 'mixing' }
  changed(hub)
  await expect(trackLine(page)).toHaveText('Track · mixing')
  st.track = null
  changed(hub)
  await expect(trackLine(page)).toHaveCount(0)
})

test('cue boxes carry their take state as line boxes do', async ({ page }) => {
  await scripts(page, state({ takes: { c1: take('c1', 'ok'), c2: take('c2', 'flagged'), c3: { state: 'rendering', file: 'Script 1/c3-1.wav' } } }))
  await expect(box(page, 'c1')).toHaveAttribute('data-take', 'ok')
  await expect(box(page, 'c2')).toHaveAttribute('data-take', 'flagged')
  await expect(box(page, 'c3')).toHaveAttribute('data-take', 'rendering')
  await expect(box(page, 'c4')).toHaveAttribute('data-take', 'none')
})
