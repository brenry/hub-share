// Static guards for the rules that matter.
import { existsSync, readFileSync, readdirSync, statSync } from 'node:fs'
import { join, relative } from 'node:path'
import { describe, expect, it } from 'vitest'

const ROOT = join(__dirname, '..', '..')
const walk = (dir: string): string[] => readdirSync(dir).flatMap(n => {
  const p = join(dir, n)
  return statSync(p).isDirectory() ? walk(p) : [p]
})
const SRC = walk(join(ROOT, 'src')).filter(p => /\.(ts|tsx|css)$/.test(p))
const TESTS = walk(join(ROOT, 'tests')).filter(p => /\.ts$/.test(p))
const read = (p: string) => readFileSync(p, 'utf8')
const rel = (p: string) => relative(ROOT, p)
const CSS = SRC.filter(p => p.endsWith('.css'))
const CODE = SRC.filter(p => /\.tsx?$/.test(p))
// The one allowed absolute URL: the Open WebUI address placeholder in the Assistant card (the server requires http://).
const PLACEHOLDER = 'http://127.0.0.1:3000'
const ROOT_SIZE = '--ui-base: clamp(15px, 10.25px + min(0.5375vw, 0.9556vh), 30px);'

describe('guards', () => {
  it('every source and test file is at most 250 lines', () => {
    const long = [...SRC, ...TESTS].filter(p => read(p).split('\n').length > 250).map(rel)
    expect(long).toEqual([])
  })

  it('overflow: hidden is banned; only [data-scroll] scrolls', () => {
    const hidden = SRC.filter(p => /overflow(-[xy])?\s*:\s*hidden|overflow:\s*['"]hidden/.test(read(p))).map(rel)
    expect(hidden).toEqual([])
    const scrolls = CSS.flatMap(p => [...read(p).matchAll(/([^{}]*)\{[^}]*overflow(-[xy])?\s*:\s*(auto|scroll)/g)].map(m => `${rel(p)}: ${m[1]!.trim()}`))
    expect(scrolls).toEqual(['src/styles/base.css: [data-scroll]'])
  })

  it('html, body, #root and .app clip', () => {
    const base = read(join(ROOT, 'src/styles/base.css'))
    for (const sel of ['html', 'body', '#root']) expect(base).toMatch(new RegExp(`\\n\\s*${sel.replace('#', '\\#')}\\s*\\{[^}]*overflow: clip`))
    expect(read(join(ROOT, 'src/shell/Frame.module.css'))).toMatch(/\.app \{[^}]*overflow: clip/)
  })

  it('the root size is the one fluid clamp times --ui-scale; no other font size is in px', () => {
    const base = read(join(ROOT, 'src/styles/base.css'))
    expect(base).toContain(ROOT_SIZE)
    const px = CSS.flatMap(p => read(p).replace(ROOT_SIZE, '').split('\n')
      .filter(l => /font(-size)?\s*:[^;]*\d+(\.\d+)?px/.test(l)).map(l => `${rel(p)}: ${l.trim()}`))
    const inline = CODE.filter(p => /fontSize\s*:/.test(read(p))).map(rel)
    expect([...px, ...inline]).toEqual([])
  })

  it('every size is in rem: px appears only for 1 px hairlines', () => {
    const bad = CSS.flatMap(p => read(p).replace(ROOT_SIZE, '').split('\n')
      .filter(l => /(?<![\w-])(?!1px|0px)\d+(\.\d+)?px/.test(l)).map(l => `${rel(p)}: ${l.trim()}`))
    expect(bad).toEqual([])
  })

  it('no banned copy: explanatory sentences, safety text or directive hints', () => {
    const banned = [/nothing is logged/i, /a fact, not a setting/i, /never downloads/i, /no address is fixed/i, /detected/i,
      /changes save as you make them/i, /nsfw/i, /safety/i, /saved with the lora/i, /drop an image, or/i, /select a lora to see/i,
      /generations appear here/i, /never typed in/i, /read-only: the hub/i, /copy it now/i]
    const hits = CODE.flatMap(p => banned.filter(re => re.test(read(p))).map(re => `${rel(p)}: ${re}`))
    expect(hits).toEqual([])
  })

  it('no source file sets a maxLength', () => {
    expect(SRC.filter(p => /maxLength/.test(read(p))).map(rel)).toEqual([])
  })

  it('no console, no storage, no absolute URLs in source', () => {
    const hits = CODE.flatMap(p => {
      const s = read(p).replaceAll(PLACEHOLDER, '')
      return [/console\./, /localStorage|sessionStorage/, /https?:\/\//].filter(re => re.test(s)).map(re => `${rel(p)}: ${re}`)
    })
    expect(hits).toEqual([])
  })

  it('modules import only react, ui/, lib/ and their own folder', () => {
    const bad = CODE.filter(p => rel(p).startsWith('src/modules/')).flatMap(p => {
      const own = rel(p).split('/')[2]
      return [...read(p).matchAll(/from '([^']+)'/g)].map(m => m[1]!).filter(spec => {
        if (spec === 'react' || spec.startsWith('react/') || spec.startsWith('./') || spec.endsWith('.css')) return false
        const target = relative(join(ROOT, 'src'), join(p, '..', spec)).split('/')
        return !(target[0] === 'ui' || target[0] === 'lib' || (target[0] === 'modules' && target[1] === own))
      }).map(spec => `${rel(p)}: ${spec}`)
    })
    expect(bad).toEqual([])
  })

  it('the build makes no external requests', () => {
    const dist = join(ROOT, 'dist')
    if (!existsSync(dist)) return
    const files = walk(dist).filter(p => /\.(js|css|html)$/.test(p))
    const urls = files.flatMap(p => [...read(p).replaceAll(PLACEHOLDER, '').matchAll(/https?:\/\/[^\s"'`)]+/g)].map(m => m[0]))
      .filter(u => !u.startsWith('https://react.dev/errors') && !u.startsWith('http://www.w3.org/'))
    expect(urls).toEqual([])
    const html = read(join(dist, 'index.html'))
    expect(html).not.toMatch(/(src|href)="(https?:)?\/\//)
  })
})
