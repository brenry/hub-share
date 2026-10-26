// The bar on the Generate screen is ONE line, in the bottom right corner, at 1366×768 and 1920×1080 —
// inside HocusPocus Desktop (so the monitor button shows) and with the widest values the bar can carry.
import { expect, test } from '@playwright/test'
import { FakeHub } from './fixtures/controller'
import { apiState } from './fixtures/api'
import { open, settle } from './helpers'

const WORST = {
  model: 'flux2_klein_9b', prompt: 'A grey cat', lorasByModel: {}, aspect: '16:9', size: 1.5, images: 6,
  advancedByModel: { flux2_klein_9b: { steps: 100, guidance: null, seed: { mode: 'random' } } },
  references: [{ id: 'out/2026-10-09/r1.png', w: 1200, h: 800 }], selected: null, draft: 'A grey cat in the rain',
}

test.use({ userAgent: 'Mozilla/5.0 HocusPocusDesktop/1.2.1 tags=1,2,3' })

for (const [w, h] of [[1366, 768], [1920, 1080]] as const) {
  test(`the bar is one line at ${w}×${h}, monitor button and worst-case values included`, async ({ page }) => {
    await page.setViewportSize({ width: w, height: h })
    await open(page, '/', new FakeHub(), apiState({ draft: WORST }))
    await page.locator('[data-lora]').first().waitFor()
    const bar = page.locator('footer[data-region="bar"]')
    await expect(bar.locator('[data-region="launch"]')).toBeVisible()
    await expect(bar.locator('[data-region="steps"] input')).toHaveValue('100')
    await expect(bar.getByRole('button', { name: 'Size' })).toHaveText('1.5 MP')
    await expect(bar.getByRole('button', { name: 'Aspect' })).toHaveText('16:9')
    await expect(bar.locator('[data-socket] img')).toHaveCount(1)
    await expect(bar.locator('[data-region="count"] output')).toHaveText('6')
    await settle(page)

    const m = await bar.evaluate(el => {
      const kids = [...el.children].map(c => c.getBoundingClientRect()).filter(r => r.width > 0 && r.height > 0)
      const input = el.querySelector<HTMLInputElement>('[data-region="steps"] input')!
      const controls = el.querySelector<HTMLElement>(':scope > span:has([data-region="references"])')!
      const c = controls.getBoundingClientRect()
      const right = Math.max(...[...controls.children].map(k => k.getBoundingClientRect().right))
      return { mids: kids.map(r => r.top + r.height / 2), n: kids.length, inSW: input.scrollWidth, inCW: input.clientWidth, over: controls.scrollWidth - controls.clientWidth, past: right - c.right }
    })
    expect(m.n).toBeGreaterThanOrEqual(6)            // fold, controls, Live, monitor, utilities, Generate
    expect(Math.max(...m.mids) - Math.min(...m.mids), `vertical centres ${m.mids.join(', ')}`).toBeLessThanOrEqual(2)
    expect(m.inSW, `steps "100" is clipped (scrollWidth ${m.inSW} > clientWidth ${m.inCW})`).toBeLessThanOrEqual(m.inCW)
    // The group clips (overflow: clip), so overflow would silently cut the last control: none may stick out, not
    // even a sub-pixel more than rounding (scrollWidth is whole pixels, so the children's right edge is checked too).
    expect(m.over, `the controls group overflows sideways (last control ${m.past.toFixed(2)}px past its right edge)`).toBeLessThanOrEqual(0)
    expect(m.past, 'the last control sticks out of the controls group (px)').toBeLessThanOrEqual(0.5)

    const g = (await bar.locator('[data-region="generate"]').boundingBox())!
    expect(g.x).toBeGreaterThanOrEqual(0)
    expect(g.y).toBeGreaterThanOrEqual(0)
    expect(g.x + g.width).toBeLessThanOrEqual(w)
    expect(g.y + g.height).toBeLessThanOrEqual(h)
    const b = (await bar.boundingBox())!
    expect(b.x + b.width).toBeLessThanOrEqual(w + 0.5)
    expect(b.y + b.height).toBeLessThanOrEqual(h + 0.5)
  })
}
