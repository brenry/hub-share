// The Casting tab (the hub's routes stubbed): Character 14 cast as Audience with a seat,
// four views 2 x 2, Approve, tagged `audience`, the seat saved when changed; Character 8's `+ Costume`, a picture and words,
// Cast, six views, Approve, the chip showing it, Remove pressed twice.
import { expect, test, type Page, type Route } from '@playwright/test'
import type { ToolInfo } from '../../src/lib/protocol'
import { FakeHub } from './fixtures/controller'
import { job } from './fixtures/data'
import { MEDIA_DRAFT, tiles, twoWindows } from './fixtures/mediaPage'

const CASTING_TOOL: ToolInfo = { id: 'casting', title: 'Casting', tab: { label: 'Casting', order: 40 }, sockets: [] }
const SIX = ['front', 'left', 'back', 'right', 'face-1', 'face-2']
const FOUR = ['front', 'left', 'right', 'face-1']
const JACKET = 'Leather jacket'
const WORDS = 'a worn black leather jacket, white T-shirt, dark jeans, black boots'

type Obj = Record<string, unknown>
type St = { drafts: Record<string, Obj>; costumes: Record<string, Obj>; calls: { path: string; body: Obj | null }[]; hub: FakeHub | null }

const files = (name: string, views: string[], dir = '', variant = '') => ({
  orbit_url: `/api/casting/orbit?name=${name}${variant ? `&variant=${encodeURIComponent(variant)}` : ''}&v=1`, bits: [],
  views: Object.fromEntries(views.map(v => [v, `chars/${name}/${dir}sheet/${v}.png`])),
  view_urls: Object.fromEntries(views.map(v => [v, `/files/chars/${name}/${dir}sheet/${v}.png?v=1`])),
})
const json = (route: Route, body: unknown) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) })

function seed(): Record<string, Obj> {
  const base = (name: string) => ({ name, state: 'none', headshot: { id: `chars/${name}.png`, keep: 'k', ignore: '' }, bits: [],
    facts: { age: '', build: '' }, job: null, orbit: null, views: null, role: 'cast', seat: { side: 'centre', row: 1 }, costumes: [] })
  return {
    'Character 8': { ...base('Character 8'), state: 'approved', record: { version: 1, name: 'Character 8', role: 'cast' }, files: files('Character 8', SIX) },
    'Character 14': base('Character 14'),
  }
}

async function mock(page: Page, st: St): Promise<void> {
  await page.route(/\/api\/casting\//, route => {
    const req = route.request()
    const url = new URL(req.url())
    const p = url.pathname.replace('/api/casting', '')
    const body = req.method() === 'POST' ? req.postDataJSON() as Obj : null
    st.calls.push({ path: p, body })
    const changed = () => st.hub?.broadcast('casting.changed', { name }, 'workspace')
    if (p === '/list') {
      return json(route, Object.values(st.drafts).map(d => {
        const rec = d.record as Obj | undefined
        return { name: d.name, picture: `chars/${String(d.name)}.png`, cast: !!rec, role: rec?.role ?? null, costumes: Object.keys(st.costumes).length }
      }))
    }
    const name = String(url.searchParams.get('name') ?? body?.name)
    const d = st.drafts[name]!
    const chips = () => Object.values(st.costumes).filter(c => c.state !== 'none').map(c => ({ variant: c.variant, state: c.state,
      approved: c.state === 'approved', earlier: false, thumb: c.state === 'approved' ? `/thumbs/chars/${name}/${String(c.variant)}/sheet/front.png/96?v=1` : null }))
    if (p === '/draft') return json(route, { ...d, costumes: chips() })
    if (p === '/seat') { d.seat = body!.seat; changed(); return json(route, { seat: body!.seat, record: d.record ?? null }) }
    if (p === '/cast') {
      const role = (body!.role as string | undefined) ?? 'cast'
      Object.assign(d, { state: 'rendering', job: 'j_character_14', role, seat: body!.seat ?? d.seat, facts: body!.facts })
      st.hub?.setJob(job('j_character_14', { tool: 'casting', kind: 'orbit', title: `Cast · ${name} · audience · 1 pictures`, state: 'running' }))
      changed()
      return json(route, { job: 'j_character_14' })
    }
    if (p === '/approve') {
      Object.assign(d, { state: 'approved', files: files(name, FOUR), record: { version: 1, name, role: d.role, seat: d.seat } })
      changed()
      return json(route, d.record)
    }
    const variant = String(url.searchParams.get('variant') ?? body?.variant)
    const c = st.costumes[variant] ??= { name, variant, state: 'none', faces: ['chars/Character 8/sheet/face-1.png', 'chars/Character 8/sheet/face-2.png'],
      face_thumbs: ['/thumbs/chars/Character 8/sheet/face-1.png/336?v=1', '/thumbs/chars/Character 8/sheet/face-2.png/336?v=1'],
      pictures: [], words: '', job: null, orbit: null, views: null, record: null, files: null }
    if (p === '/costume') return json(route, c)
    if (p === '/costume/cast') {
      Object.assign(c, { state: 'rendering', job: 'j_cost', pictures: body!.pictures, words: body!.words })
      st.hub?.setJob(job('j_cost', { tool: 'casting', kind: 'orbit', title: `Cast · ${name} · ${variant} · 3 pictures`, state: 'running' }))
      changed()
      return json(route, { job: 'j_cost' })
    }
    if (p === '/costume/approve') {
      const entry = { costume: { words: c.words, pictures: [] }, orbit: `${variant}/orbit.mp4` }
      Object.assign(c, { state: 'approved', record: entry, files: files(name, SIX, `${variant}/`, variant) })
      changed()
      return json(route, entry)
    }
    if (p === '/costume/remove') { delete st.costumes[variant]; changed(); return json(route, { removed: variant }) }
    return route.fulfill({ status: 404, contentType: 'application/json', body: '{"text":"Not found"}' })
  })
}

/** A cast job ends: its views and orbit are ready and the windows are told. */
function finish(st: St, id: string, target: Obj, views: string[]): void {
  st.hub!.setJob(job(id, { tool: 'casting', kind: 'orbit', title: 'Cast', state: 'done', progress: null }))
  Object.assign(target, { state: 'ready', orbit: 'clips/2026-10-20/120000.mp4', views: views.map(v => `out/2026-10-20/orbit-${v}.png`) })
  st.hub!.broadcast('casting.changed', { name: target.name }, 'workspace')
}

async function casting(page: Page) {
  const st: St = { drafts: seed(), costumes: {}, calls: [], hub: null }
  const hub = new FakeHub({ tools: [...new FakeHub().tools, CASTING_TOOL] })
  st.hub = hub
  const w = await twoWindows(page, MEDIA_DRAFT, { hub, before: p => mock(p, st) })
  await page.getByRole('tab', { name: 'Casting' }).click()
  await expect(page.locator('[data-region="casting-list"] [data-character]')).toHaveCount(2)
  return { ...w, st }
}

const views = (page: Page) => page.locator('[data-region="casting-views"] [data-view]')
const body = (st: St, path: string) => st.calls.filter(c => c.path === path).map(c => c.body)

test('Character 14 as Audience, the seat, four views 2 x 2, Approve, tagged audience', async ({ page }) => {
  const { st } = await casting(page)
  await page.locator('[data-character="Character 14"]').click()
  await expect(page.getByRole('combobox', { name: 'Side' })).toHaveCount(0)
  await page.getByRole('radio', { name: 'Audience' }).click()
  await page.getByRole('combobox', { name: 'Side' }).selectOption('left')
  const more = page.getByRole('button', { name: 'More row' })
  await more.click()
  await more.click()
  await expect(page.getByRole('group', { name: 'Row' }).locator('output')).toHaveText('3')
  await expect.poll(() => body(st, '/seat').at(-1)).toEqual({ name: 'Character 14', seat: { side: 'left', row: 3 } })
  await expect(page.locator('[data-region="casting-chips"]')).toHaveCount(0)

  await page.locator('[data-region="casting-cast"]').click()
  expect(body(st, '/cast').at(-1)).toMatchObject({ name: 'Character 14', role: 'audience', seat: { side: 'left', row: 3 } })
  await expect(page.locator('[data-region="casting-job"]')).toContainText('Cast · Character 14 · audience')

  finish(st, 'j_character_14', st.drafts['Character 14']!, FOUR)
  await expect(views(page).locator('img')).toHaveCount(4)
  await expect(views(page).locator('figcaption')).toHaveText(['Front', 'Left', 'Right', 'Face'])
  const box = async (i: number) => (await views(page).nth(i).boundingBox())!
  const [front, left, right] = [await box(0), await box(1), await box(2)]
  expect(Math.abs(front.y - left.y)).toBeLessThan(2)
  expect(right.y).toBeGreaterThan(front.y + front.height / 2)
  expect(Math.abs(right.x - front.x)).toBeLessThan(2)

  await page.locator('[data-region="casting-approve"]').click()
  await expect(page.locator('[data-character="Character 14"] [data-cast]')).toHaveText('audience')
  await expect(page.locator('[data-character="Character 8"] [data-cast]')).toHaveText('cast')
  await expect(views(page).nth(3).locator('img')).toHaveAttribute('src', '/files/chars/Character 14/sheet/face-1.png?v=1')
  await page.getByRole('combobox', { name: 'Side' }).selectOption('right')
  await expect.poll(() => body(st, '/seat').at(-1)).toEqual({ name: 'Character 14', seat: { side: 'right', row: 3 } })
})

test('Character 8 + Costume, a picture and words, Cast, six views, Approve, the chip, Remove twice', async ({ page }) => {
  const { media, st } = await casting(page)
  await page.locator('[data-character="Character 8"]').click()
  await page.locator('[data-region="casting-add"]').click()
  await page.getByRole('textbox', { name: 'Costume name' }).fill(JACKET)
  await page.getByRole('textbox', { name: 'Costume name' }).press('Enter')
  const boxes = page.locator('[data-region="casting-boxes"]')
  await expect(boxes).toHaveAttribute('data-costume', JACKET)
  await expect(boxes.locator('[data-face] img')).toHaveCount(2)
  await expect(page.getByLabel('Keep 1')).toHaveCount(0)
  await expect(page.locator(`[data-chip="${JACKET}"]`)).toHaveAttribute('aria-selected', 'true')

  const raw = await tiles(media).nth(0).evaluate(el => {
    const dt = new DataTransfer()
    el.dispatchEvent(new DragEvent('dragstart', { bubbles: true, dataTransfer: dt }))
    return dt.getData('application/x-hub-media')
  })
  await boxes.locator('[data-box="3"]').evaluate((el, data) => {
    const dt = new DataTransfer()
    dt.setData('application/x-hub-media', data)
    el.dispatchEvent(new DragEvent('drop', { bubbles: true, cancelable: true, dataTransfer: dt }))
  }, raw)
  await expect(boxes.locator('[data-box="3"]')).toHaveAttribute('data-filled', 'true')
  await page.getByLabel('Keep 3').fill('the jacket')
  await page.getByRole('textbox', { name: 'Costume', exact: true }).fill(WORDS)
  await page.locator('[data-region="casting-cast"]').click()
  const id = (JSON.parse(raw) as { id: string }[])[0]!.id
  expect(body(st, '/costume/cast')).toEqual([{ name: 'Character 8', variant: JACKET, pictures: [{ id, keep: 'the jacket', ignore: '' }], words: WORDS, prompt: '' }])
  await expect(page.locator('[data-region="casting-job"]')).toContainText(`Cast · Character 8 · ${JACKET}`)

  finish(st, 'j_cost', st.costumes[JACKET]!, SIX)
  await expect(views(page).locator('img')).toHaveCount(6)
  await page.locator('[data-region="casting-approve"]').click()
  expect(body(st, '/costume/approve')).toEqual([{ name: 'Character 8', variant: JACKET }])
  await expect(page.locator('[data-region="casting-sheet"]')).toHaveAttribute('data-approved', 'true')
  await expect(views(page).nth(0).locator('img')).toHaveAttribute('src', `/files/chars/Character 8/${JACKET}/sheet/front.png?v=1`)
  await expect(page.locator(`[data-chip="${JACKET}"]`)).toHaveAttribute('data-approved', 'true')
  await expect(page.locator(`[data-chip="${JACKET}"] img`)).toHaveCount(1)

  await page.locator('[data-chip=""]').click()
  await expect(page.getByLabel('Keep 1')).toBeVisible()
  await page.locator(`[data-chip="${JACKET}"]`).click()
  await expect(views(page).nth(0).locator('img')).toHaveAttribute('src', `/files/chars/Character 8/${JACKET}/sheet/front.png?v=1`)

  const remove = page.locator('[data-region="casting-remove"]')
  await remove.click()
  await expect(remove).toHaveText(`Remove ${JACKET}`)
  expect(body(st, '/costume/remove')).toEqual([])
  await remove.click()
  expect(body(st, '/costume/remove')).toEqual([{ name: 'Character 8', variant: JACKET }])
  await expect(page.locator(`[data-chip="${JACKET}"]`)).toHaveCount(0)
  await expect(page.getByLabel('Keep 1')).toBeVisible()
})
