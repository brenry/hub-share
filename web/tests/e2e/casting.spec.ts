// The Casting tab (the hub's routes stubbed): the list of characters, one opened (its
// picture in box 1 with the default keep line), a bit dropped from the Media window into box 2, Cast (one job, its
// state on the tab), the six labelled views and the orbit when it ends, Approve (marked cast); a refusal in one line.
// The tab's Prompt box goes with Cast as typed.
import { expect, test, type Page, type Route } from '@playwright/test'
import type { ToolInfo } from '../../src/lib/protocol'
import { FakeHub } from './fixtures/controller'
import { job } from './fixtures/data'
import { MEDIA_DRAFT, tiles, twoWindows } from './fixtures/mediaPage'

const CASTING_TOOL: ToolInfo = { id: 'casting', title: 'Casting', tab: { label: 'Casting', order: 40 }, sockets: [] }
const KEEP = "Take from <Picture 1> the character's identity: face shape and features, eye colour, hair colour, length and style"
const VIEWS = ['front', 'left', 'back', 'right', 'face-1', 'face-2']
const ORBIT = 'clips/2026-10-20/120000.mp4'
const NO_MODEL = 'Pick a Ref2VA video model in Generate (one that takes reference pictures)'

type Draft = Record<string, unknown> & { state: string }
type St = { cast: Set<string>; drafts: Record<string, Draft>; refuse: string | null; calls: { path: string; body: unknown }[]; hub: FakeHub | null }

const fresh = (name: string): Draft => ({
  name, state: 'none', headshot: { id: `chars/${name}.png`, keep: KEEP, ignore: '' }, bits: [], facts: { age: '', build: '' },
  job: null, orbit: null, views: null,
})
const json = (route: Route, body: unknown, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })

async function mockCasting(page: Page, st: St): Promise<void> {
  await page.route(/\/api\/casting\//, route => {
    const req = route.request()
    const url = new URL(req.url())
    const p = url.pathname.replace('/api/casting', '')
    const body = req.method() === 'POST' ? req.postDataJSON() as Record<string, unknown> : null
    st.calls.push({ path: p, body })
    if (p === '/list') return json(route, ['Character 8', 'Character 6'].map(name => ({ name, picture: `chars/${name}.png`, cast: st.cast.has(name) })))
    const name = String(url.searchParams.get('name') ?? body?.name)
    const d = st.drafts[name] ??= fresh(name)
    if (p === '/draft') return json(route, d)
    if (p === '/cast' || p === '/again') {
      if (st.refuse) return json(route, { problem: st.refuse })
      const n = 1 + (Array.isArray(body?.bits) ? body.bits.length : (d.bits as unknown[]).length)
      st.drafts[name] = { ...d, ...(p === '/cast' ? { headshot: { ...(d.headshot as object), ...(body!.headshot as object) }, bits: body!.bits, facts: body!.facts, prompt: body!.prompt } : {}),
        state: 'rendering', job: 'j_cast1', views: null, orbit: null }
      st.hub?.setJob(job('j_cast1', { tool: 'casting', kind: 'orbit', title: `Cast · ${name} · ${n} pictures`, lane: 'image.gpu0', state: 'running',
        progress: { phase: 'render', index: 0, count: 1, step: 3, steps: 8, pct: 30, eta_s: 90, text: 'step 3/8' } }))
      st.hub?.broadcast('casting.changed', { name }, 'workspace')
      return json(route, { job: 'j_cast1' })
    }
    if (p === '/approve') {
      const files = { orbit_url: `/api/casting/orbit?name=${name}`, bits: [], views: Object.fromEntries(VIEWS.map(v => [v, `chars/${name}/sheet/${v}.png`])),
        view_urls: Object.fromEntries(VIEWS.map(v => [v, `/files/chars/${name}/sheet/${v}.png?v=1`])) }
      st.drafts[name] = { ...d, state: 'approved', files, record: { version: 1, name, role: 'cast' } }
      st.cast.add(name)
      st.hub?.broadcast('casting.changed', { name }, 'workspace')
      return json(route, { version: 1, name, role: 'cast' })
    }
    return json(route, { text: 'Not found' }, 404)
  })
}

/** The cast job ends: the hub reads its outputs, sets the draft ready and tells the windows. */
function finish(st: St, name: string): void {
  st.hub!.setJob(job('j_cast1', { tool: 'casting', kind: 'orbit', title: `Cast · ${name} · 2 pictures`, state: 'done', progress: null }))
  st.drafts[name] = { ...st.drafts[name]!, state: 'ready', orbit: ORBIT, views: VIEWS.map(v => `out/2026-10-20/orbit-${v}.png`) }
  st.hub!.broadcast('casting.changed', { name }, 'workspace')
}

async function casting(page: Page, over: Partial<St> = {}) {
  const st: St = { cast: new Set(), drafts: {}, refuse: null, calls: [], hub: null, ...over }
  const base = new FakeHub()
  const hub = new FakeHub({ tools: [...base.tools, CASTING_TOOL] })
  st.hub = hub
  const w = await twoWindows(page, MEDIA_DRAFT, { hub, before: p => mockCasting(p, st) })
  await page.getByRole('tab', { name: 'Casting' }).click()
  await expect(page.locator('[data-region="casting-list"] [data-character]')).toHaveCount(2)
  return { ...w, st }
}

const box = (page: Page, n: number) => page.locator(`[data-region="casting-boxes"] [data-box="${n}"]`)

/** A Media tile dragged in the Media window and dropped on box `n` of the Casting tab. */
async function dropTile(media: Page, page: Page, tile: number, n: number): Promise<string> {
  const raw = await tiles(media).nth(tile).evaluate(el => {
    const dt = new DataTransfer()
    el.dispatchEvent(new DragEvent('dragstart', { bubbles: true, dataTransfer: dt }))
    return dt.getData('application/x-hub-media')
  })
  await box(page, n).evaluate((el, data) => {
    const dt = new DataTransfer()
    dt.setData('application/x-hub-media', data)
    el.dispatchEvent(new DragEvent('drop', { bubbles: true, cancelable: true, dataTransfer: dt }))
  }, raw)
  return (JSON.parse(raw) as { id: string }[])[0]!.id
}

test('list, open, drop a bit, Cast, six views, Approve', async ({ page }) => {
  const { media, st } = await casting(page)
  await expect(page.getByRole('tab', { name: 'Casting' })).toBeVisible()
  await page.locator('[data-character="Character 8"]').click()
  await expect(box(page, 1).locator('img')).toHaveAttribute('src', '/thumbs/chars/Character%208.png/336')
  await expect(page.getByLabel('Keep 1')).toHaveValue(KEEP)
  await expect(box(page, 2)).not.toHaveAttribute('data-filled')

  const id = await dropTile(media, page, 0, 2)
  await expect(box(page, 2)).toHaveAttribute('data-filled', 'true')
  await page.getByLabel('Keep 2').fill('the headphones')
  await page.getByRole('textbox', { name: 'Description', exact: true }).fill('description 1')
  await page.locator('[data-region="casting-cast"]').click()

  const sent = st.calls.find(c => c.path === '/cast')!.body
  expect(sent).toEqual({ name: 'Character 8', headshot: { keep: KEEP, ignore: '' }, bits: [{ id, keep: 'the headphones', ignore: '' }], facts: { age: '', build: 'description 1' }, prompt: '' })
  await expect(page.locator('[data-region="casting-job"]')).toContainText('Cast · Character 8 · 2 pictures · step 3/8')
  await expect(page.locator('[data-region="casting-cast"]')).toBeDisabled()
  await expect(page.locator('[data-region="casting-approve"]')).toHaveCount(0)

  finish(st, 'Character 8')
  const views = page.locator('[data-region="casting-views"] [data-view]')
  await expect(views.locator('img')).toHaveCount(6)
  await expect(views.locator('figcaption')).toHaveText(['Front', 'Left', 'Back', 'Right', 'Face', 'Three-quarter face'])
  await expect(views.nth(0).locator('img')).toHaveAttribute('src', '/thumbs/out/2026-10-20/orbit-front.png/1024')
  await expect(page.locator('[data-region="casting-orbit"]')).toHaveAttribute('src', `/files/${ORBIT}`)
  await expect(page.getByLabel('Keep 2')).toHaveValue('the headphones')

  await page.locator('[data-region="casting-approve"]').click()
  expect(st.calls.filter(c => c.path === '/approve').map(c => c.body)).toEqual([{ name: 'Character 8' }])
  await expect(page.locator('[data-character="Character 8"] [data-cast]')).toHaveText('cast')
  await expect(page.locator('[data-region="casting-sheet"]')).toHaveAttribute('data-approved', 'true')
  await expect(views.nth(5).locator('img')).toHaveAttribute('src', '/files/chars/Character 8/sheet/face-2.png?v=1')
  await expect(page.locator('[data-region="casting-orbit"]')).toHaveAttribute('src', '/api/casting/orbit?name=Character 8')
  await expect(page.locator('[data-region="casting-cast"]')).toHaveText('Cast again')
  await expect(page.locator('[data-character="Character 6"] [data-cast]')).toHaveCount(0)
})

test('a refusal is one line on the tab; a clip is not a bit; Again keeps the pictures', async ({ page }) => {
  const { st } = await casting(page, { refuse: NO_MODEL })
  await page.locator('[data-character="Character 6"]').click()
  await expect(page.getByLabel('Keep 1')).toHaveValue(KEEP)
  await box(page, 2).evaluate(el => {
    const dt = new DataTransfer()
    dt.setData('application/x-hub-media', JSON.stringify([{ id: 'clips/2026-10-13/180000.mp4', w: 960, h: 544, kind: 'clip', seconds: 5.17 }]))
    el.dispatchEvent(new DragEvent('drop', { bubbles: true, cancelable: true, dataTransfer: dt }))
  })
  await expect(page.locator('[data-region="casting-problem"]')).toHaveText('Only pictures go in a box')
  await expect(box(page, 2)).not.toHaveAttribute('data-filled')

  await page.locator('[data-region="casting-cast"]').click()
  await expect(page.locator('[data-region="casting-problem"]')).toHaveText(NO_MODEL)
  expect(st.hub!.jobs.size).toBe(0)

  st.refuse = null
  await page.locator('[data-region="casting-cast"]').click()
  await expect(page.locator('[data-region="casting-problem"]')).toHaveCount(0)
  finish(st, 'Character 6')
  await page.locator('[data-region="casting-again"]').click()
  expect(st.calls.filter(c => c.path === '/again').map(c => c.body)).toEqual([{ name: 'Character 6' }])
  await expect(page.locator('[data-region="casting-job"]')).toContainText('Cast · Character 6')
})

test('the Prompt box travels with Cast', async ({ page }) => {
  await casting(page)
  await page.locator('[data-character="Character 8"]').click()
  const text = page.getByRole('textbox', { name: 'Prompt', exact: true })
  await expect(text).toHaveValue('')
  const typed = 'Prompt 1\n\n[1] Line 1  '
  await text.fill(typed)
  const sent = page.waitForRequest(r => r.url().endsWith('/api/casting/cast') && r.method() === 'POST')
  await page.locator('[data-region="casting-cast"]').click()
  expect((await sent).postDataJSON()).toMatchObject({ name: 'Character 8', prompt: typed })
  await expect(page.locator('[data-region="casting-job"]')).toContainText('Cast · Character 8')
  await expect(text).toHaveValue(typed)
})
