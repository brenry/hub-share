import type { HTMLAttributes, Ref } from 'react'

/** The only way to get a scrolling box. Everything else clips. */
export function Scroll({ name, ref, ...rest }: HTMLAttributes<HTMLDivElement> & { name: string; ref?: Ref<HTMLDivElement> }) {
  return <div data-scroll={name} ref={ref} {...rest} />
}
