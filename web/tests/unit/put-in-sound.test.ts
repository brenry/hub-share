// A sound goes to the Sound box from Media's menu (Put in Sound, Enter), through the Hub, from any screen. The
// Generate side declares one Sound socket for a model that keeps a sound and places one sound in it.
import { describe, expect, it } from 'vitest'
import type { Focus, Presence, SocketDecl } from '../../src/lib/protocol'
import { declaration, planDelivery } from '../../src/modules/generate-image/delivery'
import { EMPTY_DRAFT } from '../../src/modules/generate-image/edits'
import type { Draft, Model } from '../../src/modules/generate-image/types'
import { deliveryText, soundSend } from '../../src/screens/media/send'
import { H3_OMNI, MODELS } from '../e2e/fixtures/data'

const OMNI = MODELS.find(m => m.id === 'minimax_h3_ref2va')!
const HEARS: Model = { ...OMNI, id: 'minimax_h3_ref2va_pruned', video: { ...H3_OMNI, soundtrack: 'AS' } }
const LINE = 'sounds/2026-10-17/120000-000.wav'
const D: Draft = { ...EMPTY_DRAFT, model: HEARS.id }
const box = (filled: boolean): SocketDecl => ({ id: 'sound', group: 'sound', label: 'Sound', accepts: ['audio'], filled })
const focus = (sockets: SocketDecl[]): Focus => ({ screen: 's', tool: 'generate-image', label: 'Generate Image', mode: 'refs', primary: 'reference', sockets })
const P: Presence = { screens: { workspace: 1, media: 1, aux: 0 }, labels: {}, engines: {} }

describe('the Sound socket', () => {
  it('is declared after the reference boxes only for a model that keeps a sound, filled when a sound is in', () => {
    const decl = declaration(D, HEARS)
    expect(decl.primary).toBe('reference')
    expect(decl.sockets.at(-1)).toEqual(box(false))
    expect(declaration({ ...D, sound: { id: LINE, seconds: 14 } }, HEARS).sockets.at(-1)).toEqual(box(true))
    expect(declaration(D, OMNI).sockets.some(s => s.id === 'sound')).toBe(false)
  })
  it('takes one sound, replacing; refuses more, a model without it, and a continued clip', () => {
    expect(planDelivery(D, HEARS, 'sound', [LINE, 'sounds/x.wav'])).toEqual({
      targets: [{ item: LINE, socket: 'sound', index: -1 }],
      refused: [{ item: 'sounds/x.wav', reason: 'one_only', text: 'one sound at a time' }] })
    expect(planDelivery(D, OMNI, 'sound', [LINE]).refused[0]).toMatchObject({ reason: 'missing', text: 'this model takes no sound' })
    const clip: Draft = { ...D, references: [{ id: 'clips/2026-10-17/a.mp4', w: 960, h: 544, kind: 'clip', seconds: 5 }] }
    expect(planDelivery(clip, HEARS, 'sound', [LINE]).targets).toEqual([])
  })
})

describe('Put in Sound in Media', () => {
  it('its label and why it is off, in order', () => {
    expect(soundSend(true, focus([box(false)]), P, 1, false)).toEqual({ label: 'Put in Sound', off: null })
    expect(soundSend(true, focus([box(true)]), P, 1, false)).toEqual({ label: 'Replace Sound', off: null })
    expect(soundSend(false, focus([box(false)]), P, 1, false).off).toBe('Reconnecting…')
    expect(soundSend(true, focus([box(false)]), P, 2, false).off).toBe('One sound at a time')
    expect(soundSend(true, focus([box(false)]), P, 1, true).off).toBe('One sound at a time')
    expect(soundSend(true, null, P, 1, false).off).toBe('No tool is open')
    expect(soundSend(true, focus([box(false)]), { ...P, screens: { ...P.screens, workspace: 0 } }, 1, false).off).toBe('Generate Image is offline')
    expect(soundSend(true, focus([]), P, 1, false).off).toBe('This model takes no sound')
  })
  it('the toast names the Sound box', () => {
    expect(deliveryText({ status: 'done', tool: 'generate-image', toolLabel: 'Generate Image', placed: [{ item: LINE, socket: 'sound' }], refused: [] }))
      .toBe('Added to Generate Image · Sound')
  })
})
