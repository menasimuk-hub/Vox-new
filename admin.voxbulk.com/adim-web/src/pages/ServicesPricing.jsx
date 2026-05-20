import React, { useCallback, useEffect, useState } from 'react'
import { apiFetch } from '../lib/api'

function money(pence) {
  return `£${(Number(pence || 0) / 100).toFixed(2)}`
}

export default function ServicesPricing() {
  const [services, setServices] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [preview, setPreview] = useState(null)
  const [previewForm, setPreviewForm] = useState({ service_code: 'survey', recipient_count: 100, delivery: 'ai_call' })
  const [savingRuleId, setSavingRuleId] = useState('')

  const load = useCallback(async () => {
    setError('')
    const rows = await apiFetch('/admin/platform-services')
    setServices(Array.isArray(rows) ? rows : [])
  }, [])

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      setLoading(true)
      try {
        await load()
      } catch (e) {
        if (!cancelled) setError(e?.message || 'Could not load services')
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [load])

  const saveRule = async (rule) => {
    setSavingRuleId(rule.id)
    setError('')
    try {
      await apiFetch(`/admin/platform-services/pricing-rules/${encodeURIComponent(rule.id)}`, {
        method: 'PUT',
        body: JSON.stringify(rule),
      })
      await load()
    } catch (e) {
      setError(e?.message || 'Save failed')
    } finally {
      setSavingRuleId('')
    }
  }

  const runPreview = async () => {
    setError('')
    try {
      const res = await apiFetch('/admin/platform-services/quote-preview', {
        method: 'POST',
        body: JSON.stringify({
          service_code: previewForm.service_code,
          recipient_count: Number(previewForm.recipient_count) || 0,
          options: previewForm.service_code === 'interview' ? { delivery: previewForm.delivery } : {},
        }),
      })
      setPreview(res)
    } catch (e) {
      setError(e?.message || 'Preview failed')
    }
  }

  return (
    <>
      <div className="pageTop">
        <div>
          <h1>Services &amp; pricing</h1>
          <p>Configure standalone Survey and Interview pricing. Clinic subscription packages remain under Packages &amp; Pricing.</p>
        </div>
      </div>

      {error ? <div className="note" style={{ borderColor: 'rgba(220,38,38,0.35)', marginBottom: 12 }}>{error}</div> : null}
      {loading ? <div className="card"><div className="cardBody muted">Loading…</div></div> : null}

      {!loading &&
        services.map((svc) => (
          <div className="card" key={svc.id} style={{ marginBottom: 16 }}>
            <div className="cardHead">
              <h3>{svc.name}</h3>
              <span className="pill p-cyan">{svc.code}</span>
            </div>
            <div className="cardBody">
              <p className="muted" style={{ marginTop: 0 }}>{svc.description}</p>
              {(svc.pricing_rules || []).map((rule) => (
                <div key={rule.id} className="miniGrid" style={{ marginBottom: 14, paddingBottom: 14, borderBottom: '1px solid var(--b1)' }}>
                  <div className="mini"><label>Label</label><input className="input" value={rule.label || ''} onChange={(e) => rule.label = e.target.value} /></div>
                  <div className="mini"><label>Channel</label><input className="input" value={rule.channel || ''} onChange={(e) => rule.channel = e.target.value} /></div>
                  <div className="mini"><label>Rule type</label><input className="input" value={rule.rule_type || ''} onChange={(e) => rule.rule_type = e.target.value} /></div>
                  <div className="mini"><label>Base fee (pence)</label><input className="input" type="number" value={rule.base_fee_pence ?? 0} onChange={(e) => rule.base_fee_pence = Number(e.target.value)} /></div>
                  <div className="mini"><label>Unit price (pence)</label><input className="input" type="number" value={rule.unit_price_pence ?? 0} onChange={(e) => rule.unit_price_pence = Number(e.target.value)} /></div>
                  <div className="mini"><label>Bundle size</label><input className="input" type="number" value={rule.bundle_size ?? ''} onChange={(e) => rule.bundle_size = e.target.value ? Number(e.target.value) : null} /></div>
                  <div className="mini"><label>Bundle price (pence)</label><input className="input" type="number" value={rule.bundle_price_pence ?? ''} onChange={(e) => rule.bundle_price_pence = e.target.value ? Number(e.target.value) : null} /></div>
                  <div className="actions" style={{ gridColumn: '1 / -1' }}>
                    <button type="button" className="btn primary" disabled={savingRuleId === rule.id} onClick={() => saveRule(rule)}>
                      {savingRuleId === rule.id ? 'Saving…' : 'Save rule'}
                    </button>
                    <span className="muted" style={{ fontSize: 12 }}>
                      Preview: {rule.rule_type === 'bundle' ? `${rule.bundle_size} @ ${money(rule.bundle_price_pence)}` : `${money(rule.unit_price_pence)}/unit`}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))}

      <div className="card">
        <div className="cardHead"><h3>Quote preview calculator</h3></div>
        <div className="cardBody">
          <div className="miniGrid">
            <div className="mini">
              <label>Service</label>
              <select className="input" value={previewForm.service_code} onChange={(e) => setPreviewForm((f) => ({ ...f, service_code: e.target.value }))}>
                <option value="survey">Survey</option>
                <option value="interview">Interview</option>
              </select>
            </div>
            <div className="mini">
              <label>Contacts</label>
              <input className="input" type="number" value={previewForm.recipient_count} onChange={(e) => setPreviewForm((f) => ({ ...f, recipient_count: e.target.value }))} />
            </div>
            {previewForm.service_code === 'interview' ? (
              <div className="mini">
                <label>Delivery</label>
                <select className="input" value={previewForm.delivery} onChange={(e) => setPreviewForm((f) => ({ ...f, delivery: e.target.value }))}>
                  <option value="ai_call">AI call</option>
                  <option value="zoom">Zoom</option>
                </select>
              </div>
            ) : null}
          </div>
          <div className="actions" style={{ marginTop: 12 }}>
            <button type="button" className="btn primary" onClick={runPreview}>Calculate quote</button>
          </div>
          {preview ? (
            <div className="note" style={{ marginTop: 12 }}>
              <strong>{preview.total_gbp}</strong> for {preview.recipient_count} contacts
              <ul style={{ margin: '8px 0 0', paddingLeft: 18 }}>
                {(preview.lines || []).map((l, i) => (
                  <li key={i}>{l.detail || l.label}</li>
                ))}
              </ul>
            </div>
          ) : null}
        </div>
      </div>
    </>
  )
}
