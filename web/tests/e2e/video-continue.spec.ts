// Stage 6, continue a clip: Media's Continue (a clip's right-click menu and the bar's button while the Stage shows a
// clip) posts the clip to the hub, which puts it in box 1 of Generate Image; the clip stays where it is (flat).
// Box 1 then plays it ("Continues <stem>"), boxes 2–3 are shut, Size and Aspect are greyed with the clip's size, the
// job sends the clip alone at its size, and Settings shows the step as "+N s". The Clips section is one row, its
// tiles every day's clips newest first, as the Temp. A clip tile dragged onto box 1 of the Generate window does the same; onto box 2 or 3 it
// is refused with one line.
import { expect, test, type Page } from '@playwright/test'
import { FakeHub } from './fixtures/controller'
import { apiState, type ApiState } from './fixtures/api'
import type { FakeItem } from './fixtures/data'
import { row, tiles } from './fixtures/mediaPage'
import { open, openSettings } from './helpers'

const H3 = 'minimax_h3'
const LOOSE = 'clips/2026-10-13/101500-123.mp4'
const DRAFT = {
  model: H3, prompt: '', lorasByModel: {}, aspect: '9:16', size: 2, images: 1, advancedByModel: {},
  references: [] as unknown[], selected: null, draft: 'The same shot continues.',
}
const clip = (id: string, at: number, sized = true): FakeItem => ({ id, kind: 'clip', url: `/files/${id}`, thumb: null,
  w: sized ? 960 : null, h: sized ? 544 : null, seconds: sized ? 5.17 : null, createdAt: 1791561600 + at, group: '', fav: false })
/** Newest first, as the hub lists them, one flat list: three clips of the 13th, then an unreadable clip of the 12th. */
const CLIPS = () => [clip(LOOSE, 300), clip('clips/2026-10-13/093500-000.mp4', 200), clip('clips/2026-10-13/093000-000.mp4', 100),
  clip('clips/2026-10-12/180000-000.mp4', 0, false)]
const SLOT = { id: LOOSE, w: 960, h: 544, kind: 'clip', seconds: 5.17 }
const bar = (page: Page) => page.locator('footer[data-region="bar"]')
const slot = (page: Page, n: number) => page.locator(`[data-socket="reference_${n}"]`)
const posts = (st: ApiState) => st.calls.filter(c => c.path === '/api/generate-image/continue').map(c => [c.method, c.body])
const order = (page: Page) => page.locator('[data-region="tree"] [data-row^="clips"]').evaluateAll(els => els.map(e => e.getAttribute('data-row')))

async function windows(page: Page, draft: unknown = DRAFT) {
  const hub = new FakeHub()
  const ws = await open(page, '/', hub, apiState({ draft, clips: CLIPS() }))
  await bar(page).locator('[data-region="steps"] input').waitFor()
  const media = await page.context().newPage()
  await open(media, '/clips', hub, ws.st)
  await tiles(media).first().waitFor()
  return { hub, media, st: ws.st }
}

test('right-click Continue: the id is posted, one line says so, the clip stays where it is and selected; box 1 plays it', async ({ page }) => {
  const { hub, media, st } = await windows(page)
  await tiles(media).first().click({ button: 'right' })
  const menu = media.getByRole('menu', { name: 'Clip' })
  await expect(menu.getByRole('menuitem')).toHaveText([/Add as reference/, /Put in Video/, /Continue/, /Stop looping/, /Favorite/, /Add to Characters/, /Delete/])
  await menu.getByRole('menuitem', { name: /Continue/ }).click()
  await expect(media.getByText('Continue: 101500-123 is in box 1')).toBeVisible()
  expect(posts(st)).toEqual([['POST', { id: LOOSE }]])
  await expect(media.locator(`[data-item="${LOOSE}"]`)).toHaveAttribute('aria-selected', 'true')
  await expect(tiles(media).first()).toHaveAttribute('data-item', LOOSE)
  await expect(media.locator('[data-region="stage"] [data-clip-poster] [data-clip-still]')).toHaveAttribute('data-clip-still', `/files/${LOOSE}`)
  await expect.poll(() => order(media)).toEqual(['clips'])

  // the Generate window redraws from the hub's draft: box 1 shows the clip's still (no player), boxes 2–3 shut
  await expect(slot(page, 1)).toHaveAttribute('title', 'Continues 101500-123')
  await expect(slot(page, 1).locator('[data-clip-still]')).toHaveAttribute('data-clip-still', `/files/${LOOSE}`)
  await expect(slot(page, 1).locator('[data-clip-still]')).toHaveCount(1)        // clip previews off: no still drawn
  await expect(slot(page, 1).locator('video')).toHaveCount(0)
  for (const n of [2, 3]) {
    await expect(slot(page, n)).toHaveAttribute('data-shut', 'true')
    await expect(slot(page, n)).toHaveAttribute('title', 'A continued clip takes only box 1')
  }
  // Size and Aspect are greyed: the clip's size is the hover text and nothing opens
  for (const name of ['Size', 'Aspect']) {
    const b = bar(page).getByRole('button', { name, exact: true })
    await expect(b).toHaveAttribute('aria-disabled', 'true')
    await expect(b).toHaveAttribute('title', "The clip's size, 960×544")
    await b.click({ force: true })
    await expect(page.getByRole('listbox', { name })).toBeHidden()
  }
  // the job: the clip alone, at its size, the step's frames
  await page.locator('[data-region="generate"]').click()
  await expect.poll(() => hub.sent('job.submit').length).toBe(1)
  expect(hub.sent('job.submit')[0]!.d).toEqual({ tool: 'generate-image', kind: 'image', params: {
    tool: 'generate-image', model: H3, mode: 'refs', prompt: DRAFT.draft, loras: [], width: 960, height: 544, images: 1, steps: 20,
    guidance: null, seed: { mode: 'random' }, frames: 124, references: [LOOSE] } })
})

test('the bar\'s Continue shows only while the Stage shows a clip; a refusal is one line; two clips are one at a time', async ({ page }) => {
  const { media, st } = await windows(page)
  const go = media.locator('[data-region="continue"]')
  await expect(go).toHaveAttribute('title', 'Continue this clip')
  await row(media, 'temp').click()
  await expect(media.locator('[data-stage-img]')).toBeVisible()
  await expect(go).toHaveCount(0)
  await row(media, 'clips').click()
  await media.keyboard.press('End')
  await go.click()
  await expect(media.getByText('This clip is not an MP4 the hub can read')).toBeVisible()
  await media.keyboard.press('Home')
  await go.click()
  await expect(media.getByText('Continue: 101500-123 is in box 1')).toBeVisible()
  expect(posts(st)).toEqual([['POST', { id: 'clips/2026-10-12/180000-000.mp4' }], ['POST', { id: LOOSE }]])

  await tiles(media).first().click()
  await tiles(media).nth(1).click({ modifiers: ['Control'] })
  await tiles(media).nth(1).click({ button: 'right' })
  const item = media.getByRole('menu', { name: 'Clip' }).getByRole('menuitem', { name: /Continue/ })
  await expect(item).toBeDisabled()
  await expect(item).toHaveAttribute('title', 'One clip at a time')
})

test('a picture has no Continue', async ({ page }) => {
  const { media } = await windows(page)
  await row(media, 'temp').click()
  await tiles(media).first().click({ button: 'right' })
  await expect(media.getByRole('menu', { name: 'Image' }).getByRole('menuitem', { name: /Continue/ })).toHaveCount(0)
})

test('the Clips tiles newest first across every day, as the Temp: no day or group rows', async ({ page }) => {
  const { media } = await windows(page)
  await expect.poll(() => order(media)).toEqual(['clips'])
  await expect(row(media, 'clips')).toHaveText('Clips4')
  const ids = () => tiles(media).evaluateAll(els => els.map(e => e.getAttribute('data-item')))
  await expect.poll(ids).toEqual(CLIPS().map(c => c.id))
  await expect(media.locator('[data-region="count"]')).toHaveText('1 / 4')
})

test('Settings → Seconds with a clip in box 1 shows the step as "+5.1 s" and stops at the longest step', async ({ page }) => {
  await open(page, '/', new FakeHub(), apiState({ draft: { ...DRAFT, references: [SLOT] }, clips: CLIPS() }))
  await bar(page).locator('[data-region="steps"] input').waitFor()
  await openSettings(page)
  await page.locator('[data-card="generate-image"]').click()
  const sec = page.getByRole('region', { name: 'MiniMax H3' })
  const seconds = sec.getByRole('spinbutton', { name: 'Seconds' })
  await expect(seconds).toHaveValue('5.2')
  await expect(sec.locator('[data-region="step"]')).toHaveText('+5.1 s')
  await expect(seconds).toHaveAttribute('max', '13.7')
  await seconds.fill('30')
  await seconds.press('Enter')
  await expect(seconds).toHaveValue('13.7')
  await expect(sec.locator('[data-region="step"]')).toHaveText('+13.6 s')
})

/** What the Media window's clip tile carries when dragged, dropped on a box of the Generate window (two pages: the
 *  payload is read from one and handed to the other). */
async function dragClip(media: Page, page: Page, n: number): Promise<void> {
  const raw = await tiles(media).first().evaluate(el => {
    const dt = new DataTransfer()
    el.dispatchEvent(new DragEvent('dragstart', { bubbles: true, dataTransfer: dt }))
    return dt.getData('application/x-hub-media')
  })
  expect(JSON.parse(raw)).toEqual([{ id: LOOSE, w: 960, h: 544, kind: 'clip', seconds: 5.17 }])
  await slot(page, n).evaluate((el, data) => {
    const dt = new DataTransfer()
    dt.setData('application/x-hub-media', data)
    el.dispatchEvent(new DragEvent('drop', { bubbles: true, cancelable: true, dataTransfer: dt }))
  }, raw)
}

test('a clip tile dragged onto box 1 is continued as the menu does: posted, box 1 plays it', async ({ page }) => {
  const { media, st } = await windows(page)
  await dragClip(media, page, 1)
  await expect.poll(() => posts(st)).toEqual([['POST', { id: LOOSE }]])
  await expect(slot(page, 1)).toHaveAttribute('title', 'Continues 101500-123')
  await expect(slot(page, 1).locator('[data-clip-still]')).toHaveAttribute('data-clip-still', `/files/${LOOSE}`)
  await expect(slot(page, 2)).toHaveAttribute('data-shut', 'true')
})

test('a clip tile dragged onto box 2 is refused with one line and nothing is posted', async ({ page }) => {
  const { media, st } = await windows(page)
  await dragClip(media, page, 2)
  await expect(page.getByRole('status').filter({ hasText: 'A continued clip takes only box 1' })).toBeVisible()
  expect(posts(st)).toEqual([])
  await expect(slot(page, 1)).not.toHaveAttribute('title', /Continues/)
  await expect(slot(page, 1).locator('[data-clip-still]')).toHaveCount(0)
})
