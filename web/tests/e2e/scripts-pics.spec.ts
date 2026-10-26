// A shot's own pictures: dragged from Media onto a shot in the right column, each shown with its <Picture N> tag;
// the Hub is told the shot's pictures in order; a press on one takes it off.
import { expect, test, type Route } from '@playwright/test'
import type { ToolInfo } from '../../src/lib/protocol'
import { FakeHub } from './fixtures/controller'
import { mockSequence, seqState, SEQUENCE_TOOL } from './fixtures/sequence'
import { open } from './helpers'

const TOOL: ToolInfo = { id: 'director', title: 'Storyboard', tab: { label: 'Storyboard', order: 30 }, sockets: [] }
const SCRIPT = { version: 2, context: { cast: [{ name: 'A' }] }, scenes: [{ title: 'Scene 1', cast: ['A'], shots: [
  { id: 's1', start_ms: 0, end_ms: 4000, camera: { framing: 'Wide' }, events: [] }] }] }
const json = (route: Route, body: unknown) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) })

test('pictures dropped on a shot are its <Picture 1>, <Picture 2>; a press takes one off', async ({ page }) => {
  const sent: unknown[] = []
  let held: string[] = []
  await page.setViewportSize({ width: 1600, height: 900 })
  await page.route(/\/api\/director\//, route => {
    const req = route.request()
    const p = new URL(req.url()).pathname.replace('/api/director', '')
    if (p === '/scripts') return json(route, { scripts: [{ name: 'Script 1', seconds: 4, scenes: 1, shots: 1, lines: 0, changed: 1, problem: null }] })
    if (p === '/script') return json(route, { name: 'Script 1', seconds: 4, problem: null, script: SCRIPT, pictures: {}, unpictured: [], audio: null })
    if (p === '/shot-pictures' && req.method() === 'POST') {
      const b = req.postDataJSON() as { ids: string[] }
      sent.push(b); held = b.ids
    }
    if (p === '/shot-pictures') return json(route, { pictures: held.length ? { s1: held } : {} })
    return json(route, {})
  })
  await mockSequence(page, seqState())
  await open(page, '/', new FakeHub({ tools: [...new FakeHub().tools, SEQUENCE_TOOL, TOOL] }))
  await page.getByRole('tab', { name: 'Storyboard' }).click()
  const zone = page.locator('[data-shot-pics="s1"]')
  await expect(zone).toBeVisible()
  await zone.evaluate((el, items) => {
    const dt = new DataTransfer()
    dt.setData('application/x-hub-media', JSON.stringify(items))
    el.dispatchEvent(new DragEvent('drop', { dataTransfer: dt, bubbles: true, cancelable: true }))
  }, [{ id: 'out/2026-10-21/p1.png', w: 64, h: 64 }, { id: 'out/2026-10-21/p2.png', w: 64, h: 64 }])
  await expect.poll(() => sent.at(-1)).toMatchObject({ name: 'Script 1', shot: 's1', ids: ['out/2026-10-21/p1.png', 'out/2026-10-21/p2.png'] })
  await expect(zone.locator('[data-pic="2"] input')).toHaveValue('2')
  await zone.locator('[data-pic="2"] input').fill('1')
  await zone.locator('[data-pic="2"] input').press('Enter')
  await expect.poll(() => sent.at(-1)).toMatchObject({ ids: ['out/2026-10-21/p2.png', 'out/2026-10-21/p1.png'] })
  await expect(zone.locator('[data-pic="1"] img')).toHaveAttribute('src', /p2\.png/)
  await zone.locator('[data-pic="1"] button').click()
  await expect.poll(() => sent.at(-1)).toMatchObject({ ids: ['out/2026-10-21/p1.png'] })
})

test('a pasted prompt goes to the Hub from the Import box at the top of the shot list', async ({ page }) => {
  const sent: Record<string, unknown>[] = []
  await page.setViewportSize({ width: 1600, height: 900 })
  await page.route(/\/api\/director\//, route => {
    const req = route.request()
    const p = new URL(req.url()).pathname.replace('/api/director', '')
    if (p === '/scripts') return json(route, { scripts: [{ name: 'Script 1', seconds: 4, scenes: 1, shots: 1, lines: 0, changed: 1, problem: null }] })
    if (p === '/script') return json(route, { name: 'Script 1', seconds: 4, problem: null, script: SCRIPT, pictures: {}, unpictured: [], audio: null })
    if (p === '/edit') sent.push(req.postDataJSON() as Record<string, unknown>)
    return json(route, {})
  })
  await mockSequence(page, seqState())
  await open(page, '/', new FakeHub({ tools: [...new FakeHub().tools, SEQUENCE_TOOL, TOOL] }))
  await page.getByRole('tab', { name: 'Storyboard' }).click()
  const box = page.locator('[data-region="import"]')
  await box.getByRole('textbox', { name: 'Import prompt' }).fill('subject_definitions: one\ndetailed_description: 0:00-0:03 two')
  await box.getByRole('button', { name: 'Import' }).click()
  await expect.poll(() => sent.at(-1)).toMatchObject({ name: 'Script 1', op: 'import', text: 'subject_definitions: one\ndetailed_description: 0:00-0:03 two' })
})
