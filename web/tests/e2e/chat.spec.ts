// The chat in the Generate screen: Enter sends, `assistant.chat` events update it; the hub carries it to Open WebUI.
// The reply column shows the assistant's replies (and error lines) only; the words as typed are sent, not shown.
import { expect, test, type Page } from '@playwright/test'
import type { ChatView } from '../../src/lib/protocol'
import { FakeHub } from './fixtures/controller'
import { apiState, chatView, chatWithError, chatWithTools } from './fixtures/api'
import { open } from './helpers'

const DRAFT = {
  model: 'flux2_klein_9b', prompt: '', lorasByModel: {}, aspect: '16:9', size: 1.5, images: 2,
  advancedByModel: {}, references: [], selected: null,
}
const ready = (page: Page) => page.locator('[data-lora]').first().waitFor()
const box = (page: Page) => page.locator('#prompt')

test('empty chat shows nothing, no cue and no New chat; the draft article its empty phrase', async ({ page }) => {
  await open(page, '/', new FakeHub(), apiState({ draft: DRAFT }))
  await ready(page)
  const chat = page.locator('[data-region="chat"]')
  await expect(chat).toHaveText('')
  await expect(page.locator('[data-region="status"]')).toHaveText('')      // the job line only; the cue is gone
  await expect(chat.locator('[data-region="chat-head"]')).toHaveCount(1)
  await expect(chat.getByRole('button', { name: 'New chat' })).toHaveCount(0)
  await expect(page.locator('[data-region="draft"]')).toHaveText("The assistant's draft appears here")
  await expect(page.locator('[data-region="draft"]').getByRole('button')).toHaveCount(0)
})

test('Enter sends and clears; Shift+Enter is a newline; Ctrl+Enter generates the draft, not the box', async ({ page }) => {
  const { hub, st } = await open(page, '/', new FakeHub(), apiState({ draft: { ...DRAFT, draft: 'A ginger cat on a wall' } }))
  await ready(page)
  const posts = () => st.calls.filter(c => c.method === 'POST' && c.path === '/api/assistant/chat').map(c => c.body)
  await box(page).fill('Make the cat ginger')
  await box(page).press('Shift+Enter')
  await box(page).pressSequentially('please')
  await expect(box(page)).toHaveValue('Make the cat ginger\nplease')
  expect(posts()).toEqual([])
  await box(page).press('Enter')
  await expect.poll(posts).toEqual([{ text: 'Make the cat ginger\nplease' }])
  await expect(box(page)).toHaveValue('')

  await box(page).fill('A cat on a wall')
  await box(page).press('Control+Enter')
  await expect.poll(() => hub.sent('job.submit').length).toBe(1)
  expect((hub.sent('job.submit')[0]!.d as { params: { prompt: string } }).params.prompt).toBe('A ginger cat on a wall')
  expect(posts()).toHaveLength(1)
  await expect(box(page)).toHaveValue('A cat on a wall')
})

test('while the assistant is busy, Enter does nothing', async ({ page }) => {
  const { hub, st } = await open(page, '/', new FakeHub(), apiState({ draft: DRAFT, chat: chatView(1, true) }))
  await ready(page)
  await box(page).fill('Another one')
  await box(page).press('Enter')
  await page.waitForTimeout(200)
  await expect(box(page)).toHaveValue('Another one')
  expect(st.calls.filter(c => c.method === 'POST' && c.path === '/api/assistant/chat')).toEqual([])
  st.chat = chatView(1)
  hub.chat(st.chat)
  await expect(page.locator('[data-scroll="chat"] i')).toHaveCount(0)
  await box(page).press('Enter')
  await expect(box(page)).toHaveValue('')
})

test('the chat follows assistant.chat; New chat empties the chat, the prompt box and the draft article', async ({ page }) => {
  const { hub, st } = await open(page, '/', new FakeHub(), apiState({ draft: { ...DRAFT, prompt: 'my own words', draft: 'A grape orchard under a volcano' } }))
  await ready(page)
  hub.chat(chatView(12))
  const chat = page.locator('[data-region="chat"]')
  const panel = page.locator('[data-region="draft"]')
  await expect(chat.locator('[data-scroll="chat"] p').last()).toHaveText('A grey cat curled under an apple tree, rain on the leaves, late light.')
  await expect(chat).not.toContainText('take 12. Make it rain.')            // the words as typed are not shown
  const head = chat.locator('[data-region="chat-head"]')
  await expect(head).toContainText('qwen3.5:9b')
  await expect(head.getByRole('button', { name: 'New chat' })).toBeVisible()
  const log = page.locator('[data-scroll="chat"]')
  expect(await log.evaluate(el => el.scrollHeight - el.scrollTop - el.clientHeight)).toBeLessThan(2)
  await expect(box(page)).toHaveValue('my own words')
  await expect(panel).toContainText('A grape orchard under a volcano')
  // a save of the box is on its way (held 800 ms) when New chat comes: the DELETE waits for it to land, so the old
  // text can never be written back over the clearing; typing not yet saved is dropped, never sent
  let inFlight = 0
  await page.route(/\/api\/generate-image\/draft$/, async route => { if (route.request().method() === 'PUT') { inFlight++; await new Promise(r => setTimeout(r, 800)) } await route.fallback() })
  await box(page).fill('my own words, typed before New chat')
  await expect.poll(() => inFlight, { timeout: 4000 }).toBe(1)
  await chat.getByRole('button', { name: 'New chat' }).click()
  await expect(box(page)).toHaveValue('')
  await expect(panel).toHaveText("The assistant's draft appears here")
  await expect.poll(() => st.calls.some(c => c.method === 'DELETE' && c.path === '/api/assistant/chat'), { timeout: 4000 }).toBe(true)
  await expect(chat).toHaveText('')
  await expect(page.locator('[data-region="status"]')).toHaveText('')
  const order = st.calls.filter(c => (c.method === 'PUT' && c.path === '/api/generate-image/draft') || c.method === 'DELETE').map(c => c.method)
  expect(order).toEqual(['PUT', 'DELETE'])
  expect(st.draft).toEqual({ ...DRAFT, prompt: '', draft: '' })
  await box(page).fill('typed after')                               // the box takes typing again, as usual
  const puts = () => st.calls.filter(c => c.path === '/api/generate-image/draft' && c.method === 'PUT').map(c => c.body)
  await expect.poll(puts, { timeout: 5000 }).toEqual([{ prompt: 'my own words, typed before New chat' }, { prompt: 'typed after' }])
  expect(st.draft).toEqual({ ...DRAFT, prompt: 'typed after', draft: '' })
})

test('a failed turn shows as a distinct error line; busy shows what it waits for', async ({ page }) => {
  const { hub, st } = await open(page, '/', new FakeHub(), apiState({ draft: DRAFT }))
  await ready(page)
  hub.chat(chatWithError())
  const chat = page.locator('[data-region="chat"]')
  const err = chat.getByRole('alert')
  await expect(err).toHaveText('Open WebUI did not answer: connection refused')
  await expect(chat.getByText('A grey cat curled under an apple tree')).toBeVisible()
  const color = (l: typeof err) => l.evaluate(el => getComputedStyle(el).color)
  expect(await color(err)).not.toBe(await color(chat.getByText('A grey cat curled under an apple tree')))
  await expect(chat.getByText('Waiting for Open WebUI…')).toHaveCount(0)
  st.chat = chatView(1, true)
  hub.chat(st.chat)
  await expect(chat.getByText('Waiting for Open WebUI…')).toBeVisible()
})

test('the column is the replies with their seconds: your message is not shown; a turn that ran tools and said nothing adds nothing', async ({ page }) => {
  const { hub, st } = await open(page, '/', new FakeHub(), apiState({ draft: { ...DRAFT, prompt: 'an orchard at dusk' } }))
  await ready(page)
  const chat = page.locator('[data-region="chat"]')
  const log = page.locator('[data-scroll="chat"]')
  await box(page).fill('change the orchard to a volcano')
  await box(page).press('Enter')
  st.chat = { busy: true, messages: [{ id: 'u0', role: 'user', text: 'change the orchard to a volcano', at: 1791561600, seconds: null }], model: 'qwen3.5:9b' }
  hub.chat(st.chat)
  await expect(chat.getByText('Waiting for Open WebUI…')).toBeVisible()
  // the hub's turn ended: set_generate_image_settings {draft} ran, the reply had no text — the chat gains nothing
  st.chat = { ...st.chat, busy: false }
  hub.chat(st.chat)
  await expect(chat.getByText('Waiting for Open WebUI…')).toHaveCount(0)
  await expect(log.locator('p')).toHaveCount(0)
  await expect(log).toHaveText('')
  await expect(chat.getByRole('alert')).toHaveCount(0)
  // the next turn: a reply; the view carries the two user messages in a row
  hub.chat(chatWithTools(2))
  await expect(log.getByText('4.2 s')).toBeVisible()
  await expect(log.locator('p')).toHaveText(['Queued two images of the cat.'])
  await expect(log).not.toContainText(/generate_image|set_generate_image_settings|\{|job_id|seed/)
})

test('a message of a role the chat does not know is not shown', async ({ page }) => {
  const { hub } = await open(page, '/', new FakeHub(), apiState({ draft: DRAFT }))
  await ready(page)
  const v = chatView(1)
  const foreign = { id: 't0', role: 'tool', text: 'generate_image {"job_id": "j_ABC"}', at: 1791561610, seconds: null } as unknown as ChatView['messages'][number]
  hub.chat({ ...v, messages: [v.messages[0]!, foreign, v.messages[1]!] })
  const log = page.locator('[data-scroll="chat"]')
  await expect(log.getByText('A grey cat curled under an apple tree, rain on the leaves, late light.')).toBeVisible()
  await expect(log).not.toContainText('generate_image')
  await expect(log.locator('p')).toHaveCount(1)                          // the reply; not the tool line, not yours
})

test('user-role messages are not shown in the reply column while the replies are', async ({ page }) => {
  const { hub } = await open(page, '/', new FakeHub(), apiState({ draft: DRAFT }))
  await ready(page)
  hub.chat(chatView(3))
  const chat = page.locator('[data-region="chat"]')
  const log = page.locator('[data-scroll="chat"]')
  await expect(log.locator('p')).toHaveText(Array(3).fill('A grey cat curled under an apple tree, rain on the leaves, late light.'))
  await expect(log.getByText('4.2 s')).toHaveCount(3)
  for (const i of [1, 2, 3]) await expect(chat).not.toContainText(`take ${i}. Make it rain.`)
  await expect(chat).not.toContainText('Make it rain')
})

test('the Hub\'s own line is a reply\'s card without seconds, followed to the bottom', async ({ page }) => {
  const { hub } = await open(page, '/', new FakeHub(), apiState({ draft: DRAFT }))
  await ready(page)
  const v = chatView(8)
  const text = 'Script 1: 4 takes: 3 ok, 1 flagged: l2 heard 62 %'
  hub.chat({ ...v, messages: [...v.messages, { id: 'h0', role: 'hub', text, at: 1791562200, seconds: null }] })
  const log = page.locator('[data-scroll="chat"]')
  const card = log.getByText(text)
  await expect(card).toBeVisible()
  await expect(log.locator('p').last()).toHaveText(text)
  expect(await card.evaluate(el => el.parentElement!.className)).toBe(await log.getByText('A grey cat curled under an apple tree').first().evaluate(el => el.parentElement!.className))
  await expect(log.getByText('4.2 s')).toHaveCount(8)                    // the replies' seconds; none for the Hub's line
  expect(await card.evaluate(el => el.parentElement!.querySelectorAll('span').length)).toBe(0)
  await expect(page.locator('[data-region="chat"]').getByRole('alert')).toHaveCount(0)
  expect(await log.evaluate(el => el.scrollHeight - el.scrollTop - el.clientHeight)).toBeLessThan(2)
})
