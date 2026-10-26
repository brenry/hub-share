// The Clips section of the Media window: one row between Characters and Drive, no day rows under it; it shows every
// clip of every day, newest first, as the Temp (tiles are players, the Stage plays, Loop and L loop it); a clip goes to
// no reference box, favorite, character or folder; Delete works; a new clip lands live at the top. /clips is the same
// window opened on the section.
import { expect, test, type Page } from '@playwright/test'
import type { GenerationItem } from '../../src/lib/protocol'
import { FakeHub } from './fixtures/controller'
import { apiState } from './fixtures/api'
import { fakeChars } from './fixtures/media'
import { MEDIA_DRAFT, row, tiles } from './fixtures/mediaPage'
import { open } from './helpers'

const stage = (page: Page) => page.locator('[data-region="stage"]')
const count = (page: Page) => page.locator('[data-region="count"]')
const clip = (id: string): GenerationItem => ({ id, kind: 'clip', url: `/files/${id}`, thumb: null, w: null, h: null, created: 1791562000, job: 'j_clip' })
const SECTIONS = ['temp', 'fav', 'chars', 'clips', 'sounds', 'drive:']
const ids = (page: Page) => tiles(page).evaluateAll(els => els.map(e => e.getAttribute('data-item')))
const order = (page: Page) => page.locator('[data-region="tree"] [data-row]').evaluateAll(els =>
  els.map(e => e.getAttribute('data-row')!))

/** play() and pause() recorded, `paused` kept by them: the toggle is checked without decoding anything. */
const stubPlayer = (page: Page) => page.addInitScript(() => {
  const calls: string[] = []
  ;(window as unknown as { calls: string[] }).calls = calls
  const P = HTMLMediaElement.prototype as unknown as { _on?: boolean }
  Object.defineProperty(HTMLMediaElement.prototype, 'paused', { configurable: true, get() { return !(this as typeof P)._on } })
  HTMLMediaElement.prototype.play = function () { calls.push('play'); (this as typeof P)._on = true; return Promise.resolve() }
  HTMLMediaElement.prototype.pause = function () { calls.push('pause'); (this as typeof P)._on = false }
})

test('/clips: the whole tree, Clips selected between Characters and Drive, no day rows; every clip; tiles are stills; the Stage plays', async ({ page }) => {
  const st = apiState({ chars: fakeChars(['Character 17']) })
  await open(page, '/clips', new FakeHub(), st)
  await tiles(page).first().waitFor()
  const gets = st.calls.filter(c => c.method === 'GET' && c.path.startsWith('/api/media?')).map(c => c.path)
  expect(gets.sort()).toEqual(['/api/media?limit=200', '/api/media?root=clips&limit=200', '/api/media?root=sounds&limit=200'])
  await expect.poll(async () => (await order(page)).filter(r => SECTIONS.includes(r))).toEqual(SECTIONS)
  await expect(row(page, 'clips')).toHaveAttribute('aria-selected', 'true')
  await expect(row(page, 'clips')).toHaveText('Clips5')
  await expect(row(page, 'clips')).not.toHaveAttribute('aria-expanded', /.*/)
  await expect(page.locator('[data-row^="clips/"]')).toHaveCount(0)
  await expect(row(page, 'temp')).toHaveText('Temp60')
  await expect(count(page)).toHaveText('1 / 5')
  // no fold, no days: a second click changes nothing
  await row(page, 'clips').click()
  await expect(page.locator('[data-row^="clips/"]')).toHaveCount(0)

  await expect(tiles(page)).toHaveCount(5)
  expect(await ids(page)).toEqual(['13/180000', '13/179900', '13/179800', '12/179700', '12/179600'].map(x => `clips/2026-10-${x}.mp4`))
  // nothing loads a clip until Play: clip previews are off by default (tiles wait, no still drawn) and the
  // Stage shows a Play button, no player
  await expect(tiles(page).locator('video')).toHaveCount(0)
  const still = tiles(page).first().locator('[data-clip-still]')
  await expect(still).toHaveAttribute('data-clip-still', /^\/files\/clips\/2026-10-13\/180000\.mp4/)
  await expect(tiles(page).locator('img')).toHaveCount(0)
  await page.waitForTimeout(300)
  await expect(page.locator('video')).toHaveCount(0)
  await stage(page).locator('[data-clip-poster]').click()

  const player = stage(page).locator('video')
  await expect(player).toHaveAttribute('controls', '')
  await expect(player).toHaveAttribute('src', '/files/clips/2026-10-13/180000.mp4')
  await expect(stage(page).locator('img')).toHaveCount(0)
  const side = (await page.locator('[data-region="side"]').boundingBox())!
  const box = (await player.boundingBox())!
  expect(box.x + box.width).toBeLessThanOrEqual(side.x + 1)
  expect(Math.abs(box.width / box.height - 960 / 544)).toBeLessThan(0.01)

  await page.keyboard.press('ArrowDown')
  await page.keyboard.press('ArrowRight')
  await expect(count(page)).toHaveText('4 / 5')
  await stage(page).locator('[data-clip-poster]').click()
  await expect(player).toHaveAttribute('src', '/files/clips/2026-10-12/179700.mp4')
  // a clip listed without its size fills the fit box until the file says its own
  await page.route('**/files/clips/2026-10-12/179600.mp4', route => route.fulfill({ status: 404, body: '' }))
  await page.keyboard.press('End')
  await expect(count(page)).toHaveText('5 / 5')
  await stage(page).locator('[data-clip-poster]').click()
  await expect(player).toHaveAttribute('src', '/files/clips/2026-10-12/179600.mp4')
  const sb = (await stage(page).boundingBox())!
  const filled = (await player.boundingBox())!
  expect([filled.x, filled.y, filled.width, filled.height].map(Math.round)).toEqual([sb.x, sb.y, side.x - sb.x, sb.height].map(Math.round))

  // Temp is pictures only
  await row(page, 'temp').click()
  await expect(count(page)).toHaveText('1 / 60')
  await expect(tiles(page).locator('video')).toHaveCount(0)
  await expect(page.locator('[data-stage-img]')).toBeVisible()
})

test('Space plays and pauses while the Stage has focus, and does nothing elsewhere', async ({ page }) => {
  await stubPlayer(page)
  await open(page, '/clips', new FakeHub(), apiState())
  await tiles(page).nth(1).click()
  const calls = () => page.evaluate(() => (window as unknown as { calls: string[] }).calls)
  await page.keyboard.press('Space')
  expect(await calls()).toEqual([])
  await stage(page).focus()
  await page.keyboard.press('Space')
  await expect.poll(calls).toEqual(['play'])
  await page.keyboard.press('Space')
  await expect.poll(calls).toEqual(['play', 'pause'])
  await expect(stage(page)).not.toHaveAttribute('data-wheel', /.*/)
})

test('a clip goes to no reference box, favorite, character or folder (one line each); Delete erases it', async ({ page }) => {
  const hub = new FakeHub()
  const ws = await open(page, '/', hub, apiState({ draft: MEDIA_DRAFT, chars: fakeChars(['Character 17']) }))
  await page.locator('footer[data-region="bar"]').waitFor()
  const media = await page.context().newPage()
  await open(media, '/media', hub, ws.st)
  await tiles(media).first().waitFor()
  await row(media, 'clips').click()
  await expect(count(media)).toHaveText('1 / 5')
  await expect.poll(() => hub.focus?.sockets.length ?? 0).toBeGreaterThan(0)
  await tiles(media).nth(1).click({ button: 'right' })
  const menu = media.getByRole('menu', { name: 'Clip' })
  await expect(menu.getByRole('menuitem')).toHaveText([/Add as reference/, /Put in Video/, /Continue/, /Stop looping/, /Favorite/, /Add to Characters/, /Delete/])
  const offs: [RegExp, string][] = [[/Add as reference/, 'Only pictures can be references'], [/^Favorite/, 'Only pictures can be favorites'],
    [/Add to Characters/, 'Only pictures can be characters']]
  for (const [name, text] of offs) {
    await expect(menu.getByRole('menuitem', { name })).toBeDisabled()
    await expect(menu.getByRole('menuitem', { name })).toHaveAttribute('title', text)
  }
  await expect(menu.getByRole('menuitem', { name: /Delete/ })).toBeEnabled()
  await media.keyboard.press('Escape')
  await media.keyboard.press('Enter')
  await expect(media.getByText('Only pictures can be references')).toBeVisible()
  await media.keyboard.press('f')
  await expect(media.getByText('Only pictures can be favorites')).toBeVisible()
  // dropped on a folder, Favorites or Characters, a clip moves nowhere
  for (const target of ['drive:image', 'fav', 'chars']) await tiles(media).nth(1).dragTo(row(media, target))
  await expect(media.getByLabel('Character name')).toHaveCount(0)
  expect(hub.sent('send')).toEqual([])
  expect(ws.st.calls.filter(c => c.method === 'POST' && /^\/api\/media\/(favorite|move|characters)/.test(c.path))).toEqual([])

  const gone = ws.st.clips[1]!.id
  await tiles(media).nth(1).click()
  await media.keyboard.press('Delete')
  await expect(media.getByText('Deleted')).toBeVisible()
  expect(ws.st.calls.filter(c => c.path === '/api/media/delete').map(c => c.body)).toEqual([{ ids: [gone] }])
  await expect(tiles(media)).toHaveCount(4)
  await expect(count(media)).toHaveText('2 / 4')
  await expect(row(media, 'clips')).toHaveText('Clips4')
  await expect(row(media, 'temp')).toHaveText('Temp60')
  await expect(media.locator(`[data-item="${gone}"]`)).toHaveCount(0)
})

test('a new clip lands live at the top of the Clips (no day row), never in the Temp; a new picture never in the Clips', async ({ page }) => {
  const hub = new FakeHub()
  const { st } = await open(page, '/media', hub, apiState())
  await tiles(page).first().waitFor()
  // the hub has the file when it tells the windows; Media puts it at the top, as a picture in the Temp (flat: no refetch)
  const land = (id: string) => {
    st.clips.unshift({ id, kind: 'clip', url: `/files/${id}`, thumb: null, w: null, h: null, createdAt: 1791562000, group: '', fav: false })
    hub.broadcast('generation', { item: clip(id) }, 'media')
  }
  const asks = () => st.calls.filter(c => c.path.startsWith('/api/media?root=clips')).length
  const before = asks()
  land('clips/2026-10-13/190000.mp4')
  await expect(row(page, 'clips')).toHaveText('Clips6')
  await expect(page.getByText('New clip')).toBeVisible()
  await expect(count(page)).toHaveText('1 / 60')
  await expect(row(page, 'temp')).toHaveText('Temp60')
  await expect(page.locator('[data-item^="clips/"]')).toHaveCount(0)
  expect(asks()).toBe(before)
  // a new day gets no row: its clip joins the one list, at the top
  land('clips/2026-10-14/090000.mp4')
  await expect(row(page, 'clips')).toHaveText('Clips7')
  expect((await order(page)).filter(r => r.startsWith('clips'))).toEqual(['clips'])

  await row(page, 'clips').click()
  await expect(count(page)).toHaveText('1 / 7')
  await expect.poll(async () => (await ids(page)).slice(0, 3)).toEqual(['clips/2026-10-14/090000.mp4', 'clips/2026-10-13/190000.mp4', 'clips/2026-10-13/180000.mp4'])
  // on the section, the newest clip comes up on the Stage
  land('clips/2026-10-14/100000.mp4')
  await expect(count(page)).toHaveText('1 / 8')
  await expect(stage(page).locator('[data-clip-poster] [data-clip-still]')).toHaveAttribute('data-clip-still', /2026-10-14\/100000\.mp4/)
  await expect(stage(page).locator('video')).toHaveCount(0)                  // a new clip never starts loading itself
  await expect(tiles(page).first()).toHaveAttribute('data-item', 'clips/2026-10-14/100000.mp4')
  const id = 'out/2026-10-13/flux2_klein_9b_0099.png'
  hub.broadcast('generation', { item: { id, kind: 'image', url: `/files/${id}`, thumb: `/thumbs/${id}/336`, w: 1680, h: 944, created: 1791562100, job: 'j2' } }, 'media')
  await expect(row(page, 'temp')).toHaveText('Temp61')
  await expect(count(page)).toHaveText('1 / 8')
  await expect(page.locator(`[data-item="${id}"]`)).toHaveCount(0)
  await expect(row(page, 'clips')).toHaveText('Clips8')
})

test('thumbnails folded: the Stage\'s edge zones step through the clips and never play', async ({ page }) => {
  await open(page, '/clips', new FakeHub(), apiState())
  await tiles(page).first().waitFor()
  await page.locator('[data-region="thumbs"]').click()
  await expect(page.locator('[data-region="thumbs"]')).toHaveAttribute('aria-expanded', 'false')
  const st = (await stage(page).boundingBox())!
  const y = st.y + st.height / 2
  const plays = stage(page).locator('video')
  await page.mouse.click(st.x + 20, y)
  await page.waitForTimeout(300)
  await expect(count(page)).toHaveText('1 / 5')
  await expect(plays).toHaveCount(0)                                         // an edge press never plays
  await page.mouse.click(st.x + st.width / 2, y)
  await expect(plays).toHaveCount(1)                                         // Play: the player comes, and plays
  await page.mouse.click(st.x + st.width - 4, y)
  await expect(count(page)).toHaveText('2 / 5')
  await page.mouse.click(st.x + 4, y)
  await expect(count(page)).toHaveText('1 / 5')
})

test('Loop: the clip menu toggles the Stage player\'s loop and its label flips; L too; it holds for the next clip', async ({ page }) => {
  await open(page, '/clips', new FakeHub(), apiState())
  await tiles(page).first().waitFor()
  await stage(page).locator('[data-clip-poster]').click()
  const player = stage(page).locator('video')
  const loops = () => player.evaluate(v => (v as HTMLVideoElement).loop)
  expect(await loops()).toBe(true)                                         // Loop on by default
  const item = async (name: RegExp) => {
    await tiles(page).first().click({ button: 'right' })
    return page.getByRole('menu', { name: 'Clip' }).getByRole('menuitem', { name })
  }
  await (await item(/^Stop looping/)).click()
  await expect.poll(loops).toBe(false)
  await page.keyboard.press('Escape')
  await (await item(/^Loop/)).click()
  await expect(page.getByText('Looping', { exact: true })).toBeVisible()
  await expect.poll(loops).toBe(true)
  await expect(player).toHaveAttribute('loop', '')
  await (await item(/^Stop looping/)).click()
  await expect.poll(loops).toBe(false)
  await expect(await item(/^Loop/)).toBeVisible()
  await page.keyboard.press('Escape')
  await page.keyboard.press('l')
  await expect.poll(loops).toBe(true)
  await expect(await item(/^Stop looping/)).toBeVisible()
  await page.keyboard.press('Escape')
  // the next clip loops too; L on a picture does nothing
  await page.keyboard.press('ArrowRight')
  await stage(page).locator('[data-clip-poster]').click()
  await expect(player).toHaveAttribute('src', '/files/clips/2026-10-13/179900.mp4')
  await expect.poll(loops).toBe(true)
  await row(page, 'temp').click()
  await expect(page.locator('[data-stage-img]')).toBeVisible()
  await page.keyboard.press('l')
  await row(page, 'clips').click()
  await stage(page).locator('[data-clip-poster]').click()
  await expect.poll(loops).toBe(true)
  await page.keyboard.press('L')
  await expect.poll(loops).toBe(false)
})
