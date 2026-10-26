// The lock: Ctrl+wheel and Ctrl +/−/0 never zoom the page, so no screen can be pulled out of its layout.
// The one exception is the Media Stage, which zooms its own image with the wheel and owns Ctrl+0 (fit).
const STAGE = '[data-wheel="stage"]'
const inStage = (t: EventTarget | null): boolean => t instanceof Element && t.closest(STAGE) !== null

function onWheel(e: WheelEvent): void {
  if (e.ctrlKey && !inStage(e.target)) e.preventDefault()
}

function onKey(e: KeyboardEvent): void {
  if (!(e.ctrlKey || e.metaKey) || e.altKey) return
  const zoomKey = ['=', '+', '-', '_'].includes(e.key) || ['NumpadAdd', 'NumpadSubtract'].includes(e.code)
  const resetKey = (e.key === '0' || e.code === 'Numpad0') && !document.querySelector(STAGE)
  if (zoomKey || resetKey) e.preventDefault()
}

/** Once per page. The wheel listener must be non-passive: a consumed ctrl+wheel never reaches the zoom handler. */
export function installLock(): void {
  window.addEventListener('wheel', onWheel, { passive: false })
  window.addEventListener('keydown', onKey)
}
