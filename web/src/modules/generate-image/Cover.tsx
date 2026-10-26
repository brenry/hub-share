import { cx } from '../../ui/cx'
import { loraThumb } from './api'
import type { LoraItem } from './types'
import s from './Cover.module.css'

const PALETTE = ['#5B4A3A', '#3F4E5C', '#4F5A45', '#5C4256', '#3E5552', '#5A5040', '#4A4660', '#5E4A44']

const hash = (t: string): number => [...t].reduce((h, c) => (h * 31 + c.charCodeAt(0)) >>> 0, 7)

const initials = (name: string): string =>
  name.split(/[\s_-]+/).filter(Boolean).slice(0, 2).map(w => w[0]!.toUpperCase()).join('') || '?'

/** The LoRA cover, or stable initials on a muted tile. */
export function Cover({ lora, size, className }: { lora: LoraItem; size: 96 | 336; className?: string | undefined }) {
  const src = loraThumb(lora, size)
  if (src) return <img className={cx(s.cover, className)} src={src} alt="" loading="lazy" decoding="async" width={size} height={size} draggable={false} />
  return (
    <span className={cx(s.cover, s.tile, className)} style={{ background: PALETTE[hash(lora.id) % PALETTE.length] }} aria-hidden="true">
      {initials(lora.name)}
    </span>
  )
}
