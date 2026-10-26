// Settings → Model files: each model's parts that name a file, and the files in the model folders to point them at.
import type { Route } from '@playwright/test'
import type { Listing, Part } from '../../../src/shell/settings/ModelFiles'

const CKPTS = '/srv/apps/pinokio-data/api/wan.git/app/ckpts'
const COMFY = '/srv/models/ComfyUI/models'
const part = (p: string, label: string, name: string, path: string | null): Part => ({ part: p, label, name, path, chosen: false })

export function modelFiles(): Listing {
  return {
    models: [
      { id: 'minimax_h3_fl2va_pruned', name: 'MiniMax H3 FL2VA Pruned', kind: 'video', parts: [
        part('URLs', 'Main weights', 'MiniMax-H3-FL2VA-pruned_rank8_bf16.safetensors', `${CKPTS}/MiniMax-H3-FL2VA-pruned_rank8_bf16.safetensors`),
        part('text_encoder_URLs', 'Text encoder', 'Qwen3-VL-32B-Instruct-layer50_nvfp4_awq.safetensors', `${CKPTS}/Qwen3-VL-32B-Instruct-layer50/Qwen3-VL-32B-Instruct-layer50_nvfp4_awq.safetensors`),
        part('video_vae_file', 'Video VAE', 'minimax_h3_video_vae_int8_convrot.safetensors', null),
        part('audio_vae_file', 'Audio VAE', 'minimax_h3_audio_vae.safetensors', `${CKPTS}/minimax_h3_audio_vae.safetensors`),
      ] },
      { id: 'krea2_turbo_edit', name: 'Krea 2 Turbo Edit', kind: 'image', parts: [
        part('URLs', 'Main weights', 'krea2_turbo_edit_bf16.safetensors', `${CKPTS}/krea2_turbo_edit_bf16.safetensors`),
        part('preload_URLs:0', 'Extra file: Qwen2.5-VL-7B-Instruct_vision_bf16.safetensors', 'Qwen2.5-VL-7B-Instruct_vision_bf16.safetensors', null),
        part('loras:0', 'Model LoRA: krea2_turbo_lora.safetensors', 'krea2_turbo_lora.safetensors', null),
      ] },
    ],
    files: [`${COMFY}/vae/h3_video_vae_int8_comfy.safetensors`, `${COMFY}/clip_vision/qwen25_vl_7b_vision.safetensors`],
    loras: [`${COMFY}/loras/krea2/turbo.safetensors`],
  }
}

const json = (route: Route, body: unknown, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })
const was = new Map<string, Part>()

/** Like the controller: an absolute path to a weight file; null puts the engine's own back. */
export function modelFilesRoute(route: Route, st: { modelFiles: Listing }, method: string, body: unknown) {
  if (method !== 'PUT') return json(route, st.modelFiles)
  const { model, part: name, path } = body as { model: string; part: string; path: string | null }
  const p = st.modelFiles.models.find(m => m.id === model)?.parts.find(x => x.part === name)
  if (!p) return json(route, { code: 'invalid', field: 'part', text: `${model} has no part ${name}` }, 400)
  if (path !== null && !(path.startsWith('/') && path.endsWith('.safetensors') && !path.includes('missing')))
    return json(route, { code: 'invalid', field: 'path', text: 'Not a weight file on this computer (an absolute path to a .safetensors, .gguf or like file)' }, 400)
  const key = `${model}/${name}`
  if (!was.has(key)) was.set(key, { ...p })
  Object.assign(p, path === null ? { ...was.get(key) } : { path, name: path.split('/').pop(), chosen: true })
  return json(route, st.modelFiles)
}
