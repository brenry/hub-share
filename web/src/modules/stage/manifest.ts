import type { ModuleManifest } from '../../lib/module'

export default {
  id: 'stage', label: 'Stage', order: 45, load: () => import('./StageTab'),
} satisfies ModuleManifest
