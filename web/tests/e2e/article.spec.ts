// The assistant's draft as a two-column paged article: one wheel gesture turns ONE page, the page keys too, a new
// draft starts on page 1, and a resize never leaves a sliced column at the left edge.
import { expect, test, type Page } from '@playwright/test'
import { FakeHub } from './fixtures/controller'
import { apiState } from './fixtures/api'
import { open } from './helpers'

const para = (i: number, n = 6) => `Paragraph ${i}. ` + 'A grey cat curled under an apple tree, rain on the leaves, late light over the orchard. '.repeat(n)
const LONG = Array.from({ length: 24 }, (_, i) => para(i + 1)).join('\n\n')
const OTHER = Array.from({ length: 14 }, (_, i) => para(i + 1, 5)).join('\n\n')
const DRAFT = {
  model: 'flux2_klein_9b', prompt: '', lorasByModel: {}, aspect: 'auto', size: 1, images: 1,
  advancedByModel: {}, references: [], selected: null, draft: LONG,
}

const article = (page: Page) => page.locator('[data-region="draft"]')
const counter = (page: Page) => page.locator('[data-region="pages"]')
async function at(page: Page): Promise<[number, number]> {
  const t = (await counter(page).textContent()) ?? ''
  const m = /^(\d+) \/ (\d+)$/.exec(t.trim())
  expect(m, `page counter "${t}"`).not.toBeNull()
  return [Number(m![1]), Number(m![2])]
}
/** One wheel gesture: a gap longer than the gesture's end (180 ms) before the next. */
const pause = (page: Page) => page.waitForTimeout(400)

/** The flow's shift against its page, and the visible text fragments' left edges against the window's. */
const geometry = (page: Page) => article(page).evaluate(el => {
  const flow = el.querySelector<HTMLElement>('[data-page]')!
  const win = flow.parentElement!.getBoundingClientRect()
  const page = Number(flow.dataset.page)
  const gap = parseFloat(getComputedStyle(flow).columnGap) || 0
  const shift = new DOMMatrix(getComputedStyle(flow).transform).m41
  const lefts = [...flow.querySelectorAll('p')].flatMap(p => [...p.getClientRects()])
    .filter(r => r.right > win.left + 1 && r.left < win.right - 1).map(r => r.left - win.left)
  return { page, shift, width: flow.clientWidth, gap, want: -page * (flow.clientWidth + gap), first: Math.min(...lefts), sliced: lefts.filter(l => l < -1).length }
})

test('a long draft pages: one gesture one page, wheel back, the page keys; a new draft starts on page 1', async ({ page }) => {
  const { hub, st } = await open(page, '/', new FakeHub(), apiState({ draft: DRAFT }))
  await page.locator('[data-lora]').first().waitFor()
  await expect(counter(page)).toHaveText(/^1 \/ \d+$/)
  const [, n] = await at(page)
  expect(n, "enough pages that a gesture turning more than one would show").toBeGreaterThanOrEqual(5)
  // the page's foot, in its lower right corner: the page count and Clear (no Copy: the draft never reaches the box)
  const foot = article(page).locator('[data-region="draft-foot"]')
  await expect(foot.locator('[data-region="pages"]')).toBeVisible()
  await expect(foot.getByRole('button')).toHaveText(['Clear'])
  const [a, f] = [(await article(page).boundingBox())!, (await foot.boundingBox())!]
  expect(a.x + a.width - (f.x + f.width)).toBeLessThan(40)
  expect(a.y + a.height - (f.y + f.height)).toBeLessThan(40)

  const box = (await article(page).boundingBox())!
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 3)
  await page.mouse.wheel(0, 300)
  await expect(counter(page)).toHaveText(`2 / ${n}`)
  await pause(page)
  // one gesture of several events in quick succession (a swipe and its momentum) turns one page, not several
  await article(page).evaluate(el => { for (let i = 0; i < 8; i++) el.dispatchEvent(new WheelEvent('wheel', { deltaY: 60, bubbles: true, cancelable: true })) })
  await expect(counter(page)).toHaveText(`3 / ${n}`)
  await pause(page)
  expect(await at(page)).toEqual([3, n])
  await page.mouse.wheel(0, -300)
  await expect(counter(page)).toHaveText(`2 / ${n}`)
  await pause(page)
  await page.mouse.wheel(0, -300)
  await expect(counter(page)).toHaveText(`1 / ${n}`)
  await pause(page)
  await page.mouse.wheel(0, -300)                            // no page before the first
  await pause(page)
  await expect(counter(page)).toHaveText(`1 / ${n}`)

  await article(page).focus()
  await page.keyboard.press('PageDown')
  await expect(counter(page)).toHaveText(`2 / ${n}`)
  await page.keyboard.press('PageDown')
  await expect(counter(page)).toHaveText(`3 / ${n}`)
  await page.keyboard.press('PageUp')
  await expect(counter(page)).toHaveText(`2 / ${n}`)
  expect(await page.evaluate(() => [document.scrollingElement!.scrollTop, scrollY])).toEqual([0, 0])

  st.draft = { ...(st.draft as object), draft: OTHER }      // the assistant rewrites its draft
  hub.broadcast('generate-image.draft', {}, 'workspace')
  await expect(article(page)).toContainText('Paragraph 14. A grey cat curled under an apple tree, rain on the leaves, late light over the orchard. A grey')
  await expect(counter(page)).toHaveText(/^1 \/ \d+$/)
  const g = await geometry(page)
  expect(g.page).toBe(0)
  expect(Math.abs(g.shift)).toBeLessThan(0.5)
})

test('a resize keeps the first visible paragraph on the article\'s left edge: no sliced column', async ({ page }) => {
  await open(page, '/', new FakeHub(), apiState({ draft: DRAFT }))
  await page.locator('[data-lora]').first().waitFor()
  await expect(counter(page)).toHaveText(/^1 \/ \d+$/)
  await article(page).focus()
  await page.keyboard.press('PageDown')
  await expect(counter(page)).toHaveText(/^2 \/ \d+$/)
  for (const [w, h] of [[1366, 768], [2560, 1440], [1700, 900]] as const) {
    await page.setViewportSize({ width: w, height: h })
    await expect.poll(async () => { const g = await geometry(page); return Math.abs(g.shift - g.want) }, { message: `${w}×${h} shift` }).toBeLessThan(1)
    const g = await geometry(page)
    expect(g.page, `${w}×${h} still on page 2`).toBe(1)
    expect(Math.abs(g.shift + (g.width + g.gap)), `${w}×${h} shift = -(clientWidth + columnGap)`).toBeLessThan(1)
    expect(Math.abs(g.first), `${w}×${h} first visible fragment at the left edge`).toBeLessThan(2)
    expect(g.sliced, `${w}×${h} fragments cut by the left edge`).toBe(0)
    const [p, n] = await at(page)
    expect(p).toBe(g.page + 1)
    expect(p).toBeLessThanOrEqual(n)
  }
})

test('a short draft has no page counter; an empty one shows the placeholder and no buttons', async ({ page }) => {
  const { hub, st } = await open(page, '/', new FakeHub(), apiState({ draft: { ...DRAFT, draft: 'A grey cat.' } }))
  await page.locator('[data-lora]').first().waitFor()
  await expect(article(page)).toContainText('A grey cat.')
  await expect(counter(page)).toHaveCount(0)
  await expect(article(page).locator('[data-region="draft-foot"]').getByRole('button')).toHaveText(['Clear'])
  st.draft = { ...(st.draft as object), draft: '' }
  hub.broadcast('generate-image.draft', {}, 'workspace')
  await expect(article(page)).toHaveText("The assistant's draft appears here")
  await expect(article(page).getByRole('button')).toHaveCount(0)
})
