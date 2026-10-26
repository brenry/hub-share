import { useCallback, useEffect, useState } from 'react'
import { clock } from '../../lib/format'
import { errorText, getJSON, sendJSON } from '../../lib/http'
import type { CardProps } from '../../lib/module'
import { Button } from '../../ui/Button'
import { CopyField } from '../../ui/CopyField'
import { Field } from '../../ui/Field'
import { Icon } from '../../ui/Icon'
import { Empty, Plate, Row, Section } from '../../ui/Sheet'
import { DeviceRow } from './DeviceRow'
import type { NetworkInfo } from './types'
import s from './Network.module.css'

/** Network: this server's address (read-only), paired devices, and new pairing links. */
export default function NetworkCard({ changed }: CardProps) {
  const [info, setInfo] = useState<NetworkInfo | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [name, setName] = useState('')
  const [link, setLink] = useState<{ link: string; expires: number } | null>(null)
  const load = useCallback(() => {
    getJSON<NetworkInfo>('/api/network').then(i => { setInfo(i); setError(null) }, e => setError(errorText(e)))
  }, [])
  useEffect(load, [load])
  const after = () => { load(); changed() }
  const fail = (e: unknown) => setError(errorText(e))
  const pair = () => {
    sendJSON<{ link: string; expires: number }>('POST', '/api/network/pair', { name: name.trim() })
      .then(l => { setLink(l); setName(''); after() }, fail)
  }

  if (!info) return <p className="t-meta">{error ?? ''}</p>
  const pending = info.pairing[0] ?? null
  return (
    <div>
      {error && <p className={s.error} role="alert">{error}</p>}
      <Section title="This server">
        <Row label="Address">
          {info.server.bind.map(b => <span key={b} className={`${s.addr} num`}><Icon name="lock" small />{b}:{info.server.port}</span>)}
        </Row>
      </Section>
      <Section title="Devices">
        {info.devices.length === 0 ? <Empty>No devices</Empty> : (
          <Plate>
            {info.devices.map(d => (
              <DeviceRow key={d.id} device={d} lastScreen={info.devices.length === 1}
                onRename={n => sendJSON('PATCH', `/api/network/devices/${encodeURIComponent(d.id)}`, { name: n }).then(after, fail)}
                onRemove={() => sendJSON('DELETE', `/api/network/devices/${encodeURIComponent(d.id)}`).then(after, fail)} />
            ))}
          </Plate>
        )}
      </Section>
      <Section title="Pair a device">
        <Row label="New device">
          <Field label="Device name" placeholder="Name" value={name} onChange={setName} onEnter={() => { if (name.trim()) pair() }} />
          <Button icon="link" disabled={name.trim() === ''} onClick={pair}>Create link</Button>
        </Row>
        {link && <Row label="Link"><CopyField label="Pairing link" icon="link" value={link.link} /></Row>}
        {(link || pending) && (
          <Row label="Expires"><span className="t-meta num">
            {pending ? `${pending.name} · ${clock(pending.expires)}` : link ? clock(link.expires) : ''}
          </span></Row>
        )}
      </Section>
    </div>
  )
}
