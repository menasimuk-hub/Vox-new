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

export function AdminProfileProvider({ children, initialProfile = null }) {
  const [loading, setLoading] = useState(() => !initialProfile)
  const [error, setError] = useState('')
  const [profile, setProfile] = useState(initialProfile)

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
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
    if (initialProfile) {
      setProfile(initialProfile)
      setLoading(false)
      return undefined
    }
    void load()
    return undefined
  }, [initialProfile, load])

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
