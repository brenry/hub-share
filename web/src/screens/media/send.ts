// Pure: Smart Send's state, menu and toasts, from the active tool's declared sockets.
import type { Delivery, Focus, Presence, SocketDecl } from '../../lib/protocol'

export type MenuItem = { label: string; socket: string; reason: string | null }
export type SendState =
  | { kind: 'enabled'; label: string; socket: string; menu: MenuItem[] }
  | { kind: 'pick'; label: string; menu: MenuItem[] }
  | { kind: 'disabled'; reason: string; menu: MenuItem[] }

const refNo = (id: string): number => Number(id.replace('reference_', ''))

function menuOf(sockets: SocketDecl[], n: number): MenuItem[] {
  return sockets.map(s => ({
    label: `${s.filled ? 'Replace' : 'Put in'} ${s.label}`, socket: s.id, reason: n > 1 ? 'Pick one image to place in a specific slot' : null,
  }))
}

export function sendState(linkOn: boolean, focus: Focus | null, presence: Presence | null, n: number): SendState {
  const menu = focus ? menuOf(focus.sockets, n) : []
  const off = (reason: string, keepMenu = false): SendState => ({ kind: 'disabled', reason, menu: keepMenu ? menu : [] })
  if (!linkOn) return off('Reconnecting…')
  if (n === 0) return off('Select an image')
  if (!focus) return off('No tool is open')
  if (presence && presence.screens.workspace === 0) return off(`${focus.label} is offline`)
  if (focus.sockets.length === 0) return off('This model takes no images')
  if (focus.primary === 'reference') {
    const refs = focus.sockets.filter(s => s.group === 'reference')
    const free = refs.filter(s => !s.filled).length
    if (free === 0) return off(`References are full (${refs.length} of ${refs.length})`, true)
    const label = n === 1 ? 'Add as reference' : n <= free ? `Add ${n} as references` : `Add ${free} of ${n} as references`
    return { kind: 'enabled', label, socket: 'reference', menu }
  }
  return { kind: 'pick', label: `Send to ${focus.label}…`, menu }
}

/** Media's Put in Sound: one sound into the Sound box of the pulldown's model, from any screen. Its label and
 *  why it is off, or null. */
export function soundSend(linkOn: boolean, focus: Focus | null, presence: Presence | null, n: number, other: boolean): { label: string; off: string | null } {
  const box = focus?.sockets.find(s => s.id === 'sound')
  const label = box?.filled ? 'Replace Sound' : 'Put in Sound'
  const off = !linkOn ? 'Reconnecting…' : other || n !== 1 ? 'One sound at a time' : !focus ? 'No tool is open'
    : presence && presence.screens.workspace === 0 ? `${focus.label} is offline` : box ? null : 'This model takes no sound'
  return { label, off }
}

/** Media's Put in Video: one clip into the Video box of the pulldown's model, as Put in Sound. Its label and
 *  why it is off, or null. */
export function videoSend(linkOn: boolean, focus: Focus | null, presence: Presence | null, n: number): { label: string; off: string | null } {
  const box = focus?.sockets.find(s => s.id === 'video')
  const label = box?.filled ? 'Replace Video' : 'Put in Video'
  const off = !linkOn ? 'Reconnecting…' : n !== 1 ? 'One clip at a time' : !focus ? 'No tool is open'
    : presence && presence.screens.workspace === 0 ? `${focus.label} is offline` : box ? null : 'This model takes no reference video'
  return { label, off }
}

/** The toast for a delivery result. */
export function deliveryText(d: Delivery): string {
  if (d.status === 'failed') return d.reason === 'timeout' ? d.text : `Not delivered: ${d.text}`
  const p = d.placed.length
  const r = d.refused.length
  if (p === 0) return `Not delivered: ${d.refused[0]?.text ?? 'nothing was placed'}`
  if (r > 0) return `${p} added · ${r} not added: ${d.refused[0]!.text}`
  const first = d.placed[0]!
  if (p === 1 && first.socket === 'sound') return `Added to ${d.toolLabel} · Sound`
  if (p === 1 && first.socket === 'video') return `Added to ${d.toolLabel} · Video`
  if (p === 1) return `Added to ${d.toolLabel} · Reference ${refNo(first.socket)}`
  const nums = d.placed.map(x => refNo(x.socket)).sort((a, b) => a - b)
  return `${p} added to ${d.toolLabel} · References ${nums[0]}–${nums[nums.length - 1]}`
}
