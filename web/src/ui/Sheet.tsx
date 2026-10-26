// Layout for Settings pages: a section name column, then rows; plates group entities.
import type { ReactNode } from 'react'
import { cx } from './cx'
import s from './Sheet.module.css'

export function Section({ title, aside, children }: { title: string; aside?: ReactNode; children: ReactNode }) {
  return (
    <section className={s.sec} aria-label={title}>
      <div className={s.name}>
        <h2 className="t-label">{title}</h2>
        {aside}
      </div>
      <div className={s.body}>{children}</div>
    </section>
  )
}

export function Row({ label, children, trail }: { label: string; children: ReactNode; trail?: ReactNode }) {
  return (
    <div className={s.row}>
      <span className={s.label}>{label}</span>
      <div className={s.cell}>{children}</div>
      <div className={s.trail}>{trail}</div>
    </div>
  )
}

export function Plate({ children, className }: { children: ReactNode; className?: string | undefined }) {
  return <div className={cx(s.plate, className)}>{children}</div>
}

export function PlateRow({ lead, title, sub, children }: { lead?: ReactNode; title: ReactNode; sub?: ReactNode; children?: ReactNode }) {
  return (
    <div className={s.prow}>
      <span className={s.lead}>{lead}</span>
      <div className={s.main}>
        <div className={cx(s.title, 'ell')}>{title}</div>
        {sub && <div className={cx('t-meta', 'ell', 'num')}>{sub}</div>}
      </div>
      <div className={s.acts}>{children}</div>
    </div>
  )
}

export function Tag({ children, tone = 'plain' }: { children: ReactNode; tone?: 'plain' | 'accent' | 'warn' | 'err' }) {
  return <span className={cx(s.tag, tone !== 'plain' && s[tone])}>{children}</span>
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className={s.empty}>{children}</p>
}
