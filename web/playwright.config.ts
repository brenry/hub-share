import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: 'tests/e2e',
  workers: 1,
  timeout: 60_000,
  reporter: [['list']],
  ...(process.env.SHOTS ? {} : { grepInvert: /@shots?\b/ }),
  use: { baseURL: 'http://127.0.0.1:4173', browserName: 'chromium', viewport: { width: 1920, height: 1080 } },
  webServer: { command: 'npm run preview', url: 'http://127.0.0.1:4173', reuseExistingServer: true },
})
