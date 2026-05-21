export function getApiBaseUrl() {
  if (typeof window !== 'undefined') {
    const h = window.location.hostname
    if (h === 'localhost' || h === '127.0.0.1' || h === '::1') return 'http://127.0.0.1:8000'
  }

  const raw = (import.meta?.env?.VITE_API_BASE_URL || import.meta?.env?.VITE_RETOVER_API_BASE_URL || '')
    .trim()
    .replace(/\/+$/, '')

  if (raw) return raw

  if (typeof window !== 'undefined') {
    // VPS/proxy fallback: microgreenia.com exposes FastAPI under /api/.
    if (window.location.protocol === 'https:' || window.location.protocol === 'http:') {
      return `${window.location.origin}/api`
    }
  }

  return ''
}

export function getApiWebSocketUrl(path: string) {
  const baseUrl = getApiBaseUrl()
  const p = path.startsWith('/') ? path : `/${path}`
  const origin = baseUrl || (typeof window !== 'undefined' ? window.location.origin : '')
  return `${origin.replace(/\/+$/, '')}${p}`.replace(/^http/i, 'ws')
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
  if (typeof window !== 'undefined') {
    const h = window.location.hostname
    if (h === 'localhost' || h === '127.0.0.1' || h === '::1') {
      return {
        adminUrl: 'http://localhost:5174',
        dashboardUrl: 'http://localhost:5175',
      }
    }
    if (h === 'voxbulk.com' || h === 'www.voxbulk.com' || h.endsWith('.voxbulk.com')) {
      return {
        adminUrl: 'https://admin.voxbulk.com',
        dashboardUrl: 'https://dashboard.voxbulk.com',
      }
    }
    if (h === 'microgreenia.com' || h === 'www.microgreenia.com' || h.endsWith('.microgreenia.com')) {
      return {
        adminUrl: 'https://admin.microgreenia.com',
        dashboardUrl: 'https://dashboard.microgreenia.com',
      }
    }
  }

  const adminFromEnv = import.meta?.env?.VITE_POST_LOGIN_ADMIN_URL
  const dashboardFromEnv = import.meta?.env?.VITE_POST_LOGIN_DASHBOARD_URL
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
  body.set('username', String(email).trim().toLowerCase())
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

export async function submitSelfServeRequest({ email, password, organisation_name, plan_code, promo_code }) {
  return await retoverFetch('/auth/self-serve', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      email,
      password,
      organisation_name,
      plan_code,
      promo_code: promo_code || undefined,
      payment_method: 'bank_transfer',
    }),
  })
}

export async function fetchPublicPlans() {
  return await publicJsonFetch('/billing/plans')
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

export async function startFrontpageTalkToUsCall(payload: {
  contact_name: string
  company_name: string
  email: string
  phone?: string
  client_timezone?: string
  client_locale?: string
  client_country?: string
  source?: string
}) {
  return publicJsonFetch('/frontpage/talk-to-us/start-call', {
    method: 'POST',
    body: JSON.stringify({
      contact_name: String(payload.contact_name || '').trim(),
      company_name: String(payload.company_name || '').trim(),
      email: String(payload.email || '').trim(),
      phone: String(payload.phone || '').trim() || null,
      client_timezone: String(payload.client_timezone || '').trim() || null,
      client_locale: String(payload.client_locale || '').trim() || null,
      client_country: String(payload.client_country || '').trim() || null,
      source: payload.source || 'frontpage_talk_to_us',
    }),
  })
}

export function frontpageTalkToUsVoiceUrl(callId: string) {
  return getApiWebSocketUrl(`/frontpage/talk-to-us/voice/${encodeURIComponent(callId)}`)
}

export async function fetchFrontpageTalkToUsConfig() {
  return publicJsonFetch('/frontpage/talk-to-us/config')
}

export async function completeFrontpageTalkToUsCall(
  callId: string,
  payload: {
    transcript_text?: string
    agent_response_text?: string
    duration_seconds?: number
    provider_call_id?: string
    recording?: Blob | null
  },
) {
  const baseUrl = getApiBaseUrl()
  if (!baseUrl) throw new Error('API base URL is not set')
  const form = new FormData()
  if (payload.transcript_text) form.append('transcript_text', payload.transcript_text)
  if (payload.agent_response_text) form.append('agent_response_text', payload.agent_response_text)
  if (payload.duration_seconds != null) form.append('duration_seconds', String(payload.duration_seconds))
  if (payload.provider_call_id) form.append('provider_call_id', payload.provider_call_id)
  if (payload.recording) form.append('recording', payload.recording, 'call.webm')

  const res = await fetch(`${baseUrl}/frontpage/talk-to-us/complete-call/${encodeURIComponent(callId)}`, {
    method: 'POST',
    body: form,
    headers: { Accept: 'application/json' },
  })
  const text = await res.text()
  const data = text ? safeJson(text) : null
  if (!res.ok) {
    const message = formatApiDetail(data, res.status, res.statusText)
    throw new Error(message)
  }
  return data
}

