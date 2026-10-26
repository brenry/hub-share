// Shared e2e setup: a fake hub on the bus plus API fixtures, and the lock probes.
import type { Page } from '@playwright/test'
import { FakeHub } from './fixtures/controller'
import { apiState, mockApi, type ApiState } from './fixtures/api'

export async function open(page: Page, path: string, hub = new FakeHub(), st: ApiState = apiState()): Promise<{ hub: FakeHub; st: ApiState }> {
  await hub.attach(page)
  st.broadcast = (t, d) => hub.broadcast(t, d, 'workspace')
  await mockApi(page, st)
  await page.goto(path)
  if (process.env.MUTATION) await page.addStyleTag({ content: process.env.MUTATION })
  await page.evaluate(() => document.fonts.ready)
  return { hub, st }
}

export const settle = (page: Page): Promise<void> =>
  page.evaluate(() => new Promise<void>(r => requestAnimationFrame(() => requestAnimationFrame(() => r()))))

/** The eight values that must stay 0. */
export const rootScroll = (page: Page) => page.evaluate(() => {
  const se = document.scrollingElement!
  return {
    seTop: se.scrollTop, seLeft: se.scrollLeft, x: scrollX, y: scrollY,
    bodyTop: document.body.scrollTop, bodyLeft: document.body.scrollLeft,
    rootTop: document.getElementById('root')!.scrollTop, range: se.scrollHeight - se.clientHeight,
  }
})

export const ZERO = { seTop: 0, seLeft: 0, x: 0, y: 0, bodyTop: 0, bodyLeft: 0, rootTop: 0, range: 0 }

/** Scroll containers with range that are not named scrollers. Must be empty. */
export const unnamedScrollers = (page: Page) => page.evaluate(() => [...document.querySelectorAll<HTMLElement>('*')]
  .filter(el => !el.hasAttribute('data-scroll') && !['INPUT', 'TEXTAREA', 'HTML', 'SELECT'].includes(el.tagName))
  .filter(el => {
    const cs = getComputedStyle(el)
    return /auto|scroll|hidden/.test(cs.overflowX + cs.overflowY) && (el.scrollHeight > el.clientHeight + 1 || el.scrollWidth > el.clientWidth + 1)
  })
  .map(el => `${el.tagName}.${el.className}`))

/** Bounding boxes of every region and named scroller that is not itself scrolled by a named scroller. What sits
 *  inside an inert box (the shut LoRA sheet, rolled down out of sight under its clip) is left out; the box is kept. */
export const regionRects = (page: Page) => page.evaluate(() => Object.fromEntries(
  [...document.querySelectorAll<HTMLElement>('[data-region], [data-scroll]')]
    .filter(el => el.offsetParent !== null && !el.parentElement?.closest('[data-scroll], [inert]'))
    .map(el => {
      const r = el.getBoundingClientRect()
      return [el.dataset.region ?? `scroll:${el.dataset.scroll}`, [r.x, r.y, r.width, r.height].map(v => Math.round(v))]
    })))

/** Settings opens from the Generate bar's fold-up (Settings, cache and seed) → Settings. */
export async function openSettings(page: Page): Promise<void> {
  await page.locator('[data-region="utilities"]').click()
  await page.getByRole('menuitem', { name: 'Settings' }).click()
  await page.locator('[data-region="settings"]').waitFor()
}
