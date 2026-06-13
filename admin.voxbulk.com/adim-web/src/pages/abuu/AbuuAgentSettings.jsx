import React, { useCallback, useEffect, useState } from 'react'
import {
  fetchAbuuAgentSettings,
  fetchAbuuRestaurants,
  fetchAbuuRestaurantAgentSettings,
  patchAbuuAgentSettings,
  patchAbuuRestaurantAgentSettings,
} from '../../lib/abuuApi'

const GLOBAL_FIELDS = [
  ['business_name_en', 'Business name (EN)'],
  ['business_name_ar', 'Business name (AR)'],
  ['default_delivery_radius_km', 'Default delivery radius (km)', 'number'],
  ['default_prep_minutes', 'Default prep time (minutes)', 'number'],
  ['default_min_order_agorot', 'Minimum order (agorot)', 'number'],
  ['default_delivery_fee_agorot', 'Delivery fee (agorot)', 'number'],
  ['greeting_template_en', 'Greeting template (EN)'],
  ['greeting_template_ar', 'Greeting template (AR)'],
  ['refund_policy_en', 'Refund policy (EN)'],
  ['refund_policy_ar', 'Refund policy (AR)'],
  ['cancellation_policy_en', 'Cancellation policy (EN)'],
  ['cancellation_policy_ar', 'Cancellation policy (AR)'],
  ['allergen_disclaimer_en', 'Allergen disclaimer (EN)'],
  ['allergen_disclaimer_ar', 'Allergen disclaimer (AR)'],
  ['escalation_rules_en', 'Escalation rules (EN)'],
  ['escalation_rules_ar', 'Escalation rules (AR)'],
]

export default function AbuuAgentSettings() {
  const [tab, setTab] = useState('global')
  const [settings, setSettings] = useState(null)
  const [skills, setSkills] = useState([])
  const [restaurants, setRestaurants] = useState([])
  const [restaurantId, setRestaurantId] = useState('')
  const [override, setOverride] = useState(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const loadGlobal = useCallback(async () => {
    const data = await fetchAbuuAgentSettings()
    setSettings(data.settings || {})
    setSkills(Array.isArray(data.skills) ? data.skills : [])
  }, [])

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        await loadGlobal()
        const rows = await fetchAbuuRestaurants()
        if (!cancelled) {
          setRestaurants(Array.isArray(rows) ? rows : [])
          if (rows?.[0]?.id) setRestaurantId(rows[0].id)
        }
      } catch (e) {
        if (!cancelled) setError(e.message || 'Load failed')
      }
    })()
    return () => {
      cancelled = true
    }
  }, [loadGlobal])

  useEffect(() => {
    if (!restaurantId) return
    let cancelled = false
    ;(async () => {
      try {
        const data = await fetchAbuuRestaurantAgentSettings(restaurantId)
        if (!cancelled) setOverride(data.override || {})
      } catch (e) {
        if (!cancelled) setError(e.message || 'Load restaurant settings failed')
      }
    })()
    return () => {
      cancelled = true
    }
  }, [restaurantId])

  const saveGlobal = async () => {
    setBusy(true)
    setError('')
    try {
      const saved = await patchAbuuAgentSettings(settings)
      setSettings(saved)
      await loadGlobal()
    } catch (e) {
      setError(e.message || 'Save failed')
    } finally {
      setBusy(false)
    }
  }

  const saveOverride = async () => {
    if (!restaurantId) return
    setBusy(true)
    setError('')
    try {
      const saved = await patchAbuuRestaurantAgentSettings(restaurantId, override || {})
      setOverride(saved)
    } catch (e) {
      setError(e.message || 'Save failed')
    } finally {
      setBusy(false)
    }
  }

  const toggleSkill = async (name, enabled) => {
    const next = { ...(settings.skills_config || {}) }
    next[name] = { enabled }
    const payload = { ...settings, skills_config: next }
    setSettings(payload)
    await patchAbuuAgentSettings({ skills_config: next })
    await loadGlobal()
  }

  if (!settings) return <p className='muted'>Loading agent settings…</p>

  return (
    <div className='card'>
      <h2>Agent settings</h2>
      <p className='muted'>KB facts, business policies, and WhatsApp skill toggles for Abuu.</p>
      {error ? <p className='error'>{error}</p> : null}
      <div className='pricingSubnav' style={{ marginBottom: 16 }}>
        {['global', 'restaurant', 'skills'].map((key) => (
          <button
            key={key}
            type='button'
            className={`pricingSubnavLink${tab === key ? ' on' : ''}`}
            onClick={() => setTab(key)}
          >
            {key === 'global' ? 'Global KB' : key === 'restaurant' ? 'Restaurant overrides' : 'Skills'}
          </button>
        ))}
      </div>

      {tab === 'global' ? (
        <div className='form'>
          {GLOBAL_FIELDS.map(([key, label, type]) => (
            <label key={key}>
              {label}
              <input
                type={type || 'text'}
                value={settings[key] ?? ''}
                onChange={(e) =>
                  setSettings({
                    ...settings,
                    [key]: type === 'number' ? Number(e.target.value) : e.target.value,
                  })
                }
              />
            </label>
          ))}
          <button type='button' className='btn primary' disabled={busy} onClick={saveGlobal}>
            Save global settings
          </button>
        </div>
      ) : null}

      {tab === 'restaurant' ? (
        <div className='form'>
          <label>
            Restaurant
            <select value={restaurantId} onChange={(e) => setRestaurantId(e.target.value)}>
              {restaurants.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.name_en}
                </option>
              ))}
            </select>
          </label>
          {['prep_minutes', 'min_order_agorot', 'delivery_fee_agorot', 'delivery_radius_km'].map((key) => (
            <label key={key}>
              {key}
              <input
                type='number'
                value={override?.[key] ?? ''}
                onChange={(e) => setOverride({ ...(override || {}), [key]: e.target.value ? Number(e.target.value) : null })}
              />
            </label>
          ))}
          {['notes_en', 'notes_ar', 'greeting_template_en', 'greeting_template_ar'].map((key) => (
            <label key={key}>
              {key}
              <textarea
                rows={2}
                value={override?.[key] ?? ''}
                onChange={(e) => setOverride({ ...(override || {}), [key]: e.target.value })}
              />
            </label>
          ))}
          <button type='button' className='btn primary' disabled={busy} onClick={saveOverride}>
            Save restaurant override
          </button>
        </div>
      ) : null}

      {tab === 'skills' ? (
        <ul style={{ listStyle: 'none', padding: 0 }}>
          {skills.map((skill) => (
            <li key={skill.name} style={{ display: 'flex', gap: 12, alignItems: 'center', marginBottom: 8 }}>
              <input
                type='checkbox'
                checked={!!skill.enabled}
                onChange={(e) => toggleSkill(skill.name, e.target.checked)}
              />
              <div>
                <strong>{skill.name}</strong>
                <div className='muted'>{skill.description}</div>
              </div>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  )
}
