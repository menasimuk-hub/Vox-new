export function getApiBaseUrl() {
  const raw = (import.meta?.env?.VITE_API_BASE_URL || import.meta?.env?.VITE_RETOVER_API_BASE_URL || '')
    .trim()
    .replace(/\/+$/, '')

  if (raw) return raw

  if (typeof window !== 'undefined') {
    const h = window.location.hostname
    if (h === 'localhost' || h === '127.0.0.1' || h === '::1') return 'http://127.0.0.1:8000'

    // VPS/proxy fallback: microgreenia.com exposes FastAPI under /api/.
    // This prevents deployed Vite dev/prod builds from hard-failing when env was not loaded.
    if (window.location.protocol === 'https:' || window.location.protocol === 'http:') {
      return `${window.location.origin}/api`
    }
  }

  return ''
}

export function getUserAccessToken() {
  return (
    localStorage.getItem('retover_access_token') ||
    // small compatibility bridge for earlier experiments / dev tools
    localStorage.getItem('access_token') ||
    ''
  )
}

export function setUserAuthSession({ access_token, org_id, user_id }) {
  localStorage.setItem('retover_access_token', access_token)
  localStorage.setItem('retover_org_id', org_id)
  localStorage.setItem('retover_user_id', user_id)
  // compatibility: some older code paths looked for generic key
  localStorage.setItem('access_token', access_token)
}

/** Clear clinic/public JWT storage — use when /auth/me rejects a stale token */
export function clearClinicAuthSession() {
  if (typeof localStorage === 'undefined') return
  localStorage.removeItem('retover_access_token')
  localStorage.removeItem('access_token')
  localStorage.removeItem('retover_org_id')
  localStorage.removeItem('retover_user_id')
}

/**
 * Full clear for the public-site origin (5173). Cross-app logout must run this on the marketing app
 * because dashboard/admin use separate localStorage per port.
 */
export function clearAllRetoverSiteLocalKeys() {
  if (typeof localStorage === 'undefined') return
  clearClinicAuthSession()
  localStorage.removeItem('retover_admin_access_token')
  localStorage.removeItem('retover_admin_selected_org_id')
  localStorage.removeItem('retover_signup_org_id')
  localStorage.removeItem('retover_user_email')
}

export function getPostLoginTargets() {
  const adminFromEnv = import.meta?.env?.VITE_POST_LOGIN_ADMIN_URL
  const dashboardFromEnv = import.meta?.env?.VITE_POST_LOGIN_DASHBOARD_URL
  if (!adminFromEnv && !dashboardFromEnv && typeof window !== 'undefined') {
    const host = window.location.hostname
    if (host === 'voxbulk.com' || host === 'www.voxbulk.com' || host.endsWith('.voxbulk.com')) {
      return {
        adminUrl: 'https://admin.voxbulk.com',
        dashboardUrl: 'https://dashboard.voxbulk.com',
      }
    }
    if (host === 'microgreenia.com' || host === 'www.microgreenia.com' || host.endsWith('.microgreenia.com')) {
      return {
        adminUrl: 'https://admin.microgreenia.com',
        dashboardUrl: 'https://dashboard.microgreenia.com',
      }
    }
  }
  return {
    adminUrl: (adminFromEnv || 'http://localhost:5174').replace(/\/+$/, ''),
    dashboardUrl: (dashboardFromEnv || 'http://localhost:5175').replace(/\/+$/, ''),
  }
}

/**
 * localStorage is per-origin (port included). Signing in on :5173 then redirecting to :5175
 * would drop the token unless we hand it off. Hash is never sent to the server.
 */
export function clinicDashboardUrlWithAuthHandoff(dashboardUrl) {
  const base = dashboardUrl.replace(/\/+$/, '')
  const access_token = getUserAccessToken()
  const org_id = localStorage.getItem('retover_org_id') || ''
  const user_id = localStorage.getItem('retover_user_id') || ''
  const p = new URLSearchParams()
  if (access_token) p.set('access_token', access_token)
  if (org_id) p.set('org_id', org_id)
  if (user_id) p.set('user_id', user_id)
  return `${base}/#${p.toString()}`
}

export function adminUrlWithAuthHandoff(adminUrl) {
  const base = adminUrl.replace(/\/+$/, '')
  const access_token =
    localStorage.getItem('retover_admin_access_token') || getUserAccessToken()
  const org_id = localStorage.getItem('retover_org_id') || ''
  const user_id = localStorage.getItem('retover_user_id') || ''
  const p = new URLSearchParams()
  if (access_token) p.set('access_token', access_token)
  if (org_id) p.set('org_id', org_id)
  if (user_id) p.set('user_id', user_id)
  return `${base}/#${p.toString()}`
}

function safeJson(text: string) {
  try {
    return JSON.parse(text)
  } catch {
    return null
  }
}

/** FastAPI often returns `detail` as a string, list of {msg}, or object */
function formatApiDetail(data: unknown, status: number, statusText: string): string {
  const d = (data as { detail?: unknown } | null)?.detail
  if (typeof d === 'string') return d
  if (Array.isArray(d)) {
    return d
      .map((x) =>
        x && typeof x === 'object' && 'msg' in x ? String((x as { msg?: string }).msg) : JSON.stringify(x)
      )
      .join('; ')
  }
  if (d && typeof d === 'object') return JSON.stringify(d)
  const m = (data as { message?: unknown } | null)?.message
  if (typeof m === 'string') return m
  return `${status} ${statusText}`.trim()
}

/** Do not attach JWT — avoids stale clinic token breaking login/register/social lookups */
function pathSkipsAuth(path: string): boolean {
  if (!path.startsWith('/auth/')) return false
  if (path === '/auth/token' || path.startsWith('/auth/token?')) return true
  if (path === '/auth/register' || path.startsWith('/auth/register?')) return true
  if (path === '/auth/self-serve' || path.startsWith('/auth/self-serve?')) return true
  if (path === '/auth/forgot-password' || path.startsWith('/auth/forgot-password?')) return true
  if (path === '/auth/reset-password' || path.startsWith('/auth/reset-password?')) return true
  if (path.startsWith('/auth/invite-preview')) return true
  if (path === '/auth/accept-invite' || path.startsWith('/auth/accept-invite?')) return true
  if (path.startsWith('/auth/social-login/')) return true
  if (path.startsWith('/auth/oauth/')) return true
  return false
}

export async function retoverFetch(path, options = {}) {
  const baseUrl = getApiBaseUrl()
  if (!baseUrl) {
    throw new Error(
      'API base URL is not set. Set VITE_API_BASE_URL (or VITE_RETOVER_API_BASE_URL) to your backend, e.g. http://127.0.0.1:8000'
    )
  }
  const url = `${baseUrl}${path}`

  // Dev-only guard: auth must never hit the Vite origin.
  if (
    import.meta?.env?.DEV &&
    typeof window !== 'undefined' &&
    typeof path === 'string' &&
    path.startsWith('/auth/') &&
    typeof url === 'string' &&
    url.startsWith(window.location.origin)
  ) {
    throw new Error(`Misconfigured API base URL: auth request would target ${url}`)
  }

  const headers = new Headers(options.headers || {})
  headers.set('Accept', 'application/json')

  const token = getUserAccessToken()
  if (token && typeof path === "string" && !pathSkipsAuth(path)) {
    headers.set("Authorization", `Bearer ${token}`)
  }

  const res = await fetch(url, { ...options, headers })
  const text = await res.text()
  const data = text ? safeJson(text) : null

  if (!res.ok) {
    const message = formatApiDetail(data, res.status, res.statusText)
    const err = new Error(message)
    err.status = res.status
    err.data = data
    throw err
  }
  return data
}

export async function loginWithPassword({ email, password }) {
  const body = new URLSearchParams()
  body.set('username', email)
  body.set('password', password)
  // org_id is optional on backend if the user has exactly one membership

  return await retoverFetch('/auth/token', {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body,
  })
}

export async function fetchInvitePreview(token: string) {
  const q = new URLSearchParams({ token })
  return await retoverFetch(`/auth/invite-preview?${q.toString()}`)
}

export async function acceptInvite({ token, password }: { token: string; password: string }) {
  return await retoverFetch('/auth/accept-invite', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ token, password }),
  })
}

export async function registerUser({ email, password, organisation_name, org_id }) {
  const body = { email, password, organisation_name }
  const trimmedOrg = org_id != null && String(org_id).trim() !== '' ? String(org_id).trim() : null
  if (trimmedOrg) Object.assign(body, { org_id: trimmedOrg })

  return await retoverFetch('/auth/register', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

export async function fetchSocialLoginProviders() {
  return await retoverFetch('/auth/social-login/providers')
}

export async function submitSelfServeRequest({ email, password, organisation_name, plan_code }) {
  return await retoverFetch('/auth/self-serve', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password, organisation_name, plan_code, payment_method: 'bank_transfer' }),
  })
}

/** Persist tenant membership role (must be called with a valid access token). */
export async function setMembershipRole(role) {
  return await retoverFetch('/auth/me/role', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ role }),
  })
}

/** Public auth endpoints — never attaches Authorization (avoid stale clinic tokens interfering). */
export async function publicJsonFetch(path: string, options: RequestInit = {}) {
  const baseUrl = getApiBaseUrl()
  if (!baseUrl) {
    throw new Error(
      'API base URL is not set. Set VITE_API_BASE_URL (or VITE_RETOVER_API_BASE_URL), e.g. http://127.0.0.1:8000'
    )
  }
  const url = `${baseUrl}${path}`
  const headers = new Headers(options.headers)
  headers.set('Accept', 'application/json')
  if (options.body != null && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }

  const res = await fetch(url, { ...options, headers })
  const text = await res.text()
  const data = text ? safeJson(text) : null

  if (!res.ok) {
    const message = formatApiDetail(data, res.status, res.statusText)
    const err = new Error(message)
    err.status = res.status
    err.data = data
    throw err
  }

  return data
}

export async function forgotPasswordRequest(email: string) {
  return publicJsonFetch('/auth/forgot-password', {
    method: 'POST',
    body: JSON.stringify({ email: String(email || '').trim() }),
  })
}

export async function resetPasswordRequest(payload: { token: string; password: string }) {
  return publicJsonFetch('/auth/reset-password', {
    method: 'POST',
    body: JSON.stringify({
      token: String(payload.token || '').trim(),
      password: String(payload.password || ''),
    }),
  })
}

