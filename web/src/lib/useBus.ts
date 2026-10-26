import { useEffect, useRef } from 'react'
import { bus, type LinkState } from './bus'
import { useStore } from './store'
import type { Envelope } from './protocol'

export const useLinkState = (): LinkState => useStore(bus.link, l => l.state)

/** Subscribe to one bus message type for the component's lifetime. */
export function useBusEvent(type: string, fn: (d: unknown, env: Envelope) => void): void {
  const ref = useRef(fn)
  ref.current = fn
  useEffect(() => bus.on(type, (d, e) => ref.current(d, e)), [type])
}
