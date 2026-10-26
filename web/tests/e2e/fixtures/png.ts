// Tiny PNG encoder for fixture images (no binary files in the repo).
import { crc32, deflateSync } from 'node:zlib'

function chunk(type: string, data: Buffer): Buffer {
  const len = Buffer.alloc(4)
  len.writeUInt32BE(data.length)
  const td = Buffer.concat([Buffer.from(type, 'ascii'), data])
  const crc = Buffer.alloc(4)
  crc.writeUInt32BE(crc32(td) >>> 0)
  return Buffer.concat([len, td, crc])
}

const cache = new Map<string, Buffer>()

/** A w × h gradient between two RGB colours. */
export function png(w: number, h: number, a: [number, number, number], b: [number, number, number]): Buffer {
  const key = `${w}x${h}:${a}:${b}`
  const hit = cache.get(key)
  if (hit) return hit
  const raw = Buffer.alloc((w * 3 + 1) * h)
  for (let y = 0; y < h; y++) {
    const row = y * (w * 3 + 1)
    for (let x = 0; x < w; x++) {
      const t = (x / w + y / h) / 2
      const o = row + 1 + x * 3
      raw[o] = Math.round(a[0] + (b[0] - a[0]) * t)
      raw[o + 1] = Math.round(a[1] + (b[1] - a[1]) * t)
      raw[o + 2] = Math.round(a[2] + (b[2] - a[2]) * t)
    }
  }
  const ihdr = Buffer.alloc(13)
  ihdr.writeUInt32BE(w, 0)
  ihdr.writeUInt32BE(h, 4)
  ihdr.writeUInt8(8, 8)
  ihdr.writeUInt8(2, 9)
  const out = Buffer.concat([Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]), chunk('IHDR', ihdr), chunk('IDAT', deflateSync(raw)), chunk('IEND', Buffer.alloc(0))])
  cache.set(key, out)
  return out
}

const PALETTE: [number, number, number][] = [[59, 42, 88], [179, 74, 90], [29, 43, 58], [78, 106, 125], [18, 48, 46], [44, 90, 82], [240, 163, 94], [90, 42, 73], [207, 214, 194], [127, 148, 115]]

export const tint = (seed: string): [[number, number, number], [number, number, number]] => {
  let h = 7
  for (const c of seed) h = (h * 31 + c.charCodeAt(0)) >>> 0
  return [PALETTE[h % PALETTE.length]!, PALETTE[(h >>> 4) % PALETTE.length]!]
}
