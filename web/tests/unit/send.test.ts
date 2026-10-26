import { describe, expect, it } from 'vitest'
import type { Focus, Presence, SocketDecl } from '../../src/lib/protocol'
import { deliveryText, sendState } from '../../src/screens/media/send'

const ref = (n: number, filled: boolean): SocketDecl => ({ id: `reference_${n}`, group: 'reference', label: `Reference ${n}`, accepts: ['image'], filled })
const focus = (primary: string | null, sockets: SocketDecl[], mode = 'refs'): Focus => ({ screen: 's', tool: 'generate-image', label: 'Generate Image', mode, primary, sockets })
const P: Presence = { screens: { workspace: 1, media: 1, aux: 0 }, labels: {}, engines: {} }

describe('Smart Send states', () => {
  it('disabled reasons, in order', () => {
    const f = focus('reference', [ref(1, false)])
    expect(sendState(false, f, P, 1)).toMatchObject({ kind: 'disabled', reason: 'Reconnecting…' })
    expect(sendState(true, f, P, 0)).toMatchObject({ kind: 'disabled', reason: 'Select an image' })
    expect(sendState(true, null, P, 1)).toMatchObject({ kind: 'disabled', reason: 'No tool is open', menu: [] })
    expect(sendState(true, f, { ...P, screens: { ...P.screens, workspace: 0 } }, 1)).toMatchObject({ reason: 'Generate Image is offline' })
    expect(sendState(true, focus('reference', []), P, 1)).toMatchObject({ reason: 'This model takes no images' })
  })
  it('reference verbs follow the free slots', () => {
    const f = focus('reference', [ref(1, true), ref(2, false), ref(3, false)])
    expect(sendState(true, f, P, 1)).toMatchObject({ kind: 'enabled', label: 'Add as reference', socket: 'reference' })
    expect(sendState(true, f, P, 2)).toMatchObject({ label: 'Add 2 as references' })
    expect(sendState(true, f, P, 3)).toMatchObject({ label: 'Add 2 of 3 as references' })
  })
  it('full references disable the main action but keep Replace in the menu', () => {
    const st = sendState(true, focus('reference', [ref(1, true), ref(2, true), ref(3, true)]), P, 1)
    expect(st).toMatchObject({ kind: 'disabled', reason: 'References are full (3 of 3)' })
    expect(st.menu.map(m => m.label)).toEqual(['Replace Reference 1', 'Replace Reference 2', 'Replace Reference 3'])
  })
  it('no primary is the pick state with every socket in the menu', () => {
    const st = sendState(true, focus(null, [ref(1, false)], 'new'), P, 2)
    expect(st).toMatchObject({ kind: 'pick', label: 'Send to Generate Image…' })
    expect(st.menu).toEqual([{ label: 'Put in Reference 1', socket: 'reference_1', reason: 'Pick one image to place in a specific slot' }])
  })
})

describe('delivery toasts', () => {
  const done = (placed: string[], refused: string[] = []) => ({
    status: 'done' as const, tool: 'generate-image', toolLabel: 'Generate Image',
    placed: placed.map(socket => ({ item: 'x', socket })), refused: refused.map(text => ({ item: 'y', reason: 'full', text })),
  })
  it('success, range, partial, failure, timeout', () => {
    expect(deliveryText(done(['reference_2']))).toBe('Added to Generate Image · Reference 2')
    expect(deliveryText(done(['reference_3', 'reference_2']))).toBe('2 added to Generate Image · References 2–3')
    expect(deliveryText(done(['reference_2', 'reference_3'], ['references are full']))).toBe('2 added · 1 not added: references are full')
    expect(deliveryText(done([], ['references are full']))).toBe('Not delivered: references are full')
    expect(deliveryText({ status: 'failed', reason: 'offline', text: 'Generate Image is offline' })).toBe('Not delivered: Generate Image is offline')
    expect(deliveryText({ status: 'failed', reason: 'timeout', text: 'No answer from Generate Image' })).toBe('No answer from Generate Image')
  })
})
