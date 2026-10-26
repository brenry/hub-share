import type { ModuleManifest } from '../../lib/module'

export default {
  id: 'casting', label: 'Casting', order: 40, load: () => import('./Casting'),
} satisfies ModuleManifest
