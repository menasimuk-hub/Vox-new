export const STORAGE_KEYS = {
  adminAccessToken: 'voxbulk_admin_access_token',
  adminSelectedOrgId: 'voxbulk_admin_selected_org_id',
  accessToken: 'voxbulk_access_token',
  orgId: 'voxbulk_org_id',
  userId: 'voxbulk_user_id',
  signupOrgId: 'voxbulk_signup_org_id',
  userEmail: 'voxbulk_user_email',
  adminTestEmailTo: 'voxbulk_admin_test_email_to',
}

const LEGACY_KEYS = {
  adminAccessToken: 'retover_admin_access_token',
  adminSelectedOrgId: 'retover_admin_selected_org_id',
  accessToken: 'retover_access_token',
  orgId: 'retover_org_id',
  userId: 'retover_user_id',
  signupOrgId: 'retover_signup_org_id',
  userEmail: 'retover_user_email',
  adminTestEmailTo: 'retover_admin_test_email_to',
}

export const LOGOUT_QUERY = 'voxbulk_logout'
export const LEGACY_LOGOUT_QUERY = 'retover_logout'

function readKey(key, legacyKey) {
  if (typeof window === 'undefined') return ''
  const current = localStorage.getItem(key)
  if (current) return current
  const legacy = localStorage.getItem(legacyKey)
  if (!legacy) return ''
  localStorage.setItem(key, legacy)
  localStorage.removeItem(legacyKey)
  return legacy
}

export function readAdminAccessToken() {
  return readKey(STORAGE_KEYS.adminAccessToken, LEGACY_KEYS.adminAccessToken)
}

export function readSharedAccessToken() {
  if (typeof window === 'undefined') return ''
  return (
    localStorage.getItem('access_token') ||
    readKey(STORAGE_KEYS.accessToken, LEGACY_KEYS.accessToken)
  )
}

export function persistPromotedAdminSession(token) {
  if (typeof window === 'undefined' || !token) return
  localStorage.setItem(STORAGE_KEYS.adminAccessToken, token)
  localStorage.setItem(STORAGE_KEYS.accessToken, token)
  localStorage.setItem('access_token', token)
  localStorage.removeItem(LEGACY_KEYS.adminAccessToken)
  localStorage.removeItem(LEGACY_KEYS.accessToken)
}

export function clearAllSessionStorage() {
  if (typeof window === 'undefined') return
  for (const key of Object.values(STORAGE_KEYS)) {
    localStorage.removeItem(key)
  }
  for (const key of Object.values(LEGACY_KEYS)) {
    localStorage.removeItem(key)
  }
  localStorage.removeItem('access_token')
}
