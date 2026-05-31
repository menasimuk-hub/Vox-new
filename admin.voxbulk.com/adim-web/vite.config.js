import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

/** @param {string} mode */
function resolveApiProxyTarget(mode) {
  const env = loadEnv(mode, process.cwd(), '')
  return (env.VITE_PROXY_API_TARGET || 'http://127.0.0.1:8000').trim().replace(/\/+$/, '')
}

/**
 * @param {string} target
 * @returns {Record<string, import('vite').ProxyOptions>}
 */
function buildApiProxy(target) {
  const logProxy = ['1', 'true', 'yes'].includes(String(process.env.DEBUG_ADMIN_PROXY || '').toLowerCase())

  const base = /** @type {import('vite').ProxyOptions} */ ({
    target,
    changeOrigin: true,
    secure: false,
    ws: true,
    configure(proxy) {
      proxy.on('error', (err, req, res) => {
        const code = /** @type {NodeJS.ErrnoException} */ (err)?.code || ''
        const msg = err?.message || String(err)
        console.error(`[admin-api-proxy] FAILED → ${target} | ${req?.method || '?'} ${req?.url || ''} | ${code} ${msg}`)

        if (res && typeof res.writeHead === 'function' && !res.headersSent) {
          res.writeHead(502, { 'Content-Type': 'application/json; charset=utf-8' })
          res.end(
            JSON.stringify({
              proxy_error: true,
              errno: code,
              message: msg,
              proxy_target: target,
              attempted_ingress_url: `(browser) → http://localhost:5174${req?.url || ''}`,
              hint:
                code === 'ECONNREFUSED'
                  ? `Nothing accepts HTTP on proxy target ${target}. In admin app folder run: npm run dev:full — or manually: cd voxbulk-api && uvicorn main:app --reload --host 0.0.0.0 --port 8000`
                  : 'See terminal [admin-api-proxy] line for Node-level error.',
            })
          )
        }
      })

      proxy.on('proxyReq', (_proxyReq, req) => {
        if (!logProxy) return
        console.log(`[admin-api-proxy] ${req.method} ${req.url} → ${target}${req.url || ''}`)
      })
    },
  })

  return {
    '/auth': { ...base },
    '/admin': { ...base },
    '/demo': { ...base },
    '/health': { ...base },
    '/public': { ...base },
  }
}

export default defineConfig(({ mode }) => {
  const target = resolveApiProxyTarget(mode)
  console.info(`[admin-vite-config] api proxy entries /auth,/admin,/health → ${target}`)

  const proxy = buildApiProxy(target)

  /** Exposed only for dev-bundle debug copy in api.js (`import.meta.env.DEV`). */
  const defineOverrides =
    mode === 'development'
      ? { __ADMIN_PROXY_TARGET__: JSON.stringify(target) }
      : { __ADMIN_PROXY_TARGET__: JSON.stringify('') }

  return {
    define: defineOverrides,
    plugins: [react()],
    server: {
      // Listen on IPv4 + IPv6 so both http://localhost:5174 and http://127.0.0.1:5174 hit the proxy.
      host: true,
      port: 5174,
      strictPort: true,
      proxy,
    },
    preview: {
      host: true,
      port: 5174,
      strictPort: true,
      allowedHosts: ['admin.voxbulk.com'],
      proxy,
    },
  }
})
