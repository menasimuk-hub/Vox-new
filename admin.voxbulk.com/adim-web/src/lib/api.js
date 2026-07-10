/* global __ADMIN_PROXY_TARGET__ */

import {
  LOGOUT_QUERY,
  LEGACY_LOGOUT_QUERY,
  STORAGE_KEYS,
  clearAllSessionStorage,
  persistPromotedAdminSession,
  readAdminAccessToken,
  readSharedAccessToken,
} from './sessionStorage'

/**
 * Browser → API routing
 * ─────────────────────────────────────────────────────────────────────────────
 * LOCAL DEV (vite `npm run dev`):
 * - Default when VITE_API_BASE_URL is unset: requests use SAME ORIGIN paths (`/auth/...`, `/admin/...`)
 *   which Vite proxies to FastAPI (`vite.config.js` → VITE_PROXY_API_TARGET).
 * - Set `VITE_DEV_API_PROXY=false` only if you must talk directly to FastAPI cross-origin instead.
 *
 * Staging/production `VITE_API_BASE_URL` is always honoured.
 * Loopback `:8000` URLs in development are intentionally treated like “unset”: same-origin proxy (unless `VITE_FORCE_CROSS_ORIGIN_API=true`).
 */

const LOCAL_LOOPBACK_FASTAPI_ORIGINS = new Set(['http://127.0.0.1:8000', 'http://localhost:8000'])

/** Vite sets DEV in dev server; MODE is the reliable fallback if a tool mis-inlines env. */
export function isViteDevelopment() {
  if (typeof import.meta === 'undefined' || !import.meta.env) return false
  if (import.meta.env.DEV === true) return true
  if (import.meta.env.MODE === 'development') return true
  return false
}

export function prefersDevSameOriginProxy() {
  if (!isViteDevelopment()) return false
  const disable = String(import.meta.env?.VITE_DEV_API_PROXY ?? 'true').toLowerCase()
  if (disable === 'false' || disable === '0') return false
  return true
}

function forceCrossOriginApi() {
  return ['true', '1'].includes(String(import.meta?.env?.VITE_FORCE_CROSS_ORIGIN_API ?? '').toLowerCase())
}

/** Public SPA (port 5173) stores `access_token`; legacy handoff used `retover_access_token`. */
export function getSharedJwtFromStorage() {
  return readSharedAccessToken()
}

function isLocalDevHost() {
  if (typeof window === 'undefined') return false
  const h = window.location.hostname
  return h === 'localhost' || h === '127.0.0.1' || h === '::1'
}

function isProductionAdminHost() {
  if (typeof window === 'undefined') return false
  const h = window.location.hostname
  return h === 'admin.voxbulk.com' || h === 'admin.microgreenia.com'
}

/** On production admin host, nginx proxies /api/* → FastAPI (same origin, no CORS). */
function productionAdminUsesApiPrefixProxy() {
  return !isViteDevelopment() && !forceCrossOriginApi() && isProductionAdminHost()
}

/** Browser calls /admin on this origin in local Vite dev, or /api/* on production admin (nginx). */
export function usesSameOriginApiProxy() {
  if (forceCrossOriginApi()) return false
  if (getApiBaseUrl() !== '') return false
  if (isLocalDevHost()) return true
  if (productionAdminUsesApiPrefixProxy()) return true
  return isViteDevelopment() && prefersDevSameOriginProxy()
}

export function getApiBaseUrl() {
  const explicit = String(import.meta?.env?.VITE_API_BASE_URL || import.meta?.env?.VITE_RETOVER_API_BASE_URL || '')
    .trim()
    .replace(/\/+$/, '')
  const dev = isViteDevelopment()
  const hasExplicit = Boolean(explicit)

  const useDevProxyBehaviour =
    dev &&
    prefersDevSameOriginProxy() &&
    !forceCrossOriginApi() &&
    (!hasExplicit ||
      LOCAL_LOOPBACK_FASTAPI_ORIGINS.has(explicit) ||
      (isLocalDevHost() && !LOCAL_LOOPBACK_FASTAPI_ORIGINS.has(explicit)))

  if (useDevProxyBehaviour) return ''

  // Production admin: always same-origin /api/* (ignore baked VITE_API_BASE_URL — avoids CORS).
  if (productionAdminUsesApiPrefixProxy()) return ''

  if (hasExplicit) return explicit

  if (typeof window !== 'undefined') {
    const h = window.location.hostname
    if (h === 'admin.voxbulk.com') return 'https://api.voxbulk.com'
    if (h === 'admin.microgreenia.com') return 'https://api.microgreenia.com'
  }

  if (isLocalDevHost()) return 'http://127.0.0.1:8000'

  return ''
}

/** Path sent to fetch/WebSocket — production admin prefixes /api for nginx proxy. */
export function getApiRequestPath(path) {
  const p = path.startsWith('/') ? path : `/${path}`
  if (productionAdminUsesApiPrefixProxy() && getApiBaseUrl() === '') {
    return `/api${p}`
  }
  return p
}

/** Full URL for browser fetch (origin + optional /api prefix). */
export function resolveApiUrl(path) {
  const base = getApiBaseUrl()
  const reqPath = getApiRequestPath(path)
  if (!base) {
    if (typeof window !== 'undefined') return `${window.location.origin}${reqPath}`
    return reqPath
  }
  return `${base.replace(/\/+$/, '')}${reqPath}`
}

/** WebSocket URL (http→ws) with same routing as resolveApiUrl. */
export function resolveApiWebSocketUrl(path) {
  return resolveApiUrl(path).replace(/^http/i, 'ws')
}

/** Human-readable endpoint for blocking messages (avoid implying cross-origin when using proxy). */
export function describeApiOrigin() {
  const b = getApiBaseUrl()
  if (b) return b
  if (typeof window !== 'undefined') {
    if (productionAdminUsesApiPrefixProxy()) {
      return `${window.location.origin}/api (proxied → FastAPI)`
    }
    return `${window.location.origin} (proxied → FastAPI)`
  }
  return '(unset)'
}

export function getApiMisconfigurationMessage() {
  if (typeof window === 'undefined') return ''
  if (usesSameOriginApiProxy()) return ''
  if (getApiBaseUrl() !== '') return ''
  const h = window.location.hostname
  if (isLocalDevHost()) return ''
  return `This admin host (${h}) requires VITE_API_BASE_URL (absolute URL of the VOXBULK FastAPI origin). Example: https://api.example.com`
}

function joinOriginAndPath(origin, path) {
  return resolveApiUrl(path)
}

/** Injected in dev by vite.config.js `define`; empty in production builds. */
export function getEmbeddedViteProxyTarget() {
  if (typeof __ADMIN_PROXY_TARGET__ === 'undefined') return ''
  try {
    return String(__ADMIN_PROXY_TARGET__ || '').trim()
  } catch {
    return ''
  }
}

function persistPromotedAdminSessionLocal(token) {
  persistPromotedAdminSession(token)
}

function _safeDecodeHashParam(s) {
  if (typeof s !== 'string') return ''
  try {
    return decodeURIComponent(s.replace(/\+/g, '%20'))
  } catch {
    return s
  }
}

/**
 * Read `#access_token=&org_id=&user_id=` after public → admin redirect.
 * Manual parse (split on first `=`) handles JWT safely; then strip hash without
 * wiping `history.state` (React Router relies on it).
 */
export function consumeAdminAuthHandoffFromHash() {
  if (typeof window === 'undefined') return false
  let raw = window.location.hash || ''
  if (!raw || raw.length <= 1) return false
  if (raw.startsWith('#')) raw = raw.slice(1)

  const map = {}
  for (const part of raw.split('&')) {
    if (!part) continue
    const eq = part.indexOf('=')
    if (eq <= 0) continue
    const key = _safeDecodeHashParam(part.slice(0, eq))
    const val = _safeDecodeHashParam(part.slice(eq + 1))
    if (key) map[key] = val
  }

  const access_token = map.access_token
  if (!access_token) return false

  try {
    persistPromotedAdminSessionLocal(access_token)
    if (map.org_id) localStorage.setItem(STORAGE_KEYS.orgId, map.org_id)
    if (map.user_id) localStorage.setItem(STORAGE_KEYS.userId, map.user_id)
  } catch {
    return false
  }

  const cleanPath = `${window.location.pathname}${window.location.search}`
  try {
    window.history.replaceState(window.history.state, '', cleanPath)
  } catch {
    /* ignore */
  }
  return true
}

async function fetchWithTimeout(url, options = {}, timeoutMs = 8000) {
  const timeoutCtl = new AbortController()
  const external = options.signal
  const merged = new AbortController()
  const abortMerged = () => {
    if (!merged.signal.aborted) merged.abort()
  }
  timeoutCtl.signal.addEventListener('abort', abortMerged)
  if (external) {
    if (external.aborted) abortMerged()
    else external.addEventListener('abort', abortMerged)
  }
  const t = window.setTimeout(() => timeoutCtl.abort(), timeoutMs)
  try {
    return await fetch(url, { ...options, signal: merged.signal })
  } finally {
    window.clearTimeout(t)
    timeoutCtl.signal.removeEventListener('abort', abortMerged)
    if (external) external.removeEventListener('abort', abortMerged)
  }
}

export async function probeApiConnectivity(options = {}) {
  if (typeof window === 'undefined') {
    return { ok: false, url: '', error: 'No browser context' }
  }
  const upstreamHint =
    !getApiBaseUrl() && isViteDevelopment()
      ? `Vite proxies browser calls to upstream ${getEmbeddedViteProxyTarget() || 'http://127.0.0.1:8000'} (NODE side).`
      : ''

  const ms = typeof options.timeoutMs === 'number' ? options.timeoutMs : 4500
  const baseUrl = getApiBaseUrl()
  const path = '/health'
  const url = resolveApiUrl(path)

  const ctl = new AbortController()
  const t = window.setTimeout(() => ctl.abort(), ms)
  try {
    const r = await fetch(url, { signal: ctl.signal, method: 'GET', headers: { Accept: 'application/json' } })
    const ct = (r.headers.get('content-type') || '').split(';')[0].trim().toLowerCase()
    const text = await r.text()

    /** @type {Record<string, unknown> | null} */
    let data = null
    try {
      data = text ? JSON.parse(text) : null
    } catch {
      data = null
    }

    if (data?.proxy_error) {
      const pe = /** @type {Record<string, unknown>} */ (data)
      return {
        ok: false,
        url,
        status: r.status,
        proxyTarget: String(pe.proxy_target || ''),
        error: [
          'Vite dev proxy could not reach FastAPI.',
          String(pe.hint || pe.message || 'See terminal [admin-api-proxy] log.'),
          upstreamHint || undefined,
        ]
          .filter(Boolean)
          .join(' '),
      }
    }

    if (!r.ok) {
      return {
        ok: false,
        url,
        status: r.status,
        error: `HTTP ${r.status} ${r.statusText}${text ? ` — ${text.slice(0, 240)}` : ''}`.trim(),
        upstreamHint,
      }
    }

    if (ct && ct !== 'application/json') {
      return {
        ok: false,
        url,
        status: r.status,
        error: `Expected JSON from FastAPI /health but received "${ct}" (probably not proxied — got HTML or another asset).`,
        bodySnippet: text.slice(0, 240),
        upstreamHint,
      }
    }

    if (!data || data.status !== 'ok') {
      return {
        ok: false,
        url,
        status: r.status,
        error: `Unexpected /health payload (want {"status":"ok"}): ${text.slice(0, 280)}`,
        upstreamHint,
      }
    }

    return { ok: true, url, status: r.status }
  } catch (e) {
    const name = e?.name || ''
    const msg = e?.message || String(e)
    let hint = ''
    if (name === 'AbortError' || /aborted/i.test(msg)) {
      hint = ' (timeout — API or proxy hung?)'
    } else if (/failed to fetch|networkerror|load failed/i.test(msg) || name === 'TypeError') {
      hint =
        isViteDevelopment() && !getApiBaseUrl()
          ? ` Browser could not complete request to ${url}. If the dev server is running, check terminal for [admin-api-proxy] ECONNREFUSED. ${upstreamHint}`
          : ' — Likely ECONNREFUSED, wrong host/port, or mixed http/https.'
    }
    return { ok: false, url, error: `${msg}${hint}`, upstreamHint }
  } finally {
    window.clearTimeout(t)
  }
}

export async function checkApiConnectivity(options = {}) {
  const p = await probeApiConnectivity(options)
  return p.ok
}

function networkFailureHelp() {
  if (productionAdminUsesApiPrefixProxy()) {
    return [
      'Production admin (admin.voxbulk.com):',
      '1) Nginx must proxy /api/ → http://127.0.0.1:8000 with Host api.voxbulk.com (see docs/nginx-admin.voxbulk.com.conf).',
      '2) Verify on VPS: curl -s https://admin.voxbulk.com/api/health  →  {"status":"ok"}',
      '3) Remove any old location ^~ /admin proxy — it breaks the admin UI.',
      '4) Rebuild admin after git pull: cd admin.voxbulk.com/adim-web && npm run build && rsync dist/ to /www/wwwroot/admin.voxbulk.com/',
      '5) Sign in at https://voxbulk.com/signin first (platform admin), then open https://admin.voxbulk.com',
      '6) Restart API: cd /www/voxbulk && ./vox.sh restart',
    ].join('\n')
  }
  if (isViteDevelopment() || isLocalDevHost()) {
    const baseEmpty = !getApiBaseUrl()
    return [
      'Local dev fixes:',
      '1) Run `npm run dev:full` from admin.voxbulk.com/adim-web (starts API :8000 + Vite :5174).',
      '2) Open http://localhost:5174 — not :8000.',
      baseEmpty
        ? '3) API calls use /admin, /auth on :5174 — Vite proxies to FastAPI.'
        : '3) Set VITE_API_BASE_URL or unset it to use the Vite proxy.',
      '4) Sign in on http://localhost:5173, then use admin handoff to :5174.',
    ].join('\n')
  }
  return [
    'Check VITE_API_BASE_URL in the admin build and that https://api.voxbulk.com/health responds.',
    'Ensure CORS_ALLOW_ORIGINS on the API includes this site origin.',
  ].join('\n')
}

/** Dedicated admin JWT — never send customer `access_token` to `/admin/*` (wrong tenant → Invalid authentication credentials). */
export function getAdminAccessTokenRaw() {
  return readAdminAccessToken()
}

/** Concurrent apiFetch calls must await the same admin sync (avoid parallel race → empty token). */
let _adminSyncInFlight = null

async function resolveAdminBearerToken() {
  let t = getAdminAccessTokenRaw()
  if (t) return t
  if (typeof window === 'undefined') return ''

  if (_adminSyncInFlight) return _adminSyncInFlight

  _adminSyncInFlight = (async () => {
    try {
      const shared = getSharedJwtFromStorage()
      if (!shared) return ''
      const baseUrl = getApiBaseUrl()
      const r = await fetch(joinOriginAndPath(baseUrl, '/auth/me'), {
        headers: { Authorization: `Bearer ${shared}`, Accept: 'application/json' },
      })
      const text = await r.text()
      const data = text ? safeJson(text) : null
      if (!r.ok) return ''
      if (data?.admin_access || data?.is_superuser) {
        persistPromotedAdminSession(shared)
        return shared
      }
      return ''
    } catch {
      return ''
    } finally {
      _adminSyncInFlight = null
    }
  })()

  return _adminSyncInFlight
}

const DEV_PUBLIC_MARKETING = 'http://localhost:5173'

function defaultPublicAppOrigin() {
  if (typeof window !== 'undefined') {
    const host = window.location.hostname
    if (host === 'admin.voxbulk.com' || host === 'dashboard.voxbulk.com' || host.endsWith('.voxbulk.com')) {
      return 'https://voxbulk.com'
    }
    if (host === 'admin.microgreenia.com' || host === 'dashboard.microgreenia.com' || host.endsWith('.microgreenia.com')) {
      return 'https://microgreenia.com'
    }
  }
  return DEV_PUBLIC_MARKETING
}
/** Admin (5174) and customer dashboard (5175) must never masquerade as marketing home. */
const DEV_NON_MARKETING_PORTS = new Set(['5174', '5175'])

/**
 * If VITE_PUBLIC_APP_URL accidentally points at THIS app (e.g. admin or dashboard port),
 * redirects would loop back into the wrong SPA — force the real public site (:5173).
 */
function sanitizePublicAppOrigin(raw) {
  let base = String(raw || defaultPublicAppOrigin())
    .trim()
    .replace(/\/+$/, '')
  if (!base) return defaultPublicAppOrigin()

  try {
    const u = new URL(base.includes('://') ? base : `http://${base}`)
    const port = String(u.port || (u.protocol === 'https:' ? '443' : '80'))
    const loop = u.hostname === 'localhost' || u.hostname === '127.0.0.1' || u.hostname === '::1'
    if (loop && DEV_NON_MARKETING_PORTS.has(port)) {
      return defaultPublicAppOrigin()
    }
    if (typeof window !== 'undefined' && u.host === window.location.host) {
      return defaultPublicAppOrigin()
    }
    return `${u.origin}`
  } catch {
    return defaultPublicAppOrigin()
  }
}

export function getPublicAppOrigin() {
  return sanitizePublicAppOrigin(import.meta?.env?.VITE_PUBLIC_APP_URL || defaultPublicAppOrigin())
}

/** Public marketing / customer sign-in app home (used after admin logout). */
export function getPublicAppHomeUrl() {
  return `${getPublicAppOrigin()}/`
}

/** After logout, land on public sign-in (works once voxbulk.com nginx proxies :5173). */
export function getPublicLogoutLandingUrl() {
  const u = new URL(`${getPublicAppOrigin()}/`)
  u.searchParams.set(LOGOUT_QUERY, '1')
  return u.toString()
}

/**
 * Resolve whether we have an admin session.
 * - ready: token present (validated when API is reachable)
 * - blocked: authenticated but lacks platform admin access (organisation-only user)
 * - none: no token present / session invalid HTTP
 */
function isTransientNetworkError(err) {
  const msg = err?.message || String(err)
  const name = err?.name || ''
  return (
    name === 'AbortError' ||
    /failed to fetch|networkerror|network request failed|load failed|aborted/i.test(msg) ||
    name === 'TypeError'
  )
}

async function resolveSessionFromToken(token) {
  if (!token) return null
  try {
    const url = joinOriginAndPath(getApiBaseUrl(), '/auth/me')
    const r = await fetchWithTimeout(
      url,
      {
        headers: { Authorization: `Bearer ${token}`, Accept: 'application/json' },
      },
      10000
    )
    const text = await r.text()
    const data = text ? safeJson(text) : null
    if (!r.ok) {
      return {
        status: 'none',
        message:
          r.status === 401 || r.status === 403
            ? 'Session expired or invalid. Sign in again with a platform admin account.'
            : 'Session invalid. Please sign in again.',
      }
    }
    if (data?.admin_access || data?.is_superuser) {
      return { status: 'ready', token, profile: data }
    }
    return {
      status: 'blocked',
      message:
        'This account is signed in as an organisation user only. Platform admin users (Operations / Billing / Templates roles) use the same sign-in URL but must be explicitly provisioned.',
    }
  } catch (e) {
    if (isTransientNetworkError(e)) {
      return { status: 'ready', token, offline: true }
    }
    return { status: 'ready', token, offline: true }
  }
}

export async function ensureAdminSession() {
  const mis = getApiMisconfigurationMessage()
  const storedToken = getAdminAccessTokenRaw() || getSharedJwtFromStorage()
  if (mis) {
    if (storedToken) return { status: 'ready', token: storedToken, offline: true }
    return { status: 'none', message: mis }
  }

  const direct = getAdminAccessTokenRaw()
  if (direct) {
    const session = await resolveSessionFromToken(direct)
    if (session) return session
  }

  const shared = getSharedJwtFromStorage()
  if (!shared) {
    return { status: 'none', message: 'No session found. Sign in as an admin first.' }
  }

  const session = await resolveSessionFromToken(shared)
  if (session?.status === 'ready') {
    persistPromotedAdminSession(shared)
    return session
  }
  return session || { status: 'none', message: 'No session found. Sign in as an admin first.' }
}

function formatApiError(data, status, statusText) {
  const d = data?.detail
  if (typeof d === 'string') return d
  if (d && typeof d === 'object' && !Array.isArray(d)) {
    if (typeof d.message === 'string') {
      const parts = [d.message]
      if (d.provider_error) parts.push(String(d.provider_error))
      if (d.template_name) parts.push(`Template: ${d.template_name}`)
      if (d.status_code) parts.push(`HTTP ${d.status_code}`)
      return parts.join(' — ')
    }
    return JSON.stringify(d)
  }
  if (Array.isArray(d)) {
    return d.map((x) => (x && typeof x === 'object' && x.msg ? x.msg : JSON.stringify(x))).join('; ')
  }
  if (typeof data?.message === 'string') return data.message
  return `${status} ${statusText}`.trim()
}

export async function apiFetch(path, options = {}) {
  const mis = getApiMisconfigurationMessage()
  if (mis) {
    throw new Error(`${mis}\n\n${networkFailureHelp()}`)
  }

  const baseUrl = getApiBaseUrl()
  const joined = joinOriginAndPath(baseUrl, path)

  const headers = new Headers(options.headers || {})
  headers.set('Accept', 'application/json')

  const token = await resolveAdminBearerToken()
  if (!token) {
    throw new Error(
      'No admin session. Sign in on the public app with a platform-admin account first; the console will stash voxbulk_admin_access_token.'
    )
  }
  headers.set('Authorization', `Bearer ${token}`)

  if (options.body != null && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }

  let res
  const timeoutMs = typeof options.timeoutMs === 'number' ? options.timeoutMs : 90000
  const quietNetworkHint = Boolean(options.quietNetworkHint)
  try {
    res = await fetchWithTimeout(joined, { ...options, headers }, timeoutMs)
  } catch (e) {
    const msg = e?.message || String(e)
    const userCancelled = Boolean(options.signal?.aborted)
    const isAbort =
      userCancelled ||
      (typeof e?.name === 'string' && e.name === 'AbortError') ||
      /aborted/i.test(msg)
    const isNet =
      isAbort ||
      /failed to fetch|networkerror|network request failed|load failed/i.test(msg) ||
      (typeof e?.name === 'string' && e.name === 'TypeError')
    const m = (options.method || 'GET').toString().toUpperCase()
    const secs = Math.max(1, Math.round(timeoutMs / 1000))
    const abortMsg = userCancelled
      ? 'Request cancelled'
      : isAbort
        ? `Request timed out after ${secs}s`
        : msg
    const hint = isAbort
      ? quietNetworkHint
        ? `\n(Long-running admin jobs can exceed the browser wait — try again or raise the call timeoutMs.)`
        : `\n(Timed out after ${secs}s. For Meta template sync, wait and refresh; nginx proxy_read_timeout should be ≥300s.)\n(Request was ${m} ${joined})`
      : isNet && !quietNetworkHint
        ? `\n${networkFailureHelp()}\n(Request was ${m} ${joined})`
        : isNet
          ? `\n(Request timed out or could not reach the API. Try again in a moment.)`
          : `\n(Request was ${m} ${joined})`
    const err = new Error(`${abortMsg}.${hint}`)
    err.name = isAbort ? 'AbortError' : e?.name || 'Error'
    err.cause = e
    throw err
  }
  const text = await res.text()
  const data = text ? safeJson(text) : null

  if (!res.ok) {
    const message = formatApiError(data, res.status, res.statusText)
    const err = new Error(message)
    err.status = res.status
    err.data = data
    throw err
  }

  return data
}

export async function apiFetchBlob(path, options = {}) {
  const mis = getApiMisconfigurationMessage()
  if (mis) throw new Error(`${mis}\n\n${networkFailureHelp()}`)

  const joined = joinOriginAndPath(getApiBaseUrl(), path)
  const headers = new Headers(options.headers || {})
  const token = await resolveAdminBearerToken()
  if (!token) throw new Error('No admin session.')
  headers.set('Authorization', `Bearer ${token}`)

  const res = await fetch(joined, { ...options, headers })
  if (!res.ok) {
    const text = await res.text()
    const data = text ? safeJson(text) : null
    throw new Error(formatApiError(data, res.status, res.statusText))
  }
  return res.blob()
}

export async function apiFetchText(path, options = {}) {
  const mis = getApiMisconfigurationMessage()
  if (mis) throw new Error(`${mis}\n\n${networkFailureHelp()}`)

  const joined = joinOriginAndPath(getApiBaseUrl(), path)
  const headers = new Headers(options.headers || {})
  const token = await resolveAdminBearerToken()
  if (!token) throw new Error('No admin session.')
  headers.set('Authorization', `Bearer ${token}`)

  const res = await fetch(joined, { ...options, headers })
  if (!res.ok) {
    const text = await res.text()
    const data = text ? safeJson(text) : null
    throw new Error(formatApiError(data, res.status, res.statusText))
  }
  return res.text()
}

function safeJson(text) {
  try {
    return JSON.parse(text)
  } catch {
    return null
  }
}

/** Multipart upload (e.g. knowledge base .md). Do not set Content-Type — browser sets boundary. */
export async function apiUpload(path, formData, options = {}) {
  const mis = getApiMisconfigurationMessage()
  if (mis) throw new Error(`${mis}\n\n${networkFailureHelp()}`)

  const joined = joinOriginAndPath(getApiBaseUrl(), path)
  const headers = new Headers(options.headers || {})
  const token = await resolveAdminBearerToken()
  if (!token) {
    throw new Error('No admin session. Sign in on the public app with a platform-admin account first.')
  }
  headers.set('Authorization', `Bearer ${token}`)
  headers.set('Accept', 'application/json')

  const res = await fetch(joined, { ...options, method: options.method || 'POST', headers, body: formData })
  const text = await res.text()
  const data = text ? safeJson(text) : null
  if (!res.ok) {
    const err = new Error(formatApiError(data, res.status, res.statusText))
    err.status = res.status
    err.data = data
    throw err
  }
  return data
}

export function adminLogoutRedirect() {
  if (typeof window === 'undefined') return
  try {
    _adminSyncInFlight = null
    clearAllSessionStorage()
  } catch {
    /* ignore */
  }
  const raw = String(import.meta.env.VITE_ADMIN_POST_LOGOUT_URL || '').trim()
  if (raw) {
    window.location.replace(raw)
    return
  }
  window.location.replace(getPublicLogoutLandingUrl())
}
