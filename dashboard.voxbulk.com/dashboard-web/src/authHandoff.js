/**
 * Public app (:5173) and dashboard (:5175) do not share localStorage.
 * Sign-in redirect appends a one-time #access_token=… (and org/user ids); strip it after storing.
 */
;(function consumeRetoverAuthHandoffFromHash() {
  if (typeof window === 'undefined') return
  const raw = window.location.hash
  if (!raw || raw.length <= 1) return
  try {
    const params = new URLSearchParams(raw.startsWith('#') ? raw.slice(1) : raw)
    const access_token = params.get('access_token')
    if (!access_token) return
    localStorage.setItem('retover_access_token', access_token)
    localStorage.setItem('access_token', access_token)
    const org_id = params.get('org_id')
    const user_id = params.get('user_id')
    if (org_id) localStorage.setItem('retover_org_id', org_id)
    if (user_id) localStorage.setItem('retover_user_id', user_id)
    const { pathname, search } = window.location
    window.history.replaceState(null, '', pathname + search)
  } catch {
    /* ignore */
  }
})()
