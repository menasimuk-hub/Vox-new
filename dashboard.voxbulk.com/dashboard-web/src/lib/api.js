export function getApiBaseUrl() {
  const raw = (import.meta?.env?.VITE_API_BASE_URL || import.meta?.env?.VITE_RETOVER_API_BASE_URL || '')
    .trim()
    .replace(/\/+$/, '')
  if (raw) return raw
  if (typeof window !== 'undefined') {
    const h = window.location.hostname
    if (h === 'localhost' || h === '127.0.0.1' || h === '::1') return 'http://127.0.0.1:8000'
  }
  return ''
}

export function getAccessToken() {
  const candidates = [
    localStorage.getItem('retover_access_token') || '',
    // compatibility with earlier admin/public flows/tools
    localStorage.getItem('access_token') || '',
  ].filter(Boolean)
  if (!candidates.length) return ''

  const storedOrgId = localStorage.getItem('retover_org_id') || ''
  const scored = candidates
    .map((token) => ({ token, payload: decodeJwtPayload(token) }))
    .filter(({ payload }) => !payload?.exp || payload.exp * 1000 > Date.now())

  const withMatchingOrg = scored.find(({ payload }) => payload?.org_id && String(payload.org_id) === String(storedOrgId))
  if (withMatchingOrg) return withMatchingOrg.token

  const withOrg = scored.find(({ payload }) => payload?.org_id)
  if (withOrg) return withOrg.token

  return scored[0]?.token || candidates[0] || ''
}

export async function apiFetch(path, options = {}) {
  const baseUrl = getApiBaseUrl()
  const url = baseUrl ? `${baseUrl}${path}` : path

  const headers = new Headers(options.headers || {})
  headers.set('Accept', 'application/json')
  if (
    options.body != null &&
    typeof options.body === 'string' &&
    !headers.has('Content-Type')
  ) {
    headers.set('Content-Type', 'application/json')
  }

  const token = getAccessToken()
  if (token) headers.set('Authorization', `Bearer ${token}`)
  const orgId = localStorage.getItem('retover_org_id')
  if (orgId && !headers.has('X-Retover-Org-Id')) headers.set('X-Retover-Org-Id', orgId)

  const res = await fetch(url, { ...options, headers })
  const text = await res.text()
  const data = text ? safeJson(text) : null

  if (!res.ok) {
    const message =
      (data && (data.detail || data.message)) ||
      `${res.status} ${res.statusText}`.trim()
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

function decodeJwtPayload(token) {
  try {
    const part = String(token || '').split('.')[1]
    if (!part) return null
    const normalized = part.replace(/-/g, '+').replace(/_/g, '/')
    const padded = normalized.padEnd(Math.ceil(normalized.length / 4) * 4, '=')
    return JSON.parse(atob(padded))
  } catch {
    return null
  }
}

export function getPublicSignInUrl() {
  const raw = String(import.meta?.env?.VITE_PUBLIC_SIGNIN_URL || '').trim().replace(/\/+$/, '')
  if (raw) return raw
  if (typeof window !== 'undefined') {
    const h = window.location.hostname
    if (h === 'localhost' || h === '127.0.0.1' || h === '::1') return 'http://localhost:5173/signin'
    if (h === 'dashboard.voxbulk.com') return 'https://voxbulk.com/signin'
  }
  return '/signin'
}

const DEV_PUBLIC_MARKETING = 'http://localhost:5173'
/** Admin (5174) and clinic dashboard (5175) must never be used as “marketing home” after logout. */
const DEV_NON_MARKETING_PORTS = new Set(['5174', '5175'])

function marketingOriginAfterLogout() {
  const productionDefault =
    typeof window !== 'undefined' && window.location.hostname === 'dashboard.voxbulk.com'
      ? 'https://voxbulk.com'
      : DEV_PUBLIC_MARKETING
  const raw = String(import.meta?.env?.VITE_PUBLIC_APP_URL || productionDefault)
    .trim()
    .replace(/\/+$/, '')
  try {
    const u = new URL(raw.includes('://') ? raw : `http://${raw}`)
    const host = u.hostname
    const port = String(u.port || (u.protocol === 'https:' ? '443' : '80'))
    const loop = host === 'localhost' || host === '127.0.0.1' || host === '::1'
    if (loop && DEV_NON_MARKETING_PORTS.has(port)) {
      return DEV_PUBLIC_MARKETING
    }
    if (typeof window !== 'undefined') {
      try {
        if (u.host === window.location.host) {
          return DEV_PUBLIC_MARKETING
        }
      } catch {
        /* ignore */
      }
    }
    return u.origin
  } catch {
    return DEV_PUBLIC_MARKETING
  }
}

/** Public marketing home; `retover_logout` clears clinic tokens on origin :5173. */
function getPublicLogoutLandingUrl() {
  const u = new URL(`${marketingOriginAfterLogout().replace(/\/+$/, '')}/`)
  u.searchParams.set('retover_logout', '1')
  return u.toString()
}

/** Clear clinic + admin stash keys and navigate to public home. */
export function logoutDashboard() {
  if (typeof window === 'undefined') return
  try {
    localStorage.removeItem('retover_access_token')
    localStorage.removeItem('access_token')
    localStorage.removeItem('retover_org_id')
    localStorage.removeItem('retover_user_id')
    localStorage.removeItem('retover_admin_access_token')
    localStorage.removeItem('retover_admin_selected_org_id')
    localStorage.removeItem('retover_signup_org_id')
    localStorage.removeItem('retover_user_email')
    // Wizard completion is stored on the server (membership); keep local draft only if present.
  } catch {
    /* ignore */
  }
  window.location.replace(getPublicLogoutLandingUrl())
}

