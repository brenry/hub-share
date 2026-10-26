// A sound on the Stage: the browser's own audio player, centred. Nothing is loaded until Play (as a clip):
// `preload="none"`.
import s from './Media.module.css'

/** Mount with `key={src}`. */
/** `verdict`: the words judge's line on the job that made this line, under the player. */
export function Sound({ src, name, verdict }: { src: string; name: string; verdict?: string | null }) {
  return (
    <div className={s.soundStage} data-region="sound">
      <audio className={s.soundPlayer} src={src} controls preload="none" aria-label={name} />
      {verdict && <span className="t-meta" data-region="verdict" title={verdict}>{verdict}</span>}
    </div>
  )
}
