// GET /api/network (`hub/core/admin.py` `NetworkAdmin.view`).
export type Device = {
  id: string
  name: string
  addrs: string[]
  connected: number
  you: boolean
}

export type NetworkInfo = {
  server: { bind: string[]; port: number }
  devices: Device[]
  pairing: { name: string; expires: number }[]
}
