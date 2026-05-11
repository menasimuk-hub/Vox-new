/* global __ADMIN_PROXY_TARGET__ */

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

/** Public SPA (port 5173) stores `access_token`; older handoff used `retover_access_token` — read both on this origin. */
export function getSharedJwtFromStorage() {
  if (typeof window === 'undefined') return ''
  return localStorage.getItem('access_token') || localStorage.getItem('retover_access_token') || ''
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
    (!hasExplicit || LOCAL_LOOPBACK_FASTAPI_ORIGINS.has(explicit))

  if (useDevProxyBehaviour) return ''

  if (hasExplicit) return explicit

  if (typeof window !== 'undefined') {
    const h = window.location.hostname
    if (h === 'localhost' || h === '127.0.0.1' || h === '::1') {
      return 'http://127.0.0.1:8000'
    }
  }

  return ''
}

/** Human-readable endpoint for blocking messages (avoid implying cross-origin when using proxy). */
export function describeApiOrigin() {
  const b = getApiBaseUrl()
  if (b) return b
  if (typeof window !== 'undefined') {
    return `${window.location.origin} (proxied → FastAPI)`
  }
  return '(unset)'
}

export function getApiMisconfigurationMessage() {
  if (typeof window === 'undefined') return ''
  if (getApiBaseUrl() !== '') return ''
  const h = window.location.hostname
  if (h === 'localhost' || h === '127.0.0.1' || h === '::1') return ''

  if (isViteDevelopment() && prefersDevSameOriginProxy()) return ''

  return `This admin host (${h}) requires VITE_API_BASE_URL (absolute URL of the VOXBULK FastAPI origin). Example: https://api.example.com`
}

function joinOriginAndPath(origin, path) {
  const p = path.startsWith('/') ? path : `/${path}`
  if (!origin) return p
  return `${origin.replace(/\/+$/, '')}${p}`
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

function persistPromotedAdminSession(token) {
  if (typeof window === 'undefined' || !token) return
  try {
    localStorage.setItem('retover_admin_access_token', token)
    localStorage.setItem('access_token', token)
    localStorage.setItem('retover_access_token', token)
  } catch {
    /* ignore quota / private mode */
  }
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
    persistPromotedAdminSession(access_token)
    if (map.org_id) localStorage.setItem('retover_org_id', map.org_id)
    if (map.user_id) localStorage.setItem('retover_user_id', map.user_id)
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
  const url = baseUrl ? joinOriginAndPath(baseUrl, path) : `${window.location.origin}${path}`

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
  const baseEmpty = !getApiBaseUrl()
  return [
    'Most common fixes:',
    '1) From this app folder run `npm run dev:full` — starts FastAPI on 0.0.0.0:8000 then Vite after /health is up (fixes 502 when the API was never started).',
    '   Or manually: `cd retover-api` then `python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000` (`0.0.0.0` is more reliable than 127-only on some setups).',
    '2) Restart Vite (`npm run dev`) after editing `.env` so VITE_* is picked up.',
    baseEmpty
      ? '3) Admin dev uses SAME-ORIGIN `/auth`, `/admin`, `/health` on http://localhost:5174 — Vite proxies to `VITE_PROXY_API_TARGET` (default http://127.0.0.1:8000). If `/health` fails, Node cannot reach uvicorn on that target.'
      : '3) Browser calls `VITE_API_BASE_URL` directly — it must match uvicorn’s listen URL.',
    '4) Signing in on http://localhost:5173 does NOT share localStorage with admin on :5174 — use the admin URL’s sign-in/handoff so tokens land on port 5174.',
    '5) `VITE_FORCE_CROSS_ORIGIN_API=true` forces browser→API cross-origin; `VITE_DEV_API_PROXY=false` disables the dev proxy.',
    '6) `DEBUG_ADMIN_PROXY=1 npm run dev` prints each proxied path in the Vite terminal.',
  ].join('\n')
}

/** Dedicated admin JWT — never send clinic `access_token` to `/admin/*` (wrong tenant → Invalid authentication credentials). */
export function getAdminAccessTokenRaw() {
  return localStorage.getItem('retover_admin_access_token') || ''
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
/** Admin (5174) and clinic dashboard (5175) must never masquerade as marketing home. */
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

/** Public marketing / clinic sign-in app home (used after admin logout). */
export function getPublicAppHomeUrl() {
  return `${getPublicAppOrigin()}/`
}

/** Public home with one-time flag so the marketing app clears its own localStorage (other ports). */
export function getPublicLogoutLandingUrl() {
  const u = new URL(`${getPublicAppOrigin()}/`)
  u.searchParams.set('retover_logout', '1')
  return u.toString()
}

/**
 * Resolve whether we have an admin session.
 * - ready: API reachable AND token valid for console
 * - blocked: authenticated but lacks platform admin access (clinic-only user)
 * - none: no token present / session invalid HTTP
 * - error: base URL not configured OR API unreachable
 */
export async function ensureAdminSession() {
  const mis = getApiMisconfigurationMessage()
  if (mis) {
    return {
      status: 'error',
      message: `${mis}\n\n${networkFailureHelp()}`,
    }
  }

  const health = await probeApiConnectivity()
  if (!health.ok) {
    return {
      status: 'error',
      message: [
        'Cannot verify API connectivity.',
        `- Browser requested: ${health.url || '(unknown)'}`,
        health.proxyTarget ? `- Vite proxy target (Node → FastAPI): ${health.proxyTarget}` : '',
        health.status != null ? `- HTTP status: ${health.status}` : '',
        health.error ? `- Detail: ${health.error}` : '',
        health.bodySnippet ? `- Body preview: ${health.bodySnippet}` : '',
        health.upstreamHint ? `- Note: ${health.upstreamHint}` : '',
        `- Mode: ${isViteDevelopment() && !getApiBaseUrl() ? 'Vite dev proxy (same-origin /health → upstream via Node)' : 'Direct browser → API (no proxy)'}`,
        '',
        networkFailureHelp(),
      ]
        .filter(Boolean)
        .join('\n'),
    }
  }

  const direct = getAdminAccessTokenRaw()
  if (direct) {
    try {
      const baseUrl = getApiBaseUrl()
      const url = joinOriginAndPath(baseUrl, '/auth/me')
      const r = await fetch(url, {
        headers: { Authorization: `Bearer ${direct}`, Accept: 'application/json' },
      })
      const text = await r.text()
      const data = text ? safeJson(text) : null
      if (!r.ok) {
        return { status: 'none', message: 'Session expired or invalid for this tenant. Sign in again.' }
      }
      if (data?.admin_access || data?.is_superuser) {
        return { status: 'ready', token: direct }
      }
      return {
        status: 'blocked',
        message:
          'This account is signed in as a clinic user only. Platform admin users (Operations / Billing / Templates roles) use the same sign-in URL but must be explicitly provisioned.',
      }
    } catch (e) {
      return {
        status: 'error',
        message: [
          `${e?.message || 'network error'} when calling GET ${describeApiOrigin()}/auth/me`,
          '',
          networkFailureHelp(),
        ].join('\n'),
      }
    }
  }

  const shared = getSharedJwtFromStorage()
  if (!shared) {
    return { status: 'none', message: 'No session found. Sign in as an admin first.' }
  }

  try {
    const baseUrl = getApiBaseUrl()
    const url = joinOriginAndPath(baseUrl, '/auth/me')
    const r = await fetch(url, {
      headers: { Authorization: `Bearer ${shared}`, Accept: 'application/json' },
    })
    const text = await r.text()
    const data = text ? safeJson(text) : null
    if (!r.ok) {
      return { status: 'none', message: 'Session invalid. Please sign in again.' }
    }
    if (data?.admin_access || data?.is_superuser) {
      persistPromotedAdminSession(shared)
      return { status: 'ready', token: shared }
    }
    return {
      status: 'blocked',
      message:
        'This account is signed in as a clinic user only. Platform admin users (Operations / Billing / Templates roles) use the same sign-in URL but must be explicitly provisioned.',
    }
  } catch (e) {
    return {
      status: 'error',
      message: [
        `${e?.message || 'network error'} when validating session (${describeApiOrigin()} GET /auth/me)`,
        '',
        networkFailureHelp(),
      ].join('\n'),
    }
  }
}

function formatApiError(data, status, statusText) {
  const d = data?.detail
  if (typeof d === 'string') return d
  if (Array.isArray(d)) {
    return d.map((x) => (x && typeof x === 'object' && x.msg ? x.msg : JSON.stringify(x))).join('; ')
  }
  if (d && typeof d === 'object') return JSON.stringify(d)
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
      'No admin session. Sign in on the public app with a platform-admin account first; the console will stash retover_admin_access_token.'
    )
  }
  headers.set('Authorization', `Bearer ${token}`)

  if (options.body != null && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }

  let res
  try {
    res = await fetch(joined, { ...options, headers })
  } catch (e) {
    const msg = e?.message || String(e)
    const isNet =
      /failed to fetch|networkerror|network request failed|load failed|aborted/i.test(msg) ||
      (typeof e?.name === 'string' && e.name === 'TypeError')
    const m = (options.method || 'GET').toString().toUpperCase()
    const hint = isNet
      ? `\n${networkFailureHelp()}\n(Request was ${m} ${joined})`
      : `\n(Request was ${m} ${joined})`
    const err = new Error(`${msg}.${hint}`)
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

function safeJson(text) {
  try {
    return JSON.parse(text)
  } catch {
    return null
  }
}

export function adminLogoutRedirect() {
  if (typeof window === 'undefined') return
  try {
    _adminSyncInFlight = null
    localStorage.removeItem('retover_admin_access_token')
    localStorage.removeItem('retover_admin_selected_org_id')
    localStorage.removeItem('access_token')
    localStorage.removeItem('retover_access_token')
    localStorage.removeItem('retover_org_id')
    localStorage.removeItem('retover_user_id')
    localStorage.removeItem('retover_signup_org_id')
    localStorage.removeItem('retover_user_email')
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
