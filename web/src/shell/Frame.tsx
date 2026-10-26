import type { ReactNode } from 'react'
import { Toasts } from '../ui/Toasts'
import { ConnectionCover, useCover } from './ConnectionCover'
import s from './Frame.module.css'

/** The locked window: an optional bar row and the body, exactly one screen tall, plus an optional foot row.
 *  The bar and body go inert under the connection cover; the foot stays live above it, so the Live box there can
 *  be clicked to reconnect while the cover is up. */
export function Frame({ bar, foot, children }: { bar?: ReactNode; foot?: ReactNode; children: ReactNode }) {
  const cover = useCover()
  return (
    <div className={s.app}>
      <div className={s.frame} inert={cover !== 'none'} data-dim={cover === 'off' ? '' : undefined} data-bare={bar === undefined ? '' : undefined}>
        {bar !== undefined && <header className={s.bar} data-region="topbar">{bar}</header>}
        <div className={s.body}>{children}</div>
      </div>
      {foot !== undefined && <footer className={s.foot} data-region="foot">{foot}</footer>}
      <ConnectionCover cover={cover} />
      <Toasts />
    </div>
  )
}
