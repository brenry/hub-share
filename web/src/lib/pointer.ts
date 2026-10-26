// A press followed until let go (Edit Video's edge trim, the Storyboard's box drag): the element captures the pointer,
// `move` hears its sideways travel in px on each move, `done` the last travel once, on release or cancel.
type Press = { currentTarget: Element; pointerId: number; clientX: number }

export function follow(e: Press, move: (dx: number) => void, done: (dx: number) => void): void {
  const el = e.currentTarget
  const x0 = e.clientX
  let dx = 0
  el.setPointerCapture?.(e.pointerId)
  const on = (ev: Event) => {
    dx = (ev as PointerEvent).clientX - x0
    move(dx)
  }
  const up = () => {
    el.removeEventListener('pointermove', on)
    el.removeEventListener('pointerup', up)
    el.removeEventListener('pointercancel', up)
    done(dx)
  }
  el.addEventListener('pointermove', on)
  el.addEventListener('pointerup', up)
  el.addEventListener('pointercancel', up)
}
