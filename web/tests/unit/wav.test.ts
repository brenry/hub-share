// An mp3 or wav file made the WAV the Hub keeps — the header, 16-bit samples, two channels at most,
// whole, and the one line shown for a file that is not a sound, cannot be read, or is under 2 s; one
// dropped on an Edit Video track: whole at 48 kHz, up to 10 minutes.
import { describe, expect, it } from 'vitest'
import { NOT_SEQ_SOUND, NOT_SOUND, RATE, SEQ_RATE, TOO_LONG, TOO_SHORT, UNREAD, encodeWav, isSoundFile, toSequenceWav, toVoiceWav, type Decoder } from '../../src/lib/wav'

const decoded = (seconds: number, channels: number, value = 0.5, rate = RATE) => {
  const length = Math.round(seconds * rate)
  const planes = Array.from({ length: channels }, (_, c) => new Float32Array(length).fill(c ? -value : value))
  return { numberOfChannels: channels, length, sampleRate: rate, getChannelData: (c: number) => planes[c]! }
}
const decoder = (d: ReturnType<typeof decoded>): Decoder => async () => d
const file = (name: string, type = '') => new File([new Uint8Array(8)], name, { type })
const text = (b: Uint8Array, at: number) => String.fromCharCode(...b.slice(at, at + 4))

describe('the voice sample WAV', () => {
  it('is RIFF/WAVE with fmt (PCM 16-bit) and data, nothing else', () => {
    const { bytes, cut } = encodeWav(decoded(3, 2))
    const v = new DataView(bytes.buffer)
    expect([text(bytes, 0), text(bytes, 8), text(bytes, 12), text(bytes, 36)]).toEqual(['RIFF', 'WAVE', 'fmt ', 'data'])
    expect([v.getUint16(20, true), v.getUint16(22, true), v.getUint32(24, true), v.getUint16(34, true)]).toEqual([1, 2, RATE, 16])
    expect(v.getUint32(28, true)).toBe(RATE * 4)
    expect(v.getUint32(40, true)).toBe(3 * RATE * 4)
    expect(v.getUint32(4, true)).toBe(bytes.length - 8)
    expect([v.getInt16(44, true), v.getInt16(46, true)]).toEqual([Math.trunc(0.5 * 0x7fff), -0x4000])
    expect(cut).toBe(false)
  })

  it('keeps the whole sound and two channels at most; mono stays mono; loud samples are clipped', () => {
    const long = encodeWav(decoded(40, 3))
    const v = new DataView(long.bytes.buffer)
    expect(long.cut).toBe(false)
    expect(v.getUint16(22, true)).toBe(2)
    expect(v.getUint32(40, true)).toBe(40 * RATE * 4)
    const mono = encodeWav(decoded(2, 1, 3))
    const m = new DataView(mono.bytes.buffer)
    expect(m.getUint16(22, true)).toBe(1)
    expect(m.getInt16(44, true)).toBe(0x7fff)
  })

  it('takes an mp3 or wav by name or type, and refuses anything else, unreadable or under 2 s', async () => {
    expect([isSoundFile(file('Character 8.MP3')), isSoundFile(file('k.wav')), isSoundFile(file('k', 'audio/mpeg')), isSoundFile(file('k.png', 'image/png'))])
      .toEqual([true, true, true, false])
    await expect(toVoiceWav(file('k.png', 'image/png'), decoder(decoded(3, 1)))).rejects.toThrow(NOT_SOUND)
    await expect(toVoiceWav(file('k.mp3'), async () => { throw new Error('EncodingError') })).rejects.toThrow(UNREAD)
    await expect(toVoiceWav(file('k.mp3'), decoder(decoded(1.9, 2)))).rejects.toThrow(TOO_SHORT)
    const ok = await toVoiceWav(file('k.mp3'), decoder(decoded(20, 2)))
    expect(ok.blob.type).toBe('audio/wav')
    expect(ok.blob.size).toBe(44 + 20 * RATE * 4)
  })
})

describe('a recording for an Edit Video track', () => {
  it('is kept whole at 48 kHz up to 10 minutes; anything else is refused by its line', async () => {
    const ok = await toSequenceWav(file('long.mp3'), decoder(decoded(40, 2, 0.5, SEQ_RATE)))
    expect(ok.seconds).toBe(40)
    expect(ok.blob.size).toBe(44 + 40 * SEQ_RATE * 4)
    const head = new DataView(await ok.blob.slice(0, 44).arrayBuffer())
    expect(head.getUint32(24, true)).toBe(SEQ_RATE)
    await expect(toSequenceWav(file('k.mp4', 'video/mp4'), decoder(decoded(3, 1)))).rejects.toThrow(NOT_SEQ_SOUND)
    await expect(toSequenceWav(file('k.mp3'), async () => { throw new Error('EncodingError') })).rejects.toThrow(UNREAD)
    await expect(toSequenceWav(file('k.mp3'), decoder(decoded(601, 1, 0.5, 1000)))).rejects.toThrow(TOO_LONG)
  })
})
