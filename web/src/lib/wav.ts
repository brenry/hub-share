/** A recording (an mp3 or wav file picked or dropped in the browser) made the voice sample the Hub keeps:
 *  decoded here, in the browser, at the 32 kHz the speech model resamples to, its first two channels, whole (the
 *  Hub cuts nothing), written as 16-bit PCM WAV (`fmt ` and `data` only). The file is only read.
 *  Dropped on an Edit Video track it is decoded at 48 kHz and kept whole, up to 10 minutes. */

export const RATE = 32_000
export const MIN_SECONDS = 2
export const NOT_SOUND = 'A voice sample is an mp3 or wav file'
export const UNREAD = 'That sound file could not be read'
export const TOO_SHORT = 'A voice sample is at least 2 seconds'
export const SEQ_RATE = 48_000
export const SEQ_MAX_SECONDS = 600
export const NOT_SEQ_SOUND = 'From your computer, drop an mp3 or wav'
export const TOO_LONG = 'A recording up to 10 minutes'

type Decoded = { numberOfChannels: number; length: number; sampleRate: number; getChannelData(c: number): Float32Array }
export type Decoder = (raw: ArrayBuffer) => Promise<Decoded>

const TYPES = new Set(['audio/mpeg', 'audio/mp3', 'audio/wav', 'audio/x-wav', 'audio/wave', 'audio/vnd.wave'])

export const isSoundFile = (f: { name: string; type: string }): boolean =>
  /\.(mp3|wav)$/i.test(f.name) || TYPES.has(f.type.toLowerCase())

const decoderAt = (rate: number): Decoder => raw => new OfflineAudioContext(1, 1, rate).decodeAudioData(raw)
const browserDecoder = decoderAt(RATE)

/** 16-bit PCM WAV of the first two channels of `audio`, whole, or its first `maxSeconds` when given. */
export function encodeWav(audio: Decoded, maxSeconds: number = Infinity): { bytes: Uint8Array; cut: boolean } {
  const channels = Math.min(audio.numberOfChannels, 2)
  const frames = Math.min(audio.length, Math.round(maxSeconds * audio.sampleRate))
  const data = frames * channels * 2
  const out = new DataView(new ArrayBuffer(44 + data))
  const tag = (at: number, s: string) => { for (let i = 0; i < 4; i++) out.setUint8(at + i, s.charCodeAt(i)) }
  tag(0, 'RIFF'); out.setUint32(4, 36 + data, true); tag(8, 'WAVE')
  tag(12, 'fmt '); out.setUint32(16, 16, true); out.setUint16(20, 1, true); out.setUint16(22, channels, true)
  out.setUint32(24, audio.sampleRate, true); out.setUint32(28, audio.sampleRate * channels * 2, true)
  out.setUint16(32, channels * 2, true); out.setUint16(34, 16, true)
  tag(36, 'data'); out.setUint32(40, data, true)
  const planes = Array.from({ length: channels }, (_, c) => audio.getChannelData(c))
  let at = 44
  for (let i = 0; i < frames; i++) {
    for (const plane of planes) {
      const v = Math.max(-1, Math.min(1, plane[i] ?? 0))
      out.setInt16(at, v < 0 ? v * 0x8000 : v * 0x7fff, true)
      at += 2
    }
  }
  return { bytes: new Uint8Array(out.buffer), cut: audio.length > frames }
}

/** The file as the WAV the Hub keeps, whole. Throws with the one line shown on screen. */
export async function toVoiceWav(file: File, decode: Decoder = browserDecoder): Promise<{ blob: Blob }> {
  if (!isSoundFile(file)) throw new Error(NOT_SOUND)
  let audio: Decoded
  try {
    audio = await decode(await file.arrayBuffer())
  } catch {
    throw new Error(UNREAD)
  }
  if (!audio.numberOfChannels || audio.length / audio.sampleRate < MIN_SECONDS) {
    if (!audio.numberOfChannels) throw new Error(UNREAD)
    throw new Error(TOO_SHORT)
  }
  const { bytes } = encodeWav(audio)
  return { blob: new Blob([bytes as BlobPart], { type: 'audio/wav' }) }
}

/** The file as a WAV for an Edit Video track: whole, at 48 kHz; `seconds` its length. Throws with the line shown. */
export async function toSequenceWav(file: File, decode: Decoder = decoderAt(SEQ_RATE)): Promise<{ blob: Blob; seconds: number }> {
  if (!isSoundFile(file)) throw new Error(NOT_SEQ_SOUND)
  let audio: Decoded
  try {
    audio = await decode(await file.arrayBuffer())
  } catch {
    throw new Error(UNREAD)
  }
  if (!audio.numberOfChannels || audio.length === 0) throw new Error(UNREAD)
  const seconds = audio.length / audio.sampleRate
  if (seconds > SEQ_MAX_SECONDS) throw new Error(TOO_LONG)
  const { bytes } = encodeWav(audio, SEQ_MAX_SECONDS)
  return { blob: new Blob([bytes as BlobPart], { type: 'audio/wav' }), seconds }
}
