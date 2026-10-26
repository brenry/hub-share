import { useCallback, useEffect, useLayoutEffect, useRef, useState, type KeyboardEvent } from 'react'
import { useStore } from '../../../lib/store'
import { cx } from '../../../ui/cx'
import { draft, edit } from '../draft'
import s from './Article.module.css'

/** A wheel gesture (a notch, or a swipe with its momentum) ends after this long without a wheel event; one gesture
 *  turns one page. */
const GESTURE_MS = 180

/** The assistant's draft as a two-column page, like a magazine: the text fills the left column, then the right; past
 *  both it runs on to a next page. The mouse wheel turns pages anywhere over it (down: next, up: back), as do Page
 *  Up / Page Down and the arrow keys when it has focus. Nothing scrolls and nothing animates; a rewrite starts again
 *  on the first page. The draft is the `draft` setting the assistant writes through the tool server and the only
 *  text Generate renders; it never goes into the prompt box. Clear empties it. The page count and Clear sit in the
 *  lower right corner, the reply column's margin from both edges. A draft the hub wrote from the assistant's shot
 *  carries a thin "shot" in the upper right; Clear makes it a plain draft again. */
export function Article() {
  const text = useStore(draft, d => d.draft)
  const shot = useStore(draft, d => d.shot != null)
  const field = useRef<HTMLElement>(null)
  const flow = useRef<HTMLDivElement>(null)
  const [page, setPage] = useState(0)
  const [view, setView] = useState({ width: 0, pages: 1 })
  const gesture = useRef<{ turned: boolean; timer: ReturnType<typeof setTimeout> | undefined }>({ turned: false, timer: undefined })

  // One page is the window's width plus one gutter; the flow grows sideways by that much per page.
  const measure = useCallback(() => {
    const el = flow.current
    if (!el) return
    const gap = parseFloat(getComputedStyle(el).columnGap) || 0
    const width = el.clientWidth + gap
    const pages = width > 0 ? Math.max(1, Math.round((el.scrollWidth + gap) / width)) : 1
    setView(v => (v.width === width && v.pages === pages ? v : { width, pages }))
    setPage(p => Math.min(p, pages - 1))
  }, [])
  useLayoutEffect(() => { setPage(0) }, [text])
  useLayoutEffect(measure, [text, measure])
  useEffect(() => {
    const ro = new ResizeObserver(measure)
    if (flow.current) ro.observe(flow.current)
    return () => ro.disconnect()
  }, [measure])
  useLayoutEffect(() => {
    if (flow.current) flow.current.style.transform = `translateX(${-page * view.width}px)`
  }, [page, view])

  const turn = useCallback((by: number) => setPage(p => Math.max(0, Math.min(view.pages - 1, p + by))), [view.pages])
  useEffect(() => {
    const el = field.current
    if (!el) return
    const onWheel = (e: WheelEvent) => {
      e.preventDefault()
      const g = gesture.current
      clearTimeout(g.timer)
      g.timer = setTimeout(() => { g.turned = false }, GESTURE_MS)
      const dy = e.deltaMode === 0 ? e.deltaY : e.deltaY * 16
      if (g.turned || Math.abs(dy) < 2) return
      g.turned = true
      turn(dy > 0 ? 1 : -1)
    }
    el.addEventListener('wheel', onWheel, { passive: false })
    return () => el.removeEventListener('wheel', onWheel)
  }, [turn])
  const onKey = (e: KeyboardEvent) => {
    if (e.target !== e.currentTarget) return
    const by = ['PageDown', 'ArrowDown', 'ArrowRight'].includes(e.key) ? 1 : ['PageUp', 'ArrowUp', 'ArrowLeft'].includes(e.key) ? -1 : 0
    if (by) { e.preventDefault(); turn(by) }
  }

  const paras = text.split(/\n\s*\n/).map(p => p.trim()).filter(Boolean)
  return (
    <article className={s.field} ref={field} tabIndex={0} aria-label="Draft" onKeyDown={onKey} data-region="draft" data-wheel="pages">
      {shot && paras.length > 0 && <span className={s.tag} data-region="draft-shot">shot</span>}
      <div className={s.window}>
        <div className={s.flow} ref={flow} data-page={page}>
          {paras.length ? paras.map((p, i) => <p key={i}>{p}</p>) : <p className={s.empty}>The assistant's draft appears here</p>}
        </div>
      </div>
      {paras.length > 0 && (
        <footer className={s.foot} data-region="draft-foot">
          {view.pages > 1 && <span className={cx(s.pages, 'num')} data-region="pages">{page + 1} / {view.pages}</span>}
          <button type="button" className={s.link} onClick={() => edit(d => ({ ...d, draft: '' }))}>Clear</button>
        </footer>
      )}
    </article>
  )
}
