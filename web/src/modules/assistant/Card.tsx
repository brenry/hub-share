import { useCallback, useEffect, useState } from 'react'
import { ago } from '../../lib/format'
import { errorText, getJSON, sendJSON } from '../../lib/http'
import type { CardProps } from '../../lib/module'
import { Button } from '../../ui/Button'
import { CopyField } from '../../ui/CopyField'
import { Field } from '../../ui/Field'
import { Icon } from '../../ui/Icon'
import { Select } from '../../ui/Select'
import { Empty, Plate, PlateRow, Row, Section, Tag } from '../../ui/Sheet'
import { Switch } from '../../ui/Switch'
import s from './Assistant.module.css'

type Client = { addr: string; name: string | null; at: number; status: string }
type OpenWebUI = { url: string; model: string; key: boolean; tools: string; keep: number; context: number }
type AssistantInfo = { on: boolean; endpoints: string[]; clients: Client[]; port: number; mcp_key?: string; openwebui: OpenWebUI }

/** Assistant: the Open WebUI the chat box talks to; MCP access on/off, the endpoint and recent clients. */
export default function AssistantCard({ changed }: CardProps) {
  const [info, setInfo] = useState<AssistantInfo | null>(null)
  const [error, setError] = useState<string | null>(null)
  const load = useCallback(() => {
    getJSON<AssistantInfo>('/api/assistant').then(i => { setInfo(i); setError(null) }, e => setError(errorText(e)))
  }, [])
  useEffect(load, [load])
  type Listed = { ok: boolean; text: string; models: string[] }
  const [owui, setOwui] = useState<{ url: string; key: string } | null>(null)
  const edit = owui ?? { url: info?.openwebui.url ?? '', key: '' }
  type Servers = { ok: boolean; text: string; servers: { id: string; name: string }[] }
  const [listed, setListed] = useState<Listed | null>(null)
  const [servers, setServers] = useState<Servers | null>(null)
  const listModels = useCallback(() => {
    setListed(null)
    setServers(null)
    getJSON<Listed>('/api/assistant/openwebui/models').then(r => { setListed(r); setError(null) }, e => setError(errorText(e)))
    getJSON<Servers>('/api/assistant/openwebui/tool-servers').then(setServers, e => setError(errorText(e)))
  }, [])
  useEffect(() => { if (info?.openwebui.key) listModels() }, [info?.openwebui.key, info?.openwebui.url, listModels])
  const saveOwui = () => {
    if (!owui) return
    const changes: Record<string, string> = { url: owui.url }
    if (owui.key) changes.key = owui.key
    sendJSON<unknown>('PATCH', '/api/assistant/openwebui', changes)
      .then(() => { setOwui(null); setError(null); load(); listModels() }, e => setError(errorText(e)))
  }
  const pickModel = (model: string) => {
    sendJSON<unknown>('PATCH', '/api/assistant/openwebui', { model })
      .then(() => { setError(null); load() }, e => setError(errorText(e)))
  }
  const pickTools = (tools: string) => {
    sendJSON<unknown>('PATCH', '/api/assistant/openwebui', { tools })
      .then(() => { setError(null); load() }, e => setError(errorText(e)))
  }
  const [keep, setKeep] = useState<string | null>(null)
  const saveKeep = () => {
    if (keep === null) return
    sendJSON<unknown>('PATCH', '/api/assistant/openwebui', { keep: Number(keep) })
      .then(() => { setKeep(null); setError(null); load() }, e => setError(errorText(e)))
  }
  const [context, setContext] = useState<string | null>(null)
  const saveContext = () => {
    if (context === null) return
    sendJSON<unknown>('PATCH', '/api/assistant/openwebui', { context: Number(context) })
      .then(() => { setContext(null); setError(null); load() }, e => setError(errorText(e)))
  }
  const removeKey = () => {
    sendJSON<unknown>('PATCH', '/api/assistant/openwebui', { key: '' })
      .then(() => { setListed(null); setServers(null); setError(null); load() }, e => setError(errorText(e)))
  }
  const [port, setPort] = useState('')
  const [moved, setMoved] = useState<string | null>(null)
  const savePort = () => {
    const n = Number(port)
    if (!port || !info || n === info.port) return
    sendJSON<{ endpoints: string[] }>('PATCH', '/api/assistant/port', { port: n })
      .then(r => { setMoved(r.endpoints[0] ?? null); setError(null) }, e => setError(errorText(e)))
  }
  // The server shows a key once, when it is made (never in a view): keep that one on screen until the page goes.
  const [madeKey, setMadeKey] = useState<string | null>(null)
  const newKey = () => sendJSON<{ mcp_key: string }>('POST', '/api/assistant/mcp-key', {})
    .then(r => { setMadeKey(r.mcp_key); setError(null); load() }, e => setError(errorText(e)))
  const toggle = (on: boolean) => sendJSON<unknown>('PATCH', '/api/assistant', { on }).then(() => { load(); changed() }, e => setError(errorText(e)))

  if (!info) return <p className="t-meta">{error ?? ''}</p>
  return (
    <div>
      {error && <p className={s.error} role="alert">{error}</p>}
      <Section title="Open WebUI">
        <p className="t-cap">The chat box sends your messages to this Open WebUI and shows its reply. The Hub adds nothing to your words; with a tool server picked, Open WebUI runs the tools.</p>
        <Row label="Address">
          <Field label="Address" value={edit.url} placeholder="http://127.0.0.1:3000"
            onChange={v => setOwui({ ...edit, url: v })} onEnter={saveOwui} />
        </Row>
        <Row label="API key">
          <Field label="API key" type="password" value={edit.key}
            placeholder={info.openwebui.key ? '••••••••••••••••  type a new key to replace it' : 'From Open WebUI: Settings → Account → API keys'}
            onChange={v => setOwui({ ...edit, key: v })} onEnter={saveOwui} />
          <Tag tone={info.openwebui.key ? 'plain' : 'warn'}>{info.openwebui.key ? 'Key saved' : 'No key'}</Tag>
          <Button disabled={!owui} onClick={saveOwui}>Save</Button>
        </Row>
        <Row label="">
          <Button disabled={!!owui || !info.openwebui.key} onClick={listModels}>Test</Button>
          {info.openwebui.key && <Button variant="ghost" small onClick={removeKey}>Remove key</Button>}
          {listed && <Tag tone={listed.ok ? 'plain' : 'warn'}>{listed.text}</Tag>}
          {!listed && info.openwebui.key && <span className="t-cap">Asking Open WebUI…</span>}
        </Row>
        <Row label="Model">
          {listed?.ok ? (
            <Select label="Model" value={info.openwebui.model}
              options={[...(info.openwebui.model && !listed.models.includes(info.openwebui.model)
                ? [{ value: info.openwebui.model, label: `${info.openwebui.model} (not listed)` }] : []),
                ...(info.openwebui.model ? [] : [{ value: '', label: 'Pick a model' }]),
                ...listed.models.map(m => ({ value: m, label: m }))]}
              onChange={pickModel} />
          ) : <span className="t-cap">{info.openwebui.model || 'none'} · the list comes from Open WebUI once the key works</span>}
        </Row>
        <Row label="Tool server">
          {servers ? (
            <Select label="Tool server" value={info.openwebui.tools}
              options={[{ value: '', label: 'None' },
                ...(info.openwebui.tools && !(servers.ok && servers.servers.some(v => v.id === info.openwebui.tools))
                  ? [{ value: info.openwebui.tools, label: `${info.openwebui.tools} (not listed)` }] : []),
                ...(servers.ok ? servers.servers.map(v => ({ value: v.id, label: v.name || v.id })) : [])]}
              onChange={pickTools} />
          ) : <span className="t-cap">{info.openwebui.tools || 'None'} · listed once the key works</span>}
          {servers && !servers.ok && <Tag tone="warn">{servers.text}</Tag>}
        </Row>
        <p className="t-cap">With the Hub tool server picked, the model can make images through the Hub.</p>
        <Row label="Replies kept">
          <Field label="Replies kept" value={keep ?? String(info.openwebui.keep)}
            onChange={v => setKeep(v.replace(/\D/g, ''))} onEnter={saveKeep} />
          <Button disabled={keep === null} onClick={saveKeep}>Save</Button>
        </Row>
        <p className="t-cap">The chat keeps your last messages and their replies, 1 to 20. Older ones are deleted after each reply, here and in Open WebUI, so a small model is not overfilled.</p>
        <Row label="Context length">
          <Field label="Context length" value={context ?? String(info.openwebui.context)}
            onChange={v => setContext(v.replace(/\D/g, ''))} onEnter={saveContext} />
          <Button disabled={context === null} onClick={saveContext}>Save</Button>
        </Row>
        <p className="t-cap">Tokens the model may read; 0 leaves it to Open WebUI.</p>
      </Section>
      <Section title="Access">
        <Row label="Assistant access"><Switch label="Assistant access" on={info.on} onChange={toggle} /><span>{info.on ? 'On' : 'Off'}</span></Row>
      </Section>
      <Section title="Connection">
        {info.endpoints.map((e, i) => <Row key={e} label={i === 0 ? 'Endpoint' : ''}><CopyField label="Endpoint" icon="link" value={e} /></Row>)}
        <Row label="Key">
          <CopyField label="MCP key" icon="lock" value={madeKey ?? info.mcp_key ?? ''} />
          <Button variant="ghost" small onClick={newKey}>New key</Button>
        </Row>
        <p className="t-cap">Open WebUI → Admin → External Tools → Hub → Auth: Bearer → paste this key. Without it, calls to /mcp are refused.</p>
        <Row label="Port">
          <Field label="Port" placeholder={String(info.port)} value={port}
            onChange={v => setPort(v.replace(/\D/g, ''))} onEnter={savePort} />
          <Button disabled={!port || Number(port) === info.port} onClick={savePort}>Save</Button>
        </Row>
        {moved && <p className="t-cap" role="status">Restarting on the new port. The endpoint is now {moved}. Open this page on the new port, and update Open WebUI and HocusPocus Desktop to it.</p>}
      </Section>
      <Section title="Clients">
        {info.clients.length === 0 ? <Empty>No calls</Empty> : (
          <Plate>
            {info.clients.map(c => (
              <PlateRow key={c.addr} lead={<Icon name="link" />} title={c.name ?? c.addr} sub={`${c.addr} · ${ago(Date.now() / 1000 - c.at)}`}>
                <Tag tone={c.status === 'OK' ? 'plain' : 'warn'}>{c.status}</Tag>
              </PlateRow>
            ))}
          </Plate>
        )}
      </Section>
    </div>
  )
}
