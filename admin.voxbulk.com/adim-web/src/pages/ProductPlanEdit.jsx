import React, { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { apiFetch } from '../lib/api'

const emptyDraft = {
  code: '',
  name: '',
  price_gbp_pence: 19900,
  interval: 'monthly',
  description: '',
  featuresText: '',
  calls_included: 300,
  whatsapp_included: 500,
  sms_included: 300,
  overage_per_min_pence: 20,
  trial_days_default: 15,
  service_kind: 'dental',
  sort_order: 100,
  is_active: true,
}

export default function ProductPlanEdit() {
  const { planId } = useParams()
  const navigate = useNavigate()
  const isNew = planId === 'new'
  const [draft, setDraft] = useState(emptyDraft)
  const [loading, setLoading] = useState(!isNew)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [msg, setMsg] = useState('')

  useEffect(() => {
    if (isNew) return
    let cancelled = false
    ;(async () => {
      setLoading(true)
      setError('')
      try {
        const row = await apiFetch(`/admin/products/plans/${encodeURIComponent(planId)}`)
        if (cancelled) return
        setDraft({
          code: row.code || '',
          name: row.name || '',
          price_gbp_pence: row.price_gbp_pence ?? 0,
          interval: row.interval || 'monthly',
          description: row.description || '',
          featuresText: Array.isArray(row.features) ? row.features.join('\n') : '',
          calls_included: row.calls_included ?? 0,
          whatsapp_included: row.whatsapp_included ?? 0,
          sms_included: row.sms_included ?? 0,
          overage_per_min_pence: row.overage_per_min_pence ?? 0,
          trial_days_default: row.trial_days_default ?? 0,
          service_kind: row.service_kind || 'dental',
          sort_order: row.sort_order ?? 100,
          is_active: Boolean(row.is_active),
        })
      } catch (e) {
        if (!cancelled) setError(e?.message || 'Could not load plan')
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [isNew, planId])

  const save = async () => {
    setSaving(true)
    setError('')
    setMsg('')
    const features = String(draft.featuresText || '')
      .split('\n')
      .map((s) => s.trim())
      .filter(Boolean)
    const payload = {
      name: draft.name,
      price_gbp_pence: Number(draft.price_gbp_pence) || 0,
      interval: draft.interval,
      description: draft.description,
      features,
      calls_included: Number(draft.calls_included) || 0,
      whatsapp_included: Number(draft.whatsapp_included) || 0,
      sms_included: Number(draft.sms_included) || 0,
      overage_per_min_pence: Number(draft.overage_per_min_pence) || 0,
      trial_days_default: Number(draft.trial_days_default) || 0,
      service_kind: draft.service_kind,
      sort_order: Number(draft.sort_order) || 100,
      is_active: Boolean(draft.is_active),
    }
    try {
      if (isNew) {
        const created = await apiFetch('/admin/products/plans', {
          method: 'POST',
          body: JSON.stringify({ ...payload, code: draft.code }),
        })
        setMsg('Plan created.')
        navigate(`/billing/products/plan/${created.id}/edit`, { replace: true })
      } else {
        await apiFetch(`/admin/products/plans/${encodeURIComponent(planId)}`, {
          method: 'PUT',
          body: JSON.stringify(payload),
        })
        setMsg('Plan saved.')
      }
    } catch (e) {
      setError(e?.message || 'Save failed')
    } finally {
      setSaving(false)
    }
  }

  if (loading) return <p className="muted" style={{ padding: 24 }}>Loading…</p>

  return (
    <>
      <div className="pageTop">
        <div>
          <Link to="/billing/products" className="muted" style={{ fontSize: 13 }}>
            ← Back to products hub
          </Link>
          <h1 style={{ marginTop: 8 }}>{isNew ? 'New subscription plan' : 'Edit subscription plan'}</h1>
          {!isNew ? <p className="muted">Code: <code>{draft.code}</code></p> : null}
        </div>
        <div className="actions">
          <button type="button" className="btn primary" disabled={saving} onClick={save}>
            {saving ? 'Saving…' : 'Save plan'}
          </button>
        </div>
      </div>

      {error ? <div className="note noteWarn">{error}</div> : null}
      {msg ? <div className="note">{msg}</div> : null}

      <div className="pageShell productsPlanFormShell">
        <section className="card adminPackageEditor">
          <div className="cardHead">
            <div>
              <h3>{isNew ? 'Plan details' : draft.name || 'Plan details'}</h3>
              <div className="muted packageMeta">{isNew ? 'Create a new subscription product' : `Editing ${draft.code}`}</div>
            </div>
            <button type="button" className="btn primary" disabled={saving} onClick={save}>
              {saving ? 'Saving…' : 'Save plan'}
            </button>
          </div>
          <div className="cardBody adminPackageForm">
          <div className="adminPackageFormRow">
            {isNew ? (
              <label className="label">
                Plan code
                <input
                  className="input"
                  value={draft.code}
                  onChange={(e) => setDraft({ ...draft, code: e.target.value })}
                  placeholder="dental_3"
                />
              </label>
            ) : null}
            <label className="label">
              Plan name
              <input className="input" value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} />
            </label>
            <label className="label">
              Price (pence)
              <input
                className="input"
                type="number"
                min={0}
                value={draft.price_gbp_pence}
                onChange={(e) => setDraft({ ...draft, price_gbp_pence: e.target.value })}
              />
            </label>
            <label className="label">
              Interval
              <select className="input" value={draft.interval} onChange={(e) => setDraft({ ...draft, interval: e.target.value })}>
                <option value="monthly">Monthly</option>
                <option value="yearly">Yearly</option>
              </select>
            </label>
          </div>

          <div className="adminPackageFormRow">
            <label className="label">
              Calls included / month
              <input className="input" type="number" min={0} value={draft.calls_included} onChange={(e) => setDraft({ ...draft, calls_included: e.target.value })} />
            </label>
            <label className="label">
              WhatsApp included / month
              <input className="input" type="number" min={0} value={draft.whatsapp_included} onChange={(e) => setDraft({ ...draft, whatsapp_included: e.target.value })} />
            </label>
            <label className="label">
              SMS included / month
              <input className="input" type="number" min={0} value={draft.sms_included} onChange={(e) => setDraft({ ...draft, sms_included: e.target.value })} />
            </label>
          </div>

          <div className="adminPackageFormRow">
            <label className="label">
              Overage per minute (pence)
              <input className="input" type="number" min={0} value={draft.overage_per_min_pence} onChange={(e) => setDraft({ ...draft, overage_per_min_pence: e.target.value })} />
            </label>
            <label className="label">
              Default trial days
              <input className="input" type="number" min={0} value={draft.trial_days_default} onChange={(e) => setDraft({ ...draft, trial_days_default: e.target.value })} />
            </label>
            <label className="label">
              Service kind
              <select className="input" value={draft.service_kind} onChange={(e) => setDraft({ ...draft, service_kind: e.target.value })}>
                <option value="dental">Dental</option>
                <option value="general">General</option>
              </select>
            </label>
            <label className="label">
              Sort order
              <input className="input" type="number" value={draft.sort_order} onChange={(e) => setDraft({ ...draft, sort_order: e.target.value })} />
            </label>
          </div>

          <label className="label">
            <input type="checkbox" checked={draft.is_active} onChange={(e) => setDraft({ ...draft, is_active: e.target.checked })} />{' '}
            Active (visible on signup + sales offers)
          </label>

          <label className="label">
            Description
            <textarea className="input" rows={3} value={draft.description} onChange={(e) => setDraft({ ...draft, description: e.target.value })} />
          </label>
          <label className="label">
            Features (one per line)
            <textarea className="input featuresTextarea" rows={6} value={draft.featuresText} onChange={(e) => setDraft({ ...draft, featuresText: e.target.value })} />
          </label>
          </div>
        </section>
      </div>
    </>
  )
}
