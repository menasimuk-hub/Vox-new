import { createContext, createElement, useCallback, useContext, useEffect, useState } from 'react'
import { apiFetch } from '../../lib/api'

export function penceToPounds(pence) {
  return (Number(pence || 0) / 100).toFixed(2)
}

export function poundsToPence(pounds) {
  const n = Number(String(pounds || '').replace(/[^\d.]/g, ''))
  return Math.round((Number.isFinite(n) ? n : 0) * 100)
}

const PricingSettingsContext = createContext(null)

export function PricingSettingsProvider({ children }) {
  const [settings, setSettings] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [msg, setMsg] = useState('')

  const load = useCallback(async () => {
    setError('')
    try {
      const row = await apiFetch('/admin/pricing/settings')
      if (!row || typeof row !== 'object') {
        throw new Error('Could not load pricing settings')
      }
      setSettings(row)
      return true
    } catch (e) {
      setError(e?.message || 'Could not load settings')
      return false
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      setLoading(true)
      await load()
      if (!cancelled) setLoading(false)
    })()
    return () => { cancelled = true }
  }, [load])

  const reload = useCallback(async () => {
    setLoading(true)
    await load()
    setLoading(false)
  }, [load])

  const save = async (patch) => {
    setError('')
    setMsg('')
    try {
      const row = await apiFetch('/admin/pricing/settings', { method: 'PUT', body: JSON.stringify(patch) })
      if (!row || typeof row !== 'object') {
        throw new Error('Invalid settings response')
      }
      setSettings(row)
      setMsg('Saved.')
    } catch (e) {
      setError(e?.message || 'Save failed')
    }
  }

  return createElement(
    PricingSettingsContext.Provider,
    { value: { settings, setSettings, loading, error, msg, load: reload, save } },
    children,
  )
}

export function usePricingSettings() {
  const ctx = useContext(PricingSettingsContext)
  if (!ctx) {
    throw new Error('usePricingSettings must be used within PricingSettingsProvider')
  }
  return ctx
}

export function usePricingPlans() {
  const [plans, setPlans] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [msg, setMsg] = useState('')

  const load = useCallback(async () => {
    setError('')
    try {
      const rows = await apiFetch('/admin/pricing/plans')
      setPlans(Array.isArray(rows) ? rows : [])
      return true
    } catch (e) {
      setError(e?.message || 'Could not load plans')
      return false
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      setLoading(true)
      await load()
      if (!cancelled) setLoading(false)
    })()
    return () => { cancelled = true }
  }, [load])

  const reload = useCallback(async () => {
    setLoading(true)
    await load()
    setLoading(false)
  }, [load])

  const savePlan = async (planId, patch) => {
    setError('')
    setMsg('')
    try {
      const row = await apiFetch(`/admin/pricing/plans/${encodeURIComponent(planId)}`, {
        method: 'PUT',
        body: JSON.stringify(patch),
      })
      setPlans((prev) => prev.map((p) => (p.id === planId ? row : p)))
      setMsg('Plan saved.')
    } catch (e) {
      setError(e?.message || 'Save failed')
    }
  }

  const seed = async () => {
    setError('')
    try {
      await apiFetch('/admin/pricing/seed', { method: 'POST', body: '{}' })
      await reload()
      setMsg('Default VoxBulk plans seeded.')
    } catch (e) {
      setError(e?.message || 'Seed failed')
    }
  }

  return { plans, loading, error, msg, load: reload, savePlan, seed }
}
