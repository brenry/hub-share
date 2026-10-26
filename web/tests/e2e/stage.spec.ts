// The Stage tab (the hub's routes stubbed, after mockApi): the list and New set, a picture
// dropped in box 1 with its Keep empty, Build (its body, the progress row), five labelled plates and the pan,
// Approve; on an approved set a change (old above new), Discard; Audience seen shows the House and Build house sends
// its words; a refusal in one line; each Prompt box goes with its pan's presses.
import { expect, test, type Page, type Route } from '@playwright/test'
import type { ToolInfo } from '../../src/lib/protocol'
import { FakeHub } from './fixtures/controller'
import { job } from './fixtures/data'
import { open } from './helpers'

const TOOL: ToolInfo = { id: 'stage', title: 'Stage', tab: { label: 'Stage', order: 45 }, sockets: [] }
const STAGE = ['wide', 'left', 'centre', 'right', 'audience']
const HOUSE = ['wide', 'left', 'right', 'row']
const PIC = 'out/2026-10-09/r1.png'
const NO_ERA = "Say the audience's era"

type J = Record<string, unknown>
type Set = { name: string; approved: J | null; draft: J | null; inputs: J; audience: string }
type St = { sets: Set[]; calls: { path: string; body: J | null }[]; refuse: string | null; hub: FakeHub; prompts: { stage: string; house: string } }

const file = (id: string, v = '') => ({ id, url: `/files/${id}${v}`, thumb: null })
const plates = (dir: string, names: string[], v = '') => Object.fromEntries(names.map(n => [n, file(`${dir}/${n}.png`, v)]))
const json = (route: Route, body: unknown, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })
const approvedOf = (name: string, house: boolean) => ({
  record: { version: 1, name, revision: 1 }, plates: plates(`sets/${name}/plates`, STAGE, '?v=1'), pan_url: `/api/stage/pan?name=${name}&which=stage&v=1`,
  house: house ? plates(`sets/${name}/house`, HOUSE, '?v=1') : null, house_pan_url: null, pictures: [file(`sets/${name}/pictures/1.png`, '?v=1')],
})
const setOne = (): Set => ({
  name: 'Set 1', approved: approvedOf('Set 1', false), draft: null, audience: 'heard',
  inputs: { pictures: [{ id: 'sets/Set 1/pictures/1.png', keep: 'Keep 1' }], description: '', pieces: ['long table'], audience: 'heard', house: { era: '', dress: '', hair: '', size: '' } },
})

async function mockStage(page: Page, st: St): Promise<void> {
  await page.route(/\/api\/stage\//, route => {
    const req = route.request()
    const url = new URL(req.url())
    const p = url.pathname.replace('/api/stage', '')
    const body = req.method() === 'POST' ? req.postDataJSON() as J : null
    st.calls.push({ path: p, body })
    const changed = () => st.hub.broadcast('stage.changed', { name }, 'workspace')
    if (typeof body?.prompt === 'string') st.prompts[p === '/house' || p === '/house-change' ? 'house' : 'stage'] = body.prompt
    if (p === '/sets') {
      return json(route, { sets: st.sets.map(s => ({ name: s.name, approved: !!s.approved, revision: s.approved ? 1 : null, audience: s.audience,
        house: !!s.approved?.house, thumb: s.approved ? `/thumbs/sets/${s.name}/plates/wide.png/96?v=1` : null, state: (s.draft?.state as string) ?? 'none' })), prompts: st.prompts })
    }
    const name = String(url.searchParams.get('name') ?? body?.name)
    let s = st.sets.find(x => x.name === name)
    if (p === '/set') return s ? json(route, { name, inputs: s.inputs, approved: s.approved, draft: s.draft, prompts: st.prompts }) : json(route, { field: 'name', text: 'No such set' }, 400)
    if (st.refuse) return json(route, { problem: st.refuse })
    const start = (mode: string, title: string, words: string | null = null) => {
      s!.draft = { mode, state: 'rendering', job: 'j_pan', problem: null, model: 'MiniMax H3 Ref2VA', words, pan: null, plates: null }
      st.hub.setJob(job('j_pan', { tool: 'stage', kind: 'pan', title, state: 'running',
        summary: { prompt: '', model: 'MiniMax H3 Ref2VA', loras: [], width: 864, height: 480, count: 1, step_names: ['Pan', 'Plates'] },
        progress: { phase: 'render', index: 1, count: 2, step: 3, steps: 8, pct: 30, eta_s: 90, text: 'step 3/8' } }))
      changed()
      return json(route, { job: 'j_pan' })
    }
    if (p === '/build') {
      if (!s) st.sets.push(s = { name, approved: null, draft: null, inputs: {}, audience: String(body!.audience) })
      s.inputs = { ...body, house: { era: '', dress: '', hair: '', size: '' } }
      return start('build', `Stage · ${name} · build`)
    }
    if (p === '/house-change') return start('house-change', `House · ${name} · change`, String(body!.words))
    if (p === '/change') return start('change', `Stage · ${name} · change`, String(body!.words))
    if (p === '/house') return body!.era ? start('house', `House · ${name} · build`) : json(route, { problem: NO_ERA })
    if (p === '/approve') { s!.approved = approvedOf(name, s!.draft?.mode === 'house'); s!.draft = null; changed(); return json(route, { record: {} }) }
    if (p === '/discard') { s!.draft = null; changed(); return json(route, { ok: true }) }
    if (p === '/audience') { s!.audience = String(body!.audience); changed(); return json(route, { record: {} }) }
    return json(route, { text: 'Not found' }, 404)
  })
}

/** The pan job ends: the hub reads its outputs, sets the draft ready and tells the windows. */
function finish(st: St, name: string, names = STAGE): void {
  st.hub.setJob(job('j_pan', { tool: 'stage', kind: 'pan', title: `Stage · ${name}`, state: 'done', progress: null }))
  const s = st.sets.find(x => x.name === name)!
  s.draft = { ...s.draft, state: 'ready', pan: file('clips/2026-10-20/pan.mp4'), plates: plates('out/2026-10-20/pan', names) }
  st.hub.broadcast('stage.changed', { name }, 'workspace')
}

async function stage(page: Page, sets: Set[] = []): Promise<St> {
  const base = new FakeHub()
  const hub = new FakeHub({ tools: [...base.tools, TOOL] })
  const st: St = { sets, calls: [], refuse: null, hub, prompts: { stage: '', house: '' } }
  await open(page, '/', hub)
  await mockStage(page, st)
  await page.getByRole('tab', { name: 'Stage' }).click()
  await page.locator('[data-region="stage-list"]').waitFor()
  return st
}

const box = (page: Page, n: number) => page.locator(`[data-region="stage-boxes"] [data-box="${n}"]`)
const sent = (st: St, path: string) => st.calls.filter(c => c.path === path).map(c => c.body)
const row = (page: Page, which: string, r: string) => page.locator(`[data-region="${which}-plates"] [data-row="${r}"]`)

test('New set, a picture in box 1, Build, five plates and the pan, Approve', async ({ page }) => {
  const st = await stage(page)
  await expect(page.locator('[data-region="stage-list"]')).toContainText('No set')
  await page.getByRole('textbox', { name: 'New set' }).fill('Hall')
  await page.getByRole('textbox', { name: 'New set' }).press('Enter')
  await expect(page.locator('[data-set="Hall"]')).toHaveAttribute('aria-selected', 'true')
  await expect(page.getByLabel('Keep 1')).toHaveValue('')
  await expect(page.locator('[data-region="stage-prompt"]')).toHaveValue('')

  await box(page, 1).evaluate((el, id) => {
    const dt = new DataTransfer()
    dt.setData('application/x-hub-media', JSON.stringify([{ id, w: 1200, h: 800 }]))
    el.dispatchEvent(new DragEvent('drop', { bubbles: true, cancelable: true, dataTransfer: dt }))
  }, PIC)
  await expect(box(page, 1)).toHaveAttribute('data-filled', 'true')
  await expect(page.getByLabel('Keep 1')).toHaveValue('')
  await page.getByRole('textbox', { name: 'Description', exact: true }).fill('a scripted scene')
  await page.getByRole('textbox', { name: 'Pieces' }).fill('long table\n\n two stools ')
  await page.locator('[data-region="stage-build-press"]').click()

  expect(sent(st, '/build')).toEqual([{ name: 'Hall', pictures: [{ id: PIC, keep: '' }], description: 'a scripted scene',
    pieces: ['long table', 'two stools'], audience: 'seen', prompt: '' }])
  await expect(page.locator('[data-region="stage-job"]')).toContainText('Stage · Hall · build · Step 1 of 2 · Pan · 30 %')
  await expect(page.locator('[data-region="stage-job"] [role="progressbar"]')).toHaveAttribute('aria-valuenow', '30')
  await expect(page.locator('[data-region="stage-build-press"]')).toBeDisabled()
  await expect(page.locator('[data-set="Hall"] [data-mark="draft"]')).toHaveText('draft')

  finish(st, 'Hall')
  const shown = row(page, 'stage', 'new').locator('[data-plate]')
  await expect(shown.locator('img')).toHaveCount(5)
  await expect(shown.locator('figcaption')).toHaveText(['Wide', 'Left', 'Centre', 'Right', 'Audience'])
  await expect(page.locator('[data-region="stage-pan"]')).toHaveAttribute('src', '/files/clips/2026-10-20/pan.mp4')
  await expect(page.locator('[data-region="stage-again"]')).toBeEnabled()

  await page.locator('[data-region="stage-approve"]').click()
  expect(sent(st, '/approve')).toEqual([{ name: 'Hall' }])
  await expect(page.locator('[data-set="Hall"] [data-mark="approved"]')).toHaveText('approved')
  await expect(page.locator('[data-region="stage-plates"]')).toHaveAttribute('data-approved', 'true')
  await expect(row(page, 'stage', 'approved').locator('[data-plate="wide"] img')).toHaveAttribute('src', '/files/sets/Hall/plates/wide.png?v=1')
  await expect(page.locator('[data-region="stage-pan"]')).toHaveAttribute('src', '/api/stage/pan?name=Hall&which=stage&v=1')
  await expect(page.locator('[data-region="stage-build"]')).toHaveCount(0)
  await expect(page.locator('[data-region="stage-house"]')).toBeVisible()
})

test('a change shows old above new, Discard; Audience seen and Build house; a refusal in one line', async ({ page }) => {
  const st = await stage(page, [setOne()])
  await page.locator('[data-set="Set 1"]').click()
  await expect(page.locator('[data-region="stage-house"]')).toHaveCount(0)

  st.refuse = 'Set 1 is being rendered now'
  await page.getByRole('textbox', { name: 'Change', exact: true }).fill('add a bench stage left')
  await page.locator('[data-region="stage-change-press"]').click()
  await expect(page.locator('[data-region="stage-problem"]')).toHaveText('Set 1 is being rendered now')
  st.refuse = null

  await page.locator('[data-region="stage-change-press"]').click()
  expect(sent(st, '/change').at(-1)).toEqual({ name: 'Set 1', words: 'add a bench stage left', prompt: '' })
  await expect(page.locator('[data-region="stage-problem"]')).toHaveCount(0)
  await expect(page.locator('[data-region="stage-job"]')).toContainText('Stage · Set 1 · change · Step 1 of 2 · Pan')
  finish(st, 'Set 1')
  const rows = page.locator('[data-region="stage-plates"] [data-row]')
  await expect(rows).toHaveCount(2)
  await expect(rows.nth(0)).toHaveAttribute('data-row', 'approved')
  await expect(rows.nth(1)).toHaveAttribute('data-row', 'new')
  await expect(rows.nth(1)).toContainText('New · add a bench stage left')
  await expect(rows.nth(0).locator('[data-plate="left"] img')).toHaveAttribute('src', '/files/sets/Set 1/plates/left.png?v=1')
  await expect(rows.nth(1).locator('[data-plate="left"] img')).toHaveAttribute('src', '/files/out/2026-10-20/pan/left.png')
  await expect(rows.nth(1).locator('figcaption')).toHaveText(['Wide', 'Left', 'Centre', 'Right', 'Audience'])

  await page.locator('[data-region="stage-discard"]').click()
  expect(sent(st, '/discard')).toEqual([{ name: 'Set 1' }])
  await expect(rows).toHaveCount(1)
  await expect(page.locator('[data-region="stage-plates"]')).toHaveAttribute('data-approved', 'true')

  await page.locator('[data-region="stage-audience"]').getByRole('radio', { name: 'Seen' }).click()
  expect(sent(st, '/audience')).toEqual([{ name: 'Set 1', audience: 'seen' }])
  await expect(page.locator('[data-region="stage-house"]')).toBeVisible()
  await page.locator('[data-region="house-build"]').click()
  await expect(page.locator('[data-region="stage-problem"]')).toHaveText(NO_ERA)
  await page.getByRole('textbox', { name: 'Era', exact: true }).fill('Era 1')
  await page.getByRole('textbox', { name: 'Size', exact: true }).fill('fifty')
  await page.locator('[data-region="house-build"]').click()
  expect(sent(st, '/house').at(-1)).toEqual({ name: 'Set 1', era: 'Era 1', dress: '', hair: '', size: 'fifty', prompt: '' })
  await expect(page.locator('[data-region="house-job"]')).toContainText('House · Set 1 · build · Step 1 of 2 · Pan')
  finish(st, 'Set 1', HOUSE)
  await expect(row(page, 'house', 'new').locator('figcaption')).toHaveText(['Wide', 'Left', 'Right', 'Rows'])
  await expect(page.locator('[data-region="house-approve"]')).toBeVisible()
  await expect(page.locator('[data-region="stage-approve"]')).toHaveCount(0)
})

test('each Prompt box travels with its pan\'s press', async ({ page }) => {
  const st = await stage(page, [{ ...setOne(), approved: approvedOf('Set 1', true), audience: 'seen' }])
  await page.locator('[data-set="Set 1"]').click()
  const stageBox = page.locator('[data-region="stage-prompt"]')
  const houseBox = page.locator('[data-region="house-prompt"]')
  await expect(stageBox).toHaveValue('')
  await expect(houseBox).toHaveValue('')
  await stageBox.fill('Prompt 1\n\n[Line 2] ')
  await houseBox.fill('Prompt 2')
  await page.getByRole('textbox', { name: 'Change', exact: true }).fill('Change 1')
  const changed = page.waitForRequest(r => r.url().endsWith('/api/stage/change'))
  await page.locator('[data-region="stage-change-press"]').click()
  expect((await changed).postDataJSON()).toEqual({ name: 'Set 1', words: 'Change 1', prompt: 'Prompt 1\n\n[Line 2] ' })
  finish(st, 'Set 1')
  await page.locator('[data-region="stage-discard"]').click()
  await expect(page.locator('[data-region="stage-discard"]')).toHaveCount(0)
  await page.getByRole('textbox', { name: 'House change', exact: true }).fill('Change 2')
  const housed = page.waitForRequest(r => r.url().endsWith('/api/stage/house-change'))
  await page.locator('[data-region="house-change-press"]').click()
  expect((await housed).postDataJSON()).toEqual({ name: 'Set 1', words: 'Change 2', prompt: 'Prompt 2' })
  await expect(stageBox).toHaveValue('Prompt 1\n\n[Line 2] ')
  expect(st.prompts).toEqual({ stage: 'Prompt 1\n\n[Line 2] ', house: 'Prompt 2' })
})
