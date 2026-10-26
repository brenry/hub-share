// The measurements on Generate: the reply box level with the page; one inner margin (--gen-edge) from the
// reply box to its head and cards, from a card to its text, and from the page's right and bottom edges to Clear; the
// page count one --sp-4 left of Clear; the reply box ending level with the prompt box; and the page, the replies and
// the prompt box in the bottom line's type (--fs-ctl, --text-3).
import { expect, test, type Page } from '@playwright/test'
import { FakeHub } from './fixtures/controller'
import { apiState } from './fixtures/api'
import type { ChatView } from '../../src/lib/protocol'
import { open, settle } from './helpers'

const LONG = Array.from({ length: 40 }, (_, i) => `Paragraph ${i + 1}: a grey cat asleep under an apple tree after rain, wet leaves catching the last light.`).join('\n\n')
const DRAFT = {
  model: 'flux2_klein_9b', prompt: 'A grey cat under a tree', lorasByModel: {}, aspect: 'auto', size: 1, images: 1,
  advancedByModel: {}, references: [], selected: null, draft: LONG,
}
const T = 1791561600
const CHAT: ChatView = { busy: false, model: 'qwen3.5:9b', messages: [
  { id: 'u1', role: 'user', text: 'A grey cat, please.', at: T, seconds: null },
  { id: 'a1', role: 'assistant', text: 'Drafted a grey cat asleep under an apple tree after rain.', at: T + 6, seconds: 5.8 },
] }

type Box = { left: number; right: number; top: number; bottom: number }

/** Every measurement in one pass, in CSS px. Variables resolve on a probe inside the reply box, where --gen-edge is in
 *  scope; a text's left is where its first glyph box starts. */
const measure = (page: Page) => page.evaluate(() => {
  const q = (sel: string) => {
    const el = document.querySelector<HTMLElement>(sel)
    if (!el) throw new Error(`missing ${sel}`)
    return el
  }
  const box = (el: Element): Box => { const r = el.getBoundingClientRect(); return { left: r.left, right: r.right, top: r.top, bottom: r.bottom } }
  const textLeft = (el: Element) => {
    const walk = document.createTreeWalker(el, NodeFilter.SHOW_TEXT, { acceptNode: n => (n.textContent!.trim() ? 1 : 3) })
    const node = walk.nextNode()
    if (!node) throw new Error('no text')
    const range = document.createRange()
    range.selectNodeContents(node)
    return range.getClientRects()[0]!.left
  }
  const chat = q('[data-region="chat"]')
  const probe = document.createElement('div')
  probe.style.cssText = 'position:absolute;visibility:hidden;width:var(--gen-edge);height:var(--sp-4);font-size:var(--fs-ctl);color:var(--text-3)'
  chat.append(probe)
  const ps = getComputedStyle(probe)
  const vars = { edge: parseFloat(ps.width), sp4: parseFloat(ps.height), fs: ps.fontSize, text3: ps.color }
  probe.remove()

  const head = q('[data-region="chat-head"]')
  const label = head.querySelector('span')!
  const newChat = [...head.querySelectorAll('button')].find(b => b.textContent === 'New chat')!
  const card = chat.querySelector<HTMLElement>('p:not([role="alert"])')!
  const draft = q('[data-region="draft"]')
  const clear = [...q('[data-region="draft-foot"]').querySelectorAll('button')].find(b => b.textContent === 'Clear')!
  const prompt = q('#prompt')
  const draftText = draft.querySelector('p')!
  const mirror = prompt.parentElement!.querySelector('[aria-hidden="true"] > div')!
  const style = (el: Element) => { const cs = getComputedStyle(el); return { fs: cs.fontSize, color: cs.color } }
  return {
    vars,
    chat: box(chat), draft: box(draft), prompt: box(prompt.parentElement!), card: box(card),
    labelText: textLeft(label), newChat: box(newChat), cardText: textLeft(card),
    clear: box(clear), pages: box(q('[data-region="pages"]')),
    type: { draft: style(draftText), card: style(card), prompt: style(prompt), mirror: style(mirror) },
  }
})

for (const [w, h] of [[1920, 1080], [1366, 768]] as const) {
  test(`${w}×${h}: the reply box sits level with the page; one inner margin everywhere; the quiet type`, async ({ page }) => {
    await page.setViewportSize({ width: w, height: h })
    await open(page, '/', new FakeHub(), apiState({ draft: DRAFT, chat: CHAT }))
    await page.locator('[data-region="chat"] p').first().waitFor()
    await expect(page.locator('[data-region="pages"]')).toBeVisible()
    await expect(page.locator('[data-region="chat-head"]').getByRole('button', { name: 'New chat' })).toBeVisible()
    await settle(page)
    const m = await measure(page)
    const { edge, sp4 } = m.vars
    expect(edge, '--gen-edge resolves to a length').toBeGreaterThan(0)

    expect(Math.abs(m.chat.top - m.draft.top), `reply box top ${m.chat.top} vs page top ${m.draft.top}`).toBeLessThanOrEqual(0.5)

    const gaps: Record<string, number> = {
      'head label left': m.labelText - m.chat.left,
      'New chat right': m.chat.right - m.newChat.right,
      'card left': m.card.left - m.chat.left,
      'card text left': m.cardText - m.card.left,
      'Clear right': m.draft.right - m.clear.right,
      'Clear bottom': m.draft.bottom - m.clear.bottom,
    }
    for (const [name, gap] of Object.entries(gaps)) {
      expect(Math.abs(gap - edge), `${name} gap ${gap} vs --gen-edge ${edge} (${JSON.stringify(gaps)})`).toBeLessThanOrEqual(0.5)
    }

    const pagesGap = m.clear.left - m.pages.right
    expect(Math.abs(pagesGap - sp4), `page count to Clear ${pagesGap} vs --sp-4 ${sp4}`).toBeLessThanOrEqual(0.5)

    expect(Math.abs(m.chat.bottom - m.prompt.bottom), `reply box bottom ${m.chat.bottom} vs prompt box bottom ${m.prompt.bottom}`).toBeLessThanOrEqual(1)

    // #prompt's own glyphs are transparent over the tinting mirror, so its visible colour is the mirror's.
    for (const [name, t] of Object.entries(m.type)) {
      expect(t.fs, `${name} font-size`).toBe(m.vars.fs)
      if (name !== 'prompt') expect(t.color, `${name} colour`).toBe(m.vars.text3)
    }
  })
}
