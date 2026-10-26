// The Director's first cut: the draft panel marks a draft the hub wrote from the assistant's shot; Clear makes
// it a plain draft again (the server forgets the shot when a window sends the draft).
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { afterEach, describe, expect, it } from 'vitest'
import { Article } from '../../src/modules/generate-image/chat/Article'
import { draft } from '../../src/modules/generate-image/draft'
import { EMPTY_DRAFT, normalizeDraft } from '../../src/modules/generate-image/edits'

const PROMPT = 'integrated_multimodal_description: [Shot 1] Character 7 walks to the front of the stage.'
const html = () => renderToStaticMarkup(createElement(Article))

afterEach(() => draft.set(EMPTY_DRAFT))

describe('the draft panel and a shot', () => {
  it('a draft written from a shot carries a thin "shot" label; a plain draft has none', () => {
    draft.set({ ...EMPTY_DRAFT, draft: PROMPT, shot: { subjects: [{ name: 'Character 7' }] } })
    expect(html()).toMatch(/data-region="draft-shot">shot</)
    draft.set({ ...EMPTY_DRAFT, draft: PROMPT, shot: null })
    expect(html()).not.toMatch(/draft-shot/)
    draft.set({ ...EMPTY_DRAFT, draft: '', shot: { subjects: [] } })
    expect(html()).not.toMatch(/draft-shot/)
  })

  it('the server\'s shot comes through a load as it is', () => {
    expect(normalizeDraft({ draft: PROMPT, shot: { where: 'a stage' } }).shot).toEqual({ where: 'a stage' })
    expect(normalizeDraft({ draft: PROMPT }).shot).toBeUndefined()
  })
})
