import { useCallback, useEffect, useState } from 'react'
import { apiFetch } from '../../lib/api'

export function penceToPounds(pence) {
  return (Number(pence || 0) / 100).toFixed(2)
}

export function poundsToPence(pounds) {
  const n = Number(String(pounds || '').replace(/[^\d.]/g, ''))
  return Math.round((Number.isFinite(n) ? n : 0) * 100)
}

export function usePricingSettings() {
  const [settings, setSettings] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [msg, setMsg] = useState('')

  const load = useCallback(async () => {
    setError('')
    for (let attempt = 0; attempt < 2; attempt += 1) {
      try {
        const row = await apiFetch('/admin/pricing/settings')
        setSettings(row)
        return
      } catch (e) {
        if (attempt === 0) {
          await new Promise((resolve) => setTimeout(resolve, 400))
          continue
        }
        throw e
      }
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      setLoading(true)
      try {
        await load()
      } catch (e) {
        if (!cancelled) setError(e?.message || 'Could not load settings')
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => { cancelled = true }
  }, [load])

  const save = async (patch) => {
    setError('')
    setMsg('')
    try {
      const row = await apiFetch('/admin/pricing/settings', { method: 'PUT', body: JSON.stringify(patch) })
      setSettings(row)
      setMsg('Saved.')
    } catch (e) {
      setError(e?.message || 'Save failed')
    }
  }

  return { settings, setSettings, loading, error, msg, load, save }
}

export function usePricingPlans() {
  const [plans, setPlans] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [msg, setMsg] = useState('')

  const load = useCallback(async () => {
    setError('')
    let rows = await apiFetch('/admin/pricing/plans')
    if (!Array.isArray(rows) || rows.length === 0) {
      await apiFetch('/admin/pricing/seed', { method: 'POST', body: '{}' })
      rows = await apiFetch('/admin/pricing/plans')
    }
    setPlans(Array.isArray(rows) ? rows : [])
  }, [])

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      setLoading(true)
      try {
        await load()
      } catch (e) {
        if (!cancelled) setError(e?.message || 'Could not load plans')
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => { cancelled = true }
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
      await load()
      setMsg('Default VoxBulk plans seeded.')
    } catch (e) {
      setError(e?.message || 'Seed failed')
    }
  }

  return { plans, loading, error, msg, load, savePlan, seed }
}
