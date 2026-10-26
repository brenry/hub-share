// Sending to the open tool's reference slots (the context menu's first line, Enter): one request at a time,
// the tool's delivery answer becomes the toast, no answer within six seconds says so.
import { useEffect, useRef, useState } from 'react'
import { bus } from '../../lib/bus'
import { focus as focusStore, presence } from '../../lib/live'
import type { Delivery } from '../../lib/protocol'
import { useStore } from '../../lib/store'
import { toast } from '../../lib/toast'
import { useBusEvent, useLinkState } from '../../lib/useBus'
import { deliveryText, sendState, soundSend, type SendState, videoSend } from './send'

const WAIT_MS = 6000

export function useSend(n: number, other = false): { state: SendState; send: (ids: string[], socket?: string) => void; label: string; off: string | null; sound: { label: string; off: string | null }; video: { label: string; off: string | null } } {
  const linkOn = useLinkState() === 'on'
  const focus = useStore(focusStore, f => f)
  const p = useStore(presence, v => v)
  const state = sendState(linkOn, focus, p, n)
  const [pending, setPending] = useState<{ id: string; label: string } | null>(null)
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)
  useEffect(() => () => clearTimeout(timer.current), [])
  useBusEvent('delivery', (d, env) => {
    if (!pending || env.re !== pending.id) return
    clearTimeout(timer.current)
    toast(deliveryText(d as Delivery))
    setPending(null)
  })
  /** To the next free reference, or (`socket`) into that one slot, replacing what is there. */
  const send = (ids: string[], socket?: string) => {
    if (!socket && state.kind !== 'enabled') { if (state.kind === 'disabled') toast(state.reason); return }
    if (!focus || pending || ids.length === 0) return
    const target = socket ?? (state.kind === 'enabled' ? state.socket : null)
    if (!target) return
    const id = `snd_${Date.now().toString(36)}${Math.random().toString(36).slice(2, 8)}`
    if (!bus.send('send', { tool: focus.tool, socket: target, items: ids }, id)) return
    setPending({ id, label: focus.label })
    clearTimeout(timer.current)
    timer.current = setTimeout(() => { toast(`No answer from ${focus.label}`); setPending(null) }, WAIT_MS)
  }
  const label = state.kind === 'disabled' ? (n > 1 ? `Add ${n} as references` : 'Add as reference') : state.label
  const off = pending ? 'Sending…' : state.kind === 'disabled' ? state.reason : null
  const put = soundSend(linkOn, focus, p, n, other)                      // `other`: a picture or clip chosen with it
  const shown = videoSend(linkOn, focus, p, n)                           // a clip into the Video box
  return { state, send, label, off, sound: { label: put.label, off: pending ? 'Sending…' : put.off },
    video: { label: shown.label, off: pending ? 'Sending…' : shown.off } }
}
