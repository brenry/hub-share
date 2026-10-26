import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: 'tests/full',
  workers: 1,
  timeout: 120_000,
  reporter: [['list']],
  use: { browserName: 'chromium' },
})
