// Dynamic scaling: at every viewport, nothing overlaps, nothing is cut off, Generate stays on screen.
import { expect, test, type Page } from '@playwright/test'
import { job, makeLoras } from './fixtures/data'
import { FakeHub } from './fixtures/controller'
import { apiState, chatWithTools } from './fixtures/api'
import { open, openSettings, rootScroll, settle, unnamedScrollers, ZERO } from './helpers'
import { MEDIA_SCALE, expectedRoot, fitProblems, fullyVisible, rootPx } from './fit'

const VIEWPORTS = [[2000, 1130], [1920, 1080], [2560, 1440], [1366, 768]] as const
const LORAS = makeLoras(60, true)
/** The heaviest footer: a running job, waiting ones and a reason line (the queue is full; a prompt has no
 *  length limit of the Hub's). */
const FULL = {
  model: 'flux2_klein_9b', prompt: 'A grey cat asleep under an apple tree, inkstyle, bold outlines. '.repeat(70),
  lorasByModel: { flux2_klein_9b: LORAS.slice(0, 6).map(l => ({ id: l.id, strength: 0.8 })) },
  aspect: '16:9', size: 1.5, images: 4, advancedByModel: {}, references: [],
  selected: LORAS[0]!.id, draft: 'A grey cat curled under an apple tree, rain on the leaves, late light. '.repeat(40),
}
const TOP = '[data-region="topbar"]'
type Screen = { name: string; path: string; ready: string; cols: string[]; prepare?: (p: Page) => Promise<void> }
const settings = (card?: string) => async (p: Page) => {
  await openSettings(p)
  if (card) await p.locator(`[data-card="${card}"]`).click()
}
const SET = [TOP, '[data-region="settings"]']
const SCREENS: Screen[] = [
  { name: 'generate', path: '/', ready: '[data-lora]', cols: [TOP, '[data-region="compose"]', '[data-region="draft"]', '[data-region="dock"]', '[data-region="side"]', '[data-region="chat"]', '[data-region="bar"]'] },
  { name: 'settings', path: '/', ready: 'text=Version', prepare: settings(), cols: SET },
  { name: 'network', path: '/', ready: 'text=Pair a device', prepare: settings('network'), cols: SET },
  { name: 'assistant', path: '/', ready: 'text=Clients', prepare: settings('assistant'), cols: SET },
  { name: 'media', path: '/media', ready: '[data-stage-img]', cols: [TOP, '[data-region="stage"]', '[data-region="actions"]', '[data-scroll="media-grid"]'] },
]

for (const [w, h] of VIEWPORTS) {
  test.describe(`${w}×${h}`, () => {
    test.use({ viewport: { width: w, height: h } })
    for (const sc of SCREENS) {
      test(`${sc.name} fits`, async ({ page }) => {
        const running = job('j_RUN', { state: 'running', progress: { phase: 'inference', index: 1, count: 4, step: 2, steps: 6, pct: 30, eta_s: 9, text: '' } })
        const hub = new FakeHub({ jobs: [running, ...Array.from({ length: 10 }, (_, i) => job(`j_W${i + 1}`))] })
        await open(page, sc.path, hub, apiState({ draft: FULL, loras: LORAS, chat: { ...chatWithTools(20), busy: true } }))
        await sc.prepare?.(page)
        await page.locator(sc.ready).first().waitFor()
        await page.waitForTimeout(150)
        await settle(page)
        const tag = `${w}×${h}`
        expect(await rootPx(page), `${tag} root`).toBeCloseTo(expectedRoot(w, h, sc.name === 'media' ? MEDIA_SCALE : 1), 1)
        expect.soft(await fitProblems(page, sc.cols), `${tag} fit`).toEqual([])
        expect(await rootScroll(page), `${tag} lock`).toEqual(ZERO)
        expect.soft(await unnamedScrollers(page), `${tag} scrollers`).toEqual([])
        if (sc.name === 'generate') {
          expect.soft(await fullyVisible(page, '[data-region="generate"]'), `${tag} Generate on screen`).toBe(true)
          expect.soft(await fullyVisible(page, '[data-region="queue"]'), `${tag} queue on screen`).toBe(true)
        }
      })
    }
  })
}
