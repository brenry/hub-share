// A clip's tile: its still frame (lib/stills.ts), never a player. Until the still is made the tile shows its own
// background. `at` is the frame's time in seconds.
import { useEffect, useState, type CSSProperties } from 'react'
import { forget, still, stillNow } from '../lib/stills'

type Props = { url: string; at?: number; label?: string | undefined; style?: CSSProperties | undefined }

export function ClipStill({ url, at = 0.1, label, style }: Props) {
  const [src, setSrc] = useState<string | null>(() => stillNow(url, at))
  useEffect(() => {
    let live = true
    setSrc(stillNow(url, at))
    void still(url, at).then(made => { if (live && made) setSrc(made) })
    return () => { live = false; forget(url, at) }
  }, [url, at])
  return src
    ? <img src={src} alt="" aria-label={label} data-clip-still={url} data-at={at} draggable={false} style={style} />
    : <span aria-label={label} data-clip-still={url} data-at={at} data-wait style={style} />
}
