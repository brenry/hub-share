// The LoRA sheet: the bar's fold raises it over the conversation without moving the conversation or the bar; its
// rows start on the bar's margin, where its first button (Video, left of the fold) sits; Escape lowers it; shut, it is inert.
import { expect, test, type Page } from '@playwright/test'
import { FakeHub } from './fixtures/controller'
import { apiState } from './fixtures/api'
import { open } from './helpers'

const DRAFT = {
  model: 'flux2_klein_9b', prompt: 'A grey cat', lorasByModel: {}, aspect: 'auto', size: 1, images: 1,
  advancedByModel: {}, references: [], selected: null, draft: 'A grey cat in the rain',
}
const toggle = (page: Page) => page.locator('[data-region="library-toggle"]')
const sheet = (page: Page) => page.locator('[data-region="library-sheet"]')
/** The sheet has finished rolling: the library's top sits at the sheet's top (raised) or past its bottom (shut). */
const settled = (page: Page, up: boolean) => expect.poll(() => page.evaluate(up => {
  const box = document.querySelector('[data-region="library-sheet"]')!.getBoundingClientRect()
  const lib = document.querySelector('[data-region="library"]')!.getBoundingClientRect()
  return up ? Math.abs(lib.top - box.top) < 1 : lib.top >= box.bottom - 1
}, up)).toBe(true)

for (const [w, h] of [[1920, 1080], [1366, 768]] as const) {
  test(`${w}×${h}: the fold raises the sheet over the chat; nothing moves; rows line up with the bar's margin; Escape lowers it`, async ({ page }) => {
    await page.setViewportSize({ width: w, height: h })
    const { hub } = await open(page, '/', new FakeHub(), apiState({ draft: DRAFT }))
    await page.locator('[data-lora]').first().waitFor()
    hub.chat({ busy: false, model: 'qwen3.5:9b', messages: [{ id: 'a0', role: 'assistant', text: 'A cat, then', at: 1791561600, seconds: 1.2 }] })
    const chat = page.locator('[data-region="chat"]')
    const bar = page.locator('footer[data-region="bar"]')
    await expect(chat.getByText('A cat, then')).toBeVisible()
    await expect(toggle(page)).toHaveAttribute('aria-expanded', 'false')
    await expect(sheet(page)).toHaveAttribute('inert', '')
    const [c0, b0] = [await chat.boundingBox(), await bar.boundingBox()]

    await toggle(page).click()
    await expect(toggle(page)).toHaveAttribute('aria-expanded', 'true')
    await settled(page, true)
    expect(await sheet(page).getAttribute('inert')).toBeNull()
    expect(await chat.boundingBox()).toEqual(c0)
    expect(await bar.boundingBox()).toEqual(b0)
    // over the chat: what shows at the chat's centre is the sheet; the bar stays clear of it
    const over = await page.evaluate(([x, y]) => Boolean(document.elementFromPoint(x!, y!)?.closest('[data-region="library-sheet"]')),
      [c0!.x + c0!.width / 2, c0!.y + c0!.height / 2])
    expect(over).toBe(true)
    const s = (await sheet(page).boundingBox())!
    expect(s.y + s.height).toBeLessThanOrEqual(b0!.y + 0.5)
    const t = (await page.locator('[data-region="video-toggle"]').boundingBox())!
    const row = (await page.locator('[data-lora]').first().boundingBox())!
    expect(Math.abs(row.x - t.x), `row left ${row.x} vs the bar's first button left ${t.x}`).toBeLessThanOrEqual(4)

    await page.keyboard.press('Escape')
    await expect(toggle(page)).toHaveAttribute('aria-expanded', 'false')
    await expect(toggle(page)).toBeFocused()
    await settled(page, false)
    await expect(sheet(page)).toHaveAttribute('inert', '')
    expect(await chat.boundingBox()).toEqual(c0)
    expect(await bar.boundingBox()).toEqual(b0)
  })
}

test('shut, the sheet is inert: a LoRA row can be neither clicked nor focused', async ({ page }) => {
  const { st } = await open(page, '/', new FakeHub(), apiState({ draft: DRAFT }))
  const row = page.locator('[data-lora]').first()
  await row.waitFor()
  await expect(sheet(page)).toHaveAttribute('inert', '')
  await expect(row).toHaveAttribute('aria-checked', 'false')
  await expect(row.dblclick({ timeout: 1500 })).rejects.toThrow()
  await row.focus()
  await expect(row).not.toBeFocused()
  // where the row sits when the sheet is up, a click while it is shut lands on the chat, never on the row
  await toggle(page).click()
  await settled(page, true)
  const r = (await row.boundingBox())!
  await page.keyboard.press('Escape')
  await settled(page, false)
  await page.mouse.dblclick(r.x + r.width / 2, r.y + r.height / 2)
  await page.waitForTimeout(300)
  await expect(row).toHaveAttribute('aria-checked', 'false')
  expect(st.calls.filter(c => c.method === 'PUT' && JSON.stringify(c.body).includes('lorasByModel'))).toEqual([])
})
