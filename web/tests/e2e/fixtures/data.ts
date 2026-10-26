// Deterministic fixture data for the fake controller and API.
import type { Job, JobSummary } from '../../../src/lib/protocol'
import type { LoraItem, Model, VideoFacts } from '../../../src/modules/generate-image/types'

/** MiniMax H3 as the catalog gives it (its `ui_model`): a video model, its text encoders, the two offered tiers (540p, 720p) with the
 *  engine's sizes, frames on 17n+5; box 1 is its start frame, box 2 its last frame (`end`, refCap 2). */
export const H3_VIDEO: VideoFacts = {
  fps: 24, frames: { min: 124, step: 17, max: 345, default: 124 }, steps: 20,
  tiers: [
    { name: '540p', sizes: { '21:9': [1280, 544], '16:9': [960, 544], '9:16': [544, 960], '1:1': [736, 736], '4:3': [736, 544], '3:4': [544, 736], '3:2': [896, 576], '2:3': [576, 896] } },
    { name: '720p', sizes: { '21:9': [1632, 704], '16:9': [1280, 704], '9:16': [704, 1280], '1:1': [704, 704], '4:3': [928, 704], '3:4': [704, 928], '3:2': [1152, 768], '2:3': [768, 1152] } },
  ],
  text_encoders: ['nvfp4_awq', 'gguf_q2_k', 'gguf_q4_k_m', 'int8'], text_encoder_default: 'nvfp4_awq', text_encoders_found: ['nvfp4_awq', 'gguf_q2_k'],
  text_encoder_names: { nvfp4_awq: 'NVFP4 AWQ (Recommended)', gguf_q2_k: 'GGUF Q2_K (Lowest RAM)', gguf_q4_k_m: 'GGUF Q4_K_M', int8: 'Quanto INT8' },
  references: { role: 'start', max: 2, end: true }, continues: true, overlap: 18,
}
/** The engine's detail choices for Omni (Stage 7), in its order and by its labels. */
export const OMNI_DETAIL = { key: 'minimax_h3_reference_detail', choices: [{ value: 'match', label: 'Match output' }, { value: 'max', label: 'Maximum detail' }], default: 'match' }
/** The Omni model (Stages 4, 7): identities in boxes 1 to 3, at least one (it cannot run text only); refCap is the max; its detail
 *  choices. It never continues a clip. */
export const H3_OMNI: VideoFacts = { ...H3_VIDEO, references: { role: 'identity', min: 1, max: 3, detail: OMNI_DETAIL }, continues: false, overlap: null }

export const MODELS: Model[] = [
  { id: 'flux2_klein_9b', label: 'Flux 2 Klein 9B', family: 'Flux 2', modes: ['new', 'refs'], refCap: 3, defaults: { steps: 4, guidance: null }, guidanceKey: null, kind: 'image', video: null },
  { id: 'qwen_image_edit_plus', label: 'Qwen Image Edit Plus', family: 'Qwen', modes: ['refs'], refCap: 2, defaults: { steps: 20, guidance: 4 }, guidanceKey: 'guidance_scale', kind: 'image', video: null },
  { id: 'z_image_turbo', label: 'Z-Image Turbo', family: 'Z-Image', modes: ['new'], refCap: 0, defaults: { steps: 8, guidance: null }, guidanceKey: null, kind: 'image', video: null },
  { id: 'minimax_h3', label: 'MiniMax H3', family: 'MiniMax', modes: ['new', 'refs'], refCap: 2, defaults: { steps: 20, guidance: null }, guidanceKey: null, kind: 'video', video: H3_VIDEO },
  { id: 'minimax_h3_ref2va', label: 'H3 Omni — Pruned', family: 'MiniMax', modes: ['refs'], refCap: 3, defaults: { steps: 20, guidance: null }, guidanceKey: null, kind: 'video', video: H3_OMNI },
]

/** The speech model as `ui_model` gives it: one character's picture in box 1, a typed line; not in MODELS, so
 *  the specs that count the pulldown's models stay as they are; a spec that needs it adds it. */
export const SPEECH: Model = { id: 'minimax_h3_tts_ref2va_pruned', label: 'TTS MiniMax H3 Voice Clone 20B', family: 'Tts', modes: ['refs'], refCap: 1,
  defaults: { steps: null as unknown as number, guidance: null }, guidanceKey: null, kind: 'speech', video: null }   // the hub sends steps null

const GROUPS = ['style', 'photography', 'characters', 'concepts', '']
const WORDS = ['Comic Ink Lineart', 'Anime Cel Shade', 'Paper Cutout', 'Watercolor Wash', 'Neon Noir', 'Realism Engine', 'Golden Hour Portrait', 'Studio Softbox', 'Cinematic Film Grain', 'Identity Edit']

export function makeLoras(n: number, longNames = false): LoraItem[] {
  return Array.from({ length: n }, (_, i) => {
    const base = WORDS[i % WORDS.length]!
    const name = longNames && i % 7 === 0 ? `${base} ${'extended variant '.repeat(7)}`.slice(0, 120) : i < WORDS.length ? base : `${base} ${Math.floor(i / WORDS.length) + 1}`
    const group = GROUPS[i % GROUPS.length]!
    const file = `${name.toLowerCase().replace(/\s+/g, '_').slice(0, 60)}_${i}.safetensors`
    return {
      id: `flux2_klein_9b/${group ? group + '/' : ''}${file}`, name, file,
      fileTriggers: i % 3 === 0 ? [] : [`${base.split(' ')[0]!.toLowerCase()}style`, 'bold outlines'],
      cover: i % 4 === 0 ? null : { url: `c${i}` }, strength: null, defaultStrength: i % 5 === 0 ? 0.8 : 1, addedAt: 1791561600 - i * 86400,
    }
  })
}

export function job(id: string, patch: Partial<Job> = {}): Job {
  return {
    id, tool: 'generate-image', kind: 'image', title: '2 images · Flux 2 Klein 9B', lane: 'image.gpu0', state: 'queued',
    created: 1791561600, started: null, position: 1, cancel_requested: false, progress: null, outputs: [], error: null, ...patch,
  }
}

/** A generate-image job's summary as the hub's build.py writes it (model_id and seeds included). */
export function summary(model_id: string, seeds: number[], patch: Partial<JobSummary> = {}): JobSummary {
  const label = MODELS.find(m => m.id === model_id)?.label ?? model_id
  return { prompt: 'A grey cat in the rain', model: label, model_id, loras: [], width: 1344, height: 768, count: seeds.length, seeds, ...patch }
}

export type FakeItem = { id: string; kind: 'image' | 'clip' | 'sound'; url: string; thumb: string | null; w: number | null; h: number | null; createdAt: number; group: string; fav: boolean
  /** A clip's length from its facts (none when the hub cannot read it). */
  seconds?: number | null }

/** `n` Temp items, newest first; every fifth one is in the "Character 17" group, every seventh in "Group 2". */
export function mediaItems(n: number): FakeItem[] {
  return Array.from({ length: n }, (_, i) => {
    const k = n - i
    const group = k % 5 === 0 ? 'Character 17' : k % 7 === 0 ? 'Group 2' : ''
    const id = `out/2026-10-09/${group ? group + '/' : ''}flux2_klein_9b_${String(k).padStart(4, '0')}.png`
    return {
      id, kind: 'image', url: `/files/${id}`, thumb: `/thumbs/${id}/336`, w: 1680, h: 944, createdAt: 1791561600 - i * 60, group, fav: false,
    }
  })
}

/** `n` clips in the clips root, newest first, two days: as the hub lists them (no thumbnail; the oldest has no size or length). */
export function clipItems(n: number): FakeItem[] {
  return Array.from({ length: n }, (_, i) => {
    const day = i < Math.ceil(n / 2) ? '2026-10-13' : '2026-10-12'
    const id = `clips/${day}/${String(180000 - i * 100).padStart(6, '0')}.mp4`
    const last = i === n - 1
    return { id, kind: 'clip' as const, url: `/files/${id}`, thumb: null, w: last ? null : 960, h: last ? null : 544, seconds: last ? null : 5.17,
      createdAt: 1791561600 - i * 600, group: '', fav: false }
  })
}
