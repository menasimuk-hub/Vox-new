import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

const API_PROXY_PATHS = [
  '/auth',
  '/dashboard',
  '/organisations',
  '/calls',
  '/billing',
  '/onboarding',
  '/support',
  '/notifications',
  '/whatsapp',
  '/appointments',
  '/branches',
  '/users',
  '/health',
]

function buildApiProxy(target) {
  const entries = Object.fromEntries(API_PROXY_PATHS.map((path) => [path, { target, changeOrigin: true }]))
  return entries
}

// Do not use Vite’s default 5173 — that port is the public marketing app (voxbulk.com/frontend).
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const target = (env.VITE_PROXY_API_TARGET || 'http://127.0.0.1:8000').replace(/\/+$/, '')

  return {
    plugins: [react()],
    server: {
      host: true,
      port: 5175,
      strictPort: true,
      proxy: buildApiProxy(target),
    },
    preview: {
      host: true,
      port: 5175,
      strictPort: true,
      allowedHosts: ['dashboard.voxbulk.com'],
      proxy: buildApiProxy(target),
    },
  }
})
