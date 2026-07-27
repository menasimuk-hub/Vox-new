import React, { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { apiFetch } from '../lib/api'

const REDEEM_MODES = [
  { value: 'anyone', label: 'Anyone with the code (signup or Dashboard)' },
  { value: 'signup_only', label: 'Signup only' },
  { value: 'admin_only', label: 'Admin apply only' },
]

function daysUntil(expiresAt) {
  if (!expiresAt) return 30
  const end = new Date(expiresAt).getTime()
  if (Number.isNaN(end)) return 30
  const days = Math.ceil((end - Date.now()) / (24 * 60 * 60 * 1000))
  return Math.max(1, days)
}

export default function PromoOfferEdit() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [promo, setPromo] = useState(null)
  const [draft, setDraft] = useState({
    name: '',
    max_redemptions: 1,
    expires_in_days: 30,
    redeem_mode: 'anyone',
    is_active: true,
  })

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      setLoading(true)
      setError('')
      try {
        const data = await apiFetch(`/admin/promo-offers/${id}`)
        if (cancelled) return
        setPromo(data)
        setDraft({
          name: data?.name || data?.code || '',
          max_redemptions: Number(data?.max_redemptions || 1),
          expires_in_days: daysUntil(data?.expires_at),
          redeem_mode: data?.redeem_mode || 'anyone',
          is_active: Boolean(data?.is_active),
        })
      } catch (e) {
        if (!cancelled) setError(e?.message || 'Could not load promo offer')
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [id])

  const setField = (key, value) => setDraft((d) => ({ ...d, [key]: value }))

  const summary = useMemo(() => {
    if (!promo) return ''
    return promo.benefit_summary || promo.offer_type || ''
  }, [promo])

  const onSubmit = async (e) => {
    e.preventDefault()
    const name = String(draft.name || '').trim()
    if (!name) {
      setError('Name is required')
      return
    }
    setSaving(true)
    setError('')
    try {
      await apiFetch(`/admin/promo-offers/${id}`, {
        method: 'PATCH',
        body: JSON.stringify({
          name,
          max_redemptions: Number(draft.max_redemptions) || 1,
          expires_in_days: Number(draft.expires_in_days) || 30,
          redeem_mode: draft.redeem_mode,
          is_active: Boolean(draft.is_active),
        }),
      })
      navigate('/marketing/promo-offers?updated=1')
    } catch (err) {
      setError(err?.message || 'Could not save promo offer')
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return (
      <div className="page" style={{ maxWidth: 720 }}>
        <p className="muted">Loading promo…</p>
      </div>
    )
  }

  if (!promo) {
    return (
      <div className="page" style={{ maxWidth: 720 }}>
        <div style={{ marginBottom: 12 }}>
          <Link to="/marketing/promo-offers">← Promo offers</Link>
        </div>
        <p style={{ color: 'crimson' }}>{error || 'Promo not found'}</p>
      </div>
    )
  }

  return (
    <div className="page" style={{ maxWidth: 720 }}>
      <div style={{ marginBottom: 12 }}>
        <Link to="/marketing/promo-offers">← Promo offers</Link>
      </div>
      <h1>Edit promo</h1>
      <p className="muted">
        Code <strong>{promo.code}</strong>
        {summary ? ` · ${summary}` : ''}
      </p>

      <form onSubmit={onSubmit} className="card" style={{ padding: 20 }}>
        {error ? <p style={{ color: 'crimson' }}>{error}</p> : null}

        <label className="field">
          <span>Name</span>
          <input
            className="input"
            value={draft.name}
            onChange={(e) => setField('name', e.target.value)}
            placeholder="Display name for this promo code"
            required
          />
        </label>

        <label className="field">
          <span>Who can redeem</span>
          <select className="input" value={draft.redeem_mode} onChange={(e) => setField('redeem_mode', e.target.value)}>
            {REDEEM_MODES.map((s) => (
              <option key={s.value} value={s.value}>
                {s.label}
              </option>
            ))}
          </select>
        </label>

        <label className="field">
          <span>Max redemptions</span>
          <input
            className="input"
            type="number"
            min={1}
            value={draft.max_redemptions}
            onChange={(e) => setField('max_redemptions', e.target.value)}
          />
          <span className="muted" style={{ fontSize: 12 }}>
            Already used: {promo.redemption_count || 0}
          </span>
        </label>

        <label className="field">
          <span>Expires in (days from now)</span>
          <input
            className="input"
            type="number"
            min={1}
            value={draft.expires_in_days}
            onChange={(e) => setField('expires_in_days', e.target.value)}
          />
        </label>

        <label className="field" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <input
            type="checkbox"
            checked={Boolean(draft.is_active)}
            onChange={(e) => setField('is_active', e.target.checked)}
          />
          <span>Active</span>
        </label>

        <div style={{ display: 'flex', gap: 12, marginTop: 16 }}>
          <button type="submit" className="btn primary" disabled={saving}>
            {saving ? 'Saving…' : 'Save changes'}
          </button>
          <button type="button" className="btn" onClick={() => navigate('/marketing/promo-offers')}>
            Cancel
          </button>
        </div>
      </form>
    </div>
  )
}
