/// <reference types="vitest/config" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  build: { assetsInlineLimit: 0, sourcemap: false, modulePreload: { polyfill: false } },
  server: { proxy: { '/api': 'http://127.0.0.1:42010', '/files': 'http://127.0.0.1:42010', '/thumbs': 'http://127.0.0.1:42010', '/bus': { target: 'ws://127.0.0.1:42010', ws: true } } },
  test: { environment: 'node', include: ['tests/unit/**/*.test.ts'] },
})
