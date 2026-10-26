// The Edit Video tab (Stage 11): Media is the bin, in the other window. A clip dragged from it goes into
// the gap of track 1 under the pointer; a picture is refused; tiles move; I and O trim; Delete takes the item out of
// the sequence and never touches the clip; play runs the items in order; Save queues and says when it is done; a save
// drawn from an old revision reloads; hidden, the tab's keys do nothing.
import { expect, test } from '@playwright/test'
import type { JobSummary } from '../../src/lib/protocol'
import { job } from './fixtures/data'
import { row } from './fixtures/mediaPage'
import { CLIP, OPENING } from './fixtures/sequence'
import { blur, dropFromMedia, dropRaw, plays, puts, shown, strip, tile, windows } from './fixtures/sequencePage'

test('a clip dragged from Media goes into the gap under the pointer, whole, in one save; the strip shows it in its place', async ({ page }) => {
  const { media, st, seq } = await windows(page)
  await expect(tile(page, 3)).toBeVisible()
  await expect(tile(page, 1)).toContainText('1 · 5.17 s')
  await expect(tile(page, 2)).toContainText('2 · 2 s')
  await expect(page.locator('[data-region="time"]')).toHaveText('0:00.0 / 0:09.1')
  await row(media, 'clips').click()
  const second = (await tile(page, 2).boundingBox())!
  const left = (await strip(page).boundingBox())!.x
  await dropFromMedia(media, page, 3, second.x - left + 4)
  const added = CLIP(179700, '2026-10-12')
  // its frames unknown to Media: `out` left for the hub, which keeps the clip whole
  await expect(tile(page, 2)).toHaveAttribute('title', '179700.mp4')
  expect(puts(st)).toEqual([[OPENING[0], { clip: added, in: 0 }, OPENING[1], OPENING[2]]])
  expect(seq.seqs.Opening!.revision).toBe(4)
  await expect(tile(page, 2)).toContainText('2 · 5.17 s')
  await expect(tile(page, 4)).toContainText('4 · 2 s')
  await expect(tile(page, 2).locator('[data-clip-still]')).toHaveAttribute('data-clip-still', `/files/${added}`)
  await expect(tile(page, 2).locator('[data-clip-still]')).toHaveAttribute('data-at', '0')
  await expect(tile(page, 3).locator('[data-clip-still]')).toHaveAttribute('data-at', '0.5')
  await expect(page.locator('[data-region="strip"] video')).toHaveCount(0)
  await expect(page.locator('[data-region="time"]')).toHaveText('0:00.0 / 0:14.3')
  // frames carried by the drag: `out` at them, still one save
  await dropRaw(page, JSON.stringify([{ id: CLIP(179600), w: 960, h: 544, kind: 'clip', seconds: 4, frames: 96, fps: 24 }]), 4)
  await expect(tile(page, 1)).toContainText('1 · 4 s')
  expect(puts(st)).toHaveLength(2)
  expect(puts(st)[1]).toEqual([{ clip: CLIP(179600), in: 0, out: 96 }, OPENING[0], { clip: added, in: 0, out: 124 }, OPENING[1], OPENING[2]])
  expect(seq.seqs.Opening!.revision).toBe(5)
})

test('a picture is refused with its line and nothing is saved', async ({ page }) => {
  const { media, st } = await windows(page)
  await dropFromMedia(media, page, 0, 10)
  await expect(page.getByRole('status').filter({ hasText: 'Only clips and sounds go in a sequence' })).toBeVisible()
  await page.waitForTimeout(200)
  expect(puts(st)).toEqual([])
  await expect(page.locator('[data-track="1"] [data-tile]')).toHaveCount(3)
})

test('a tile dragged along the strip moves', async ({ page }) => {
  const { st } = await windows(page)
  const box = (await strip(page).boundingBox())!
  await tile(page, 1).dragTo(strip(page), { targetPosition: { x: box.width - 8, y: box.height / 2 } })
  await expect.poll(() => puts(st)).toEqual([[OPENING[1], OPENING[2], OPENING[0]]])
  await expect(tile(page, 3)).toHaveAttribute('title', '180000.mp4')
  await expect(tile(page, 3)).toHaveAttribute('aria-selected', 'true')
  // the playhead at its start in the saved order (2 s + 2 s), not the old one
  await expect(page.locator('[data-region="time"]')).toHaveText('0:04.0 / 0:09.1')
})

test('tile 3 moved to gap 0: the playhead sits at 0', async ({ page }) => {
  const { st } = await windows(page)
  await tile(page, 2).click()
  await expect(page.locator('[data-region="time"]')).toHaveText('0:05.1 / 0:09.1')
  await tile(page, 3).dragTo(strip(page), { targetPosition: { x: 4, y: (await strip(page).boundingBox())!.height / 2 } })
  await expect.poll(() => puts(st)).toEqual([[OPENING[2], OPENING[0], OPENING[1]]])
  await expect(tile(page, 1)).toHaveAttribute('aria-selected', 'true')
  await expect(page.locator('[data-region="time"]')).toHaveText('0:00.0 / 0:09.1')
})

test('I and O set the selected item\'s in and out at the playhead and save them', async ({ page }) => {
  const { st } = await windows(page)
  await tile(page, 2).click()
  await expect(tile(page, 2)).toHaveAttribute('aria-selected', 'true')
  await expect(page.locator('[data-region="time"]')).toHaveText('0:05.1 / 0:09.1')
  await expect(page.getByRole('button', { name: 'In', exact: true })).toHaveText('0.50')
  for (let i = 0; i < 3; i++) await page.keyboard.press('ArrowRight')
  await page.keyboard.press('i')
  await expect.poll(() => puts(st)).toEqual([[OPENING[0], { ...OPENING[1], in: 15 }, OPENING[2]]])
  await expect(page.getByRole('button', { name: 'In', exact: true })).toHaveText('0.63')
  for (let i = 0; i < 5; i++) await page.keyboard.press('ArrowRight')
  await page.keyboard.press('o')
  await expect.poll(() => puts(st).length).toBe(2)
  expect(puts(st)[1]).toEqual([OPENING[0], { ...OPENING[1], in: 15, out: 21 }, OPENING[2]])
  await expect(page.getByRole('button', { name: 'Out', exact: true })).toHaveText('0.88')
  await expect(tile(page, 2)).toContainText('2 · 0.25 s')
  // the playhead outside the item: nothing
  await page.keyboard.press('Home')
  await page.keyboard.press('i')
  await page.waitForTimeout(200)
  expect(puts(st)).toHaveLength(2)
})

test('Delete takes the item out of the sequence and never erases the clip', async ({ page }) => {
  const { st } = await windows(page)
  await tile(page, 3).click({ button: 'right' })
  const menu = page.getByRole('menu', { name: 'Item' })
  await expect(menu.getByRole('menuitem')).toHaveText([/Split at playhead\s*S/, /Remove from sequence\s*Delete/])
  await page.keyboard.press('Escape')
  await page.keyboard.press('Delete')
  await expect.poll(() => puts(st)).toEqual([[OPENING[0], OPENING[1]]])
  await expect(page.locator('[data-track="1"] [data-tile]')).toHaveCount(2)
  expect(st.calls.filter(c => c.path.startsWith('/api/media/delete'))).toEqual([])
})

test('play runs the items in order: at an item\'s out the held player shows the next one', async ({ page }) => {
  await windows(page)
  await expect(shown(page)).toHaveAttribute('data-place', '1')
  const held = page.locator('[data-region="player"] video:not([data-on])')
  await expect(held).toHaveAttribute('data-place', '2')
  expect(await held.evaluate(v => (v as HTMLVideoElement).currentTime)).toBeCloseTo(12.5 / 24, 9)
  await page.keyboard.press('Space')
  await expect(page.getByRole('button', { name: 'Pause' })).toBeVisible()
  await expect.poll(() => plays(page)).toEqual(['play 1'])
  const end = async (seconds: number) => shown(page).evaluate((v, t) => {
    (v as HTMLVideoElement).currentTime = t
    v.dispatchEvent(new Event('timeupdate'))
  }, seconds)
  await end(123 / 24)
  await expect(shown(page)).toHaveAttribute('data-place', '1')
  await end(124 / 24)
  await expect(shown(page)).toHaveAttribute('data-place', '2')
  await expect(shown(page)).toHaveAttribute('src', `/files/${CLIP(179900)}`)
  await expect(held).toHaveAttribute('data-place', '3')
  await expect.poll(() => plays(page)).toEqual(['play 1', 'play 2'])
  await end(60 / 24)
  await expect(shown(page)).toHaveAttribute('data-place', '3')
  await end(48 / 24)
  await expect(page.getByRole('button', { name: 'Play' })).toBeVisible()
  await expect(page.locator('[data-region="time"]')).toHaveText('0:09.1 / 0:09.1')
})

test('Save posts the sequence; its progress shows and "Saved" says when the job is done', async ({ page }) => {
  const { hub, st, seq } = await windows(page)
  await page.locator('[data-region="join"]').click()
  await expect.poll(() => st.calls.filter(c => c.path === '/api/sequence/join').map(c => c.body)).toEqual([{ name: 'Opening' }])
  expect(seq.joins).toEqual(['Opening'])
  const j = job('j_join1', { tool: 'sequence', kind: 'join', title: 'Save · Opening · 3 items', state: 'running',
    progress: { phase: 'joining', index: 0, count: 1, step: 110, steps: 220, pct: 0, eta_s: null, text: '' } })
  hub.setJob(j)
  await expect(page.getByRole('progressbar', { name: 'Saving' })).toHaveAttribute('aria-valuenow', '50')
  hub.setJob({ ...j, state: 'done', progress: null, summary: { seconds: 9.17 } as unknown as JobSummary })
  await expect(page.getByRole('status').filter({ hasText: 'Saved: 9.17 s' })).toBeVisible()
  await expect(page.getByRole('progressbar', { name: 'Saving' })).toHaveCount(0)
  await expect(page.locator('[data-region="join"]')).toHaveAttribute('title', 'Save')
  // an empty sequence: Save is off and says why
  await page.locator('[data-region="sequences"]').click()
  await page.getByRole('menuitem', { name: /^Trailer/ }).click()
  await expect(page.locator('[data-region="join"]')).toHaveAttribute('title', 'The sequence is empty')
  await expect(page.locator('[data-region="join"]')).toHaveAttribute('aria-disabled', 'true')
})

test('a save drawn from an old revision is refused: the window reloads the sequence and says the line', async ({ page }) => {
  const { st, seq } = await windows(page)
  // another window saved without this one hearing of it
  seq.seqs.Opening = { revision: 9, tracks: [[OPENING[2]!, OPENING[0]!], []], changed: 2 }
  await tile(page, 1).click()
  await page.keyboard.press('Delete')
  await expect(page.getByRole('status').filter({ hasText: 'The sequence changed in another window' })).toBeVisible()
  await expect(page.locator('[data-track="1"] [data-tile]')).toHaveCount(2)
  await expect(tile(page, 1)).toHaveAttribute('title', '179800.mp4')
  expect(puts(st)).toEqual([[OPENING[1], OPENING[2]]])
  // told of a change, it reloads; told of its own revision, it does not
  const gets = () => st.calls.filter(c => c.path.startsWith('/api/sequence/one?')).length
  const before = gets()
  seq.broadcast?.('sequence.changed', { name: 'Opening', revision: 9 })
  await page.waitForTimeout(300)
  expect(gets()).toBe(before)
  seq.seqs.Opening = { revision: 10, tracks: [[OPENING[0]!], []], changed: 2 }
  seq.broadcast?.('sequence.changed', { name: 'Opening', revision: 10 })
  await expect(page.locator('[data-track="1"] [data-tile]')).toHaveCount(1)
})

test('hidden, the tab\'s keys do nothing', async ({ page }) => {
  const { st } = await windows(page)
  await tile(page, 2).click()
  await page.getByRole('tab', { name: 'Generate Image' }).click()
  await blur(page)
  for (const k of ['Delete', 'Space', 'i', 'o', 'End']) await page.keyboard.press(k)
  await page.waitForTimeout(200)
  expect(puts(st)).toEqual([])
  expect(await plays(page)).toEqual([])
  await page.getByRole('tab', { name: 'Edit Video' }).click()
  await blur(page)
  await expect(page.locator('[data-region="time"]')).toHaveText('0:05.1 / 0:09.1')
  await page.keyboard.press('Delete')
  await expect.poll(() => puts(st)).toEqual([[OPENING[0], OPENING[2]]])
})
