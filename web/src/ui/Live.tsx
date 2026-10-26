import { useEffect, useRef, useState } from 'react'
import { controllerBlip } from '../lib/blips'
import { bus } from '../lib/bus'
import { errorText, sendJSON } from '../lib/http'
import { useStore } from '../lib/store'
import { toast } from '../lib/toast'
import { StatusDot } from './StatusDot'
import { cx } from './cx'
import s from './Live.module.css'

const ARM_MS = 3000

/** The connection light, the same box on every screen's bar. Green and "Live" while the hub answers. While the link
 *  is cut it dims, the light turns amber like the cover's, and a click tries to reconnect right now. While live, a
 *  click arms a restart of the Hub and a second click within three seconds does it (as Settings → Restart does:
 *  the engine reloads; a running image is lost); the light shows "Restart?" meanwhile. A Hub whose process is
 *  gone cannot be started from here; the service on the server does that by itself. */
export function Live({ className }: { className?: string | undefined }) {
  const link = useStore(bus.link, l => l)
  const blip = controllerBlip(link, Date.now())
  const on = link.state === 'on'
  const [armed, setArmed] = useState(false)
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)
  useEffect(() => () => clearTimeout(timer.current), [])
  useEffect(() => { if (!on) setArmed(false) }, [on])
  const click = () => {
    if (!on) { bus.nudge(); return }
    if (!armed) {
      setArmed(true)
      clearTimeout(timer.current)
      timer.current = setTimeout(() => setArmed(false), ARM_MS)
      return
    }
    clearTimeout(timer.current)
    setArmed(false)
    sendJSON<unknown>('POST', '/api/settings/restart', {}).then(() => toast('Restarting the Hub'), e => toast(errorText(e)))
  }
  const title = !on ? `${blip.title} · click to try now` : armed ? 'Click again to restart the Hub' : 'Live · click twice to restart the Hub'
  return (
    <button type="button" className={cx(s.live, !on && s.dim, armed && s.armed, className)} title={title}
      aria-label={!on ? `${blip.title}, reconnect` : armed ? 'Click again to restart the Hub' : 'Live, restart the Hub'} onClick={click}
      data-live data-state={link.state} data-armed={armed ? '' : undefined}>
      <StatusDot kind={armed ? 'warn' : blip.dot} />{armed ? 'Restart?' : 'Live'}
    </button>
  )
}
