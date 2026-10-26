import { useRef, useState } from 'react'
import { copyOrSelect } from '../lib/copy'
import { Button } from './Button'
import type { IconName } from './Icon'
import { Field } from './Field'

/** A read-only value with a Copy button. */
export function CopyField({ label, value, icon }: { label: string; value: string; icon?: IconName }) {
  const ref = useRef<HTMLInputElement>(null)
  const [done, setDone] = useState<'copied' | 'selected' | null>(null)
  const copy = () => {
    void copyOrSelect(value, ref.current).then(r => { setDone(r); setTimeout(() => setDone(null), 1500) })
  }
  return (
    <>
      <Field label={label} value={value} readOnly inputRef={ref} {...(icon ? { icon } : {})} />
      <Button icon="copy" onClick={copy}>{done === 'copied' ? 'Copied' : done === 'selected' ? 'Selected' : 'Copy'}</Button>
    </>
  )
}
