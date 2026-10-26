import { Suspense, lazy, useCallback, useEffect, useMemo, useState } from 'react'
import { getJSON } from '../../lib/http'
import type { CardInfo } from '../../lib/module'
import { Icon } from '../../ui/Icon'
import { Scroll } from '../../ui/Scroll'
import { cardPanels } from '../registry'
import { CoreList } from './CoreList'
import { Dock } from './Dock'
import s from './Settings.module.css'

/** Settings: the standard list on top, module cards pinned below; a card opens its panel in place. */
export function Settings() {
  const [view, setView] = useState('main')
  const [cards, setCards] = useState<CardInfo[]>([])
  const refresh = useCallback(() => {
    getJSON<CardInfo[]>('/api/cards').then(setCards, () => {})
  }, [])
  useEffect(refresh, [refresh])
  const shown = useMemo(() => cards.filter(c => c.module in cardPanels).sort((a, b) => a.order - b.order), [cards])
  const panels = useMemo(() => Object.fromEntries(Object.entries(cardPanels).map(([id, load]) => [id, lazy(load)])), [])
  const card = shown.find(c => c.module === view)
  const Panel = card ? panels[card.module] : undefined

  return (
    <div className={s.settings} data-region="settings">
      <Scroll name={card ? card.module : 'settings'} className={s.page} key={view}>
        <div className={s.measure}>
          <header className={s.head}>
            {card
              ? <button type="button" className={s.tile} aria-label="Back to Settings" onClick={() => setView('main')}><Icon name="left" /></button>
              : <span className={s.tile} aria-hidden="true"><Icon name="sliders" /></span>}
            <h1 className={`t-head ${s.crumb}`}>
              {card ? <><button type="button" className={s.up} onClick={() => setView('main')}>Settings</button><Icon name="right" small />{card.title}</> : 'Settings'}
            </h1>
          </header>
          {Panel ? <Suspense fallback={null}><Panel changed={refresh} /></Suspense> : <CoreList />}
        </div>
      </Scroll>
      <Dock cards={shown} open={view} onOpen={id => setView(v => (v === id ? 'main' : id))} />
    </div>
  )
}
