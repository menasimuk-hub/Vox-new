import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'path'
import { fileURLToPath } from 'url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { '@': path.resolve(__dirname, './src') },
  },
  server: {
    host: true,
    port: 5176,
    strictPort: true,
    proxy: {
      '/abuu': { target: 'http://127.0.0.1:8000', changeOrigin: true },
    },
  },
  preview: {
    host: true,
    port: 5176,
    strictPort: true,
    allowedHosts: ['abuu.voxbulk.com', 'restaurant.yallasay.com'],
    proxy: {
      '/abuu': { target: 'http://127.0.0.1:8000', changeOrigin: true },
    },
  },
})
