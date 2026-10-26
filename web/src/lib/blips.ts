// Pure: what the connection light says.
import type { Link } from './bus'
import type { DotKind } from '../ui/StatusDot'

type Blip = { key: string; dot: DotKind; name: string; detail: string; title: string }

export function controllerBlip(link: Link, now: number): Blip {
  const base = { key: 'controller', name: 'Live', detail: '' }
  if (link.state === 'on') return { ...base, dot: 'ok', title: 'Connected' }
  if (link.state === 'off') return { ...base, dot: 'idle', detail: 'off', title: 'Switched off' }
  if (link.state === 'unpaired') return { ...base, dot: 'err', detail: 'not paired', title: 'Not paired' }
  const wait = link.nextTry === null ? null : Math.max(0, Math.ceil((link.nextTry - now) / 1000))
  return { ...base, dot: 'cut', detail: 'reconnecting', title: wait === null ? 'Reconnecting' : `Reconnecting, next try in ${wait} s` }
}
