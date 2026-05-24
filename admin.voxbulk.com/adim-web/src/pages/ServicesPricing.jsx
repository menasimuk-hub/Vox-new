import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { apiFetch } from '../lib/api'

const SURVEY_CHANNELS = [
  { key: 'ai_call', label: 'AI call', icon: 'ti-phone' },
  { key: 'whatsapp', label: 'WhatsApp', icon: 'ti-brand-whatsapp' },
]

function money(pence) {
  return `£${(Number(pence || 0) / 100).toFixed(2)}`
}

function emptyPackage(channel) {
  return {
    channel,
    rule_type: 'bundle',
    label: '',
    bundle_size: 50,
    bundle_price_pence: 0,
    overage_unit_price_pence: 0,
    sort_order: 100,
    is_active: true,
    notes: '',
  }
}

function Toggle({ checked, onChange, label }) {
  return (
    <label className='svcPriceToggle' title={label}>
      <input type='checkbox' checked={Boolean(checked)} onChange={(e) => onChange(e.target.checked)} />
      <span className='svcPriceToggleUi' aria-hidden='true' />
      <span className='svcPriceToggleLabel'>{checked ? 'On' : 'Off'}</span>
    </label>
  )
}

function Field({ label, children, className = '' }) {
  return (
    <label className={`svcPriceField ${className}`.trim()}>
      <span>{label}</span>
      {children}
    </label>
  )
}

export default function ServicesPricing() {
  const [services, setServices] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [msg, setMsg] = useState('')
  const [preview, setPreview] = useState(null)
  const [previewForm, setPreviewForm] = useState({
    service_code: 'survey',
    recipient_count: 100,
    survey_channel: 'ai_call',
    package_id: '',
    delivery: 'ai_call',
  })
  const [savingRuleId, setSavingRuleId] = useState('')
  const [creating, setCreating] = useState('')
  const [surveyTab, setSurveyTab] = useState('ai_call')
  const [editingSetup, setEditingSetup] = useState(false)

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

  const surveyService = useMemo(() => services.find((s) => s.code === 'survey') || null, [services])
  const interviewService = useMemo(() => services.find((s) => s.code === 'interview') || null, [services])

  const surveyRules = useMemo(() => surveyService?.pricing_rules || [], [surveyService])
  const baseRule = useMemo(() => surveyRules.find((r) => r.channel === 'base') || null, [surveyRules])
  const channelPackages = useMemo(
    () =>
      surveyRules.filter(
        (r) => r.channel === surveyTab && r.rule_type === 'bundle',
      ),
    [surveyRules, surveyTab],
  )

  const patchSurveyService = (updater) => {
    setServices((rows) =>
      rows.map((svc) => {
        if (svc.code !== 'survey') return svc
        return updater(svc)
      }),
    )
  }

  const patchRule = (ruleId, field, value) => {
    patchSurveyService((svc) => ({
      ...svc,
      pricing_rules: (svc.pricing_rules || []).map((rule) =>
        rule.id === ruleId ? { ...rule, [field]: value } : rule,
      ),
    }))
  }

  const saveRule = async (rule) => {
    setSavingRuleId(rule.id)
    setError('')
    setMsg('')
    try {
      await apiFetch(`/admin/platform-services/pricing-rules/${encodeURIComponent(rule.id)}`, {
        method: 'PUT',
        body: JSON.stringify(rule),
      })
      await load()
      setMsg('Package saved.')
    } catch (e) {
      setError(e?.message || 'Save failed')
    } finally {
      setSavingRuleId('')
    }
  }

  const createPackage = async () => {
    if (!surveyService) return
    setCreating(surveyTab)
    setError('')
    setMsg('')
    try {
      const draft = emptyPackage(surveyTab)
      draft.label = surveyTab === 'whatsapp' ? 'WhatsApp package' : 'AI call package'
      await apiFetch(`/admin/platform-services/${encodeURIComponent(surveyService.id)}/pricing-rules`, {
        method: 'POST',
        body: JSON.stringify(draft),
      })
      await load()
      setMsg('New package added.')
    } catch (e) {
      setError(e?.message || 'Could not create package')
    } finally {
      setCreating('')
    }
  }

  const runPreview = async () => {
    setError('')
    setPreview(null)
    try {
      const options =
        previewForm.service_code === 'survey'
          ? {
              survey_channel: previewForm.survey_channel,
              ...(previewForm.package_id ? { package_id: previewForm.package_id } : {}),
            }
          : { delivery: previewForm.delivery }

      const res = await apiFetch('/admin/platform-services/quote-preview', {
        method: 'POST',
        body: JSON.stringify({
          service_code: previewForm.service_code,
          recipient_count: Number(previewForm.recipient_count) || 0,
          options,
        }),
      })
      setPreview(res)
    } catch (e) {
      setError(e?.message || 'Preview failed')
    }
  }

  const previewPackages = useMemo(() => {
    if (previewForm.service_code !== 'survey') return []
    return surveyRules.filter((r) => r.channel === previewForm.survey_channel && r.rule_type === 'bundle' && r.is_active !== false)
  }, [previewForm.service_code, previewForm.survey_channel, surveyRules])

  return (
    <div className='svcPricePage'>
      <div className='pageTop'>
        <div>
          <Link to='/billing/products' className='muted' style={{ fontSize: 13 }}>
            ← Products hub
          </Link>
          <h1 style={{ marginTop: 8 }}>Survey pricing</h1>
          <p className='muted'>Manage AI call and WhatsApp survey packages, setup fee, and overage rates.</p>
        </div>
        <div className='actions'>
          <button type='button' className='btn soft' onClick={load} disabled={loading}>
            Refresh
          </button>
        </div>
      </div>

      {error ? <div className='note noteWarn svcPriceNote'>{error}</div> : null}
      {msg ? <div className='note svcPriceNote'>{msg}</div> : null}
      {loading ? <div className='card'><div className='cardBody muted'>Loading…</div></div> : null}

      {!loading && surveyService ? (
        <div className='svcPriceLayout'>
          {/* SETUP FEE */}
          <section className='card svcPriceService'>
            <div className='svcPriceServiceHead'>
              <div>
                <h3>Setup fee</h3>
                <p className='muted'>One-time charge per survey order</p>
              </div>
            </div>

            {baseRule ? (
              <div className='svcPriceSetupRow'>
                {!editingSetup ? (
                  <div className='svcPriceSetupDisplay'>
                    <div className='svcPriceSetupValue'>{money(baseRule.base_fee_pence)}</div>
                    <div className='svcPriceSetupLabel'>{baseRule.label || 'Setup fee'}</div>
                    <button type='button' className='btn soft bsm' onClick={() => setEditingSetup(true)}>
                      Edit
                    </button>
                  </div>
                ) : (
                  <div className='svcPriceSetupEdit'>
                    <Field label='Label'>
                      <input className='input inputCompact' value={baseRule.label || ''} onChange={(e) => patchRule(baseRule.id, 'label', e.target.value)} />
                    </Field>
                    <Field label='Fee (pence)'>
                      <input className='input inputCompact' type='number' min={0} value={baseRule.base_fee_pence ?? 0} onChange={(e) => patchRule(baseRule.id, 'base_fee_pence', Number(e.target.value))} />
                    </Field>
                    <Field label='Active'>
                      <Toggle checked={baseRule.is_active !== false} onChange={(v) => patchRule(baseRule.id, 'is_active', v)} label='Setup fee active' />
                    </Field>
                    <div className='svcPriceSetupActions'>
                      <button type='button' className='btn primary bsm' disabled={savingRuleId === baseRule.id} onClick={() => saveRule(baseRule)}>
                        {savingRuleId === baseRule.id ? 'Saving…' : 'Save'}
                      </button>
                      <button type='button' className='btn soft bsm' onClick={() => setEditingSetup(false)}>
                        Cancel
                      </button>
                    </div>
                  </div>
                )}
              </div>
            ) : null}
          </section>

          {/* PACKAGES */}
          <section className='card svcPriceService'>
            <div className='svcPriceServiceHead'>
              <div>
                <h3>Survey packages</h3>
                <p className='muted'>Choose channel and manage bundle sizes, prices, and overage rates.</p>
              </div>
              <span className='pill p-cyan'>{surveyRules.filter(r => r.rule_type === 'bundle').length} packages</span>
            </div>

            <div className='svcPriceChannelTabs' role='tablist'>
              {SURVEY_CHANNELS.map(({ key, label, icon }) => (
                <button
                  key={key}
                  type='button'
                  role='tab'
                  aria-selected={surveyTab === key}
                  className={`svcPriceChannelTab${surveyTab === key ? ' active' : ''}`}
                  onClick={() => setSurveyTab(key)}
                >
                  <i className={`ti ${icon}`} />
                  {label}
                  <span className='svcPriceChannelCount'>
                    {surveyRules.filter((r) => r.channel === key && r.rule_type === 'bundle').length}
                  </span>
                </button>
              ))}
            </div>

            <div className='svcPricePackageToolbar'>
              <span className='muted'>Bundle size, price, and extra-contact overage for {surveyTab === 'whatsapp' ? 'WhatsApp' : 'AI call'} surveys.</span>
              <button type='button' className='btn soft bsm' disabled={creating === surveyTab} onClick={createPackage}>
                {creating === surveyTab ? 'Adding…' : 'Add package'}
              </button>
            </div>

            <div className='svcPricePackageCards'>
              {channelPackages.map((rule) => (
                <div key={rule.id} className={`svcPricePackageCard${rule.is_active === false ? ' isOff' : ''}`}>
                  <div className='svcPricePackageHeader'>
                    <input className='svcPriceCardInput svcPriceCardInputLabel' value={rule.label || ''} onChange={(e) => patchRule(rule.id, 'label', e.target.value)} placeholder='Package label' />
                    <Toggle checked={rule.is_active !== false} onChange={(v) => patchRule(rule.id, 'is_active', v)} label={`${rule.label || 'Package'} active`} />
                  </div>

                  <div className='svcPriceCardBody'>
                    <div className='svcPriceCardField'>
                      <label>Bundle size</label>
                      <input className='input inputCompact' type='number' min={1} value={rule.bundle_size ?? ''} onChange={(e) => patchRule(rule.id, 'bundle_size', Number(e.target.value) || null)} />
                    </div>
                    <div className='svcPriceCardField'>
                      <label>Price (pence)</label>
                      <input className='input inputCompact' type='number' min={0} value={rule.bundle_price_pence ?? ''} onChange={(e) => patchRule(rule.id, 'bundle_price_pence', Number(e.target.value) || null)} />
                      {rule.bundle_size ? <span className='svcPriceCardCalc'>£{((Number(rule.bundle_price_pence || 0) / 100) / (Number(rule.bundle_size) || 1)).toFixed(2)} each</span> : null}
                    </div>
                    <div className='svcPriceCardField'>
                      <label>Overage per contact (pence)</label>
                      <input className='input inputCompact' type='number' min={0} value={rule.overage_unit_price_pence ?? ''} onChange={(e) => patchRule(rule.id, 'overage_unit_price_pence', Number(e.target.value) || null)} />
                    </div>
                    <div className='svcPriceCardField'>
                      <label>Sort order</label>
                      <input className='input inputCompact' type='number' value={rule.sort_order ?? 100} onChange={(e) => patchRule(rule.id, 'sort_order', Number(e.target.value) || 100)} />
                    </div>
                  </div>

                  <button type='button' className='btn primary bsm svcPriceCardSave' disabled={savingRuleId === rule.id} onClick={() => saveRule(rule)}>
                    {savingRuleId === rule.id ? 'Saving…' : 'Save package'}
                  </button>
                </div>
              ))}
              {!channelPackages.length ? (
                <div className='svcPriceEmptyState'>
                  <p className='muted'>No packages for this channel yet. Click "Add package" to get started.</p>
                </div>
              ) : null}
            </div>
          </section>

          {interviewService ? (
            <section className='card svcPriceService svcPriceServiceSecondary'>
              <div className='svcPriceServiceHead'>
                <div>
                  <h3>Interview pricing</h3>
                  <p className='muted'>Separate from survey packages.</p>
                </div>
                <span className='pill p-cyan'>{interviewService.code}</span>
              </div>
              <div className='svcPriceRuleList'>
                {(interviewService.pricing_rules || []).map((rule) => (
                  <div key={rule.id} className='svcPriceRuleCompact'>
                    <strong>{rule.label}</strong>
                    <span className='muted'>{rule.channel} · {money(rule.unit_price_pence)}/person</span>
                  </div>
                ))}
              </div>
            </section>
          ) : null}

          <section className='card svcPricePreview'>
            <div className='cardHead'><h3>Quote preview</h3></div>
            <div className='cardBody'>
              <div className='svcPricePreviewGrid'>
                <Field label='Service'>
                  <select className='input inputCompact' value={previewForm.service_code} onChange={(e) => setPreviewForm((f) => ({ ...f, service_code: e.target.value }))}>
                    <option value='survey'>Survey</option>
                    <option value='interview'>Interview</option>
                  </select>
                </Field>
                <Field label='Contacts'>
                  <input className='input inputCompact' type='number' min={0} value={previewForm.recipient_count} onChange={(e) => setPreviewForm((f) => ({ ...f, recipient_count: e.target.value }))} />
                </Field>
                {previewForm.service_code === 'survey' ? (
                  <>
                    <Field label='Channel'>
                      <select className='input inputCompact' value={previewForm.survey_channel} onChange={(e) => setPreviewForm((f) => ({ ...f, survey_channel: e.target.value, package_id: '' }))}>
                        <option value='ai_call'>AI call</option>
                        <option value='whatsapp'>WhatsApp</option>
                      </select>
                    </Field>
                    <Field label='Package (optional)'>
                      <select className='input inputCompact' value={previewForm.package_id} onChange={(e) => setPreviewForm((f) => ({ ...f, package_id: e.target.value }))}>
                        <option value=''>Auto pick best fit</option>
                        {previewPackages.map((pkg) => (
                          <option key={pkg.id} value={pkg.id}>
                            {pkg.label} ({pkg.bundle_size} @ {money(pkg.bundle_price_pence)})
                          </option>
                        ))}
                      </select>
                    </Field>
                  </>
                ) : (
                  <Field label='Delivery'>
                    <select className='input inputCompact' value={previewForm.delivery} onChange={(e) => setPreviewForm((f) => ({ ...f, delivery: e.target.value }))}>
                      <option value='ai_call'>AI call</option>
                      <option value='zoom'>Zoom</option>
                    </select>
                  </Field>
                )}
              </div>
              <div className='actions svcPricePreviewActions'>
                <button type='button' className='btn primary bsm' onClick={runPreview}>Calculate quote</button>
              </div>
              {preview ? (
                <div className='svcPricePreviewResult'>
                  <strong>{preview.total_gbp}</strong>
                  {preview.survey_channel ? <span className='muted'> · {preview.survey_channel}</span> : null}
                  {' '}for {preview.recipient_count} contacts
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
