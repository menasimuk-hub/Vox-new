import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5177,
    strictPort: true,
    proxy: {
      '/abuu': { target: 'http://127.0.0.1:8000', changeOrigin: true },
    },
  },
  preview: {
    host: true,
    port: 5177,
    strictPort: true,
    allowedHosts: ['driver.voxbulk.com'],
    proxy: {
      '/abuu': { target: 'http://127.0.0.1:8000', changeOrigin: true },
    },
  },
})
