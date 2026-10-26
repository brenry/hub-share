// The Edit Video tab: two tracks ready with no sequence, and the first drop makes "Sequence 1"; a tile's
// edge dragged trims it in one save and the tiles after it close up; S splits at the playhead; a sound from Media
// placed on track 2 where it is dropped; an mp3 file from the computer made a 48 kHz WAV, kept in Sounds and placed; track
// 1 refuses a sound beside clips with the hub's line.
import { readFileSync } from 'node:fs'
import { expect, test, type Page } from '@playwright/test'
import { CLIP, OPENING, SOUND, seqState } from './fixtures/sequence'
import { dropRaw, saves, strip, tile, windows } from './fixtures/sequencePage'

const fixture = (name: string) => new URL(`./fixtures/${name}`, import.meta.url).pathname
/** Px per second at the default zoom (3 rem a second). */
const perSecond = (page: Page) => page.evaluate(() => parseFloat(getComputedStyle(document.documentElement).fontSize) * 3)

async function dropFile(page: Page, file: string, type: string, track: number, name = file) {
  const b64 = readFileSync(fixture(file)).toString('base64')
  const dt = await page.evaluateHandle(([data, name, kind]) => {
    const t = new DataTransfer()
    t.items.add(new File([Uint8Array.from(atob(data!), c => c.charCodeAt(0))], name!, { type: kind! }))
    return t
  }, [b64, name, type])
  await strip(page, track).dispatchEvent('dragover', { dataTransfer: dt })
  await strip(page, track).dispatchEvent('drop', { dataTransfer: dt })
}

test('with no sequence two empty tracks show; the first drop makes "Sequence 1" and saves into it', async ({ page }) => {
  const { st, seq } = await windows(page, seqState({ seqs: {} }), /Sequences/)
  await expect(strip(page, 1)).toBeVisible()
  await expect(strip(page, 2)).toBeVisible()
  await dropRaw(page, JSON.stringify([{ id: CLIP(179600), w: 960, h: 544, kind: 'clip', seconds: 4, frames: 96, fps: 24 }]), 10)
  await expect(page.locator('[data-region="sequences"]')).toHaveText(/Sequence 1/)
  expect(st.calls.filter(c => c.path === '/api/sequence/new').map(c => c.body)).toEqual([{ name: 'Sequence 1' }])
  await expect.poll(() => saves(st)).toEqual([[{ clip: CLIP(179600), in: 0, out: 96 }]])
  expect(seq.seqs['Sequence 1']!.revision).toBe(1)
  await expect(tile(page, 1)).toContainText('1 · 4 s')
})

test('a tile\'s edge dragged trims it in one save; the tiles after it close up', async ({ page }) => {
  const { st } = await windows(page)
  const PER = await perSecond(page)
  const edge = tile(page, 2).locator('[data-edge="out"]')
  const box = (await edge.boundingBox())!
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2)
  await page.mouse.down()
  await page.mouse.move(box.x + box.width / 2 - PER / 2, box.y + box.height / 2, { steps: 4 })
  await page.mouse.move(box.x + box.width / 2 - PER, box.y + box.height / 2, { steps: 4 })
  // while dragging: drawn, not saved
  await expect(tile(page, 2)).toContainText('2 · 1 s')
  expect(saves(st)).toEqual([])
  await page.mouse.up()
  await expect.poll(() => saves(st)).toEqual([[OPENING[0], { ...OPENING[1], out: 36 }, OPENING[2]]])
  const [second, third] = [(await tile(page, 2).boundingBox())!, (await tile(page, 3).boundingBox())!]
  expect(Math.abs(second.x + second.width - third.x)).toBeLessThan(1.5)
  // the playhead stays on the last frame kept, where the edge was let go
  await expect(page.locator('[data-region="time"]')).toHaveText('0:06.1 / 0:08.1')
})

test('S splits the selected item at the playhead into two of the same clip', async ({ page }) => {
  const { st } = await windows(page)
  await tile(page, 1).click()
  for (let i = 0; i < 12; i++) await page.keyboard.press('ArrowRight')
  await page.keyboard.press('s')
  await expect.poll(() => saves(st)).toEqual([[{ ...OPENING[0], out: 12 }, { ...OPENING[0], in: 12 }, OPENING[1], OPENING[2]]])
  await expect(page.locator('[data-track="1"] [data-tile]')).toHaveCount(4)
  await expect(page.locator('[data-region="time"]')).toHaveText(/ \/ 0:09\.1$/)
})

test('a sound from Media goes on track 2 where it is dropped; another dropped over it goes after it', async ({ page }) => {
  const { st } = await windows(page)
  const PER = await perSecond(page)
  const fx = JSON.stringify([{ id: SOUND(120000), w: 0, h: 0, kind: 'sound', seconds: 1.5 }])
  await dropRaw(page, fx, 2 * PER, 2)
  await expect.poll(() => saves(st, 1)).toEqual([[{ sound: SOUND(120000), in: 0, out: 1500, at: 2000 }]])
  expect(saves(st, 0)).toEqual([OPENING])
  await expect(tile(page, 1, 2)).toHaveAttribute('data-kind', 'sound')
  await dropRaw(page, fx, 2.5 * PER, 2)
  await expect.poll(() => saves(st, 1).length).toBe(2)
  expect(saves(st, 1)[1]).toEqual([{ sound: SOUND(120000), in: 0, out: 1500, at: 2000 }, { sound: SOUND(120000), in: 0, out: 1500, at: 3500 }])
})

test('an mp3 file from the computer is made a 48 kHz WAV, kept in Sounds and placed; beside clips on track 1 it is refused', async ({ page }) => {
  const { st, seq } = await windows(page)
  await dropFile(page, 'voice-3s.mp3', 'audio/mpeg', 1)
  await expect(page.getByRole('status').filter({ hasText: 'Track 1 holds clips or sounds, not both' })).toBeVisible()
  expect(seq.uploads).toHaveLength(1)
  expect(seq.uploads[0]!.rate).toBe(48000)
  await page.locator('[data-region="sequences"]').click()
  await page.getByRole('menuitem', { name: /^Trailer/ }).click()
  await expect(page.locator('[data-region="sequences"]')).toHaveText(/Trailer/)
  await dropFile(page, 'voice-3s.mp3', 'audio/mpeg', 1)
  await expect.poll(() => seq.seqs.Trailer!.tracks[0].map(x => x.sound)).toEqual(['sounds/2026-10-17/up2.wav'])
  await expect(tile(page, 1)).toHaveAttribute('data-kind', 'sound')
  expect(saves(st).at(-1)).toEqual([{ sound: 'sounds/2026-10-17/up2.wav', in: 0, out: Math.round(seq.uploads[1]!.seconds * 1000) }])
  // a file that is not an mp3 or wav: its line, nothing sent
  await dropFile(page, 'voice-1s.wav', 'video/mp4', 2, 'clip.mp4')
  await expect(page.getByRole('status').filter({ hasText: 'From your computer, drop an mp3 or wav' })).toBeVisible()
  expect(seq.uploads).toHaveLength(2)
})

test('a bed on track 2 takes a level, a fade and ducking from its menu; the title says them', async ({ page }) => {
  const { st } = await windows(page)
  const PER = await perSecond(page)
  const fx = JSON.stringify([{ id: SOUND(120000), w: 0, h: 0, kind: 'sound', seconds: 1.5 }])
  await dropRaw(page, fx, 2 * PER, 2)
  await expect.poll(() => saves(st, 1)).toEqual([[{ sound: SOUND(120000), in: 0, out: 1500, at: 2000 }]])
  await tile(page, 1, 2).click({ button: 'right' })
  const menu = page.getByRole('menu', { name: 'Item' })
  const top = menu.locator('[role=menuitem]:not([data-sub] [role=menuitem])')
  await expect(top).toHaveText([/Level 100%/, /Fade in 1 s/, /Fade out 1 s/, /Duck under track 1/, /Split at playhead\s*S/, /Remove from sequence\s*Delete/])
  await menu.getByRole('menuitem', { name: /Level 100%/ }).hover()
  await page.getByRole('menu', { name: /Level/ }).getByRole('menuitem', { name: '50%', exact: true }).click()
  await expect.poll(() => saves(st, 1).length).toBe(2)
  expect(saves(st, 1)[1]).toEqual([{ sound: SOUND(120000), in: 0, out: 1500, at: 2000, level: 0.5 }])
  await tile(page, 1, 2).click({ button: 'right' })
  await menu.getByRole('menuitem', { name: 'Duck under track 1' }).click()
  await expect.poll(() => saves(st, 1).length).toBe(3)
  expect(saves(st, 1)[2]).toEqual([{ sound: SOUND(120000), in: 0, out: 1500, at: 2000, level: 0.5, duck: true }])
  await expect(tile(page, 1, 2)).toHaveAttribute('title', /50% · ducked$/)
  await expect(page.locator('[data-region="sounds"] audio[data-level="0.5"]')).toHaveCount(1)
  await tile(page, 1, 2).click({ button: 'right' })
  await menu.getByRole('menuitem', { name: 'Duck under track 1' }).click()
  await expect.poll(() => saves(st, 1).length).toBe(4)
  expect(saves(st, 1)[3]).toEqual([{ sound: SOUND(120000), in: 0, out: 1500, at: 2000, level: 0.5 }])
  // a track-1 clip's menu has no bed items
  await tile(page, 1).click({ button: 'right' })
  await expect(top).toHaveText([/Split at playhead\s*S/, /Remove from sequence\s*Delete/])
})
