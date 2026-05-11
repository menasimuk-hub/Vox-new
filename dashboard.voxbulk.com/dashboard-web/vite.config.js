import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Do not use Vite’s default 5173 — that port is the public marketing app (voxbulk.com/frontend).
export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5175,
    strictPort: true,
  },
  preview: {
    host: true,
    port: 5175,
    strictPort: true,
  },
})
