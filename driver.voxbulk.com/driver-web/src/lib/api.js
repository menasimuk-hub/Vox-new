const TOKEN_KEY = 'abuu_driver_token'

export function getApiBase() {
  const explicit = String(import.meta.env.VITE_API_BASE_URL || '').trim().replace(/\/+$/, '')
  if (explicit) return explicit
  if (import.meta.env.DEV) return ''
  return 'https://api.voxbulk.com'
}

export function getToken() {
  return localStorage.getItem(TOKEN_KEY) || ''
}

export function setToken(token) {
  if (token) localStorage.setItem(TOKEN_KEY, token)
  else localStorage.removeItem(TOKEN_KEY)
}

export async function apiFetch(path, options = {}) {
  const base = getApiBase()
  const url = `${base}${path.startsWith('/') ? path : `/${path}`}`
  const headers = { ...(options.headers || {}) }
  if (!headers['Content-Type'] && options.body) headers['Content-Type'] = 'application/json'
  const token = getToken()
  if (token) headers.Authorization = `Bearer ${token}`

  const res = await fetch(url, { ...options, headers })
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

export async function loginDriver(email, password) {
  const body = new URLSearchParams({ username: email, password })
  const base = getApiBase()
  const res = await fetch(`${base}/abuu/auth/driver/token`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body,
  })
  const data = await res.json()
  if (!res.ok) throw new Error(data?.detail || 'Login failed')
  setToken(data.access_token)
  return data
}
