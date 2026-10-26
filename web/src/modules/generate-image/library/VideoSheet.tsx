import { useStore } from '../../../lib/store'
import { Select } from '../../../ui/Select'
import { ModelPicker } from '../compose/ModelPicker'
import { draft, edit } from '../draft'
import { withAdvanced, withModel } from '../edits'
import { sheetModel, sheetModels } from '../modelList'
import { Seconds } from '../Seconds'
import type { Model, VideoFacts } from '../types'
import { clipInBox, continuesOf, detailOf, detailOptions, encoderOf, encoderOptions, framesOf, isVideo, refsOf, sizeValue, soundOf, tierOptions } from '../video'
import { SheetFrame } from './LoraList'
import l from './LoraLibrary.module.css'
import s from './VideoSheet.module.css'

type Video = Model & { video: VideoFacts }

/** The offered size tiers (each kept as its megapixels value in the draft); greyed while a clip in box 1 sets the size. */
function Size({ model }: { model: Video }) {
  const d = useStore(draft, v => v)
  return (
    <label className={l.guidance} data-region="video-size"><span>Size</span>
      <Select label="Size" className={l.encoder} value={sizeValue(model.video, d.size)} disabled={clipInBox(d) !== null}
        options={tierOptions(model.video).map(o => ({ value: o.value, label: o.name }))} onChange={v => edit(x => ({ ...x, size: Number(v) }))} />
    </label>
  )
}

/** The clip's length in seconds (kept per model in the draft); continuing a clip, the seconds it adds. */
function Length({ model }: { model: Video }) {
  const d = useStore(draft, v => v)
  return (
    <label className={l.guidance} data-region="seconds"><span>Seconds</span>
      <span className={s.seconds}>
        <Seconds className={s.number} video={model.video} frames={framesOf(d, model)} step={continuesOf(model) && clipInBox(d) !== null}
          put={frames => edit(x => withAdvanced(x, model, { frames }))} sound={soundOf(d, model)?.seconds} />
      </span>
    </label>
  )
}

/** The text encoder variant (kept per model in the draft), for a model that lists variants. */
function Encoder({ model }: { model: Video }) {
  const d = useStore(draft, v => v)
  if ((model.video.text_encoders?.length ?? 0) === 0) return null
  return (
    <label className={l.guidance} data-region="text-encoder"><span>Text encoder</span>
      <Select label="Text encoder" className={l.encoder} value={encoderOf(d, model)} options={encoderOptions(model.video)}
        onChange={text_encoder => edit(x => withAdvanced(x, model, { text_encoder }))} />
    </label>
  )
}

/** The reference detail (kept per model in the draft), for a model whose engine announces the choices. */
function Detail({ model }: { model: Video }) {
  const d = useStore(draft, v => v)
  const refs = refsOf(model)
  if (!refs?.detail) return null
  return (
    <label className={l.guidance} data-region="detail"><span>Detail</span>
      <Select label="Detail" className={l.encoder} value={detailOf(d, model)} options={detailOptions(refs)}
        onChange={detail => edit(x => withAdvanced(x, model, { detail }))} />
    </label>
  )
}

/** The video sheet, raised by the bar's Video button: the video models only, the model's size tier, seconds, text
 *  encoder and detail under it, then its LoRAs. Picture models are on the image sheet (`LoraLibrary.tsx`). */
export function VideoSheet({ models, model }: { models: Model[]; model: Model | null }) {
  const own = sheetModel(model, 'video')
  const video = isVideo(own) ? own : null
  return (
    <SheetFrame label="Video" region="video-sheet" list={own !== null} head={<>
      <ModelPicker models={sheetModels(models, 'video')} model={own} onPick={m => edit(x => withModel(x, m))} />
      {video && <><Size model={video} /><Length model={video} /><Encoder model={video} /><Detail model={video} /></>}
    </>} />
  )
}
