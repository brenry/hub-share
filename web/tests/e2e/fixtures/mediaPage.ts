// Shared by the Media specs: a Generate window with one reference, and a Media window on the same FakeHub.
import type { Page } from '@playwright/test'
import { FakeHub } from './controller'
import { apiState } from './api'
import { open } from '../helpers'

const DRAFT = {
  model: 'flux2_klein_9b', lastModel: { image: 'flux2_klein_9b', video: '' }, prompt: 'A cat', lorasByModel: {}, aspect: 'auto', size: 1, images: 1, advancedByModel: {},
  references: [{ id: 'out/2026-10-09/r1.png', w: 1200, h: 800 }], selected: null, draft: 'A grey cat in the rain',
}
export { DRAFT as MEDIA_DRAFT }
export const row = (page: Page, id: string) => page.locator(`[data-row="${id}"]`)
export const tiles = (page: Page) => page.locator('[data-item]')

/** `hub`: a hub of the spec's own (more tools); `before`: routes registered on the Generate window before it opens. */
export async function twoWindows(page: Page, draft: unknown = DRAFT, opts: { hub?: FakeHub; before?: (p: Page) => Promise<void> } = {}) {
  const hub = opts.hub ?? new FakeHub()
  await opts.before?.(page)
  const ws = await open(page, '/', hub, apiState({ draft }))
  await page.locator('footer[data-region="bar"]').waitFor()
  const media = await page.context().newPage()
  await open(media, '/media', hub, ws.st)
  await tiles(media).first().waitFor()
  return { hub, media, st: ws.st }
}
