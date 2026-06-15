const TOKEN_KEY = 'abuu_restaurant_token'

const PORTAL_HOSTS = new Set([
  'abuu.voxbulk.com',
  'driver.voxbulk.com',
  'restaurant.yallasay.com',
  'driver.yallasay.com',
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

export function apiUrl(path) {
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
    const msg = data?.detail || data?.message || res.statusText || 'Request failed'
    throw new Error(typeof msg === 'string' ? msg : JSON.stringify(msg))
  }
  return data
}

export async function loginRestaurant(email, password) {
  const body = new URLSearchParams({ username: email, password })
  let res
  try {
    res = await fetch(apiUrl('/abuu/auth/restaurant/token'), {
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
