// Continue a clip: the hub puts it in box 1 and the draft on a model that continues it (Media's Continue, or a clip
// dropped on a box). Every window redraws from the draft the hub saved.
import { errorText } from '../../lib/http'
import { api } from './api'

/** Null when the clip is in box 1; otherwise the reason it is not. */
export const continueClip = (id: string): Promise<string | null> => api.continueClip(id).then(() => null, e => errorText(e))
