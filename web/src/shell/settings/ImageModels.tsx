import { useCallback, useEffect, useState } from 'react'
import { errorText, getJSON, sendJSON } from '../../lib/http'
import { useBusEvent } from '../../lib/useBus'
import { draft } from '../../modules/generate-image/draft'
import { loadLoras } from '../../modules/generate-image/loras'
import { loadModels } from '../../modules/generate-image/modelList'
import { Button } from '../../ui/Button'
import { FolderList } from '../../ui/PathField'
import { Section } from '../../ui/Sheet'
import s from './ImageModels.module.css'

type Folders = { image_model_folders: string[]; helper_folders?: string[]; lora_folders: string[]; video_lora_folders?: string[] }

const WEIGHTS = '/api/generate-image/weights'

/** The model pulldown and the LoRA library follow what the folders hold now. */
function refreshScreen(): void {
  void loadModels().then(() => { const id = draft.get().model; if (id) void loadLoras(id) })
}

/** Image models: the model folders, by what they hold, and Rescan. Every model file in the model folders shows in
 *  Generate's pulldown under its own name; nothing here copies or moves a file. */
export function ImageModels() {
  const [folders, setFolders] = useState<Folders | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const loadFolders = useCallback(() => {
    getJSON<Folders>('/api/settings').then(f => { setFolders(f); setError(null) }, e => setError(errorText(e)))
  }, [])
  useEffect(() => { loadFolders() }, [loadFolders])
  useBusEvent('settings', () => { loadFolders() })

  const saveFolders = (body: object) =>
    sendJSON<Folders>('PATCH', '/api/settings', body).then(f => { setFolders(f); refreshScreen() })
  const rescan = () => {
    setBusy(true)
    sendJSON('POST', `${WEIGHTS}/rescan`, {}).then(() => { setError(null); refreshScreen() }, e => setError(errorText(e)))
      .finally(() => setBusy(false))
  }
  return (
    <Section title="Image models" aside={<Button icon="refresh" small disabled={busy} onClick={rescan}>{busy ? 'Scanning…' : 'Rescan'}</Button>}>
      {error && <p className={s.error} role="alert">{error}</p>}
      {folders && <>
        <FolderList label="Model folders" name="Model folder" paths={folders.image_model_folders} onSave={f => saveFolders({ engine: { model_folders: f } })} />
        <FolderList label="VAE folders" name="VAE or text encoder folder" paths={folders.helper_folders ?? []} onSave={f => saveFolders({ engine: { helper_folders: f } })} />
        <FolderList label="LoRA folders" name="LoRA folder" paths={folders.lora_folders} onSave={f => saveFolders({ modules: { loras: { folders: f } } })} />
        <FolderList label="Video LoRA" name="Video LoRA folder" paths={folders.video_lora_folders ?? []} onSave={f => saveFolders({ modules: { director: { video_lora_folders: f } } })} />
      </>}
    </Section>
  )
}
