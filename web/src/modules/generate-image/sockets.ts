// "I accept X" and "received": declare sockets, and place what Media sends.
import { useEffect, useMemo } from 'react'
import { bus } from '../../lib/bus'
import { errorText } from '../../lib/http'
import type { Deliver, Placed, Refused } from '../../lib/protocol'
import { useBusEvent } from '../../lib/useBus'
import { api, itemThumb } from './api'
import { draft, edit } from './draft'
import { declaration, planDelivery, SOUND, VIDEO } from './delivery'
import { placeRef } from './edits'
import { fitsBox, flash, imageSize } from './inputs'
import type { Draft, Model } from './types'
import { UNREAD } from './run/SoundBox'
import { SHORTEST, VIDEO_SHORT, VIDEO_UNREAD } from './run/VideoBox'
import { shapeNote } from './video'

async function receive(sendId: string, del: Deliver, model: Model | null): Promise<void> {
  const plan = planDelivery(draft.get(), model, del.socket, del.items.map(i => i.id))
  const out: Refused[] = [...plan.refused]
  const placed: Placed[] = []
  const targets = plan.targets.filter(t => t.socket !== SOUND && t.socket !== VIDEO)
  for (const t of plan.targets.filter(x => x.socket === VIDEO)) {         // a clip for camera and set
    const seconds = del.items.find(i => i.id === t.item)?.seconds
    if (typeof seconds !== 'number' || seconds <= 0) { out.push({ item: t.item, reason: 'error', text: VIDEO_UNREAD }); continue }
    if (seconds < SHORTEST) { out.push({ item: t.item, reason: 'error', text: VIDEO_SHORT }); continue }
    edit(d => ({ ...d, video: { id: t.item, seconds } }))
    placed.push({ item: t.item, socket: VIDEO })
  }
  for (const t of plan.targets.filter(x => x.socket === SOUND)) {         // a sound: its id and seconds
    const seconds = del.items.find(i => i.id === t.item)?.seconds
    if (typeof seconds !== 'number' || seconds <= 0) { out.push({ item: t.item, reason: 'error', text: UNREAD }); continue }
    edit(d => ({ ...d, sound: { id: t.item, seconds } }))
    placed.push({ item: t.item, socket: SOUND })
  }
  if (targets.length > 0) {
    try {
      const res = await api.check(targets.map(t => t.item))
      const urls = new Map(del.items.map(i => [i.id, i.url]))
      const sized = await Promise.all(targets.map(async t => {
        const input = res.placed.find(p => p.item === t.item)
        if (!input) return { t, input: null, size: { w: 0, h: 0 } }
        const size = await imageSize(urls.get(t.item) ?? itemThumb(input.id, 1024)).catch(() => ({ w: 0, h: 0 }))
        return { t, input: input.id, size }
      }))
      for (const { t, input, size } of sized) {
        if (input === null) { out.push({ item: t.item, reason: 'error', text: 'could not be placed' }); continue }
        if (!fitsBox(model, size)) { out.push({ item: t.item, reason: 'shape', text: shapeNote(model!) }); continue }
        const slot = { id: input, ...size }
        edit(d => placeRef(d, t.index, slot))
        placed.push({ item: t.item, socket: t.socket })
      }
      flash(placed.filter(p => p.socket !== SOUND && p.socket !== VIDEO).map(p => p.socket))
    } catch (e) {
      out.push(...targets.map(t => ({ item: t.item, reason: 'error', text: errorText(e) })))
    }
  }
  bus.receipt(sendId, { placed, refused: out })
}

/** Keeps the controller's copy of this tool's sockets current, and answers every delivery. References go to the
 *  model picked in the pulldown, in its own boxes (none, pictures, a start frame or identities); the model never changes. */
export function useSockets(d: Draft, model: Model | null): void {
  const decl = useMemo(() => declaration(d, model), [d, model])
  const key = JSON.stringify(decl)
  useEffect(() => { bus.declare(JSON.parse(key)) }, [key])
  useBusEvent('deliver', (data, env) => {
    if (env.id) void receive(env.id, data as Deliver, model)
  })
}
