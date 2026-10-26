import { useCallback, useEffect, useState } from 'react'
import { bus } from '../../lib/bus'
import { errorText, getJSON, sendJSON } from '../../lib/http'
import { gb } from '../../lib/format'
import { useStore } from '../../lib/store'
import { useBusEvent } from '../../lib/useBus'
import { Button } from '../../ui/Button'
import { Select } from '../../ui/Select'
import { Row, Section, Tag } from '../../ui/Sheet'
import { PathRow } from '../../ui/PathField'
import { ImageModels } from './ImageModels'
import { Switch } from '../../ui/Switch'
import { profileOf, tierLocked, toggleTier, type Profile, type VideoTiers } from './coreSettings'
import s from './CoreList.module.css'

type CoreSettings = {
  drive: string
  characters: string
  engine: {
    root: string; python: string; ok: boolean
    profile: Profile; profiles: Choice[]; profile_video: Profile; video_profiles: Choice[]
  }
  video_tiers: VideoTiers
  video_tiers_max: number
  gpus: { name: string; total_mb: number }[]
  vram: { idle_unload: boolean; idle_minutes: number; clip_previews?: boolean }
}

type Choice = { value: Profile; label: string }

const MINUTES = [5, 10, 15, 20, 30, 45, 60, 90, 120]

/** The standard list: the Drive folder (Media's one folder; the Temp is the Hub's own), engine paths, the memory profiles (general, and for video models), the video sizes the size menu offers, the image models (folders, every weight file, the base chosen for a file), hardware, and the idle-unload setting. */
export function CoreList() {
  const [data, setData] = useState<CoreSettings | null>(null)
  const [error, setError] = useState<string | null>(null)
  const version = useStore(bus.link, l => l.version)
  const load = useCallback(() => {
    getJSON<CoreSettings>('/api/settings').then(d => { setData(d); setError(null) }, e => setError(errorText(e)))
  }, [])
  useEffect(load, [load])
  useBusEvent('settings', load)

  const setIdle = (vram: CoreSettings['vram']) => {
    setData(d => (d ? { ...d, vram } : d))
    sendJSON<CoreSettings>('PATCH', '/api/settings', { vram }).then(setData, e => { setError(errorText(e)); load() })
  }

  /** Shown at once; the server's view (or its refusal, and the saved value again) follows. */
  const patch = (shown: (d: CoreSettings) => CoreSettings, body: object) => {
    setData(d => (d ? shown(d) : d))
    sendJSON<CoreSettings>('PATCH', '/api/settings', body).then(setData, e => { setError(errorText(e)); load() })
  }
  const setProfile = (key: 'profile' | 'profile_video', v: string) => {
    const value = profileOf(v)
    patch(d => ({ ...d, engine: { ...d.engine, [key]: value } }), { engine: { [key]: value } })
  }
  const setTier = (name: string, on: boolean) => {
    const offered = toggleTier(data!.video_tiers, name, on)
    patch(d => ({ ...d, video_tiers: { ...d.video_tiers, offered } }), { modules: { 'generate-image': { video_tiers: offered } } })
  }

  /** PATCH one change; the screen keeps the old value and shows the server's line if it is refused. */
  const save = (body: object) => sendJSON<CoreSettings>('PATCH', '/api/settings', body).then(setData)

  const [restarting, setRestarting] = useState(false)
  const restart = () => {
    setRestarting(true)
    sendJSON<unknown>('POST', '/api/settings/restart', {}).catch(e => { setError(errorText(e)); setRestarting(false) })
  }

  if (!data) return <p className="t-meta">{error ?? ''}</p>
  const idle = data.vram
  const tiers = data.video_tiers
  return (
    <div className={s.list}>
      {error && <p className={s.error} role="alert">{error}</p>}
      <Section title="Storage">
        <PathRow label="Drive" value={data.drive} onSave={v => save({ paths: { drive: v } })} />
        <PathRow label="Characters" value={data.characters} onSave={v => save({ paths: { characters: v } })} />
      </Section>
      <Section title="Image engine">
        <PathRow label="Engine folder" value={data.engine.root} onSave={v => save({ engine: { root: v } })}
          trail={data.engine.ok ? <Tag>Found</Tag> : <Tag tone="err">Not found</Tag>} />
        <PathRow label="Engine Python" icon="term" value={data.engine.python} onSave={v => save({ engine: { python: v } })} />
        <Row label="Memory profile">
          <Select label="Memory profile" className={s.profile} value={String(data.engine.profile)} onChange={v => setProfile('profile', v)}
            options={data.engine.profiles.map(p => ({ value: String(p.value), label: p.label }))} />
          <span className="t-cap">Takes effect at the next engine start</span>
        </Row>
        <Row label="Video models">
          <Select label="Video memory profile" className={s.profile} value={String(data.engine.profile_video)}
            onChange={v => setProfile('profile_video', v)}
            options={data.engine.video_profiles.map(p => ({ value: String(p.value), label: p.label }))} />
        </Row>
        <Row label="Video sizes">
          {tiers.names.length === 0 ? <span className="t-cap">None</span> : (
            <span className={s.tiers}>
              {tiers.names.map(n => (
                <label key={n} className={s.tier} data-tier={n}>
                  <Switch label={n} on={tiers.offered.includes(n)} disabled={tierLocked(tiers, n, data.video_tiers_max)}
                    onChange={on => setTier(n, on)} />
                  <span className="num">{n}</span>
                </label>
              ))}
            </span>
          )}
        </Row>
      </Section>
      <ImageModels />
      <Section title="Hardware">
        <Row label="Clip previews">
          <Switch label="Clip previews" on={idle.clip_previews === true} onChange={on => setIdle({ ...idle, clip_previews: on })} />
          <span className="t-cap">Clip tiles show the clip's first frame. Off: no clip is loaded on any screen until you play it.</span>
        </Row>
        <Row label="Graphics card"><span className="num">{data.gpus.length ? data.gpus.map(g => `${g.name} · ${gb(g.total_mb)} GB`).join(', ') : 'None'}</span></Row>
        <Row label="Unload when idle">
          <Switch label="Unload when idle" on={idle.idle_unload} onChange={on => setIdle({ ...idle, idle_unload: on })} />
          <Select label="Idle minutes" className={s.minutes} value={String(idle.idle_minutes)} disabled={!idle.idle_unload}
            onChange={v => setIdle({ ...idle, idle_minutes: Number(v) })}
            options={(MINUTES.includes(idle.idle_minutes) ? MINUTES : [...MINUTES, idle.idle_minutes].sort((a, b) => a - b))
              .map(m => ({ value: String(m), label: `${m} min` }))} />
        </Row>
      </Section>
      <Section title="About">
        <Row label="Version"><span className="num">{version ? `Hub ${version}` : 'Hub'}</span></Row>
        <Row label="Hub">
          <Button icon="refresh" disabled={restarting} onClick={restart}>{restarting ? 'Restarting…' : 'Restart'}</Button>
          {restarting && <span className="t-cap" role="status">Back in a few seconds; the page reconnects itself.</span>}
        </Row>
      </Section>
    </div>
  )
}
