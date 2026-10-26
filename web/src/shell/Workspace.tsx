import { Suspense, lazy, useEffect, useMemo, useState } from 'react'
import { bus } from '../lib/bus'
import { tools } from '../lib/live'
import { settingsOpen } from '../lib/settingsOpen'
import { useStore } from '../lib/store'
import { Icon } from '../ui/Icon'
import { Live } from '../ui/Live'
import { Frame } from './Frame'
import { TopBar } from './TopBar'
import { modules } from './registry'
import { Settings } from './settings/Settings'
import s from './Workspace.module.css'

/** The "/" screen: tool tabs plus Settings. The visible tool is reported as the focus. The open tool carries its own
 *  bar (Live, the instances, the fold-up that opens Settings, Generate); Settings brings a slim foot to close it. */
export default function Workspace() {
  const known = useStore(tools, t => t)
  const tabs = useMemo(() => (known ? modules.filter(m => known.some(t => t.id === m.id)) : modules), [known])
  const [active, setActive] = useState(modules[0]?.id ?? '')
  const settings = useStore(settingsOpen, v => v)
  const setSettings = (v: boolean) => settingsOpen.set(v)
  const panels = useMemo(() => Object.fromEntries(modules.map(m => [m.id, lazy(m.load)])), [])

  useEffect(() => {
    if (!active) return
    bus.focus(active)
    const onFocus = () => bus.focus(active)
    window.addEventListener('focus', onFocus)
    return () => window.removeEventListener('focus', onFocus)
  }, [active])

  const bar = <TopBar tabs={tabs} active={active} settings={settings} onTab={id => { setActive(id); setSettings(false) }} />
  // Settings brings its own foot; so does a window with no tool to show (the tool's bar is the usual way in).
  const bare = !settings && tabs.length === 0
  const foot = settings || bare ? <>
    <span className={s.grow} />
    <Live />
    <button type="button" className={s.close} aria-label={settings ? 'Close Settings' : 'Settings'} title={settings ? 'Close Settings' : 'Settings'}
      onClick={() => setSettings(!settings)} data-region="settings-close"><Icon name="sliders" small /></button>
  </> : undefined
  return (
    <Frame bar={bar} foot={foot}>
      {tabs.map(m => {
        const Panel = panels[m.id]!
        const visible = !settings && m.id === active
        return (
          <section key={m.id} id={`panel-${m.id}`} role="tabpanel" aria-labelledby={`tab-${m.id}`} hidden={!visible} className={s.panel}>
            <Suspense fallback={null}><Panel visible={visible} /></Suspense>
          </section>
        )
      })}
      {settings && <Settings />}
    </Frame>
  )
}
