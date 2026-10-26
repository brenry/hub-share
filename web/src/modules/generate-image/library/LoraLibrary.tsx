import { ModelPicker } from '../compose/ModelPicker'
import { Guidance } from '../run/Canvas'
import { edit } from '../draft'
import { withModel } from '../edits'
import { sheetModel, sheetModels } from '../modelList'
import type { Model } from '../types'
import { SheetFrame } from './LoraList'
import s from './LoraLibrary.module.css'

/** The image sheet, raised by the bar's fold: the image models (with the model's guidance under it), then its LoRAs; a
 *  speech model is picked here too and has no LoRAs. A video model is on its own sheet (`VideoSheet.tsx`). */
export function LoraLibrary({ models, model }: { models: Model[]; model: Model | null }) {
  const own = sheetModel(model, 'image')
  return (
    <SheetFrame label="LoRA library" region="library" list={own !== null && own.kind === 'image'} head={<>
      <ModelPicker models={sheetModels(models, 'image')} model={own} onPick={m => edit(x => withModel(x, m))} />
      {own?.guidanceKey && <label className={s.guidance}><span>Guidance</span><Guidance model={own} /></label>}
    </>} />
  )
}
