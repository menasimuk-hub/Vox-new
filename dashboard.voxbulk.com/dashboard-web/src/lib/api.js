function productionApiOrigin() {
  if (typeof window === 'undefined') return ''
  if (window.location.hostname === 'dashboard.voxbulk.com') return 'https://api.voxbulk.com'
  return ''
}

export function getApiBaseUrl() {
  const raw = (import.meta?.env?.VITE_API_BASE_URL || import.meta?.env?.VITE_RETOVER_API_BASE_URL || '')
    .trim()
    .replace(/\/+$/, '')

  if (raw) {
    try {
      const configured = new URL(raw.includes('://') ? raw : `https://${raw}`)
      if (
        typeof window !== 'undefined' &&
        configured.hostname === window.location.hostname
      ) {
        // Misconfigured build (e.g. VITE_API_BASE_URL=https://dashboard.voxbulk.com) — static nginx returns 405 on PATCH.
        const fallback = productionApiOrigin()
        if (fallback) return fallback
      }
      return configured.origin
    } catch {
      /* use defaults below */
    }
  }

  if (typeof window !== 'undefined') {
    const h = window.location.hostname
    if (h === 'localhost' || h === '127.0.0.1' || h === '::1') return ''
    const prod = productionApiOrigin()
    if (prod) return prod
  }
  return ''
}

function isTokenUsable(token) {
  const payload = decodeJwtPayload(token)
  if (!payload?.sub) return false
  if (payload.exp && payload.exp * 1000 <= Date.now()) return false
  return true
}

function syncOrgIdFromToken(token) {
  const payload = decodeJwtPayload(token)
  if (!payload?.org_id) return
  const orgId = String(payload.org_id)
  if (localStorage.getItem('retover_org_id') !== orgId) {
    localStorage.setItem('retover_org_id', orgId)
  }
}

export function getAccessToken() {
  const candidates = [
    localStorage.getItem('retover_access_token') || '',
    localStorage.getItem('access_token') || '',
  ].filter(Boolean)

  const storedOrgId = localStorage.getItem('retover_org_id') || ''
  const usable = candidates
    .filter(isTokenUsable)
    .map((token) => ({ token, payload: decodeJwtPayload(token) }))

  const withMatchingOrg = usable.find(
    ({ payload }) => payload?.org_id && String(payload.org_id) === String(storedOrgId),
  )
  const picked = withMatchingOrg || usable.find(({ payload }) => payload?.org_id) || usable[0]
  if (!picked?.token) return ''

  syncOrgIdFromToken(picked.token)
  return picked.token
}

export function buildAuthHeaders(extraHeaders) {
  const headers = new Headers(extraHeaders || {})
  const token = getAccessToken()
  if (token) headers.set('Authorization', `Bearer ${token}`)
  const orgId = localStorage.getItem('retover_org_id')
  if (orgId && !headers.has('X-Retover-Org-Id')) headers.set('X-Retover-Org-Id', orgId)
  return headers
}

export function authErrorMessage(err) {
  if (err?.status === 401 || /invalid authentication credentials/i.test(String(err?.message || ''))) {
    return 'Your session expired. Please sign in again.'
  }
  return err?.message || 'Request failed'
}

export function handleUnauthorizedApiError(err, { redirect = true } = {}) {
  if (err?.status !== 401 && !/invalid authentication credentials/i.test(String(err?.message || ''))) {
    return false
  }
  if (redirect) {
    setTimeout(() => redirectToSignIn(), 800)
  }
  return true
}

export async function downloadAuthenticatedFile(path, filename) {
  const baseUrl = getApiBaseUrl()
  const url = baseUrl ? `${baseUrl}${path}` : path
  const headers = buildAuthHeaders()
  const res = await fetch(url, { headers })
  if (!res.ok) {
    const text = await res.text()
    let message = `${res.status} ${res.statusText}`.trim()
    try {
      const data = JSON.parse(text)
      if (data?.detail) message = typeof data.detail === 'string' ? data.detail : message
    } catch {
      /* ignore */
    }
    const err = new Error(message)
    err.status = res.status
    throw err
  }
  const blob = await res.blob()
  const objectUrl = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = objectUrl
  anchor.download = filename
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  URL.revokeObjectURL(objectUrl)
}

export async function apiFetch(path, options = {}) {
  const baseUrl = getApiBaseUrl()
  const url = baseUrl ? `${baseUrl}${path}` : path

  const headers = buildAuthHeaders(options.headers || {})
  headers.set('Accept', 'application/json')
  if (
    options.body != null &&
    typeof options.body === 'string' &&
    !headers.has('Content-Type')
  ) {
    headers.set('Content-Type', 'application/json')
  }

  const res = await fetch(url, { ...options, headers })
  const text = await res.text()
  const data = text ? safeJson(text) : null

  if (!res.ok) {
    const message =
      (data && (typeof data.detail === 'string' ? data.detail : data.message)) ||
      `${res.status} ${res.statusText}`.trim()
    const err = new Error(message)
    err.status = res.status
    err.data = data
    if (res.status === 401 && options.redirectOn401 !== false) {
      handleUnauthorizedApiError(err)
    }
    throw err
  }
  return data
}

export async function apiUploadFile(path, file, fieldName = 'file') {
  const baseUrl = getApiBaseUrl()
  const url = baseUrl ? `${baseUrl}${path}` : path
  const fd = new FormData()
  fd.append(fieldName, file)
  const headers = buildAuthHeaders()
  const res = await fetch(url, { method: 'POST', headers, body: fd })
  const text = await res.text()
  const data = text ? safeJson(text) : null
  if (!res.ok) {
    const message =
      (data && (typeof data.detail === 'string' ? data.detail : data.message)) ||
      `${res.status} ${res.statusText}`.trim()
    const err = new Error(message)
    err.status = res.status
    err.data = data
    if (res.status === 401) handleUnauthorizedApiError(err)
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
    const port = String(u.port || (u.protocol === 'https:' ? '443' : '80'))
    const loop = u.hostname === 'localhost' || u.hostname === '127.0.0.1' || u.hostname === '::1'
    if (loop && DEV_NON_MARKETING_PORTS.has(port)) return DEV_PUBLIC_MARKETING
    if (typeof window !== 'undefined' && u.host === window.location.host) return DEV_PUBLIC_MARKETING
    return u.origin
  } catch {
    return DEV_PUBLIC_MARKETING
  }
}

function getPublicLogoutLandingUrl() {
  const u = new URL(`${marketingOriginAfterLogout().replace(/\/+$/, '')}/`)
  u.searchParams.set('retover_logout', '1')
  return u.toString()
}

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
  } catch {
    /* ignore */
  }
  window.location.replace(getPublicLogoutLandingUrl())
}

export function redirectToSignIn() {
  window.location.replace(getPublicSignInUrl())
}
