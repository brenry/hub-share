// The Edit Video page in the e2e tests (Stage 11): the two windows with the tool, the tracks and their
// tiles, the saves sent, and drops on a track.
import { expect, type Page } from '@playwright/test'
import { FakeHub } from './controller'
import { MEDIA_DRAFT, tiles, twoWindows } from './mediaPage'
import { SEQUENCE_TOOL, mockSequence, seqState, type SeqState } from './sequence'

export const tile = (page: Page, n: number, track = 1) => page.locator(`[data-track="${track}"] [data-tile="${n}"]`)
export const strip = (page: Page, track = 1) => page.locator(`[data-track="${track}"]`)
export const shown = (page: Page) => page.locator('[data-region="player"] video[data-on]')

/** play() and pause() recorded; no frame callback (so `timeupdate` hands over); currentTime kept as set. */
export const stubPlayer = (page: Page) => page.addInitScript(() => {
  const calls: string[] = []
  ;(window as unknown as { calls: string[] }).calls = calls
  type V = HTMLMediaElement & { _on?: boolean; _t?: number }
  delete (HTMLVideoElement.prototype as Partial<HTMLVideoElement>).requestVideoFrameCallback
  Object.defineProperty(HTMLMediaElement.prototype, 'paused', { configurable: true, get() { return !(this as V)._on } })
  Object.defineProperty(HTMLMediaElement.prototype, 'currentTime', { configurable: true, get() { return (this as V)._t ?? 0 }, set(v: number) { (this as V)._t = v } })
  HTMLMediaElement.prototype.play = function () { calls.push(`play ${(this as HTMLElement).dataset.place ?? ''}`); (this as V)._on = true; return Promise.resolve() }
  HTMLMediaElement.prototype.pause = function () { (this as V)._on = false }
})
export const plays = (page: Page) => page.evaluate(() => (window as unknown as { calls: string[] }).calls.filter(c => /^play [1-9]/.test(c)))

export async function windows(page: Page, seq: SeqState = seqState(), first = /Opening/) {
  await stubPlayer(page)
  const base = new FakeHub()
  const hub = new FakeHub({ tools: [...base.tools, SEQUENCE_TOOL] })
  const w = await twoWindows(page, MEDIA_DRAFT, { hub, before: p => mockSequence(p, seq) })
  seq.broadcast = (t, d) => hub.broadcast(t, d, 'workspace')
  await page.getByRole('tab', { name: 'Edit Video' }).click()
  await blur(page)
  await expect(page.locator('[data-region="sequences"]')).toHaveText(first)
  return { ...w, hub, seq }
}
/** The focus off the tab (a focused tab answers the arrows and Space itself). */
export const blur = (page: Page) => page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur())
/** Each save's tracks (`track` 0: track 1). */
export const saves = (st: { calls: { method: string; path: string; body: unknown }[] }, track = 0) =>
  st.calls.filter(c => c.method === 'PUT' && c.path === '/api/sequence/one').map(c => (c.body as { tracks: unknown[] }).tracks[track])
export const puts = (st: { calls: { method: string; path: string; body: unknown }[] }) => saves(st)

/** A tile of the Media window, dragged and dropped on track 1 at `x` px from its left (two pages: the payload is
 *  read from one and handed to the other). */
export async function dropFromMedia(media: Page, page: Page, n: number, x: number): Promise<void> {
  const raw = await tiles(media).nth(n).evaluate(el => {
    const dt = new DataTransfer()
    el.dispatchEvent(new DragEvent('dragstart', { bubbles: true, dataTransfer: dt }))
    return dt.getData('application/x-hub-media')
  })
  await dropRaw(page, raw, x)
}
/** A Media payload dropped on a track at `x` px from its left. */
export async function dropRaw(page: Page, raw: string, x: number, track = 1): Promise<void> {
  const box = (await strip(page, track).boundingBox())!
  await strip(page, track).evaluate((el, [data, cx, cy]) => {
    const dt = new DataTransfer()
    dt.setData('application/x-hub-media', data as string)
    el.dispatchEvent(new DragEvent('drop', { bubbles: true, cancelable: true, dataTransfer: dt, clientX: cx as number, clientY: cy as number }))
  }, [raw, box.x + x, box.y + box.height / 2] as const)
}
