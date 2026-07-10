import React, { useCallback, useEffect, useState } from 'react'
import { apiFetch } from '../lib/api'

function parseFeatures(row) {
  const raw = row?.features_json
  if (!raw) return []
  try {
    const j = JSON.parse(raw)
    return Array.isArray(j) ? j.map(String) : []
  } catch {
    return []
  }
}

function formatPrice(pence) {
  return `£${(Number(pence || 0) / 100).toFixed(0)}`
}

export default function PackagesPricing() {
  const [plans, setPlans] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [savingId, setSavingId] = useState('')
  const [drafts, setDrafts] = useState({})

  const load = useCallback(async () => {
    setError('')
    const rows = await apiFetch('/admin/billing/plans')
    const list = Array.isArray(rows) ? rows : []
    setPlans(list)
    const next = {}
    for (const p of list) {
      next[p.id] = {
        name: p.name || '',
        price_gbp_pence: p.price_gbp_pence ?? 0,
        interval: p.interval || 'monthly',
        description: p.description || '',
        featuresText: parseFeatures(p).join('\n'),
      }
    }
    setDrafts(next)
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
    return () => {
      cancelled = true
    }
  }, [load])

  const updateDraft = (id, field, value) => {
    setDrafts((d) => ({
      ...d,
      [id]: { ...(d[id] || {}), [field]: value },
    }))
  }

  const savePlan = async (planId) => {
    const d = drafts[planId]
    if (!d) return
    setSavingId(planId)
    setError('')
    try {
      const features = String(d.featuresText || '')
        .split('\n')
        .map((s) => s.trim())
        .filter(Boolean)
      await apiFetch(`/admin/billing/plans/${encodeURIComponent(planId)}`, {
        method: 'PUT',
        body: JSON.stringify({
          name: d.name,
          price_gbp_pence: Number(d.price_gbp_pence) || 0,
          interval: d.interval || 'monthly',
          description: d.description,
          features,
        }),
      })
      await load()
    } catch (e) {
      setError(e?.message || 'Save failed')
    } finally {
      setSavingId('')
    }
  }

  return (
    <>
      <div className="pageTop packagesTop">
        <div>
          <h1>Packages &amp; Pricing</h1>
          <p>
            Manage public package cards shown to customers. Changes here are read by the customer dashboard Packages page.
          </p>
        </div>
        <div className="actions">
          <button type="button" className="btn soft" onClick={() => load()} disabled={loading}>
            Refresh
          </button>
        </div>
      </div>

      {error ? (
        <div className="card" style={{ marginBottom: 16, borderColor: '#fecaca' }}>
          <div className="cardBody" style={{ color: '#b91c1c', fontSize: 14 }}>
            {error}
          </div>
        </div>
      ) : null}

      {loading ? (
        <div className="note">Loading plans…</div>
      ) : (
        <>
          <div className="adminPackagePreviewGrid">
            {plans.map((p, idx) => {
              const d = drafts[p.id] || {}
              const features = String(d.featuresText || '')
                .split('\n')
                .map((s) => s.trim())
                .filter(Boolean)
              return (
                <article className={`adminPackagePreview ${idx === 1 ? 'highlight' : ''}`} key={`${p.id}-preview`}>
                  <div className="adminPackagePreviewTop">
                    <span className="packageCode">{p.code}</span>
                    {idx === 1 ? <span className="pill p-green">Most popular</span> : null}
                  </div>
                  <h2>{d.name || p.name}</h2>
                  <div className="packagePrice">
                    {formatPrice(d.price_gbp_pence)}
                    <span>/{d.interval === 'yearly' ? 'yr' : 'mo'}</span>
                  </div>
                  <p>{d.description || 'Add a short customer-facing description for this plan.'}</p>
                  <div className="packageFeatureList">
                    {features.slice(0, 6).map((f) => (
                      <div className="packageFeatureItem" key={f}>
                        <span>✓</span>
                        <strong>{f}</strong>
                      </div>
                    ))}
                  </div>
                </article>
              )
            })}
          </div>

          <div className="adminPackageEditorGrid">
            {plans.map((p) => {
              const d = drafts[p.id] || {}
              return (
                <article key={p.id} className="card adminPackageEditor">
                  <div className="cardHead">
                    <div>
                      <h3>{p.name}</h3>
                      <div className="muted packageMeta">
                        <code>{p.code}</code> · {p.id.slice(0, 8)}…
                      </div>
                    </div>
                    <button
                      type="button"
                      className="btn primary"
                      disabled={savingId === p.id}
                      onClick={() => savePlan(p.id)}
                    >
                      {savingId === p.id ? 'Saving…' : 'Save'}
                    </button>
                  </div>
                  <div className="cardBody adminPackageForm">
                    <div className="adminPackageFormRow">
                      <label className="label">
                        Plan name
                        <input
                          className="input"
                          value={d.name ?? ''}
                          onChange={(e) => updateDraft(p.id, 'name', e.target.value)}
                        />
                      </label>
                      <label className="label">
                        Price in pence
                        <input
                          className="input"
                          type="number"
                          min={0}
                          value={d.price_gbp_pence ?? 0}
                          onChange={(e) => updateDraft(p.id, 'price_gbp_pence', e.target.value)}
                        />
                      </label>
                      <label className="label">
                        Interval
                        <select
                          className="input"
                          value={d.interval || 'monthly'}
                          onChange={(e) => updateDraft(p.id, 'interval', e.target.value)}
                        >
                          <option value="monthly">Monthly</option>
                          <option value="yearly">Yearly</option>
                        </select>
                      </label>
                    </div>
                    <label className="label">
                      Short description
                      <textarea
                        className="input"
                        rows={3}
                        value={d.description ?? ''}
                        onChange={(e) => updateDraft(p.id, 'description', e.target.value)}
                        placeholder="Shown on the customer dashboard package card"
                      />
                    </label>
                    <label className="label">
                      Features
                      <textarea
                        className="input featuresTextarea"
                        rows={7}
                        value={d.featuresText ?? ''}
                        onChange={(e) => updateDraft(p.id, 'featuresText', e.target.value)}
                        placeholder="One feature per line"
                      />
                    </label>
                  </div>
                </article>
              )
            })}
          </div>
        </>
      )}
    </>
  )
}
