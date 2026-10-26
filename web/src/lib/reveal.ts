/** Scroll only the nearest named scroller so `el` is visible. The page itself never moves. */
function revealInScroller(el: HTMLElement): void {
  const box = el.closest<HTMLElement>('[data-scroll]')
  if (!box) return
  const b = box.getBoundingClientRect()
  const r = el.getBoundingClientRect()
  if (r.top < b.top) box.scrollTop -= b.top - r.top
  else if (r.bottom > b.bottom) box.scrollTop += r.bottom - b.bottom
}

/** Focus without letting the browser scroll anything, then reveal inside the named scroller. */
export function focusInScroller(el: HTMLElement): void {
  el.focus({ preventScroll: true })
  revealInScroller(el)
}
