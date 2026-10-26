// Fit probes: nothing escapes its column, no text overflows without an ellipsis, a box stays fully on screen.
import type { Page } from '@playwright/test'

/** Problems inside the given column selectors. An element's visible part, clipped only by boxes *inside* its column
 *  (scrollers, inputs, thumbnails), must lie within the column; a box that clips its own text must ellipsize. */
export const fitProblems = (page: Page, columns: string[]) => page.evaluate((cols) => {
  const out: string[] = []
  const name = (el: Element) => `${el.tagName.toLowerCase()}${el.className && typeof el.className === 'string' ? `.${el.className.split(' ')[0]}` : ''}${(el as HTMLElement).dataset?.region ? `[${(el as HTMLElement).dataset.region}]` : ''} "${(el.textContent ?? '').trim().slice(0, 24)}"`
  const vw = innerWidth
  const vh = innerHeight
  const skip = (el: Element) => el.closest('[popover], [data-stage-img], .visually-hidden, textarea, input, select') !== null
  for (const sel of cols) {
    for (const col of document.querySelectorAll<HTMLElement>(sel)) {
      const C = col.getBoundingClientRect()
      if (C.width === 0 || C.height === 0) continue
      if (C.left < -0.5 || C.top < -0.5 || C.right > vw + 0.5 || C.bottom > vh + 0.5) out.push(`${sel} leaves the window`)
      for (const el of col.querySelectorAll('*')) {
        if (skip(el)) continue
        const r = el.getBoundingClientRect()
        if (r.width < 1 || r.height < 1) continue
        let [L, T, R, B] = [r.left, r.top, r.right, r.bottom]
        if (col.hasAttribute('data-scroll')) { T = Math.max(T, C.top); B = Math.min(B, C.bottom) }
        for (let a = el.parentElement; a && a !== col; a = a.parentElement) {
          const cs = getComputedStyle(a)
          const ar = a.getBoundingClientRect()
          if (cs.overflowX !== 'visible') { L = Math.max(L, ar.left); R = Math.min(R, ar.right) }
          if (cs.overflowY !== 'visible') { T = Math.max(T, ar.top); B = Math.min(B, ar.bottom) }
        }
        if (R - L < 1 || B - T < 1) continue
        if (L < C.left - 1 || R > C.right + 1 || T < C.top - 1 || B > C.bottom + 1) {
          out.push(`${name(el)} escapes ${sel} by ${Math.round(Math.max(C.left - L, R - C.right, C.top - T, B - C.bottom))}px`)
        }
        // Exempt: the draft article's pager (descendants of [data-wheel="pages"]): its flow is a deliberately
        // sideways-growing run of columns, clipped by its window and turned a page at a time by a transform, so its
        // window's scrollWidth is the whole draft by design. Its escape (above) is still checked.
        if (el.parentElement?.closest('[data-wheel="pages"]') && !el.closest('footer')) continue
        if (!(el instanceof HTMLElement) || el.hasAttribute('data-scroll') || el.closest('[aria-hidden="true"], [data-wheel="stage"]')) continue
        const cs = getComputedStyle(el)
        const clipsX = cs.overflowX !== 'visible'
        const text = [...el.childNodes].some(n => n.nodeType === 3 && n.textContent!.trim())
        if ((clipsX || text) && el.clientWidth > 0 && el.scrollWidth > el.clientWidth + 1 && cs.textOverflow !== 'ellipsis') {
          if (clipsX && !text && el.querySelector('img, [data-scroll]')) continue
          out.push(`${name(el)} overflows its own box by ${el.scrollWidth - el.clientWidth}px`)
        }
      }
    }
  }
  return [...new Set(out)].slice(0, 20)
}, columns)

/** True when the element's own box is fully on screen and not cut by any ancestor. */
export const fullyVisible = (page: Page, sel: string) => page.locator(sel).first().evaluate(el => {
  const r = el.getBoundingClientRect()
  if (r.left < 0 || r.top < 0 || r.right > innerWidth + 0.5 || r.bottom > innerHeight + 0.5) return false
  for (let a = el.parentElement; a; a = a.parentElement) {
    const cs = getComputedStyle(a)
    const ar = a.getBoundingClientRect()
    if (cs.overflowX !== 'visible' && (r.left < ar.left - 0.5 || r.right > ar.right + 0.5)) return false
    if (cs.overflowY !== 'visible' && (r.top < ar.top - 0.5 || r.bottom > ar.bottom + 0.5)) return false
  }
  return true
})

export const rootPx = (page: Page) => page.evaluate(() => parseFloat(getComputedStyle(document.documentElement).fontSize))

/** The Media window's fixed --ui-scale (base.css). */
export const MEDIA_SCALE = 0.68

/** The root the formula in base.css promises for a viewport and scale. */
export const expectedRoot = (w: number, h: number, scale = 1) =>
  Math.min(30, Math.max(15, 10.25 + Math.min(w * 0.005375, h * 0.009556))) * scale
