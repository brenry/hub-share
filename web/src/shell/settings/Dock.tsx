import type { CardInfo } from '../../lib/module'
import { Icon, type IconName } from '../../ui/Icon'
import { StatusDot, type DotKind } from '../../ui/StatusDot'
import { cx } from '../../ui/cx'
import s from './Settings.module.css'

const ICONS: Record<string, IconName> = { network: 'net', assistant: 'chat' }
const DOTS: Record<CardInfo['status'], DotKind> = { ok: 'ok', attention: 'warn', off: 'idle', error: 'err' }
const WORDS: Record<CardInfo['status'], string> = { ok: 'OK', attention: 'Attention', off: 'Off', error: 'Error' }

export function Dock({ cards, open, onOpen }: { cards: CardInfo[]; open: string; onOpen: (id: string) => void }) {
  if (cards.length === 0) return null
  return (
    <nav className={s.dock} aria-label="Cards">
      <div className={cx(s.measure, s.cards)}>
        {cards.map(c => (
          <button key={c.module} type="button" className={cx(s.card, open === c.module && s.cardOn)} aria-pressed={open === c.module}
            onClick={() => onOpen(c.module)} data-card={c.module}>
            <span className={s.cardHead}>
              <Icon name={ICONS[c.module] ?? 'layers'} />
              <b className="ell">{c.title}</b>
              <span className={s.st} title={WORDS[c.status]}><StatusDot kind={DOTS[c.status]} /><span className="visually-hidden">{WORDS[c.status]}</span></span>
              <Icon name="right" small />
            </span>
            <span className={cx(s.sum, 'ell', 'num')}>{c.summary}</span>
          </button>
        ))}
      </div>
    </nav>
  )
}
