import type { ModuleManifest } from '../../lib/module'

export default {
  id: 'sequence',
  label: 'Edit Video',
  order: 20,
  load: () => import('./Sequence'),
} satisfies ModuleManifest
