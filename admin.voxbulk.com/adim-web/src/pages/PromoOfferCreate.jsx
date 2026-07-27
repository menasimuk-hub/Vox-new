import React, { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import PlanPickerSelect from '../components/billing/PlanPickerSelect'
import { apiFetch } from '../lib/api'

const SERVICES = [
  { value: 'voxbulk', label: 'Core subscription' },
  { value: 'survey', label: 'Survey' },
  { value: 'interview', label: 'Interview' },
  { value: 'customer_feedback', label: 'Customer Feedback' },
  { value: 'expo', label: 'Expo' },
]

const BENEFITS = [
  { value: 'free_usage', label: 'Free usage' },
  { value: 'discount', label: 'Discount (% or £)' },
]

const REDEEM_MODES = [
  { value: 'anyone', label: 'Anyone with the code (signup or Dashboard)' },
  { value: 'signup_only', label: 'Signup only' },
  { value: 'admin_only', label: 'Admin apply only' },
]

const emptyDraft = {
  code: '',
  name: '',
  service_kind: 'survey',
  benefit_kind: 'free_usage',
  plan_code: '',
  usage_amount: 20,
  trial_days: 15,
  discount_type: 'percent',
  discount_value: 20,
  redeem_mode: 'anyone',
  max_redemptions: 10,
  expires_in_days: 30,
  prospect_name: '',
  prospect_email: '',
  prospect_phone: '',
}

function usageLabel(service) {
  if (service === 'survey') return 'Free survey contacts'
  if (service === 'interview') return 'Free interviews'
  if (service === 'customer_feedback') return 'Free Feedback units'
  if (service === 'expo') return 'Free Expo days'
  return 'Trial days'
}

export default function PromoOfferCreate() {
  const navigate = useNavigate()
  const [draft, setDraft] = useState(emptyDraft)
  const [plans, setPlans] = useState([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [created, setCreated] = useState(null)
  const [orgQuery, setOrgQuery] = useState('')
  const [orgs, setOrgs] = useState([])
  const [selectedOrgIds, setSelectedOrgIds] = useState([])
  const [applying, setApplying] = useState(false)
  const [applyResult, setApplyResult] = useState(null)

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const data = await apiFetch('/admin/plans')
        if (!cancelled) setPlans(Array.isArray(data) ? data : data?.items || [])
      } catch {
        if (!cancelled) setPlans([])
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [])

  const corePlans = useMemo(
    () =>
      (plans || []).filter((p) => {
        const kind = String(p.service_kind || p.service_code || 'voxbulk').toLowerCase()
        return kind === 'voxbulk' || kind === 'dental' || !kind
      }),
    [plans],
  )

  const setField = (key, value) => setDraft((d) => ({ ...d, [key]: value }))

  const previewLine = useMemo(() => {
    if (draft.benefit_kind === 'discount') {
      if (draft.discount_type === 'percent') {
        return `${draft.discount_value || 0}% off next ${draft.service_kind.replace('_', ' ')} checkout`
      }
      return `£${(Number(draft.discount_value || 0) / 100).toFixed(2)} off next ${draft.service_kind.replace('_', ' ')} checkout`
    }
    if (draft.service_kind === 'voxbulk') {
      return `${draft.trial_days || draft.usage_amount || 0}-day Core trial`
    }
    return `${draft.usage_amount || 0} × ${usageLabel(draft.service_kind).toLowerCase()}`
  }, [draft])

  const onSubmit = async (e) => {
    e.preventDefault()
    setSaving(true)
    setError('')
    try {
      const payload = {
        code: draft.code || undefined,
        name: draft.name || undefined,
        service_kind: draft.service_kind,
        benefit_kind: draft.benefit_kind,
        redeem_mode: draft.redeem_mode,
        max_redemptions: Number(draft.max_redemptions) || 1,
        expires_in_days: Number(draft.expires_in_days) || 30,
        prospect_name: draft.prospect_name || undefined,
        prospect_email: draft.prospect_email || undefined,
        prospect_phone: draft.prospect_phone || undefined,
      }
      if (draft.benefit_kind === 'discount') {
        payload.discount_type = draft.discount_type
        payload.discount_value =
          draft.discount_type === 'fixed_minor'
            ? Math.round(Number(draft.discount_value) || 0)
            : Number(draft.discount_value) || 0
        if (draft.discount_type === 'fixed_minor' && payload.discount_value < 100) {
          // Allow entering pounds in the UI when value looks like pounds (< 100 with type fixed) — treat as pounds.
          // Prefer pence input: if user typed 20 with fixed, convert pounds→pence when < 500 and no decimals intent.
        }
      } else {
        payload.usage_amount = Number(draft.usage_amount) || 0
        if (draft.service_kind === 'voxbulk') {
          payload.plan_code = draft.plan_code || 'starter'
          payload.trial_days = Number(draft.trial_days) || Number(draft.usage_amount) || 15
          payload.usage_amount = payload.trial_days
        }
        if (draft.service_kind === 'expo') {
          payload.trial_days = Number(draft.usage_amount) || 3
        }
        if (draft.service_kind === 'survey') payload.survey_contacts_included = payload.usage_amount
        if (draft.service_kind === 'interview') payload.interview_contacts_included = payload.usage_amount
      }
      if (draft.benefit_kind === 'discount' && draft.discount_type === 'fixed_minor') {
        // UI stores pounds in discount_value_pounds field via discount_value when type fixed — convert £ to pence
        const pounds = Number(draft.discount_value)
        payload.discount_value = Math.round(pounds * 100)
      }
      const res = await apiFetch('/admin/promo-offers', { method: 'POST', body: JSON.stringify(payload) })
      setCreated(res.promo)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not create promo')
    } finally {
      setSaving(false)
    }
  }

  const searchOrgs = async () => {
    try {
      const data = await apiFetch(`/admin/organisations?search=${encodeURIComponent(orgQuery || '')}&limit=30`)
      setOrgs(Array.isArray(data) ? data : data?.items || data?.organisations || [])
    } catch {
      setOrgs([])
    }
  }

  const toggleOrg = (id) => {
    setSelectedOrgIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]))
  }

  const applyToOrgs = async () => {
    if (!created?.id || selectedOrgIds.length === 0) return
    setApplying(true)
    setApplyResult(null)
    try {
      const res = await apiFetch(`/admin/promo-offers/${created.id}/apply`, {
        method: 'POST',
        body: JSON.stringify({ org_ids: selectedOrgIds }),
      })
      setApplyResult(res)
    } catch (err) {
      setApplyResult({ ok: false, error: err instanceof Error ? err.message : 'Apply failed' })
    } finally {
      setApplying(false)
    }
  }

  if (loading) return <div className="page">Loading…</div>

  if (created) {
    return (
      <div className="page" style={{ maxWidth: 720 }}>
        <h1>Promo created</h1>
        <p className="muted">{created.benefit_summary || previewLine}</p>
        <div className="card" style={{ padding: 16, marginBottom: 16 }}>
          <div>
            <strong>Code:</strong> {created.code}
          </div>
          <div style={{ marginTop: 8 }}>
            <strong>Signup link:</strong>{' '}
            <a href={created.signup_url} target="_blank" rel="noreferrer">
              {created.signup_url}
            </a>
          </div>
          <button
            type="button"
            className="btn"
            style={{ marginTop: 12 }}
            onClick={() => navigator.clipboard?.writeText(created.signup_url || created.code)}
          >
            Copy link
          </button>
        </div>

        <h2>Apply to organisations</h2>
        <p className="muted">Select one or more orgs to apply this promo now (Admin apply).</p>
        <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
          <input
            className="input"
            placeholder="Search organisations"
            value={orgQuery}
            onChange={(e) => setOrgQuery(e.target.value)}
          />
          <button type="button" className="btn" onClick={() => void searchOrgs()}>
            Search
          </button>
        </div>
        <div className="card" style={{ maxHeight: 240, overflow: 'auto', padding: 8 }}>
          {orgs.length === 0 ? (
            <p className="muted">Search to find organisations.</p>
          ) : (
            orgs.map((o) => (
              <label key={o.id} style={{ display: 'flex', gap: 8, padding: 6, cursor: 'pointer' }}>
                <input
                  type="checkbox"
                  checked={selectedOrgIds.includes(o.id)}
                  onChange={() => toggleOrg(o.id)}
                />
                <span>
                  {o.name} <span className="muted">{o.id?.slice(0, 8)}</span>
                </span>
              </label>
            ))
          )}
        </div>
        <button
          type="button"
          className="btn primary"
          style={{ marginTop: 12 }}
          disabled={applying || selectedOrgIds.length === 0}
          onClick={() => void applyToOrgs()}
        >
          {applying ? 'Applying…' : `Apply to ${selectedOrgIds.length} org(s)`}
        </button>
        {applyResult ? (
          <pre style={{ marginTop: 12, fontSize: 12 }}>{JSON.stringify(applyResult, null, 2)}</pre>
        ) : null}

        <div style={{ marginTop: 24, display: 'flex', gap: 12 }}>
          <button type="button" className="btn" onClick={() => navigate('/marketing/promo-offers')}>
            Back to list
          </button>
          <button
            type="button"
            className="btn"
            onClick={() => {
              setCreated(null)
              setDraft(emptyDraft)
              setSelectedOrgIds([])
              setApplyResult(null)
            }}
          >
            Create another
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="page" style={{ maxWidth: 720 }}>
      <div style={{ marginBottom: 12 }}>
        <Link to="/marketing/promo-offers">← Promo offers</Link>
      </div>
      <h1>New promo</h1>
      <p className="muted">Pick a service, free usage or discount, then who can redeem it.</p>

      <form onSubmit={onSubmit} className="card" style={{ padding: 20 }}>
        {error ? <p style={{ color: 'crimson' }}>{error}</p> : null}

        <label className="field">
          <span>1. Service</span>
          <select className="input" value={draft.service_kind} onChange={(e) => setField('service_kind', e.target.value)}>
            {SERVICES.map((s) => (
              <option key={s.value} value={s.value}>
                {s.label}
              </option>
            ))}
          </select>
        </label>

        <label className="field">
          <span>2. Benefit</span>
          <select className="input" value={draft.benefit_kind} onChange={(e) => setField('benefit_kind', e.target.value)}>
            {BENEFITS.map((s) => (
              <option key={s.value} value={s.value}>
                {s.label}
              </option>
            ))}
          </select>
        </label>

        {draft.benefit_kind === 'free_usage' ? (
          <>
            {draft.service_kind === 'voxbulk' ? (
              <>
                <label className="field">
                  <span>Plan</span>
                  <PlanPickerSelect
                    plans={corePlans}
                    value={draft.plan_code}
                    onChange={(code) => setField('plan_code', code)}
                  />
                </label>
                <label className="field">
                  <span>Trial days</span>
                  <input
                    className="input"
                    type="number"
                    min={1}
                    value={draft.trial_days}
                    onChange={(e) => setField('trial_days', e.target.value)}
                  />
                </label>
              </>
            ) : (
              <label className="field">
                <span>{usageLabel(draft.service_kind)}</span>
                <input
                  className="input"
                  type="number"
                  min={1}
                  value={draft.usage_amount}
                  onChange={(e) => setField('usage_amount', e.target.value)}
                />
              </label>
            )}
          </>
        ) : (
          <>
            <label className="field">
              <span>Discount type</span>
              <select
                className="input"
                value={draft.discount_type}
                onChange={(e) => setField('discount_type', e.target.value)}
              >
                <option value="percent">Percent off</option>
                <option value="fixed_minor">Fixed £ off</option>
              </select>
            </label>
            <label className="field">
              <span>{draft.discount_type === 'percent' ? 'Percent (1–100)' : 'Pounds (£)'}</span>
              <input
                className="input"
                type="number"
                min={1}
                step={draft.discount_type === 'percent' ? 1 : 0.01}
                value={draft.discount_value}
                onChange={(e) => setField('discount_value', e.target.value)}
              />
            </label>
          </>
        )}

        <label className="field">
          <span>3. Who can redeem</span>
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
        </label>
        <label className="field">
          <span>Expires in (days)</span>
          <input
            className="input"
            type="number"
            min={1}
            value={draft.expires_in_days}
            onChange={(e) => setField('expires_in_days', e.target.value)}
          />
        </label>

        <label className="field">
          <span>Name</span>
          <input
            className="input"
            value={draft.name}
            onChange={(e) => setField('name', e.target.value)}
            placeholder="Display name for this promo code"
          />
        </label>
        <label className="field">
          <span>Code (optional)</span>
          <input className="input" value={draft.code} onChange={(e) => setField('code', e.target.value)} placeholder="Auto if blank" />
        </label>

        <p className="muted">Preview: {previewLine}</p>

        <button type="submit" className="btn primary" disabled={saving}>
          {saving ? 'Creating…' : 'Create promo'}
        </button>
      </form>
    </div>
  )
}
