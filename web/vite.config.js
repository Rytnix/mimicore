import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// FastAPI runs on :8000 — proxy /api (REST) and /api/**/transcribe + /stream (WS).
export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        ws: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
})
