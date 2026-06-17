const TOKEN_KEY = 'abuu_driver_token'

const PORTAL_HOSTS = new Set([
  'driver.voxbulk.com',
  'abuu.voxbulk.com',
  'driver.yallasay.com',
  'restaurant.yallasay.com',
])

export function getApiBase() {
  const explicit = String(import.meta.env.VITE_API_BASE_URL || '').trim().replace(/\/+$/, '')
  if (explicit) return explicit
  if (import.meta.env.DEV) return ''
  if (typeof window !== 'undefined' && PORTAL_HOSTS.has(window.location.hostname)) {
    return ''
  }
  return 'https://api.voxbulk.com'
}

function apiUrl(path) {
  const p = path.startsWith('/') ? path : `/${path}`
  const base = getApiBase()
  if (!base) return p
  return `${base}${p}`
}

export function getToken() {
  return localStorage.getItem(TOKEN_KEY) || ''
}

export function setToken(token) {
  if (token) localStorage.setItem(TOKEN_KEY, token)
  else localStorage.removeItem(TOKEN_KEY)
}

export function clearToken() {
  localStorage.removeItem(TOKEN_KEY)
}

export async function logoutDriver() {
  try {
    await apiFetch('/abuu/auth/driver/logout', { method: 'POST', body: '{}' })
  } catch {
    // still clear local session
  }
  clearToken()
  if (typeof window !== 'undefined') window.location.href = '/login'
}

export async function apiFetch(path, options = {}) {
  const url = apiUrl(path)
  const headers = { ...(options.headers || {}) }
  if (!headers['Content-Type'] && options.body) headers['Content-Type'] = 'application/json'
  const token = getToken()
  if (token) headers.Authorization = `Bearer ${token}`

  let res
  try {
    res = await fetch(url, { ...options, headers })
  } catch (err) {
    throw new Error(
      err?.message === 'Failed to fetch'
        ? 'Cannot reach API — check nginx /abuu/ proxy and that FastAPI is running on :8000'
        : err?.message || 'Network error',
    )
  }
  const text = await res.text()
  let data = null
  try {
    data = text ? JSON.parse(text) : null
  } catch {
    data = text
  }
  if (!res.ok) {
    if (res.status === 401 && getToken()) {
      clearToken()
      if (typeof window !== 'undefined' && !window.location.pathname.startsWith('/login')) {
        window.location.href = '/login'
      }
    }
    const msg = data?.detail || data?.message || res.statusText || 'Request failed'
    throw new Error(typeof msg === 'string' ? msg : JSON.stringify(msg))
  }
  return data
}

export async function loginDriver(email, password) {
  const body = new URLSearchParams({ username: email, password })
  let res
  try {
    res = await fetch(apiUrl('/abuu/auth/driver/token'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body,
    })
  } catch (err) {
    throw new Error(
      err?.message === 'Failed to fetch'
        ? 'Cannot reach login API — ensure nginx proxies /abuu/ to 127.0.0.1:8000'
        : err?.message || 'Network error',
    )
  }
  let data
  try {
    data = await res.json()
  } catch {
    throw new Error('Invalid response from login API')
  }
  if (!res.ok) throw new Error(data?.detail || 'Login failed')
  setToken(data.access_token)
  return data
}

export async function fetchDemoDrivers() {
  const res = await fetch(apiUrl('/abuu/internal/demo/drivers'))
  if (res.status === 404) {
    throw new Error('Demo directory is disabled (set ABUU_DEMO_SHOWALL_ENABLED=true on API)')
  }
  const data = await res.json()
  if (!res.ok) throw new Error(data?.detail || 'Could not load demo drivers')
  return data
}
