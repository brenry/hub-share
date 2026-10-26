import { useState } from 'react'
import { Button } from '../../ui/Button'
import { Field } from '../../ui/Field'
import { Icon } from '../../ui/Icon'
import { PlateRow, Tag } from '../../ui/Sheet'
import { StatusDot } from '../../ui/StatusDot'
import type { Device } from './types'

type Props = { device: Device; lastScreen: boolean; onRename: (name: string) => void; onRemove: () => void }

export function DeviceRow({ device: d, lastScreen, onRename, onRemove }: Props) {
  const [name, setName] = useState<string | null>(null)
  const [confirm, setConfirm] = useState(false)
  const keep = d.you ? 'This device' : lastScreen ? 'Last screen' : null
  const state = d.connected > 0 ? `Connected · ${d.connected === 1 ? '1 window' : `${d.connected} windows`}` : 'Not connected'
  const commit = () => {
    const n = name?.trim()
    if (n && n !== d.name) onRename(n)
    setName(null)
  }
  const title = name !== null
    ? <Field label="Device name" value={name} onChange={setName} onEnter={commit} onEscape={() => setName(null)} />
    : <>{d.name} {d.you && <Tag tone="accent">This device</Tag>}</>
  return (
    <PlateRow lead={<Icon name="monitor" />} title={title} sub={`${d.addrs.join(', ')} · ${state}`}>
      <StatusDot kind={d.connected > 0 ? 'ok' : 'idle'} />
      {name !== null ? <Button onClick={commit}>Save</Button> : confirm ? <>
        <Button variant="danger" onClick={() => { setConfirm(false); onRemove() }}>Remove {d.name}</Button>
        <Button variant="ghost" onClick={() => setConfirm(false)}>Cancel</Button>
      </> : <>
        <Button variant="ghost" icon="pen" onClick={() => setName(d.name)}>Rename</Button>
        <Button variant="ghost" icon="trash" aria-label={`Remove ${d.name}`} disabled={keep !== null} title={keep ?? undefined} onClick={() => setConfirm(true)} />
      </>}
    </PlateRow>
  )
}
