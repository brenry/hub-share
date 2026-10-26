// The image models whose files are in the model folders, and the default models. Reloaded when the
// picker opens and when Settings change (folders); the server re-checks the folders, so this is cheap.
// A page refresh asks for a full rescan, so files added deep in a folder are found without a restart.
import { createStore } from '../../lib/store'
import { api, type Defaults } from './api'
import type { Model } from './types'

export const modelList = createStore<Model[] | null>(null)
export const defaults = createStore<Defaults>({ text: null, refs: null, video: null })
let latest = 0

export async function loadModels(rescan = false): Promise<void> {
  const n = ++latest
  void loadDefaults()
  try {
    const list = await api.models(rescan)
    if (n === latest) modelList.set(list)
  } catch {
    if (n === latest) modelList.set(m => m ?? [])
  }
}

async function loadDefaults(): Promise<void> {
  try {
    defaults.set(await api.defaults())
  } catch {
    // The last known defaults stay.
  }
}

export async function saveDefaults(next: Defaults): Promise<void> {
  defaults.set(next)
  try {
    defaults.set(await api.saveDefaults(next))
  } catch {
    void loadDefaults()
  }
}

/** Which sheet a model belongs to: the bar's fold raises the image models (a speech model among them: it is picked in
 *  the same pulldown), its Video button the video models. */
export type SheetKind = 'image' | 'video'
export const sheetOf = (m: Model): SheetKind => (m.kind === 'video' ? 'video' : 'image')

/** The models a sheet lists: only its own kind. */
export const sheetModels = (models: readonly Model[], kind: SheetKind): Model[] => models.filter(m => sheetOf(m) === kind)

/** The model a sheet shows: the draft's when it is of the sheet's kind, else none (the picker asks for one). */
export const sheetModel = (model: Model | null, kind: SheetKind): Model | null => (model && sheetOf(model) === kind ? model : null)
