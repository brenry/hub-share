import { useEffect, useState } from 'react'
import { HttpError, sendJSON } from '../../lib/http'
import { PAIR_TEXT, readFragment, stateFor, type PairState } from './pair'
import s from './Pair.module.css'

let started = false

/** /pair: trade the one-time code for this device's cookie, then continue. */
export default function Pair() {
  const [state, setState] = useState<PairState>('working')
  useEffect(() => {
    if (started) return
    started = true
    const { code, next } = readFragment(location.hash, location.origin)
    history.replaceState(null, '', location.pathname)
    if (!code) { setState('bad'); return }
    sendJSON<{ device: string }>('POST', '/api/pair', { code }).then(
      () => { setState('paired'); location.replace(next) },
      e => setState(e instanceof HttpError ? stateFor(e.status) : 'failed'),
    )
  }, [])
  return (
    <main className={s.page}>
      <div className={s.card} role="status">
        <div className={s.mark}><i aria-hidden="true" />Hub</div>
        <p className={state === 'working' || state === 'paired' ? s.ok : s.bad} data-pair={state}>{PAIR_TEXT[state]}</p>
      </div>
    </main>
  )
}
