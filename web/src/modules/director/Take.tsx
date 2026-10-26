import { useEffect, useRef, type SyntheticEvent } from 'react'
import type { Take as TakeT } from './api'
import { gainOf, takeLine } from './timeline'
import s from './Scripts.module.css'

/** One audio context for the page, made at the first play (no sound starts before a click); each player's gain
 *  node, made once per element (an element can be a media source only once). */
let context: AudioContext | null = null
const gains = new WeakMap<HTMLMediaElement, GainNode>()

/** The element through a gain node at `gain`, from its first play on; the context resumed each play. */
function route(el: HTMLMediaElement, gain: number): void {
  context ??= new AudioContext()
  let node = gains.get(el)
  if (!node) {
    node = context.createGain()
    context.createMediaElementSource(el).connect(node)
    node.connect(context.destination)
    gains.set(el, node)
  }
  node.gain.value = gain
  void context.resume()
}

/** A selected line's take in the bar: its line, then, for an ok, flagged or failed take whose file is in
 *  Sounds, a player of the whole take file (the lead and tail the measure cut can be heard). The player is
 *  the same element while its take's address is the same (it plays on across a reload), heard at the take's
 *  measured gain, a new gain set on its node. */
export function Take({ take, plannedMs }: { take: TakeT; plannedMs: number }) {
  const line = takeLine(take, plannedMs)
  const play = take.url && take.state !== 'none' && take.state !== 'stale' && take.state !== 'rendering' ? take.url : null
  const gain = gainOf(take)
  const el = useRef<HTMLAudioElement>(null)
  useEffect(() => {
    const node = el.current ? gains.get(el.current) : undefined
    if (node) node.gain.value = gain
  }, [gain, play])
  const onPlay = (e: SyntheticEvent<HTMLAudioElement>) => route(e.currentTarget, gain)
  return <>
    <span className={`${s.take} ell`} data-region="take" title={line}>{line}</span>
    {play ? <audio ref={el} key={play} className={s.takePlay} controls preload="none" src={play} onPlay={onPlay} data-region="take-play" /> : null}
  </>
}
