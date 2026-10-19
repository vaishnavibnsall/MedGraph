import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// MedGraph frontend dev server proxies /api to the FastAPI backend.
// Default backend port is 8000; override with VITE_API_TARGET if needed, e.g.:
//   VITE_API_TARGET=http://127.0.0.1:8010 npm run dev
const apiTarget = process.env.VITE_API_TARGET ?? 'http://127.0.0.1:8000'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: apiTarget,
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
  },
})
