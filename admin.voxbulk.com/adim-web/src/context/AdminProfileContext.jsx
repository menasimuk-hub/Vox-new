import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { apiFetch } from '../lib/api'
import { normalizeAdminRole } from '../lib/adminPaths'

const AdminProfileContext = createContext({
  loading: true,
  error: '',
  profile: null,
  adminRole: 'superadmin',
  reload: async () => {},
})

export function AdminProfileProvider({ children }) {
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [profile, setProfile] = useState(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      // In Vite dev, `getApiBaseUrl()` is intentionally '' so `/auth/me` hits the same origin and Vite proxies to FastAPI.
      const data = await apiFetch('/auth/me')
      setProfile(data && typeof data === 'object' ? data : null)
    } catch (e) {
      setProfile(null)
      setError(e?.message || 'Could not load admin profile.')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  const adminRole = useMemo(() => normalizeAdminRole(profile?.admin_role), [profile])

  const value = useMemo(
    () => ({
      loading,
      error,
      profile,
      adminRole,
      reload: load,
    }),
    [loading, error, profile, adminRole, load]
  )

  return <AdminProfileContext.Provider value={value}>{children}</AdminProfileContext.Provider>
}

export function useAdminProfile() {
  return useContext(AdminProfileContext)
}
