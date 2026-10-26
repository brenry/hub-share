import type { KeyboardEvent } from 'react'
import { cx } from '../ui/cx'
import type { ModuleManifest } from '../lib/module'
import s from './TopBar.module.css'

type Props = {
  tabs: ModuleManifest[]
  active: string
  settings: boolean
  onTab: (id: string) => void
}

/** The tool tabs. Settings is not a tool: the open tool's bar opens it (its sliders fold-up). */
export function TopBar({ tabs, active, settings, onTab }: Props) {
  const onKey = (e: KeyboardEvent, i: number) => {
    const n = e.key === 'ArrowRight' ? i + 1 : e.key === 'ArrowLeft' ? i - 1 : e.key === 'Home' ? 0 : e.key === 'End' ? tabs.length - 1 : null
    const t = n === null ? undefined : tabs[(n + tabs.length) % tabs.length]
    if (!t) return
    e.preventDefault()
    onTab(t.id)
    document.getElementById(`tab-${t.id}`)?.focus({ preventScroll: true })
  }
  return (
    <div className={s.bar}>
      <div role="tablist" aria-label="Tools" className={s.tabs}>
        {tabs.map((t, i) => {
          const on = !settings && t.id === active
          return (
            <button key={t.id} id={`tab-${t.id}`} type="button" role="tab" aria-selected={on} aria-controls={`panel-${t.id}`}
              tabIndex={t.id === active ? 0 : -1} className={cx(s.tab, on && s.on)} onClick={() => onTab(t.id)} onKeyDown={e => onKey(e, i)}>
              {t.label}
            </button>
          )
        })}
      </div>
    </div>
  )
}
