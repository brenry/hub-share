import { useEffect, useMemo } from 'react'
import type { CardProps } from '../../lib/module'
import { useStore } from '../../lib/store'
import { Button } from '../../ui/Button'
import { Row, Section } from '../../ui/Sheet'
import { Segmented } from '../../ui/Segmented'
import { Select } from '../../ui/Select'
import { cx } from '../../ui/cx'
import { type Defaults } from './api'
import { ModelPicker } from './compose/ModelPicker'
import { draft, draftReady, edit, loadDraft } from './draft'
import { advancedOf, isDefault, resetAdvanced, withAdvanced } from './edits'
import { defaults, loadModels, modelList, saveDefaults, sheetModels } from './modelList'
import { Seconds } from './Seconds'
import type { Advanced, Model } from './types'
import { clipInBox, continuesOf, framesOf, isVideo, soundOf } from './video'
import s from './Card.module.css'

const randomSeed = (): number => Math.floor(Math.random() * 1e9)
const NOT_SET: Model = { id: '', label: 'Not set', family: '', modes: [], refCap: 0, defaults: { steps: 0, guidance: null }, guidanceKey: null, kind: 'image', video: null }

/** The LoRA column's model picker with "Not set" on top. */
function DefaultPicker({ models, id, onPick }: { models: Model[]; id: string | null; onPick: (id: string | null) => void }) {
  const all = useMemo(() => [NOT_SET, ...models], [models])
  return (
    <div className={s.pick}>
      <ModelPicker models={all} model={models.find(m => m.id === id) ?? NOT_SET} onPick={m => onPick(m.id || null)} />
    </div>
  )
}

/** The default video model: a video model, or Not set. */
function VideoDefault({ models, id, onPick }: { models: Model[]; id: string | null; onPick: (id: string | null) => void }) {
  const options = [{ value: '', label: 'Not set' }, ...sheetModels(models, 'video').map(m => ({ value: m.id, label: m.label }))]
  return <Select label="Default video model" value={id ?? ''} options={options} onChange={v => onPick(v || null)} />
}

/** Generate Image settings: the default models (image models for text and references, a video model for video), then seed, seconds (a video model; its text encoder is on the raised
 *  LoRA sheet) and guidance for the current model (kept per model in the draft).
 *  Model folders and the weight files live under Settings → Image models. */
export default function GenerateCard({ changed }: CardProps) {
  const d = useStore(draft, v => v)
  const ready = useStore(draftReady, v => v)
  const models = useStore(modelList, v => v)
  const defs = useStore(defaults, v => v)
  useEffect(() => {
    if (!ready) void loadDraft()
    void loadModels()
  }, [])
  const model = models?.find(m => m.id === d.model) ?? null
  const images = useMemo(() => sheetModels(models ?? [], 'image').filter(m => m.kind === 'image'), [models])
  const setDefault = (key: keyof Defaults) => (id: string | null) => void saveDefaults({ ...defaults.get(), [key]: id })
  const later = () => setTimeout(changed, 1200)
  const set = (patch: Partial<Advanced>) => { if (model) edit(x => withAdvanced(x, model, patch)); later() }
  const fixSeed = () => set({ seed: { mode: 'fixed', value: randomSeed() } })
  const num = (label: string, value: number, max: number, step: number, put: (v: number) => void) => (
    <input type="number" className={cx(s.number, 'num')} aria-label={label} value={value} min={0} max={max} step={step}
      onChange={e => { const v = Number(e.target.value); if (Number.isFinite(v)) put(Math.min(max, Math.max(0, v))) }} />
  )
  const a = model ? advancedOf(d, model) : null
  return (
    <div>
      <Section title="Default models">
        <Row label="Text to image"><DefaultPicker models={images} id={defs.text} onPick={setDefault('text')} /></Row>
        <Row label="Reference to image"><DefaultPicker models={images} id={defs.refs} onPick={setDefault('refs')} /></Row>
        <Row label="Video"><VideoDefault models={models ?? []} id={defs.video} onPick={setDefault('video')} /></Row>
      </Section>
      {model && a && (
        <Section title={model.label}>
          <Row label="Seed">
            <Segmented<'random' | 'fixed'> label="Seed" value={a.seed.mode}
              options={[{ value: 'random', label: 'Random' }, { value: 'fixed', label: 'Fixed' }]}
              onChange={m => (m === 'fixed' ? fixSeed() : set({ seed: { mode: 'random' } }))} />
            {a.seed.mode === 'fixed' && num('Seed value', a.seed.value, 999999999, 1, v => set({ seed: { mode: 'fixed', value: Math.round(v) } }))}
          </Row>
          {isVideo(model) && <Row label="Seconds"><Seconds className={s.number} video={model.video} frames={framesOf(d, model)} step={continuesOf(model) && clipInBox(d) !== null} put={frames => set({ frames })} sound={soundOf(d, model)?.seconds} /></Row>}
          {model.guidanceKey !== null && (
            <Row label="Guidance">{num('Guidance', a.guidance ?? 0, 20, 0.1, g => set({ guidance: Math.round(g * 10) / 10 }))}</Row>
          )}
          {!isDefault(a, model) && <Row label=""><Button variant="ghost" onClick={() => { edit(x => resetAdvanced(x, model)); later() }}>Reset to model defaults</Button></Row>}
        </Section>
      )}
    </div>
  )
}
