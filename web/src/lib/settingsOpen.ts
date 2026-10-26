// Whether the workspace shows Settings in place of the open tool. The tool's bar opens it (its sliders fold-up); the
// foot that Settings brings closes it.
import { createStore } from './store'

export const settingsOpen = createStore(false)
