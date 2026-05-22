import React, { useCallback, useEffect, useState } from 'react'
import { apiFetch } from '../lib/api'

function money(pence) {
  return `£${(Number(pence || 0) / 100).toFixed(2)}`
}

function rulePreview(rule) {
  if (rule.rule_type === 'bundle') {
    return `${rule.bundle_size || '—'} @ ${money(rule.bundle_price_pence)}`
  }
  return `${money(rule.unit_price_pence)}/unit`
}

function Field({ label, children }) {
  return (
    <label className='svcPriceField'>
      <span>{label}</span>
      {children}
    </label>
  )
}

export default function ServicesPricing() {
  const [services, setServices] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [preview, setPreview] = useState(null)
  const [previewForm, setPreviewForm] = useState({ service_code: 'survey', recipient_count: 100, delivery: 'ai_call' })
  const [savingRuleId, setSavingRuleId] = useState('')
  const [openRuleId, setOpenRuleId] = useState('')

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

  const patchRule = (serviceId, ruleId, field, value) => {
    setServices((rows) =>
      rows.map((svc) => {
        if (svc.id !== serviceId) return svc
        return {
          ...svc,
          pricing_rules: (svc.pricing_rules || []).map((rule) =>
            rule.id === ruleId ? { ...rule, [field]: value } : rule,
          ),
        }
      }),
    )
  }

  const saveRule = async (rule) => {
    setSavingRuleId(rule.id)
    setError('')
    try {
      await apiFetch(`/admin/platform-services/pricing-rules/${encodeURIComponent(rule.id)}`, {
        method: 'PUT',
        body: JSON.stringify(rule),
      })
      await load()
      setOpenRuleId('')
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

  const ruleCount = services.reduce((n, s) => n + (s.pricing_rules || []).length, 0)

  return (
    <div className='svcPricePage'>
      <div className='pageTop'>
        <div>
          <h1>Services &amp; pricing</h1>
          <p className='muted'>Survey and Interview pricing rules. Click a row to edit all fields.</p>
        </div>
        <div className='actions'>
          <span className='pill p-cyan'>{ruleCount} rules</span>
        </div>
      </div>

      {error ? <div className='note noteWarn svcPriceNote'>{error}</div> : null}
      {loading ? <div className='card'><div className='cardBody muted'>Loading…</div></div> : null}

      {!loading ? (
        <div className='svcPriceLayout'>
          {services.map((svc) => (
            <section className='card svcPriceService' key={svc.id}>
              <div className='svcPriceServiceHead'>
                <div>
                  <h3>{svc.name}</h3>
                  <p className='muted'>{svc.description}</p>
                </div>
                <span className='pill p-cyan'>{svc.code}</span>
              </div>

              <div className='svcPriceRuleList'>
                {(svc.pricing_rules || []).map((rule) => {
                  const open = openRuleId === rule.id
                  return (
                    <div key={rule.id} className={`svcPriceRuleItem${open ? ' isOpen' : ''}`}>
                      <button type='button' className='svcPriceRuleSummary' onClick={() => setOpenRuleId(open ? '' : rule.id)}>
                        <div>
                          <strong>{rule.label || 'Pricing rule'}</strong>
                          <span className='muted'>{rule.channel} · {rule.rule_type} · {rulePreview(rule)}</span>
                        </div>
                        <span className='svcPriceRuleToggle'>{open ? 'Close' : 'Edit'}</span>
                      </button>

                      {open ? (
                        <div className='svcPriceRuleEditor'>
                          <div className='svcPriceFieldGrid'>
                            <Field label='Label'>
                              <input className='input inputCompact' value={rule.label || ''} onChange={(e) => patchRule(svc.id, rule.id, 'label', e.target.value)} />
                            </Field>
                            <Field label='Channel'>
                              <input className='input inputCompact' value={rule.channel || ''} onChange={(e) => patchRule(svc.id, rule.id, 'channel', e.target.value)} />
                            </Field>
                            <Field label='Rule type'>
                              <input className='input inputCompact' value={rule.rule_type || ''} onChange={(e) => patchRule(svc.id, rule.id, 'rule_type', e.target.value)} />
                            </Field>
                            <Field label='Base fee (pence)'>
                              <input className='input inputCompact' type='number' value={rule.base_fee_pence ?? 0} onChange={(e) => patchRule(svc.id, rule.id, 'base_fee_pence', Number(e.target.value))} />
                            </Field>
                            <Field label='Unit price (pence)'>
                              <input className='input inputCompact' type='number' value={rule.unit_price_pence ?? 0} onChange={(e) => patchRule(svc.id, rule.id, 'unit_price_pence', Number(e.target.value))} />
                            </Field>
                            <Field label='Bundle size'>
                              <input className='input inputCompact' type='number' value={rule.bundle_size ?? ''} onChange={(e) => patchRule(svc.id, rule.id, 'bundle_size', e.target.value ? Number(e.target.value) : null)} />
                            </Field>
                            <Field label='Bundle price (pence)'>
                              <input className='input inputCompact' type='number' value={rule.bundle_price_pence ?? ''} onChange={(e) => patchRule(svc.id, rule.id, 'bundle_price_pence', e.target.value ? Number(e.target.value) : null)} />
                            </Field>
                            <Field label='Included units'>
                              <input className='input inputCompact' type='number' value={rule.included_units ?? ''} onChange={(e) => patchRule(svc.id, rule.id, 'included_units', e.target.value ? Number(e.target.value) : null)} />
                            </Field>
                            <Field label='Overage / unit (pence)'>
                              <input className='input inputCompact' type='number' value={rule.overage_unit_price_pence ?? ''} onChange={(e) => patchRule(svc.id, rule.id, 'overage_unit_price_pence', e.target.value ? Number(e.target.value) : null)} />
                            </Field>
                            <Field label='Sort order'>
                              <input className='input inputCompact' type='number' value={rule.sort_order ?? 100} onChange={(e) => patchRule(svc.id, rule.id, 'sort_order', Number(e.target.value))} />
                            </Field>
                            <Field label='Active'>
                              <select className='input inputCompact' value={rule.is_active === false ? '0' : '1'} onChange={(e) => patchRule(svc.id, rule.id, 'is_active', e.target.value === '1')}>
                                <option value='1'>Yes</option>
                                <option value='0'>No</option>
                              </select>
                            </Field>
                          </div>
                          <Field label='Notes'>
                            <input className='input inputCompact' value={rule.notes || ''} onChange={(e) => patchRule(svc.id, rule.id, 'notes', e.target.value)} />
                          </Field>
                          <div className='actions svcPriceRuleActions'>
                            <button type='button' className='btn primary' disabled={savingRuleId === rule.id} onClick={() => saveRule(rule)}>
                              {savingRuleId === rule.id ? 'Saving…' : 'Save rule'}
                            </button>
                            <span className='muted'>Preview: {rulePreview(rule)}</span>
                          </div>
                        </div>
                      ) : null}
                    </div>
                  )
                })}
              </div>
            </section>
          ))}

          <section className='card svcPricePreview'>
            <div className='cardHead'><h3>Quote preview</h3></div>
            <div className='cardBody'>
              <div className='svcPricePreviewForm'>
                <Field label='Service'>
                  <select className='input inputCompact' value={previewForm.service_code} onChange={(e) => setPreviewForm((f) => ({ ...f, service_code: e.target.value }))}>
                    <option value='survey'>Survey</option>
                    <option value='interview'>Interview</option>
                  </select>
                </Field>
                <Field label='Contacts'>
                  <input className='input inputCompact' type='number' value={previewForm.recipient_count} onChange={(e) => setPreviewForm((f) => ({ ...f, recipient_count: e.target.value }))} />
                </Field>
                {previewForm.service_code === 'interview' ? (
                  <Field label='Delivery'>
                    <select className='input inputCompact' value={previewForm.delivery} onChange={(e) => setPreviewForm((f) => ({ ...f, delivery: e.target.value }))}>
                      <option value='ai_call'>AI call</option>
                      <option value='zoom'>Zoom</option>
                    </select>
                  </Field>
                ) : null}
                <button type='button' className='btn primary' onClick={runPreview}>Calculate</button>
              </div>
              {preview ? (
                <div className='svcPricePreviewResult'>
                  <strong>{preview.total_gbp}</strong> for {preview.recipient_count} contacts
                  <ul>{(preview.lines || []).map((l, i) => <li key={i}>{l.detail || l.label}</li>)}</ul>
                </div>
              ) : null}
            </div>
          </section>
        </div>
      ) : null}
    </div>
  )
}
