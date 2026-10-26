import type { ModuleManifest } from '../../lib/module'

export default {
  id: 'generate-image',
  label: 'Generate Image',
  order: 10,
  load: () => import('./GenerateImage'),
  queue: () => import('./queue').then(m => m.queue()),
  randomSeed: () => import('./api').then(m => m.api.randomSeed()),
  continueClip: (id: string) => import('./continue').then(m => m.continueClip(id)),
} satisfies ModuleManifest
