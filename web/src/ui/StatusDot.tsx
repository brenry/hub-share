import { cx } from './cx'
import s from './StatusDot.module.css'

export type DotKind = 'ok' | 'warn' | 'cut' | 'err' | 'idle'

export function StatusDot({ kind }: { kind: DotKind }) {
  return <span className={cx(s.dot, s[kind])} aria-hidden="true" />
}
