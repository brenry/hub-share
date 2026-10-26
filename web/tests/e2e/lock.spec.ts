// The lock: the page never scrolls; only named scrollers do.
import { expect, test, type Page } from '@playwright/test'
import { job, makeLoras } from './fixtures/data'
import { FakeHub } from './fixtures/controller'
import { apiState, chatWithTools } from './fixtures/api'
import { CLIP, SEQUENCE_TOOL, mockSequence, seqState } from './fixtures/sequence'
import { MEDIA_SCALE, expectedRoot } from './fit'
import { open, openSettings, regionRects, rootScroll, settle, unnamedScrollers, ZERO } from './helpers'

const SIZES = [[1366, 768], [1920, 1080], [2560, 1440], [3840, 2160]] as const
const LORAS = makeLoras(200, true)
const HEAVY = {
  model: 'flux2_klein_9b', prompt: 'A grey cat asleep under an apple tree, inkstyle, bold outlines. '.repeat(64).slice(0, 4000),
  lorasByModel: { flux2_klein_9b: LORAS.slice(0, 20).map(l => ({ id: l.id, strength: 0.8 })) },
  aspect: 'auto', size: 1, images: 6, advancedByModel: { flux2_klein_9b: { steps: 6, guidance: null, seed: { mode: 'fixed', value: 42 } } },
  references: [{ id: 'out/2026-10-09/r1.png', w: 1, h: 1 }, { id: 'out/2026-10-09/r2.png', w: 1, h: 1 }, { id: 'out/2026-10-09/r3.png', w: 1, h: 1 }],
  selected: LORAS[0]!.id,
  draft: 'A grey cat curled under an apple tree, rain on the leaves, late light, inkstyle. '.repeat(48).slice(0, 4000),
}

/** Lists whose fixtures always exceed any window: they must have scroll range, never just grow. */
const FULL_LISTS = ['lora-list', 'media-grid']
/** `sequence`: the hub lists the Edit Video tool and answers its routes (registered before the page opens). */
type Screen = { name: string; path: string; ready: string; prepare?: (p: Page) => Promise<void>; lists: string[]; sequence?: boolean }
/** Forty items, wider than any window: the strip scrolls sideways. */
const LONG = seqState({ seqs: { Opening: { revision: 1, changed: 1, tracks: [Array.from({ length: 40 }, (_, i) => ({ clip: CLIP(180000 - i * 100), in: i % 3, out: 124 })), []] } } })
const settings = (card?: string) => async (p: Page) => {
  await openSettings(p)
  if (card) await p.locator(`[data-card="${card}"]`).click()
}
const SCREENS: Screen[] = [
  { name: 'generate', path: '/', ready: '[data-lora]', lists: ['chat', 'prompt'] },
  // The LoRA list lives in the sheet the bar rolls up; raised, it is a named scroller like any other.
  { name: 'generate-loras', path: '/', ready: '[data-lora]', prepare: async p => { await p.locator('[data-region="library-toggle"]').click(); await p.waitForTimeout(300) }, lists: ['lora-list'] },
  { name: 'settings', path: '/', ready: 'text=Version', prepare: settings(), lists: [] },
  { name: 'network', path: '/', ready: 'text=Pair a device', prepare: settings('network'), lists: [] },
  { name: 'assistant', path: '/', ready: 'text=Clients', prepare: settings('assistant'), lists: [] },
  { name: 'media', path: '/media', ready: '[data-item]', lists: ['media-grid'] },
  { name: 'edit-video', path: '/', ready: '[data-tile]', sequence: true, lists: ['sequence-strip'],
    prepare: async p => { await p.getByRole('tab', { name: 'Edit Video' }).click() } },
  { name: 'pair', path: '/pair#c=bad', ready: '[data-pair="bad"]', lists: [] },
]

async function probes(page: Page): Promise<[number, number][]> {
  const pts = await page.evaluate(() => {
    const out: [number, number][] = []
    for (const el of document.querySelectorAll<HTMLElement>('[data-region], [data-scroll], button, [role=tab]')) {
      const r = el.getBoundingClientRect()
      if (r.width > 0 && r.height > 0) out.push([r.x + r.width / 2, r.y + r.height / 2], [r.right + 0.5, r.y + r.height / 2])
    }
    return out
  })
  const { width, height } = page.viewportSize()!
  const corners: [number, number][] = [[2, 2], [width - 2, 2], [2, height - 2], [width - 2, height - 2]]
  return [...corners, ...pts.filter(([x, y]) => x > 0 && y > 0 && x < width && y < height).filter((_, i) => i % 4 === 0).slice(0, 24)]
}

for (const [w, h] of SIZES) {
  test.describe(`${w}×${h}`, () => {
    test.use({ viewport: { width: w, height: h } })
    for (const sc of SCREENS) {
      test(`${sc.name} stays locked`, async ({ page }) => {
        const tools = sc.sequence ? { tools: [...new FakeHub().tools, SEQUENCE_TOOL] } : {}
        const hub = new FakeHub({ jobs: [job('j_RUN', { state: 'running', progress: { phase: 'inference', index: 1, count: 6, step: 1, steps: 6, pct: 3, eta_s: null, text: '' } }), job('j_W1')], ...tools })
        if (sc.sequence) await mockSequence(page, structuredClone(LONG))
        await open(page, sc.path, hub, apiState({ draft: HEAVY, loras: LORAS, chat: { ...chatWithTools(30), busy: true }, media: (await import('./fixtures/data')).mediaItems(5000) }))
        await sc.prepare?.(page)
        await page.locator(sc.ready).first().waitFor()
        await page.waitForTimeout(150)
        await settle(page)

        expect(await rootScroll(page)).toEqual(ZERO)
        expect(await unnamedScrollers(page)).toEqual([])
        const rects = await regionRects(page)
        for (const [k, [x, y, rw, rh]] of Object.entries(rects)) {
          expect.soft(x! >= 0 && y! >= 0 && x! + rw! <= w + 1 && y! + rh! <= h + 1, `${k} inside the window`).toBe(true)
        }
        await page.evaluate(() => { scrollTo(0, 1e6); document.body.scrollTop = 1e6; document.getElementById('root')!.scrollTop = 1e6 })
        expect(await rootScroll(page)).toEqual(ZERO)

        for (const [x, y] of await probes(page)) {
          await page.mouse.move(x, y)
          for (const [dx, dy] of [[0, 2000], [0, -600], [800, 0], [0, 10000]] as const) await page.mouse.wheel(dx, dy)
        }
        await settle(page)
        expect(await rootScroll(page)).toEqual(ZERO)
        if (sc.name !== 'media') expect(await regionRects(page)).toEqual(rects)

        for (const name of sc.lists) {
          const box = page.locator(`[data-scroll="${name}"]`).first()
          expect(await box.evaluate(el => getComputedStyle(el).overflowY), `${name} is a scroller`).toBe('auto')
          const range = await box.evaluate(el => el.scrollHeight > el.clientHeight + 1)
          // 200 LoRAs and 5000 media items always overflow; a list that holds them without range has grown past its box.
          expect.soft(range || !FULL_LISTS.includes(name), `${name} holds its rows inside its box`).toBe(true)
          if (!range) continue
          await box.evaluate(el => { el.scrollTop = 0 })
          const b = (await box.boundingBox())!
          await page.mouse.move(b.x + b.width / 2, b.y + Math.min(b.height / 2, 40))
          await page.mouse.wheel(0, 300)
          await expect.poll(() => box.evaluate(el => el.scrollTop), { message: `${name} scrolls` }).toBeGreaterThan(0)
          await box.evaluate(el => { el.scrollTop = el.scrollHeight })
          await page.mouse.wheel(0, 3000)
          expect(await rootScroll(page)).toEqual(ZERO)
        }

        const { root, small } = await page.evaluate(() => ({
          root: parseFloat(getComputedStyle(document.documentElement).fontSize),
          small: Math.min(...[...document.querySelectorAll<HTMLElement>('body *')]
            .filter(el => !el.closest('[aria-hidden="true"]') && el.offsetParent !== null && [...el.childNodes].some(n => n.nodeType === 3 && n.textContent!.trim()))
            .map(el => parseFloat(getComputedStyle(el).fontSize))),
        }))
        expect(root).toBeCloseTo(expectedRoot(w, h, sc.name === 'media' ? MEDIA_SCALE : 1), 1)
        expect(small).toBeGreaterThanOrEqual(0.85 * root)
      })
    }
  })
}

test.describe('keyboard', () => {
  test('Tab and page keys never move the page', async ({ page }) => {
    await open(page, '/', new FakeHub(), apiState({ draft: HEAVY, loras: LORAS }))
    await page.locator('[data-lora]').first().waitFor()
    const rects = await regionRects(page)
    for (let i = 0; i < 60; i++) {
      await page.keyboard.press('Tab')
      expect(await rootScroll(page)).toEqual(ZERO)
    }
    await page.mouse.click(600, 10)
    for (const k of ['PageDown', 'Space', 'End', 'ArrowDown', 'PageUp', 'Home']) await page.keyboard.press(k)
    expect(await rootScroll(page)).toEqual(ZERO)
    expect((await regionRects(page)).topbar).toEqual(rects.topbar)
  })
})
