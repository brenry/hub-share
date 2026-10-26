import { dismiss, toasts } from '../lib/toast'
import { useStore } from '../lib/store'
import s from './Toasts.module.css'

/** One polite live region; at most three toasts. */
export function Toasts() {
  const list = useStore(toasts, t => t)
  return (
    <div className={s.stack} role="status" aria-live="polite">
      {list.map(t => (
        <div key={t.id} className={s.toast}>
          <span>{t.text}</span>
          {t.action && <button type="button" className={s.act} onClick={() => { t.action?.run(); dismiss(t.id) }}>{t.action.label}</button>}
        </div>
      ))}
    </div>
  )
}
