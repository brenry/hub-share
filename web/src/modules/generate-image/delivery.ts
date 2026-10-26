// Pure: the socket declaration and where delivered items go.
import type { Declaration, Refused, SocketDecl } from '../../lib/protocol'
import { CLIP_ONLY_TEXT } from './blocking'
import { jobMode } from './job'
import { TOOL, type Draft, type Model } from './types'
import { besideClip, boxLabel, clipInBox, soundOf, videoOf } from './video'

/** The Sound box's socket (Media's Put in Sound). */
export const SOUND = 'sound'
/** The Video box's socket (Media's Put in Video). */
export const VIDEO = 'video'

export function declaration(d: Draft, m: Model | null): Declaration {
  const sockets: SocketDecl[] = []
  for (let i = 0; i < (m?.refCap ?? 0); i++) {
    sockets.push({ id: `reference_${i + 1}`, group: 'reference', label: boxLabel(m, i, clipInBox(d) !== null), accepts: ['image'], filled: i < d.references.length })
  }
  const primary = sockets.length > 0 ? 'reference' : null
  if (m?.video?.soundtrack) sockets.push({ id: SOUND, group: SOUND, label: 'Sound', accepts: ['audio'], filled: soundOf(d, m) !== null })
  if (m?.video?.reference_video) sockets.push({ id: VIDEO, group: VIDEO, label: 'Video', accepts: ['video'], filled: videoOf(d, m) !== null })
  return { tool: TOOL, mode: jobMode(d), primary, sockets }
}

type Target = { item: string; socket: string; index: number }

/** Decide each item's slot. Nothing is silently replaced: a group fills free slots only; nothing joins a clip in box 1
 *  but the identities of a model that takes them beside it. */
export function planDelivery(d: Draft, m: Model | null, socket: string, items: string[]): { targets: Target[]; refused: Refused[] } {
  const refuse = (list: string[], reason: string, text: string): Refused[] => list.map(item => ({ item, reason, text }))
  if (socket === VIDEO) {                                   // one clip into the Video box, replacing what is there
    const [one, ...more] = items
    if (!m?.video?.reference_video) return { targets: [], refused: refuse(items, 'missing', 'this model takes no reference video') }
    if (clipInBox(d)) return { targets: [], refused: refuse(items, 'clip', 'a continued clip takes no reference video') }
    return { targets: one === undefined ? [] : [{ item: one, socket: VIDEO, index: -1 }], refused: refuse(more, 'one_only', 'one video at a time') }
  }
  if (socket === SOUND) {                                   // one sound into the Sound box, replacing what is there
    const [one, ...more] = items
    if (!m?.video?.soundtrack) return { targets: [], refused: refuse(items, 'missing', 'this model takes no sound') }
    if (clipInBox(d)) return { targets: [], refused: refuse(items, 'clip', 'a continued clip takes no sound') }
    return { targets: one === undefined ? [] : [{ item: one, socket: SOUND, index: -1 }], refused: refuse(more, 'one_only', 'one sound at a time') }
  }
  const clip = clipInBox(d) !== null
  if (clip && (besideClip(m) === 0 || socket === 'reference_1')) return { targets: [], refused: refuse(items, 'clip', CLIP_ONLY_TEXT) }
  const decl = declaration(d, m)
  if (!decl.sockets.some(s => s.id === socket || s.group === socket)) {
    return { targets: [], refused: refuse(items, 'missing', 'this model takes no images there') }
  }
  const [first, ...rest] = items
  if (first === undefined) return { targets: [], refused: [] }
  const cap = clip ? besideClip(m) + 1 : m?.refCap ?? 0
  if (socket === 'reference') {
    const free = Math.max(0, cap - d.references.length)
    const fits = items.slice(0, free)
    const targets = fits.map((item, i) => ({ item, socket: `reference_${d.references.length + i + 1}`, index: d.references.length + i }))
    return { targets, refused: refuse(items.slice(free), 'full', 'references are full') }
  }
  const index = Math.min(Number(socket.replace('reference_', '')) - 1, d.references.length)
  return { targets: [{ item: first, socket: `reference_${index + 1}`, index }], refused: refuse(rest, 'one_only', 'pick one image per slot') }
}
