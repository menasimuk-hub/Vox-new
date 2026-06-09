import { createContext, createElement, useCallback, useContext, useEffect, useState } from 'react'
import { apiFetch } from '../../lib/api'

export function penceToPounds(pence) {
  return (Number(pence || 0) / 100).toFixed(2)
}

export function poundsToPence(pounds) {
  const n = Number(String(pounds || '').replace(/[^\d.]/g, ''))
  return Math.round((Number.isFinite(n) ? n : 0) * 100)
}

const SETTINGS_WRITABLE_KEYS = [
  'connection_fee_pence',
  'connection_fee_label',
  'connection_fee_enabled',
  'interview_per_min_pence',
  'wa_survey_package_fee_pence',
  'wa_survey_extra_pence',
  'ats_cv_scan_fee_pence',
  'estimator_default_duration_min',
  'estimator_default_interview_count',
]

export function pricingSettingsSavePayload(settings) {
  const out = {}
  for (const key of SETTINGS_WRITABLE_KEYS) {
    if (settings?.[key] !== undefined && settings?.[key] !== null) {
      out[key] = settings[key]
    }
  }
  return out
}

function settingsFieldMatches(key, expected, fresh) {
  if (key === 'wa_survey_package_fee_pence') {
    const got = fresh.wa_survey_package_fee_pence ?? fresh.whatsapp_survey_fee_pence
    return Number(got) === Number(expected)
  }
  const got = fresh[key]
  if (typeof expected === 'boolean') return Boolean(got) === Boolean(expected)
  if (typeof expected === 'number') return Number(got) === Number(expected)
  return String(got ?? '') === String(expected ?? '')
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
    const body = pricingSettingsSavePayload(patch)
    try {
      await apiFetch('/admin/pricing/settings', { method: 'PUT', body: JSON.stringify(body) })
      const fresh = await apiFetch('/admin/pricing/settings')
      if (!fresh || typeof fresh !== 'object') {
        throw new Error('Could not verify saved settings')
      }
      for (const [key, val] of Object.entries(body)) {
        if (!settingsFieldMatches(key, val, fresh)) {
          throw new Error('Save did not persist. Reload the page and try again.')
        }
      }
      setSettings(fresh)
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
