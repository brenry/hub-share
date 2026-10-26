import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { cx } from './cx'
import s from './Menu.module.css'

export type SubItem = { label: string; run: () => void }
export type MenuItem =
  | { label: string; icon?: ReactNode; key?: string; danger?: boolean; off?: string | null; run: () => void; sub?: SubItem[] }
  | { sep: true }
/** Where the menu opens: at the pointer, or (`up`) above a bar button whose top edge is `y`. */
export type MenuAt = { x: number; y: number; up?: boolean }

/** The enabled items of one menu, at any depth of wrapper, leaving out those of a fold-out list inside it. */
const enabled = (menu: HTMLElement | null) => [...menu?.querySelectorAll<HTMLButtonElement>('[role=menuitem]:not(:disabled)') ?? []].filter(b => b.closest('[role=menu]') === menu)

type Props = { at: MenuAt | null; items: MenuItem[]; onClose: () => void; label: string; row?: boolean }

/** A right-click menu at the pointer: the page's own, so the window's Copy / Select All one stays out of the way.
 *  Escape, a click anywhere else, a scroll or the window losing focus closes it. `off` keeps an item visible but
 *  explains why it cannot run. An item with `sub` folds a second list out to its left on hover (or ArrowLeft).
 *  `row` draws the items as a line of icons (the label is the tooltip), for a bar button's fold-up. */
export function Menu({ at, items, onClose, label, row = false }: Props) {
  const box = useRef<HTMLDivElement>(null)
  const [pos, setPos] = useState<MenuAt | null>(null)
  useLayoutEffect(() => {
    const el = box.current
    if (!at || !el) { setPos(null); return }
    const r = el.getBoundingClientRect()
    const y = at.up ? at.y - r.height - 6 : at.y
    setPos({ x: Math.max(0, Math.min(at.x, window.innerWidth - r.width - 4)), y: Math.max(0, Math.min(y, window.innerHeight - r.height - 4)) })
  }, [at])
  useEffect(() => { if (pos && box.current) enabled(box.current)[0]?.focus() }, [pos])
  useEffect(() => {
    if (!at) return
    const down = (e: PointerEvent) => { if (!box.current?.contains(e.target as Node)) onClose() }
    const key = (e: KeyboardEvent) => {
      if (e.key === 'Escape') { e.stopPropagation(); onClose(); return }
      const here = document.activeElement as HTMLElement | null
      if (e.key === 'ArrowLeft' && here?.dataset.hasSub) { here.parentElement?.querySelector<HTMLButtonElement>('[data-sub] button')?.focus(); e.preventDefault(); return }
      if (e.key === 'ArrowRight' && here?.closest('[data-sub]')) { here.closest('[data-sub]')?.parentElement?.querySelector<HTMLButtonElement>('[data-has-sub]')?.focus(); e.preventDefault(); return }
      const next = row ? 'ArrowRight' : 'ArrowDown', prev = row ? 'ArrowLeft' : 'ArrowUp'
      if (e.key !== next && e.key !== prev) return
      const all = enabled(here?.closest<HTMLElement>('[role=menu]') ?? box.current)
      const i = all.indexOf(here as HTMLButtonElement)
      all[(i + (e.key === next ? 1 : all.length - 1)) % all.length]?.focus()
      e.preventDefault()
    }
    window.addEventListener('pointerdown', down, true)
    window.addEventListener('keydown', key, true)
    window.addEventListener('blur', onClose)
    window.addEventListener('scroll', onClose, true)
    window.addEventListener('resize', onClose)
    return () => {
      window.removeEventListener('pointerdown', down, true)
      window.removeEventListener('keydown', key, true)
      window.removeEventListener('blur', onClose)
      window.removeEventListener('scroll', onClose, true)
      window.removeEventListener('resize', onClose)
    }
  }, [at, onClose, row])
  if (!at) return null
  return createPortal(
    <div ref={box} role="menu" aria-label={label} aria-orientation={row ? 'horizontal' : 'vertical'} className={cx(s.menu, row && s.row)} data-region="menu"
      style={{ left: pos?.x ?? at.x, top: pos?.y ?? at.y, visibility: pos ? 'visible' : 'hidden' }} onContextMenu={e => e.preventDefault()}>
      {items.map((it, i) => {
        if ('sep' in it) return <hr key={i} className={s.sep} />
        if (row) {
          return (
            <button key={i} type="button" role="menuitem" className={s.iconItem} disabled={Boolean(it.off)} title={it.off ?? it.label} aria-label={it.label}
              onClick={() => { onClose(); it.run() }}>{it.icon}</button>
          )
        }
        const button = (
          <button type="button" role="menuitem" className={cx(s.item, it.danger && s.danger)} disabled={Boolean(it.off)} title={it.off ?? undefined}
            aria-haspopup={it.sub ? 'menu' : undefined} data-has-sub={it.sub ? '1' : undefined} onClick={() => { onClose(); it.run() }}>
            <span className={s.icon} aria-hidden="true">{it.icon}</span>
            <span className={s.text}>{it.label}</span>
            {it.key && <kbd className={s.key}>{it.key}</kbd>}
          </button>
        )
        if (!it.sub || it.off) return <span key={i} className={s.slot}>{button}</span>
        return (
          <div key={i} className={cx(s.slot, s.hasSub)}>
            {button}
            <div role="menu" aria-label={it.label} className={cx(s.menu, s.sub)} data-sub>
              {it.sub.map((x, j) => (
                <button key={j} type="button" role="menuitem" className={s.item} onClick={() => { onClose(); x.run() }}>
                  <span className={s.text}>{x.label}</span>
                </button>))}
            </div>
          </div>
        )
      })}
    </div>,
    document.body)
}
